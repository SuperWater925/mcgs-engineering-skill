# 第三方文件与许可

本项目自有工具及源码按 skill/LICENSE（MIT）分发。MIT 不覆盖本包厂商软件、安装介质或第三方运行时。

- `vendor/pro/media`：本地保存的 McgsPro 3.5.2.12210 完整安装介质。原始来源归档 SHA256 为 `5de7bdbabe5cd8cd8ae7d38ceba8cef26109beaefeac57d5290ca19f4192ae95`，逐文件清单见相邻 media-files.json。保留 `Other/copyright_license.txt`（原中文编码）、`Other/third-party-license.html` 等全部原文件。第3.2条允许非商业性完整复制、分发和传播，要求完整真实且保留文档、版权、商标和协议；第4.3条要求商业销售、复制、分发、预装或捆绑取得作者授权。请以原许可全文为准。归档及文件校验只证明本次副本一致，不声称取得厂商签名认证。
- `vendor/stu/media`：本地保存的 McgsStu 3.5.3.9198 SP1 完整介质，原 ZIP SHA256 为 `1a4587a37c11f7fbbf46a749c5bdf1c8e09da730198e026f9b63f35e2f1e3f4b`。完整保留原 ReadMe 及其余文件。本次介质未发现独立许可文本，不能据此推断自由再授权或商业捆绑授权；安装及传播遵循权利人实际许可。
- `runtime/python`：来自 [Python 官方 Windows 可嵌入分发](https://www.python.org/downloads/windows/)，保留 LICENSE。附加 Capstone、Pillow 的 wheel 许可证随其 dist-info/licenses 原样保留。
- `runtime/pwsh`：来自 [PowerShell 官方发布](https://github.com/PowerShell/PowerShell/releases/tag/v7.6.6)，保留 LICENSE、第三方通知及分发自带文件。
- `runtime/installers/accessdatabaseengine_X64.exe`：来自 [Microsoft 官方下载](https://www.microsoft.com/en-us/download/details.aspx?id=54920) 的 Access Database Engine 2016 x64 Redistributable。组件按原 Microsoft 许可使用，仅离线数据库访问需要；不自动接受许可、不绕过 Office 安装冲突。原安装器完整保留。

完整包文件校验清单为 bundle-files.json；本包与源代码仓库分别交付，厂商安装文件不进入 Git 源仓库。未经另外确认，不把本地整合包等同于已获任意商业再分发许可的产品。
