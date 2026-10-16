# 项目文件功能目录

**文档版本**：v1.12 · 2026-10-16（登记项目状态历史附件）
**维护规则**：新增或删除文件时同步更新；历史文档中的原路径仅作来源记录。

## 当前目录

- `docs/design/`：现行设计、草案及历史参考；不是运行代码。
- `docs/proposals/`：重构计划与独立审查。
- `docs/workorders/`：执行记录及逐文件清理清单。
- `archive/maybe_useful/`：唯一留存的代码候选与离线测试；没有应用入口。
- `tasks/`、`docs/VibeCodingRecord/`、本地 `auto-check/`：历史任务/学习资料。
- `AGENTS.md`、`LICENSE`：项目约束与许可。

旧 `backend/`、`frontend/`、`e2e/` 及本地依赖环境已删除。未启动新核心实现。

## docs/ — 契约文档

### 项目与设计入口

| 文件 | 职责 |
|------|------|
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | 项目进度与待完成项统一入口；汇总当前状态、开放决策、延期事项、关闭条件和证据 |
| [PROJECT_STATUS_APPENDIX.md](PROJECT_STATUS_APPENDIX.md) | 项目状态附件；保存已收口事项细节、历轮验证和主文件修改记录 |
| [design/README.md](design/README.md) | 分层设计文档集入口；说明权威性、文件结构和阅读顺序 |
| [file_map.md](file_map.md) | **本文件**；项目文件功能目录 |

### 设计文件（编号顺序）

同组主文件在前，派生索引、速查及附录按子编号升序排列；同号持久化设计主文在 SQL 草案之前。参考候选与历史资料另列，不改变文档权威性。

| 文件 | 职责 |
|------|------|
| [design/00_layers.md](design/00_layers.md) | 分层总览；定义架构边界、依赖方向与横切约束 |
| [design/00-00_layer_design_file_mapping.md](design/00-00_layer_design_file_mapping.md) | 分层文件映射；定位现行设计文件 |
| [design/01_functional_requirements.md](design/01_functional_requirements.md) | 现行功能需求基线；需求含义、优先级和验收以本需求正文为准 |
| [design/01-01-FR-reference.md](design/01-01-FR-reference.md) | FR 派生速查；不定义独立需求规则 |
| [design/02_domain_core.md](design/02_domain_core.md) | Domain 主文；聚合边界、模块接口、通用规则与专题附录索引 |
| [design/02-01-domain-reference.md](design/02-01-domain-reference.md) | Domain 派生速查；聚合、对象、链路与 FR 映射，不定义独立规则 |
| [design/02-02_construction_versioning_appendix.md](design/02-02_construction_versioning_appendix.md) | Domain 规范附录；知识库版本详细规则的统一来源，覆盖对象、生命周期、发布、构建槽、并行构建、版本采用、确认和冲突裁决 |
| [design/02-03_construction_assets_appendix.md](design/02-03_construction_assets_appendix.md) | Domain 规范附录；Construction 检索输入、身份与去重、筛选、手动补充、解析和分析确认 |
| [design/02-04_run_recovery_appendix.md](design/02-04_run_recovery_appendix.md) | Domain 规范附录；运行重试、重连、重跑、断点、清理与回复恢复 |
| [design/03_ui_workspace.md](design/03_ui_workspace.md) | UI 主文；全局导航、Shell 布局组合、跨模块约束、分期和验收要求；与四份 UI 附录具有相同规范效力，业务规则以 01/02 为准 |
| [design/03-01_ui_system_pages_appendix.md](design/03-01_ui_system_pages_appendix.md) | UI 系统页面规范；认证、Project Hub、个人及管理员设置 |
| [design/03-02_ui_construction_appendix.md](design/03-02_ui_construction_appendix.md) | UI 构建规范；配置、运行步骤、补充请求和构建流程 |
| [design/03-03_ui_research_review_appendix.md](design/03-03_ui_research_review_appendix.md) | UI 研究与综述规范；研究会话、综述架构、章节编辑和生成流程 |
| [design/03-04_ui_shared_interactions_appendix.md](design/03-04_ui_shared_interactions_appendix.md) | UI 共用交互规范；知识资产、知识更新、冲突确认、恢复和对象切换 |
| [design/04_api_contracts.md](design/04_api_contracts.md) | P0 API 公共协议；认证、信封、修订/确认、幂等、错误与分期，未决分支不视为定稿 |
| [design/04-01_p0_operation_contracts.md](design/04-01_p0_operation_contracts.md) | P0 操作附录；请求响应、具名用例及验收入口 |
| [design/04-02_transport_task_file_contracts.md](design/04-02_transport_task_file_contracts.md) | 任务/SSE/文件附录；技术投影、回放、上传下载与限制 |
| [design/05_application_use_cases.md](design/05_application_use_cases.md) | 应用用例设计；衔接 P0 受理/提交、锁、幂等、内容保护与状态；未决分支及后续恢复保持待细化，领域规则由 Domain 规范定义 |
| [design/06_agent_knowledge_services.md](design/06_agent_knowledge_services.md) | Agent 与 Knowledge 服务草案；Construction、Research、Review Agent 与 Knowledge 能力边界 |
| [design/07_data_persistence.md](design/07_data_persistence.md) | 现行持久化设计草案；关系库、文件、向量、图谱、版本及同步状态，不能反向定义领域规则 |
| [design/07_data_schema.sql](design/07_data_schema.sql) | MVP 关系数据结构 SQL 草案；供迁移实现参考，不作为已实施证明 |
| [design/08_security_permissions.md](design/08_security_permissions.md) | 权限与安全草案；本轮同步 P0 API 认证/文件/管理员边界，完整安全设计和实现仍待后续 |
| [design/09_quality_observability.md](design/09_quality_observability.md) | QA 与可观测层；错误码体系、结构化错误信封、SSE 错误事件协议、健康检查、诊断快照、测试策略、Inspector Panel |
| [design/10_operations_deployment.md](design/10_operations_deployment.md) | 运维部署与演进层；占位文档，待补环境变量、部署拓扑、迁移、备份恢复、监控告警和版本演进 |
| [design/12_gap_decisions_review.md](design/12_gap_decisions_review.md) | 旧决策迁移审核；不等同于旧决策全文或实现完成证明 |
| [design/12-00_gap_downstream_reference.md](design/12-00_gap_downstream_reference.md) | 12 号审核的下游待细化参考项；不表示已完成实现 |

### 选型参考（编号顺序）

| 文件 | 职责 |
|------|------|
| [design/013-graph-choose.md](design/013-graph-choose.md) | 13 号 Graph-RAG / Agent Memory 技术选型参考；仅候选、尚未采纳，不定义现行要求 |

### 历史资料、备份与附图

| 文件 | 职责 |
|------|------|
| [workorders/api_p0_design_review_2026-10-16.md](workorders/api_p0_design_review_2026-10-16.md) | 本轮 API 独立预案、主代理评审、未决业务项及文档检查证据 |
| [proposals/ui_design_historical_review_2026-06-01.md](proposals/ui_design_historical_review_2026-06-01.md) | 原 UI 第 10 章历史评审；仅供追溯，不定义现行规范 |
| [design/backup/06_data_requirements.backup.md](design/backup/06_data_requirements.backup.md) / [design/backup/06_data_model.backup.sql](design/backup/06_data_model.backup.sql) | 历史数据需求与 SQL 备份；仅供追溯，不作为现行权威契约 |
| [design/backup/07_api_contract.backup.md](design/backup/07_api_contract.backup.md) | 旧详细 API 契约备份；仅供追溯，不作为现行权威契约 |
| [design/backup/09_quality_observability.backup.md](design/backup/09_quality_observability.backup.md) | 旧质量控制备份；仅供追溯，不作为现行权威契约 |
| [VibeCodingRecord/VibeCoding_record.md](VibeCodingRecord/VibeCoding_record.md) | 开发过程记录；设计演进历史 |
| [media/](media/) | 文档附图（logo、RAG 结构图等） |

---

### 历史入口处理记录

本次核对原目录中的 19 个失效路径：7 个更新路径、3 个保留为历史参考、9 个撤下失效入口。下表保留旧路径及原职责说明；“更新路径”表示现行职责承接，不保证旧文件全文原样迁移。“删除失效入口”仅删除不可用链接，不删除文件或历史说明。当前规范身份以 [设计文档集说明](design/README.md) 为准。

| 旧入口 | 处理分类 | 原职责说明（历史记录） | 现行去向或处理依据 |
| --- | --- | --- | --- |
| `design/01_design_layer_template.md` | 删除失效入口 | Web App Design 分层参考模板；用于简单到复杂 Web App 的产品、流程、状态、数据、API、UI、权限、QA、部署分层设计 | 当前仓库未找到该模板或可确认的等价替代文件；撤下可点击入口，保留原用途记录。 |
| `design/00_index.md` | 更新路径 | 分层设计总览；按层组织当前设计文档群，标记权威来源、冲突点与待确认项 | [design/00_layers.md](design/00_layers.md)。职责由现行分层总览承接；文件定位另见分层文件映射，不表示旧文档内容逐字迁移。 |
| `design/02_product_requirements.md` | 更新路径 | 产品与需求层；需求规格说明书（v1.7）；FR-001~FR-029 完整功能需求；**修改需评审** | [design/01_functional_requirements.md](design/01_functional_requirements.md)。现行需求基线承接；原 v1.7、FR-001~029 是历史版本范围。 |
| `design/03_architecture_decisions.md` | 更新路径 | 架构决策层；核心架构设计、三模式互斥、RAG 数据库分层和关键取舍 | [design/00_layers.md](design/00_layers.md)。现行架构分层由总览承接；原“三模式互斥”仅保留为历史描述，不作为现行约束。 |
| `design/04_information_architecture_ui.md` | 更新路径 | 信息架构与 UI 交互层；ASCII 线框图、路由、页面布局与交互逻辑 | [design/03_ui_workspace.md](design/03_ui_workspace.md)。现行 UI / Workspace 设计承接。 |
| `design/05_state_workflow.md` | 更新路径 | 状态机与业务流程层；占位文档，待补 Project/Stage/Task、调度、取消、暂停、恢复和补偿策略 | [design/05_application_use_cases.md](design/05_application_use_cases.md)。执行编排由应用用例承接；状态含义与不变量由 Domain 主文及专题附录定义，不声称旧占位设计已经全部实现。 |
| `design/06_data_requirements.md` | 保留历史说明 | 数据需求设计；从 `02_product_requirements.md` 迁出的原第 6 章，说明关系库、向量库、图数据库和多数据库协同 | [design/backup/06_data_requirements.backup.md](design/backup/06_data_requirements.backup.md)。旧数据需求仅作为备份参考；现行持久化设计见 design/07_data_persistence.md。 |
| `design/06_data_model.sql` | 保留历史说明 | 数据模型层；PostgreSQL DDL（v1.1）；13 张表结构（含 system\_configs）、索引、约束；**数据层唯一权威** | [design/backup/06_data_model.backup.sql](design/backup/06_data_model.backup.sql)。旧 SQL v1.1 与原“唯一权威”声明属于历史资料；现行 design/07_data_schema.sql 仍是草案，不能据旧目录提升其权威性。 |
| `design/07_api_contract.md` | 更新路径 | API 契约层；所有 HTTP 端点请求/响应格式、前后端接口契约、SSE 通信 | [design/04_api_contracts.md](design/04_api_contracts.md)。现行 API 草案承接；旧详细契约另保存在 design/backup/07_api_contract.backup.md，不表示新草案已经覆盖全部旧端点。 |
| `design/11_design_audit.md` | 删除失效入口 | 设计审计层；评估设计是否足以无额外信息实现完整 Web App，并列出缺失设计 | design/README.md 明确该历史审计已废弃、不再迁入新版设计集；撤下入口，保留原审计用途，不用其他同编号文件替代。 |
| `design/12_gap_decisions.md` | 保留历史说明 | 决策待确认层；基于审计和分层重整生成的缺失设计选择与建议，待人工确认后回写各契约文档 | [design/12_gap_decisions_review.md](design/12_gap_decisions_review.md)。指向旧决策的逐项迁移审核，不将审核文件视为原决策全文；未关闭事项另见下游参考。 |
| `spec.md`、`api.md`、`schema.sql`、`ui_design.md`、`ADR_design.md`、`qa_design.md`、`design_layers.md`（7 个入口） | 删除失效入口 | 兼容旧路径；Markdown 文件为跳转入口，`schema.sql` 为指向 `design/06_data_model.sql` 的符号链接 | 当前工作树不存在这些跳转文件或符号链接，撤下兼容入口声明；按主题分别阅读现行需求、API、SQL、UI、分层总览与质量设计。旧兼容机制仅作为历史记录保留。 |
| `VibeCoding_record.md` | 更新路径 | 开发过程记录；设计演进历史 | [VibeCodingRecord/VibeCoding_record.md](VibeCodingRecord/VibeCoding_record.md)。更新到当前实际保存路径。 |

旧说明中的版本号、FR 范围、“三模式互斥”“数据层唯一权威”和兼容符号链接声明仅反映当时目录状态。下文代码目录及关键路径图保留既有实现说明；其中 `docs/schema.sql`、`docs/api.md`、`docs/spec.md` 等是历史依赖名称，不表示当前仍存在兼容入口，也不据此认定旧实现符合现行设计。

---

## 或许有用的逻辑存档

| 路径 | 职责 |
| --- | --- |
| `archive/maybe_useful/README.md` | 候选存档范围与使用限制 |
| `archive/maybe_useful/agent_logic/` | 解析、字段映射、引用与邮件布局片段及离线验证 |
| `archive/maybe_useful/support_logic/` | 独立辅助片段及身份/配置规则 |
| `archive/maybe_useful/ui_materials/` | 独立展示素材、格式化及有效测试场景 |
| `docs/workorders/legacy_cleanup_manifest_2026-10-16.json` | 删除源文件哈希、留存资产和分类记录 |
| `docs/workorders/legacy_cleanup_execution_2026-10-16.md` | 实际删除范围、验证和剩余限制 |

旧文件职责与路径可通过 Git 历史、重构计划和独立审查追溯。历史设计中的源码路径不代表当前存在对应实现。

## 导航维护变更记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.12 | 2026-10-16 | 增加项目状态历史附件入口 |
| v1.11 | 2026-10-16 | 登记 P0 API 操作/传输附录及审查工作单，同步应用、安全文档定位 |
| v1.10 | 2026-10-16 | 按设计编号与主文/附属顺序整理导航，补齐 06 号服务草案及 13 号候选参考入口，分列项目入口和历史资料；不改变权威性或业务规则 |
