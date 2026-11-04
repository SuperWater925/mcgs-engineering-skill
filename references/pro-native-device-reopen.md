# 设备保存与正常重开比对

同一会话的 before/after 仍逐字段精确比较原始值。下面的规则只用于正常关闭、重新由原厂 LOAD 后的新会话对照，不能作为编辑中宽泛掩码。

先绑定两个成功取得的完整 catalog、各自工程实际路径、原厂二进制 ABI、正常保存/关闭/重开回执。重开时重新验证对象 RTTI、所有权、合法内存与树结构，不把历史 pointer 作为新目标。

持久对照按完整 root→child 路径和原顺序匹配；名称、驱动模型、UID、绑定名称、已解析 native DWORD/byte 字段、数组及记录、完整 driver configuration BLOB 均必须与原厂 STORE 后像精确一致。H5U/McgsIoT 的 warm cache 另按实际已证明的原生 STORE 投影与同一完整 BLOB 核对，不能只比显示的少数属性。

| 字段 | 正常 STORE/LOAD 语义与严格比较规则 |
| --- | --- |
| complete/IObject/owner/数组与 CString 指针 | 本会话地址；新会话须重验其身份与所有权，不能要求数值相等，也不能据此忽略所指完整数据 |
| `native_serial`（complete+14） | 原 LOAD 按全局计数依次填写，STORE 不持久化此值；克隆也可能消耗该临时计数。保留实际值作诊断，不当永久唯一 device ID，不因此额外保存或重开 |
| physical parent（complete+24） | 原 LOAD 的 child 可以为 NULL；内存中原 SetParent 创建的对象可为确切 owning parent。root 必须 NULL，child 只接受 NULL 或当前确切 parent；树关系仍由真实拥有数组及完整路径确定 |
| complete+18 flags | 不属于已证 Base/Derived STORE 的 wire 字段；STORE 仅按 byte+114 对 bit24 作精确投影。会话内不能吞掉未知 flag 变化；跨 LOAD 记录原始值附表，不以此替代持久字段比较 |
| FC/warm cache 指针 | 可能由正常初始化/保存产生或重开后为空；不能仅为比较而额外初始化。已闭合 cache 完整内容须投影到 canonical BLOB，未闭合的语义仍报告 false/pending |
| serial scratch counter | 原 Doc STORE 可以归零，LOAD/clone 再消耗；不与永久业务 ID 混用。缺少中间调用证据时只报告真实变化，不设任意宽白名单 |

这些分类来自实际原厂 Base Serialize、Doc Serialize、LOAD 枚举与驱动 STORE 链，适用于包内实际守卫覆盖的类型。新派生类必须另证明，不能直接继承“所有字段都不重要”的结论。unknown raw 或新属性差异必须列出并停止对应验收。

安装驱动 Add 或配置修改成功表示组态接口正常返回，不表示通信、运行脚本或 PLC 已验证。原厂完整检查及最终保存重开结果单独记录；禁止把模块 Get 成功、handler_returned 或文件哈希变化写成 native_check_passed。
