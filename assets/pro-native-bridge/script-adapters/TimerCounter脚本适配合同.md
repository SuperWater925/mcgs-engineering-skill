# Timer / Counter 脚本适配合同

入口为 `timer_counter_source.emit(action: dict)`，返回 `source / required_bindings / required_timer_ids / source_evidence / semantic_limits`。它只生成字符串，没有文件写入、模块加载、原生调用或宿主访问。根代理将文本放进产品实际支持的原厂 Prog，沿现有 SourceBatch 保存与全工程 Check；不新增 engine kind，不修改 OS 或支持位，也不创建不受当前 Linux 产品支持的旧 Counter/Timer 节点。

输入通用字段为 `class_name`、原 UI 形状的 `fields`、`bindings`、`state_contract`。每个 binding 需真实 `name/native_id/native_type`，写入角色还需实际 `initial_text="0"`。native_type 在这里是工程数据对象类型：1开关、2数值，和脚本 DLL 的3/4/264声明码不是同一编号体系。返回的 required_bindings 必须由根代理再次对照新会话实际目录；生成器不能验证调用方提供的 ID。ID只用于绑定审查，脚本文本始终使用合法变量名。

Counter 支持已闭合的 `event_index=2` 正跳变与3负跳变。原资源 RT_DLGINIT240、对话框646、控件47A的六项依序为：数值报警产生、事件产生、开关正跳变、负跳变、正负跳变、负正跳变。不能把4/5自行理解为任意边沿，更不能把数值报警或事件计数偷换成布尔采样。本机安装脚本库没有已闭合的直接 Counter API；其余事件需要另行明确事件来源合同。

Counter 字段使用 `counter_object/reset_condition/preset_value/current_value/state_variable`。绑定角色还需 `previous`、`initialized`。`counter_object/previous/initialized/state_variable` 类型1；`current_value` 类型2。current/state/previous/initialized 四个写入 ID 必须各异，并与所有输入/复位/预置值变量分离。`state_contract` 必须明确：

- `exclusive_state_variable_ids`：完整四个写入 ID；
- `initial_previous="sample_input"`、`initial_value="0"`；
- `reset_priority="reset_before_edge"`；
- `invocation_contract="each_input_transition_at_most_one_edge_per_invocation"`；
- `count_policy="count_each_selected_edge"` 或 `"saturate_at_preset"`。

计数脚本是明确的边沿算法，不声称逐字节等同旧 Windows 功能块。采样调用之间若发生多次输入变化，算法不能恢复漏掉的事件。计数值也受工程数值对象精度限制。root应将 initialized 等状态配置为运行开始时从0初始化，不能用保留的已就绪状态跳过必要初始化。

Timer 字段使用 `preset_seconds/current_seconds/timing_condition/reset_condition/state_variable`。current_seconds为类型2，state_variable为类型1；额外 `initialized/last_result/preset_cache` 均为类型2，初值0，五个写入 ID 全部独立。initialized 取0未初始化、1已就绪、-1出错锁存；每项初始化/运行/停止 API 的非零状态都锁存错误，不静默重试。动态有限预置值变成非正数时也锁存错误；原 API 的非正数无限计时语义仍在原函数合同中明确，不冒充有限延时。

Timer 还必须给出 `timer_id` 及 `timer_reservation={timer_id,owner,project_sources_sha256,exclusive_for_this_action:true}`。timer_id是全局0—127系统计时器槽位，和变量ID、策略ID、行号毫无对应关系；不得默认占0号或从变量ID猜槽位。根代理需按完整当前源码/调用点核预留。`state_contract` 必须给出完整五个写入 ID，并明确 `interval_seconds`（>=0.1的有限十进制）、`condition_false_policy="pause_and_resume"` 或 `"reset_when_false"`、`output_mode="poll_original_TimerValue"`、`reset_priority="reset_before_run"`。

脚本采用原 `TimerStop/Reset/SetLimit/ChangeInterval/Run/State/Value`；到达有限上限后停止，完成位由完整原值比较生成。Preset变量变化时通过原 SetLimit 更新，并维护独立 preset_cache。未使用阻塞 TimerWaitFor。若需要由原服务自动连接输出，真实语法是 `!TimerSetOutput(计时器号,未加引号的数值变量引用)`：DLL第二参声明264/0x108，正式引用 getter 解析后传入运行时数据ID，再由 RTDB 查类型；不能写成变量ID数字或带引号的变量名。

旧 programme 中 Counter 和 Timer 均把 `Recipe_EditAble` 同时当输入和状态、把业务 `time` 当当前值；本模块保留其准确旧目标供对照，但不复用这些冲突绑定。所有新状态变量都由根代理通过普通原厂数据对象接口创建并拿到真实 ID，之后再生成实际 Prog 计划。当前只有文件与本机工程端 DLL/原厂帮助证据，没有 Linux 目标运行实测，也没有宣称原厂 Check 已通过。
