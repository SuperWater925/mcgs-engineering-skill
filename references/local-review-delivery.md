# 本地审核更新与交付

2026-11-17 的改动先在本地完成统一验证，再更新本机技能及匹配的预编译引擎。本轮不发布、不创建远程标签，也不自动恢复暂停的工程。既有公开版本与本地未提交源码分开记录。

11 月 20 日续做的 Stu 工厂和 Pro 动画纳入同批本地交付。实际结果见[本地统一验收](local-validation-20261120.md)。

## 本轮范围

| 复查项 | 当前实现要求 |
| --- | --- |
| 1 | 首次变更前在同一原生调用核对计划依赖的工程实例、页面身份和必要前像 |
| 2–3 | 重开证据绑定读回进程及根身份；按每个父对象比较有序子控件 |
| 4–6 | 写前检查源子树克隆资格；工具栏动作后重核活动画布；依赖闭包排程 |
| 7–9 | 旧结果字段引用保留单件合同；可安全合批的同页动作使用批量入口；编译核实际引擎能力 |
| 10–11 | 完整 `prepare-online` 入口及唯一实例发现；启动 Python 前解析显式包路径 |
| 12–14 | 旧备份校验后迁出扫描根；启动器原样返回状态和输出流；自动索引失败不阻断后续候选 |
| 15 | CI 运行克隆、整页计划、HWND 和交付回归，并纳入本轮新增结构回归 |
| 条件风险 | 当前组布局按角色定位，顶层简单目标不因无关组树被阻断；Apply 异常后保留未知状态且不擅自刷新 |

离线新增的已有多状态控件与原生图库能力见[字段规格](state-resource-edits.md)。这些功能仍是安全导出归档的有限修改，所有源 SHA、前指纹、白名单及事务守卫继续生效。验证应明确区分纯夹具、文件回读与原厂打开、检查、保存重开、模拟；各阶段实际结果另记。

## 组装本地完整候选

全仓源码及清单检查完成后，生成当前业务引擎源码并编译到新目录，再构建启动器工具。业务引擎构建入口为 `assets/pro-native-bridge/portable-engine/build_generic.py` 及其生成的 `build-release.ps1`；启动器工具入口为 `scripts/build_turnkey_tools.ps1 -Output <新工具目录>`。工具清单记录 Launcher/InstallerChoice 的源码和 EXE 指纹。

使用已完整校验的旧包作为运行时、桥和安装介质来源：

```powershell
python -B -X utf8 scripts/build_local_candidate.py --base <旧完整包> --engine-build <本轮引擎构建目录> --tools <本轮工具目录> --output <新候选目录> --label 2026.11.17-local-review
python -B -X utf8 scripts/test_turnkey_launcher.py --bundle-root <新候选目录>
```

构建器核当前源码包清单、引擎来源合同、生成源码指纹和工具源码/产物指纹，替换根目录及 tools 中的新版启动器，按全部文件重新生成清单并完整校验后才公布候选目录。候选 `local-candidate.json` 记录 `local_only=true`、`source_commit=null`、实际 `source_base_commit`、`source_dirty`、源码包指纹、引擎和工具指纹。HEAD 只是基础提交，不冒充这份未提交源码；不生成发布索引或下载 URL。

正式 `build_turnkey_update.py` 仍要求已提交的干净源码树。它使用 `--tools` 或明确的本机工具候选，缺少匹配产物就拒绝，不能把旧基底启动器带回新包。

## 更新本机技能

候选已完成本轮约定的统一验收、且用户已授权更新本机技能时，执行：

```powershell
& '<新候选目录>\McgsRun.cmd' turnkey install-skill --bundle-root '<新候选目录>' --no-download
```

非默认技能位置加 `--destination <实际技能目录>`。回执给出旧技能完整备份及既有旧备份迁移记录；核安装内容与候选源码清单一致、安装指针指向本候选、引擎 SHA 与来源合同匹配。安装本身不接入 Pro、不启动业务任务；有已授权的在线验收需求时，再使用实际实例执行 `prepare-online`，保留各阶段证据。

纯回归依赖用 `python -m pip install -r scripts/requirements-tests.txt` 准备。CI 的夹具不调用厂商软件、不访问公共网络、不依赖作者路径；环境准备下载 Python/依赖与测试本身分开。
