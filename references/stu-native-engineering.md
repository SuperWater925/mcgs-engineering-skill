# Stu 原生在线入口

同一完整包内的 Stu、Pro 共用 Python、PowerShell 和热接队列。Stu 使用自己的预编译原厂接口适配器。接收端从当前安装定位实际函数和对象类型，按动作报告支持情况。发行版本与作者机器的整文件指纹均无需相同。

## 接入和选择工程

普通方式打开 McgsStu 和要读的 MCS。使用已明确的运行实例，多个实例时指定 PID。把本次连接的完整 JSON 保存到自有工作目录，后续从该回执读取实际会话。

```powershell
& .\run.ps1 turnkey fetch-bundle --family stu
& .\run.ps1 turnkey prepare-online --family stu --pid $StuPid --no-download > $Connection
& .\run.ps1 native-engineering --family stu --connection $Connection inspect --project $Project
& .\run.ps1 native-engineering --family stu --connection $Connection capabilities --project $Project
```

Stu 适配器支持工程身份、页面与控件目录、设计页激活、同页标签与几何批量修改、原厂控件模板复制和组态检查。用 `capabilities` 核对当前进程的能力。已连接表示队列已响应。各个在线动作仍需当前映像的对应角色和实际原厂对象通过核对。

## 原生目录和组态检查

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection page-catalog --project $Project
& .\run.ps1 native-engineering --family stu --connection $Connection control-catalog --project $Project --page-id $PageId --page $PageName
& .\run.ps1 native-engineering --family stu --connection $Connection compile --project $Project
```

控件目录使用原厂回读的页 ID 和完整名称。`control_count` 是原厂编辑器目录的对象数量，部分组会展开为组内图元。`control_path` 记录该目录位置。实际原厂顶层列表可读时另提供 `top_level_control_count`，并为顶层项给出 `top_level_path`。文件归档层级使用离线控件树核对。四个查询保持工程和原生配置，`compile` 调用原厂检查并更新编译状态，返回本次计数和诊断。分别记录文件回读、原厂检查、关闭重开和模拟。

## 激活设计页并批量修改静态标签

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection page-view-open --project $Project --page-id $PageId --page $PageName
& .\run.ps1 native-engineering --family stu --connection $Connection control-catalog --project $Project --page-id $PageId --page $PageName
& .\run.ps1 native-engineering --family stu --connection $Connection label-properties-batch --project $Project --spec $LabelBatch
```

`page-view-open` 使用原厂页面打开逻辑，再核对实际活动的设计子窗。写入前确认 `page_view.exact_page_is_active` 为真。切换发生在 Stu 内部，保持系统焦点及主窗口大小。批次规格使用同一 `page_id` 和完整 `page`，`changes` 每项填写目录中的 `control_name`、`native_type_id`、`before` 和 `after`。以下数值只演示 JSON 结构，实际身份与前值都取自本次目录。

```json
{
  "page_id": 2,
  "page": "主页",
  "changes": [
    {
      "control_name": "标签",
      "native_type_id": 20488,
      "before": {"caption": "原文字", "caption_primary": "原文字", "text_color_bgr": 16777215},
      "after": {"caption": "新文字", "text_color_bgr": 2378244}
    }
  ]
}
```

`before` 记录两份现有文字和原始颜色整数。`after` 可提交文字、普通 24 位 BGR 颜色或两者。文字写入要求两份原文字一致。颜色写入要求旧颜色也是普通 BGR。标签须由该页直接持有且没有事件和动画；复杂形态使用对应的离线入口。批次在任何字段写入前核对全部目标，实际修改完成后对同一设计视图集中刷新并保存该页和工程。分别检查 `view_refresh_verified`、`page_save_verified`、`root_save_verified`，再做独立文件回读。没有字段变化的请求返回 `no_changes`。

## 批量调整位置和尺寸

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection control-geometry-batch --project $Project --spec $GeometryBatch
```

几何批次每次处理一页，使用 `page_id`、`page` 和 `changes`。每项需要目录给出的 `top_level_path`、`control_name`、`native_type_id`，以及 `before.rect` 和 `after.rect`。矩形由左、上、右、下四个整数组成，按设计页坐标填写。使用原厂顶层路径区分同名控件。标签、输入框和标准按钮的原厂 Setter 分别验证，`capabilities` 给出各类状态。写前核对本批次所有身份和矩形，写后回读四个坐标，集中刷新并保存该页及工程。

## 读取与切换已有可见动画

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection control-visible-read --project $Project --spec $Animation
& .\run.ps1 native-engineering --family stu --connection $Connection control-visible-mode-edit --project $Project --spec $AnimationEdit
```

规格填写当前 `page_id`、`page`、`top_level_path`、`control_name`、`native_type_id` 和从零开始的 `animation_index`。写入再填本次原生回读的 `expected_expression`、`expected_mode` 与目标 `mode`。原厂模式 0 在表达式非零时可见，模式 1 在非零时不可见。原样读取其它模式值，写入支持已确认的 0 和 1。修改发生在 Stu 内部当前页，原表达式和动画集合位置保留，然后刷新并保存页与根工程。

## 复制同页原厂控件

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection control-template-clone-batch --project $Project --spec $CloneBatch
```

使用与几何批次相同的字段。源控件为该页的真实顶层标签、输入框或标准按钮，处于当前原生绘图模式 0 或 1。可重复使用同一源控件。`before.rect` 是来源前像，`after.rect` 是新控件的位置和尺寸。原厂创建独立对象并分配名称，`changes[].actual` 返回新名称、顶层路径、控件类和实际位置。保留源控件并核对原输入绑定、按钮信息及标签内容。批次复用内部活动页并集中刷新和保存。部分执行先从原回执确认已收养和已保存的对象。

## 新建默认原厂控件

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection control-native-create-batch --project $Project --spec $CreateBatch
```

规格包含当前 `page_id`、完整 `page` 和 `changes`。每项填写 `native_type_id` 与 `after.rect`。原厂类型为标签 20488、普通输入框 20517、标准按钮 20519；当前接入模式为 0 和 1。先激活目标设计页，再逐个创建并由原厂命名。每个新件保留原厂初始字段，输入框的变量和按钮的脚本从各自默认值开始。回执给出实测名称、类、矩形和真正顶层路径，以及刷新、页保存和根保存状态。

## 新建和复制用户窗口

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection page-native-create --project $Project --spec $CreatePage
& .\run.ps1 native-engineering --family stu --connection $Connection page-native-copy --project $Project --spec $CopyPage
```

新建空窗填写 `page_name` 和当前目录的 `expected_page_count`。复制另外填写源页的 `source_page_id` 和 `source_page_name`。复制使用当前工程内的无保护源页，按原厂归档保留控件、脚本及原有引用，包括指向源页的引用。原厂保存后读回新窗口 ID、名称和控件数，操作前的活动设计页保持。新窗口可用返回的 ID 和名称打开。

## 读取实时数据库与编辑标量备注或单位

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection data-catalog --project $Project
& .\run.ps1 native-engineering --family stu --connection $Connection data-read --project $Project --spec $Variable
& .\run.ps1 native-engineering --family stu --connection $Connection data-edit --project $Project --spec $VariableEdit
```

变量规格使用本次目录返回的 `name`、`native_id` 和 `native_type`。编辑现有标量时再填 `before` 和 `after`，两者包含同样的字段，可选 `comment` 和 `unit`。实际写入时激活 Stu 内部实时数据库工作台，集中保存原厂数据模块与根工程，再逐条复核数据名称、ID、类型、初值和非目标备注、单位。操作结束后恢复原活动页。

## 读取配方与编辑现有单元格

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection recipe-catalog --project $Project
& .\run.ps1 native-engineering --family stu --connection $Connection recipe-read --project $Project --spec $Group
& .\run.ps1 native-engineering --family stu --connection $Connection recipe-cell-edit --project $Project --spec $Cell
```

读取规格填写完整 `group_name`，可加从零开始的 `offset` 与正整数 `limit`。编辑规格填写 `group_name`、从零开始的 `row_index`、`column_index`、字符串 `expected` 与 `after`。列定义的原厂类型决定输入格式，已识别整数、数值与字符列。写入前检查当前内存值和原厂具名归档，根文档和配方模块应处于已保存状态。写入使用原厂单组持久化入口及根保存，回读目标单元格并核对同组其余归档内容。配方属于 Stu 独立对话框，工程写入期间内部显示实时数据库工作台，结束后恢复原活动页。

## 读取和编辑策略源码

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection strategy-catalog --project $Project
& .\run.ps1 native-engineering --family stu --connection $Connection strategy-source-read --project $Project --spec $SourceSelector
& .\run.ps1 native-engineering --family stu --connection $Connection strategy-source-edit --project $Project --spec $SourceEdit
```

用策略目录里的 `block_id` 和 `block_name`，再用 `row_index` 选定实际的原厂 `CStgyFuncProg`。读取返回全文和 UTF-16LE SHA-256。写入规格在同一选择器上加 `expected_source_sha256_utf16le` 及完整 `source`。先激活 Stu 内部策略工作台。如果同一策略已打开独立设计文档，先由该窗口处理现有草稿，避免从保存模型覆盖工作副本。程序内容使用原厂 `TrimRight` 投影，`source_normalization` 和前后摘要可核对保存的精确文字。

分别检查 `native_script_compile_passed`、`native_strategy_compiled`、`native_strategy_saved`、`root_save_verified` 和最终源码回读。写入后 `native_project_compile_required` 为真。回执保留原厂根编译标记的前后读值，整项目的当前有效性以最后一次原厂 `compile` 为准。策略类型、触发设置及其它策略源码保持原值。

## 在同一 Stu 进程关闭并重开

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection project-lifecycle-state --project $Project
& .\run.ps1 native-engineering --family stu --connection $Connection project-reopen --project $Project --id $OperationId
& .\run.ps1 native-engineering --family stu --connection $Connection project-reopen-result --project $Project --id $OperationId
```

`project-reopen` 要求工程及打开的子文档已保存。它先在原 UI 线程核对关闭和重开入口，再调用原厂关闭。关闭返回且两个工程根均为空时，才以第二条原厂请求打开同一路径。回执分别记录 close 和 open。成功后重用当前进程的连接。

超时时凭原 ID 查进度。若回执确认关闭已完成，且 open 为 `not_submitted`，可给 `project-reopen-result` 加 `--continue-open` 继续原操作。若 open 已提交，查询它的原回执即可。原厂出现备份恢复提示时，先在当前编辑器处理提示，再查同一请求。项目重新加载后，原厂检查及独立文件回读按实际执行分别记录。

## 页面逻辑尺寸和背景色

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection page-properties-read --project $Project --page-id $PageId --page $PageName
& .\run.ps1 native-engineering --family stu --connection $Connection page-background-edit --project $Project --spec $BackgroundChange
```

先读 `page_properties` 取得页面身份、工程逻辑宽高及原始背景色。背景编辑规格如下，前值取自当前原厂读回。

```json
{
  "page_id": 21,
  "page": "公共窗口_主页",
  "before": {"background_color_bgr": 3223857},
  "after": {"background_color_bgr": 15920871}
}
```

读回保留背景色的完整 DWORD。编辑使用高字节为零的普通 24 位 COLORREF。写前激活 Stu 内部的目标页，回读背景及逻辑宽高，分别核原厂绘图刷新、页保存和根保存。逻辑尺寸由这个入口读取。相同前后颜色返回 `no_changes`，不激活页面或发起保存。文件独立回读和原厂检查另记。

请求超时时查询原请求 ID 和已提交请求的 SHA。用 `request-result --project <同一工程> --id <原 ID> --request-sha256 <原摘要>` 查询当前队列。旧 Pro 专用包可作为配有 Stu 引擎的小更新基底。接收端按当前 Stu 技能源码核对预测的引擎合同和预编译产物。`--no-download` 时使用本地已有的匹配目录或更新包。
