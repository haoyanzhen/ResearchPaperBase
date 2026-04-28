# Web App 设计文档审计报告

审计日期：2026-04-28

审计范围：

- `docs/design/03_architecture_decisions.md`
- `docs/design/02_product_requirements.md`
- `docs/design/07_api_contract.md`
- `docs/design/06_data_model.sql`
- `docs/design/04_information_architecture_ui.md`
- `docs/design/09_quality_observability.md`

## 1. 常规 Web App Design 的分层方式

完整的 Web App 设计通常不是只写页面或接口，而是按以下层次逐层闭环：

| 层级 | 目标 | 必须产物 |
| --- | --- | --- |
| 产品与领域层 | 明确系统做什么、不做什么、核心实体和业务边界 | 目标、角色、核心实体、功能清单、非目标 |
| 信息架构与用户流程层 | 明确用户如何进入、切换、完成任务、退出异常状态 | 路由、导航、状态流转、关键用户旅程、空态/错误态/加载态 |
| UI 交互层 | 明确页面结构、组件行为、表单校验、交互反馈 | 页面线框、组件状态、交互规则、响应式规则、可访问性约束 |
| API 契约层 | 明确前后端通信、请求响应、错误协议、实时通信 | REST/SSE/WebSocket 契约、统一响应、错误码、分页、上传下载 |
| 业务流程层 | 明确服务端如何执行复杂任务 | 工作流阶段、异步任务、重试、取消、幂等、并发控制 |
| 数据层 | 明确持久化模型和数据约束 | SQL schema、索引、约束、迁移策略、数据字典、删除语义 |
| 安全与权限层 | 明确谁能访问和修改什么 | 认证、授权、管理员规则、密钥存储、审计日志、数据隔离 |
| 质量与可观测层 | 明确如何发现、定位、验证问题 | 测试策略、健康检查、错误信封、日志、监控、E2E 验收 |
| 运维与部署层 | 明确系统如何运行、升级和恢复 | 环境变量、依赖服务、启动顺序、备份恢复、迁移流程、CI/CD |

评价一套设计文档是否足够实现完整 Web App，关键不是“有没有很多内容”，而是跨层契约是否一致：同一个字段、状态、接口、权限规则、任务生命周期，在 UI、API、DB、QA 中必须只有一个解释。

## 2. 总体结论

当前文档已经覆盖了核心产品形态、三模式架构、主要数据表、主要页面、主要 API 和 QA 方向，但**不能在没有额外信息的前提下实现完整 Web App**。如果直接按现有文档开发，较大概率会产生状态机冲突、接口实现返工、前端运行时问题和权限/任务边界缺陷。

可直接支撑实现的部分：

- 三模式顶层架构清晰：构建模式、深度研究模式、综述模式互斥。
- 核心数据轴清晰：用户 -> Project -> 论文关联 / 阶段记录 / 对话 / 综述。
- `06_data_model.sql` 对关键实体、约束、删除语义和状态枚举较完整。
- `04_information_architecture_ui.md` 覆盖主要页面和工作台结构。
- `09_quality_observability.md` 对错误信封、健康检查、Inspector 和测试层级有较好方向。

不能直接支撑实现的部分：

- API 文档与 schema/status 约束存在冲突。
- API 文档与需求文档存在缺失和相互矛盾。
- 浏览器原生能力与 SSE 认证示例冲突。
- 多个 FR 在 spec 中有需求，但 API/DB/UI 缺少可实现契约。
- 部分 QA 文档混入“已实现/待实现”描述，与设计文档职责边界不清。
- 缺少部署、迁移、文件存储、向量库事务补偿、任务取消幂等等工程化设计。

## 3. 高优先级阻塞问题

### 3.1 `projects.status` 枚举跨文档冲突

`06_data_model.sql` 定义 `projects.status` 只能是：

- `idle`
- `running`
- `paused`
- `error`
- `archived`

但 `07_api_contract.md` 中：

- `POST /projects` 示例返回 `status: "draft"`。
- `GET /projects` 查询参数说明仍写 `draft/running/completed`。
- `/tasks/{task_id}/cancel` 返回 `status: "cancelled"`。

风险：

- 后端按 API 实现会违反数据库 CHECK 约束。
- 前端按 API 枚举渲染会遇到 schema 中不存在的状态。
- 任务取消后项目状态无法落到唯一权威状态。

缺失设计：

- 统一项目状态枚举，以 `06_data_model.sql` 为准。
- 明确任务状态和项目状态是否是两套状态机。若需要 task 级 `cancelled/completed`，必须新增任务表或在 `stage_records.status` 中定义对应状态，而不是复用 `projects.status`。
- 修改 `07_api_contract.md` 中所有 `draft/completed/cancelled` 示例。

### 3.2 构建阶段是否允许跳过存在硬冲突

`02_product_requirements.md` 的 FR-019 验收标准明确写“不提供跳过步骤的入口，所有阶段必须执行”。但：

- `07_api_contract.md` 的 `POST /construction/stages/{stage}/action` 支持 `action: "skip"`。
- `04_information_architecture_ui.md` 的构建阶段页面包含 `[跳过]` 按钮。

风险：

- 前后端会实现出与验收标准相反的功能。
- 跳过下载/分析/存储阶段后，后续阶段依赖数据可能缺失，产生脏状态或空邮件。

缺失设计：

- 删除 `skip` API 和 UI 入口，或重新修订 FR-019 允许跳过并定义每个阶段跳过后的数据补偿规则。
- 若保留跳过，必须定义哪些阶段可跳过、跳过后的 `stage_records.result` 最小结构、后续阶段如何处理缺失字段。

### 3.3 深度研究模式“只读图谱”与重建接口冲突

`03_architecture_decisions.md` 和 `02_product_requirements.md` 明确：深度研究模式只读论文库和图谱，不触发图谱重建，不写入图数据库。但：

- `07_api_contract.md` 在深度研究模式章节提供 `POST /projects/{project_id}/graph/rebuild`。
- `04_information_architecture_ui.md` 的知识图谱页有 `[重建图谱]` 按钮。

风险：

- 深度研究对话期间触发图谱重建会破坏“只读约定”和模式互斥边界。
- 图谱重建可能与构建模式增量写入并发，导致 Graph-RAG 上下文不一致。

缺失设计：

- 删除深度研究模式下的重建入口。
- 若必须提供手动重建，应归入构建模式或管理员维护能力，并定义运行中任务拦截、锁、状态展示、失败恢复。

### 3.4 统一响应结构与接口示例不一致

`07_api_contract.md` 总体约定声明成功响应应统一为：

```json
{
  "code": 0,
  "data": {},
  "message": "ok"
}
```

但绝大多数接口示例直接返回裸对象或数组，例如登录、项目列表、论文列表、对话列表、推荐列表等。

同时，`07_api_contract.md` 使用数字错误码如 `40001`，而 `09_quality_observability.md` 使用字符串错误码如 `ERR-VAL-002`，部分测试示例还断言 `response.json()["data"]["code"] == "ERR-AUTH-004"`。

风险：

- 前端 API client 无法生成稳定类型。
- 错误处理层无法统一判断业务错误。
- 契约测试会因 OpenAPI 与文档示例不一致而失效。

缺失设计：

- 明确所有 REST 响应是否包裹 `code/data/message`。
- 明确业务错误码使用数字码、字符串码，还是两者共存。
- 为 SSE 错误事件单独定义 ErrorEnvelope，不要与 REST 错误结构混用。
- 全量更新 API 示例，确保每个接口都符合统一响应结构。

### 3.5 SSE 认证示例在浏览器原生 `EventSource` 中不可实现

`07_api_contract.md` 的 SSE 示例使用：

```typescript
new EventSource(url, { headers: { Authorization: `Bearer ${token}` } })
```

浏览器原生 `EventSource` 不支持自定义 headers。

风险：

- 前端按文档实现会在浏览器中失效。
- 若后端只接受 Authorization header，SSE 连接无法认证。
- 流式构建进度和 LLM 回复会在实际前端不可用。

缺失设计：

- 选择 SSE 认证方案：HttpOnly Cookie、短期 stream token 查询参数、或改用 `fetch` readable stream。
- 明确 CSRF、防重放、token 过期、断线重连策略。
- 更新 `07_api_contract.md` 的前端示例。

### 3.6 多个已声明 FR 缺少 API 契约

`02_product_requirements.md` 声明的多个功能没有完整 API：

- FR-001 密码找回缺少接口。
- FR-009 数据导出缺少论文库 Excel/PDF ZIP 导出接口。
- FR-010 项目级定时配置缺少 `PATCH /projects/{project_id}/schedule`，虽然 `07_api_contract.md` 注释中引用了该接口。
- FR-018 手动重新发送邮件缺少接口。
- FR-024 综述版本管理缺少差异、回退、删除、标签/注释、合并接口。
- FR-028 总结模块缺少按时间范围/主题范围总结、总结历史、导出接口。
- FR-029 管理员用户管理缺少用户列表、禁用/启用、删除、重置密码、提权/撤权接口。
- 系统级 LLM / 学术数据库默认配置缺少管理员接口，仅有系统邮件配置。
- 推荐模块内容审核缺少管理员审核/隐藏/恢复接口。

风险：

- 前端无法完整实现 UI。
- 开发时会临时补接口，造成命名、权限和响应结构不一致。
- 验收标准无法落地到自动测试。

缺失设计：

- 补齐 API 文档，并为每个 FR 建立 FR -> API -> DB -> UI -> QA 的追踪矩阵。

### 3.7 文件上传契约冲突

`07_api_contract.md` 的手动添加论文示例使用：

```json
{ "pdf_file": "<base64>" }
```

但通信设计章节又写文件上传使用 HTTP Multipart。

风险：

- 大 PDF 用 base64 会显著膨胀请求体，影响性能和内存。
- 前后端对上传方式理解不同。

缺失设计：

- 统一为 `multipart/form-data`，或明确小文件 base64 的限制。
- 定义文件大小上限、支持 MIME、批量上传字段、上传进度、失败项返回结构。

## 4. 中优先级设计缺口

### 4.1 Project 调度与异步任务模型不完整

已有 `projects.auto_push/push_interval/next_push_at` 和 `stage_records`，但缺少真实任务模型。

缺失设计：

- 是否需要独立 `tasks` 表；若不需要，`GET /tasks` 如何从 `stage_records` 聚合。
- task_id 与 stage_record_id 的关系。
- 任务取消、暂停、恢复的幂等语义。
- 同一项目 running 锁如何实现。
- 定时任务跳过后的记录是否写入。
- 任务失败后 `projects.status` 何时从 `error` 回到 `idle`。

### 4.2 PostgreSQL 与 ChromaDB “同一事务”缺少可实现策略

文档多次要求 PostgreSQL 与 ChromaDB 强一致、同一事务回滚。但 ChromaDB 通常不能直接参与 PostgreSQL ACID 事务。

缺失设计：

- 两阶段提交、outbox、补偿删除、重试队列或一致性校验任务的具体方案。
- PostgreSQL 提交成功但 ChromaDB 写入失败时的恢复策略。
- ChromaDB 写入成功但 PostgreSQL 回滚时的清理策略。
- 向量 chunk ID 与 paper/project 关系的规范。

### 4.3 文件存储与导出产物缺少生命周期设计

文档有 `pdf_path`、`text_path`、导出 ZIP/PDF/Word，但缺少文件系统或对象存储规范。

缺失设计：

- 文件根目录、路径命名、安全校验、防路径穿越。
- PDF/text/GraphML/export 文件保留时长。
- 用户删除项目后文件如何清理。
- 导出文件下载链接如何授权、过期和撤销。
- 大文件下载是否走流式响应。

### 4.4 权限矩阵不完整

当前有用户隔离、管理员访问、项目所有者规则，但没有完整权限矩阵。

缺失设计：

- 普通用户、管理员、项目所有者对每类资源的 CRUD 权限。
- 管理员是否能查看普通用户项目内容。
- 推荐模块中他人内容的删除、隐藏、点赞权限。
- 404 防枚举和 403 权限错误的统一规则。
- 禁用账号后现有 token 是否立即失效。

### 4.5 配置模型存在重复语义

`user_configs` 中有 `is_system_default`，同时又新增 `system_configs`。这会造成系统默认配置有两个可能来源。

缺失设计：

- 明确废弃 `user_configs.is_system_default`，或说明其用途。
- 配置 key 命名规范需要固定，例如 `llm.provider.openai.url` 与 `system.llm.default` 当前同时出现。
- API key 加密方式、密钥轮换、脱敏返回规则需要单独定义。

### 4.6 Review 版本管理数据模型不足

`review_outlines` 和 `review_chapters` 能支持大纲版本和章节状态，但不能完整支持 FR-024 中的完整文章版本、差异、回退、合并、版本标签/注释。

缺失设计：

- 新增或定义 `review_documents` / `review_versions`。
- 定义版本快照粒度：大纲、章节、完整文章、导出产物是否一起版本化。
- 定义回退后是否创建新版本，而不是覆盖历史版本。

### 4.7 推荐模块点赞和审核模型不足

`recommendations` 只有 `like_count`，没有记录用户点赞关系。

风险：

- 无法防止同一用户重复点赞。
- 无法取消点赞。
- 无法审计点赞来源。

缺失设计：

- 增加 `recommendation_likes(user_id, recommendation_id)` 或定义服务端去重策略。
- 增加审核操作 API 和审核日志。

### 4.8 UI 文档缺少响应式、可访问性和设计系统细节

`04_information_architecture_ui.md` 有线框图，但缺少具体视觉规范。

缺失设计：

- 响应式断点和移动端布局。
- 表单校验文案。
- 空态、加载态、错误态、禁用态。
- 可访问性要求：键盘操作、焦点管理、ARIA、色彩对比。
- 设计 token：颜色、字体、间距、阴影、圆角、层级。

## 5. 低优先级但建议补齐的设计

- 部署文档：环境变量、依赖服务、启动顺序、Docker Compose/K8s、反向代理、HTTPS。
- 数据库迁移策略：schema 版本升级、回滚、种子数据、首位管理员并发注册锁。
- OpenAPI 生成策略：是否由 FastAPI schema 作为最终 API 契约。
- 成本控制：LLM token 预算、用户级限流、任务级并发限制。
- 外部 API 速率限制：每个 provider 的队列、退避和降级策略。
- GraphML 持久化并发锁：每日重建与手动导出/读取冲突处理。
- 浏览器兼容策略：SSE 重连、Safari 行为、大文本流式渲染性能。
- 国际化/时区：文档写 UTC 存储，但 UI 展示时区和用户偏好未定义。
- 审计日志：管理员操作、项目删除、配置变更、密钥更新、导出下载。

## 6. 建议的修复顺序

1. 统一全局契约：项目状态、阶段状态、任务状态、错误码、响应 envelope。
2. 修正高风险冲突：删除/重设 `skip`、移除深研图谱重建、修复 SSE 认证方案、统一文件上传。
3. 补齐 API：调度、导出、管理员用户管理、系统默认 LLM/数据库配置、邮件重发、推荐审核、密码找回、综述版本管理。
4. 补齐任务模型：task_id、stage_record_id、取消/暂停/恢复、定时任务、并发锁、幂等规则。
5. 补齐工程化设计：文件存储、ChromaDB 一致性补偿、部署、迁移、密钥加密、审计日志。
6. 补齐 UI 细节：响应式、空/错/加载态、设计 token、可访问性。
7. 建立追踪矩阵：每个 FR 必须能映射到 API、DB、UI、QA 测试。

## 7. FR 到缺失设计追踪表

| FR | 当前状态 | 缺失/冲突 |
| --- | --- | --- |
| FR-001 用户注册与登录 | 部分可实现 | 缺少密码找回 API；首位管理员并发注册锁未定义 |
| FR-002 LLM 配置 | 部分可实现 | 用户配置有 API；系统级默认 LLM 管理 API 不完整；密钥加密细节缺失 |
| FR-003 学术数据库 API 配置 | 部分可实现 | 用户配置有 API；系统级默认数据库配置 API 不完整 |
| FR-004 邮件配置 | 部分可实现 | 普通用户收件人与系统 SMTP 已区分；邮件模板自定义缺少 API/DB |
| FR-005 三模式切换 | 有冲突 | 状态枚举冲突；运行中任务取消语义不完整 |
| FR-006 检索历史查看 | 不完整 | 缺少历史详情/重新执行/导出报告 API |
| FR-007 数据库查看与管理 | 部分可实现 | 独立论文库 UI 未完整；清空当前课题论文关联缺少 API |
| FR-008 任务管理 | 不完整 | `/tasks` 有接口草稿，但无任务表和 task-stage 关系设计 |
| FR-009 数据导出 | 不完整 | 缺少 Excel/PDF ZIP 导出 API、任务状态和文件生命周期 |
| FR-010 定时自动任务 | 不完整 | 缺少 schedule API；调度器、跳过记录、并发锁细节不足 |
| FR-011 推荐模块 | 部分可实现 | 缺少 UI、点赞去重、审核 API、审核日志 |
| FR-012 多源论文检索 | 部分可实现 | 速率限制、失败降级、去重冲突解决细节不足 |
| FR-013 智能评分与筛选 | 部分可实现 | `skip` 冲突；阈值变更后是否重算 `is_valid` 需定义 |
| FR-014 论文补充与上传 | 不完整 | base64 vs multipart 冲突；批量上传 API 不完整 |
| FR-015 PDF 下载与解析 | 部分可实现 | 文件存储、图片表格裁剪规范、失败降级细节不足 |
| FR-016 AI 分析生成 | 部分可实现 | AI analysis JSON schema 未固定 |
| FR-017 数据库存储 | 高风险不完整 | PostgreSQL + ChromaDB 强一致缺少可实现事务/补偿方案 |
| FR-018 邮件提示服务 | 部分可实现 | 手动重发、模板管理、发送日志 API/DB 缺失 |
| FR-019 分步骤交互 | 有冲突 | spec 禁止跳过，API/UI 允许跳过 |
| FR-020 综述架构设计 | 部分可实现 | 阶段操作 API 与 review outline API 边界需统一 |
| FR-021 章节内容撰写 | 部分可实现 | 引用格式 schema、章节并发写入策略不足 |
| FR-022 自动审查迭代 | 部分可实现 | 迭代上限、接受/拒绝建议 API 不完整 |
| FR-023 综述汇总 | 部分可实现 | 汇总产物存储、导出任务、文件下载授权不足 |
| FR-024 版本管理 | 不完整 | 缺少完整文章版本表、diff、rollback、merge API |
| FR-025 知识图谱浏览 | 有冲突 | 深研只读与 graph rebuild 接口/UI 冲突 |
| FR-026 对话式探讨 | 部分可实现 | SSE 认证方案不可用；Graph-RAG 参数和引用格式需固定 |
| FR-027 研究历史记录 | 部分可实现 | 检索操作/实验设计历史未单独建模 |
| FR-028 Agent 总结模块 | 不完整 | 缺少总结历史、范围总结、导出、分享 API/DB |
| FR-029 管理员配置面板 | 不完整 | 缺少用户管理、系统级 LLM/数据库、提权/撤权、重置密码 API |

## 8. 最终判定

当前设计文档适合作为系统方向和核心模型的基础，但还不是可直接交付给开发团队的完整实现契约。

实现前必须至少补齐以下内容，否则会产生高概率设计冲突：

- 统一状态机与错误响应契约。
- 补齐缺失 API。
- 修正 SSE 认证、文件上传、图谱重建、阶段跳过等现实冲突。
- 明确异步任务和存储一致性策略。
- 补齐权限矩阵、部署迁移、文件生命周期和 UI 状态设计。

建议将 `06_data_model.sql` 继续作为数据层权威契约，将 `07_api_contract.md` 修订为可生成 OpenAPI 的单一接口契约，将 `02_product_requirements.md` 只保留需求与验收含义，避免多个文档同时定义同一字段或枚举。
