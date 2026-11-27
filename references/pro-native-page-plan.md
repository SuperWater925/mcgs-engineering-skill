# Pro 整页设计与原生回读

`run.ps1 native-page-plan` 接受 JSON 设计声明，将原生检查回执整理为当前页快照，编译为既有 native engineering session program，并生成独立的 HTML 对照。准备、编译和生成报告都是纯文件操作。工程变更沿用 session 的 stage、run、原生身份守卫和失败前缀记录。

## 从原生检查取得快照

用 [原生编辑入口](pro-native-deployment.md) 对当前工程执行只读 `engineering-edit-inspect`。每页可用一次 `control-native-create` 的读适配器取得完整绘图树，并核当前页及类的原生构造接口。以下是 inspection specification 中的选择器。

```json
{
  "actions": [
    {
      "action_id": "source-page",
      "kind": "control-native-create",
      "target": {"page_id": 3, "page_name": "Title", "class": "CDrawRect"}
    },
    {
      "action_id": "source-button",
      "kind": "button-actions-batch",
      "target": {"page_id": 3, "page_name": "Title", "control_path": [2],
                 "control_name": "控件6", "rtti": ".?AVCDrawButton@@"}
    }
  ]
}
```

ID、名称、路径、控件类和大小以本次工程实际值为准。也可用 `control-geometry-batch` 采集有已知目标的整页树。每个将创建的新类都需要该页相应的成功 factory 读取。原根属性来自 `control-properties`，用 `control_path`、`control_name` 和 `rtti` 选择对象。当前样式入口接受根 getter 的 `native_key`、`native_type_tag`、`value`，字体保留原 flag 和真实语言行。给新控件配置样式时，同页同类的 getter 样本须能证明相应成员的类型。

`data-catalog` 提供变量名称。可选 `reference-graph` 提供完整已登记边，及 MainCtrl 当前配置的辅助窗口列表。声明 `common_page_ids` 时，逐个核这些页已采集且在该列表内。需修改公共窗时，将公共窗作为一个单独的页面增量编排。辅助窗口列表只证明配置归属，具体运行页中是否显示仍需模拟证据。

```powershell
.\run.ps1 native-page-plan snapshot --receipts inspect-before.json --out before.json
```

## 设计声明示例

```json
{
  "schema": "mcgs-page-design/v1",
  "project_path": "D:/Test/Project.mcp",
  "save": true,
  "pages": [{
    "id": 3,
    "name": "Title",
    "resolution": [800, 480],
    "layers": [{
      "id": "main",
      "controls": [
        {"id": "source", "existing": {"path": [2], "name": "控件6", "class": "CDrawButton"}},
        {"id": "array", "depends_on": ["source"], "array": {
          "source": "source", "rows": 2, "columns": 3,
          "row_gap": 8, "column_gap": 12, "origin": [30, 80]
        }}
      ]
    }]
  }]
}
```

`resolution` 以当前页实际宽高为准，示例数字不设默认值。已有对象按实际路径和身份取证，可进一步给出 `native_id` 或 `complete`。原生属性和几何编辑先于新增原生内容。新增对象使用实际构造回执的完整身份，数组内按行列顺序生成同源连续克隆，结束统一保存。源可为当前页面的已有顶层控件或前面新建的原型，均继承源的实际内部组态。规则阵列使用原生模板克隆，重叠布局可声明并在报告中看到原件与实例重叠。各矩形必须落入实际页面，组内几何按原生 10000 坐标合同；改变组矩形需显式启用 `transform_group_children`。

普通图层采用原生新增顺序 `placement: "append"`。需要底板的层显式指定 `placement: "back"`，用原厂调层调用把该层自己的新增对象连续置底，已存在的对象保留相互顺序。使用页面的 `remove` 声明目标身份，使用 `control_order` 声明保留顶层控件的完整顺序。依赖应定义在前面的设计控件上。其中已有对象的路径型修改在新增前执行，依赖新增对象的已有路径型修改需要拆成独立规划。

`bindings` 核对采集到的原绑定。写入时使用 `binding_updates`，提供真实 getter 的 `native_key`、`native_type_tag` 和 `value`。纯变量连接可增加同名 `variable`，根据当前数据目录检查；tag 6 的 `value` 用 `text` 记录变量名、`number` 记录目标变量的实际 `native_type`。组件在 `component_updates` 中提供原生组件 `path` 与 `properties`，每个路径单独采集。标准按钮 BasicProxy 的水平或垂直对齐由两态共享，同时声明抬起和按下组件的同一个值。按钮 `button_changes` 需要相位、槽号、启用态和文本。数组 `overrides` 使用从 1 开始的 `cell: [row, column]`，支持对应的绑定、组件和按钮更新，目标从本次克隆回执定位。其它字段由原型继承。

已有控件的 `events` 按原厂声明 ID 或现有事件索引配置完整列表，`animations` 复用动画计划的有序业务规格。先通过相应原生检查采集实际前像，再生成计划。计划可带完整 `expected_reference_edges` 并传递已证明的 `native_derived_cache_contract`，独立运行引用同步。

页级 `remove` 要求原始顶层路径、名称、类型、原生 ID 和当前对象身份。可选 `control_order` 列出全部最终顶层对象，原对象使用采集路径，新对象使用设计 ID（数组格使用 `id[row,col]`）。执行中以对象身份和实际回执重建位置。

新增、调整页面分辨率和删除空页通过 `native-page-plan prepare-pages --design … --snapshot … --program …` 生成第一阶段。设计格式为 `mcgs-page-setup/v1`，需要项目完整路径和 `operations`。每个操作包含 `operation`（`create`、`size` 或 `delete`）与 `name`。已有页需给出 `id`，调整尺寸需提供 `resolution`。新页可同时提供分辨率，调整请求读取实际新页 ID。结构阶段完成后重新采集，再编译和保存画面，便于使用新对象、尺寸与路径。

### 原厂组合和拆组

打开或激活目标设计页，再为当前页面和顶层控件准备一份组合设计。组合以原厂文档层序接收控件，生成新的符号组。拆组传入一个 native `CDrawCell` 的现有身份。每个选择器使用实际路径、名称与类，可同时给出本次原生 ID 和完整对象地址。以下是组合规格示例。

```json
{
  "schema": "mcgs-page-group-design/v1",
  "project_path": "D:/Test/Project.mcp",
  "page": {"id": 3, "name": "Title"},
  "operation": "group",
  "save": true,
  "controls": [
    {"path": [0], "name": "矩形1", "class": "CDrawRect"},
    {"path": [2], "name": "椭圆1", "class": "CDrawEllipse"}
  ]
}
```

```powershell
.\run.ps1 native-page-plan group-inspect --design group.json --out group-inspect.json
.\run.ps1 native-page-plan prepare-groups --design group.json --capture group-before.json --program group-program.json --readback group-readback.json --review group-review.json
.\run.ps1 native-page-plan group-report --review group-review.json --capture group-after.json --out group-result.json
```

第一条生成原生 `inspect` 的只读规格，回执保存为 `group-before.json`。第二条从本次回执生成标准工程程序，正常使用 `stage`、`run`。当前支持使用原厂基类坐标虚槽且无事件、无动画的静态矩形、椭圆、标签和线段。按 Win32 `MulDiv` 语义转换坐标，线段保留有向端点。拆组需从实际目录定位当前 `CDrawCell`，并核对每个子件的同一坐标合同。原生执行前重新核对当前目标页面的活动设计器、绘图树、选择、属性、链接及引用图，并独立复算成员的预期坐标、属性和原厂选择。入组成员的外部入引用、拆组容器本身的引用、未证坐标角色及顶层名称冲突都会阻止计划执行。

组合时可显式设置 `flatten_selected_cells: true`，选入同页一个或多个顶层静态 `CDrawCell`。原厂组合会移除所选旧容器，把其直接子件和选中的普通控件按文档顺序放入同一新组。计划先把旧组局部坐标换算成页面坐标，再以新组实际包围框计算局部坐标。只接收上述四类静态叶件，仍逐件比对地址、属性、原注册路径及全图。旧容器的出入引用、现有成员的外部入引用、嵌套容器和重复名称都会阻止写入。

第三条用 `group-readback.json` 另做一次原生 `inspect`，从回执独立检查同一实例中的页面身份、页面目录、每件位置、绘图父子树、原生对象身份、属性和完整注册引用。原厂组合前后，既有成员的注册对象路径仍以页面为前缀，绘图树中的新父级另行核对。原厂保存结果查 `page-flush` 和 `root-flush` 回执。文件、组态检查、重开和模拟另留实际证据。在线跨两个既有组迁移仍需专用原厂入口及引用适配。

```powershell
.\run.ps1 native-page-plan compile --design design.json --snapshot before.json --program program.json --review review.json
```

把输出 `program.json` 交给已有 `engineering_session.py stage` 和 `run` 的原生部署入口。按已授权范围一次运行。选择保存时，每个变更页一次 `page-flush`，末尾一次 `root-flush`。纯保留声明没有动作时只输出 review。编译不连接 Pro，不生成审批文件，也不代表当前构建已通过验收。

编译计划携带本次快照的 `design_preflight`，首个原生执行调用在任何动作前核对进程代际、工程路径/文件、根/页面身份、有序控件树及实际依赖的样式和绑定；后续保存阶段不重复套用修改前的旧快照。计划要求的 `required_features` 只覆盖实际使用的能力。执行前用一次轻量只读能力查询核对当前加载引擎，不能仅凭动作名称相同推断旧引擎支持新选择器。已有对象使用完整身份；不消费完整身份的新建操作不额外要求该能力。

克隆资格来自当前源子树和原生调用合同，明确不支持的类在任何工程写入前报告。依赖经过无改动节点仍保留传递关系。同页彼此独立的叶控件几何与样式可分别合批；存在依赖、重复对象或父子关系时维持顺序。读取旧 `$native_result` 的 `forest_after` 等完整投影时只对涉及的克隆保留旧单件回执，其余仍可合批。不能用调序或删依赖来增加合批数量。

## 生成 HTML 对照

原生完成后独立再读整页，按需补读 typed properties 与按钮两相动作。使用新回执生成 `after.json`，将 session 留存的原始 `*-rpc-response.json` 与新快照一起提供给报告。

```powershell
.\run.ps1 native-page-plan snapshot --receipts inspect-after.json --out after.json
.\run.ps1 native-page-plan report --review review.json --snapshot after.json --receipts page-plan-rpc-response.json --out review.html
```

新对象身份来自真实新增/克隆回执，引用由本次设计和原生前像命名。报告比较真页尺寸、几何、所有者、层序和已读绑定。没有绑定样本则显示未读到。相同文档实例核完整内存身份；提供本次正常重开证据后按页 ID 和唯一持久原生 ID、类、名称匹配重载对象。重新打开后的多解仍需人工核实。示意图使用实际页坐标，原厂字体、动态状态和截图单独验收。

实际视口可用 `snapshot --viewport observation.json` 补充可靠的测量结果。输入 `schema: "mcgs-page-viewport-evidence/v1"`，`actual_project`、`process_id`、`creation_filetime`，以及 `pages` 数组中的 `page_id`、`document`、`hwnd`、`visible_page_rect` 和 `source`。可附测得的 `zoom`。可见矩形必须是扣除滚动和缩放后的页坐标。没有对应观察时显示未读到；窗口像素宽高不能直接代替页坐标。

报告的可选 `--evidence` 文件分别保存 `save`、`file`、`check`、`reopen`、`simulation` 的实际原始或提取证据。每项含 `actual_project` 和证据来源 `source`，以及具体读值。保存核 `native_save_return_verified`、`root_modified`、`sha256_after`；文件核 `independent_file_readback_verified`、`sha256`；检查核本次 Root85 worker 返回、检查结果和最终 compile flag；重开核 `normal_project_closed_then_reopened_verified` 与 `open_confirmed_same_project`；模拟核 `simulation_executed` 与 `observed_result_verified`。分项显示缺证据。HTML 预览和动作 `ok=true` 无法替代这些验收。

重开还须携带真实生命周期回执中的 `state_before/state_after`、进程 ID/创建时间、根身份、当前文件 SHA，并关联本次 `review_id`。只有路径相同或两个成功布尔值不能证明本次重开。不得用设计值伪造原生状态字段。层序比较覆盖每个父组的有序子项；分组内部交换顺序不能被顶层数量相同掩盖。


## 新建控件的业务声明

原始设计可给新控件或数组格声明 `binding_updates`、`component_updates`、`button_changes`、`events` 与 `animations`。例如，`{"cell":[1,2],"animations":[{"add":"CAniVisible","visibility":{"expression":"1"}}]}` 给第 1 行第 2 列追加可见动画。数组格从构造或已有原型继承当前原生属性，新建原型的后续修改只应用于原型自身，数组格各用自己的 `overrides`。使用已有原型时，已读取原型的绑定、组件、按钮覆写可随首轮克隆应用。

首次编译把需要读新对象前像的业务修改保存在 review 的 `deferred_updates`，首轮按原生构造和克隆回执核对。打算集中保存时，首轮设置 `save: false`，完成后续修改后统一保存。首轮创建完成后留存原始执行回执，重新读取实际控件树并生成快照。以下两个命令默认使用 review 中的待办声明。

```powershell
.\run.ps1 native-page-plan followup-inspect --review first-review.json --snapshot fresh.json --receipts action-rpc-response.json --out details.spec.json
.\run.ps1 native-engineering --scope-config connection.scope.json inspect --project D:/Work/Example.mcp --spec details.spec.json --require-all > details.json
.\run.ps1 native-page-plan snapshot --receipts inspect-forest.json details.json --out detailed.json
.\run.ps1 native-page-plan followup --review first-review.json --snapshot detailed.json --receipts action-rpc-response.json --out second-design.json
```

第一条命令从本次回执与新控件树生成目标当前路径、完整身份和类型的只读选择器。第二条命令按声明读取该控件的绑定属性、具体组件属性、按钮槽、事件或动画。声明了具名绑定变量时同时读取数据目录。用 `detailed.json` 和 `second-design.json` 再运行普通 `compile`，复用其原生前像检查、写入及独立回读。两阶段之间保留同一个工程、进程代际和页面实例。多个需要改变页面历史属性 13 的编辑按原有规则在状态变化后重新采集，可通过 `--updates` 分开生成。

有任何请求字段未读到时，`inspect --require-all` 退出码为 2，保留完整原始回执和已读取的部分。依赖完整前像的后续计划等全部目标可读后再执行。

按钮槽的 `text` 按所选动作的原生语义填写。本机实测标准按钮 `phase:0, action_index:1` 是打开用户窗口，文本填写当前工程实际窗口名，保存并通过原厂检查。

页面操作使用独立的 page-setup 计划。策略、数据、配方、资源及模拟交互各有证据范围。页面报告仅涵盖本次声明与实读字段。部分执行后依据成功动作回执和新快照确认剩余工作，再编译新计划；原计划不得自动重放。

`followup --updates updates.json` 仍可显式指定新建或克隆控件的补充编辑。更新文件提供首轮 `review_id` 和 `updates` 数组。每项含新的设计 `id`、首轮控件的真实 `result_action`，以及对应业务声明。最终保存与引用同步可在更新文件中通过 `save`、`expected_reference_edges` 和需要时的 `native_derived_cache_contract` 显式声明。重开后需重新核对身份，再用普通 `existing` 声明。

## 多模块计划与独立回读

`native-page-plan project --design plan.json --program edit.json --readback verify.json --review review.json` 输出两个标准 session program 和一份核对单。设计为 `mcgs-project-design/v1`，包含工程绝对 `project_path`、`sections` 和 `checks`。每个 section 指定 `domain` 和已有工具生成的 `program` 对象。可用域为 `pages`、`data`、`strategies`、`recipes`、`pictures`、`languages`、`devices`、`references`。按依赖排列，工程路径一致且步骤 ID 唯一。页面片段使用 `save: false` 生成，保留它的实际前像和动作 ID。

在可选的 `persistence` 提供 `flush` 列表和布尔值 `root_save`。每个保存项提供原生 `kind`、`target`，例如 `page-flush` 使用原生 `page_id`、`page_name`。最终按明确列出的模块顺序保存，最后按要求调用一次 `root-flush`。引用重建沿用同一 session 的实际边集核对。原厂动作若自带保存，以它的回执为准。

本机实测一个联合计划在先执行 `page-flush` 后，语言新记录已可从文件读取，语言模块的 `modified` 已为 0。此时独立 `language-flush` 会拒绝。依照已完成动作和实际文件回读，保留语言写入和页面保存，只完成剩余的根工程保存，再运行独立回读计划。

每条检查包含 `id`、`domain`、`selector`（原生 `kind`、`target` 和可选 `after`）以及 `expected` 列表。每项 expected 包含相对于当前原生 `before` 的 JSON Pointer 和预期 `value`，例如 `{"pointer":"/record/comment","value":"Reviewed"}`。每个域提供至少一条检查。先正常 stage/run 编辑，结束后独立 stage/run 验证程序，最后执行 `native-page-plan project-report --review review.json --readback-session <验证会话目录> --out result.json`。报告比较指定的业务值并核对请求身份。文件回读、原厂检查、关闭重开和模拟分别保留自己的验收凭据。实际功能仍由本机原生适配决定。

检查选择器可用 `{"$ref":"/steps/<检查ID>/inspect/..."}` 引用本次独立会话之前一条检查的原厂回执。报告先核对来源请求，再用解析后的选择器核对实际请求和回读。来源缺失或身份不符时，依赖该来源的检查标为 `unverified`。

可见条件回读只对已见的 CAniVisible 常量 1 记录识别空缓存转为特定 32 字节原厂结果。检查证据需含本次 `review_id`、原厂 Root85 类型与工作线程返回及编译有效值，检查后状态需对应重开前的工程、进程、根和文件指纹。任何其它缓存值、记录字段差异或证据缺失均沿用完整记录比较。
