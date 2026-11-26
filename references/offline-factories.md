# Stu / Pro 离线控件与页面工厂

本页说明可调用入口及其业务语义。实际验收见[本轮验证](offline-parity-validation.json)。软件版本号不作准入，使用实际工程归档；Stu 与 Pro 使用同一环境。原始工程保持，写入测试或交付副本。

## Pro JSON 控件入口

`run.ps1 create/edit` 均接 `label`、`line`、`rectangle`、`button`、`numeric-input`、`character-input`、`numeric-display`、`character-display`。显示类使用真正原生 0x5025 只读字段，不是文字伪装；按钮为真正 0x5027，支持原生按下/释放源码。

新增使用本包脱敏 Pro 图元默认值，无旧变量、动作或图片引用。按钮默认启用、无安全确认及动作，业务源码默认空。`press_source/release_source` 明确指定原生两阶段，不能将 release 改成 generic Click 绕过既有安全语义。已有按钮编辑只改变请求字段，保留未请求的动作、使能、安全、权限与动画。

普通新增输入和显示控件会关闭两份原生图片门控，并同步移除对应图片描述。新按钮关闭 legacy 与 metadata 图片门控；legacy 描述仍按既有格式保留，不能猜测其门控关闭后就省略字节。这些清理只用于新图元默认值。已有控件编辑与显式克隆保留有效图片，不能为了消除新建模板的残留而清掉原工程资源。

共同必需字段为 `type/name/bounds`，bounds 是 `[左,上,右,下]`。绑定使用当前工程真实变量；数字类接布尔/数值，字符类接字符串，工具同步原生名称/ID/类型并清实际改变的缓存。`caption` 为按钮文案，`text` 保留兼容；样式为适用类别的 `fill/border/text_color/font/alignment/unit/decimals`，字体规格依离线 codec，不是在线 FontValue。单位通过原组件字段写入，不能再叠重复单位。

`visible_when` 只操作已支持的原生可见动画结构；原来其它动画保留，未覆盖的组合报告具体结构缺口，不删动画通过。预览不执行条件、脚本和实际运行值。

显式 `clone_from={page_id,path,name,kind,sha256}` 才继承当前工程模板业务。page_id＋完整组内 path＋名称＋类型＋payload SHA 同时定位，不能只靠控件名。所有未请求字段、源码、条件保持；克隆输入框后若显式转显示模式，只更改明确的只读字段。

最小可执行示例见[创建按钮及绑定示例](../assets/pro-3.5-cli/examples/create-button.json)：

```powershell
pwsh -NoProfile -File .\run.ps1 create --spec .\assets\pro-3.5-cli\examples\create-button.json --output '<新的完整路径.MCP>'
```

该示例只包含自有演示变量与图元，不含驱动、账号、设备地址或用户工程。`create` 仍使用包内 800×480 空白模板；既有工程 `edit` 沿用真实尺寸，不要求该分辨率。

模板保留实际原厂版本记录。目标原厂软件可能提示“自动备份工程后继续打开”；这是原厂转换交互，不是工具版本白名单，也不是要求升级到某发行号。已授权的独立副本按原厂实际备份/转换结果验收，不改写 MCGSVER 假装兼容。若用户不允许 UI 操作且内部接口不能回应该模态，应保留现场并明确未完成，不能把文件回读或连接成功当作原厂已打开。

## Pro 页面与事件

修改既有页使用 `pages:[{id,controls,add_controls,events}]`；顶层 `source_sha256` 和既有控件 `sha256` 按 inspect 当前回读填写。`events` 接 `open/cycle/close/period_ms`，未指定项保留原值与缓存，实际更改项仅清对应缓存。

新增页使用 `add_pages:[{id,name,template_page_id,controls,events}]`。id 可省略，由现有 ID 后分配；源模板须来自当前工程，新名/号不能重复。保留模板原尺寸、背景、公共窗口关系、未知设置及额外数据库字段，控件使用明确的新列表；页面事件默认空，不继承旧业务源码。若要继承原控件和事件，使用共享工具明确 `clone_window`。不暗改启动页面、变量、权限、配方或其它表。

## Stu JSON 创建与编辑

在输出中指定 `.mcs`，可直接用 `create --spec <创建.json> --output <新工程.mcs>`。规格使用 `variables` 与 `pages`，同一命令输出 `.mcp` 时使用 Pro 空白模板。Stu 空白模板由原厂新建工程提取，包含默认表结构、系统变量与权限结构。创建工程时按原厂自增列、主键和索引重建数据库，再回读全表。

以同家族原生模板新建副本时使用 `create --template <原厂或用户模板.mcs> --spec <修改.json> --output <新工程.mcs>`。修改已有工程使用 `edit --source <现有工程.mcs>`。两者共用 `source_sha256`、`add_variables`、`variables`、`pages`、`add_pages` 字段。已知布局允许布尔、数值、字符三个标量类型，以及上述八类基础图元。已有模板对象、默认主页、权限和其它表按当前工程数据保留。

新增图元优先使用当前 Stu 的同类中性原型，绑定接当前工程实际对象 ID。明确要求继承原有业务时给出完整 `clone_from` 选择器。模板和导出仅为来源证据，不以软件版本号选适配。

Stu 与 Pro 的 `create/edit` 均可用 `history-curve` 或 `saved-data-browser` 新增原生默认控件。填写 `type`、`name` 和 `bounds`，名称同步写入外层和内部字段。历史曲线含 16 条未绑定迹线，存盘浏览含 8 个默认列和空数据源；存盘浏览外框的宽和高均须大于 28 像素，原厂默认内表格从右、下各留 28 像素。新增控件使用各自产品的已验证归档，无须工程内已有同类控件。

## 共享工具与事务

Stu/Pro 共用 `Export`、`Templates.pick`、`Page`、样式编辑、`new_window/clone_window`、`Candidate`、离线预览及文字容纳检查。Pro 的对象名称、ID、类型来自 Pro 实际 ObjData 适配；不能套 Stu 对象结构。窗口/策略按明文或 MCGSZIPE 读取，更新保持原包装与未知字节。

`Page.button` 普通新增 Pro 按钮使用空动作图元；`Page.clone_button` 明确继承模板业务。`Page.value/string` 使用真实绑定、原组件单位和只读属性。`new_window` 的事件参数为 None 时沿用模板事件；要空事件应显式给空文本；`clone_window` 继承原控件和事件，不假称全新空页。

Candidate 只有更新时走 `apply`；含新页时走统一入口：

```powershell
pwsh -NoProfile -File .\run.ps1 new-window `
  -Project '<本次快照.MCP>' -Manifest '<实际候选manifest.json>' `
  -ManifestSha256 '<该清单的实际SHA256>' -Out '<新工程.MCP>' -Report '<新报告.json>'
# 已授权提交时增加 -Commit；需要实际新导出时再加 -ExportAfter '<新目录>'。
```

默认只预检。原中文参数保持兼容；只新增 WndUser，已有行只允许既有 BLOB 白名单。标准六列由新页指定，额外字段必须与显式 template_key 对应源行精确相同。事务内及提交后核所有表/行/字段，源码/策略双容器和原工程保持；不提供任意 SQL 或通用表增删。

预览和字宽是离线辅助，不是原厂截图或运行验收；未知/不支持图元单列，保留其内容，不把跳过算通过。策略、配方、已有控件批量修改此前已共用，沿用共享命令，不重复造一套 Pro 工具。

## 本轮校正与验证边界

集中原厂检查暴露了新建输入图元残留图片引用、按钮空图门控仍开启的问题，已按上述新建规则修复。定点文件回归覆盖八类 JSON 新建、按钮克隆与 `Page.button`；真实有效图片按钮及输入框的克隆均保持 payload 字节一致。此前七份主语料及二十二种家族/样式组合的结果保留，没有为图片修复重复全部测试。

本轮另修复部署 binder：绑定后的 `DirectDocument` 与 `LoadDirectPlan` 内部请求均写入当前 delivery scope，原 Plan 的文档/请求比较保持。未绑定的 C# 模板及 ABI 资料清单保持原样；实际绑定产物的两处 DTO 已通过十三项隔离断言。这些断言不调用原厂保存或检查，原厂检查、保存、关闭重开、业务回读及本机模拟仍以[本轮验证](offline-parity-validation.json)的各项真实结果为准。

原厂单位 getter 的替换字符、厂家转换后的字体索引未配置与未知 DWORD 变化分别记录为观察限制，不推断未知字段含义，也不修改版本字段来绕过转换提示。

## 既有页、控件和变量的结构编辑

`run.ps1 edit --source <原工程> --spec <结构编辑.json> --output <新的同类型工程>` 支持 Stu 和 Pro。页重命名使用当前 ID 和原名；启动页改名会同步 MainCtrl 中配对的名称和 ID。删除页或标量变量也需要当前 ID 和名称。已被其它对象引用时，先调整引用；当前启动页需先改选启动页。

下面是顶层规格片段。工程 SHA、ID 和名称均需取自待编辑的实际文件。

```json
{
  "source_sha256": "<当前整个工程文件的 SHA-256>",
  "rename_pages": [{"source": {"id": 1, "name": "运行总览"}, "name": "生产总览"}],
  "delete_pages": [{"id": 7, "name": "备用空页"}],
  "delete_variables": [{"id": 103, "name": "UnusedScalar"}]
}
```

同一页内，`remove_controls` 逐项核对原始零基索引、数字类型、名称和控件正文 SHA；`control_order` 列出删除后全部存留对象的**原始索引**。例如有三个顶层控件，删除中间对象后用 `[2,0]` 将原第三项放在第一项前。随后 `add_controls[].insert_at` 使用此时的零基位置，省略表示追加。该入口操作顶层同级控件。完整取证和执行示例见[离线结构事务](database-and-transactions.md#结构编辑示例)。

### 创建与结构变更规格

Stu 和 Pro 均支持 `create --template`。模板派生使用 `edit` 的规格和原文件 `source_sha256`，输出扩展名须与读出的工程家族相符。空白新建时，顶层 `variables`、`pages` 先建立工程，可选的 `edits` 对象接收同一套结构编辑字段，省略 `source_sha256`。两步完成后一起写出并回读。

- 新建页、已有页和从模板追加页都接受 `width`、`height` 像素值，可独立设置其中一项。使用当前原生属性字段宽度。
- 已有输入框的 `binding` 必须解析到工程变量。可选 `binding_id`、`binding_type` 须与查到的身份相符。已有控件改名会检查本页脚本、控件和工程内使用原完整名的位置；出现引用时返回所在页或表。
- `retarget_main_pages` 接收 `[{"source":{"id":1,"name":"旧主页"},"target":{"id":2,"name":"新主页"}}]`，替换 MainCtrl 两份已解析列表中匹配的名称和 ID，先于页改名和删除执行。跨页脚本、辅助窗口等其余引用仍按各自原生字段处理。
- `main_page_lists` 可独立设置 MainCtrl 的 `startup` 启动列表或 `memory` 内存列表。每个列表给出完整、有序的 `before` 和 `after`；每项为 `{"id":2,"name":"首页"}`。用 `python assets/pro-3.5-cli/scripts/mcgs_file.py inspect <原工程>` 读取当前 `main_page_lists`。同页可同时登记在两个角色中，各列表内 ID 唯一。
- 例如 `"main_page_lists":{"memory":{"before":[{"id":7,"name":"备用空页"}],"after":[]}}` 移除内存列表中的登记。列表设置在新增页之后、改选和删除之前执行，同一规格可以先移除登记再删除页。更换现有的最后一项启动登记时，给出至少一个合法接替页。归档前后文、未改列表和已有登记的原编码保持不变。至少一个当前登记须能核对实际页身份。
- `pages[].groups[]` 的 `path` 是从顶层逐级进入原生组的身份数组，每级包含当前 `index`、`type_id`、`name`、`sha256`。在该组的直接子项上使用 `remove_controls`、`control_order`、`add_controls`，索引与顶层规则相同。每个组操作读取上一个操作完成后的组归档。删除组时也检查后代名称的使用位置。
- `rename_variables` 接收 `[{"source":{"id":103,"name":"UnusedScalar"},"name":"NewScalar"}]`。仅适用于通过引用核对的用户标量。工程内出现使用者、关联设备、报警或组成员时先处理关联。
- 已有原生输入/显示控件直接绑定该标量时，可在对应改名项加入 `"update_input_bindings":true`。按绑定名称、变量 ID 和类型匹配现有控件，保留 ID 和类型，被改控件的表达式缓存由原厂重新编译。同一事务写出变量表及被改窗口。脚本、条件表达式、设备、报警或其它未识别使用者仍须另行处理。

### 数据组新建和成员顺序

Stu 和 Pro 可在 `add_variables` 中加入 `{"name":"新数据组","type":"group"}`，从空白创建时同一项放入 `variables`。两者分别使用自家原厂保存的默认空组记录创建原生 ID，说明、单位、成员及附带配置采用原厂默认值。Pro 用户组名的原厂上限为 64 个 UTF-8 字节。

用 `inspect <原工程>` 读取 `data_groups`。每组给出当前 ID、名称及能解析的有序 `members`。在写入规格的 `data_group_orders` 中填入其中 `order_editable: true` 的组 ID、组名、完整 `before` 和重排后的 `after`。例如 `"data_group_orders":[{"id":16,"name":"示例组","before":[{"id":10,"name":"温度"},{"id":11,"name":"流量"}],"after":[{"id":11,"name":"流量"},{"id":10,"name":"温度"}]}]`。

`after` 保留原成员 ID 和名称，各出现一次。工具在原生 `ObjData` 中移动已有 CString 成员片段，保留其它归档字节。组的报警标志或辅助向量非空时，仍可读取已解析成员，重排待核实对应原生布局。编译产生的缓存由原厂生成。

用 `data_group_members` 增删一组的成员，填写该组 ID、名称、完整 `before` 和完整 `after`。例如 `"data_group_members":{"id":216,"name":"独立数据组","before":[],"after":[{"id":113,"name":"depth1"}]}`。成员使用工程内已有用户标量的 ID 和名称，每个只出现一次。入口核对原厂默认的组存盘及辅助字段，并检查该组的现有引用。即使工程内当前所有组都为空，也可按各家原厂读取逻辑和真实当次字段定位首个 CString 成员。Stu 的归档头大于 12.5、Pro 大于或等于 float32 的 12.1 时原厂用此成员格式。组 ID、未编辑的对象、原厂派生缓存和其它数据库表保持原状。

Pro 实测 `00005041` ObjData 布局中的首个且唯一的默认空组也可写入成员。离线写入和清除分别与原厂的有成员、空组归档逐字节一致。该分支取实际文件结构、空组形状和已确认的范围。其它未实证的空组布局仍采用当前项目能识别的成员格式。

用 `"delete_data_groups":[{"id":216,"name":"独立数据组"}]` 删除已存在的默认空组。按当前 ID、名称、完整空归档和已有引用校验。其它组、变量、ID 及其归档保持。删除与同一组的创建、重排及成员编辑使用不同事务。

### 已有报警的分组、优先级、启用、设定和文字引用

使用 `python assets/pro-3.5-cli/scripts/mcgs_file.py inspect <原工程>` 读取 `alarm_definitions`。从 `editable: true` 的结果取 `variable`、`index` 和完整条目的 `sha256`。例如 `"alarm_edits":[{"variable":{"id":115,"name":"speedon3"},"index":0,"sha256":"<当前条目 SHA-256>","group":17,"priority":43}]`。每项可单独设置 `group`（0–255）或 `priority`（0–100）。

`enabled` 对应原厂报警详情中的“立即启用”。查询可读取当前布尔状态，编辑同一条目时用 `"enabled":true` 或 `"enabled":false` 修改。该字段只更新选中的配置项，保留报警种类、参数、消息和其它条目。

浮点变量的已有上限报警若显示 `upper_limit_value_editable: true`，可设置 `upper_limit_value`。已有开关相等报警若显示 `switch_equals_value_editable: true`，可用 `switch_equals_value` 写原生 0 或 1。两种操作均使用已核实的默认参数源字和原生浮点宽度，从新副本核对实际存值。未指定的报警消息、启用状态、优先级及其它条件保持原值。

`message_text_id_editable: true` 表示该报警的当前 `message_text_id` 能唯一对应现有多语言表。报告中 `message_translations` 按语言 ID 展示现有翻译。可用 `message_text_id` 将该报警改指向另一个实际存在且有翻译的文本 ID。该操作只写入当前报警的原生字符串引用。现有多语言表、使用原文字的其它控件和报警保持原状。

Stu、Pro 各自按实际 `ObjData` 报警条目边界解析。现有原厂样例把这些定义存为 `ObjData`，数据库 `Alarm` 表为空；遇到非空表或边界不明的工程，入口报告该布局待验证。用普通 `edit` 提交副本与完整回读。


### 原生组合、背景和外部构件

- 页面新建、追加和编辑均可设置 `background`。它接受原生 COLORREF 整数，例如纯红为 255。宽度、高度和底色按当前页的原生字段独立写入。
- 页面新建、追加和编辑均可指定 `description`。例如 `{"id":4,"description":"维护说明"}` 可更新已有页，空字符串可清空说明。工具同步页面原生说明及 `WndUser` 的说明列。仅修改说明时保留编译标记、控件和窗口事件。编辑已有页未指定此字段时保留原来的两份说明。新页未指定说明时，采用当前模板的原生说明，并同步到新页数据库列。查看工程时可通过 `description` 和 `description_mirror_matches` 核对。
- 窗口查询的 `common_page` 显示当前宿主引用的公共窗口 ID 和名称，`null` 表示原厂空值。对两种已证事件扩展，删页前逐页核对保存的引用编号。被引用页会指出宿主，无法识别的归档会说明对应窗口。公共窗口是原厂窗口属性中的模板引用。[McgsPro 厂商教程第 2.4 节](https://uploadfile.gongkong.com/Upload/gongkong/BBSFile/202303/08/b9995e19c6a2495183f1ba9643ad8401.pdf)
- 编辑已有页的 `common_page` 默认操作第一公共窗口。示例为 `{"id":4,"common_page":{"owner_name":"状态监控","source":{"id":3,"name":"Title"},"target":{"id":21,"name":"公共窗口"}}}`。宿主、来源和目标需要与当前工程身份一致。用 `source:null` 从空槽开始，用 `target:null` 清除当前槽。改选前沿目标页的所有已识别引用槽核查循环，保留其余槽和 MainCtrl 启动、内存页列表。目标必须是本工程现有的窗口。
- Stu 窗口的 `inspect` 结果含 `common_page_layers` 时，可在 `common_page` 内指定 `"layer":"bottom"`、`"middle"` 或 `"top"`，分别操作原厂底层、中层、顶层窗口。用对应层的当前 ID 和名称作为 `source`。例如 `{"id":4,"common_page":{"owner_name":"状态监控","layer":"middle","source":null,"target":{"id":21,"name":"公共窗口"}}}`。显式选层时，同一宿主的其他层占用该目标会阻止改选。只有一个已识别槽的归档及 Pro 继续使用默认入口。
- Stu 和 Pro 的 `controls` 或 `add_controls` 接受 `{"type":"group","name":"组件","bounds":[10,20,210,120],"children":[{"type":"rectangle","name":"边框","bounds":[0,0,10000,10000]}]}`。子项坐标相对于组，10000 对应组宽或组高。子项可以递归包含组。Stu 使用 G 系列样例中的原生 CDrawUnit 壳，保留该布局的组尾。Pro 使用独立的 Pro 样本壳。
- 编辑页的 `group_operations` 数组按序执行。组合项为 `{"action":"group","name":"组件","members":[…]}`，拆组项为 `{"action":"ungroup","member":…}`。每个身份包含当前层的 `index`、`type_id`、`name`、`sha256`。组合按照原始层序选择至少两个连续顶层对象。支持直线、矩形、文字、输入显示、标准按钮及组的公共边界。组合时保留可反算的页面坐标。拆组按页面像素舍入，并检查组壳是否与对应家族中性壳一致。动态坐标、外部链接、不支持的几何类、存在名称引用或会丢失的组属性均会报告具体错误。
- 同页跨组移动用 `{"action":"move","source":[…],"destination":[…],"insert_at":0}`。`source` 是从顶层到原控件的完整身份链，`destination` 是从顶层到目标组的身份链，空目标链代表页面顶层。`insert_at` 是目标层插入位置，从 0 开始。各层使用同样的四字段身份；厂商文件工厂的 `mcgs_file.py inspect <工程路径>` 在可解析组项下提供 `children`，其中 `kind` 转为整数后用作 `type_id`。移动按组的原生坐标换算，保持共同容器中的矩形。未知动态坐标、目标重名和改动所涉引用会指出具体阻塞。
- 已有 `recipe-table`、`xy-curve`、`alarm-table` 可以使用同一工程的 `clone_from` 新增，按完整构件路径、核心结构及原控件指纹核对。需要显式提供新名称和边界。配方表还支持正整数 `row_height` 和按唯一列标题指定的 `column_widths`。同样的字段可用于修改已有实例。模板业务关联会随复制保留。已用三种真实 Pro 归档核对构件正文；运行和原厂检查待验。

- 在已识别的报警浏览表（原生核心 `0x55b1b`、`0x55b36`）上，`row_height` 是正整数像素；`alarm_colors` 可指定 `title_background`、`title_text`、`grid_color`、`odd_background`、`even_background`、`focus_background`、`focus_text`、`focus_border` 及已解析的报警状态文字和分类底色。数值均使用 COLORREF，仅写入列出的角色。例如 `{"row_height":36,"alarm_colors":{"title_background":16777215,"grid_color":8421504}}`。筛选条件、来源和列定义保留原归档。
- Stu、Pro 的存盘浏览可一起提交 `row_height` 和 `saved_data_colors`。支持表头底色 `header_fill`、表头文字 `header_text`、奇偶行底色 `odd_row_fill` / `even_row_fill`、正文文字 `body_text`、网格 `grid`、焦点行/单元格底色 `focus_row_fill` / `focus_cell_fill` 及焦点文字 `focus_text`。按当前控件指纹提交已读到的角色，COLORREF 仅写低三字节。列、绑定、查询字段和颜色高字节保持。
- `saved_data_fonts` 接收 `header_font` 和 `body_font`。例如 `{"saved_data_fonts":{"header_font":{"height":22,"weight":600},"body_font":{"height":18}}}`。每个角色按原生字体合同接收 `height`、`weight`、`family`、`italic`、`underline`、`strikeout`。只更新选择的属性并应用到该角色的已存语言行，保留语言 ID、字体标志和其余属性。`inspect` 返回两种字体的语言行。可与列、行高和颜色一起提交。
- 存盘浏览的 `saved_data_columns` 可加入同一次控件编辑。按 `inspect` 返回的现有索引提交 `[{"index":0,"width":86,"title":"压力","alignment":"center","unit":"kPa","display_format":"3|2"}]`。宽度为正整数像素，对齐可用 `left`、`center`、`right`。按 `title_editable`、`unit_editable` 区分字面文本和多语言引用。格式 `3|2` 是三位小数和两个尾部空格，`-1|0` 是自然小数位数，`开|关` 是开关显示。绑定和未指定字段按原归档保留。
- 列的 `data_name` 选择当前源声明的字段，`output_variable` 选择当前工程中的普通标量。用空字符串清除输出；已保存的其它列绑定保持。原厂设计检查重新生成修改列的输出索引。
- `inspect` 的 `saved_data_source` 列出当前来源类别及工程中保存的名字，`saved_data_fields` 按原厂顺序提供可选列的数据字段和原生类型。`{"saved_data_source":{"kind":"group","group":"AlternateBatchGroup"}}` 可在现有存盘组之间选择字段名称和类型相同的组，保存当前列配置。
- `{"saved_data_source":{"kind":"alarm_history"}}` 选择系统报警历史 `MCGS_ALARM`，`operation_log` 选择系统操作日志 `MCGS_OPERATION_LOG`。两款软件使用各自原厂数据源字段、类型及时间列。已有的序号字段语言保持，空白控件默认 `MCGS序号`，可显式给 `index_field:"MCGSIndexID"` 写入原厂英文序号字段。切换来源时，旧列继续使用新来源中同名同类型的字段。其余已绑定列用同一次 `saved_data_columns` 的对应 `index` 和 `data_name` 指定目标字段。列数、标题、格式、输出变量与显示样式仍可独立编辑。系统来源切回任意存盘组涉及按原厂重建组字段顺序，当前合同仍限定已验证的存盘组选择方式。
- 存盘浏览的 `saved_data_time_parts` 对应原厂显示属性中的年、月、日、时、分、秒和毫秒。Stu 与 Pro 均可提交部分勾选状态，例如 `{"saved_data_time_parts":{"year":false,"millisecond":true}}`，并可与列、行高、颜色或字体合批。`inspect` 中的 `null` 表示当前归档使用了未识别的复选框状态，仍可独立修改其余字段。
- 存盘浏览的 `saved_data_time_filter` 对应原厂时间条件。排序可用 `ascending` 或 `descending`，可切换 `all`、`recent`、`fixed`、`variables`。例如 `{"saved_data_time_filter":{"order":"descending","mode":"fixed","fixed_period":"this_week","fixed_split_point":3}}`。最近时间以分钟计。固定时间的分割点按原厂选项分别使用 0 到 23 时、1 到 7 日或 1 到 31 日，可独立保存未启用的时间配置。变量方式用 `start_variable` 和 `end_variable` 选择当前工程中已有的字符变量，运行时使用原厂日期时间格式。原有绑定可从 `inspect` 读取，未请求的绑定表达式保留。
- Stu 和 Pro 原生历史曲线的 `history_curve_pens` 由 `mcgs_file.py inspect <工程路径>` 列出。用当前控件指纹提交专用编辑，例如 `"edits":{"history_curve_pens":[{"trace_index":0,"style":6,"width":3,"color":16711680}]}`。迹线索引从 0 开始，三个视觉字段可分别填写。原厂选择器的 `style` 值 1 至 4 对应虚线、点线、点划线、双点划线，配线宽 1，值 6 对应实线，配线宽 1 至 6。颜色用整数 COLORREF，只更新低三字节。保留线宽记录中的 Y 字、数据源、范围和未选迹线。旧 `history_curve_colors` 仍仅接受 `trace_index` 和 `color`。两个入口都支持顶层页面 `edit` 和按完整控件路径的共享 `controls` 事务。
- Stu 和 Pro 原生存盘浏览控件（`0x5033`）也通过 `inspect` 列出 `row_height`。用当前控件指纹，在顶层页面 `edit` 或共享 `controls` 提交 `"edits":{"row_height":42}`。单位是像素，可用正整数。保留已选存盘字段、各列配置、源和条件。
- 现有页通过 `events` 单独更新 `open`、`cycle`、`close` 脚本或 `period_ms`（1 至 2147483647 毫秒）。只有源码改变的事件清空其编译缓存；单改周期保留三个缓存。新页以独立空事件初始化。
