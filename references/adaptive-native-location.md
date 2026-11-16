# Pro 自动定位与单项功能隔离

本轮把函数定位证据与真实调用合同分开。离线命令不读取在线ABI资料；在线定位失败不能直接解释为软件版本不支持或要求升级。当前验证见[自动适配验证](adaptive-native-location-validation.json)，前轮记录保持其原有范围。

## 分层定位

具名导出优先按当前导出表确定方法。RTTI 接口和已证明调用方提供唯一角色时，先复用能识别的代码证据；旧实现不同则按当前接口角色绑定，不再要求旧函数体、诊断字符串和完整终端函数相同。参考 RVA 只标识来源，不作为当前地址或候选择优依据。

原字节和受约束等价指令匹配继续帮助定位没有具名身份的方法。同类方法只在当前已读虚表成员中搜索，不先反复扫描整个程序。多个角色指向不同方法时记录具体歧义，不擅自挑一个。

RTTI 按实际类和非虚接口基类身份选择虚表，读取当前 COL/PMD；接口偏移变化不再因旧数字不同而直接拒绝。私有对象字段用独立本机 `object_layout`，不把方法角色识别成功等同于任意布局都相同。归档、设备和派生对象仍按它们实际使用的字段处理。更新说明见[跨机使用与批量执行](portable-online.md)。

## 仅隔离对应功能

根上下文只取得本次必要身份，虚调用只检查实际使用的槽位。未使用的尾槽未定位，不应阻止其它已闭合功能。

多selector只读检查逐项返回前像或未适配原因。`ok=true`只表示该次检查流程完成；必须同时查看`all_requested_features_available`、`partial_inspection`、`unsupported_actions`和各项结果。缺失项没有可用前像，客户端不能拿空对象生成写入请求。

写入程序保留依赖与部分执行语义：某项失败后不自动跳过它继续写后续步骤；保留已完成前缀、失败kind/action/profile/entry。超时先查实际状态，不重放。

| 结果类别 | 处理 |
| --- | --- |
| 定位缺失或候选不唯一 | 记录具体接口与已尝试规则，其它独立功能保留各自结果 |
| 已确认的对象布局或槽位差异 | 只报告使用该合同的功能未适配，不猜新字段偏移 |
| 自有资料混装、scope或文件完整性不一致 | 修复本次部署；不能当成厂商软件版本限制或忽略错误继续调用 |
| 当前进程、工程或对象身份不符 | 重新确认本次目标，不写入错误对象 |

## 查看本次解析报告

绑定目录包含`adaptation.json`及`profiles/attestation.json`。只读报告不接入Pro，可按完整profile或具体entry筛选：

```powershell
pwsh -NoProfile -File '<技能完整路径>\run.ps1' native-abi report `
  --adaptation '<本次bound目录>\abi-resolution\adaptation.json' `
  --attestation '<本次bound目录>\abi-resolution\profiles\attestation.json' `
  --profile 'static/read-tree-guard-profile.json' `
  --include-located --out '<新报告文件>.json'
```

目录以本次绑定输出为准，不复用作者目录或历史session。`located_runtime_unverified`只表示所提供的静态证据已定位；`metadata_only`不是可调用函数。报告不能代替原厂修改、保存、检查和关闭重开，也不能说明全部历史发行版已经实测。
