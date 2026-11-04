# 后台准备、UI原生执行、后台回执

0102将纯数据工作移出Pro原UI线程，保持同一工程的原生修改、原厂保存和原生资源释放由一个UI执行者完成。不是多个线程同时写同一工程，也不要求用户重新批准已授权动作。当前业务工程不会因更新工具而恢复施工。

## 执行链

1. **客户端后台预备。** 同一Python进程中的线程池提前编码、复制和哈希无结果依赖的后续同页组。当前RPC进行时可以预备下一组；遇`$ref`、页面/元数据变化、inspect、保存、检查或不兼容动作即结束预备窗口。不猜原生对象ID、不提前调用原生getter。
2. **桥的后台准备。** 专用MTA工作线程读取队列、保留唯一claim、校验并固定本请求的engine、读取和解析spec/inspection文件。新版engine的`PrepareRequest`只处理managed数据和文件。已提交输入被复制/冻结为本请求数据；文件在准备后的变化不替换该请求内容。
3. **原UI线程批量执行。** `SynchronizationContext.Send`只把`Dispatch`送回首次接入时捕获的UI线程。当前工程、目标、完整路径、类型、owner及写前状态仍即时核对。原生构造、setter、历史、绘制、保存和资源释放均留在UI。并发提交只排队，不形成并发原生写者。
4. **后台完成。** UI返回普通managed回执数据。`FinalizeResponse`在后台等待trace结束、写比较证据、编码并发布完整结果；准备与完成固定使用同一个engine ticket，切换active-engine不改变已开始的请求。
5. **客户端后台派生输出。** 原件接收后，线程池写步骤spec、inspect/apply回执和journal。下一RPC可与这些独立文件写入重叠；最终返回前drain所有任务并报告错误。

`run --prepare-workers N`默认1，0关闭前看；`--io-workers N`默认1，可增加不同派生文件的写入并发。仍默认8动作/兼容组，`--max-merged-actions`可调；原单step不因分组预算被拒绝。资源窗口有界，不为每个控件创建新Python进程。

## 采集与日志

- direct原生创建在单个动作内复用首次权威前像，并在紧邻Apply处做一次完整fresh核对；从约4次CaptureFactory减少为2次。动作结束即清除，不跨原生变更或下一动作缓存live状态。legacy保留原有路线，无view仍回落原逐项创建。
- DrawingCapture在一次读取中共享forest、展开索引和对应节点，完整typed/linker/graph及变更前后核对仍保留。公开`control-layer`仍是单目标，底层selection数组不代表已提供多选调层。
- UI只捕获trace的时点、线程和标量；后台writer编码并写入，完成时统一强制刷盘。排队claim仍是超时/崩溃时的执行依据，trace不是逐原生调用的同步提交凭证。
- 比较失败时，UI捕获原始expected/actual JSON、原UI线程和phase，后台才写证据文件并更新原metadata引用。比较规则、失败结果及实际已执行前缀不改变。
- 请求提交、去重、实际提交spec、RPC原件和最终结果仍持久保存；可重建的派生文件flush/close后不逐份fsync。异常退出后可能需从原件重建派生文件，不能据此重放原生写入。
- 后台trace失败在`runtime_pipeline.trace.complete/error`可见，不把已执行操作宣称未执行；客户端派生输出失败会使整体执行报告不成功。原厂操作是否完成与输出记录是否完整分别报告。

## 兼容与更新

要使用桥端三段调度，需要热接新版Bootstrap并选择重新绑定的新engine；仅替换客户端或旧已加载DLL不会改变现有线程结构。不为工具更新擅自关闭、重开Pro或恢复暂停工程。新transport另存为runtime中的版本化文件，例如`bridge_client_0102.py`，重绑对应scope后按既有file-only选择流程切换。

旧engine没有`PrepareRequest/FinalizeResponse`时仍可调用，UI Dispatch内部原有编码/文件工作不会自动移出。新engine被旧bootstrap调用时也保留同步兼容路径；完整提速需两侧配套。原`$ref`路径、逐step回执、部分执行、超时不重试和原厂保存合同保持。

`queue_prepare_thread_id/queue_dispatch_thread_id/queue_finalize_thread_id/queue_publish_thread_id`标明线程归属；`native_thread_id`始终是原UI线程。后台准备与发布可以复用同一worker，关键是原生段只在UI，其他线程不碰原生工程对象。`runtime_pipeline`另含engine准备、原生、trace和后台文件的计时。

## 实际验证范围

[验证记录](pro-native-pipeline-validation.json)区分三类证据：生产Python客户端的假transport并发测试；实际生产managed helper/回执/证据代码的隔离测试；独立原生宿主以及已运行Pro的纯ping线程测试。真实Pro只验证新桥的队列线程分离，没有加载业务engine执行画面修改。新版整页净耗时、批量创建/保存重开仍未在Pro工程复测，不能把线程或ping结果当作工程验收。
