# 离线配方与策略编辑

编辑规格使用 `recipe_edits` 和 `strategy_edits` 两个可选数组，索引从 0 开始。每项在上一项修改结果上执行。提交前会重新解析两个策略归档、配方索引和相应的触发器记录，错误会使本批数据整体回滚。

## 配方

| op | 字段 | 效果 |
|---|---|---|
| add_group | name, 可选 columns、records、template | 新建 System 定义并登记索引，可按已登记的模板组保留名称列及日志尾段 |
| rename_group | name, new_name, 可选 sync_controls | 保留数据库行 ID、组顺序、记录、列和尾段，更新索引、定义键和内部组名。可同步已核实的原生配方表组绑定 |
| delete_group | name | 移除指定定义和登记项 |
| insert_column / update_column | name, index, column, values | 插入或修改数据列。已有记录时插入列需逐行提供字符串，修改类型也需为各行提供值 |
| delete_column | name, index | 同时从每条记录删除该列 |
| insert_record / update_record | name, index, values | 插入或替换同宽记录 |
| delete_record | name, index | 删除指定记录 |

`column` 使用 `{"binding":"温度设定","title":"温度","type":2}`，绑定名和原生标量类型必须匹配当前工程变量。类型 1、2、3 分别代表开关、数值和字符。记录值按原厂 CString 保存，第一列是记录名称。组编辑仅处理已注册组，新组不能与遗留定义重名。

配方组被画面引用时，可显式提交 `{"op":"rename_group","name":"旧组名","new_name":"新组名","sync_controls":true}`。编辑会核对同一组使用的各个原生 `DrawRecipe.ui` 归档格式 22 配方表，包括组合内的表，并在同一次文件提交中更新这些表的组字段。至少要有一个可验证的配方表。记录中的文本原样保存，已验证的完整变量声明（例如配方名为 `面包`，变量名为 `面包组`）也按原归档保存。无法确认的引用或另一处完整同名仍会阻止写入，提示对应的表、字段和已知所属行。

Stu 与 Pro 官方 E 系列样例的 `面包` 组均已通过独立副本写入、文件回读和反向改名。16 条配方记录、变量与类型/浏览归档原样保留，逆向回读的 12 张表与源一致。本次样例未执行原厂打开、检查或模拟。

## 策略

| op | 字段 | 效果 |
|---|---|---|
| add_user_strategy | name, source, 可选 comment | 新建用户策略、一个脚本单元和用户触发器 |
| rename_user_strategy | name, new_name | 保留策略与触发器 ID，重算名称元数据长度并更新双份归档。仅支持单个用户触发器，其他字段含旧名或新名时停止 |
| set_strategy_comment | name, comment | 编辑现有用户策略的内容注释，传空串清空。按策略名及对应的唯一用户触发器核实身份，两份策略归档同步，保留触发器的独立备注、脚本及编译缓存 |
| delete_user_strategy | name | 移除任意位置的用户策略及与其 ID、类型精确对应的唯一用户触发器。两份归档分别重建 MFC 类和对象引用，保留其余策略和触发器的顺序及数据库 ID。其余字段中仍有同名引用时停止 |
| add_loop_strategy | name, 可选 interval_ms, comment | 新建空白自定义循环策略及原生间隔触发器。默认间隔 60000 毫秒，可在同一批次继续设定日历或添加脚本行 |
| delete_loop_strategy | name | 删除空白自定义循环和唯一匹配的触发器。保留系统默认循环，剩余字段有同名引用时停止 |
| set_loop_interval | name, interval_ms, 可选 switch_from_calendar | 修改 Stu 或 Pro 的现有间隔。自定义循环可显式用 `switch_from_calendar:true` 从已核对的日历归档切回间隔。同步两份存档 |
| set_loop_calendar | name，可选 calendar_period, month, day, hour, minute, second | 编辑 Stu、Pro 自定义循环的年、月、日、时、分定时。由间隔转换时提供所选周期实际使用的时间字段，省略周期时默认按日。原有日历模式可保留周期，仅修改指定字段 |
| add_event_strategy | name, variable, 可选 edge、comment | 新建一个空白事件策略并登记原生触发器。触发数据对象使用当前工程的开关或数值标量，默认正跳变 |
| delete_event_strategy | name | 删除没有策略正文和现存引用的自定义事件策略及其唯一触发表行 |
| set_event_trigger_variable | name, variable | 将现有事件策略的触发数据对象改为当前工程已登记的开关或数值标量。同步两份触发归档 |
| set_event_trigger_edge | name, edge | 修改原厂可编译的执行条件。同步两份触发归档，各自保留已有的表达式和编译缓存 |
| insert_script_row | name, row, source | 插入一个带默认条件与脚本的单元行 |
| delete_script_row | name, row | 删除具有单一默认条件和单一脚本的行 |
| set_script / set_condition | name, row, cell, index, value | 按精确路径替换脚本源码或条件表达式，清空被修改节点的旧编译码 |

`add_event_strategy` 与 `set_event_trigger_edge` 的 `edge` 可填 `rising`（正跳变）、`falling`（负跳变）或 `change`（数据变化）。原厂归档可保留 0→1→0 和 1→0→1，已验两家原厂编译器会拒绝这两种条件。已有此类条件的工程可将其改为上述可编译选项。未尝试写入时按原记录保留。

Stgy 的 lbObjects 和 System 的 StgyAndTrigger 必须包含相同的策略列表。触发器按策略 ID、类型、原生载荷和数据库行逐项配对。实测某些原厂默认触发器复用同一个首 DWORD，循环触发器两份归档的首个循环配置字也可能相差 65536。这些原有值分别保留。

例如用 `{"op":"add_event_strategy","name":"事件策略1","variable":{"id":103,"name":"本地触发"},"edge":"falling"}` 新建负跳变策略。触发器的原厂默认延时为 0，初始表达式缓存为空。后续可在同一 `strategy_edits` 数组用已有脚本行入口填充正文。删除按实际策略及触发表身份执行，即使原厂已经生成表达式缓存，也能删除符合上述条件的空策略。

`set_event_trigger_variable` 的 `variable` 使用离线 `inspect` 返回的 ID 和名称。示例为 `{"op":"set_event_trigger_variable","name":"事件策略1","variable":{"id":103,"name":"本地触发"}}`。支持单个变量名称。改绑会清空两份触发器的旧表达式编译缓存，策略正文、执行条件和延时保持原值。同一绑定重提时保留两份原生缓存，包括 Pro 实物中已核实、只有缓存内部变量 ID 不同的情况。由原厂组态检查重新编译。

`set_event_trigger_edge` 保持策略正文、触发表备注、表达式、各镜像原有编译缓存和原生延时字段。Pro 原厂保存可能在策略注册档写入当前开关的编译程序，而独立触发行仍保持空缓存，离线读写会保持这两份实际原文。可以把改绑和改执行条件写入同一编辑数组。

已识别的事件触发器可能有单独的数据库主键。此时按唯一的策略 ID 和触发类别定位数据库行，核对行备注和两个归档的完整原生身份与载荷，分别保留数据库主键和触发器内部 ID。

`set_loop_interval` 的 `interval_ms` 使用原厂范围 100 至 2147483647 毫秒。原本是间隔时保留两份归档各自的模式和日历配置字。自定义循环从日历切回间隔时，`System/StgyAndTrigger` 使用原厂保存的选择索引加一，`Trigger.lbContext` 使用原厂间隔读取的选择索引；两份档案的时间字段都保持。策略代码与编译缓存保持。

`set_loop_calendar` 的 `calendar_period` 使用 `year`、`month`、`day`、`hour`、`minute`，从间隔切入时分别填写月日起至秒、日起至秒、时分秒、分秒、秒。原生已存的间隔值和未指定或未使用字段均保持。两家按当前两份触发归档和原生循环类读写。Pro 有原厂保存、检查和重开记录，Stu 的原厂验收待统一执行。文件回读、原厂检查、关闭重开和运行效果分开验收。
修改列结构或删除组会定位用户窗口和嵌套组合中的实际配方控件。如果同名组正在被页面引用，操作会报告页面名称。仍可正常增删或修改组内记录。新建组遇到已有同名控件时会逐列验证组定义。首次建组采用实测的产品格式：Pro 格式字 1134562542，无日志尾段；Stu 格式字 1134564147，尾段为 0、2、0。

列操作可显式设置 `"sync_controls":true`，在同一事务内更新组定义、各行数据以及对应页面上的 DrawRecipe.ui 控件。每个控件先核对原关联，再独立回读新关联。控件第 0 列为序号，第 1 列对应组的记录名称列，均受保护。修改列保留原生显示设置，限相同类型。插入时还须指定 `display_template_index`，填同一组中已有的、同类型的非保留列索引，各页面分别从自身对应列取得显示设置。删除时保留所有其余显示列的完整原生字段。支持归档格式 22，遇到无法确认的页面引用或原关联不一致时整批停止。
