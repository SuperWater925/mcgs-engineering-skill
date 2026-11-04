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
        using (var gate = new Mutex(false, @"Local\McgsInternalBridgeSessionLauncher"))
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
        int original = -1;
        bool prepared = false;
        var record = new Dictionary<string, object>();
        try
        {
            string pro = BootstrapLayout.EditorFile;
            BootstrapLayout.Check();
            if (!File.Exists(pro)) throw new FileNotFoundException("Installed Pro engineering executable is missing.");
            if (Process.GetProcessesByName("McgsSetPro").Length != 0)
                throw new InvalidOperationException("Pro is already running. Close it normally before starting a bridge session.");
            if (!File.Exists(BootstrapLayout.Regular(Path.Combine(ownDir, "McgsInternalBridge.dll"))))
                throw new FileNotFoundException("This launcher must remain next to the installed bridge bootstrap.");
            // The child inherits this token. Do not silently elevate; confirm that
            // the native wrapper can access only its already installed roots.
            using(var machine=RegistryKey.OpenBaseKey(RegistryHive.LocalMachine,RegistryView.Registry32))foreach(string root in new[]{@"Software\Classes\CLSID\{52119C44-5875-4DA6-9F72-E97D2E2182B4}",@"Software\Classes\McgsInternalBridge.AddInObj",@"Software\Classes\TypeLib\{4D2519E0-CC21-4F82-A19C-1AF9801C64E1}"})using(var installed=machine.OpenSubKey(root,true)){if(installed==null)throw new InvalidOperationException("Install the exact private native-wrapper registration before starting the session.");}
            using (RegistryKey user = RegistryKey.OpenBaseKey(RegistryHive.CurrentUser, RegistryView.Registry32))
            using (RegistryKey key = user.OpenSubKey(startup, true))
            {
                if (key == null || key.GetValueKind("Count") != RegistryValueKind.DWord)
                    throw new InvalidOperationException("Expected the existing native Startup Count DWORD; no key will be created.");
                original = (int)key.GetValue("Count");
                if (original != 0 && original != 1) throw new InvalidOperationException("Unexpected native startup state.");
                record["bootstrap_scope_sha256"]=BootstrapLayout.ConfigurationSha256;
                record["utc"] = DateTime.UtcNow.ToString("o");
                record["registry_hive"] = "HKEY_CURRENT_USER";
                record["registry_view"] = 32;
                record["registry_path"] = startup;
                record["value_name"] = "Count";
                record["before"] = original;
                record["requested"] = 0;
                record["pro_was_closed"] = true;
                record["status"] = "prepared_before_write";
                WriteJson(transactionPath, record);
                key.SetValue("Count", 0, RegistryValueKind.DWord);
                prepared = true;
                key.Flush();
                if ((int)key.GetValue("Count") != 0) throw new IOException("Native startup preparation readback failed.");
            }
            // Count0 selects one native cold scan. /BuildIni would append a second catalog after warm loading.
            Process child = Process.Start(new ProcessStartInfo(pro)
            {
                WorkingDirectory = Path.GetDirectoryName(pro),
                UseShellExecute = false
            });
            record["status"] = "native_process_started";
            record["process_id"] = child.Id;
            record["native_arguments"] = "";
            record["note"] = "Only the existing per-user native startup Count is prepared. Pro normally returns it to1 during startup. No cache serialization or executable patch.";
            WriteJson(transactionPath, record);
            record["ok"] = true;
            record["transaction"] = transactionPath;
            WriteJson(log, record);
            return 0;
        }
        catch (Exception error)
        {
            bool restored = false;
            if (prepared && Process.GetProcessesByName("McgsSetPro").Length == 0)
            {
                try
                {
                    using (RegistryKey user = RegistryKey.OpenBaseKey(RegistryHive.CurrentUser, RegistryView.Registry32))
                    using (RegistryKey key = user.OpenSubKey(startup, true))
                    {
                        if (key != null && key.GetValueKind("Count") == RegistryValueKind.DWord && (int)key.GetValue("Count") == 0)
                        { key.SetValue("Count", original, RegistryValueKind.DWord); key.Flush(); restored = true; }
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
}
