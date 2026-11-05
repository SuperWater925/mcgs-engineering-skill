param(
 [Parameter(Mandatory=$true)][string]$PreparedRoot,
 [string]$CscX86=(Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'),
 [string]$CscX64=(Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
 [string]$Python='python'
)
$ErrorActionPreference='Stop'
$boot=(Resolve-Path -LiteralPath $PreparedRoot).Path
function Hash([string]$p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
function Regular([string]$p){if(-not(Test-Path -LiteralPath $p -PathType Leaf)){throw "Missing regular input: $p"};for($d=Get-Item -LiteralPath $p;$null-ne$d;$d=$(if($d-is[IO.FileInfo]){$d.Directory}else{$d.Parent})){if(($d.Attributes-band[IO.FileAttributes]::ReparsePoint)-ne0){throw "Reparse input: $p"}}}
function Run([string]$exe,[string[]]$a){& $exe @a;if($LASTEXITCODE-ne0){throw "Own-source build helper failed ($LASTEXITCODE): $exe"}}
Regular $CscX86;Regular $CscX64
$record=Get-Content -LiteralPath (Join-Path $boot 'preparation-record.json') -Raw -Encoding UTF8|ConvertFrom-Json
$configFile=Join-Path $boot 'McgsInternalBridge.bridge.json'
Regular $configFile
$cfg=Get-Content -LiteralPath $configFile -Raw -Encoding UTF8|ConvertFrom-Json
if((Hash $configFile)-ne$record.config_sha256){throw 'Prepared configuration changed.'}
if([IO.Path]::GetFullPath($record.bootstrap_root)-ine$boot){throw 'Prepared root differs.'}
foreach($r in $record.sources){$file=Join-Path (Join-Path $boot 'bound-source') $r.source_name;Regular $file;if((Hash $file)-ne$r.bound_sha256){throw "Bound source changed: $file"}}
foreach($name in @('McgsInternalBridge.dll','McgsInternalBridge.tlb','McgsBridgeSession.exe','build-manifest.json','native-wrapper','own-build-tools')){if(Test-Path -LiteralPath (Join-Path $boot $name)){throw "Build output already exists; prepare a new root: $name"}}
$tools=Join-Path $boot 'own-build-tools';New-Item -ItemType Directory -Path $tools|Out-Null
$src=Join-Path $boot 'bound-source';$dll=Join-Path $boot 'McgsInternalBridge.dll';$tlb=Join-Path $boot 'McgsInternalBridge.tlb'
$sources=@('Bootstrap.cs','BootstrapLayout.cs','EngineLoader.cs','DurableQueuePump.cs','NullSafeDispatch.cs')|ForEach-Object{Join-Path $src $_}
Run $CscX86 (@('/nologo','/target:library','/platform:x86','/codepage:65001','/optimize+','/reference:System.Web.Extensions.dll','/reference:System.Windows.Forms.dll',('/out:'+$dll))+$sources)
# These executables process only this own assembly/type library. No COM class
# registration, bridge callback, vendor DLL or engineering process is invoked.
$exporter=Join-Path $tools 'ExportHostTypeLib-x86.exe'
Run $CscX86 @('/nologo','/platform:x86','/codepage:65001',('/out:'+$exporter),(Join-Path $src 'ExportHostTypeLib.cs'))
Run $exporter @($dll,$tlb)
$embedder=Join-Path $tools 'EmbedTypeLib-x64.exe'
Run $CscX64 @('/nologo','/platform:x64','/codepage:65001',('/out:'+$embedder),(Join-Path $src 'EmbedTypeLib.cs'))
Run $embedder @($dll,$tlb)
$dumper=Join-Path $tools 'TypeLibDump-x64.exe'
Run $CscX64 @('/nologo','/platform:x64','/codepage:65001','/reference:System.Web.Extensions.dll',('/out:'+$dumper),(Join-Path $src 'TypeLibDump.cs'))
$readback=& $dumper $dll
if($LASTEXITCODE-ne0){throw 'Own TYPELIB readback failed.'}
$readbackText=$readback-join"`n";$meta=$readbackText|ConvertFrom-Json
$co=@($meta.types|Where-Object kind -eq 'TKIND_COCLASS')
$expectedProgId='McgsInternalBridge.AddInObj';$wrapperName='McgsInternalLoader.dll'
if($null-ne$cfg.cold_com_identity){$identity=$cfg.cold_com_identity;$expectedProgId=$identity.progid;$wrapperName=$identity.native_wrapper_file_name;if(([Guid]$meta.guid)-ne([Guid]$identity.type_library_guid)-or$co.Count-ne1-or([Guid]$co[0].guid)-ne([Guid]$identity.class_guid)){throw 'Own typelib GUID differs from this deployment-scoped configuration.'}}
if($co.Count-ne1-or@($co[0].implemented_types).Count-ne1-or$co[0].implemented_types[0].name-ne'IAddInObj'-or($meta.name+'.'+$co[0].name)-ne$expectedProgId){throw 'Own typelib no longer matches the configured native scanner contract.'}
$iface=@($meta.types|Where-Object name -eq 'IAddInObj')[0]
if($null-ne$cfg.cold_com_identity-and([Guid]$iface.guid)-ne([Guid]$identity.interface_guid)){throw 'Own callback interface GUID differs from this deployment.'}
$expected=@{SvrMenuCommand=@('VT_BSTR','VT_I4','VT_DISPATCH');SvrStgySetOperator=@('VT_BSTR','VT_BSTR','VT_I4','VT_DISPATCH','VT_DISPATCH','VT_I4');SvrStgyRunOperator=@('VT_DISPATCH','VT_DISPATCH');SvrCheck=@('VT_DISPATCH','VT_I4')}
foreach($name in $expected.Keys){$m=@($iface.functions|Where-Object name -eq $name);if($m.Count-ne1-or$m[0].return-ne'VT_I4'-or@($m[0].parameters).Count-ne$expected[$name].Count){throw "Unexpected own callback: $name"};for($i=0;$i-lt$expected[$name].Count;$i++){if($m[0].parameters[$i].type.kind-ne'VT_PTR'-or$m[0].parameters[$i].type.element-ne$expected[$name][$i]){throw "Unexpected own callback parameter: $name/$i"}}}
[IO.File]::WriteAllText((Join-Path $boot 'bootstrap-embedded-typelib.json'),$readbackText,(New-Object Text.UTF8Encoding($false)))
Run $CscX86 @('/nologo','/target:winexe','/platform:x86','/codepage:65001','/reference:System.Web.Extensions.dll',('/out:'+(Join-Path $boot 'McgsBridgeSession.exe')),(Join-Path $src 'BridgeSessionLauncher.cs'),(Join-Path $src 'BootstrapLayout.cs'))
Run $Python @((Join-Path $boot 'build_native_wrapper.py'),'--bootstrap-root',$boot,'--registration-contract',(Join-Path $boot 'prepared-registration-contract.json'))
$files=@('McgsInternalBridge.dll','McgsInternalBridge.tlb','McgsBridgeSession.exe','McgsInternalBridge.bridge.json','loader-capability.json','hklm-registration-plan.json','prepared-registration-contract.json',('native-wrapper\'+$wrapperName))|ForEach-Object{$f=Join-Path $boot $_;[ordered]@{relative_path=$_;sha256=(Hash $f);bytes=(Get-Item -LiteralPath $f).Length}}
$manifest=[ordered]@{schema=1;state='built_own_sources_only_not_installed';bootstrap_root=$boot;bootstrap_scope_sha256=(Hash $configFile);files=@($files);typelib_callbacks_verified=$true;vendor_code_loaded=$false;bridge_callback_executed=$false;registry_written=$false;deployed=$false;host_started=$false;new_machine_native_compatibility_verified=$false;utc=[DateTime]::UtcNow.ToString('o')}
$text=$manifest|ConvertTo-Json -Depth 20
$path=Join-Path $boot 'build-manifest.json';$bytes=[Text.Encoding]::UTF8.GetBytes($text);$f=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);try{$f.Write($bytes,0,$bytes.Length);$f.Flush($true)}finally{$f.Dispose()}
$text
