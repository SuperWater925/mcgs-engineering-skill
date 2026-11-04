# Pro 原生工程编辑入口

同一技能可对已打开的 Pro 工程使用内部接口批量编辑。先有与当前实际二进制 ABI 匹配的桥包，再使用 `run.ps1 native-engineering`；工程发行版本只记录。未匹配的模块、布局、产品能力或未闭合数据拒绝对应动作。

布局和样式任务先读[在线界面施工](pro-native-ui-workflow.md)：用当前完整森林/typed getter准备一次完整方案，复用几何/属性batch、原按钮配对和单位组件合同；施工中不边写工程边研发接口。原生创建批次、连续step合并及其回执/依赖边界按[在线提速合同](pro-native-performance.md)执行；不要拿离线工厂限制拒绝已有原生kind，也不把该批次扩称任意对象工厂。

入口使用已配置的 scope 连接参数；可由环境变量 `MCGS_NATIVE_SCOPE_CONFIG` 提供，配置 SHA 自动计算，无需逐次手填。配置说明任务目录、冻结接口资料目录、运行目录、安装目录和现有 transport 客户端；项目路径由每次请求给出。当前工程路径和对象身份从本次连接读取。连接配置不是许可证；正常执行不需要准备许可文件。

```powershell
# 这里只核连接配置文件；使用本次实际配置的完整路径，SHA自动计算。
pwsh -NoProfile -File .\run.ps1 native-engineering --scope-config '<engine>.scope.json完整路径' layout

# stage 只写新的 session 文件；run 会向已配置原生桥提交。
pwsh -NoProfile -File .\run.ps1 native-engineering --scope-config '<完整路径>' stage --program '<本次program完整路径>' --directory '<runtime\engineering\新session>'
pwsh -NoProfile -File .\run.ps1 native-engineering --scope-config '<完整路径>' run --directory '<同一session完整路径>' --timeout 180
```

默认使用直接执行：同一个原生队列调用内，按动作顺序读取当前目标、准备调用并执行，不生成或要求用户提供permit文件，不逐批索要确认。多步骤program的`run`默认把连续同页、无结果依赖且兼容的编辑step合并为队列调用，默认每组最多8个动作（`--max-merged-actions`可调）；`$ref`依赖、显式inspect、页面/元数据变化、保存、检查或不兼容动作结束当前组。原单step不因自动分组预算被拆分或拒绝，同一step内仍按动作顺序执行；`--no-merge-steps`保留逐step路线。已完成动作的真实ID、名称和路径仍可通过`$ref`引用。

```powershell
# 连接配置也可在本次终端一次设置。
$env:MCGS_NATIVE_SCOPE_CONFIG = '<engine>.scope.json完整路径'
pwsh -NoProfile -File .\run.ps1 native-engineering execute --project '<当前工程完整路径>' --spec '<动作JSON完整路径>' --timeout 180 --out '<runtime内新结果JSON完整路径>'
```

`apply --project ... --spec ...` 与 `execute` 使用相同默认直接执行入口；`--id` 自动生成，`--out` 可省略而直接返回JSON。指定结果文件时使用已配置runtime内的全新文件。`inspect`可用于明确的只读查询；普通执行不再要求先跑inspect/prepare/apply三条命令。旧`prepare/--permit`入口仅供兼容历史调用，不是新流程前提。配置、位数、ABI、目标类型和owner用于正确调用本机原生接口，不是授权审批。工程可位于任务目录之外，仍须命中实际打开的目标工程。

成功返回不等于原厂检查通过；超时先看该请求的实际结果，避免重复创建同一个对象。队列ID用于关联一次调用结果，不是许可证。

设备最小选择以完整 root→child 路径、原生对象所有权、名称和 UID 为准。`device-catalog` 是当前树/配置前像；驱动属性发现使用`device-driver-property-catalog-preserve-tree`，它在自有私有对象中调用原厂 Get，保持 canonical 配置。不能从 raw 字节目录编造 property before_value。

已实现的实际编辑入口包括安装驱动目录 Add、原设备/节点 clone、rename、delete、保留子树的原位属性 Get/Set、引用感知 rename、设备树保存。各kind的target/after按对应原生接口填写；当前before和ABI资料由执行入口取得，不要求用户准备许可前像。H5U_MODBUSTCP、McgsIoT 和 monidevdrv 的支持分支依实际安装文件及守卫，不将三者当作所有驱动的通用合同；未知派生节点不猜布局。monidevdrv 的完整运行参数业务语义仍未全部闭合。

普通编辑默认暂不调用 bridge 保存，`commit=true` 或 `root_save=true` 是保存行为参数，不是审批。显式 `page-flush`、`data-flush`、`recipe-flush`、`device-tree-flush`、`picture-flush`、`language-flush` 或 `root-flush` 在direct中直接执行对应保存，不另要求commit许可；`root-flush`本身即要求RootSave。原厂 worker 内嵌保存仍可能更新工程文件；回执必须准确记录每个 own_persistence_boundary 和新的期望 storage SHA。不要将已授权原厂保存误认为外部漂移，也不要任意接纳不明磁盘变化。最终一次统一保存需覆盖全部被改页面、策略及模块；引用改名也须保存完整真实消费者。

该入口不自动运行 PLC 通信、不下载、不启动脚本或设备运行。当前产品不支持原始策略动作时，应使用帮助和实际产品能力证明的等效合法脚本，并明确变量、计时器和对象绑定，不修改产品 OS/支持位来伪装兼容。

结束时分别记录保存、原厂检查、关闭重开和运行的实际范围；需要重载验收时按[设备重开比对](pro-native-device-reopen.md)区分持久业务字段与本次会话地址，不为每个小修改反复关闭重开。Root85通过条件见[在线界面施工](pro-native-ui-workflow.md)，单独的调用 `ok` 不能当检查通过。未知结构或未执行的验收明确记录 pending。

关闭重开使用专用生命周期入口，直接模式不要求六项许可参数或许可文件。入口在同一UI线程按原厂关闭/打开方法执行，保留原厂提示和保存语义；正常保存、关闭、重开按用户已授权任务连续处理，不逐项重问。调用前先完成当前工作文档的同步和保存；这些是原厂生命周期的状态前提，不是审批。旧生命周期permit命令只用于兼容历史脚本。可直接使用 `pwsh -NoProfile -File .\run.ps1 native-engineering close-reopen --project '<当前工程完整路径>' --timeout 180`，`--closed-copy` 可省略以自动生成独立快照。关闭重开后重新读取root、指针和文档身份，不能继续用旧对象地址。实际重开成功与完整业务数据回读分别记录。

本机已配置桥可沿原 TaskRoot/RuntimeRoot 使用新工程 scope。首次搬到另一任务或电脑时，先检查当前进程已有桥；普通启动且未接桥的 Pro 优先使用热接入口，按本次目录配置生成自有工具并连接。原 Addins/桥接启动器部署是可选兼容路径，不是每次在线修改的前提。只复制客户端或 scope 不会完成桥接。原桥的引擎加载目录和命名规则继续保留，部署时 DLL 与同名 `.scope.json` 必须一起放到该目录。

完整自有源码、目录绑定/首次部署工具、原生保存边界及配方/图库持久化合同见[部署与保存](pro-native-deployment.md)。包内源码需按本次显式目录生成绑定并编译；不能将未绑定模板当作可加载 DLL。
