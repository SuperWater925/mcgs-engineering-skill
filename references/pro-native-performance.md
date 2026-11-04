# Pro 在线执行提速

本轮优化复用已有原生接口和归档合同，不改软件版本准入，不增加permit或逐批审批。保持当前工程、页面、完整路径、类型和owner的正确调用条件；用合并计算和请求代替反复采集同一事实。用户暂停的工程不会因工具更新而恢复。

0102进一步采用[后台准备、UI原生执行、后台回执](pro-native-pipeline.md)，包括实际线程分工、输入冻结、异步日志、采集去重及旧桥兼容范围。下面的批次合同继续适用。

## 默认执行方式

`run`默认direct，并把连续同页、无保存、兼容的独立编辑step合成一次RPC。支持合并原生创建、几何和属性动作；每个原动作仍按原顺序取得当前目标并执行。显式inspect、页面切换、保存、检查、调层、未知kind、不同页面、不同spec元数据和组内依赖都结束当前组。已完成组之外的`$ref`仍按真实回执解析；需要当前组结果的step留到下一RPC。

分组只改变传输和可合并的原生边界，不改变原step的输出索引、实际动作ID、前像或完成记录。原生部分执行、批次末尾刷新失败和超时分别记录；未完成尾部不自动重放。`run --no-merge-steps`保留逐step direct兼容方式。单step既有能力不因分组上限而拒绝。

默认跨step每组最多8个动作，`run --max-merged-actions N`可调整；8MiB输入预算和完整回执容量仍按实际结构处理。这个上限只拆分自动合并组，不拆分或拒绝原有单step。整页前像会随组内动作数累积，不能只按输入spec很小就盲目扩大分组；W2样本8份前像约961KB，不代表任意工程都相同。

同页连续的`control-native-create`可共用一次原生BeforeModify历史记录和一次末尾刷新。每个控件仍调用原构造、defaults、DocAdd、typed setter并逐项核对新对象和非目标对象。无view时回落原逐项路径。显式保存发生在创建批次完成之后；`coalesce_native_creates=false`可用于保留逐对象历史/刷新或做对照。调用方应在创建动作的`after.properties`直接给最终样式，减少后续属性动作。

调层原命令包含原厂内嵌STORE及选择状态变化。本轮保留这些调用，不将调层包装进创建scope，也不声称实现了一次历史记录的通用批量调层。当前公开control-layer仅支持单目标；底层selection数组不代表多选适配已经实现。本轮先共享单次Capture中的树，不放开目标数量。

## 计算和通信

- 动画Capture/Verify每轮只读取一次当前森林，并建立完整对象身份索引。原有raw/owned值和所有非目标动画仍逐项比较，前后两轮Verify不变，不跨mutation缓存live对象。
- 创建后的森林只读取一次，复用于新增对象定位和原有控件保留核对。
- 仅处理页面控件时，不再无条件枚举策略编辑窗口；真正涉及canonical策略时仍即时检查。
- 新Bootstrap的后台worker监听本地命名事件，仅将原生Dispatch投递回原UI线程，再于后台封装并发布回复。文件队列、请求ID和回执关联继续保留。通知不可用时保留轮询回退，兼容旧桥。
- 更新engine和Python客户端本身不会替换已加载的Bootstrap。新通知能力需在后续正常连接时热接新版Bootstrap；不得为更新技能擅自关闭Pro或恢复暂停工程。

已有桥升级时，将新版transport另存为本次runtime内的新文件（例如`bridge_client_0101.py`），用它重新生成engine scope并编译，再按既有file-only选择流程切换新engine。不要把旧scope交给只认新版transport字节的客户端，也不覆盖尚在使用的旧transport。已有Bootstrap可以继续服务同一队列并走轮询回退；启用新事件通知才需要接入新版Bootstrap，不需要每个工程重启Pro。

## 性能记录

新版回执提供`queue_wake_source`、事件/轮询pump计数及`queue_dispatch_elapsed_ms`。客户端submission记录保留各phase的UTC时点。direct各动作记录目标读取、当前摘要/计划、准备执行核对及保存的分阶段毫秒；内层Apply另外区分prepare、目标校验、apply/verify/refresh、flush/save和cleanup总耗时。

这些数值是包络时长：`apply_verify_refresh`不能解释成单独原厂绘图CPU时间，队列调度总时长也不等于某个setter时间。应以同一工程、同一方案的最终集中验收测净收益，不能将算法模拟或隔离ping结果宣称为真实Pro整页提速倍数。

## 本轮验证范围

验证记录见[性能更新记录](pro-native-performance-validation.json)。已做动画索引行为对照、真实客户端runner的假transport集成、独立原生宿主事件/轮询回退，以及完整目录绑定和x86编译。没有为本轮优化连接或修改暂停中的用户工程；新版批量创建和整页净耗时尚未取得原厂实测。此前真实Pro普通启动热接入ping的记录是连接基础验证，不代替本轮新增业务优化验收。
