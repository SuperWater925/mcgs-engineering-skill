# Pro 在线提速小更新包

小更新包供 Windows x64 用户使用。它更新技能源码、说明、清单和预编译 Pro 引擎，复用本机完整包的安装介质、Python、PowerShell 和热接桥。可复用原完整包或上一版更新目录。源码技能入口会按当前合同自动获取匹配小更新，不静默退回旧引擎。 [下载小更新包](https://github.com/SuperWater925/mcgs-engineering-skill/releases/tag/v2026.11.16-portable-online) · [下载完整基底](https://github.com/SuperWater925/mcgs-engineering-skill/releases/tag/v2026.11.06-turnkey-bootstrap)

本轮按能力解析当前函数、RTTI 和实际字段布局。原生创建与属性编辑按页共享工作，保存集中执行。已有连接可以选用当前预编译引擎，小更新复用已有完整目录的已校验文件。 [在线提速合同](https://github.com/SuperWater925/mcgs-engineering-skill/blob/v2026.11.16-portable-online/references/pro-native-performance.md)

## 交给 AI 更新

1. 优先运行新版技能的 `turnkey fetch-bundle` 自动匹配更新。手动时下载更新 ZIP 和同一 Release 的 `SHA256SUMS.txt`，核对后解压。Release 同时提供 `mcgs-engineering-index.json`，供 AI 按技能合同找到匹配引擎。
2. 提供已解压完整基底目录和更新包目录。让 AI 选择一个新的输出目录，用完整基底自带的 Python 应用更新。已应用上一版小更新时，也可直接把上一版完整目录作为来源，不必重新下载600MB安装介质。

```powershell
$base = 'D:\MCGS\完整基底'
$update = 'D:\MCGS\小更新包'
$new = 'D:\MCGS\在线新版'
& "$base\runtime\python\python.exe" -B -X utf8 "$update\scripts\apply_turnkey_update.py" --base-bundle $base --output $new
```

更新器校验基底清单和实际复用的文件，在新目录组装并校验完整文件集。更新完成后，用新版目录登记技能。

```powershell
& "$new\McgsRun.cmd" turnkey install-skill --bundle-root $new
```

其他智能体可用 `--destination` 指定实际技能目录。也可从新版目录运行 `McgsStart.exe`。新 Pro 连接会加载新版预编译引擎。已有连接运行 `turnkey prepare-online`，会在原桥选择匹配新业务 DLL并返回实际引擎信息；无需重开 Pro。旧目录保留作回退或后续复用来源。

首次在线使用时，普通方式打开 Pro 工程，再在新版目录运行 `McgsRun.cmd turnkey prepare-online`。接收方使用包内引擎和运行时，只在本机生成 ABI 定位资料。 [在线操作](https://github.com/SuperWater925/mcgs-engineering-skill/blob/v2026.11.16-portable-online/references/turnkey-start-zh.md)
