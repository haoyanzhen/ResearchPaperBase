# 新核心设计与审核入口

文档版本：v1.2
更新日期：2026-10-22

## 1. 当前依据

本入口组织Codex任务和人工审核，不新增产品规则。工程交付范围与实际运行状态统一见[项目状态](PROJECT_STATUS.md)；首批工程审核材料见[任务005](../tasks/005-engineering-skeleton.md)。A01–A03为此前设计与流程准备；业务实现仍须有明确任务范围。

开始任务时读取[AGENTS](../AGENTS.md)、[项目状态](PROJECT_STATUS.md)、[设计索引](design/README.md)和下表对应规范。业务含义与分期以01为最高依据；02及附录展开领域规则；03定义交互；04定义协议；05–10负责各层约束。明确的派生速查错误可按规范更正；真实业务规范冲突只暂停依赖部分并请求裁决，不能按文件更新时间选择规则。

| 任务范围 | 最小必读集 | 使用边界 |
| --- | --- | --- |
| 工程初始化 | [00](design/00_layers.md)、[工程基线](design/00-01_engineering_baseline.md)、[05-01](design/05-01_internal_module_contracts.md)、[09](design/09_quality_observability.md)、[10](design/10_operations_deployment.md) | 目录落地与验证证据见任务005；不把层拆成服务 |
| 账号、配置、Project | [01](design/01_functional_requirements.md) FR-001–008适用子条目、[02](design/02_domain_core.md)、[03-01](design/03-01_ui_system_pages_appendix.md)、[04-01](design/04-01_p0_operation_contracts.md)对应操作、[05](design/05_application_use_cases.md)、[07](design/07_data_persistence.md)、[08](design/08_security_permissions.md) | 配置测试字段仍须按08 §12.2校准，不推定已有schema全部闭合 |
| 受理与提交 | 04 §7、05 §3/§12、05-01 §2/§4、07 §6、09 ARC-03/04 | 同步命令不创建伪Task/outbox；异步先持久提交再返回 |
| 补充、解析、分类 | [02-03](design/02-03_construction_assets_appendix.md)、[03-02](design/03-02_ui_construction_appendix.md)、[04-02](design/04-02_transport_task_file_contracts.md)、[06](design/06_agent_knowledge_services.md)、[08-01](design/08-01_agent_data_access_policy.md)及对应05/07 | 单文件为P0；A05–A08未闭合，不能用通用metadata接口补洞 |
| 发布、研究与综述 | [02-02](design/02-02_construction_versioning_appendix.md)、[03-03](design/03-03_ui_research_review_appendix.md)、[03-04](design/03-04_ui_shared_interactions_appendix.md)、04–09对应章节 | 空版合法、旧对象固定版本；A09选型仍延期 |
| HTTP与任务交付 | [04](design/04_api_contracts.md)、04-01/04-02、[04-03](design/04-03_machine_contract_governance.md)、08、09 | 机器契约只约束实际覆盖结构；错误/任务/资料策略缺项按任务收口 |

## 2. 任务与审核流程

Codex执行原则与测试义务统一见[AGENTS](../AGENTS.md#codex-delivery-principles)及其验证要求；本节维护人工审核与双方交接流程，任务模板只记录本次实例。人工决定产品取舍与最终接受，Codex负责交付质量和验证证据。

| 阶段 | Codex交付 | 人工职责 |
| --- | --- | --- |
| 明确任务 | 按[任务模板](../tasks/example.md)列出可观察结果、范围、规范与验收场景；用[小任务清单](workorders/preimplementation_design_tasks_2026-10-21.md)确定实际前置 | 明确授权范围和预期，不把所有A类事项设为共同阻塞 |
| 核对依据 | 核对实际工作区与规范，建立精确基线；真实冲突列入决策栏 | 裁决需人的业务问题，不逐项审批常规工程细节 |
| 实现与自验 | 实现切片、补齐需求到测试的追踪、执行检查并完成自审 | 按需澄清规则；不代替Codex补基础测试或排查明显报错 |
| 提交审核 | 提供单一审核包：差异、当前执行证据、演示步骤、关键代码位置、未验证项 | 先审行为与反例，再检查关键实现，抽查或复现证据 |
| 修复与复验 | 修复缺陷并重跑受影响检查；基线变化时更新证据和审核范围 | 核对问题闭合；新增需求单列范围与授权，不混入缺陷修复 |
| 记录结论 | 分列设计、代码、自动验证和人工审核状态；汇总到PROJECT_STATUS，细节保留在任务记录 | 明确接受范围、未接受项和后续授权；未审核不得记为批准 |

[Project创建幂等示例](../tasks/004-project-create-idempotency-example.md)仅演示填写，不授权编码，也不关闭A04/A10。设计批准不自动授权部署、外部通信或下一任务。

### 人工审核要点

以任务涉及的现行规范为准，逐项选择适用检查；下表只提供审核视角，不新增业务语义。

| 审核对象 | 要回答的问题 | 可检查的证据 |
| --- | --- | --- |
| 需求与用户行为 | 成功、拒绝和失败是否符合预期；每个可测需求是否有面向需求的用例且通过 | 需求追踪表、演示、断言与当前运行结果；缺项不能用通过率掩盖 |
| Project隔离与权限 | 身份共享是否泄露其他Project文件或分析；读取、下载和结果提交是否执行适用授权 | 授权位置、跨Project负例、撤权场景及持久副作用 |
| 状态与写入所有权 | Workspace恢复是否越界写业务状态；知识版本是否仅由成功Construction Run发布 | 应用写入入口、事务边界、失败及迟到Worker测试 |
| 版本与人工保护 | 旧Session/Review是否保持绑定；Agent是否覆盖人工确认或编辑内容 | 版本选择与提交条件、旧版本读取及并发编辑反例 |
| 持久一致性 | 重复、并发、响应丢失或提交失败是否导致重复与部分写入 | 唯一约束、事务代码、真实存储与确定交错的测试 |
| 证据可信度 | 检查是否针对当前产物；反例能否识别错误实现；隔离和清理是否成立 | diff、基线、实际命令、报告与残留记录；mock和静态检查不得冒充端到端验收 |

不要求平均阅读每行代码，应直接检查权限、事务、绑定和提交资格等关键位置，并对重要场景亲自复现或抽查。不能仅依据Codex总结或测试数量接受交付。审核结论记录审核者、日期、产物基线、接受范围及问题处置；未验证项保留明确状态。“看起来不错”不能替代有范围的接受记录，自动检查通过也不代替人工结论。

## 3. 历史与候选材料

- [历史重写计划](proposals/core_rewrite_plan_2026-10-16.md)保留旧文件处置和当时工作包，不作为当前路径、待决事项或任务依赖；历史测试不验收新核心。
- [01-01](design/01-01-FR-reference.md)与[02-01](design/02-01-domain-reference.md)只用于定位，整条FR分期不能覆盖P0子集，聚合对象清单不等于首版建表清单。
- [013选型参考](design/013-graph-choose.md)、backup和archive不定义现行规范；Memory及未授权延期范围不自动启动。
- 本轮限定核对的差异、接缝与精确摘要见[A01–A03记录](workorders/a01_a03_design_closure_2026-10-21.md)。记录区分Agent核对与人类批准，不声称全设计集语义已审查。
