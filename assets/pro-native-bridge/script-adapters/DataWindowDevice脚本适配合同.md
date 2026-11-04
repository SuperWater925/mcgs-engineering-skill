# Data / Window / Device / Beep 源码适配

`generic_action_source.emit(action)` 只返回 `source / required_bindings / required_timer_ids / source_evidence / semantic_limits` 五字段，不访问宿主或运行时。调用者把 `source` 放入产品实际支持的 Prog，并逐 ID 对照当前原生库存核验绑定；不得用生成成功代替原厂编译或运行验收。

- `data-assign`：`target={name,native_id,native_type,writable:true}`；`value={kind:"literal",native_type,text}` 或 `{kind:"data-object",binding:{name,native_id,native_type}}`。仅同类型；原生1为开关、2为数值、3为字符串。字符串走原帮助明确的转义；开关常量仅0/1。组及只读系统对象不能作为左值。
- `window-operation`：`target={object_kind:"window",name,script_expression,page_id}`，`mode` 为1可见打开、2隐藏打开、3关闭、4打印、5刷新；可选 `result` 是实际可写数值变量绑定。`script_expression` 必须由实际对象解析获得，不能由生成器猜前缀或数字 ID。
- `device-operation`：`target={object_kind:"device",name,script_expression,native_serial,path,driver_uid}`；`mode` 为1启动、2停止、3查询、4一次采集、5周期、6驱动命令。模式5必须给正整数 `period_ms`；模式6必须给完整 `command` 与 `driver_command_contract`，不生成猜测命令。1..4的命令固定空串。可选 `result` 可保存0/-1/-2或模式3的状态返回。
- `beep`：仅无参数 `!Beep()`，可选数值 `result`。不接受 WAV 文件、播放参数或旧声效 flags。

所有操作拒绝未知字段/操作；不把 Statistics、WAV 或整策略 Exit 替换成别的功能。绑定中的名字、类型、ID、路径和表达式必须来自当前实际回执；生成器只声明所需绑定，不冒称自行验证调用者提供的字典。输出源码末尾恰有一对 CRLF，后续程序合成器可只移除此尾部，不改正文。required_bindings 中的数据条目沿原接口，窗口/设备条目明确带 object_kind；后者不能当作数据变量 ID 校验。

原声明的 SetWindow 参数码为 `0x105,4`，SetDevice 为 `0x106,3,8`，Beep 无参数；返回码均4。参数码与 CObjData 的1/2/3不是同一枚举。精确安装 DLL 与函数证据见 `generic-action-source-native-declarations.json`；未执行编译、脚本运行、PLC或设备操作。
