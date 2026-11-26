param([Parameter(Mandatory=$true)][int]$EditorPid, [Parameter(Mandatory=$true)][long]$ControlHwnd)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,Accessibility
$node=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$ControlHwnd)
if ($node.Current.ProcessId -ne $EditorPid) { throw 'Selected control no longer belongs to the editor.' }
$uiaError=$null
try {
    $all=$node.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
    $rows=@(foreach($child in $all) {
        $info=$child.Current
        if ($info.ProcessId -ne $EditorPid -or $info.IsOffscreen -or $info.IsPassword) { continue }
        $type=$info.ControlType.ProgrammaticName
        if ($type -notin @('ControlType.ListItem','ControlType.DataItem','ControlType.TreeItem')) { continue }
        $cells=@(foreach ($cell in $child.FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition)) {
            $current=$cell.Current
            if ($current.ProcessId -eq $EditorPid -and !$current.IsOffscreen -and !$current.IsPassword -and
                $current.ControlType.ProgrammaticName -eq 'ControlType.Text' -and $current.Name) { $current.Name }
        })
        if ($info.Name -or $cells.Count) {
            $parts=@($cells)
            if ($info.Name -and $info.Name -notin $parts) { $parts=@($info.Name)+$parts }
            $value=$parts -join "`t"
            [ordered]@{text=$value;cells=$cells;type=$type;runtime_id=@($child.GetRuntimeId());provider='UIA'}
        }
    })
}
catch {
    $uiaError=$_.Exception.Message
    $rows=@()
}
if (!$rows.Count) {
    # Use the documented MSAA client object for this HWND. Some classic list
    # controls expose their rows as integer child IDs rather than UIA nodes.
    $collectionReference=Join-Path $PSHOME 'ref/System.Collections.dll'
    Add-Type -ReferencedAssemblies @([Accessibility.IAccessible].Assembly.Location,$collectionReference) `
        -CompilerOptions '/nowarn:1701' -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using Accessibility;
public static class DiagnosticAccessibility {
    public sealed class Row {
        public string Text;
        public string Description;
        public int Role;
        public int[] Path;
    }

    [DllImport("oleacc.dll")]
    private static extern int AccessibleObjectFromWindow(IntPtr window, uint id, ref Guid iid,
        [MarshalAs(UnmanagedType.Interface)] out IAccessible result);
    [DllImport("oleacc.dll")]
    private static extern int AccessibleChildren(IAccessible parent, int first, int count,
        [Out, MarshalAs(UnmanagedType.LPArray, SizeParamIndex=2, ArraySubType=UnmanagedType.Struct)] object[] children,
        out int returned);

    public static Row[] ReadRows(IntPtr window) {
        var iid = typeof(IAccessible).GUID;
        IAccessible client;
        int result = AccessibleObjectFromWindow(window, 0xFFFFFFFC, ref iid, out client);
        if (result != 0 || client == null)
            throw new InvalidOperationException(string.Format("AccessibleObjectFromWindow failed (HRESULT 0x{0:X8})", result));
        var rows = new List<Row>();
        Visit(client, new int[0], rows);
        return rows.ToArray();
    }

    private static string ReadDescription(IAccessible owner, object childId) {
        try {
            return owner.get_accDescription(childId);
        } catch (NotImplementedException) {
            return null;
        } catch (COMException error) {
            if (error.ErrorCode == unchecked((int)0x80020003))
                return null;
            throw;
        }
    }

    private static void Visit(IAccessible parent, int[] path, List<Row> rows) {
        if (path.Length > 32)
            throw new InvalidOperationException("Accessibility tree too deep");
        int count = parent.accChildCount;
        for (int start = 0; start < count; start += 64) {
            int expected = Math.Min(64, count - start);
            var children = new object[expected];
            int received;
            int result = AccessibleChildren(parent, start, expected, children, out received);
            if (result != 0 || received != expected)
                throw new InvalidOperationException(string.Format(
                    "AccessibleChildren returned HRESULT 0x{0:X8}, {1} of {2} children", result, received, expected));
            for (int index = 0; index < received; ++index) {
                object child = children[index];
                var component = child as IAccessible;
                if (component == null && (!(child is int) || (int)child <= 0))
                    continue;
                var address = new int[path.Length + 1];
                Array.Copy(path, address, path.Length);
                address[path.Length] = start + index;
                var owner = component ?? parent;
                object childId = component != null ? (object)0 : child;
                object state = owner.get_accState(childId);
                if (state == null || (Convert.ToInt32(state) & 0x20018000) != 0)
                    continue;
                object roleValue = owner.get_accRole(childId);
                int role = roleValue is int ? (int)roleValue : -1;
                if (role == 0x1C || role == 0x22 || role == 0x24) {
                    string name = owner.get_accName(childId);
                    string description = ReadDescription(owner, childId);
                    if (!string.IsNullOrEmpty(name) || !string.IsNullOrEmpty(description))
                        rows.Add(new Row { Text = name, Description = description, Role = role, Path = address });
                } else if (component != null) {
                    Visit(component, address, rows);
                }
            }
        }
    }
}
"@
    $rows=@(foreach ($entry in [DiagnosticAccessibility]::ReadRows([IntPtr]$ControlHwnd)) {
        $row=[ordered]@{text=$entry.Text;type="MSAA.Role.$($entry.Role)";accessible_path=@($entry.Path);provider='MSAA'}
        if ($entry.Description -and $entry.Description -cne $entry.Text) {
            $row.description=$entry.Description
            $row.text=(@($entry.Text,$entry.Description) | Where-Object { $_ }) -join "`t"
        }
        $row
    })
    if (!$rows.Count -and $uiaError) { throw "UIA: $uiaError. MSAA returned no visible rows." }
}
if ($node.Current.ProcessId -ne $EditorPid) { throw 'Selected control changed' }
[ordered]@{rows=$rows} | ConvertTo-Json -Compress -Depth 8
