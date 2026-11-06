# 预编译 Pro 热接桥

发布端一次构建 `McgsPortableBridge_v6.dll`、`McgsPortableHook_v6.dll` 和 `McgsPortableAttach_v6.exe`。接收端仅复制同字节产物并生成当前目录、程序、进程及线程配置；不需要 C# 编译器，不按 Pro 软件版本设置白名单。

```powershell
python build.py --output D:\Publisher\bridge
python materialize.py --artifacts D:\Package\engine\bridge --task-root D:\Connections\one --runtime-root D:\Connections\one\queue --bootstrap-root D:\Connections\one\bootstrap --install-root C:\McgsPro --editor C:\McgsPro\Program\McgsSetPro.exe --pid 1234 --ui-thread 5678 --creation-filetime 133000000000000000
```

上述路径和 PID 都只是命令示例，必须读取本机当前进程。`materialize.py` 不启动进程、不注册 COM、不挂钩。不要用旧工程 session/claim 替代本次配置，也不要覆盖仍在使用的连接目录。

```powershell
& D:\Package\engine\bridge\McgsPortableAttach_v6.exe --discover 1234 133000000000000000
& D:\Connections\one\bootstrap\McgsPortableAttach_v6.exe --plan D:\Connections\one\bootstrap\hot-attach.json
& D:\Connections\one\bootstrap\McgsPortableAttach_v6.exe --connect D:\Connections\one\bootstrap\hot-attach.json
& D:\Connections\one\bootstrap\McgsPortableAttach_v6.exe --status D:\Connections\one\bootstrap\hot-attach.json
& D:\Connections\one\bootstrap\McgsPortableAttach_v6.exe --unregister D:\Connections\one\bootstrap\hot-attach.json
```

仅使用当前已核实 UI 线程的 `WH_GETMESSAGE`，通过 COM 激活自有托管桥；不创建远程线程、不写目标私有内存、不抢系统焦点。DllMain 只返回 TRUE。共享映射以 PID 和创建 FILETIME 命名，携带本次配置路径与 SHA；通用 Hook 不携带作者目录或工程身份。私有 COM GUID 按发行版固定，只修改自有注册；目标进程权限较高时，客户端也须有写入对应自有注册的权限，不能把权限错误称为 Pro 版本不支持。

桥在进程生命周期内保留发现映射。同一 Pro 再连接时直接返回现有 `runtime_root` 和配置，继续使用这条连接。换工程不等于换桥。`--status` 的发现记录只证明桥仍被该进程持有；真正队列响应、工程检查、保存重开及模拟分别验收。

连接调用先持久化 attempt，再挂钩。超时、失败或缺少结果时保留回执，不自动重放，不删除 claim。`--unregister` 只清除与本次自有二进制及 CodeBase 完全一致的私有项，不卸载已加载桥。停止业务队列沿用 `bridge.stop` 合同。

业务引擎放进 `bootstrap\engines`，`active-engine.json` 沿用原合同：`assembly` 是该目录内 DLL 的完整路径、`sha256` 是其实际摘要、`bootstrap_scope_sha256` 是本次 `McgsInternalBridge.bridge.json` 摘要。业务地址和 ABI 由独立的运行时适配文件提供，热接成功不代表业务功能已适配。

此目录是新增实现；静态构建、独立消息循环宿主热接和真实 Pro 业务验收必须分开记录。完成统一验证前，不把源码实现或 `ok=true` 当成真实工程验收。
