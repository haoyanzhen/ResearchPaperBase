# Layer Design File Mapping

文档版本：v1.3
更新日期：2026-10-16
依据文档：`00_layers.md`  
用途：保存当前 `docs/design/` 目录中实际存在的分层设计与设计文件对应表，供其他设计文档引用，避免引用已删除或已改名的旧文件。

## 1. 对应表

| 分层/设计域 | 主要设计文件 | 协作设计文件 | 说明 |
| --- | --- | --- | --- |
| 分层总览与文件映射 | `00_layers.md`、`00-00_layer_design_file_mapping.md` | `README.md` | `00_layers.md` 定义分层原则；`00-00` 保存层到文件的对应表；`README.md` 作为目录入口。 |
| Functional Requirements / 需求与验收 | `01_functional_requirements.md` | `01-01-FR-reference.md`、`12_gap_decisions_review.md` | FR 是需求含义和验收标准的最高依据；参考与缺口决策文档用于追溯和审查。 |
| Domain Core / 领域核心 | [02_domain_core.md](02_domain_core.md)、[02-02_construction_versioning_appendix.md](02-02_construction_versioning_appendix.md)、[02-03_construction_assets_appendix.md](02-03_construction_assets_appendix.md)、[02-04_run_recovery_appendix.md](02-04_run_recovery_appendix.md) | `01_functional_requirements.md`、`07_data_persistence.md`、`07_data_schema.sql` | 主文定义核心边界、接口和领域事件；02-02 集中知识库版本规则，02-03 集中构建资产规则，02-04 集中运行恢复规则；附件与主文同规格、同规范效力，02-01 仅作派生速查，不定义 UI/API/数据库字段细节。 |
| UI / Workspace | [03_ui_workspace.md](03_ui_workspace.md)、[03-01_ui_system_pages_appendix.md](03-01_ui_system_pages_appendix.md)、[03-02_ui_construction_appendix.md](03-02_ui_construction_appendix.md)、[03-03_ui_research_review_appendix.md](03-03_ui_research_review_appendix.md)、[03-04_ui_shared_interactions_appendix.md](03-04_ui_shared_interactions_appendix.md) | `01_functional_requirements.md`、`02_domain_core.md` 及领域附录、`04_api_contracts.md`、`08_security_permissions.md` | 主文定义全局导航、Shell 布局组合和跨模块约束；附录分别维护系统页面、构建、研究与综述、共用交互的详细规范。主文与附录具有相同 UI 规范效力；业务规则以 01/02 为准。 |
| API Boundary / Contracts | `04_api_contracts.md` | `05_application_use_cases.md`、`08_security_permissions.md`、`09_quality_observability.md` | 定义 UI 与应用用例之间的 HTTP/SSE/文件访问契约、错误信封和鉴权边界。 |
| Application Use Cases / 应用编排 | `05_application_use_cases.md` | `02_domain_core.md`、`04_api_contracts.md`、`06_agent_knowledge_services.md`、`08_security_permissions.md` | 定义命令/查询、状态推进、任务提交、锁、幂等和失败诊断的编排边界。 |
| Agent & Knowledge Services | `06_agent_knowledge_services.md` | `02_domain_core.md`、`05_application_use_cases.md`、`07_data_persistence.md` | 定义 Construction、Research、Review、Graph-RAG、Knowledge Version、引用证据等服务能力。 |
| Infrastructure / Data Persistence | `07_data_persistence.md`、`07_data_schema.sql` | `06_agent_knowledge_services.md`、`10_operations_deployment.md` | 定义关系库、文件、向量、图谱、同步状态和 SQL schema。 |
| Security / Permissions | `08_security_permissions.md` | `02_domain_core.md`、`04_api_contracts.md`、`05_application_use_cases.md` | 定义用户隔离、管理员边界、Project 权限、文件访问、归档只读和高风险操作保护。 |
| Quality / Observability | `09_quality_observability.md` | `04_api_contracts.md`、`05_application_use_cases.md`、`10_operations_deployment.md` | 定义测试、日志、诊断、审计、指标和可观测闭环。 |
| Operations / Deployment | `10_operations_deployment.md` | `07_data_persistence.md`、`09_quality_observability.md` | 定义部署、容量、调度、备份、清理、运行维护和演进约束。 |
| Gap / Decisions Review | `12_gap_decisions_review.md` | 全部设计文件 | 保存跨文件缺口、决策、后续修订项和一致性审查结果。 |

## 2. 维护规则

- 本文件只登记当前 `docs/design/` 下实际存在的顶层设计文件。
- 新增、删除或重命名设计文件时，必须同步更新本文件及必要导航；`00_layers.md` 通过本映射引用文件结构，不再维护重复对应表。
- 若某一层的职责发生变化，应先更新 `00_layers.md` 的分层说明，再更新本文件的映射。

## 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|---------|--------|
| v1.0 | 2026-05-22 | 新建层级与当前设计文件对应表 | Codex |
| v1.1 | 2026-10-16 | 登记知识库并行构建与版本更新领域附录 | Codex |
| v1.2 | 2026-10-16 | 登记构建资产与运行恢复领域附录，明确专题详细规则和主文接口索引的职责 | Codex |
| v1.3 | 2026-10-16 | 登记四份 UI 模块附录，明确 Shell 主文、模块细节及业务规则来源 | Codex |
