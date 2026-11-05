# Pro 内部工程入口的目录绑定与部署

原生模块是内部 ABI 适配，随包提供自有源码、静态接口资料、Python 客户端和首次桥接部署工具。不含厂商 DLL、用户工程、图片、历史许可、私有账户或密码；离线空白工厂模板保留原厂默认权限结构，密码字段空。Stu 仍用共同的离线入口。发行版本和厂商整文件 SHA 都不作作者准入白名单；实际函数代码/重定位、RTTI、结构、归档和产品能力按调用需要核对，整文件差异仅记录。见[构建与接口匹配](pro-native-binary-compatibility.md)。

## 实际能力与选择

inspection 的 `compiled_kinds` 是本次编译入口清单，`action_preimages` 给出所选目标完整前像和 ABI SHA；编译存在不等于当前工程/产品一定允许。对应 kind 的实现源位于 `delivery/source/sources`，字段合同以当前 Read/Prepare 校验为准，不用历史例子补默认参数。

当前界面施工包含 `control-geometry-batch` 与标准按钮的显式 paired visual 预期；不同目标集合、组/组件选择、Flow包络、单位拆分和最终回读规则集中在[在线界面施工](pro-native-ui-workflow.md)。批次不再按样本写死64项，实际消息容量仍须满足。它们复用当前工程和原生接口，不建立第二套版本环境。

| 功能 | 选择与实际合同 |
| --- | --- |
| 页面/标准与复合控件 | 当前 page ID、完整 control path/name/type、原生 owner；创建/复制/组/层/几何/属性/动画/事件和集合保留非目标旁项 |
| 策略 | 当前 block ID/name、canonical/working 模型及真实行索引；完整源码、条件/动作/触发/上下文、创建/复制/删除及 pure-sync/close；先核产品能力 |
| 数据/组/数组/报警/配方 | 当前对象 ID/name/type、完整组及消费者；合法类型转换、嵌套/数组、原生 owned 报警列表、完整配方列/矩阵及具名回读 |
| 设备 | 完整 root→child path/name/UID/owner；安装目录原厂 Add、树 CRUD、保留子树属性发现/修改、引用感知改名；H5U/McgsIoT/monidevdrv 分别按各自闭合合同 |
| 图库/语言 | 当前完整 resource/language catalog、精确 carrier path；导入/导出/创建/复制/删除/重定向及完整目标外保护；独立图库 named 位按原 STORE 展开 |
| 引用与工程服务 | 全量真实消费者及 module/page/strategy 保存参与者；原厂引用编译同步、分阶段保存、Root85检查、专用正常Close/Open |

`device-catalog`、`data-catalog`、`recipe-catalog`、`picture-catalog`、`language-catalog`、`reference-graph` 等通过 inspection selectors 取得当前内容；驱动 property catalog 的原厂 Get 则是私有clone动作，不能把它混作完全无副作用的普通读取。未知派生控件/驱动、未闭合属性或产品不支持的动作精确拒绝；没有 PLC 运行或下载命令。

## 首次热接的文件准备

已有桥直接按下节更新；首次部署按以下顺序执行。使用 PowerShell 7，把占位路径替换为接收电脑的实际绝对路径；SkillRoot 可为 Codex 或 Claude 的实际安装目录，TaskRoot 可使用现有任务目录。InstallRoot 包含明确选择的真实 EXE，不再要求固定 `Program` 子目录。需要本机 `%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe`（x86）存在。所有工具用绝对路径调用，不依赖当前工作目录；SHA 均从本次文件计算，不复制作者路径、PID、历史 claim 或哈希。下面为首次输出生成独立子目录；已有桥不要重复首次部署。

```powershell
$ErrorActionPreference = 'Stop'
$SkillRoot = (Resolve-Path -LiteralPath '<已解压的mcgs-engineering完整目录>').Path
$InstallRoot = (Resolve-Path -LiteralPath '<本机Pro安装根目录>').Path
$TaskRoot = '<本次任务目录的绝对路径>'
$Native = Join-Path $SkillRoot 'assets\pro-native-bridge'
$PythonExecutable = if ($env:MCGS_PYTHON) { (Get-Command $env:MCGS_PYTHON -ErrorAction Stop).Source } else { (Get-Command python -ErrorAction Stop).Source }
$env:MCGS_PYTHON = $PythonExecutable
# 首次使用动态函数定位时，在同一解释器安装准备依赖；已有可用依赖无需重复安装。
& $PythonExecutable -m pip install -r "$Native\abi-adapter\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw '当前Python的在线定位依赖未就绪。' }
$DotNetFrameworkX86Csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
$ActualProExecutable = (Resolve-Path -LiteralPath '<本机Pro真实EXE的完整路径>').Path
if (-not (Test-Path -LiteralPath $DotNetFrameworkX86Csc -PathType Leaf)) { throw '缺少.NET Framework x86 csc.exe，先补齐本机编译环境。' }
if (-not (Test-Path -LiteralPath $ActualProExecutable -PathType Leaf)) { throw '安装根目录中未找到原Pro程序。' }
$ConnectionStamp = [DateTime]::UtcNow.ToString('yyyyMMddHHmmssfff')
$RuntimeRoot = Join-Path $TaskRoot ('runtime-' + $ConnectionStamp)
$FreshBootstrapRoot = Join-Path $TaskRoot ('bootstrap-' + $ConnectionStamp)
$EngineeringRoot = Join-Path $TaskRoot ('engineering-payload-' + $ConnectionStamp)
$NewLayoutDirectory = Join-Path $RuntimeRoot 'binding'
$NewBoundDirectory = Join-Path $RuntimeRoot 'bound'
$NewEngineFileName = 'McgsInternalEngine_' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmssfff') + '.dll'
$NewEngineScopeFileName = [IO.Path]::ChangeExtension($NewEngineFileName, '.scope.json')
New-Item -ItemType Directory -Path $TaskRoot -Force | Out-Null

# 1. 生产桥准备/编译；不加 --ping-only，不注册、不接入、不启动Pro。
& $PythonExecutable "$Native\hot-attach\prepare_hot_attach.py" `
  --task-root $TaskRoot --runtime-root $RuntimeRoot `
  --bootstrap-root $FreshBootstrapRoot --install-root $InstallRoot `
  --editor $ActualProExecutable --host-kind pro
if ($LASTEXITCODE -ne 0) { throw 'hot prepare失败；保留输出，不重跑同一目录。' }

# 2. 创建分离的只读资料目标与运行输出目录，复制本版transport原字节。
New-Item -ItemType Directory -Path $EngineeringRoot | Out-Null
New-Item -ItemType Directory -Path (Join-Path $RuntimeRoot 'engineering') | Out-Null
$TransportClientFile = Join-Path $RuntimeRoot 'bridge_client.py'
Copy-Item -LiteralPath "$Native\transport\bridge_client.py" -Destination $TransportClientFile
$Layout = Join-Path $Native 'delivery\device-entry-v2\NativeEngineeringDeliveryLayout.cs'
$LayoutSha = (Get-FileHash -LiteralPath $Layout -Algorithm SHA256).Hash.ToLowerInvariant()
& $PythonExecutable "$Native\delivery\device-entry-v2\prepare_delivery_binding.py" `
  --task-root $TaskRoot --engineering-root $EngineeringRoot --runtime-root $RuntimeRoot `
  --install-root $InstallRoot --transport-client-file $TransportClientFile `
  --editor-executable $ActualProExecutable `
  --engine-file-name $NewEngineFileName --layout-source $Layout --layout-source-sha256 $LayoutSha `
  --output-directory $NewLayoutDirectory
if ($LASTEXITCODE -ne 0) { throw 'binding失败；保留输出。' }

# 3. 从本次选定程序定位函数/RTTI，生成当前ABI资料并绑定源码，再编译x86自有engine。
$NewScopeJson = Join-Path $NewLayoutDirectory $NewEngineScopeFileName
& $PythonExecutable "$Native\delivery\bind_common_delivery.v5.py" `
  --source-stage "$Native\delivery\source" --scope-json $NewScopeJson `
  --bound-layout-source "$NewLayoutDirectory\NativeEngineeringDeliveryLayout.cs" `
  --output-directory $NewBoundDirectory --engine-file-name $NewEngineFileName
if ($LASTEXITCODE -ne 0) { throw '源码binding失败；保留输出。' }
& "$NewBoundDirectory\build-bound-source.ps1" -Csc $DotNetFrameworkX86Csc

# 4. 从本次输出取SHA，部署新ABI资料；每个目标都必须尚不存在。
$BoundManifest = Join-Path $NewBoundDirectory 'bound-source-manifest.json'
$BoundScope = Join-Path $NewBoundDirectory $NewEngineScopeFileName
$BoundEngine = Join-Path $NewBoundDirectory $NewEngineFileName
$BoundManifestSha = (Get-FileHash -LiteralPath $BoundManifest -Algorithm SHA256).Hash.ToLowerInvariant()
$ScopeSha = (Get-FileHash -LiteralPath $BoundScope -Algorithm SHA256).Hash.ToLowerInvariant()
& $PythonExecutable "$Native\delivery\promote_delivery_payload.py" `
  --bound-manifest $BoundManifest --bound-manifest-sha256 $BoundManifestSha `
  --scope-json $BoundScope --scope-sha256 $ScopeSha `
  --record "$NewBoundDirectory\payload-promotion.json" --commit
if ($LASTEXITCODE -ne 0) { throw '资料promotion失败；保留部分输出。' }

# 5. 首次stage只创建新active-engine，不覆盖已有选择。
& $PythonExecutable "$Native\bootstrap\stage_engine.py" --bootstrap-root $FreshBootstrapRoot `
  --engine-file $BoundEngine --engine-scope-file $BoundScope
if ($LASTEXITCODE -ne 0) { throw 'engine stage失败；保留输出。' }
$DeployedScopeJson = Join-Path "$FreshBootstrapRoot\engines" $NewEngineScopeFileName
$ScopeSha = (Get-FileHash -LiteralPath $DeployedScopeJson -Algorithm SHA256).Hash.ToLowerInvariant()

# 6. layout只核本地配置/资料，不接入Pro、不访问工程。
& "$SkillRoot\run.ps1" native-engineering `
  --scope-config $DeployedScopeJson --scope-sha256 $ScopeSha layout
if ($LASTEXITCODE -ne 0) { throw 'layout核对失败。' }
```

七项基本配置仍兼容：schema、task_root、engineering_root、runtime_root、install_root、transport_client_file、transport_client_sha256。新增可选 `editor_executable` 指定真实程序，ProgramRoot 从其父目录取得；旧七键沿用历史默认路径。生成器从当前 transport 合同填写指纹项。EngineeringRoot 与 RuntimeRoot 分离，前者保存只读 profiles / task-evidence，后者保存队列、claim 与 `engineering` 输出。未绑定 Layout 的 PENDING 不能部署。上述流程完成后，按[热接入的目标身份与连接步骤](../assets/pro-native-bridge/hot-attach/README.md#选择目标并连接)继续；只有接入成功后才使用当前工程的 inspect/编辑入口。

2026-11-04 从发布 ZIP 新解压到含中文及空格的独立目录，已完成本节生产 prepare、157源编译、307份自有ABI资料promotion、stage与新scope layout核对；均未注册或接入Pro、未调用业务engine。独立自有宿主另完成3次ping与清理。这是可搬移文件链证据，不代表新电脑环境或原厂业务验收。

新增 `editor_executable` 需要用本版 Layout 重新编译对应 engine；复制技能不会改变进程中已加载的程序集。上述示例使用数字引擎名，兼容旧 Bootstrap；本版 EngineLoader 才支持相同规则下的描述性 DLL 名。已有旧 Bootstrap 时继续用数字名，或按当前连接状态明确更新桥，不能只换引擎名就宣称旧代码已更新。显式 EXE 的路径绑定/部署已验证，改名 EXE 的完整厂商业务尚未验证，部分业务入口仍按原模块名找主模块。

## 已有桥的同任务更新

复用实际 TaskRoot、RuntimeRoot、BootstrapRoot、队列和历史结果；不要重跑上节创建新任务/首次 stage 的命令。选新的 binding/bound 输出目录、独立 EngineeringRoot 和版本化 transport 文件（例如 `bridge_client_0102.py`），按上节对应的 binding → compile → promotion 段生成新 engine / 同名 scope，不覆盖已加载DLL或在用资料。已有 Bootstrap 不随 engine 更新替换；启用新版后台调度需按[流水线兼容规则](pro-native-pipeline.md)接入新版 Bootstrap。

使用公开 `native-engine-select` 入口更新已有连接。先读当前选择；默认执行文件更新，显式加 `--plan` 才只预览，不需要重跑首次 stage：

```powershell
$CurrentSelection = & "$SkillRoot\run.ps1" native-engine-select --bootstrap-root $BootstrapRoot --status | ConvertFrom-Json
$EngineSha = (Get-FileHash -LiteralPath $BuiltDll -Algorithm SHA256).Hash.ToLowerInvariant()
$ScopeSha = (Get-FileHash -LiteralPath $ScopeJson -Algorithm SHA256).Hash.ToLowerInvariant()
& "$SkillRoot\run.ps1" native-engine-select `
  --bootstrap-root $BootstrapRoot --engine-file $BuiltDll --engine-scope-file $ScopeJson `
  --engine-sha256 $EngineSha --engine-scope-sha256 $ScopeSha `
  --manifest-sha256 $CurrentSelection.manifest_sha256
```

该步骤读取实际桥配置、核新 DLL 的编译 scope 合同，将新名称 DLL / scope 写入已有 engines 目录，保留选择前像后原子更新 active-engine，并回读；相同文件已选中时返回实际幂等状态。它不调用原厂对象，也不注册或启动新桥。发生未知结果先 `--status` 核实际选择，不重复工程写入。当前引擎名不能复用为另一份内容。

工具保留当前 bootstrap_scope_sha256，不能误填 engine 的 engineering_delivery_scope_sha256。每次工程请求单独给路径，默认 direct 在调用内读取当前 PID、线程与目标前像。切换后仅做一次实际工程 inspect，确认 scope attestation、大结果 payload、`cross_build_contract=mcgs-native-cross-build/v2` 和当前身份，不为更新重跑全部业务功能：

```powershell
& "$SkillRoot\run.ps1" native-engineering `
  --scope-config $DeployedScopeJson --scope-sha256 $ScopeSha `
  inspect --project $ActualOpenProject --out $FreshReceipt
```

FreshReceipt 使用 runtime 内的新文件。未知/超时结果保留 claim，先读实际状态，不自动重发。暂停工程不会因工具更新恢复。

## 普通启动 Pro 后的热接入

先检查当前 Pro 是否已有可用桥：已有桥直接复用。未接桥时，包内提供[热接入工具与命令](../assets/pro-native-bridge/hot-attach/README.md)，可针对当前 PID 和主窗口所属 UI 线程加载自有桥，无需通过桥接启动器重新启动。`prepare_hot_attach.py` 只生成和编译工具；`McgsHotAttach.exe --connect` 自动完成自身 COM 注册与接入，不使用许可文件或额外确认框。生产连接沿用上面的目录绑定/编译和 `bootstrap/stage_engine.py`，工程操作仍由同一原生引擎执行。

本轮已验证自有纯 native x86 进程的冷 CLR 机制，并于2026-11-03完成**真实 Pro 普通启动后的热接入与同 UI 线程队列 ping**：接入前没有 CLR 或桥模块，接入后加载 CLR、连接成功、临时 hook 已移除，Pro 保持响应；随后停本次桥泵并清理专属 COM 注册，应用保留运行。详见[验证范围](../assets/pro-native-bridge/hot-attach/validation-summary.json)。本次没有打开或修改工程，也没有调用工程业务接口；连接通过不代替工程编辑或新电脑兼容验收。原有冷启动桥接方式继续可用，不为每次换工程重启。

## 可选冷启动部署

仅在选择原厂 Addins/桥接启动器兼容路线时，按 `bootstrap\README.md` 的 prepare、build、安装计划、Commit、launcher 和精确移除顺序操作。普通进程热接不要求这些 Addins/Startup 配置或重新启动。冷启动路线按真实安装资料指定原 EXE、Addins 目录/INI、Startup registry path、task/runtime/bootstrap 根。冷接按显式 Addin、TYPELIB 和四回调协议配置，不要求作者 EXE 指纹相等；实际加载与业务结果另行核实，不能按产品版本猜入口。prepare/build 只处理自有源码，不注册、启动或打开工程；install 的 Commit 和 launcher 的 start 是独立明确操作。

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
