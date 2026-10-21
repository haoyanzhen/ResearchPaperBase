# Layer Design File Mapping

文档版本：v1.10
更新日期：2026-10-21
依据文档：`00_layers.md`  
用途：保存当前 `docs/design/` 目录中实际存在的分层设计与设计文件对应表，供其他设计文档引用，避免引用已删除或已改名的旧文件。

## 1. 对应表

| 分层/设计域 | 主要设计文件 | 协作设计文件 | 说明 |
| --- | --- | --- | --- |
| 分层总览与文件映射 | `00_layers.md`、`00-00_layer_design_file_mapping.md` | `README.md` | `00_layers.md` 定义分层原则；`00-00` 保存层到文件的对应表；`README.md` 作为目录入口。 |
| Functional Requirements / 需求与验收 | `01_functional_requirements.md`、`01-01-FR-reference.md` | [退役归档](../archive/design_retirement_2026-10-19/README.md) | FR 是需求含义和验收标准的最高依据；01-01 仅为派生速查，不定义独立需求规则；缺口决策文档用于追溯和审查。 |
| Domain Core / 领域核心 | [02_domain_core.md](02_domain_core.md)、[02-01-domain-reference.md](02-01-domain-reference.md)、[02-02_construction_versioning_appendix.md](02-02_construction_versioning_appendix.md)、[02-03_construction_assets_appendix.md](02-03_construction_assets_appendix.md)、[02-04_run_recovery_appendix.md](02-04_run_recovery_appendix.md) | `01_functional_requirements.md`、`07_data_persistence.md` | 主文定义核心边界、接口和领域事件；02-02 集中知识库版本规则，02-03 集中构建资产规则，02-04 集中运行恢复规则；附件与主文同规格、同规范效力，02-01 仅作派生速查，不定义 UI/API/数据库字段细节。 |
| UI / Workspace | [03_ui_workspace.md](03_ui_workspace.md)、[03-01_ui_system_pages_appendix.md](03-01_ui_system_pages_appendix.md)、[03-02_ui_construction_appendix.md](03-02_ui_construction_appendix.md)、[03-03_ui_research_review_appendix.md](03-03_ui_research_review_appendix.md)、[03-04_ui_shared_interactions_appendix.md](03-04_ui_shared_interactions_appendix.md) | `01_functional_requirements.md`、`02_domain_core.md` 及领域附录、`04_api_contracts.md`、`08_security_permissions.md` | 主文定义全局导航、Shell 布局组合和跨模块约束；附录分别维护系统页面、构建、研究与综述、共用交互的详细规范。主文与附录具有相同 UI 规范效力；业务规则以 01/02 为准。 |
| API Boundary / Contracts | [04_api_contracts.md](04_api_contracts.md)、[04-01_p0_operation_contracts.md](04-01_p0_operation_contracts.md)、[04-02_transport_task_file_contracts.md](04-02_transport_task_file_contracts.md)、[04-03_machine_contract_governance.md](04-03_machine_contract_governance.md) | `05_application_use_cases.md`、`08_security_permissions.md`、`09_quality_observability.md` | P0 主文定义公共协议，04-01 定义操作字段/用例，04-02 定义任务/SSE/文件；机器契约覆盖及维护入口见04；历史决策见 API 工作单，新核心未实现。 |
| Application Use Cases / 应用编排 | `05_application_use_cases.md`、[05-01_internal_module_contracts.md](05-01_internal_module_contracts.md) | `02_domain_core.md`、`04_api_contracts.md`、`06_agent_knowledge_services.md`、`08_security_permissions.md` | 定义命令/查询、状态推进、任务提交、锁、幂等和失败诊断；05-01 明确模块写入归属、内部类型及结果提交责任。 |
| Agent & Knowledge Services | `06_agent_knowledge_services.md` | `02_domain_core.md`、`05_application_use_cases.md`、`07_data_persistence.md` | 定义 Construction、Research、Review、Graph-RAG、Knowledge Version、引用证据等服务能力。 |
| Infrastructure / Data Persistence | `07_data_persistence.md` | `06_agent_knowledge_services.md`、`10_operations_deployment.md` | 定义逻辑记录、约束、发布/回收与迁移协议；SQL草案已删除，可执行结构后续由迁移维护。 |
| Security / Permissions | `08_security_permissions.md`、[08-01_agent_data_access_policy.md](08-01_agent_data_access_policy.md) | `02_domain_core.md`、`04_api_contracts.md`、`05_application_use_cases.md` | 定义授权矩阵、检查时机、数据流与不可信内容边界；Provider/凭据规则见08 §12；资料策略已确认，规则及剩余接入单列08-01，不复制策略细节。 |
| Quality / Observability | `09_quality_observability.md` | `04_api_contracts.md`、`05_application_use_cases.md`、`10_operations_deployment.md` | 按ARC架构级/MOD功能模块级组织测试，以SEC/OPS场景细化安全和交付，保留最小隔离、诊断及证据要求。 |
| Operations / Deployment | `10_operations_deployment.md` | `07_data_persistence.md`、`09_quality_observability.md` | 保留部署隔离、配置契约、可重复构建与交付证据、升级恢复和失败处置；运行目标单列10 §9。 |

### 选型参考（编号顺序）

| 参考领域 | 参考文件 | 定位 |
| --- | --- | --- |
| Graph-RAG / Agent Memory | [013-graph-choose.md](013-graph-choose.md) | 13 号技术选型参考；仅候选、尚未采纳，不定义现行要求 |

## 2. 维护规则

- 本文件只登记当前 `docs/design/` 下实际存在、纳入公开导航的顶层设计文件；受控内部参考不因完整性检查而新增公开入口。
- 对应表按主要设计文件编号数值升序排列；同组主文先于派生索引、速查和附录，附属按子编号升序，协作引用按职责需要保留。选型参考单列，不提升为现行契约。
- 新增、删除或重命名设计文件时，必须同步更新本文件及必要导航；`00_layers.md` 通过本映射引用文件结构，不再维护重复对应表。
- 若某一层的职责发生变化，应先更新 `00_layers.md` 的分层说明，再更新本文件的映射。

## 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|---------|--------|
| v1.0 | 2026-05-22 | 新建层级与当前设计文件对应表 | Codex |
| v1.1 | 2026-10-16 | 登记知识库并行构建与版本更新领域附录 | Codex |
| v1.2 | 2026-10-16 | 登记构建资产与运行恢复领域附录，明确专题详细规则和主文接口索引的职责 | Codex |
| v1.3 | 2026-10-16 | 登记四份 UI 模块附录，明确 Shell 主文、模块细节及业务规则来源 | Codex |
| v1.4 | 2026-10-16 | 明确编号与主文/附属导航顺序，统一 01-01、02-01 派生速查的组内导航，登记 12-00 和单列 13 号候选参考，保持受控参考边界 | Codex |
| v1.5 | 2026-10-16 | 登记 P0 操作与传输附录，明确 API 单点维护与未决边界 | Codex |

本次修订 v1.6（2026-10-19）：登记内部模块契约与 API 机器契约导航，区分现行规范、局部细化和未实现边界。

本次修订（2026-10-19）：同步数据设计、测试用例入口及历史归档引用；不修改业务语义。

本次修订 v1.8（2026-10-19）：同步安全和运行交付职责细化及SEC/OPS测试入口。

本次修订 v1.9（2026-10-20）：登记08-01独立专题，不改变分层职责。

本次修订（2026-10-21）：同步资料策略Q1–Q4已确认决定与双向立即生效，详细规则在08-01维护；接口与运行验证未完成。
