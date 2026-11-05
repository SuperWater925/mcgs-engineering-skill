using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using Microsoft.Win32;
using McgsInternalBridge;

// A normal application launcher. No injection, window messages or host memory writes.
internal static class BridgeSessionLauncher
{
    [STAThread]
    private static int Main(string[] args)
    {
        if(args.Length!=1||(args[0]!="--start"&&args[0]!="--plan"))return 2;
        BootstrapLayout.Check();
        if(args[0]=="--plan"){string output=Path.Combine(BootstrapLayout.RuntimeRoot,"launcher-plan-"+Guid.NewGuid().ToString("N")+".json");BootstrapLayout.OwnedRuntime(output);Directory.CreateDirectory(BootstrapLayout.RuntimeRoot);WriteJson(output,new Dictionary<string,object>{{"schema",1},{"action","plan"},{"bootstrap_scope_sha256",BootstrapLayout.ConfigurationSha256},{"editor",BootstrapLayout.EditorFile},{"runtime_root",BootstrapLayout.RuntimeRoot},{"startup_registry_path",BootstrapLayout.StartupRegistryPath},{"registry_written",false},{"process_started",false}});return 0;}
        // Share the gate only where the same editor or original Startup key can
        // race. Independent installations have independent cold-launch gates.
        string gateKey;using(var hash=System.Security.Cryptography.SHA256.Create())gateKey=BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(BootstrapLayout.StartupRegistryPath.ToUpperInvariant()))).Replace("-","");
        using (var gate = new Mutex(false, @"Local\McgsInternalBridgeSessionLauncher_"+gateKey))
        {
            bool owned = false;
            try
            {
                try { owned = gate.WaitOne(0); }
                catch (AbandonedMutexException) { owned = true; }
                if (!owned) return 2;
                return Run();
            }
            finally { if (owned) gate.ReleaseMutex(); }
        }
    }

    private static int Run()
    {
        string ownDir = BootstrapLayout.BootstrapRoot;
        string logs=Path.Combine(BootstrapLayout.RuntimeRoot,"launcher");BootstrapLayout.OwnedRuntime(logs);Directory.CreateDirectory(logs);
        string log = Path.Combine(logs, "session-launch-result.json");
        string transactionPath = Path.Combine(logs, "session-start-" + DateTime.UtcNow.ToString("yyyyMMddTHHmmssfff") + "-" + Guid.NewGuid().ToString("N") + ".json");
        string startup = BootstrapLayout.StartupRegistryPath;
        string startupValue = BootstrapLayout.StartupValueName;
        int scanValue = BootstrapLayout.StartupScanValue;
        int original = -1;
        bool prepared = false;
        var record = new Dictionary<string, object>();
        try
        {
            string pro = BootstrapLayout.EditorFile;
            BootstrapLayout.Check();
            if (!File.Exists(pro)) throw new FileNotFoundException("Installed Pro engineering executable is missing.");
            if (BoundEditorRunning())
                throw new InvalidOperationException("The bound editor is already running. Close it normally before starting a cold bridge session.");
            if (!File.Exists(BootstrapLayout.Regular(Path.Combine(ownDir, "McgsInternalBridge.dll"))))
                throw new FileNotFoundException("This launcher must remain next to the installed bridge bootstrap.");
            // The child inherits this token. Do not silently elevate; confirm that
            // the native wrapper can access only its already installed roots.
            using(var machine=RegistryKey.OpenBaseKey(BootstrapLayout.ColdRegistryHive=="HKCU"?RegistryHive.CurrentUser:RegistryHive.LocalMachine,RegistryView.Registry32))foreach(string root in BootstrapLayout.ColdRegistrationRoots)using(var installed=machine.OpenSubKey(root,true)){if(installed==null)throw new InvalidOperationException("Install the exact private native-wrapper registration before starting the session.");}
            using (RegistryKey user = RegistryKey.OpenBaseKey(RegistryHive.CurrentUser, RegistryView.Registry32))
            using (RegistryKey key = user.OpenSubKey(startup, true))
            {
                if (key == null || key.GetValueKind(startupValue) != RegistryValueKind.DWord)
                    throw new InvalidOperationException("Expected the configured existing startup DWORD; no key will be created.");
                original = (int)key.GetValue(startupValue);
                if (!BootstrapLayout.AcceptsStartupValue(original)) throw new InvalidOperationException("Current startup state differs from the configured loader protocol.");
                record["bootstrap_scope_sha256"]=BootstrapLayout.ConfigurationSha256;
                record["utc"] = DateTime.UtcNow.ToString("o");
                record["registry_hive"] = "HKEY_CURRENT_USER";
                record["registry_view"] = 32;
                record["registry_path"] = startup;
                record["value_name"] = startupValue;
                record["before"] = original;
                record["requested"] = scanValue;
                record["pro_was_closed"] = true;
                record["status"] = "prepared_before_write";
                WriteJson(transactionPath, record);
                key.SetValue(startupValue, scanValue, RegistryValueKind.DWord);
                prepared = true;
                key.Flush();
                if ((int)key.GetValue(startupValue) != scanValue) throw new IOException("Native startup preparation readback failed.");
            }
            // The supplied loader protocol selects one native cold scan.
            Process child = Process.Start(new ProcessStartInfo(pro)
            {
                WorkingDirectory = Path.GetDirectoryName(pro),
                UseShellExecute = false
            });
            record["status"] = "native_process_started";
            record["process_id"] = child.Id;
            record["native_arguments"] = "";
            record["note"] = "Only the configured existing per-user startup DWORD was prepared. Native scanner completion is observed separately; no executable patch.";
            WriteJson(transactionPath, record);
            record["ok"] = true;
            record["transaction"] = transactionPath;
            WriteJson(log, record);
            return 0;
        }
        catch (Exception error)
        {
            bool restored = false;
            if (prepared && BoundEditorDefinitelyClosed(record))
            {
                try
                {
                    using (RegistryKey user = RegistryKey.OpenBaseKey(RegistryHive.CurrentUser, RegistryView.Registry32))
                    using (RegistryKey key = user.OpenSubKey(startup, true))
                    {
                        if (key != null && key.GetValueKind(startupValue) == RegistryValueKind.DWord && (int)key.GetValue(startupValue) == scanValue)
                        { key.SetValue(startupValue, original, RegistryValueKind.DWord); key.Flush(); restored = true; }
                    }
                }
                catch (Exception restoreError) { record["restore_error"] = restoreError.Message; }
            }
            record["ok"] = false;
            record["status"] = "failed";
            record["message"] = error.Message;
            record["original_startup_count_restored"] = restored;
            WriteJson(transactionPath, record);
            WriteJson(log, record);
            return 1;
        }
    }

    private static void WriteJson(string path, object value)
    {
        File.WriteAllText(path, new JavaScriptSerializer().Serialize(value), new UTF8Encoding(false));
    }

    private static bool BoundEditorRunning()
    {
        string expected=BootstrapLayout.EditorFile;
        foreach(Process process in Process.GetProcessesByName(Path.GetFileNameWithoutExtension(expected)))using(process)
        {
            try
            {
                // Read PID/create identity around the path lookup so an exited
                // or replaced process is never accepted as evidence of absence.
                int pid=process.Id;DateTime created=process.StartTime.ToUniversalTime();
                string actual=process.MainModule.FileName;
                if(process.HasExited)continue;
                if(pid!=process.Id||created!=process.StartTime.ToUniversalTime())throw new InvalidOperationException("Editor process identity changed while checking its path.");
                if(BootstrapLayout.SamePath(actual,expected))return true;
            }
            catch(InvalidOperationException){if(process.HasExited)continue;throw;}
            catch(Exception error){throw new InvalidOperationException("Cannot inspect candidate editor PID "+process.Id+"; preserve Startup Count until its actual identity is known.",error);}
        }
        return false;
    }

    private static bool BoundEditorDefinitelyClosed(Dictionary<string,object> record)
    {
        try{return !BoundEditorRunning();}
        catch(Exception error){record["editor_identity_check_error"]=error.Message;return false;}
    }
}
