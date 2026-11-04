# 昆仑通态 MCGS 工程编辑技能（Stu / Pro）

给 Claude Code / Codex 使用的技能，离线读取、检查和修改 McgsStu `.MCS`、McgsPro `.MCP` 工程，也可通过 Pro 内部原生接口在线编辑已打开的工程。**两种软件共用一个技能、一个 `run.ps1` 主入口及 PowerShell 7 / Python 环境，离线数据库层使用 ACE。** Stu 当前使用离线流程，Pro 可选择离线或在线。

**不限定软件大版本或小版本。** 版本号只记录，按实际数据库、归档结构、引用、完整回环与有限修改边界判断能力。保留原版本字段和未知字节，未知结构明确报告。

在线连接与业务入口不再用作者 EXE/DLL/驱动的整文件指纹作准入白名单。厂商文件 SHA 差异作为观测信息返回；函数、RTTI、虚表和对象布局仍按实际接口核对。连接成功与业务适配分别记录，离线模板版本不构成升级要求。详见[构建与接口匹配](references/pro-native-binary-compatibility.md)。

[下载技能包](https://github.com/SuperWater925/mcgs-engineering-skill/releases/latest) · [更新记录](CHANGELOG.md) · [验证范围](references/unified-validation.md) · [贡献指南](CONTRIBUTING.md)

本次可迁移性补丁移除了控件、策略和批次的样本数量配额，补齐显式安装路径与编辑器路径绑定、ACE 创建失败回退及在线独立预检。仍需适配的真实 ABI、控件和驱动，以及本轮实际验证范围见[可迁移性复查](references/portability-review.md)。

## 功能范围

| 功能 | McgsStu | McgsPro |
| --- | --- | --- |
| 共享快照、安全导出、全表指纹、比较 | 共用主入口 | 共用主入口 |
| 现有行的受限 BLOB 更新 | 源 SHA、字段前指纹、白名单、事务与提交复读 | 同左 |
| 已有文字、输入框、标准按钮等控件修改 | `controls`，支持组内路径及控件前指纹 | 同左，按真实结构适配 |
| 已有策略源码、配方单元格 | `strategy-source` / `recipe-cell` | 同左，保留双容器与封套 |
| 已测历史输入框长度异常 | 显式 `normalize-inputs`，只读不自动修复 | 同左 |
| 基础 JSON 工程、变量、控件创建与编辑 | 无空白工程工厂 | `create` / `edit` / `demo` |
| 模板控件工厂、样式、预览、文字检查、受限新增窗口 | 保留既有 `tools/` 工具链 | 未将这组 Stu 工具扩展为通用 Pro 工厂 |
| 已打开工程的原生页面、控件、策略、数据库、配方、设备和资源编辑 | 本版不提供在线入口 | `native-engineering`，按已闭合 ABI 与实际产品能力执行 |
| 原厂保存、检查、关闭重开 | 离线输出后另行验收 | 在线原生入口；各项结果分别记录 |

离线字段、命令和规格见[有界修改](references/bounded-edits.md)、[Pro 适配](references/pro-adapter.md)、[Stu 界面工具](references/ui-tools.md)。离线工厂不提供任意新控件或通用表增删；在线原生能力见[工程入口](references/pro-native-engineering.md)。本技能不提供设备协议生成、PLC 程序开发或现场下载。

离线文件读写不启动厂商软件、不连接设备。离线 `apply` 默认只预检；提交输出新文件，或在独立备份后就地修改。在线入口使用当前 Pro 的原生对象及保存方法，也不连接设备。文件回读、原厂检查、关闭重开和本机模拟分别验收。

重复修改优先使用 `baseline`、`batch-edit` 和 `apply -ExportAfter`：一次准备基线、多项修改合成一次提交，并复用提交后完整回读生成导出。Stu 预览可只解析本次修改页及公共层；命令、规格和实测见[离线提速](references/offline-performance.md)。

历史优化版 `v2026.10.30-offline-opt` 已完成 211 项离线/预览检查及安装后 9 项检查；六步混合修改本机耗时减少约 88.5%。该结果仅对应当时的离线流程。此前发布的 `v2026.11.04-pro-online` 集成 Pro 热接入、原生编辑及后台流水线，未取得新版真实整页提速实测。统一更名版 `v2026.11.04-engineering` 保留这些历史结果；当前可迁移性补丁的隔离证据另列，不视作真实工程重新验收。

## 选择离线或在线

环境检查完成后，智能体会向使用者说明并询问采用哪一种方式；已明确选择时不重复询问。

- **离线修改**：直接处理工程文件，适合批量生成和整页调整，完成后在原厂软件查看。
- **在线修改（Pro）**：通过内部接口修改当前已打开工程，可以看到画面逐步变化，并调用原厂保存和检查；需接入本机桥，频繁刷新通常更慢。

普通启动的 Pro 优先热接入，不要求每次经桥接启动器重启；已有桥直接复用。实际模块、位数、对象布局及产品能力仍须匹配，软件版本号不作白名单。连接配置不是许可证，正常在线执行默认 direct，不要求许可文件或逐批审批。

在线采用“后台准备 → 原 UI 线程批量执行 → 后台回执”：纯数据准备、日志和不同派生文件输出可以并行，同一工程的原生修改、保存和资源释放仍由单一 UI 线程执行。更改前先激活 Pro 内部目标页面或编辑器，不强制最大化或抢 Windows 焦点。更新技能不会自动恢复已暂停的工程。

首次部署、热接入和已有桥升级见[连接与部署](references/pro-native-deployment.md)；界面施工见[在线界面工作流](references/pro-native-ui-workflow.md)；线程、批次及旧桥兼容范围见[后台流水线](references/pro-native-pipeline.md)。包内交付自有源码与绑定工具，不含可直接套用到任意电脑的厂商 DLL 或本机绑定结果。

## 安装

从 [Releases](https://github.com/SuperWater925/mcgs-engineering-skill/releases/latest) 下载 ZIP，按同页 `SHA256SUMS.txt` 核对 SHA256。解压后的顶层目录是 `mcgs-engineering`，放入其中一处：

- Claude Code：`%USERPROFILE%\.claude\skills\mcgs-engineering`
- Codex：`%USERPROFILE%\.codex\skills\mcgs-engineering`

也可以克隆：

```powershell
# Claude Code
git clone https://github.com/SuperWater925/mcgs-engineering-skill.git "$env:USERPROFILE\.claude\skills\mcgs-engineering"
# Codex
git clone https://github.com/SuperWater925/mcgs-engineering-skill.git "$env:USERPROFILE\.codex\skills\mcgs-engineering"
```

目标已存在时，先比较并保全本地修改。保留整个目录结构，不只复制 `SKILL.md`。Codex 中调用 `$mcgs-engineering`，Claude Code 中描述任务，或直接执行命令。

从旧版迁移时，先保全并比较本地修改，将旧 `mcgs-offline-edit` 安装目录备份移到 `skills` 目录之外，再安装新包唯一根目录 `mcgs-engineering`；不要同时保留两个技能。本版不保留旧调用别名，改用 `$mcgs-engineering`。已有在线运行资料不自动搬动，也无需因技能更名重建运行 scope。

安装后先按用途检查：离线用 `pwsh -NoProfile -File .\run.ps1 doctor`；Pro 在线用 `pwsh -NoProfile -File .\run.ps1 native-doctor --install-root '<实际安装根目录>' --editor-executable '<实际Pro EXE完整路径>'`。`native-engineering --help` 仅表示命令入口可读，`native-doctor` 通过只表示选定文件与构建前提通过，不代表已经连接或业务接口全部适配。首次在线接入需本机的 .NET Framework x86 编译器及实际 Pro 安装；按[首次在线准备](references/pro-native-deployment.md#首次热接的文件准备)生成并编译自有桥和业务引擎，仅复制技能目录不会自动建立连接。便携安装与隔离连接的实际范围见[安装验证记录](references/installation-validation.json)。

## 共用环境

- Windows、PowerShell 7、Python 3.11+。
- 离线数据库读写需要与 PowerShell 位数匹配的 Microsoft ACE OLEDB 16.0 或 12.0；优先 16.0，实际失败再试 12.0。纯在线组态无需先安装 ACE。
- Pro 新建数据库另需同位数 `ADOX.Catalog`，不再使用独立 32 位 PowerShell 5.1 / Jet OLEDB 环境。
- 核心命令无 pip 依赖；Stu 预览和文字宽度工具另需 Pillow，SVG 预览可选 Node.js / sharp。
- 原厂 McgsStu / McgsPro、驱动、控件和字体用于最终验证，由使用者安装。

`assets/pro-3.5-cli/` 仅保留兼容路径及模板来源，不是版本门槛，也不再注册第二个技能。详见[环境说明](references/environment-and-tools.md)。

## 离线快速使用

在技能目录执行，替换本次输入与新的输出路径；两种工程使用同样的已有内容处理命令：

```powershell
pwsh -NoProfile -File .\run.ps1 doctor
pwsh -NoProfile -File .\run.ps1 inspect -Project 'D:\工程\当前.MCP' -Out 'D:\验收\导出'
pwsh -NoProfile -File .\run.ps1 audit --export 'D:\验收\导出'
pwsh -NoProfile -File .\run.ps1 controls --export 'D:\验收\导出' --spec 'D:\修改\控件.json' --out 'D:\验收\控件补丁'
pwsh -NoProfile -File .\run.ps1 apply -Project 'D:\工程\当前.MCP' -Manifest 'D:\验收\控件补丁\manifest.json' -Out 'D:\验收\修改.MCP'
```

最后一条只预检。已有写入授权并确认本次清单后，加 `-Commit` 才提交；就地写入另需 `-InPlace -Backup <新备份路径>`。`doctor` 通过仅表示环境可用。

## 验证范围

### 当前可迁移性补丁

本轮使用自有容器、managed 夹具、文件绑定与自有消息环宿主验证，不启动 Pro、不访问用户工程。生产源码统一绑定编译及分项证据见[复查记录](references/pro-native-portability-validation.json)。安装目录可显式指定；某个未知版本的函数字节或对象布局不符，仍需实现对应适配，不能靠删除检查得到有效接口。

### 历史 Pro 在线集成

- 完整目录绑定及 x86 编译通过：156 份原生源码加绑定 Layout，共 157 份；另核对 187 份自有 ABI 资料。
- 生产客户端的 14 项假 transport 测试、实际 managed 准备/回执/比较证据代码的隔离验证通过；覆盖预备与 RPC 重叠、文件输出完成与错误传播、依赖边界和超时不重放。
- 自有原生宿主 6 个并发提交测试通过，原生 UI Dispatch 最大并发始终为 1。
- 真实 Pro 普通启动后热接入及新版桥的 3 次纯 ping 通过，确认后台队列与原 UI 线程分离；未重启 Pro，也未恢复暂停工程。

0102 后台流水线的业务 engine 尚未在 Pro 启用；新增批量创建、保存重开及整页净耗时仍未在真实工程复测。连接成功、隔离测试或 `ok=true` 均不能代替原厂工程检查通过。详见[流水线验证记录](references/pro-native-pipeline-validation.json)、[此前界面接口验证](references/native-ui-validation.json)和[性能验证](references/pro-native-performance-validation.json)。

### 历史离线与原厂验收

2026-10-30 本地验证覆盖 6 份 Pro、38 份厂商样例/模板和新旧 Stu，共 46 个不同工程，完成 7,888 项专项检查及适用记录功能回归。测试工程、业务数据、截图和厂商程序不公开；见[验证摘要](references/unified-validation.md)与[机器统计](references/validation.json)。

- 六份 Pro 修改副本均原厂打开；补齐 H5U_MODBUSTCP、McgsIoT 和另发现的 S7Plus G2 依赖后，全部为零错误，警告按实际结果保留。
- Pro 控件/策略/非空配方综合副本为 0 错误、0 警告；Stu 综合副本为 0 错误、3 条已有警告。
- 两种软件均观察到本机模拟页面和指定交互；P06 策略综合副本保存重开后为 0 错误、19 条警告。
- 未执行实体 HMI/PLC 下载、通信或现场配方运行。历史验收不代表其他新工程自动通过。

原厂可能只先报告第一项缺失驱动，补齐后须重做全工程检查，见[驱动依赖](references/driver-dependencies.md)。

## 仓库与发布检查

```powershell
python scripts/check_repository.py --update-manifest
python scripts/check_repository.py
pwsh -NoProfile -File scripts/check_powershell.ps1
python scripts/build_release.py --version v2026.11.04-portability --out local-artifacts/release
```

静态检查覆盖语法、JSON、链接和指纹，不证明原厂编译或在线业务通过。打包器先验证清单，再输出单技能根目录 ZIP 和 SHA256 文件。格式与写入器改动仍须附对应回环、差异和原厂证据，明确实际已测与待验证范围。

欢迎通过 [Issues](https://github.com/SuperWater925/mcgs-engineering-skill/issues/new/choose) 和 PR 参与；任务见 [ROADMAP](ROADMAP.md)。只提交有权公开的最小脱敏资料。

## 许可

本项目不是昆仑通态官方工具。代码按 [MIT](LICENSE) 发布；Pro 适配器原始第三方许可见 [THIRD_PARTY_LICENSE.txt](assets/pro-3.5-cli/THIRD_PARTY_LICENSE.txt)。包中不含厂商二进制、客户工程或账号。
