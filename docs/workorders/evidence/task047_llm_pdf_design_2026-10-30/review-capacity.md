# Task047容量配置及纯预算核心独立增量审查

版本：v1.0
日期：2026-10-30

## 局部结论

容量配置增量及新纯预算核心局部S3复审通过；发现一项P2机器契约漏洞，已修复并用原红测验证。没有发现本次范围内剩余实现阻塞。**这不是完整LP、Run接入、数据库预算原子性或M-P0-16验收。** D-PDF-03已由用户决定新增可修改每模型容量、默认256K；D-PDF-04未填写输出上限时的处理仍待答复，不据本报告默认4096或沿Provider默认擅自派发。

范围包括context_capacity.py、LLMStore/API、LLMSettings、相关unit/LC23–24/LU10/系统字段与契约测试、四个机器schema、bounded特例和04-04/task047；后续追加pdf_cleanup_budget.py及其unit。按AGENTS bootstrap、task entry、DELIVERY_TOOLS §5独立read，ledger=review-capacity-ledger.json，context=review-capacity-20261030。相关实际文件及未跟踪预算文件均纳入，原/最终SHA分别在review-capacity-artifacts.json、review-capacity-final-artifacts.json。

## P2发现与修复

contracts/p0.openapi.json中LLMWrite、LLMPatch、LLMView的容量映射propertyNames原pattern以$结束。JSON Schema所用正则允许$匹配末尾换行之前，因而模型ID“model-a＋LF”通过机器契约，但后端model.strip()明确拒绝，违反04-04“无首尾空白”。独立review-capacity-contract1三条反例均失败（真实exit1），不是推断。

主代理把三个schema及check_api_contracts精确路径特例统一为绝对末端否定断言(?![\s\S])，新增真实LF回归。独立原三条红测在review-capacity-final1全绿，契约专用测试3/3、完整check_api_contracts也通过。仅三处具名容量映射放行动态键，仍限定1000项、200字符键、正整数上限2147483647，未放宽任意其他开放对象。曾怀疑测试字面量转义，实际测试通过且主AST核对为LF；不列作第二项缺陷。

## 业务、权限与兼容核对

容量位于model_context_windows独立应用元数据，context_window_tokens只做解析后选项投影；未设置模型为262144，不是模型能力实测。严格拒绝bool、零/负/非整数/超界值和非法模型键。PATCH省略保留、提供映射整体替换、{}恢复默认、null拒绝，服务端沿原事务/expected_revision与审计路径写入，修改失效旧修订测试。新配置UI明确声明用户假设、输入与输出总容量及重测要求，草稿加入/删除恢复默认后沿原保存流程。

个人owner_filter与系统管理员permitted_actor先于配置读取/修改，容量未增加绕过权限的独立入口；系统安全ModelOption只增加容量数字，不含配置或密钥。本人/管理员作用域仍由既有服务判定。本次未新跑完整权限/浏览器套件；主capacity-storage2摘要60/60含相关回归已读，不能说由本代理独立重跑。

独立真实隔离PG反例将已存在且模型测试通过的配置数据移除新字段，模拟升级前持久数据：GET返回{}及默认262144、保持旧revision和available，不写回数据库；随后显式容量修改正常生成新修订并要求重测。与LC23/24共3/3通过。读取兼容不要求迁移或把旧记录全量补写。

独立四协议请求体probe给config加入524288容量，仍只外发原生成参数与文本，request body无容量字段或值。主追加LP07/LCP01同类断言也在本代理最终批次通过。配置保存不调用模型，容量不是parameters/custom_params透传入口。Run冻结容量及真实token预算尚未接入，不能从配置CRUD通过推断实现完成。

## 纯预算核心审查

new_budget保存revision=1及当次limits；reserve采用冻结的30/120/240秒与32/64次，按来源与组剩余取最小timeout，先预扣整个时限和调用数，设置唯一pending。未知结果经JSON往返仍阻止后续派发，不能通过换source逃脱；settle仅匹配pending ID，重复/迟到不能给新请求退款。已知耗时按实际调账，超时执行过长也计入组/来源；新独立组创建独立预算。默认代码值后改不改变已有快照，最终budget07已审并执行。

本模块只修改应用拥有的可序列化字典，尚无Run锁或数据库事务。调用方必须在锁下持久提交reservation后才能外呼，并在同一执行/来源/输入修订资格下提交settle；禁止把该字典当客户端可修改配额。崩溃后的pending不得清零重发。14项纯函数通过不证明这些跨事务/外呼边界，后续仍需确定性交错与真实持久化测试。

## 实际执行证据

- review-capacity-unit1：exit0，17/17（容量13＋独立四协议不外发4）。
- review-capacity-storage1：exit0，3/3（LC23/24＋独立旧数据兼容）。使用scripts/run_storage_tests.py及PostgreSQL17临时隔离集群，禁用TCP、非超级用户；log含server_stopped=true、root_removed=true。未接触业务数据库或真实Provider。
- review-capacity-contract1：exit1，3条末尾LF红测失败，原证据保留。
- review-capacity-final1：exit0，58/58（原LF反例3＋当时预算13＋两Provider回归42），没有skip。
- review-capacity-contract-suite1：exit0，契约专用3/3。
- review-budget-final1：最终冻结limits增量后，仅复测预算14/14，exit0；未重复不受影响整批。
- review-capacity-check1：系统python缺openapi_spec_validator，真实exit1，未安装依赖或称通过；读取主run记录后改用既有contracts/.venv/bin/python，review-capacity-check2真实exit0。工具明确未提供旧baseline，所以不声称机器兼容性全量证明，权限/事务也不是此工具验收内容。

以上全部保存完整log、真实run退出码、JUnit（适用时）并实际调用delivery_summary，非仅提及工具。预算新symbol首次猜错退出2，outline后读取实际test_budget07_restart_uses_frozen_limits；未用错误输出推断通过。最终业务/测试SHA见review-capacity-final-artifacts.json，失败证据不删除。

## 剩余边界

输出预算默认规则D-PDF-04、Run选择与冻结、分类等待/自动继续、实际输入/输出/协议开销预算、权限收紧/取消/迟到、确认失效与UI闭环都仍须接入和验证。用户声明容量不是tokenizer或服务端上下文能力的证明；不可静默忽略输出预算或宣称Provider一定接受。M-P0-15平台/提交缺口继续独立保留；局部代码审查不批准提交、push、真实模型测试或外发资料。
