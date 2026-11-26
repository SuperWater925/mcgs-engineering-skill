# 离线动画列表

Stu 与 Pro 的 `audit` 在 `animation_lists` 中列出窗口、组内路径、控件 SHA 和每项的原序号、类别、表达式、SHA。可见动画还列出模式，画刷和文字颜色动画列出阈值及 COLORREF 数组，闪烁动画列出速度、方式、字符色、边线色和填充色。类或对象映射引用可以读取。未知序列化类在 `unsupported` 中按窗口和路径记录。

`controls` 规格的 `edits.animations` 给出目标列表。每个保留项使用审计结果中的 `index` 和 `sha256`。顺序决定层内执行顺序，省略表示移除，空数组移除全部。可用 `{"new_visible":{"expression":"运行标志","mode":0}}` 给原有可见条件工厂确认的控件增加可见条件（矩形 0x5004、文字 0x5008、输入框 0x5025、插件控件 0x503d）。模式 0 表示表达式非零时可见，1 表示非零时不可见。新增同类可见条件会检查重复。

已有项的 `set` 支持以下字段。

| 类型 | 可修改字段 |
| --- | --- |
| CAniVisible | expression、mode |
| CAniBrush、CAniTextColor | expression、等长 thresholds 和 colors 数组 |
| CAniOutput | expression、off_text、on_text。开关文字保留原 CString 编码，四个输出参数保持原值 |
| CAniVMove | expression、offsets（两个有符号 32 位整数）、values（两个有限 float32）。两个数组可独立修改 |
| CAniBlink | expression、speed、mode、text_color、border_color、fill_color |
| CAniSize | expression |
| CAniInput、CAniClick | 现有项完整保留、移除或调整顺序 |

带类映射引用的列表支持增删、重排。第一次保留该类时按原 schema 写出类声明，其余对象的类编号按最终归档顺序计算。对象别名可以删除或随目标移动，保留别名时须保留并先列出其原目标，别名继续指向同一实例。未重新编号的原扩展标签保留其长度。`{"clone_index":0,"sha256":"原动画摘要","set":{"expression":"新表达式"}}` 从同一控件复制已解析对象，保留该对象的原生字段。复制的是新的对象，其他别名仍绑定原目标。复制别名须直接选择其拥有本体的源项。

`new_animation` 可直接用于空动画列表或插入已有列表。必须填写 `class` 和非空 `expression`。以下组合已有原生归档证据。

| 类别 | 目标控件 | 新项字段 |
| --- | --- | --- |
| CAniBrush | 矩形 0x5004、椭圆 0x5006、文字 0x5008 | 可写等长、非空的 `thresholds` 和 `colors`，默认 0、1 两级 |
| CAniOutput | 文字 0x5008 | 表达式；可选 off_text 和 on_text，默认空文字，原生输出参数 1、0、1、1 |
| CAniBlink | 图元 0x5039 | 表达式；可选速度、方式和三种颜色，默认中速、可见度、黑字黑边白填 |
| CAniSize | 矩形 0x5004 | 表达式；沿用 Stu 和 Pro 原厂样例中相同的缩放参数 |
| CAniVMove | 文字 0x5008 | 必填 `offsets` 两个有符号整数和 `values` 两个有限 float32 |

例：`{"new_animation":{"class":"CAniBrush","expression":"温度","thresholds":[0,45,80],"colors":[65280,65535,255]}}`。

闪烁速度 `speed` 取 `fast`、`normal` 或 `slow`，对应原厂的快、中、慢。方式 `mode` 取 `visibility` 或 `properties`，对应原厂的图元可见度变化或者图元属性变化。颜色使用 24 位 COLORREF。例 `{"set":{"speed":"slow","mode":"properties","fill_color":255}}` 可作为已有动画的修改字段。

普通 `edit` 的 `pages[].controls[].edits.animations` 支持单独编辑椭圆 0x5006、图元 0x5039 和插件控件 0x503d 的原生动画。独立 `controls` 路径支持通过完整路径选取组内图元。

独立文件比较涵盖 Pro 原生输出、画刷和闪烁对象，以及 Stu 工程的 38 个原生画刷对象。多个阈值和颜色由真实记录读出，再从零写出完整原始对象。缩放工厂以相同表达式重建两份原厂示例内相同的 SHA-256。文件层检验不含本轮新增能力的原厂编译。

颜色更改仅写 COLORREF 的低 24 位，保留归档高字节。未知类没有可证的对象边界，整控件拒绝写入。脚本动作、点击缓存及输入限值结构均无字段编辑入口。修改后将控件的动画待编译位置 1，保留同一字的其他位、控件元数据及未修改的动画字节。离线回读与原厂编译、保存重开和模拟分别验收。

2026-11-20 在两份已有工程导出上验证。Pro 读取 120 组动画，Stu 读取 299 组。逐控件在内存移除后回读，在 5 组 Pro 和 110 组 Stu 多项列表上逆序并比对各项 SHA。两份导出各通过一次 audit → controls 候选文件生成和窗口逆向复原检查。原数据库未写入，原厂编译、重开和模拟待验。
