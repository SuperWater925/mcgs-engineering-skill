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

直接执行在同一个原生队列调用内按动作顺序读取、准备和操作当前目标，无需生成 permit 文件。多步骤 program 的 `run` 默认合并连续同页、无结果依赖且兼容的编辑步骤，默认按实际依赖和消息大小分组（可用 `--max-merged-actions` 另外限定动作数）。显式查询、页面或元数据变化、保存、检查、不兼容动作和组内 `$ref` 依赖会结束当前编辑组。连续的显式页保存与末尾工程保存可另成一组，按顺序调用各自的原厂接口。单步原有动作保持完整，`--no-merge-steps` 保留逐步路线。已完成动作的真实 ID、名称和路径可通过 `$ref` 引用。

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

普通 direct 批次部分成功后，可用 `plan-remainder --id <原请求 ID> --request-sha256 <原队列 SHA-256>` 核对实际成功前缀、失败边界和未开始动作。确认失败动作未进入当次原厂应用后，可附 `--replace-failed <修正的单动作.json> --out <新规格.json>`，生成修正动作与尚未开始动作的草案。修正动作沿用原 ID、类别和目标，成功动作由原回执记录。命令只查询原队列并生成草案；准备下一次正常 `execute` 时，重新读取当前目标和工程状态。若原请求未终结、执行边界不明、原规格已改或剩余动作依赖已经执行的原生结果，先核对当前状态和相应回执。

Pro 可从当前已加载页面的单个静态矩形或斜线创建原生图库 VECT。提交 `picture-create-from-controls`，`target` 指定模块 11 和新名称。矩形使用 `source.kind: "current-rectangle-control"` 与 `CDrawRect`，线段使用 `source.kind: "current-line-control"` 与 `CDrawLine`。用当前页号、页名、顶层索引、控件名及类型定位。源控件须无动画、事件或引用。提交 `expected_reference_name:""`、`expected_reference_count:0`、`allow_original_selection_vector_creation:true`、`allow_original_hash_recompute:true`、`allow_private_animation_removal:false`。调用原厂选择转图与身份生成。采用前核对独立图元、画笔画刷及空引用，线段另核对画布和端点方向，再显式保存图片模块和工程。单条横线或竖线的原厂选区画布有一边为零，可通过离线 `add-vector-line` 提供正面积画布来创建。

同一页选取多个静态矩形、线段时，使用 `source.kind: "current-static-controls"`。在 `source` 填当前 `page_id`、`page_name` 及至少两项不同的 `controls`，每一项填写 `control_path`、`control_name` 和 `class`，其余参数沿用上述静态转图。图库内部沿用页面原有层次，依次保留每个图元的形状、笔刷和有序端点。选区总画布有正宽高时，可包含横线、竖线和斜线。写入只新增一个图库项。

多选可包含已有图库光栅引用的静态 `CDrawBitmap`。有位图时，`after.expected_reference_names` 按页面层次填每个所选位图对应的真实资源名，替代 `expected_reference_name` 和 `expected_reference_count`。采用前逐件用原厂接口核对图像身份，并在当前编辑会话中恢复对应具名引用。原厂保存图库时将对应光栅的尺寸和像素写入新 VECT 作为独立副本，重开后每个子件仍可编辑。源页面控件仍保留原引用，原图库资源保持原样。

矩形和线段组成的静态 `CDrawCell` 或 `CDrawUnit` 组可用同一入口转图库。源选择按顶层组定位，选中的一棵或多棵子树须合计至少有两个叶图元，且可包含嵌套组。沿用纯图元的 `after` 字段，并填写 `allow_original_group_flattening:true`。原厂按页面及组内层次生成独立叶图元，保留矩形、笔刷和有序线段端点。回执中 `original_groups_flattened_in_created_vector:true` 指新图库项的结构，源页面的组和所有子件保持原样。

本机原厂验收中新图与 86 个原资源的名称、尺寸及内容均已核对，源页面保持。原厂模块保存把 85 个既有图片行的存档签名更新为操作前已读取的原厂内存签名。文件校验、原厂检查与同一 Pro 实例关闭重开分别通过。

不含其他引用的原生 `picture-rename` 可以提交模块 11、现有资源名称和 `after.name`。服务从当前原厂前像推导完整目录，按名称比对每个记录，独立保持图库实际展示顺序；可处理本次导入时内嵌名称为空、没有帧的普通光栅。图库和工程保存各自有回执，按保存的实际像素及索引复读。涉及其他业务引用时沿用当前消费者后像合同。

普通 `reference-graph` 可读取已存在的 `CTriggerEvent`。策略记录通过共用原生策略目录取得，`trigger_fields` 提供策略 ID、触发器记录 ID、条件表达式、两个完整原生尾词，以及编译条件缓存的字节数和全量 SHA-256。正反向引用边仍由原厂已登记图读取，包含原有所有策略和其它消费者。Event 字段按当前程序的原生类、虚表、序列化成员布局及 MFC 字节数组身份进行只读定位。`trigger_write_supported=false` 表示通用触发器和策略生命周期入口仍使用原有四类写入合同。

`reference-sync` 按指定页面生成并保存时，可同时捕获工程中未选中的 Event 策略及完整引用图。作用域可使用非空 `page_ids` 和空 `strategy_ids`。通用同步准备阶段会拒绝把只读 Event 策略选入 `strategy_ids`。

`strategy-event-edge` 修改现有 Event 的条件选项。目标用当前策略的 `block_id` 与 `block_name`，例如 `{"kind":"strategy-event-edge","target":{"block_id":15,"block_name":"AuditEventOnFall"},"after":{"edge":"rising"}}`。原生读取可用空 `after` 查询当前值。可写 `rising`（正跳变）、`falling`（负跳变）及 `change`（数据变化）。读取可报告已存的 0→1→0 和 1→0→1，已验原厂编译器会拒绝这两种条件。策略和 Trigger 行各自保留现有表达式及编译缓存。更改前在 Pro 内部工作台选中该策略的可见管理行，目标同名私有工作编辑器须关闭。该步骤不改变系统前台窗口。

编辑使用 `commit:true`，在同次请求里通过原厂写入所选 Trigger 行。内存和 DAO 行各自保留原有的条件表达式、缓存、延时与身份，并核对完整已登记引用图。设置 `root_save:true` 可在本批末尾执行一次原厂工程保存，也可与其它操作集中使用一次 `root-flush` 保存根归档。请求正好等于当前跳变模式时无工程写入。工程检查及关闭重开按统一阶段另行回执。

用 `strategy-create` 新增空循环策略且保持策略编辑器关闭时，设置 `trigger_type: "Loop"`、`initial_row: "none"`、`open: false`，并按当前查询填写 `expected_next_block_id`。省略 `reference_edges` 可沿用本次读取的完整原引用图。若显式提供完整引用图，先核对其与原图一致再开始创建，完成后再核对全图。带初始行、打开编辑器或其它策略操作使用各自的既有合同。

普通页面上的多态按钮，可用 `control-properties` 读取完整分段和图文属性。要更换某个已有具名图片帧，按本次实际 `component_path` 定位 `分段点`、`图像列表`、`背景图`，各段用原生同名组件的 occurrence。提交已读到的 `背景图片`（原生 tag 12）和同一工程图库中实际存在的目标名称。保存该页和工程，再分别核对目标帧、原生状态目录、工程图库和文件归档。

单项与批量属性写入在原厂修改前查当前图库中的实际非空名称。空值、已匹配值及其它类型沿用对应属性语义。状态目录立即反映新名称。重开前需要使用最新引用图时，可对已验证的普通双态多态按钮另行执行以下原生操作。

- 读取 `reference-sync`，`target` 带唯一 `page_ids`、空 `strategy_ids` 和 `control`，控件按真实页号、页名、完整路径、名称、类和 RTTI 定位。该入口只接收两个状态各一个具名图片帧且无文字帧、事件或动画的类型。
- 执行时使用本次完整前像和 ABI 回执，`commit:false`，`after.allow_original_control_generate:true`。用完整 `after.expected_reference_edges` 提交预期图，保留所有其他边，只把该控件到模块 11 的图片边替换为实际 `named_picture_targets`，同图同名只保留一条。
- 原厂只重建所选控件的引用。核对完整双向图、原生图文状态、图库目录和文件哈希。另行集中保存该页和工程。其他按钮形态使用各自已验证的整页同步或正常关闭重开。

已有文字帧的路径为 `分段点`、`文本列表` 及各级实际 occurrence。只修改当前读取的 `动画文本`（原生 tag 8）时，原厂保持其颜色、字体和位置等其它已读属性。随后核文件中的文字与同一状态原生回读。

`language-management-catalog` 返回 Pro 工程的 `current_language_id`、`preview_language_id` 和已配置原生 ID。要调整其中一项，在 `language-management-batch` 的 `after.operations` 写入 `{"operation":"language-selectors","expected_preview_language_id":0,"preview_language_id":1}`。同一操作可用对应的 `expected_current_language_id` 和 `current_language_id` 改当前语言。每项必须提供本次实际旧 ID，目标 ID 必须已配置并有项目定义。选择器变更放在文本操作之前。批次同时指定 `refresh_configured_font_map:false`、`allow_original_font_cache_changes:false` 即可保留现有字体映射。

写入时核对当前 CLinguist 虚表分派及实际原厂 setter，提交后回读两个选择值、配置、定义和文本映射。用已有 `language-flush` 和 `root-flush` 完成归档保存，再独立核对 `MCGSLINGUIST` 和原厂重开。已在 Pro 3.5.2.12210 原厂分别将预览语言与当前语言从 0 调为 1，保存后原厂检查为 0 错误，独立归档与同进程重开均读到 1。运行画面使用自身的语言选择与显示流程。

本机已配置桥可沿原 TaskRoot/RuntimeRoot 使用新工程 scope。首次搬到另一任务或电脑时，先检查当前进程已有桥；普通启动且未接桥的 Pro 优先使用热接入口，按本次目录配置生成自有工具并连接。原 Addins/桥接启动器部署是可选兼容路径，不是每次在线修改的前提。只复制客户端或 scope 不会完成桥接。原桥的引擎加载目录和命名规则继续保留，部署时 DLL 与同名 `.scope.json` 必须一起放到该目录。

完整自有源码、目录绑定及原生保存合同见[部署与保存](pro-native-deployment.md)。普通用户通过 `turnkey prepare-online` 自动取得与当前技能配套的预编译引擎，只物化本机资料。源码编译仅供维护者开发，不是换电脑或换 Pro 版本后的必做步骤。
