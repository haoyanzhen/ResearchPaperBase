# Research Paper Base 设计文档集

文档版本：v1.4
更新日期：2026-10-16
适用项目大版本：v1  
权威基线：`01_functional_requirements.md`、`00_layers.md`

## 1. 权威性规则

1. `01_functional_requirements.md` 是需求含义、优先级和验收标准的最高依据。
2. `00_layers.md` 是当前架构分层、依赖方向和横切约束的基础蓝本。
3. `02_domain_core.md` 与 `02-02`、`02-03`、`02-04` 专题附录按相同设计规格共同展开领域规则，`03` 与 `03-01` 至 `03-04` 附录共同定义 UI，主文和附录具有相同 UI 规范效力，业务规则以 `01`、`02` 及其领域附录为准；`04` 及以后仍为待细化草案，本轮局部纠偏不代表其已定稿。若发生冲突，按 `01_functional_requirements.md` 裁决，并回写修订到相关设计文件。
4. 历史审计文件 `11_design_audit.md` 已废弃，不再迁入新版设计集。
5. 旧式大接口清单、质量控制和数据模型仅保留在 `backup/` 目录作为参考，不作为权威契约。
6. 旧 `12_gap_decisions.md` 的逐项审核结果见 `12_gap_decisions_review.md`；未关闭项应回写到对应新版设计文件。

## 2. 文件结构

| 文件 | 分层定位 | 主要回答 |
| --- | --- | --- |
| `00_layers.md` | 总览 | 系统分几层、层间如何依赖、横切约束是什么 |
| `01_functional_requirements.md` | 需求基线 | 系统必须满足哪些功能、优先级和验收标准 |
| [02_domain_core.md](02_domain_core.md) | Domain Core | 聚合边界、跨模块接口、通用领域规则与专题附件索引 |
| [02-01-domain-reference.md](02-01-domain-reference.md) | Domain 派生速查 | 聚合、对象、链路与 FR 映射；不定义独立规则 |
| [02-02_construction_versioning_appendix.md](02-02_construction_versioning_appendix.md) | Domain Core 专题附录 | 知识库版本对象、生命周期、发布、构建槽、并行构建、版本采用、确认和冲突裁决的详细规则 |
| [02-03_construction_assets_appendix.md](02-03_construction_assets_appendix.md) | Domain Core 专题附录 | Construction 检索输入、论文与资料身份、去重、筛选、手动补充、解析和分析确认 |
| [02-04_run_recovery_appendix.md](02-04_run_recovery_appendix.md) | Domain Core 专题附录 | 重试、重连、重跑、断点、临时产物清理与回复恢复 |
| [03_ui_workspace.md](03_ui_workspace.md) | UI / Workspace 主文 | 全局导航、Shell 布局组合、跨模块约束、分期和验收要求 |
| [03-01_ui_system_pages_appendix.md](03-01_ui_system_pages_appendix.md) | UI 系统页面附录 | 认证、Project Hub、个人和管理员设置 |
| [03-02_ui_construction_appendix.md](03-02_ui_construction_appendix.md) | UI Construction 附录 | 构建配置、运行步骤、补充请求和构建流程 |
| [03-03_ui_research_review_appendix.md](03-03_ui_research_review_appendix.md) | UI Research / Review 附录 | 研究会话、综述架构、章节编辑和生成流程 |
| [03-04_ui_shared_interactions_appendix.md](03-04_ui_shared_interactions_appendix.md) | UI 共用交互附录 | 知识资产面板、知识更新、冲突确认、恢复和对象切换 |
| `04_api_contracts.md` | API Boundary | HTTP/SSE/API 错误信封、资源命名、权限前置和端点骨架 |
| `05_application_use_cases.md` | Application Use Cases | 写操作入口、业务流程、状态推进、锁、配置快照和幂等 |
| `06_agent_knowledge_services.md` | Agent & Knowledge Services | Construction、Research、Review Agent 与 Knowledge 能力边界 |
| `07_data_persistence.md` | Infrastructure / Data | 关系库、文件、向量、图谱、版本和同步状态的持久化设计 |
| `07_data_schema.sql` | Infrastructure / Data | MVP 关系数据结构草案，供迁移实现参考 |
| `08_security_permissions.md` | AuthZ 横切约束 | 用户隔离、管理员边界、文件访问、密钥和审计 |
| `09_quality_observability.md` | Quality 横切约束 | 测试入口、错误分类、日志、健康检查和诊断快照 |
| `10_operations_deployment.md` | Operations | 本地/MVP 部署、调度、队列、备份、容量和演进策略 |
| `12_gap_decisions_review.md` | 迁移审核 | 依据旧 `12_gap_decisions.md` 逐项核对新版设计吸收情况 |
| [UI 历史评审](../proposals/ui_design_historical_review_2026-06-01.md) | 历史记录 | 原 UI 第 10 章评审，仅供追溯，不定义现行规范 |
| `backup/` | 备份参考 | 旧 API 契约、质量控制、数据模型和数据需求，仅供查证 |

## 3. 阅读顺序

新任务优先阅读：

1. `01_functional_requirements.md`
2. `00_layers.md`
3. 与任务所属层对应的设计文件
4. `04_api_contracts.md`、`08_security_permissions.md`、`09_quality_observability.md` 中的横切要求

Domain 任务先由主文定位边界，再按专题阅读附件：知识库版本读 `02-02`，构建资产入库读 `02-03`，运行恢复读 `02-04`。附件与主文具有相同领域规范效力；详细规则只在对应附件维护，主文及其他模块通过索引和接口承接，`02-01` 仅作派生速查。

UI 任务先阅读 [主文](03_ui_workspace.md) 的 Shell 布局组合和跨模块约束，再按模块进入 `03-01` 至 `03-04`。附录是详细 UI 规则的唯一维护位置，保留原 P 编号供追踪；主文不重复维护模块线框与交互。历史评审单独保存在 `docs/proposals/`。

## 4. 修订要求

- 所有设计文件保持项目大版本 `v1.x`。
- 设计文档只描述稳定边界、流程、规则和骨架；字段枚举和端点细节可随实现补充，但不得违背 FR。
- P0/P1 需求必须能追踪到 UI 入口、应用用例、领域/Agent 规则、数据写入、权限检查和测试入口。
