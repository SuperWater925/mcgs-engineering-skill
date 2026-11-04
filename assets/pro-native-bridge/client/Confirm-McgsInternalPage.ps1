param(
    [Parameter(Mandatory=$true)][string]$NativeReceipt,
    [Parameter(Mandatory=$true)][string]$Output,
    [Parameter(Mandatory=$true)][int]$ExpectedPageId,
    [Parameter(Mandatory=$true)][string]$ExpectedPageName,
    [switch]$Activate
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $Output) { throw 'The visibility receipt must be a new file.' }
$capture = Get-Content -LiteralPath $NativeReceipt -Raw | ConvertFrom-Json -AsHashtable
if ($capture.ok -ne $true -or $capture.write_attempted -ne $false) {
    throw 'Use a successful current read-only native receipt.'
}
$viewStates = @($capture.action_preimages | ForEach-Object { $_.before } | Where-Object {
    $_.ContainsKey('target_open') -and $_.page.page_id -eq $ExpectedPageId -and $_.page.page_name -eq $ExpectedPageName
})
if ($viewStates.Count -ne 1 -or $viewStates[0].target_open -ne $true) {
    throw 'The exact native page must already have a designer frame. This helper never opens/retries a page.'
}
$viewState = $viewStates[0]
$mcgsProcessId = [int]$capture.process_id
$mcgsProcess = [System.Diagnostics.Process]::GetProcessById($mcgsProcessId)
if ($mcgsProcess.StartTime.ToUniversalTime().ToFileTimeUtc() -ne [long]$capture.creation_filetime) {
    throw 'The native process generation changed.'
}
$mcgsImage = $mcgsProcess.MainModule.FileName
if ((Get-FileHash -LiteralPath $mcgsImage -Algorithm SHA256).Hash.ToLowerInvariant() -ne $capture.editor_image_sha256) {
    throw 'The native image differs from the current ABI-bound receipt.'
}
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class McgsPageVisibility {
  [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left,Top,Right,Bottom; }
  [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr OpenProcess(uint access,bool inherit,int pid);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool ReadProcessMemory(IntPtr process,IntPtr address,byte[] buffer,UIntPtr bytes,out UIntPtr read);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
  [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr hwnd);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hwnd);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hwnd);
  [DllImport("user32.dll")] public static extern IntPtr GetParent(IntPtr hwnd);
  [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr hwnd,uint flags);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd,out uint pid);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr hwnd,StringBuilder name,int length);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr hwnd,StringBuilder text,int length);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hwnd,out Rect rect);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr hwnd,uint message,IntPtr wparam,IntPtr lparam);
  public static bool Owned(IntPtr hwnd,uint expected) { uint actual; GetWindowThreadProcessId(hwnd,out actual); return IsWindow(hwnd)&&actual==expected; }
  public static string ClassName(IntPtr hwnd) { var b=new StringBuilder(256); GetClassName(hwnd,b,b.Capacity); return b.ToString(); }
  public static string Text(IntPtr hwnd) { var b=new StringBuilder(2048); GetWindowText(hwnd,b,b.Capacity); return b.ToString(); }
  public static IntPtr CurrentFrameHwnd(int pid,long frame) {
    // The current page-view ABI validates C0FrmChild. Read only its existing
    // x86 CWnd HWND field at+0x20, exactly as the native reader does. Never write
    // process memory, create a frame, or fall back to a guessed title/handle.
    IntPtr process=OpenProcess(0x0010,false,pid);
    if(process==IntPtr.Zero) throw new InvalidOperationException("Cannot read the existing frame HWND.");
    try { byte[] b=new byte[4]; UIntPtr read;
      if(!ReadProcessMemory(process,new IntPtr(checked(frame+0x20)),b,new UIntPtr(4),out read)||read.ToUInt64()!=4)
        throw new InvalidOperationException("Existing x86 CWnd HWND field could not be read exactly.");
      return new IntPtr(unchecked((long)BitConverter.ToUInt32(b,0)));
    } finally { CloseHandle(process); }
  }
}
'@
$frameAddress = [Convert]::ToInt64(($viewState.target_frame -replace '^0x',''),16)
$frameHwnd = [McgsPageVisibility]::CurrentFrameHwnd($mcgsProcessId,$frameAddress)
$mdiHwnd = [McgsPageVisibility]::GetParent($frameHwnd)
$mainHwnd = [McgsPageVisibility]::GetAncestor($frameHwnd,2)
foreach ($handle in @($frameHwnd,$mdiHwnd,$mainHwnd)) {
    if (-not [McgsPageVisibility]::Owned($handle,[uint32]$mcgsProcessId)) { throw 'The native frame/window ownership changed.' }
}
if ([McgsPageVisibility]::ClassName($mdiHwnd) -ne 'MDIClient') { throw 'The native page is not under the expected MDI client.' }
$beforeActive = [McgsPageVisibility]::SendMessage($mdiHwnd,0x0229,[IntPtr]::Zero,[IntPtr]::Zero)
if ($Activate) {
    if ([McgsPageVisibility]::IsIconic($frameHwnd)) {
        [void][McgsPageVisibility]::SendMessage($mdiHwnd,0x0223,$frameHwnd,[IntPtr]::Zero)
    }
    if ($beforeActive -ne $frameHwnd) {
        [void][McgsPageVisibility]::SendMessage($mdiHwnd,0x0222,$frameHwnd,[IntPtr]::Zero)
    }
}
$actualActive = [McgsPageVisibility]::SendMessage($mdiHwnd,0x0229,[IntPtr]::Zero,[IntPtr]::Zero)
$passed = ($actualActive -eq $frameHwnd) -and [McgsPageVisibility]::Owned($frameHwnd,[uint32]$mcgsProcessId) -and ([McgsPageVisibility]::GetParent($frameHwnd) -eq $mdiHwnd)
$result = [ordered]@{
    schema=1; ok=$passed; process_id=$mcgsProcessId; creation_filetime=$capture.creation_filetime;
    page_id=$ExpectedPageId; page_name=$ExpectedPageName; native_receipt=(Resolve-Path -LiteralPath $NativeReceipt).Path;
    native_receipt_sha256=(Get-FileHash -LiteralPath $NativeReceipt -Algorithm SHA256).Hash.ToLowerInvariant();
    native_frame_object=$viewState.target_frame; frame_hwnd=('0x{0:X}' -f $frameHwnd.ToInt64());
    mdi_client_hwnd=('0x{0:X}' -f $mdiHwnd.ToInt64()); main_hwnd=('0x{0:X}' -f $mainHwnd.ToInt64());
    before_active_mdi_child=('0x{0:X}' -f $beforeActive.ToInt64()); active_mdi_child=('0x{0:X}' -f $actualActive.ToInt64());
    exact_page_is_active=($actualActive -eq $frameHwnd); frame_title=[McgsPageVisibility]::Text($frameHwnd);
    activation_requested=[bool]$Activate; no_project_content_write=$true; no_input_injection=$true;
    no_system_foreground_requirement=$true; no_automatic_retry=$true
}
$result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Output -Encoding utf8NoBOM
$result | ConvertTo-Json -Depth 6 -Compress
if (-not $passed) { throw 'The exact native page is not the active MDI child. Do not write the project.' }
