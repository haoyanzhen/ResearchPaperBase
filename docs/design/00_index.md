# Research Paper Base 分层设计总览

文档版本：v0.1
更新日期：2026-04-28
用途：按照 `01_design_layer_template.md` 对现有设计文档进行结构重整，作为后续修订入口。

## 0. 文档控制

现有设计文档职责重整如下：

| 分层 | 当前承载文档 | 权威性说明 |
| --- | --- | --- |
| 产品与领域层 | `02_product_requirements.md`, `03_architecture_decisions.md` | `02_product_requirements.md` 定义 FR；`03_architecture_decisions.md` 定义顶层架构意图 |
| 信息架构与用户流程层 | `04_information_architecture_ui.md`, `02_product_requirements.md` | `04_information_architecture_ui.md` 定义页面与路由；`02_product_requirements.md` 定义业务入口条件 |
| 状态机与业务流程层 | `05_state_workflow.md`, `03_architecture_decisions.md`, `02_product_requirements.md`, `06_data_model.sql`, `07_api_contract.md` | `05_state_workflow.md` 为占位入口；状态枚举应以 `06_data_model.sql` 为准，待人工确认 |
| 数据模型层 | `06_data_model.sql`, `06_data_requirements.md` | `06_data_model.sql` 自声明为数据层唯一权威契约；`06_data_requirements.md` 承载解释性数据需求 |
| API 契约层 | `07_api_contract.md`, `09_quality_observability.md` | `07_api_contract.md` 是接口入口，但响应结构和错误码需统一 |
| UI 与交互层 | `04_information_architecture_ui.md` | 页面草稿完整度较高，但视觉系统、响应式、可访问性缺失 |
| 权限与安全层 | `08_security_permissions.md`, `02_product_requirements.md`, `07_api_contract.md`, `06_data_model.sql`, `09_quality_observability.md` | `08_security_permissions.md` 为占位入口；有用户隔离和管理员规则，但缺少完整权限矩阵 |
| 质量与可观测层 | `09_quality_observability.md` | 错误信封、健康检查、测试策略较完整，但含实现状态描述 |
| 运维部署与演进层 | `10_operations_deployment.md`, `02_product_requirements.md`, `../file_map.md` | `10_operations_deployment.md` 为占位入口；运行环境有描述，部署/迁移/备份设计不足 |

文档修订原则：

- 数据字段、枚举、约束冲突时，先以 `06_data_model.sql` 为候选权威。
- API 请求/响应冲突时，以人工确认后的 `07_api_contract.md` 修订版作为权威。
- 需求含义以 `02_product_requirements.md` 为权威，但 `02_product_requirements.md` 不应重复定义可由 API/DB 约束表达的细节。
- 架构意图以 `03_architecture_decisions.md` 为权威，特别是三模式互斥、深度研究只读约定、RAG 数据库分层。
- QA 只定义验证和诊断机制，不应作为业务字段或接口最终来源。

## 1. 产品与领域层

来源：`02_product_requirements.md` §1~§3、`03_architecture_decisions.md`。

产品目标：

- 构建课题组级学术论文研究平台。
- 以 Project 为核心单元，支持构建、深度研究、综述三种互斥模式。
- 为研究人员提供文献收集、Graph-RAG 深度探讨、综述撰写和推荐分享能力。

用户角色：

| 角色 | 需求 | 关键权限 |
| --- | --- | --- |
| 学术研究人员 | 自动收集和分析论文、对话研究、生成综述 | 管理自己的项目与数据 |
| 研究生 | 快速理解领域文献、整理研究历史 | 管理自己的项目与数据 |
| 科研团队成员 | 共享观点和洞察 | 发布推荐内容、查看公开推荐 |
| 系统管理员 | 维护系统配置和账号 | 管理系统默认配置、用户账号、系统邮件 |

核心实体：

- `users`
- `projects`
- `papers`
- `project_paper_relations`
- `keywords`
- `stage_records`
- `research_dialogues`
- `dialogue_turns`
- `review_outlines`
- `review_chapters`
- `recommendations`
- `user_configs`
- `system_configs`

系统模式：

| 模式 | 目标 | Agent 形态 | 数据写入 |
| --- | --- | --- | --- |
| 构建模式 | 检索、筛选、下载、解析、分析、入库、邮件推送 | 线性七阶段流水线 | 写论文库、向量库、图谱 |
| 深度研究模式 | 基于已有论文库做 Graph-RAG 对话 | 持续对话循环 | 只写对话记录，不写论文库和图谱 |
| 综述模式 | 生成大纲、章节、审查、汇总导出 | 分阶段审查工作流 | 写综述大纲、章节、汇总结果 |

非目标或限制：

- 推荐模块禁止评论、回复、讨论和实时聊天。
- 深度研究模式不负责建立或更新论文库、向量库、图谱。
- Project 同一时间只能处于一种模式。

待确认：

- 管理员是否可以读取普通用户项目内容，还是仅管理账号与系统配置。
- 推荐内容是否需要管理员审核后才公开，还是默认公开后可隐藏。

## 2. 信息架构与用户流程层

来源：`04_information_architecture_ui.md`、`02_product_requirements.md` FR-005/FR-010/FR-019。

当前路由结构：

| 路由 | 页面 |
| --- | --- |
| `/login` | 登录 / 注册 |
| `/projects` | 项目列表 |
| `/projects/:projectId` | 构建模式工作台 |
| `/projects/:projectId/dialogue` | 深度研究工作台 |
| `/projects/:projectId/review` | 综述工作台 |
| `/settings` | 普通用户和管理员设置 |
| `/settings/health` | 健康检查 |

全局布局：

- Topbar：Logo、当前项目、模式切换、设置、头像。
- Sidebar：随当前模式切换导航项。
- Content Area：渲染当前页面或当前工作台阶段。

核心用户流程：

1. 注册/登录。
2. 创建 Project，默认进入构建模式。
3. 配置 LLM、学术数据库、邮件收件人；管理员配置系统默认项。
4. 启动构建流程，按阶段审查结果。
5. 构建完成后进入深度研究或综述模式。
6. 在深度研究中创建对话、发送问题、查看引用和图谱。
7. 在综述模式中确认课题扩写、大纲、章节、审查结果并导出。
8. 可发布推荐内容供他人查看。

模式切换入口条件：

- 当前项目 `valid_papers = 0` 时，不允许进入深度研究或综述模式。
- 当前项目有运行中任务时，必须先确认继续等待或取消任务。
- 切换不应删除已有对话、综述草稿或阶段记录。

待确认：

- “取消任务后切换”是取消当前 stage、整条 pipeline，还是标记项目回到 `idle`。
- 论文库为空时“返回构建模式”应跳转到阶段 1，还是最新可恢复阶段。
- 当前 UI 文档中存在深度研究图谱重建入口，需决定是否移除。

## 3. 状态机与业务流程层

来源：`05_state_workflow.md`、`03_architecture_decisions.md`、`02_product_requirements.md`、`06_data_model.sql`、`07_api_contract.md`。

### 3.1 Project 模式

候选权威：`06_data_model.sql`。

| 字段 | 枚举 |
| --- | --- |
| `projects.mode` | `construction` / `deep_research` / `review` |

规则：

- 每个 Project 必须且只能处于一个 mode。
- mode 切换不清空各模式历史数据。
- 深度研究对话期间不改变 `projects.status`。

### 3.2 Project 状态

候选权威：`06_data_model.sql`。

| 状态 | 含义 |
| --- | --- |
| `idle` | 无活动任务 |
| `running` | 构建或综述阶段任务正在执行 |
| `paused` | 阶段完成，等待用户交互 |
| `error` | 任务失败，需要用户介入 |
| `archived` | 项目归档，禁止新任务 |

当前冲突：

- `07_api_contract.md` 示例仍包含 `draft`、`completed`、`cancelled`。
- `/tasks` 接口的状态与 Project/Stage 状态边界不清。

### 3.3 Stage 状态

候选权威：`06_data_model.sql`。

| 字段 | 枚举 |
| --- | --- |
| `stage_records.status` | `running` / `paused` / `completed` / `failed` |

构建模式阶段：

1. 检索词生成
2. 检索与汇总
3. 评分与筛选
4. 下载与解析
5. 总结生成
6. 格式化与储存
7. 邮件发送

综述模式阶段：

1. 扩写课题内容
2. 生成综述架构
3. 撰写章节内容
4. 自动审查迭代
5. 汇总成综述文章

当前冲突：

- `02_product_requirements.md` FR-019 禁止跳过阶段。
- `07_api_contract.md` 和 `04_information_architecture_ui.md` 仍保留 `skip`。

### 3.4 异步任务

当前设计：

- `07_api_contract.md` 有 `/tasks` 接口。
- `06_data_model.sql` 无独立 `tasks` 表。
- `stage_records` 记录构建/综述阶段。

待确认：

- 是否把 `stage_records.id` 作为 task_id。
- 是否新增独立 `tasks` 表来表达 pipeline、调度、取消、暂停和导出任务。
- 导出、图谱重建、邮件重发是否也纳入统一任务模型。

## 4. 数据模型层

来源：`06_data_model.sql` 为权威，`06_data_requirements.md` 作为解释性数据需求与多数据库协同说明。

数据设计原则：

- 用户是顶层隔离单元。
- Project 是系统核心业务单元。
- `papers` 全局去重共享。
- 课题相关评分、有效性、推送状态存储在 `project_paper_relations`。
- 构建模式维护 PostgreSQL、ChromaDB、NetworkX。
- 深度研究和综述只读论文库；综述写自己的大纲和章节。

核心表分组：

| 分组 | 表 |
| --- | --- |
| 用户与配置 | `users`, `user_configs`, `system_configs` |
| 项目与构建 | `projects`, `keywords`, `stage_records` |
| 论文库 | `papers`, `project_paper_relations` |
| 深度研究 | `research_dialogues`, `dialogue_turns` |
| 综述 | `review_outlines`, `review_chapters` |
| 推荐 | `recommendations` |

删除语义：

- 删除用户：级联删除该用户所有项目、配置、推荐等用户数据。
- 从课题移除论文：删除 `project_paper_relations`，不删除全局 `papers`。
- 删除 Project：级联删除项目下关联、阶段、对话、综述等。
- `papers` 不因某个 Project 移除关联而被删除。

一致性设计：

- PostgreSQL 与 ChromaDB 被要求强一致。
- NetworkX 图谱最终一致。

待确认：

- ChromaDB 不能自然参与 PostgreSQL 事务，需选择 outbox/补偿/两阶段提交等实现策略。
- 文件系统中的 PDF、文本、导出产物、GraphML 是否随 DB 删除清理。
- `user_configs.is_system_default` 与 `system_configs` 是否保留两套系统默认配置语义。
- 推荐点赞是否需要新增用户点赞关系表。
- 综述完整文章版本是否需要新增版本表。

## 5. API 契约层

来源：`07_api_contract.md`，但需修订为单一 OpenAPI 契约。

当前模块：

| 模块 | 端点范围 |
| --- | --- |
| 认证 | `/auth/register`, `/auth/login`, `/auth/logout`, `/auth/me` |
| 配置 | `/config/llm`, `/config/databases`, `/config/email` |
| 项目 | `/projects`, `/projects/{id}/mode` |
| 构建 | `/projects/{id}/construction/*` |
| 论文 | `/projects/{id}/papers/*` |
| 深度研究 | `/projects/{id}/dialogues/*`, `/projects/{id}/graph` |
| 综述 | `/projects/{id}/review/*` |
| 任务 | `/tasks/*` |
| 推荐 | `/recommendations/*` |
| 管理员 | `/admin/*` |

统一响应待确认：

当前 `07_api_contract.md` 总体约定使用：

```json
{
  "code": 0,
  "data": {},
  "message": "ok"
}
```

但接口示例大多返回裸对象。需决定：

- 方案 A：所有 REST 返回统一 envelope。
- 方案 B：成功返回裸对象，错误返回统一错误对象。

错误码待确认：

- `07_api_contract.md` 使用数字码。
- `09_quality_observability.md` 使用 `ERR-*` 字符串错误码。

SSE 待确认：

- 浏览器原生 `EventSource` 无法携带 Authorization header。
- 需要选择 Cookie、短期 stream token、或 `fetch` readable stream。

缺失 API：

- 密码找回。
- 项目级定时配置。
- 论文库 Excel / PDF ZIP 导出。
- 邮件手动重发。
- 管理员用户管理。
- 系统级 LLM/数据库默认配置。
- 推荐审核。
- 综述版本 diff/rollback/delete/merge。
- 深度研究总结历史、范围总结、导出。

## 6. UI 与交互层

来源：`04_information_architecture_ui.md`。

页面分组：

| 分组 | 页面 |
| --- | --- |
| 入口 | 登录/注册、项目列表 |
| 全局 | 设置、健康检查、Inspector |
| 构建模式 | 构建阶段、评分详情、论文库、定时设置 |
| 深度研究 | 对话、知识图谱、研究历史 |
| 综述模式 | 综述大纲、章节撰写、汇总导出、版本管理 |
| 推荐 | 推荐广场、发布观点 |

现有 UI 设计状态：

- 主要页面线框已经存在。
- 部分页面在 `04_information_architecture_ui.md` 中标注为未实现或部分实现。
- 当前文档存在实现状态描述，后续建议移入实现进度文档，避免 UI 设计和实现记录混杂。

待确认：

- 是否移除构建阶段 `[跳过]` 按钮。
- 是否移除深度研究知识图谱 `[重建图谱]` 按钮。
- 论文库导出按钮应为 Excel/PDF ZIP，当前线框仍有 CSV。
- 推荐模块 UI 是否纳入当前版本。
- Inspector fatal 错误是否需要全屏遮罩。

缺失设计：

- 响应式断点。
- 设计 token。
- 表单校验文案。
- 空态、加载态、错误态、权限态。
- 可访问性规则。

## 7. 权限与安全层

来源：`08_security_permissions.md`、`02_product_requirements.md`、`06_data_model.sql`、`07_api_contract.md`、`09_quality_observability.md`。

已有规则：

- 除登录/注册外接口需要 JWT。
- 用户只能访问自己的项目和项目数据。
- 首位注册用户自动成为管理员。
- 管理员可以维护系统级配置和用户账号。
- 普通用户访问管理员接口返回 403。
- 管理员不能删除或禁用自己。
- 至少保留一个管理员。
- API key 和邮件密码不应明文返回。

待确认权限矩阵：

| 资源 | 普通用户 | 项目所有者 | 管理员 | 待确认 |
| --- | --- | --- | --- | --- |
| 自己账号 | 读/改 | 读/改 | 可管理其他账号 | 管理员是否可改邮箱 |
| Project | 仅自己的 | CRUD | 是否可查看全部 | 管理员项目可见性 |
| 论文关联 | 仅自己的项目 | CRUD 关联 | 是否可维护 | 管理员数据边界 |
| 系统配置 | 不可写 | 不可写 | CRUD | 变更审计 |
| 推荐内容 | 创建/删自己的 | 创建/删自己的 | 审核/隐藏 | 默认是否公开 |
| 导出文件 | 仅自己的 | 下载自己的 | 是否可下载全部 | 下载审计 |

缺失设计：

- 账号禁用后已签发 token 是否立即失效。
- 404 防枚举与 403 权限不足的统一策略。
- 密钥加密算法和密钥轮换。
- 审计日志字段。
- SSE 认证安全方案。

## 8. 质量、测试与可观测层

来源：`09_quality_observability.md`。

已有设计：

- 分层诊断协议。
- 结构化错误信封 ErrorEnvelope。
- 构建/综述 SSE 错误事件。
- 深度研究 SSE `error` 事件。
- `/health`, `/health/db`, `/health/deep`, `/health/pipeline`。
- `/projects/{id}/inspect` 诊断快照。
- 单元、集成、契约、E2E 测试策略。
- Inspector Panel。
- 结构化日志规范。

待整理：

- `09_quality_observability.md` 同时包含设计规范和实现现状，建议拆分为：
  - `09_quality_observability.md`：规范。
  - `implementation_status.md`：实现进度。
- 附录 B 中多处写“待实现”，但文档前文又写“已实现”，需统一口径。

待确认：

- REST 错误是否也使用 ErrorEnvelope。
- 错误严重级别是否进入 API 契约。
- Inspector 是否负责操作按钮，还是只负责展示诊断。

## 9. 运维、部署与演进层

来源：`10_operations_deployment.md`、`02_product_requirements.md` 运行环境、`../file_map.md` 实现目录说明。

已有内容：

- 客户端浏览器版本要求。
- 服务端 OS、Python、内存、存储、网络要求。
- 技术栈：React、TypeScript、FastAPI、LangGraph、PostgreSQL、ChromaDB、NetworkX。
- `file_map.md` 描述了后端、前端、测试、迁移、脚本等实际文件职责。

缺失设计：

- `.env` 完整说明和安全要求。
- Docker Compose 或部署步骤。
- PostgreSQL/ChromaDB/文件存储/GraphML 启动和备份。
- Alembic 迁移流程和回滚。
- 定时任务部署形态。
- 日志采集和告警。
- 容量估算。

## 10. 追踪矩阵

当前建议用以下矩阵修订设计文档：

| FR | 产品层 | 流程/状态 | 数据 | API | UI | 权限 | QA | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FR-001 | 已有 | 部分 | 已有 | 部分 | 已有 | 部分 | 部分 | 待补密码找回 |
| FR-002 | 已有 | 部分 | 已有 | 部分 | 已有 | 部分 | 部分 | 待补系统级 LLM |
| FR-003 | 已有 | 部分 | 已有 | 部分 | 已有 | 部分 | 部分 | 待补系统级数据库 |
| FR-004 | 已有 | 部分 | 已有 | 部分 | 已有 | 部分 | 部分 | 待补模板管理 |
| FR-005 | 已有 | 冲突 | 已有 | 冲突 | 部分 | 部分 | 已有 | 待统一状态 |
| FR-006 | 已有 | 部分 | 部分 | 缺失 | 部分 | 部分 | 部分 | 待补历史 API |
| FR-007 | 已有 | 部分 | 已有 | 部分 | 部分 | 部分 | 部分 | 待补清空关联 |
| FR-008 | 已有 | 缺失 | 缺失 | 部分 | 部分 | 部分 | 部分 | 待定任务模型 |
| FR-009 | 已有 | 缺失 | 缺失 | 缺失 | 部分 | 部分 | 部分 | 待补导出 |
| FR-010 | 已有 | 部分 | 已有 | 缺失 | 已有 | 部分 | 部分 | 待补调度 API |
| FR-011 | 已有 | 部分 | 部分 | 部分 | 缺失 | 部分 | 部分 | 待补审核/点赞 |
| FR-012~019 | 已有 | 部分冲突 | 已有 | 部分冲突 | 部分冲突 | 部分 | 已有 | 待统一 skip/事务 |
| FR-020~024 | 已有 | 部分 | 部分 | 部分 | 部分 | 部分 | 部分 | 待补版本管理 |
| FR-025~028 | 已有 | 部分冲突 | 部分 | 部分冲突 | 部分冲突 | 部分 | 已有 | 待统一图谱/SSE/总结 |
| FR-029 | 已有 | 部分 | 部分 | 缺失 | 部分 | 部分 | 部分 | 待补管理员接口 |

## 11. 下一步修订建议

建议按以下顺序修订原始文档：

1. 先在 `12_gap_decisions.md` 中确认所有待决策项。
2. 再更新 `07_api_contract.md`，统一响应 envelope、错误码、SSE 认证、缺失端点。
3. 更新 `04_information_architecture_ui.md`，删除或调整与确认结果冲突的按钮和页面状态。
4. 更新 `02_product_requirements.md`，保留需求和验收，不重复定义已由 DB/API 承担的字段细节。
5. 更新 `05_state_workflow.md`、`08_security_permissions.md`、`10_operations_deployment.md`，补齐当前占位层。
6. 更新 `06_data_model.sql`，只在需要新增表或约束时变更。
7. 更新 `09_quality_observability.md`，让测试和诊断对齐最终契约。
