# 昆仑通态 MCGS 工程编辑技能（Stu / Pro）

给 Claude Code / Codex 使用的技能，离线读取、检查和修改 McgsStu `.MCS`、McgsPro `.MCP` 工程，也可通过 Pro 内部原生接口在线编辑已打开的工程。**两种软件共用一个技能、一个 `run.ps1` 主入口及 PowerShell 7 / Python 环境，离线数据库层使用 ACE。** Stu 当前使用离线流程，Pro 可选择离线或在线。

**不限定软件大版本或小版本。** 版本号只记录，按实际数据库、归档结构、引用、完整回环与有限修改边界判断能力。保留原版本字段和未知字节，未知结构明确报告。

在线连接与业务入口不再用作者 EXE/DLL/驱动的整文件指纹作准入白名单。厂商文件 SHA 差异作为观测信息返回；函数、RTTI、虚表和对象布局仍按实际接口核对。连接成功与业务适配分别记录，离线模板版本不构成升级要求。详见[构建与接口匹配](references/pro-native-binary-compatibility.md)。

在线业务引擎绑定时，按当前 EXE/DLL 动态定位函数、RTTI 和虚表，生成本次调用资料，不直接套用参考构建的固定 RVA。根接口按当前请求实际使用的函数核对；未解析项报告具体接口，不要求统一升级到作者版本。机制与范围见[当前程序函数定位](references/pro-native-dynamic-functions.md)。

[下载技能包](https://github.com/SuperWater925/mcgs-engineering-skill/releases/latest) · [更新记录](CHANGELOG.md) · [验证范围](references/unified-validation.md) · [贡献指南](CONTRIBUTING.md)

本版继续接通跨构建适配的实际调用链：统一代码重定位与模块路径，拆分变量/配方和离线页面依赖，保留非目标未知控件，并兼容压缩封套、旧注释列及扩展窗口属性。既有桥更新到 v3 业务引擎即可复用连接。实现规则见[适配补全](references/compatibility-completion.md)，实际证据见[本轮验证](references/compatibility-completion-validation.json)。

## 功能范围

| 功能 | McgsStu | McgsPro |
| --- | --- | --- |
| 共享快照、安全导出、全表指纹、比较 | 共用主入口 | 共用主入口 |
| 现有行的受限 BLOB 更新 | 源 SHA、字段前指纹、白名单、事务与提交复读 | 同左 |
| 已有文字、输入框、标准按钮等控件修改 | `controls`，支持组内路径及控件前指纹 | 同左，按真实结构适配 |
| 已有策略源码、配方单元格 | `strategy-source` / `recipe-cell` | 同左，保留双容器与封套 |
| 已测历史输入框长度异常 | 显式 `normalize-inputs`，只读不自动修复 | 同左 |
| 基础 JSON 工程、变量、控件创建与编辑 | 无空白工程工厂 | `create` / `edit` / `demo`；含原生按钮、数值/字符输入与显示 |
| 模板新页、克隆页及事件 | 共享 `new_window/clone_window`、`new-window` | 同左；JSON `add_pages/events` |
| 模板控件工厂、样式、预览、文字检查、受限新增窗口 | 共用 `tools/` 工具链 | 已接 Pro 变量、封套、模板及受限事务；未知厂商控件保留 |
| 已打开工程的原生页面、控件、策略、数据库、配方、设备和资源编辑 | 本版不提供在线入口 | `native-engineering`，按已闭合 ABI 与实际产品能力执行 |
| 原厂保存、检查、关闭重开 | 离线输出后另行验收 | 在线原生入口；各项结果分别记录 |

离线字段、命令和规格见[有界修改](references/bounded-edits.md)、[Pro 适配](references/pro-adapter.md)、[共享界面工具](references/ui-tools.md)。离线工厂不提供任意新控件或通用表增删；在线原生能力见[工程入口](references/pro-native-engineering.md)。本技能不提供设备协议生成、PLC 程序开发或现场下载。

离线文件读写不启动厂商软件、不连接设备。离线 `apply` 默认只预检；提交输出新文件，或在独立备份后就地修改。在线入口使用当前 Pro 的原生对象及保存方法，也不连接设备。文件回读、原厂检查、关闭重开和本机模拟分别验收。

重复修改优先使用 `baseline`、`batch-edit` 和 `apply -ExportAfter`：一次准备基线、多项修改合成一次提交，并复用提交后完整回读生成导出。Stu/Pro 离线预览可只解析本次修改页及公共层；命令、规格和实测见[离线提速](references/offline-performance.md)。

历史优化版 `v2026.10.30-offline-opt` 已完成 211 项离线/预览检查及安装后 9 项检查；六步混合修改本机耗时减少约 88.5%。该结果仅对应当时的离线流程。此前发布的 `v2026.11.04-pro-online` 集成 Pro 热接入、原生编辑及后台流水线，未取得新版真实整页提速实测。统一更名版 `v2026.11.04-engineering` 保留这些历史结果；当前可迁移性补丁的隔离证据另列，不视作真实工程重新验收。

Pro 离线新增按钮及 Stu/Pro 工具对接的规格见[离线工厂](references/offline-factories.md)，本轮实际测试见[离线功能对接验证](references/offline-parity-validation.json)。新增、克隆、修改已有控件分别记录，未执行的原厂项目不计通过。

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
- 离线核心命令无 pip 依赖；在线准备的动态函数定位使用同一 Python 中的 Capstone，依赖见 `assets/pro-native-bridge/abi-adapter/requirements.txt`。已准备好的桥的普通请求无需重复定位。Stu/Pro 离线预览和文字宽度工具另需 Pillow，SVG 预览可选 Node.js / sharp。
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

当前八组适配补全、附带样本假设、文件/托管/数据库与原厂结果见[本轮分项记录](references/compatibility-completion-validation.json)。每项记录实际执行范围，未执行的关闭重开、模拟或通信不计通过。

### 此前九项跨构建修复（2026-11-05）

- 集中完成实现后，地址与元数据、延迟绑定、部署更新、家族识别分别完成 51、27、7、10 项针对性检查。复查追加的数组、MFC 角色、证明依赖及模块发现顺序问题均已收口；失败与修正经过保留。
- 162 份源码生成的 x86 业务引擎已校对实际程序集和编译 scope；161 份生成源码、另一个 Layout 及 308 份部署文件 SHA 回读一致。通过公开 `native-engine-select` 在已有桥中切换，未重启 Pro。
- 自有 Pro 工程的一次几何修改、新建原生文字、统一保存、原生回读和独立文件 BLOB/归档回读通过；一次原厂检查已进入并返回 0，调用后编译有效标志为 1。错误、警告数量仍未知，文件解析器未暴露控件实例 ID，不据此猜值。
- 冷部署完成自有源码编译与实际 TYPELIB、GUID、回调和包装器资源回读；未注册 COM、修改 Startup 或执行原厂冷启动。关闭重开、本机模拟和设备通信本轮未执行。

详见[九项修复验证](references/cross-build-fixes-validation.json)。这是针对性修复证据，不代表每个历史发行版、任意编译器代码形态或未知对象布局均已实际验收。

### 此前在线函数动态定位（2026-11-05）

- 当前程序的 17 个模块、123 份派生接口资料及 543 处源码地址、17 处导出序号、6 处内嵌检查完成解析。161 份源码编译通过；实际 DLL 读取派生资料及校验引用的回归通过。
- 自有 PE 的地址重排、不同内容、导出序号移动与歧义反例分别验证。相同完整文件的定位缓存与内容变化后的动态解析分别记录，接收者无需作者参考 EXE/DLL。
- 独立 Pro 测试副本完成一次控件几何修改、原厂保存和原生回读；一次原厂检查正常返回 0，调用后编译有效标志为 1，错误和警告数量未取得。独立文件内容回读受原厂排他锁阻塞，未完成；关闭重开、本机模拟及设备通信本轮未执行。
- 首次打开测试页后，布局/打印尺寸属性从 0 变为 212，严格后验未通过，保留为独立观察。未放宽比较或回写旧值；确认当前目标页已活动后，以新前像完成上述修改。该打开步骤不计通过。

分项证据见[本轮定位与原厂结果](references/pro-native-dynamic-functions-validation.json)。这些结果不代表逐个实际验收了所有旧发行版，也不证明未知对象布局自动兼容。

### 此前 Pro 离线能力补齐（2026-11-04）

- 7 份主要工程与 2 份补充样例完成适用的文件验证，Stu/Pro 共 22 项样式组合通过；新增控件、精确克隆和已有控件修改分别核对。
- 自有 Pro 测试副本含 2 页、9 个控件和 7 个变量，实际原厂检查、保存、一次关闭重开及新上下文回读通过。检查调用正常返回且当时编译有效标志为 1；错误、警告数量未取得，保持未知。重开后控件、变量、页面事件和按钮动作相同，12 张表的结构及全部字段/BLOB 内容相同。
- 原厂转换时发现的未配置语言字体行移除、未知 DWORD 变化及单位 getter 返回替换字符均单列记录。文件中的单位及小数位已核对，未据此宣称实际显示和模拟交互全部通过。本轮未执行本机模拟或设备通信。

详细结果及本轮修复的图片引用、在线交付配置问题见[分项验证记录](references/offline-parity-validation.json)。这份测试副本的结果不代替其它用户工程的原厂验收。

### 此前可迁移性补丁

该轮使用自有容器、managed 夹具、文件绑定与自有消息环宿主验证，未启动 Pro、未访问用户工程。生产源码统一绑定编译及分项证据见[复查记录](references/pro-native-portability-validation.json)。安装目录可显式指定；某个未知版本的函数字节或对象布局不符，仍需实现对应适配，不能靠删除检查得到有效接口。

### 历史 Pro 在线集成

- 完整目录绑定及 x86 编译通过：156 份原生源码加绑定 Layout，共 157 份；另核对 187 份自有 ABI 资料。
- 生产客户端的 14 项假 transport 测试、实际 managed 准备/回执/比较证据代码的隔离验证通过；覆盖预备与 RPC 重叠、文件输出完成与错误传播、依赖边界和超时不重放。
- 自有原生宿主 6 个并发提交测试通过，原生 UI Dispatch 最大并发始终为 1。
- 真实 Pro 普通启动后热接入及新版桥的 3 次纯 ping 通过，确认后台队列与原 UI 线程分离；未重启 Pro，也未恢复暂停工程。

该历史流水线记录未包括真实 Pro 中的新版业务执行；本轮补齐了上方测试副本的检查、保存重开和回读，仍未取得新版整页在线施工净耗时。连接成功、隔离测试或 `ok=true` 均不能代替原厂工程检查通过。详见[流水线验证记录](references/pro-native-pipeline-validation.json)、[此前界面接口验证](references/native-ui-validation.json)和[性能验证](references/pro-native-performance-validation.json)。

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
python scripts/build_release.py --version v2026.11.05-cross-build-fixes --out local-artifacts/release
```

静态检查覆盖语法、JSON、链接和指纹，不证明原厂编译或在线业务通过。打包器先验证清单，再输出单技能根目录 ZIP 和 SHA256 文件。格式与写入器改动仍须附对应回环、差异和原厂证据，明确实际已测与待验证范围。

欢迎通过 [Issues](https://github.com/SuperWater925/mcgs-engineering-skill/issues/new/choose) 和 PR 参与；任务见 [ROADMAP](ROADMAP.md)。只提交有权公开的最小脱敏资料。

## 许可

本项目不是昆仑通态官方工具。代码按 [MIT](LICENSE) 发布；Pro 适配器原始第三方许可见 [THIRD_PARTY_LICENSE.txt](assets/pro-3.5-cli/THIRD_PARTY_LICENSE.txt)。包中不含厂商二进制、客户工程或账号。
