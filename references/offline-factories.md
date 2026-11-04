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
