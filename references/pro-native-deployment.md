# Pro 内部工程入口的目录绑定与部署

原生模块是内部 ABI 适配，随包提供自有源码、静态接口资料、Python 客户端和首次桥接部署工具。不含厂商 DLL、用户工程、图片、历史许可、私有账户或密码；离线空白工厂模板保留原厂默认权限结构，密码字段空。Stu 仍用共同的离线入口。发行版本不作白名单；实际安装的模块 SHA、代码/重定位、RTTI、结构、归档和产品能力守卫必须匹配。

## 实际能力与选择

inspection 的 `compiled_kinds` 是本次编译入口清单，`action_preimages` 给出所选目标完整前像和 ABI SHA；编译存在不等于当前工程/产品一定允许。对应 kind 的实现源位于 `delivery/source/sources`，字段合同以当前 Read/Prepare 校验为准，不用历史例子补默认参数。

当前界面施工补充了 `control-geometry-batch` 与标准按钮的显式 paired visual 预期；各页最多64个不同目标、组/组件选择、Flow包络、单位拆分和最终回读规则集中在[在线界面施工](pro-native-ui-workflow.md)。它们复用当前工程和原生接口，不建立第二套版本环境。

| 功能 | 选择与实际合同 |
| --- | --- |
| 页面/标准与复合控件 | 当前 page ID、完整 control path/name/type、原生 owner；创建/复制/组/层/几何/属性/动画/事件和集合保留非目标旁项 |
| 策略 | 当前 block ID/name、canonical/working 模型及真实行索引；完整源码、条件/动作/触发/上下文、创建/复制/删除及 pure-sync/close；先核产品能力 |
| 数据/组/数组/报警/配方 | 当前对象 ID/name/type、完整组及消费者；合法类型转换、嵌套/数组、原生 owned 报警列表、完整配方列/矩阵及具名回读 |
| 设备 | 完整 root→child path/name/UID/owner；安装目录原厂 Add、树 CRUD、保留子树属性发现/修改、引用感知改名；H5U/McgsIoT/monidevdrv 分别按各自闭合合同 |
| 图库/语言 | 当前完整 resource/language catalog、精确 carrier path；导入/导出/创建/复制/删除/重定向及完整目标外保护；独立图库 named 位按原 STORE 展开 |
| 引用与工程服务 | 全量真实消费者及 module/page/strategy 保存参与者；原厂引用编译同步、分阶段保存、Root85检查、专用正常Close/Open |

`device-catalog`、`data-catalog`、`recipe-catalog`、`picture-catalog`、`language-catalog`、`reference-graph` 等通过 inspection selectors 取得当前内容；驱动 property catalog 的原厂 Get 则是私有clone动作，不能把它混作完全无副作用的普通读取。未知派生控件/驱动、未闭合属性或产品不支持的动作精确拒绝；没有 PLC 运行或下载命令。

## 已有桥的同任务更新

先核清实际 TaskRoot、RuntimeRoot、BootstrapRoot、InstallRoot。原队列留在 RuntimeRoot，工程结果与 claim 在 RuntimeRoot\engineering。当前请求使用新ID关联结果；不覆盖已加载DLL，不自动重发尚未明确结果的超时操作。每个工程请求给出目标工程；默认direct会在原生调用内取得当前PID、线程、对象和必要前像。

下面 `$Native` 为本技能的 `assets\pro-native-bridge`，路径和 SHA 来自本次绑定结果。已有桥复用原 RuntimeRoot、传输文件及原队列；无桥则先按热接或明确选择的冷启动 prepare 生成本次目录，再创建 EngineeringRoot 和 runtime\engineering。两种 prepare 的新目录前提以各自工具为准，不能拿冷启动的目录规则强制重建已有桥。TransportClientFile 可将包内 `transport\bridge_client.py` 原字节复制到本次 RuntimeRoot。

```powershell
$Layout = Join-Path $Native 'delivery\device-entry-v2\NativeEngineeringDeliveryLayout.cs'
$LayoutSha = (Get-FileHash -LiteralPath $Layout -Algorithm SHA256).Hash.ToLowerInvariant()
python "$Native\delivery\device-entry-v2\prepare_delivery_binding.py" `
  --task-root $TaskRoot --engineering-root $EngineeringRoot --runtime-root $RuntimeRoot `
  --install-root $InstallRoot --transport-client-file $TransportClientFile `
  --engine-file-name $NewEngineFileName --layout-source $Layout --layout-source-sha256 $LayoutSha `
  --output-directory $NewLayoutDirectory

python "$Native\delivery\bind_common_delivery.v5.py" `
  --source-stage "$Native\delivery\source" --scope-json $NewScopeJson `
  --bound-layout-source "$NewLayoutDirectory\NativeEngineeringDeliveryLayout.cs" `
  --output-directory $NewBoundDirectory --engine-file-name $NewEngineFileName

& "$NewBoundDirectory\build-bound-source.ps1" -Csc $DotNetFrameworkX86Csc

# 默认只列出精确新文件计划；--commit 才复制自有资料，每个目标均须不存在。
python "$Native\delivery\promote_delivery_payload.py" `
  --bound-manifest "$NewBoundDirectory\bound-source-manifest.json" `
  --bound-manifest-sha256 $BoundManifestSha --scope-json "$NewBoundDirectory\$NewEngineScopeFileName" --scope-sha256 $ScopeSha `
  --record "$NewBoundDirectory\payload-promotion.json" --commit
```

七个配置键为 schema、task_root、engineering_root、runtime_root、install_root、transport_client_file、transport_client_sha256。所有根目录显式给出，工程不放进配置。EngineeringRoot 保存只读 profiles 和独立的 task-evidence 资料镜像；绑定工具仅处理本交付manifest明确列出的自有源码/ABI文件，不扫描任务目录追收历史回执。既有清洁基线的150源I/O/185资料审查、15份实际数据排除和9份混合profile净化保留来源，新增源数以当前manifest为准；原生函数、RTTI、类、布局、偏移和导入字节仍严格守卫。4个先前只有路径加载的热输入已补齐，Shared StrategyApi、ReadApi四种固定profileName及两处PageDuplicate SaveProfile增加整体SHA校验。绑定工具递归重算自有资料的路径及内容 SHA，并同步所有原 SHA→纯ABI派生 SHA 的源 pin，不修改旧证据、不放松 native 守卫。WorkingRoot=RuntimeRoot\engineering。未绑定 Layout 源中的 PENDING 只是生成器输入，不能直接部署。

编译结果是 x86 自有 engine。将新的 `McgsInternalEngine_NNNN.dll` 与同名 `.scope.json` 一起放到已配置 BootstrapRoot\engines，核 DLL/SHA 后再由当前桥的既有 file-only engine 选择流程切换。已有 Bootstrap 不在更新 engine 时替换。首次部署的 `stage_engine.py` 只创建第一份 active-engine.json，不覆盖后续选择。新 bootstrap 的选择文件另外保留 bootstrap_scope_sha256；它与 engine 配置 engineering_delivery_scope_sha256 分开。

切换后只需一次当前工程 inspect 确认 scope attestation、大结果 payload、当前身份和完整前像，不为接入重新跑所有功能。以下是本次新 ID/新输出的命令形状；不要复制示例为某个历史 fixture。

```powershell
pwsh -NoProfile -File "$SkillRoot\run.ps1" native-engineering `
  --scope-config $DeployedScopeJson --scope-sha256 $ScopeSha layout
pwsh -NoProfile -File "$SkillRoot\run.ps1" native-engineering `
  --scope-config $DeployedScopeJson --scope-sha256 $ScopeSha `
  inspect --project $ActualOpenProject --id $FreshId --out $FreshReceipt
```

## 普通启动 Pro 后的热接入

先检查当前 Pro 是否已有可用桥：已有桥直接复用。未接桥时，包内提供[热接入工具与命令](../assets/pro-native-bridge/hot-attach/README.md)，可针对当前 PID 和主窗口所属 UI 线程加载自有桥，无需通过桥接启动器重新启动。`prepare_hot_attach.py` 只生成和编译工具；`McgsHotAttach.exe --connect` 自动完成自身 COM 注册与接入，不使用许可文件或额外确认框。生产连接沿用上面的目录绑定/编译和 `bootstrap/stage_engine.py`，工程操作仍由同一原生引擎执行。

本轮已验证自有纯 native x86 进程的冷 CLR 机制，并于2026-11-03完成**真实 Pro 普通启动后的热接入与同 UI 线程队列 ping**：接入前没有 CLR 或桥模块，接入后加载 CLR、连接成功、临时 hook 已移除，Pro 保持响应；随后停本次桥泵并清理专属 COM 注册，应用保留运行。详见[验证范围](../assets/pro-native-bridge/hot-attach/validation-summary.json)。本次没有打开或修改工程，也没有调用工程业务接口；连接通过不代替工程编辑或新电脑兼容验收。原有冷启动桥接方式继续可用，不为每次换工程重启。

## 可选冷启动部署

仅在选择原厂 Addins/桥接启动器兼容路线时，按 `bootstrap\README.md` 的 prepare、build、安装计划、Commit、launcher 和精确移除顺序操作。普通进程热接不要求这些 Addins/Startup 配置或重新启动。冷启动路线按真实安装资料指定原 EXE、Addins 目录/INI、Startup registry path、task/runtime/bootstrap 根。原 loader ABI 未匹配就拒绝，不能按产品版本猜入口。prepare/build 只处理自有源码，不注册、启动或打开工程；install 的 Commit 和 launcher 的 start 是独立明确操作。

冷启动 bootstrap prepare 要求新的 RuntimeRoot/BootstrapRoot，之后才建 RuntimeRoot 供 engine 绑定；原队列不能这样重建。该路线首次 stage_engine 后正常启动原应用，由原生回调建立 UI 线程队列。冷启动部署工具已做自有离线编译与 TYPELIB 检查，未据此声称任意电脑原厂加载、UAC/COM 环境均已验收。

## 编辑、保存与验收

`stage/run`在同一打开工程中实施program，`execute`可直接提交动作规格。默认direct在一个原生调用内逐动作取当前目标并执行，不使用磁盘permit文件或逐次审批。旧inspect/prepare/permit流程保留为兼容选项，正常操作无需先走它。

`commit`表示是否随编辑保存，不是授权许可。明确的page/module/root-flush动作本身即表示保存要求，无需再加一层commit许可。普通编辑可集中到末尾保存。原厂worker自身仍可能落盘，结果应如实记录。

最终保存前先用真实 pure-sync/close 入口同步关闭策略工作文档。历史策略 Doc83 内部会调用全工程保存，不能贴 child-only 标签使用。各被修改页面/主控/模块在direct中保存，最后单独RootSave；不要跨动作自动接纳未知 storage SHA。错误/timeout 保留 claim 和现场，依据新只读事实仅生成剩余步骤。

界面任务集中一次保存/检查/统一回读。direct将当前读取和执行放在同一队列调用内，减少跨调用的保存/编译状态变化。发生部分执行时，读取实际结果，只继续未完成动作，不重放已成功创建的对象。实际字节与编译缓存、图库hash及空密码尾字节的有限原厂投影按[在线界面施工](pro-native-ui-workflow.md)逐项证据处理，不宽免字段。

配方具名 System key 含 `MCGS_RECIPE_` 前缀，原 strName 容量为32个 UTF-16 code units；所有配方名在创建、复制、改名及 module4 保存前校验，不能仅凭原服务 AL1/dirty0 认定落盘。保存后原 ReadNamedData 完整解析索引及每个具名 CRecipe，比较所有已知列/矩阵/尾耗尽。`recipe-named-persistence-audit` 可核已保存内容而不重放 Save。raw_byte38 未入原 wire，仍按 live STORE 投影保护。具名回读前后如果整文件 SHA 变化，单独记录两个哈希；原72B0B0无Update/AddNew且时序不等于因果，以完整12表字段/BLOB确认仅已授权预期变更，不伪称物理恒定，也不接纳任意业务差异。

独立图库 CPicture 的原厂 STORE 会把内部 named Bitmap 展开成独立内嵌像素；重开后不存在永久嵌套名称链接。`picture-contained-reference-redirect` 支持显式 carrier path 的 private raster 替换，完整保护 path、owner、原 image/像素及其它资源，调用原 init/name setter/Refresh/Dirty/Save，不按重复 hash 猜 owner。最终比较必须核目标像素和其它 draw tree，而不能把 links1→0 当成永久引用成功。

Root85 检查和原 Close/Open 保留原厂自身 UI/警告/持久化语义，不是纯 headless API。原厂可能出现 Recovery 询问，消息循环中的计时保存也可能打开 SaveAs；须由用户或已授权电脑操作按真实提示处理，不通过系统消息、内存或隐藏确认包装跳过。既有关闭重开验收中实际取消SaveAs并选择不恢复后正常完成，原始claim未重发。Root85成功必须核 `native_check_passed`、本次worker entered/returned、返回整型0及检查后compile1；单独 `ok=true` 只表示正常返回。未知错误/警告计数写 unknown，不能编造0或仅用历史 compile1。生命周期默认直接执行；关闭后旧root/指针作废；原生新上下文及完整重开比较单独取证。运行期 PLC/脚本/设备通信不由组态操作执行。

CAniInput 的兼容字段 `words_uint32['54']` 只组合真实 byte54/55 两个0/1布尔值；可写packed值仅0、1、0x100、0x101。+56/+57是对齐填充，私有修改也不写这两字节。该类+60/+74为原编译器根据+58/+5C表达式生成的CByteArray，原工程STORE/LOAD不保存它们，重开构造后可为空；原运行输出在对应布尔为真时可能使用缓存，不能泛称无运行作用。当前业务比较仍精确保护两个真实布尔、源表达式、浮点备用值及所有其它已知字段，原始缓存差异另记，不宽免字节数组或序列化字段。

产品不支持旧 Counter/Timer/Data/Window/Device 动作节点时，`assets/pro-native-bridge/script-adapters` 提供纯文件 `emit(action)` 源码生成器及逐字段合同。返回 source、required_bindings、required_timer_ids、source_evidence、semantic_limits；实际对象/变量、独占状态变量及计时器预约必须由当前 inventory 证明。Window/Device 是原生对象表达式，不能以会话临时serial当永久ID。Counter边沿算法不能借用无关业务变量充当状态；纯Beep不等同WAV播放。该步骤只生成合法Prog文本，提交时仍使用真实source-batch前像与产品能力守卫；不运行生成的源码。
