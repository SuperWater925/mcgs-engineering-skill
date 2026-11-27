# 现有多状态控件与图片资源的有限编辑

本入口直接编辑安全导出的原生工程归档。它不读取运行包，不转换 VE 运行封套，不反编译脚本，也不新建或替换整个工程。软件版本只记入证据；结构、长度、完整消费和前像决定是否可修改。

实际样本的独立文件回读、原厂检查以及保存重开结果见[本地统一验收](local-validation-20261120.md)。按钮内嵌图片在本轮 Pro 的保存流程中转成图库引用，像素、尺寸及其余按钮内容按实际结果比较。

## 多状态控件

`controls` 的 `edits.state_edits` 支持当前可解析的 `0x5028/0x502a`，沿用现有窗口/path/控件 SHA 守卫和组内路径。下标从零开始。下例修改状态内已有字段。

```json
{
  "state_edits": [
    {
      "state": 1,
      "fill": 4478310,
      "texts": [
        {"child": 0, "text": "待机", "font": {"height": 18, "weight": 600}, "color": 255}
      ],
      "images": [
        {"child": 0, "picture": {"reference": "图片16"}}
      ]
    }
  ]
}
```

`fill` 只改该状态现有填充颜色，保留刷子样式，因此不会把透明填充擅自启用。文字颜色修改子项主 COLORREF，保留辅助颜色与尾部。字体支持 `height/weight/family`，以及布尔字段 `italic/underline/strikeout`。这三个 LOGFONT 字节也可用于编辑既有文字、输入框和标准按钮的 `font`。每个语言项分别更新，按钮同步两份字体。阈值、输入/输出绑定、权限、动画、事件和其它状态均保留；修改后按所列字段逆向还原，必须重获原始字节。

### 状态与子项的增删、重排

`edits.state_layout` 按最终状态顺序给出每行的原始 `source`。重复来源可增加状态，省略来源可删除状态。每行继承来源的阈值、两项填充字段、图像列表和文字列表。`threshold` 覆盖阈值，最终阈值转换为 float32 后须严格递增。`texts` 和 `images` 均可按原索引重排、重复或删除子项。跨状态复用同类子项可写 `{"state":1,"child":0}`，空列表会移除该集合的所有子项。同一操作另列的 `state_edits` 使用变更后的状态和子项索引。

```json
{
  "state_layout": [
    {"source": 1, "threshold": 0, "texts": [0, {"state": 0, "child": 0}]},
    {"source": 0, "threshold": 1},
    {"source": 1, "threshold": 2, "images": []}
  ],
  "state_edits": [{"state": 2, "texts": [{"child": 0, "text": "报警"}]}]
}
```

阈值数量及数值可调整的结构包括两种已识别模式的多态显示器，以及两种动作尾满足实测结构的多态按钮。后者的同一动作尾分别见于 2/5/10 态和 1/2 态的原始记录。动作、读写绑定及条件均按原字节保留。其余动作尾允许在原阈值序列上重排图文。每种格式由实际结构判断。无法绑定到数据的控件不会因增加状态而自动获得业务绑定。

独立文件验证使用六份额外 Pro 工程和一份 Stu 工程的只读导出。两份含非双态按钮的 Pro 工程中，4 和 45 个按钮的新增状态、删除新增状态均恢复完整源字节。Stu 工程的 7 个多态显示器同样完成增减往返。这些结果记录文件层行为。

### 从空白工程或现有工程创建多态控件

`create` 的 `pages[].controls` 和 `edit` 的 `pages[].add_controls` 均接受 `multi-state-button` 与 `multi-state-display`。默认包含 0、1 两个状态。各状态均有文字子项，按钮还带空图片槽。新控件没有原样例的事件、图片引用和变量绑定。两系列各自使用厂商 N 系列样例的图文结构及对应的元数据长度。使用 `clone_from` 时，按页、路径、名称、类别和 SHA 验证源控件，保留它的既有动作和绑定。

```json
{
  "type": "multi-state-button",
  "name": "模式选择",
  "bounds": [20, 30, 180, 85],
  "binding": "当前模式",
  "write_binding": "模式命令",
  "state_layout": [{"source": 0}, {"source": 1}, {"source": 1, "threshold": 2}],
  "state_edits": [{"state": 2, "texts": [{"child": 0, "text": "检修"}]}]
}
```

`binding` 必须解析为本工程已有的布尔或数值变量。按钮的读写字段分别保存名称、ID 和类型。`write_binding` 仅适用于按钮。显示器将变量名写入已验证的表达式槽，保留独立的条件字段。克隆中已有的间接引用、附加绑定字段会报告具体限制。图库引用修改走能检查实际图库的 `controls --export`，创建时可指定嵌入图片。

`audit` 的 `state_layouts` 输出每个多态控件的窗口、组内路径、前像 SHA、阈值、填色、各状态图文数量和阈值结构可写性。两系列空白工程各实建一个三态按钮和一个三态显示器，又分别在已有工程增加一个显示器。四次数据库写入各核对 12 表，独立复读了状态、文字、几何、绑定和非目标控件。原厂保存重开与现场运行需单独验收。

### 标准按钮图片槽

标准按钮使用 `edits.button_pictures`：

```json
{"button_pictures": {"primary": {"reference": "图片8"}, "properties": {"reference": "图片9"}}}
```

原生位图 `CDrawBitmap`（类型 `0x5009`）使用 `{"bitmap_picture":{"reference":"图片9"}}`，可走共享 `controls` 的完整路径或普通 `edit` 的顶层现有控件。具名引用须已登记在当前工程图库中。写入独立像素时，改用 `bitmap_picture.embedded_hex` 并提供完整 BMP、PNG 或 JPEG 文件字节。两种写法均针对选定的图片封套，保留图库和其它引用者、原控件事件、动画及非图片字段。

`primary` 和 `properties` 是原生主归档、属性归档中两个独立图片槽的名称，不能把它们假定为所有布局的按下/释放语义。只替换已序列化的图片槽，不修改启用位、动作、安全条件或脚本。

图片可指定 `reference`（安全导出中唯一存在的图库名称；不是资源 hash identity），或 `embedded_hex`（完整 BMP/PNG/JPEG 文件的十六进制字符串）。嵌入时从真实文件解码读取宽高，再写 mode=2 原生封套及精确字节长度；无需用户手填尺寸。尺寸和 payload 字节数必须能由原生封套的 DWORD 字段表示，并通过已有预览环境中 Pillow 的实际格式检查、尺寸保护及完整解码；内存与解码器限制按实际错误报告。工具不另设 64 MiB、16M 像素或 8K 分辨率门槛，不关闭 Pillow 自身的保护，也不重编码图片。旧 mode=2 中未知 payload 可原样保留，不能当作已支持的图像内部结构。

## 已有图库资源

只读查看现有资源与 VECT 子元件路径/前像：

```powershell
pwsh -NoProfile -File run.ps1 resources --export <安全导出目录> --key MCGS_PICTURE_DATA_19
```

准备资源编辑：

```powershell
pwsh -NoProfile -File run.ps1 resources --export <安全导出目录> --spec <资源修改.json> --out <新候选目录>
```

资源规格：

```json
{
  "input_sha256": "当前工程SHA256",
  "resources": [
    {
      "key": "MCGS_PICTURE_DATA_19",
      "sha256": "解封装后整个资源归档SHA256",
      "edits": {
        "vector_children": [
          {"path": [0], "sha256": "子元件payload的SHA256", "edits": {"fill": 5614216, "border": 2241348}}
        ]
      }
    }
  ]
}
```

现有 kind=16 的 BMP/VECT/CDrawCell 资源支持原生子元件 `bounds/fill/border` 等长编辑。核 BMP 分配、VECT 长度、完整根组与子项边界，保留资源名/身份、资源宽高、原始 BMP 头、未编辑子元件和原分配尾字节。识别 Stu 原厂根元数据及其 12 字节尾后，整体保留根归档。两家原厂样例 162 个现有 VECT 已通过读取，另有真文件正反写入记录。不会重建分配空间，不转换 VE，不把矢量栅格化；结构未知、长度改变或字段超出范围时拒绝。

现有 kind=2 且确认为 BMP/PNG/JPEG 的资源可用 `edits.raster_hex` 替换整张图片。原尺寸必须与封套一致，新尺寸按文件内容更新；图库名称和身份不变，因此会影响所有引用此资源的控件。只想改一个控件时使用该控件的图片槽。VS、其它未知 payload 与非光栅资源禁止隐式转换，未列资源原样保留。

`batch-edit` 可同时包含 `{"command":"controls","spec":"controls.json"}` 与 `{"command":"resources","spec":"resources.json"}`，与策略/配方共用同一工程基线、同一最终清单。相同资源的后续修改必须使用上一批次步骤输出的前像。数据库提交仍经过既有 `apply` 的源 SHA、字段指纹、固定白名单、事务及回读，不绕过任何守卫。

## 结构证据和验证边界

只读盘点的厂商工程中已有 11 个双态按钮，各状态已有图像子项；85 个图库行中有 PNG、VS 以及 3 个原生 VECT，VECT 分别含 1/2/1 个矩形子元件。另一个原厂 N 系列样例含三态文字显示和带文字子项的多态按钮，两类子项均有 72 字节头、字体语言映射、28 字节文字尾部。只读盘点不是编辑后原厂验收。

新增纯回归入口 `python scripts/test_state_resources.py` 覆盖精确状态字段、越界/重复/未知字段拒绝、按钮另一图片槽及脚本保留、BMP/PNG/JPEG 封套、未知 payload 保留、资源身份、VECT 非目标子元件/非零尾字节保留，以及统一批次资源分派。原厂验证结果应另记，不能由这些断言推定。

格式事实参考了独立工具的原生资源封套描述，并在当前工程实际字节中核对；实现使用本仓库既有归档解析器独立编写，没有引入该工具的转换代码、运行包解析器、业务模块或许可证不明的整段代码。
