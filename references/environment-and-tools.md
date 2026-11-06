# 环境、安装与工具接口

拿到完整整合包时先读[开箱配置](turnkey-start-zh.md)：运行时、Capstone/Pillow、预编译引擎及桥已包含；`run.ps1` 自动从整合包或安装位置指针找到同一 Python/PowerShell。首次只物化当前目标数据，不运行 Csc。完整包带单独许可的完整厂商安装介质；本 Git 源码技能不含这些介质，两者分别交付。

日常修改优先按[离线提速](offline-performance.md)使用 `baseline` 一次生成快照、导出与指纹，`batch-edit` 合并控件/策略/配方修改，并用 `apply -Commit -ExportAfter <新目录>` 复用提交后的完整回读。源 SHA、字段前指纹、备份、固定白名单及全表核对保留；提交后重新只读打开验证实际文件。原有独立命令仍可用于专项核验。


## Stu / Pro 共同前提

共同基础为 Windows、PowerShell 7、Python 3.11+；仅离线数据库命令另需与进程位数相同的 Microsoft ACE OLEDB 16.0 或 12.0，纯在线无需 ACE。离线入口优先16.0，失败才试12.0；这两个是数据库提供程序版本，不表示工程有16张/12张表。项目实际为12张业务表，必须动态枚举，不能据此只比较某几张表。

Python3.11+用于纯字节归档解码、候选准备和Pro CLI；共同数据库命令只依赖PowerShell/.NET和ACE；Pro新建还使用同位数ADOX.Catalog创建Jet 4兼容格式数据库，但不使用Jet OLEDB提供程序或32位宿主。优先显式传入本机已有Python路径；找不到时可在Codex中调用`mcp__codex_app__load_workspace_dependencies`定位已捆绑运行时。不要把作者机器的Python绝对路径写成迁移前提。离线核心命令无pip依赖；在线准备的动态函数定位另用Capstone，安装到同一个Python，不建第二套环境。

原厂McgsStu / McgsPro及相匹配的控件、驱动、字体用于最终检查与模拟。源代码技能不分发这些程序；完整整合包保留完整介质及原许可，由接收者选择保留本机版或备份后安装。不要下载未知DLL补齐依赖。

将整个`mcgs-engineering`文件夹放到目标电脑的`%USERPROFILE%\.codex\skills\`（Codex，调用`$mcgs-engineering`）或`%USERPROFILE%\.claude\skills\`（Claude Code），也可用PowerShell7直接运行该文件夹内的`run.ps1`。保留`assets/`、`scripts/`、`references/`的相对结构。若同名技能已有本地改动，先比较再合并，不盲目覆盖。

旧仓库名 `mcgs-offline-edit-skill` 会重定向到当前仓库；提交和文件相同时无需重装，也不要求停止绑定。真正迁移旧技能或处理重复安装时，先保全本地修改并备份到 `skills` 外，只保留一个 `mcgs-engineering` 技能。已有在线运行资料不自动搬动，仓库或技能更名不要求重建 scope，见[安装说明](../README.md#安装)。

更新时先核本机实际安装位置与已有本地修改，再同步本次授权的技能副本，并重算`references/package-files.sha256.json`：
- 按路径不区分大小写排序，列出除它自身外的全部文件，记字节数和SHA256；
- `descriptor_sha256`是各行`路径\0sha256\n`拼接后的SHA256。

```powershell
pwsh -NoProfile -File .\run.ps1 doctor
pwsh -NoProfile -File .\run.ps1 doctor -Project 'D:\工程\当前.MCS'
```

`doctor`枚举ACE并只读打开指定工程；不创建写测试数据库，因此`database_write_tested=false`。其通过不证明原厂软件能编译工程。

## 本项目实际使用的工具与替代

| 工具/API | 用处 | 无此接口时 |
| --- | --- | --- |
| `exec_command`、Claude Code的`Bash/PowerShell`或本地shell | 启动PowerShell/Python，读文件、计算SHA、执行离线脚本 | Windows终端运行本包命令 |
| `apply_patch`、Claude Code的`Edit/Write`或本地文件编辑 | 精确修改脚本与清单 | 编辑器保存UTF-8源码与JSON |
| `view_image`、Claude Code的`Read` | 查看已在磁盘上的原厂截图/离线预览 | 本地图片查看器；应区分两类证据 |
| `mcp__codex_app__load_workspace_dependencies` | 定位Codex已有Python等运行时 | 手工指定已安装解释器 |
| `mcp__codex_app__open_in_codex` | 打开交接文档/预览，便于审阅 | 资源管理器或本地查看器 |
| `mcp__node_repl__js` | 历史会话中的持久JavaScript检查、纯字节分析与工具编排 | 本包PowerShell/Python或本机Node；不要求新建MCP服务 |
| 浏览/搜索工具 | 官方帮助或版本资料；离线源码处理不依赖网络 | 接收方安装目录中的官方帮助及现成证据 |
| computer-use技能/获准UI接口 | 必要时执行原厂检查、保存重开、本机模拟 | 用户在原厂编辑器操作并保存实际日志 |

表中是本项目已实际出现的接口，不是声称目标电脑必然具有这些工具。每次会话应发现实际可用工具。MCP是工具调用协议；`mcp__...`工具名只是某些能力由MCP公开。项目文件`.mcp`与此协议没有关系；本包没有新建MCP服务、监听端口或伪造厂商MCP API，也不要求Codex专用联网服务才能离线处理。

历史元数据（根会话与可靠关联子会话共42个、无正文/参数/凭据）摘要见`tool-history.json`。其中的skill用途：原`mcgs-offline-engineering`两包用于通用离线流程/Pro3.5工具；`computer-use`用于获准原厂UI验收；`hmi-launcher-maintenance`是既有仿真启动器维护，非MCS编解码依赖；`pdf/documents`用于手册与交接文件；`openai-docs`用于Codex工具说明；`skill-creator`用于本包创建。历史版本路径不能作为目标电脑安装路径；当前技能可用性从接收环境发现。只出现引用但没有读取证据的项不计作已应用；新Stu技能由本次任务创建。

## 统一入口与格式适配

两种工程的离线数据库命令均使用 PowerShell 7 和 ACE；纯在线不要求 ACE。`scripts/ace-runtime.ps1`是共用连接层，自动优先16.0再试12.0；未注册/无法打开时报告原因，不另启32位Windows PowerShell。

```powershell
pwsh -NoProfile -File .\run.ps1 doctor -Project 'D:\工程\当前.mcp'
pwsh -NoProfile -File .\run.ps1 inspect -Project 'D:\工程\当前.mcp' -Out 'D:\验收\基线'
& 'C:\本机Python\python.exe' -X utf8 .\scripts\native_tool.py audit --export 'D:\验收\基线'
pwsh -NoProfile -File .\run.ps1 create --spec 'D:\规格\create.json' --output 'D:\工程\新建.mcp'
pwsh -NoProfile -File .\run.ps1 edit --source 'D:\工程\当前.mcp' --spec 'D:\规格\edit.json' --output 'D:\工程\修改.mcp'
```

`MCGS_PYTHON`可指定现有Python。Pro旧兼容入口`assets/pro-3.5-cli/run.cmd`仍可用，但也只调用本包共用的PowerShell 7/ACE；`MCGS_PWSH`可显式指定pwsh。历史目录名`pro-3.5-cli`仅是兼容路径，不是另一套环境或软件版本准入条件，不再注册独立技能。

原始通用空白模板来自 McgsPro 3.5.1.6963、800×480，描述模板来源，不限制现有工程的大版本或小版本。新建时沿用模板机型及分辨率；不同目标需真实模板依据。基础JSON格式见[Pro适配](pro-adapter.md)。

`doctor`默认只读，`database_write_tested=false`。需要单独验证Pro新建组件，可调用旧兼容CLI的`doctor --workdir <可写目录>`，它在随机临时数据库执行实际创建/二进制回读，完成后只清理它自己的随机探针文件。

2026-10-30 六份Pro样本、38份原厂样例和新旧Stu工程的结果见[统一验证](unified-validation.md)。软件版本字段仅记录；无法解析时按真实字段/封套/类缺口说明，不重新加发行版本白名单。

## 环境准备后的交互

先检查共同基础并说明离线、在线的区别，让接收者选择，再核所选方式的依赖。离线数据库命令使用 `doctor` 检查 ACE；在线用 `native-doctor --editor-executable '<实际Pro EXE>' --install-root '<实际安装根>'` 检查文件准备前提，纯在线不依赖独立 ACE 提供程序。不要让纯离线任务先配置在线编译器，也不要把 `doctor` 退出0当作在线接入或业务就绪。`native-doctor.ready_to_prepare` 仅指文件准备，连接权限和实际业务另行核对。用户已明确说“离线”或“在线”时直接沿用，不重问。当前 Stu 只提供离线方式，其在线入口待后续更新。

技能是 AI 的操作说明和入口；`assets/pro-native-bridge` 是实现在线操作的自有工具与源码。当前使用本机文件队列传输，不是 MCP 协议服务器，也不需要额外联网服务。

## Pro 原生桥与同一环境

[原生工程入口](pro-native-engineering.md)复用本技能的 Python 与一次性文件队列；宿主中的 helper 为匹配 Pro 位数的原生接口适配，不另建 Jet/32位 PowerShell 环境。目录由编译绑定的显式 `.scope.json` 给出，工程由 request.expected_project 给出。冻结资料与可写 runtime 分离，完整回执使用本地文件长度与哈希关联，不再按16MiB样本拒绝；实际容量仍受x86/.NET与内存限制，小 queue envelope不删字段假装完整。实际 DLL/ABI 不匹配则拒绝对应操作，软件发行版本不另设白名单。

原生首次部署、已有桥升级及完整包内工具路径见[部署与保存合同](pro-native-deployment.md)。Stu不启动此桥，继续共用的离线环境。
