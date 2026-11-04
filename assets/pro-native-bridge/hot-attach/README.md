# 已运行进程的自有桥热接入

此入口让用户先正常启动 Pro，再按所选 PID 接入自有队列桥，不要求用 BridgeSessionLauncher 启动。它不打开、关闭、保存、切换或检查工程；实际工程编辑继续使用原引擎、前像与保存合同。

**已验证自有纯 native x86 宿主的冷 CLR 机制，以及本机真实 Pro 普通启动会话的热接入连接层。** 真实 Pro 接入前未载入 CLR 或桥；接入后在原 UI 线程返回 OwnPing，未读取原生工程对象或调用厂商业务方法。连接层通过不等于工程编辑、厂商业务 ABI 或新机器兼容性验收。普通无参数启动仍可能恢复最近工程，不能把本次无工程会话推定为“保证不打开任何工程”的启动合同。

## 准备与一次连接

目录放在 `assets/pro-native-bridge/hot-attach`，其兄弟 `bootstrap` 提供既有自有 Bootstrap/EngineLoader/DurableQueuePump/NullSafeDispatch 与 PE assembler。默认按包内相对目录查找，不依赖 Codex/Claude 安装目录或本机用户目录；也可显式给 `--bootstrap-template`。

先由既有目录配置取得绝对参数；下面变量是调用者提供的路径，不是固定任务或工程：

```powershell
python .\hot-attach\prepare_hot_attach.py `
  --task-root $TaskRoot --runtime-root $RuntimeRoot `
  --bootstrap-root $FreshBootstrapRoot --install-root $InstallRoot `
  --editor $ActualProExecutable --host-kind pro
```

准备器只生成/编译自有代码，不注册、不加载到目标、不启动 Pro、不修改 Addins/Startup/厂商文件。BootstrapRoot 必须全新；RuntimeRoot 与它分开且都在显式 TaskRoot 下。当前 loader 能力文件必须匹配实际原 EXE SHA，不以软件版本号判断支持。未知二进制的业务支持仍由原引擎 ABI 合同决定。

每个配置使用独立随机 CLSID、接口和程序集 GUID、唯一 `McgsHotBridge_*` 程序集名，并剥掉未用的冷 AddIn COM 壳。不会复用旧冷桥的程序集身份、52119C44 类或类型库注册。

生产配置不加 `--ping-only`，使用原有文件级 `bootstrap/stage_engine.py` 装入已经绑定到**相同 TaskRoot/RuntimeRoot/InstallRoot** 的自有引擎和同名 scope。prepare 的 build manifest 已提供 `bootstrap_scope_sha256`，并预建 engines 目录，因此与原 staging 合同直接兼容：

```powershell
python .\bootstrap\stage_engine.py --bootstrap-root $FreshBootstrapRoot `
  --engine-file $BoundEngine --engine-scope-file $BoundScope
```

首次 staging 的 active-engine.json 必须未存在，不覆盖别的运行会话。换 Bootstrap 时不能借用另一个 RuntimeRoot 的 active-engine、scope 或 claims。

对已选定、同位数且权限可访问的目标，读取其当前 PID、主窗口所属 UI 线程和 creation FILETIME。它们是调用身份，不能沿用历史进程值：

```powershell
& "$FreshBootstrapRoot\McgsHotAttach.exe" --plan `
  "$FreshBootstrapRoot\hot-attach.json" $TargetPid $UiThreadId $CreationFiletime

# 已授权接入时一条 connect 自动完成自身注册和线程接入，无额外许可文件/UI。
& "$FreshBootstrapRoot\McgsHotAttach.exe" --connect `
  "$FreshBootstrapRoot\hot-attach.json" $TargetPid $UiThreadId $CreationFiletime
```

可在参数末尾追加需要排除的 PID；命中即拒绝。Pro 模式还核真实 main HWND 的 owner PID/UI thread，不接受任意工作线程。仅安装所选线程的 WH_GETMESSAGE，不装全局 hook，不使用 WriteProcessMemory/CreateRemoteThread、输入注入、SendInput、ShowWindow、菜单 handler 或窗口操作。只投递没有业务语义的 WM_NULL 唤醒消息循环。Windows 返回权限不足时直接报告，不提升权限或修改安全策略。

默认注册范围为 auto：目标 IL 高于 Medium 时选自身独立 HKLM/Registry32 类，否则选 HKCU/Registry32。高完整性下 COM 会忽略 per-user 注册，不能通过 RegistryOverride 绕过。HKLM 真无写权限即失败；普通 Medium 的 HKCU 路径已实现，但本机实际运行验证覆盖的是 High/HKLM。

`--register`/`--unregister` 也可单独使用。清理只针对同一配置标记且全部值/子键精确匹配的自有 CLSID，不修改其它注册项。

## 工作链与结束

native GetMsgProc 的 DllMain 只返回 TRUE。首次线程回调通过标准 COM CCW 激活自有 HotAttachObject；后者核实际 EXE/配置/位数及现有 COM STA，再捕获UI同步上下文并启动后台队列worker。worker只在原UI线程调用原生Dispatch，准备及回复发布在后台完成；新版engine另支持可选PrepareRequest/FinalizeResponse。`datObj=null`：当前工程引擎仅保留此稳定签名参数，身份和业务方法从自身native状态取得；热接入不制造厂商DatObj，后台也不访问UI拥有的datObj。

临时 hook 回调一直调用 CallNextHookEx，完成后 client 尝试移除并报告 `thread_hook_removed`。新队列用独立 RuntimeRoot/互斥体，不能抢占别的 live bridge queue。失败或不确定结果保留 native 结果文件，不自动重试、删除 marker 或重放。

停桥写入该配置 RuntimeRoot 下的 `bridge.stop`，等待 `ui_pump_stopped`，这只停该桥泵；不退出应用。托管程序集留驻到应用正常退出，不尝试不可靠的进程内卸载。清自身注册可运行 `--unregister CONFIG PID`；此动作不调用目标进程。再次接入/换配置需按当前结果和实际进程生命周期处理，不擅删失败记录。

## 已执行的最小机制验证

使用 `--host-kind own-test-native-message-loop` 可编译独立自有 PE32 消息环：没有 CLR 目录，OleInitialize STA、message-only 窗口、GetMessage/Dispatch；它不是 Pro，也不模拟厂商 ABI。首次接入前实际模块表不含 clr/mscoree/mscorlib；接入后实际载入 CLR、在原 MAINSTA UI 线程启动泵，再由唯一数字名 OwnPingEngine 返回同线程 pong。成功后已停泵、经 WM_DESTROY/PostQuitMessage 正常退出，并清唯一自有 HKLM 类。

`--ping-only` 为真实应用的连接层准备仅接受 ping 的自有引擎；该引擎没有厂商业务方法，不能作为工程编辑引擎。本机真实 Pro 已以原 EXE、无工程参数正常启动后完成一次连接：接入前没有 CLR/桥模块，线程专属 hook 经 COM 激活自有程序集，原 UI 线程返回同线程 pong，`write_attempted=false`、`manufacturer_business_abi_tested=false`。随后已移除临时 hook、停止新泵、清理唯一自有 CLSID；Pro 保持运行。本次没有打开、切换、保存、关闭或编辑工程，也没有调用工程检查。实际覆盖 High/HKLM/Registry32；Medium/HKCU 及新机器仍未实测。

本地验证的 DLL/EXE、配置、队列、结果及绝对路径不交付；仅按 source-manifest 的 allowlist 分发源码、说明和去路径的 validation-summary。没有工程、厂商二进制、账号、dump 或历史 claim。

尚未实现/安装常驻 watcher 或登录自启。本入口解决按需连接普通启动进程；不把未实现的自动发现声称已经后台运行。

## 公共接口依据

- 线程 hook 的 DLL/位数及指定线程规则：[SetWindowsHookExW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowshookexw)。
- 托管类的 mscoree/Assembly/Class/CodeBase 注册：[Registering Assemblies with COM](https://learn.microsoft.com/en-us/dotnet/framework/interop/registering-assemblies-with-com)。
- 权限与 per-user COM 的限制：[Merged View of HKEY_CLASSES_ROOT](https://learn.microsoft.com/en-us/windows/win32/sysinfo/merged-view-of-hkey-classes-root)、[COM Elevation Moniker 的完整性说明](https://learn.microsoft.com/en-us/windows/win32/com/the-com-elevation-moniker)。本实现不使用 elevation moniker 提权。

这些文档说明公开 API 合同；本次功能证据包括自有 native 冷 CLR 宿主和真实 Pro 的连接层结果，不扩大到工程业务或其它环境。
