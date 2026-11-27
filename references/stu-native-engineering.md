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

## 原厂生成并保存单页

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection page-native-generate --project $Project --spec $PageGeneration
```

规格填写 `page_id`、完整 `page` 和本次控件目录的 `top_level_control_count`，最后一项在规格中填为 `expected_top_level_count`。原厂设计页生成使用同一个页面的文档和顶层控件，完成后刷新设计页并保存单页和根工程。`native_selected_page_generated`、`page_save_verified` 和 `root_save_verified` 分别记录调用结果与两层保存。具体事件的派生缓存仍逐项从落盘归档读取，工程检查使用 `compile`。

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

几何批次每次处理一页，使用 `page_id`、`page` 和 `changes`。每项需要目录给出的 `top_level_path`、`control_name`、`native_type_id`，以及 `before.rect` 和 `after.rect`。普通矩形由左、上、右、下四个整数组成。直线按设计页坐标填写有向端点 `[x1,y1,x2,y2]`，支持水平、垂直和反向。使用原厂顶层路径区分同名控件。标签、输入框、标准按钮及静态直线和矩形的原厂 Setter 分别定位，`capabilities` 给出各类状态。静态图元要求绘图模式为 0 或 1，且不带事件或动画。写前核对本批次所有身份和原坐标，写后回读四个坐标及静态图元原有笔刷字段，集中刷新并保存该页及工程。

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

规格包含当前 `page_id`、完整 `page` 和 `changes`。每项填写 `native_type_id` 与 `after.rect`。原厂类型为直线 20482、矩形 20484、标签 20488、普通输入框 20517、标准按钮 20519。当前接入模式为 0 和 1。直线的 `rect` 按 `[x1,y1,x2,y2]` 提供有序端点，支持水平、垂直和反向。先激活目标设计页，再逐个创建并由原厂命名。每个新件保留原厂初始字段，输入框的变量和按钮的脚本从各自默认值开始。回执给出实测名称、类、坐标和真正顶层路径，以及刷新、页保存和根保存状态。

## 新建和复制用户窗口

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection page-native-create --project $Project --spec $CreatePage
& .\run.ps1 native-engineering --family stu --connection $Connection page-native-copy --project $Project --spec $CopyPage
```

新建空窗填写 `page_name` 和当前目录的 `expected_page_count`。复制另外填写源页的 `source_page_id` 和 `source_page_name`。复制使用当前工程内的无保护源页，按原厂归档保留控件、脚本及原有引用，包括指向源页的引用。原厂保存后读回新窗口 ID、名称和控件数，操作前的活动设计页保持。新窗口可用返回的 ID 和名称打开。

新建前通过原厂名称查询重建内存名称索引，核对现有窗口的 ID、名称、对象和工程状态，再调用新建。回执中的 `native_page_name_index_rebuilt` 和 `native_existing_page_names_verified` 记录这一步。此前版本连续新建自定义名称时曾返回 `native_partial_state`，磁盘已有默认名 `窗口0`，内存目录仍未登记该窗口。遇到部分状态，先读取原生目录和磁盘 `WndUser`，依据已有结果决定后续动作。

## 页面和标量变量改名

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection page-reference-inspect --project $Project --page-id $PageId --page $PageName
& .\run.ps1 native-engineering --family stu --connection $Connection page-rename-referenced --project $Project --spec $PageRename
& .\run.ps1 native-engineering --family stu --connection $Connection data-reference-inspect --project $Project --spec $Variable
& .\run.ps1 native-engineering --family stu --connection $Connection data-rename-referenced --project $Project --spec $VariableRename
```

页面填写 `page_id`、`page`，变量填写原生目录的 `name`、`native_id`、`native_type`。改名再填写 `after` 为新名，`expected_reference` 为原厂读取返回的完整 `before_reference`。用 `registered_incoming_edges` 核实实际登记引用，原厂状态 1 只表示精确路径有引用。入边为空时使用上述规格。有且仅有一条直接 Prog 入边时另填 `expected_consumer`，含策略的 `block_id`、`block_name`、`row_index` 和 `source_sha256_utf16le`。页面支持 `!OpenSubWnd` 直接第一个参数，变量支持脚本直接标识符。回读核对完整双向登记图和脚本正文，保留注释和字符串字面量。其它消费对象、多个消费者、未知引用及运行时动态拼接需要各自确认。

页面通过内部用户窗口工作台操作，并核对原厂窗口 ID、文档和控件目录。现有标量通过内部实时数据库工作台改名，完整核对其余变量和原有 ID、类型、初值、备注及单位。分别核对原厂业务结果、页或数据模块保存、根工程保存和独立文件。软件不会切到 Windows 系统前台。

## 顶层标签和存盘浏览控件改名

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection control-reference-inspect --project $Project --spec $Label
& .\run.ps1 native-engineering --family stu --connection $Connection control-rename-referenced --project $Project --spec $LabelRename
```

规格填写 `page_id`、`page`、`top_level_path`、`control_name` 和标签类型 `native_type_id: 20488`。写入再填写 `after` 和读取回执中的完整 `before_reference`，后者以 `expected_reference` 提交。写入要求顶层静态标签的入边、出边都为空，目标设计页关闭，工程处于已保存状态。回执分别记录页保存、根保存和完整登记图回读。实测版本为 Stu 3.5.3.9198。

顶层存盘浏览控件使用类型 `20531`。写入再提交读取回执的 `registered_graph_sha256` 和完整 `reference_consumers`，规格字段分别为 `expected_graph_sha256` 和 `expected_consumers`。支持已登记的窗口打开事件、按钮松开事件和一个 Prog 消费者，调用为单行无参的 `Home`、`End`、`PageUp`、`PageDown`、`SetTimeDialog` 或 `Refresh`。写入前关闭目标和受影响的设计页及策略页。保存回执列出受影响的页和策略，读回核对所有登记关系及脚本指纹。

## 项目语言和译文

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection language-catalog --project $Project
& .\run.ps1 native-engineering --family stu --connection $Connection language-catalog --project $Project --spec $TextSelector
& .\run.ps1 native-engineering --family stu --connection $Connection language-add --project $Project --spec $Language
& .\run.ps1 native-engineering --family stu --connection $Connection language-text-edit --project $Project --spec $Translation
```

目录返回原厂名称、字体、已配置的语言顺序、当前和预览语言，以及项目文本和下一个可用项目文本 ID。读取指定文本时填写 `text_id`。分页可填写 `offset` 和 `limit`，默认从第 0 条读最多 128 条。添加内置语言填写目录里的 `language_id`、`language_name` 和当前完整的 `expected_configured_language_ids`。

编辑译文时填写项目 `text_id`、已启用的 `language_id`、原值 `before` 和目标 `after`。`before: null` 表示该语言的译文尚不存在。创建项目文本还须使用当前的 `next_project_text_id`。修改会核对语言工作区和原保存版本，保存后读回全部译文、语言定义及当前和预览选择。运行时切换语言及对具体控件的实际显示需各自验收。

## 项目图库

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection picture-catalog --project $Project
& .\run.ps1 native-engineering --family stu --connection $Connection picture-import --project $Project --spec $PictureImport
& .\run.ps1 native-engineering --family stu --connection $Connection picture-copy --project $Project --spec $PictureCopy
& .\run.ps1 native-engineering --family stu --connection $Connection picture-replace --project $Project --spec $PictureReplace
& .\run.ps1 native-engineering --family stu --connection $Connection picture-export --project $Project --spec $PictureExport
```

目录返回项目内的图片顺序、名称、原厂内容指纹、档案格式、缓存长度和仅引用标志。可传 `offset` 和 `limit` 分页。操作规格如下。

| 操作 | 规格字段 |
| --- | --- |
| 导入 | 新 `name`、当前 `expected_count`、绝对本地路径 `source_file`、输入文件的 `source_sha256` |
| 复制 | 新 `name`、当前 `expected_count`、目录中的 `source_name` 和 `source_content_hash` |
| 替换 | 原厂 `name`、当前 `expected_count`、目录中的 `expected_content_hash`、绝对本地路径 `source_file` 和输入文件的 `source_sha256` |
| 导出 | 原厂 `name`、目录中的 `expected_content_hash`、工程同目录内尚不存在的绝对路径 `destination_file` |

支持嵌入式 24 位无压缩 BMP、JPEG、PNG 和静态 SVG。路径扩展名须匹配文件格式。替换保留原图库名称、顺序和原厂对象身份。写入回执核对原厂目录、图库模块与根保存、归档索引和嵌入数据。导出回执附文件 SHA-256，客户端独立读取新文件核对。外部引用图片只读目录。重命名和删除尚没有公开在线图库动作。

## 读取实时数据库与编辑标量属性

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection data-catalog --project $Project
& .\run.ps1 native-engineering --family stu --connection $Connection data-read --project $Project --spec $Variable
& .\run.ps1 native-engineering --family stu --connection $Connection data-edit --project $Project --spec $VariableEdit
```

变量规格使用本次目录返回的 `name`、`native_id` 和 `native_type`。编辑现有标量时再填 `before` 和 `after`，两者包含同样的字段，可选 `comment`、`unit` 和 `initial_text`。初值使用原厂字符串，数值型使用有限十进制，开关型的值为 0 或 1，字符型允许空串。实际写入时激活 Stu 内部实时数据库工作台，集中保存原厂数据模块与根工程，再逐条复核变量名称、ID、类型和可编辑字段。操作结束后恢复原活动页。

## 读取配方与编辑现有单元格

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection recipe-catalog --project $Project
& .\run.ps1 native-engineering --family stu --connection $Connection recipe-read --project $Project --spec $Group
& .\run.ps1 native-engineering --family stu --connection $Connection recipe-cell-edit --project $Project --spec $Cell
```

读取规格填写完整 `group_name`，可加从零开始的 `offset` 与正整数 `limit`。编辑规格填写 `group_name`、从零开始的 `row_index`、`column_index`、字符串 `expected` 与 `after`。列定义的原厂类型决定输入格式，已识别整数、数值与字符列。写入前检查当前内存值和原厂具名归档，根文档和配方模块应处于已保存状态。写入使用原厂单组持久化入口及根保存，回读目标单元格并核对同组其余归档内容。配方属于 Stu 独立对话框，工程写入期间内部显示实时数据库工作台，结束后恢复原活动页。

## 空配方组改名

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection recipe-reference-inspect --project $Project --spec $Group
& .\run.ps1 native-engineering --family stu --connection $Connection recipe-rename-referenced --project $Project --spec $GroupRename
```

读取规格仅填写 `group_name`。写入填写 `group_name`、`after`、`expected_recipe_index`、`expected_reference`、`expected_archive_sha256`、`expected_index_sha256`，其中四个前像字段来自同工程的读取回执。Stu 3.5.3.9198 下须确认配方记录数为零、登记无入边，用户页没有控件、脚本及事件分派，策略没有内容或事件触发器。遇到配方模块有待保存状态时，从原厂执行「保存工程」，再重新读取前像。保存验证活动索引中原名移除、新名保持原位置、配方内容一致。原厂保留的旧具名归档会单独核对。

读取规格可增加 `include_referenced_consumers: true` 检查 DrawRecipe 原厂目录控件的配方组绑定，以及 Prog、页面退出脚本中实际使用组名的直接引号参数。若回执 `referenced_consumers_supported` 为真，写入再提交完整的 `recipe_consumers`，规格字段为 `expected_consumers`。读到动态组名、不能证明归属的引用或其它未知消费者时，查看 `unsupported_recipe_consumer_reasons`。源指纹、命中的参数和实际保存的页面会逐项回读。

带页面退出脚本的配方改名保存新源码并清除该脚本的旧编译缓存。改名回执通过后，按回执的 `saved_page_ids` 对相关页执行一次 `page-native-generate`，再做 `compile`、独立文件回读和关闭重开。原厂根检查可以先得到 0 错误，而该页的新退出缓存需要由单页生成保存。不要重新提交已成功的改名请求。

## 空串口父设备波特率

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection device-serial-config-read --project $Project --spec $SerialParent
& .\run.ps1 native-engineering --family stu --connection $Connection device-serial-config-edit --project $Project --spec $SerialEdit
```

读取规格填写设备的单段 `path`，例如原厂设备工具箱创建的 `["通用父设备_串口0"]`。编辑追加 `native_id`、`field`（`baud_rate`）、`before` 与 `after`。Stu 3.5.3.9198 当前支持唯一原厂串口父设备，已核对的驱动键为 `通用父设备_串口` 和 `通用串口父设备`。要求零子驱动和零绑定，端口 1、8 位数据、1 位停止、无校验，波特率在 9600 与 19200 之间切换。写入前在同一次请求内验证工程已保存、运行原厂检查，并再次核对工程和设备前像。检查结果保留于 `original_check`。保存后回读设备身份及五项配置。操作只调用组态入口。

## 读取和编辑策略源码

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection strategy-catalog --project $Project
& .\run.ps1 native-engineering --family stu --connection $Connection strategy-source-read --project $Project --spec $SourceSelector
& .\run.ps1 native-engineering --family stu --connection $Connection strategy-source-edit --project $Project --spec $SourceEdit
```

用策略目录里的 `block_id` 和 `block_name`，再用 `row_index` 选定实际的原厂 `CStgyFuncProg`。读取返回全文和 UTF-16LE SHA-256。写入规格在同一选择器上加 `expected_source_sha256_utf16le` 及完整 `source`。先激活 Stu 内部策略工作台。如果同一策略已打开独立设计文档，先由该窗口处理现有草稿，避免从保存模型覆盖工作副本。程序内容使用原厂 `TrimRight` 投影，`source_normalization` 和前后摘要可核对保存的精确文字。

分别检查 `native_script_compile_passed`、`native_strategy_compiled`、`native_strategy_saved`、`root_save_verified` 和最终源码回读。写入后 `native_project_compile_required` 为真。回执保留原厂根编译标记的前后读值，整项目的当前有效性以最后一次原厂 `compile` 为准。策略类型、触发设置及其它策略源码保持原值。

## 原厂触发器目录

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection strategy-trigger-catalog --project $Project
& .\run.ps1 native-engineering --family stu --connection $Connection strategy-trigger-read --project $Project --spec $Strategy
```

读取规格填写策略目录中的 `block_id` 和 `block_name`。目录返回启动、退出、自定义、循环及事件触发器的真实策略归属、原始触发器 ID 和注释。库存系统策略可持有相同的原始触发器 ID，按实际策略 ID 区分。循环提供间隔及原始日历字段，事件提供原厂表达式和两个尾字段。未适配的记录在 `unavailable` 保留原因，部分结果退出码为 2。此入口只读取现有触发器。

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

## 读取和编辑页面说明

```powershell
& .\run.ps1 native-engineering --family stu --connection $Connection page-description-read --project $Project --page-id $PageId --page $PageName
& .\run.ps1 native-engineering --family stu --connection $Connection page-description-edit --project $Project --spec $Description
```

从本次原厂 `page_description` 取页面身份和说明前值。规格包含 `page_id`、`page` 和各含 `description` 的 `before`、`after`。允许空字符串和换行，最多 32768 个 UTF-16 代码单元。实际写入前核对当前页面前值和内部活动设计页。刷新及保存后回读目标说明和相邻原厂文字，另用独立文件回读核对窗口归档与数据库说明列。

请求超时时查询原请求 ID 和已提交请求的 SHA。用 `request-result --project <同一工程> --id <原 ID> --request-sha256 <原摘要>` 查询当前队列。旧 Pro 专用包可作为配有 Stu 引擎的小更新基底。接收端按当前 Stu 技能源码核对预测的引擎合同和预编译产物。`--no-download` 时使用本地已有的匹配目录或更新包。
