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

普通图层采用原生新增顺序 `placement: "append"`。需要底板的层显式指定 `placement: "back"`，用原厂调层调用把该层自己的新增对象连续置底，已存在的对象保留相互顺序。当前编译器没有删除和任意重排既有对象的指令。依赖应定义在前面的设计控件上。其中已有对象的路径型修改在新增前执行，依赖新增对象的已有路径型修改需要拆成独立规划。

`bindings` 可显式核对采集到的原绑定，例如 CDrawEdit 的 `input_variable` 或 CDrawButton 的 `button_phases`。新按钮连线、控件事件和任意表达式写入仍使用对应原生编辑合同。原型克隆继承原生绑定，未知 getter 继续显示待验证。计划可带完整 `expected_reference_edges`，并在已有证据支持时显式传递 `native_derived_cache_contract`。同步作为独立阶段运行；缺完整边时不默认运行原厂引用生成。

```powershell
.\run.ps1 native-page-plan compile --design design.json --snapshot before.json --program program.json --review review.json
```

把输出 `program.json` 交给已有 `engineering_session.py stage` 和 `run` 的原生部署入口。按已授权范围一次运行。选择保存时，每个变更页一次 `page-flush`，末尾一次 `root-flush`。纯保留声明没有动作时只输出 review。编译不连接 Pro，不生成审批文件，也不代表当前构建已通过验收。

## 生成 HTML 对照

原生完成后独立再读整页，按需补读 typed properties 与按钮两相动作。使用新回执生成 `after.json`，将 session 留存的原始 `*-rpc-response.json` 与新快照一起提供给报告。

```powershell
.\run.ps1 native-page-plan snapshot --receipts inspect-after.json --out after.json
.\run.ps1 native-page-plan report --review review.json --snapshot after.json --receipts page-plan-rpc-response.json --out review.html
```

新对象身份来自真实新增/克隆回执，引用由本次设计和原生前像命名。报告比较真页尺寸、几何、所有者、层序和已读绑定。没有绑定样本则显示未读到。相同文档实例核完整内存身份；提供本次正常重开证据后按页 ID 和唯一持久原生 ID、类、名称匹配重载对象。重新打开后的多解仍需人工核实。示意图使用实际页坐标，原厂字体、动态状态和截图单独验收。

实际视口可用 `snapshot --viewport observation.json` 补充可靠的测量结果。输入 `schema: "mcgs-page-viewport-evidence/v1"`，`actual_project`、`process_id`、`creation_filetime`，以及 `pages` 数组中的 `page_id`、`document`、`hwnd`、`visible_page_rect` 和 `source`。可附测得的 `zoom`。可见矩形必须是扣除滚动和缩放后的页坐标。没有对应观察时显示未读到；窗口像素宽高不能直接代替页坐标。

报告的可选 `--evidence` 文件分别保存 `save`、`file`、`check`、`reopen`、`simulation` 的实际原始或提取证据。每项含 `actual_project` 和证据来源 `source`，以及具体读值。保存核 `native_save_return_verified`、`root_modified`、`sha256_after`；文件核 `independent_file_readback_verified`、`sha256`；检查核本次 Root85 worker 返回、检查结果和最终 compile flag；重开核 `normal_project_closed_then_reopened_verified` 与 `open_confirmed_same_project`；模拟核 `simulation_executed` 与 `observed_result_verified`。分项显示缺证据。HTML 预览和动作 `ok=true` 无法替代这些验收。
