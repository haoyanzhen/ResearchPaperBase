# Layer Design File Mapping

文档版本：v1.0  
更新日期：2026-05-22  
依据文档：`00_layers.md`  
用途：保存当前 `docs/design/` 目录中实际存在的分层设计与设计文件对应表，供其他设计文档引用，避免引用已删除或已改名的旧文件。

## 1. 对应表

| 分层/设计域 | 主要设计文件 | 协作设计文件 | 说明 |
| --- | --- | --- | --- |
| 分层总览与文件映射 | `00_layers.md`、`00-00_layer_design_file_mapping.md` | `README.md` | `00_layers.md` 定义分层原则；`00-00` 保存层到文件的对应表；`README.md` 作为目录入口。 |
| Functional Requirements / 需求与验收 | `01_functional_requirements.md` | `01-01-FR-reference.md`、`12_gap_decisions_review.md` | FR 是需求含义和验收标准的最高依据；参考与缺口决策文档用于追溯和审查。 |
| Domain Core / 领域核心 | `02_domain_core.md` | `01_functional_requirements.md`、`07_data_persistence.md`、`07_data_schema.sql` | 定义核心对象、关系、生命周期、不变量和领域事件，不定义 UI/API/数据库字段细节。 |
| UI / Workspace | `03_ui_workspace.md` | `01_functional_requirements.md`、`04_api_contracts.md`、`08_security_permissions.md` | 定义系统入口、Project Workspace、对象切换、面板、只读知识资产和用户可见状态。 |
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
- 新增、删除或重命名设计文件时，必须同步更新本文件和 `00_layers.md` 中的对应表。
- 若某一层的职责发生变化，应先更新 `00_layers.md` 的分层说明，再更新本文件的映射。

## 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|---------|--------|
| v1.0 | 2026-05-22 | 新建层级与当前设计文件对应表 | Codex |
