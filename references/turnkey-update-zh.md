# MCGS 在线工程小更新包

小更新包供 Windows x64 用户使用。它更新技能、说明、清单和预编译业务引擎，复用已有完整包或上一次更新目录中的安装介质与运行时。包含 Stu 的更新会同时提供 Stu DLL、源合同及匹配的共用热接桥。按当前产品选择匹配的预编译文件。 [已发布的 Pro 小更新](https://github.com/SuperWater925/mcgs-engineering-skill/releases/tag/v2026.11.16-native-page-update) · [完整基底](https://github.com/SuperWater925/mcgs-engineering-skill/releases/tag/v2026.11.06-turnkey-bootstrap)

新版支持同页同源原生批量克隆、整页设计计划、工具栏语义发现，以及可逐项回读的原生规则阵列复制。已有连接可以选用新预编译引擎。 [在线工程编辑](https://github.com/SuperWater925/mcgs-engineering-skill/blob/v2026.11.16-native-page-update/references/pro-native-engineering.md) · [实测范围](https://github.com/SuperWater925/mcgs-engineering-skill/blob/v2026.11.16-native-page-update/references/pro-native-page-update-validation.md)

## 交给 AI 更新

1. 优先运行新版技能的 `turnkey fetch-bundle --family stu` 或 `--family pro` 匹配更新。手动时下载更新 ZIP 和同批次的 `SHA256SUMS.txt`，核对后解压。索引 `mcgs-engineering-index.json` 记录包与引擎合同。离线已有两个文件时，可用 `MCGS_UPDATE_INDEX` 指定本地索引，并加 `--no-download`。
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

其他智能体可用 `--destination` 指定实际技能目录。也可从新版目录运行 `McgsStart.exe`。新 Pro 连接会加载新版预编译引擎。已有连接使用下方同一条完整命令，会在原桥选择匹配新业务 DLL并返回实际引擎信息；无需重开 Pro。完整包旧目录可用于回退或后续更新。技能暂存和旧技能备份保存在技能扫描根之外的同卷目录。安装失败时原目录会恢复，安装成功的回执用 `previous_backup` 给出旧技能备份位置。扫描根里旧安装器留下的同名备份，经路径、技能身份和同卷校验后整体迁出，用户资料保留；`legacy_backups` 给出迁移位置及持久回执，身份不符的目录保留并说明原因。

首次在线使用时，普通方式打开 Pro 工程，再运行：

```powershell
& "$new\McgsRun.cmd" turnkey prepare-online
```

Stu 带包使用时，普通方式打开 Stu 工程，再运行 `turnkey prepare-online --family stu`。安装技能时也可以加 `--family stu`，回执会记录所选 Stu 引擎指纹。

唯一运行中的 Pro 自动选定，不启动或重启软件。多个实例时可直接沿用已知的 `--pid`，或明确路径：

```powershell
& "$new\McgsRun.cmd" turnkey prepare-online --editor "D:\McgsPro\Program\McgsSetPro.exe" --install-root "D:\McgsPro" --pid 1234
```

路径与 PID 换成本次实例；没有运行实例时返回实际安装候选，正常打开后再准备。接收方使用包内引擎和运行时，只在本机生成 ABI 定位资料。源码入口在启动 Python 前也识别 `--bundle-root`，无系统 Python 时可用已有包内 PowerShell：

```powershell
& "$base\runtime\pwsh\pwsh.exe" -NoProfile -File .\run.ps1 turnkey fetch-bundle --bundle-root $base
```

[在线操作与连接后命令](turnkey-start-zh.md)。构建小更新时使用与当前启动器源码一致的发布方工具。`scripts/build_turnkey_tools.ps1 -Output <新目录>` 生成工具及清单。Stu 更新可用 `build_turnkey_update.py --stu-engine-build <Stu产物> --bridge-build <共用桥产物>` 传入预编译组件，也可复用基底中与当前合同相符的同一组组件。接收端应用更新和准备在线时直接使用包内产物。
