# Pro 动画列表编辑

在工程会话中，用 `kind=control-animation-list` 读取目标控件。选择器支持 `page_id`、`page_name`、`control_path`、`control_name`、`class`、`complete` 和 `native_id`。可直接将成功的完整检查回执传给 `--capture`。包含多个动画动作时，用 `--capture-action-id` 选择原动作。也可从该动作的检查回执取出含 `page`、`target_control`、`items` 的完整 `before` 对象，写为 `before.json`。

准备动作时，`order.json` 按目标顺序列出动画。索引从零开始，始终指向这次读取的原列表。只在所有希望保留的动画均已列出后提交，省略的原项会被移除。

| 目标 | order.json 示例 |
| --- | --- |
| 交换原有两项的位置 | `[{"keep":1},{"keep":0}]` |
| 在原动画前插入一个独立克隆 | `[{"clone":0},{"keep":0}]` |
| 修改第一项启用状态，同时保留第二项 | `[{"update":0,"native_member_updates":{"enabled_raw_byte":1}},{"keep":1}]` |
| 删除第一项，保留第二项 | `[{"keep":1}]` |
| 移除所有项 | `[]` |

可见度动画支持业务字段。例如 `{"add":"CAniVisible","visibility":{"expression":"Ready","mode":0}}` 新建一项，`{"update":0,"visibility":{"expression":"Alarm"}}` 修改已有表达式，`{"clone":0,"visibility":{"mode":1}}` 创建使用另一模式的副本。模式取 0 或 1。新建时必须给出表达式，默认模式为 0。执行时完整核对工厂结果。

其它新建动画使用 `add` 指定原厂具体类，并提供 `expected_record`。此高级操作需要已验证的原厂构造记录，其中包含该类原厂构造及指定成员更新后的全部预期数据。修改原有记录时，可使用 `enabled_raw_byte`、`strings`、`arrays` 或 `words_uint32`，对应字段须符合该动画类的可编辑布局。

```powershell
pwsh -NoProfile -File run.ps1 native-animation-plan --capture before.json --items order.json --output action.json
```

把输出的单个动作放入工程会话的 `actions` 数组。动作保存了当前控件的 `complete` 身份。重开工程后应重新读取该控件并生成计划。执行器会重新获取前像，并在修改前比较准备计划时读取的完整动画列表。保留项继续使用同一原生对象，克隆项和修改项逐一校验私有副本。原厂序列化若未能保留源动画的全部已知字段，该副本会在提交前被拒绝。

已有编译缓存的 `CAniVisible` 修改表达式或模式时，计划用原厂工厂生成替换项。只把该项的派生表达式缓存交给后续原厂编译重建，原列表以及替换项的全部其余字段仍按实际前像和预期校验。复制该已验证布局的可见度动画也使用同一工厂，源控件上的原项可用 keep 保留。其它缓存字段或其它具体类继续比较完整记录。

动作回执中的 `retained_original_count` 是按原对象身份保留的数量，`constructed_item_count` 包含新增、克隆和替换项，`removed_original_count` 包含被删除和被替换的原对象。工程保存、检查和关闭重开分别查看对应步骤回执。

对已读取的动画，`{"update":0,"fields":{"expression":"温度设定1"}}` 和 `{"clone":0,"fields":{"expression":"温度设定2"}}` 适用于输出、闪烁、垂直移动、大小、画刷及文字颜色。画刷和文字颜色支持 `fields.thresholds` 与 `fields.colors`。输入与当前档位数量一致的数组，阈值按 float32 取整后严格递增，颜色按 24 位 COLORREF 设置并保留各档原高字节。

输入动画可指定 `{"update":1,"fields":{"binding":"数字输入_二进制"}}`。把 `control-animation-list` 和 `data-catalog` 放在同一个原生检查请求中，将完整回执传给 `--capture`。计划记录原变量和目标变量的名称、ID 和标量类型。执行器在写入前重新核对当前工程中的两份变量身份，再成对更新绑定名称和 ID。换绑适用于已验证的空缓存布局，同时保留输入模式、限值及提示文字。

带编译缓存的 CAniOutput 分支先逐字段验证原厂私有克隆的实测结果，再通过已声明可写成员还原四项原值。新对象接入前再次核对整个记录，其中偏移 `14` 的编译缓存已由原厂克隆清空，最终由原厂编译重建。未命中该实测归档形状时停止在对应动画。其它布局仍精确比较私有克隆的全部记录，CAniInput 的附加缓存同样参与比较。

带原厂缓存的 CAniSize 在同一控件、同一动画位置修改表达式时，原厂私有反序列化会保留归档业务字段，并留下两个未序列化的尺寸字段。计划携带当前尺寸值，执行器先在私有对象恢复这两个字段，再核对完整克隆记录，只允许该类的派生表达式缓存为空。表达式应用后再比较完整记录。实机保存只修改原动画的 CString；检查保留尺寸并重建了 35 字节原厂缓存。

已有 `CAniBrush` 与 `CAniTextColor` 的同槽颜色或阈值修改可识别实际私有克隆清空的偏移 `14` 派生缓存。原列表、表达式、启用标志、未选档位及颜色高字节仍参与完整验证。已在同一工程独立回读两条动画，每条仅一个颜色 DWORD 改动。原厂工作函数返回 0，检查和重开各读回两条 31 字节缓存。

已有 `CAniBlink` 可以在同一控件原槽更新表达式、速度、方式和颜色。例如 `{"update":0,"fields":{"expression":"0","speed":"slow","mode":"properties","text_color":1193046,"border_color":6636321,"fill_color":2241348}}`。速度用 `fast`、`normal`、`slow`，方式用 `visibility`、`properties`。颜色保留原高字节。执行器用原厂属主接口初始化基色，完整比对私有副本，再应用指定字段。原厂检查重建表达式缓存。实际原厂新增、同槽改值、文件核对与同实例重开均已验收。

已有 `CAniVMove` 的空缓存布局支持同一控件、同一位置的命名表达式更新。执行器先把当前原件偏移 `40` 的未序列化尺寸复制到私有原厂克隆，再核对完整记录。实测将表达式改为现有数值变量，文件只改该 CString，原偏移、上下限和同一列表的输出动画原样保留。原厂检查与关闭重开通过，两条动画的编译缓存均为 31 字节。
