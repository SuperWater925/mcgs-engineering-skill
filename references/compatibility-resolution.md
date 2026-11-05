# 跨版本复查后的逐项处理

本页维护“某个消费入口实际能做什么”，不按Pro/Stu软件发行号准入。历史发布验证保持原含义；当前验证见[分项记录](compatibility-resolution-validation.json)。

本页对应前轮消费入口与配额修复；后续分层定位和功能隔离见[自动适配说明](adaptive-native-location.md)及[独立验证](adaptive-native-location-validation.json)，不改写本页原验证范围。

## 先区分四类结果

- 接线遗漏：同一个格式适配器必须接到所有实际入口，不能因一个审计分支通过就认为修改分支也已接通。
- 不必要依赖：局部读取或修改只解析目标和必需消费者；不用到的变量、页面、策略、驱动或函数不得作为前置。
- 工具配额：依实际容器、流边界、可读内存和运行时表示范围处理，不用作者工程数量作为上限。默认合并预算是性能设置，不是原厂容量。
- 真实能力：未知私有布局、不同架构/调用约定、未实现的插件/驱动归档要对应codec或ABI；不能删除比较、猜偏移或要求升级到作者版本。

## 当前工具和连接

复制新版技能不会替换进程中已加载的引擎。记录回执的`native_function_binding`、`cross_build_contract`及实际按条目验证能力；合同修订号用于定位工具，不按精确字符串拒绝未来修订，更不是Pro版本限制。本次所需接口能力缺失时，更新相应业务引擎。普通小请求沿用已有桥；涉及宿主新能力时，另外核对实际加载的宿主，不能把磁盘源码已更新当成进程已经升级。

本版业务引擎记录`cross_build_contract=mcgs-native-cross-build/v4`。这是工具实现的证据标签；接收入口仍核本次所需能力，不以恰好等于`v4`作为准入条件。

路径先绑定真实目标；文件、当前进程、工程、配置和回执仍核对各自身份。等价DLL副本必须证明内容和逻辑角色唯一；不同内容同名文件不能混用。模块发现、函数定位和可调用布局分别记录，自动发现到同族运行库不等于ABI兼容。

热接自有COM注册的CodeBase使用CLR读取程序集得到的值，与RegAsm一致；不能将中文路径改成百分号编码后当作同等可加载。旧工具留下的编码值只在本任务scope、CLSID、程序集及全部注册结构一致时迁移这两个字段，不改厂商或其他任务注册。连接失败先读原始HRESULT和回执，未进入Attach的已证失败与结果未知分开处理。

## 局部操作与保存

目标读取、显式inspect、direct编辑和关闭重开的摘要分别核对。默认摘要不解释无关控件和策略的私有结构；关闭重开仍核真实工程身份和已打开文档的未保存状态。需要全工程引用同步或完整归档的操作，继续验证它真实需要的消费者，不能以局部规则跳过关联更新。

只有实际使用的函数、虚表槽和属性参与本次可用性判定。资料不完整不代表其中已证明的入口不可用；反之，资料文件能读也不代表未证明的槽可以调用。未识别的非目标对象保留原状态；目标自身的未知私有结构不假装已支持。

接口资料中的modules/functions/methods可按实际使用列表或具名映射；规范化不改原始条目及解析证明。没有明确rva的语义说明、标量或反汇编资料不生成可调用函数。同名多条声明保留，只有请求歧义名称时报告，不能猜选一条或阻塞无关读取。静态属性等合同文件同样纳入本次部署完整性索引；资料SHA不等同于厂商发行版白名单。

## 容量与并行

stage/run不再使用每步64动作、每程序1024步作为准入；独立direct与阶段程序遵守同一非空、唯一身份和实际数据合同。默认8动作/8MiB合并预算用于控制单次UI占用，可调整动作合并预算，不能写成原生请求容量。后台准备和派生IO可以并行，原厂工程对象访问、修改、保存和释放仍在同一UI线程。

请求正文优先以规格文件传递。输入和完整回执不再按16MiB样本拒绝，仍受当前x86/.NET字符串、数组和JSON序列化能力及实际内存限制。回执长度、SHA和请求关联必须核对。结果序列化失败或超时可能发生在写入之后，先读实际状态，不自动重放。

## 保留的真实边界

- Stu当前仅离线；在线仅当前x86 Pro/MSVC/MFC适配，不宣称x64/ARM或任意编译器对象布局支持。
- 真实私有对象、字段、动画/事件、插件、驱动缓存和归档变化仍需实现，源码函数不写死不等于所有内部结构都一致。
- 固定空白模板描述新建来源；不限制既有工程分辨率。低版原厂能否打开该模板需真实证据，不能改写MCGSVER伪装。
- ACE/ADOX、PowerShell/Python、编译工具、字体/插件、COM及文件权限按相应功能准备；离线ACE缺失不拒绝纯在线。
- 原厂产品能力、工程密码、保存转换/恢复提示及模态框仍按实际行为处理。编辑接口不自动包含设备下载或现场通信。

## 离线编码、模板和预览

未改CString保留实际窄/宽字符和原长度编码。已知中文归档的窄字符串默认cp936；其他实际编码可在同一环境设置`MCGS_ARCHIVE_CODEPAGE`，例如`$env:MCGS_ARCHIVE_CODEPAGE='cp1252'`，作用于本次Python子进程的窄字符串及相应字体读取，不按软件发行号猜测编码。原UTF-16内容不受该设置改变。编码设置不代表未知字段或插件schema已适配。

`tools/离线预览.py --language-id N`可选择实际语言ID；没有指定时优先语言ID 0，否则使用实际首个翻译。选择归档已知使用的编码和实际存在的语言ID后，可从PowerShell 7运行以下文件入口；`$PreviewOutput`须为新目录或空目录，命令只读取既有安全导出。

```powershell
$SkillRoot = (Resolve-Path -LiteralPath '<mcgs-engineering完整目录>').Path
$PythonExecutable = if ($env:MCGS_PYTHON) { (Get-Command $env:MCGS_PYTHON -ErrorAction Stop).Source } else { (Get-Command python -ErrorAction Stop).Source }
$ExportDirectory = (Resolve-Path -LiteralPath '<run.ps1 inspect的导出目录>').Path
$PreviewOutput = '<本次预览输出绝对路径>'
$LanguageId = 0 # 替换为当前多语言表实际存在的ID
$PreviousArchiveCodepage = $env:MCGS_ARCHIVE_CODEPAGE
try {
  $env:MCGS_ARCHIVE_CODEPAGE = 'cp1252' # 仅在本次窄字符串确属该编码时设置；中文默认cp936
  & $PythonExecutable -B -X utf8 "$SkillRoot\tools\离线预览.py" `
    --export-dir $ExportDirectory --output $PreviewOutput --language-id $LanguageId
  if ($LASTEXITCODE -ne 0) { throw '离线预览未完成，请核本次输出与错误。' }
} finally {
  if ($null -eq $PreviousArchiveCodepage) { Remove-Item Env:\MCGS_ARCHIVE_CODEPAGE -ErrorAction SilentlyContinue }
  else { $env:MCGS_ARCHIVE_CODEPAGE = $PreviousArchiveCodepage }
}
```

预览与文字检查逐页列出无法解析的内容，模板自动扫描列出不支持的候选；不把“其余页继续”解释为未知控件可以删除。明确指定的目标页或模板无法解析时仍报告该目标缺口。

多状态nav样式可用`states`映射选择实际状态；未选择状态和未知填充保持原样。窗口属性通过语义字段及Variant类型核对，仍需当前实际字段顺序合同，不能根据几个相邻数值猜属性重排。

验证必须分开写：源码/文件回环、托管或隔离宿主、真实Pro读取与写入、原厂检查、关闭重开、本机模拟、现场通信。未执行的项目写未完成；本机通过不能扩写成所有旧版已实测。
