# JSON工程规格

## 新建

完整可执行示例见`examples/create.json`。create从随包通用空白数据新建数据库，逐项写入真实工程内容，不启动编辑器。

顶层使用 `variables`、`pages`，可选 `edits` 提交初始结构操作。标量变量可使用 `boolean`、`number`、`string`，空数据组使用 type:group。数值初值须为有限数值，布尔初值为0或1；字符串直接填写文本。变量ID由工具按工程顺序分配，不由调用方猜测。

`pages` 每项可声明 `name`、`controls`、`events`、`width`、`height`、`background`、`description`。名称 1～32 字符，页名和同页控件名分别唯一。第一项作为启动页。省略尺寸时沿用模板。编辑窗体尺寸不会改动设备型号和驱动协议。

控件字段：

| type | 可用字段 |
| --- | --- |
| label | name、bounds、text |
| line | name、bounds |
| rectangle | name、bounds |
| numeric-input | name、bounds、binding、minimum、maximum |
| character-input | name、bounds、binding |
| numeric-display / character-display | name、bounds、binding（原生输入框的只读显示模式） |
| button | name、bounds、caption、press_source、release_source |

已接入样式 `fill/border/text_color/font/alignment/unit/decimals`（依控件类别），可见表达式 `visible_when`，以及显式 `clone_from={page_id,path,name,kind,sha256}`。完整合同见[离线工厂](../../../references/offline-factories.md)。普通新增按钮不继承旧动作；显式克隆保留未指定业务。

bounds为`[左,上,右,下]`四整数。右大于左、下大于上；请把控件放在画面尺寸内。水平/垂直线使用至少1像素的外接矩形。binding必须为工程中已有布尔/数值变量名，工具同时写入真实ID与名称；数字类不接受未知变量或字符串绑定，字符类只接已有字符串变量。数值上下限按minimum≤maximum校验。

## 修改

先inspect原工程。修改规格示例：

```json
{
  "source_sha256": "原工程实际SHA256",
  "add_variables": [{"name":"新设定值","type":"number","initial":"10"}],
  "variables": [{"name":"原有变量名","initial":"35","note":"新注释"}],
  "pages": [{
    "id": 1,
    "controls": [{
      "name":"原标题控件名",
      "sha256":"inspect返回的该控件SHA256",
      "edits":{"text":"新标题","bounds":[30,20,700,70]}
    }],
    "add_controls":[{"type":"numeric-input","name":"新增输入","bounds":[250,100,450,150],"binding":"新设定值","minimum":0,"maximum":100}]
  }]
}
```

从实际inspect结果填写ID、名称与SHA，不使用上述示意值。文字支持变长/变短及中文，控件记录长度会自动更新。edits可修改名称和bounds；静态标签和按钮可改文案，数字/字符输入与显示可改对应绑定及样式，数值输入可改上下限。页面 `events` 接原生打开/循环/退出源码，按钮接明确按下/释放源码；已有策略源码可走共享 `strategy-source`，策略和触发器结构另见[策略与配方编辑](offline-program-recipe.md)。已有变量改名、删除和窗口改名按[离线工厂](../../../references/offline-factories.md)的身份和引用条件执行。

原有变量的初值、note、unit可更新；新增变量通过add_variables。修改已有工程时不替换其他页面、设备、权限、策略或未知控件内容；文件级全表回读会检测意外改动。实际不支持的变量布局或控件归档分支报告具体缺口；不按软件发行版本拦截。

edit 顶层 `add_pages` 接 `{id,name,template_page_id,controls,events,width,height,background,description}`。ID 可省略自动分配，模板来自本次工程。新页默认使用空脚本和空的已识别派发列表，保留母页公共窗设置。已有页 `events` 可指定 `open/cycle/close/period_ms`；Pro 已证的窗口 `Click` 也可由 `events` 新增、改源码或删除。 [页面及事件规格](../../../references/offline-factories.md#pro-页面与事件)

## 编写需求时

先建立画面、变量和绑定清单，按实际支持范围生成JSON。对未实现项清楚列出缺口，不写空脚本或假地址，不把可编辑工程误说成已满足全部业务需求。修改前后分别保留摘要；用户原工程不被覆盖。
