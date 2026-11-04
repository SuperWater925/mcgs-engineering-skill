# First deployment / task change: own native bridge

This is the optional cold-start deployment entry; ordinary running Pro processes should use [hot attachment](../hot-attach/README.md). This entry prepares and builds the bridge only. It never edits a vendor DLL, opens an engineering project, or carries a user project/account/claim/dump. Preparation and build do not register COM, deploy into Addins, or start Pro. The existing live bridge is untouched.

## Explicit inputs

Supply absolute local paths: an existing owned `task_root`, fresh disjoint children `runtime_root` and `bootstrap_root`, the original `install_root`, exact `editor_executable`, `addins_directory`, `addins_ini_file`, and the **actual existing** per-user `startup_registry_path`. No drive-relative paths, network paths, reparse ancestors, guessed parent-directory layout, software release whitelist, or automatic installation search is used. A fresh task has fresh roots; previous claims are never copied or deleted.

`loader-capability.current.json` preserves the reference scanner/TYPELIB/callback protocol and historical evidence. Preparation binds the explicitly selected current executable without an author-file SHA admission list. For a different binary, the prepared contract declares the configured cold Addin protocol while retaining reference evidence separately and does not claim that its native scanner was already verified. Hot attachment uses its independent Windows hook / COM / UI-STA mechanism contract. Actual loading and business acceptance remain separate observations.

## File-only preparation and build

Run from this source entry directory, with the variables explicitly supplied for the intended machine. The startup registry key is an input from the actual loader configuration; it is not inferred from a displayed software version.

```powershell
python .\prepare_bootstrap.py `
  --task-root $TaskRoot --runtime-root $RuntimeRoot --bootstrap-root $BootstrapRoot `
  --install-root $InstallRoot --editor-executable $EditorExecutable `
  --addins-directory $AddinsDirectory --addins-ini-file $AddinsIniFile `
  --startup-registry-path $StartupRegistryPath `
  --loader-contract-file .\loader-capability.current.json

& "$BootstrapRoot\build_bootstrap.ps1" -PreparedRoot $BootstrapRoot -Python $PythonExecutable
```

Preparation accepts absent or empty bootstrap/runtime output roots and preserves initialized nonempty roots. It creates bound own sources, the sibling `McgsInternalBridge.bridge.json`, its compile-time SHA binding, and the exact three-root private HKLM/Registry32 registration plan. It does not create the queue root yet. The build uses the installed .NET Framework x86/x64 compilers (or explicit `-CscX86`/`-CscX64` paths), compiles the own shim and launcher, exports/normalizes/embeds its own TYPELIB/#1, checks its four callback signatures, and creates the own native x86 scanner adapter in pure Python. Type-library helper execution processes only the own assembly; no vendor module or bridge callback runs. Output `build-manifest.json` contains exact hashes and the uninstalled status.

The callback interface and private CLSID/ProgID stay the established bridge interface. The constructor is inert. Its original native UI callback captures the UI SynchronizationContext and acquires the runtime-root mutex. A dedicated MTA worker prepares requests and publishes replies; only Dispatch returns through that captured context to the original UI thread. Native modifications, saving and owned-resource release remain on that one UI thread. The worker uses event notification with a 250ms polling fallback; shutdown posts UI cleanup without joining the worker from UI. The mutex prevents two bootstrap owners from sharing one queue. Native runtime/device execution callbacks are declined. See the [pipeline contract](../../../references/pro-native-pipeline.md) for optional engine PrepareRequest/FinalizeResponse hooks and old-engine compatibility.

## Stage the already built engine

Use the device-entry/common delivery binder to compile and bind the engineering engine and its legacy seven-key or optional-editor eight-key `<engine>.scope.json` to the same explicit task/runtime/install roots. EngineeringRoot may be a read-only payload directory outside the task; writable engineering files remain `RuntimeRoot\engineering`.

```powershell
python "$BootstrapRoot\stage_engine.py" --bootstrap-root $BootstrapRoot `
  --engine-file $BoundEngineDll --engine-scope-file $BoundEngineScopeJson
```

This copies only the own engine/scope to `BootstrapRoot\engines`, using a new valid engine DLL name (the numeric `McgsInternalEngine_NNNN.dll` form also works with old loaded Bootstrap versions). Descriptive DLL names require this version of EngineLoader; copying a new skill does not update already loaded code. It creates the initial `RuntimeRoot\active-engine.json` once. That manifest must contain `assembly`, `sha256`, and **`bootstrap_scope_sha256`** (the bridge config SHA). Future file-only engine selection must retain this third field. Engine updates do not change the bootstrap configuration; changing task/bootstrap/runtime scope requires a normal exit and a newly bound bootstrap. Engine response `engineering_delivery_scope_sha256` remains the engine's independent binding; the bootstrap adds `bridge_bootstrap_scope_sha256`.

## Installation plan and separate installation entry

```powershell
& "$BootstrapRoot\install_bootstrap.ps1" -PreparedRoot $BootstrapRoot
# Separate deployment operation, only when installation is the intended task:
& "$BootstrapRoot\install_bootstrap.ps1" -PreparedRoot $BootstrapRoot -Commit
```

The default command prints a plan and writes nothing. The explicit install command requires Pro normally closed, unchanged original EXE/Addins.ini, no existing own DLL filename, and all three private roots absent from both HKLM/Registry32 and HKCU/Registry32. It does not silently replace an earlier task. It copies only the own `McgsInternalLoader.dll`, adds one numbered entry in the original preload INI section while preserving its encoding and original bytes, and writes only the prepared private REG_SZ entries with an ownership marker. All changes are journaled before the first deployment write. Unknown pre-existing registrations/INI changes are rejected. It never invokes DllRegisterServer, a vendor DLL, process injection, or a native application during installation.

The original scanner will later call the own adapter's native DllRegisterServer during the normal cold scan. The adapter checks its ownership marker and exact existing planned values before any write; it does not take over another registration. This currently uses a private machine/Registry32 route. The Pro token must be able to write these already installed private roots during the native scan. The launcher checks that access and does not auto-elevate or change ACL/UAC policy. A new machine's different token/COM policy may require a separately authorized installation configuration, not an assumption that local evidence covered it.

A partial install retains its journal and is not automatically retried or rolled back.

## Normal native launch, not a hidden host attachment

```powershell
& "$BootstrapRoot\McgsBridgeSession.exe" --plan
# Separate normal application start, when requested:
& "$BootstrapRoot\McgsBridgeSession.exe" --start
```

The launcher refuses any already running McgsSetPro process. It records the existing per-user Startup Count DWORD, sets it to0 for exactly one original cold scanner pass, and starts the original editor normally without /BuildIni, injection, kill, UI automation, window restoration, or menu-message simulation. The original application normally returns Count to1. A launch failure before any Pro process exists restores only the same unchanged Count value. The launcher does not select or modify a project: the engine's per-request expected_project and identity guards still require the intended actually open project. An application which naturally opens an old recent project is not authorization to edit it.

## Change task / remove the old own registration

Normally exit Pro first. The explicit removal entry can inspect the exact prior installation journal and then remove that installation only:

```powershell
& .\remove_bootstrap.ps1 -InstallationJournal $OldInstallationJournal
& .\remove_bootstrap.ps1 -InstallationJournal $OldInstallationJournal -Commit
```

It requires the same config hash, exact own wrapper hash, exact post-install INI bytes, all planned private registry values and no unknown subkeys/values, and the same ownership marker. Only then does it remove the three fixed private roots, restore the original INI bytes and remove the exact own wrapper file. Bootstrap/runtime/task directories, projects, user state and claims remain intact. If anything changed or the previous install had a partial/unknown outcome, it stops for reconciliation. Prepare the new task into fresh roots afterwards. Do not copy previous claims or replace a loaded same-name assembly.

## Evidence and capability boundary

Current C# templates were offline-compiled once in an owned staging directory. Own TYPELIB readback showed one coclass with one explicit default interface and all four exact callback signatures; the own native PE32 adapter was generated without loading it. No registration, Addins deployment, launcher --start, native project operation, or new-machine acceptance was performed. `offline-compile-0001` is local evidence only and is excluded from the source delivery allowlist. The final source manifest contains only own sources/scripts and the small loader capability profile; it contains no vendor DLL, project, TLB/DLL/EXE artifact, history queue, account, dump or claim.
