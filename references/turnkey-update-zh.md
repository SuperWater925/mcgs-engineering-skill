# Pro 在线提速小更新包

小更新包供 Windows x64 用户使用。它更新技能源码、说明、清单和预编译 Pro 引擎，复用本机完整包的安装介质、Python、PowerShell 和热接桥。基底为 11 月 6 日 bootstrap 完整包。 [下载小更新包](https://github.com/SuperWater925/mcgs-engineering-skill/releases/tag/v2026.11.10-online-flow) · [下载完整基底](https://github.com/SuperWater925/mcgs-engineering-skill/releases/tag/v2026.11.06-turnkey-bootstrap)

本轮将画面激活与前后核对放入一次 direct 调用，同页属性批次在每次采集内共用页面上下文，范围明确的连续页保存及工程保存共用一个 RPC。ABI 配置生成按路径索引条目，保留原发布指纹及原生校验。 [在线提速合同](https://github.com/SuperWater925/mcgs-engineering-skill/blob/v2026.11.10-online-flow/references/pro-native-performance.md)

## 交给 AI 更新

1. 下载更新 ZIP 和同一 Release 的 `SHA256SUMS.txt`，核对 SHA256 后解压。
2. 提供已解压完整基底目录和更新包目录。让 AI 选择一个新的输出目录，用完整基底自带的 Python 应用更新。已应用上一版小更新时，仍从保留的 11 月 6 日完整基底生成新版目录。

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

其他智能体可用 `--destination` 指定实际技能目录。也可从新版目录运行 `McgsStart.exe`。新 Pro 连接会加载新版预编译引擎。已有连接继续按当前 scope 执行，更新过程保留原完整基底，供后续小更新使用。

首次在线使用时，普通方式打开 Pro 工程，再在新版目录运行 `McgsRun.cmd turnkey prepare-online`。接收方使用包内引擎和运行时，只在本机生成 ABI 定位资料。 [在线操作](https://github.com/SuperWater925/mcgs-engineering-skill/blob/v2026.11.10-online-flow/references/turnkey-start-zh.md)
