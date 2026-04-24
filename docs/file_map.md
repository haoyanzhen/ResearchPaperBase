# 项目文件功能目录

**文档版本**：v3.1 · 2026-04-24
**维护规则**：新增或删除文件时同步更新本文档；重命名文件时同步更新所有引用路径。
**用途**：作为参考契约文件，供 AI 辅助开发快速定位文件职责、避免重复创建或误改。

---

## 顶层目录

```
agent_paperpush/
├── docs/          契约文档（权威来源，不含实现代码）
├── backend/       Python 后端（FastAPI + SQLAlchemy + Alembic）
├── src/           TypeScript 前端 API 客户端层
└── old_files/     废弃原型代码（仅供参考，不参与构建）
```

---

## docs/ — 契约文档

| 文件 | 职责 |
|------|------|
| [spec.md](spec.md) | 需求规格说明书（v1.7）；FR-001~FR-029 完整功能需求；**修改需评审** |
| [api.md](api.md) | API 设计文档（已对齐 schema.sql v1.1 / spec.md v1.7）；所有 HTTP 端点请求/响应格式；前后端接口契约 |
| [schema.sql](schema.sql) | PostgreSQL DDL（v1.1）；13 张表结构（含 system\_configs）、索引、约束；**数据层唯一权威** |
| [ui_design.md](ui_design.md) | 前端界面设计草稿；ASCII 线框图；各页面布局与交互逻辑 |
| [ADR_design.md](ADR_design.md) | 架构决策记录（ADR）；技术选型理由与取舍 |
| [file_map.md](file_map.md) | **本文件**；项目文件功能目录 |
| [qa_design.md](qa_design.md) | QA 与错误诊断设计（v1.0）；错误码体系、结构化错误信封、SSE 错误事件协议、健康检查探针规范、诊断快照端点、分层测试策略、Inspector Panel 规范；§10 验收检查清单含逐项完成状态，20 项中 12 项完成、4 项待完成（均为前端交互逻辑） |
| [VibeCoding_record.md](VibeCoding_record.md) | 开发过程记录；设计演进历史 |
| [media/](media/) | 文档附图（logo、RAG 结构图等） |

---

## backend/ — Python 后端

### 入口与配置

| 文件 | 职责 |
|------|------|
| [backend/app/main.py](../backend/app/main.py) | FastAPI 应用入口；注册路由、CORS 中间件、/health 端点；`lifespan` 上下文启动 APScheduler（FR-010 自动推送，每 5 分钟检查 `next_push_at <= now`） |
| [backend/requirements.txt](../backend/requirements.txt) | Python 依赖声明（含 openpyxl / python-docx / networkx / apscheduler） |
| [backend/.env.example](../backend/.env.example) | 环境变量模板（DATABASE\_URL / SECRET\_KEY / APP\_ENV 等） |
| [backend/alembic.ini](../backend/alembic.ini) | Alembic 迁移配置；指向 `alembic/` 脚本目录 |

### backend/app/core/ — 基础设施

| 文件 | 职责 |
|------|------|
| [core/config.py](../backend/app/core/config.py) | 应用配置（pydantic-settings）；从 .env 读取 DATABASE\_URL / SECRET\_KEY 等 |
| [core/database.py](../backend/app/core/database.py) | 异步数据库引擎（asyncpg）；`get_db()` 依赖注入会话工厂 |
| [core/security.py](../backend/app/core/security.py) | JWT 生成/验证；bcrypt 密码哈希；内存 token 黑名单（登出用） |
| [core/deps.py](../backend/app/core/deps.py) | FastAPI 依赖项；`get_current_user()` — Bearer token → User 对象；`get_current_admin()` — 额外要求 is\_admin=True，否则 403 |
| [core/errors.py](../backend/app/core/errors.py) | 错误码体系（`AppErrorCode` 枚举，40+ 个 ERR-* 码）；`ErrorEnvelope` Pydantic 模型；`make_envelope()` 构造函数（自动填充 retryable/suggestion/traceback）；`classify_agent_error()` 按模式+阶段推断错误码；`RETRYABLE_CODES` / `SUGGESTIONS` 映射表 |
| [core/logging.py](../backend/app/core/logging.py) | 结构化 JSON 日志（qa_design §9）；`JsonFormatter`（LogRecord → 单行 JSON，含 timestamp/level/logger/message + 上下文字段）；`setup_logging()` — 应用启动时配置根日志器，读取 `APP_ENV` 决定日志级别；`bind_log_context()` 上下文管理器（通过 `contextvars` 注入 project_id/user_id/stage 等字段） |

### backend/app/models/ — ORM 数据层

对应 schema.sql 的 12 张原始表 + migration 0002 新增的 `system_configs` 表，是数据库结构的 Python 映射。

| 文件 | 对应表（schema.sql 编号） |
|------|--------------------------|
| [models/base.py](../backend/app/models/base.py) | SQLAlchemy `DeclarativeBase` 公共基类 |
| [models/user.py](../backend/app/models/user.py) | `users`(1) · `user_configs`(2) · `system_configs`(13，管理员全局配置) |
| [models/project.py](../backend/app/models/project.py) | `projects`(3) · `keywords`(4) |
| [models/paper.py](../backend/app/models/paper.py) | `papers`(5) · `project_paper_relations`(6) |
| [models/stage.py](../backend/app/models/stage.py) | `stage_records`(7) |
| [models/dialogue.py](../backend/app/models/dialogue.py) | `research_dialogues`(8) · `dialogue_turns`(9) |
| [models/review.py](../backend/app/models/review.py) | `review_outlines`(10) · `review_chapters`(11) |
| [models/recommendation.py](../backend/app/models/recommendation.py) | `recommendations`(12) |
| [models/\_\_init\_\_.py](../backend/app/models/__init__.py) | 集中导入所有模型，确保 Alembic metadata 完整注册 |

### backend/app/schemas/ — Pydantic 请求/响应模型

| 文件 | 职责 |
|------|------|
| [schemas/common.py](../backend/app/schemas/common.py) | 统一响应结构 `ApiResponse[T]`；`ok()` / `err()` 工厂函数 |
| [schemas/health.py](../backend/app/schemas/health.py) | 健康检查与诊断响应 schema：`CheckResult`、`ShallowHealthResponse`、`DbHealthResponse`、`DeepHealthResponse`、`PipelineHealthResponse`、`InspectResponse`（含 `StageHistoryItem`、`ConfigStatus` 等） |
| [schemas/auth.py](../backend/app/schemas/auth.py) | FR-001 注册/登录/用户信息相关 schema |
| [schemas/config.py](../backend/app/schemas/config.py) | FR-002~004 LLM / 数据库 / 邮件配置相关 schema |
| [schemas/project.py](../backend/app/schemas/project.py) | FR-005~011 项目、论文、任务、导出、定时、推荐相关 schema |
| [schemas/construction.py](../backend/app/schemas/construction.py) | FR-012~018 构建模式请求/响应 schema（启动、状态、关键词、阶段操作） |
| [schemas/dialogue.py](../backend/app/schemas/dialogue.py) | FR-025~028 深度研究模式请求/响应 schema（对话会话列表/详情、轮次、摘要、图谱节点/边） |
| [schemas/review.py](../backend/app/schemas/review.py) | FR-020~024 综述模式请求/响应 schema（启动、架构版本、章节、汇总、导出、状态） |
| [schemas/admin.py](../backend/app/schemas/admin.py) | FR-029 管理员面板 schema（用户列表条目 / 账号操作 / 重置密码响应 / 系统 LLM 与数据库配置请求） |

### backend/app/services/ — 业务逻辑层

| 文件 | 职责 |
|------|------|
| [services/auth\_service.py](../backend/app/services/auth_service.py) | 用户注册（首位用户自动提升为管理员）/认证（含 is\_active 禁用检查）/信息更新；密码校验 |
| [services/config\_service.py](../backend/app/services/config_service.py) | 基于 user\_configs 的 Key-Value 读写；系统级配置（system\_configs）读写；回落函数（`get_config_with_fallback` / `get_all_llm_providers_with_fallback` / `get_databases_config_with_fallback`）；LLM / 数据库 / 邮件配置序列化 |
| [services/admin\_service.py](../backend/app/services/admin_service.py) | FR-029 用户账号管理：列表 / 启停（`set_user_active`）/ 提权（`set_user_admin`）/ 删除（级联）/ 重置密码（含 SMTP 发信） |
| [services/project\_service.py](../backend/app/services/project_service.py) | 项目 CRUD；模式切换；论文关联管理（含 `clear_papers` 清空所有关联）；`archive_project` 归档；评分更新；推荐 CRUD；定时配置 |
| [services/construction\_service.py](../backend/app/services/construction_service.py) | 关键词 CRUD（含所有权校验）；阶段记录管理；启动构建；状态查询；阶段操作（confirm/retry/skip，confirm 时通过 `_apply_stage_modifications` 立即应用 removed\_ids / score\_overrides / analysis\_overrides）；FR-018 邮件发送（`send_stage7_email` / `execute_stage7`）；`get_pipeline_params` |
| [services/dialogue\_service.py](../backend/app/services/dialogue_service.py) | FR-025~028 深度研究模式业务逻辑：对话会话 CRUD；`list_turns`（分页）；`_derive_sub_mode`（从最近轮次派生）；`_parse_summary` / `_summary_preview`（AgentSummary JSON 序列化） |
| [services/review\_service.py](../backend/app/services/review_service.py) | FR-020~024 综述模式业务逻辑：启动综述 `start_review`；架构 CRUD；`confirm_outline`；章节 CRUD；`trigger_chapter_review`；`compile_outline`（stage5）；`get_review_status`；`export_outline`（Markdown ✅ / DOCX ✅ via `_compile_docx()` / PDF 存根） |

### backend/app/api/v1/ — HTTP 路由层

| 文件 | 覆盖端点 | 对应 FR |
|------|----------|---------|
| [api/v1/router.py](../backend/app/api/v1/router.py) | 注册所有子路由到 `/api/v1` | — |
| [api/v1/auth.py](../backend/app/api/v1/auth.py) | `POST /auth/register` · `login` · `logout` · `GET/PATCH /auth/me` | FR-001 |
| [api/v1/config.py](../backend/app/api/v1/config.py) | `GET/POST/PATCH/DELETE /config/llm` · `/config/databases` · `/config/email` | FR-002~004 |
| [api/v1/projects.py](../backend/app/api/v1/projects.py) | `/projects` CRUD · `/mode` · `/archive` · `/stage-records` · `/papers`（含 `DELETE /papers` 清空全部；`POST /papers` 同步 arXiv/DOI 抓取入库，FR-007）· `/export`（同步生成 Excel/PDF-ZIP，StreamingResponse，FR-009）· `/schedule` · `/recommendations` | FR-005~011 |
| [api/v1/tasks.py](../backend/app/api/v1/tasks.py) | `GET /tasks` · `POST /tasks/{id}/pause·resume·cancel` | FR-008 |
| [api/v1/construction.py](../backend/app/api/v1/construction.py) | `/construction/start` · `/status` · `/keywords` · `/stages/{stage}/action` · `/stream`（SSE）；stage 6 confirm 后 BackgroundTask 自动触发 stage 7 | FR-012~019 |
| [api/v1/dialogues.py](../backend/app/api/v1/dialogues.py) | `/dialogues` CRUD · `/dialogues/{id}/turns`（GET分页/POST SSE流）· `/dialogues/{id}/summarize` · `/graph`（JSON/GraphML）· `/graph/rebuild`（202，调用 `rebuild_graph_stub(db=db)` 真实重建+持久化）；发消息直接 StreamingResponse 不走 Queue | FR-025~028 |
| [api/v1/review.py](../backend/app/api/v1/review.py) | `/review/status` · `/review/start` · `/outlines` CRUD · `/outlines/{id}/confirm` · `/outlines/{id}/chapters` CRUD · `/outlines/{id}/chapters/{id}/review` · `/outlines/{id}/compile` · `/outlines/{id}/export`（Markdown ✅ / DOCX ✅ / PDF 返回 501）· `/stream`（SSE）；chapter review 通过独立 AsyncSession 的 `_run_chapter_review` wrapper 执行 | FR-020~024 |
| [api/v1/admin.py](../backend/app/api/v1/admin.py) | `/admin/users` 用户列表/启停/提权/删除/重置密码；`/admin/system-config/llm` 系统 LLM CRUD + 连通性测试；`/admin/system-config/databases` 系统数据库配置；所有端点均通过 `get_current_admin` 鉴权（非管理员返回 403） | FR-029 |
| [api/v1/health.py](../backend/app/api/v1/health.py) | `GET /health`（浅层，公开）· `GET /health/db`（PostgreSQL 连通性，公开，503+ErrorEnvelope on fail）· `GET /health/deep`（全依赖并发探针：LLM主/备+arXiv/OpenAlex/SS/ADS+SMTP，需认证，返回 `DeepHealthResponse`）· `GET /health/pipeline/{id}`（流水线活跃阶段快照，需认证，ErrorEnvelope 解析）| — |
| [api/v1/inspect.py](../backend/app/api/v1/inspect.py) | `GET /projects/{id}/inspect`（项目诊断快照，需认证，项目所有者或管理员）；返回阶段历史、论文/关键词统计、配置状态、自动修复建议（`recommendations` 按优先级生成） | — |

### backend/app/agents/ — Agent 执行层

Agent 层按模式分为三个子包，对外仅暴露 `run_stage()` 接口，由 FastAPI `BackgroundTasks` 调用。

#### 公共基础设施

| 文件 | 职责 |
|------|------|
| [agents/\_\_init\_\_.py](../backend/app/agents/__init__.py) | 模块入口注释 |
| [agents/base.py](../backend/app/agents/base.py) | `LLMClient`（OpenAI 兼容 API）；`get_llm_client()` 工厂；SSE 队列（`get_sse_queue` / `emit_sse_event`）；配置加载（`load_construction_prompts` / `load_llm_defaults`）；`parse_json_response` |
| [agents/config/construction\_prompts.yaml](../backend/app/agents/config/construction_prompts.yaml) | 构建模式 LLM 提示词配置（stage1 检索词生成 / stage3 评分 / stage5 分析）；变量占位符 `{name}` 风格 |
| [agents/config/review\_prompts.yaml](../backend/app/agents/config/review_prompts.yaml) | 综述模式 LLM 提示词配置（stage1 课题扩写 / stage2 架构生成 / stage3 章节撰写 / stage4 审查+修改 / stage5 摘要关键词） |
| [agents/config/deep\_research\_prompts.yaml](../backend/app/agents/config/deep_research_prompts.yaml) | 深度研究模式 LLM 提示词配置（dialogue\_theory / dialogue\_technical / dialogue\_experiment 三种子模式 + dialogue\_summarize 摘要生成） |
| [agents/config/llm\_defaults.yaml](../backend/app/agents/config/llm_defaults.yaml) | LLM 全局默认参数 + 各阶段覆盖（temperature / max\_tokens / batch\_size）；学术数据库检索配置；PDF 下载配置 |

#### 构建模式 Agent（FR-012~019）

| 文件 | 职责 |
|------|------|
| [agents/construction/\_\_init\_\_.py](../backend/app/agents/construction/__init__.py) | `run_stage(project_id, user_id, stage, record_id)` — 统一入口；按 stage 分发到对应 handler；未捕获异常自动标记 failed |
| [agents/construction/pipeline.py](../backend/app/agents/construction/pipeline.py) | 阶段记录生命周期：`mark_stage_paused` / `mark_stage_failed` / `mark_stage_completed`；`get_pipeline_params`（读取 stage1 启动参数） |
| [agents/construction/stage1\_keyword\_gen.py](../backend/app/agents/construction/stage1_keyword_gen.py) | 检索词生成：调用 LLM 生成 3-5 组英文检索词 + 各 DB 布尔表达式；写入 keywords 表；paused 等待用户确认 |
| [agents/construction/stage2\_retrieval.py](../backend/app/agents/construction/stage2_retrieval.py) | 多源检索（FR-012）：并发调用 arXiv / OpenAlex / Semantic Scholar API；三路去重（DOI / arXiv ID / 小写 title）；写入 papers + project\_paper\_relations |
| [agents/construction/stage3\_scoring.py](../backend/app/agents/construction/stage3_scoring.py) | AI 评分（FR-013）：批量并发 LLM 评分；按 score\_threshold 设置 is\_valid；支持 score\_overrides 手动覆盖；更新 project.valid\_papers |
| [agents/construction/stage4\_download.py](../backend/app/agents/construction/stage4_download.py) | PDF 下载与解析（FR-015）：arXiv 直链 + Unpaywall 开放获取；`pypdf` 提取文本；存储到 `STORAGE_DIR/papers/` |
| [agents/construction/stage5\_analysis.py](../backend/app/agents/construction/stage5_analysis.py) | AI 分析生成（FR-016）：优先全文、次选摘要；LLM 生成 summary / highlights / relevance\_points / technical\_methods；支持 analysis\_overrides |
| [agents/construction/stage6\_storage.py](../backend/app/agents/construction/stage6_storage.py) | 格式化与存储（FR-017）：完整性校验；`_sync_chromadb()`（JSON 元数据缓存→`STORAGE_DIR/chroma_cache/{project_id}.json`）；`_update_networkx_graph()`（networkx DiGraph 含 co-author 边→`STORAGE_DIR/graphs/{project_id}.json`）；paused 等待用户 confirm 触发 stage7 |

#### 深度研究模式 Agent（FR-025~028）

| 文件 | 职责 |
| ---- | ---- |
| [agents/deep\_research/\_\_init\_\_.py](../backend/app/agents/deep_research/__init__.py) | 公开接口：`run_dialogue_turn` / `generate_summary` / `build_graph_data` / `get_graphml` / `rebuild_graph_stub` |
| [agents/deep\_research/pipeline.py](../backend/app/agents/deep_research/pipeline.py) | `SUB_MODE_NAMES`；`load_deep_research_prompts()`（lru\_cache）；`get_project_valid_papers`；`graph_rag_retrieve`（关键词匹配简化版 Graph-RAG）；`build_context_from_papers`；`build_history_text`；`extract_referenced_papers` |
| [agents/deep\_research/graph\_builder.py](../backend/app/agents/deep_research/graph_builder.py) | `build_graph_data(db, project_id, node_types)`：从 DB 动态构建图（paper/author/keyword/venue 节点 + authored\_by/has\_keyword/in\_venue 边）；`get_graphml()`：手动生成 GraphML XML；`rebuild_graph_stub(db)`：若传入 db 则调用 `build_graph_data()` 并持久化到 `STORAGE_DIR/graphs/{project_id}.json`，返回 node/edge 计数 |
| [agents/deep\_research/dialogue\_agent.py](../backend/app/agents/deep_research/dialogue_agent.py) | `run_dialogue_turn()`：Graph-RAG 检索→LLM 调用→提取引用→持久化 turn→yield SSE 事件（turn\_start / text\_delta / turn\_complete）；`generate_summary()`：FR-028 生成 AgentSummary JSON 并写入 dialogue.summary |

#### 综述模式 Agent（FR-020~024）

| 文件 | 职责 |
| ---- | ---- |
| [agents/review/\_\_init\_\_.py](../backend/app/agents/review/__init__.py) | `run_stage(project_id, user_id, stage, record_id)` — 统一入口；按 stage 1-5 分发到对应 handler；未捕获异常自动标记 failed + SSE 错误事件 |
| [agents/review/pipeline.py](../backend/app/agents/review/pipeline.py) | `REVIEW_STAGE_NAMES`；阶段记录生命周期：`mark_stage_paused` / `mark_stage_failed` / `mark_stage_completed`；`load_review_prompts`（lru\_cache）；`get_record` / `get_project` / `get_latest_draft_outline` / `get_outline_chapters` |
| [agents/review/stage1\_topic\_expansion.py](../backend/app/agents/review/stage1_topic_expansion.py) | 课题扩写：LLM 扩展课题描述，写入 `outline.topic_expansion`；自动链接 stage2（无暂停）；stage2 异常由 stage1 捕获并以 stage2 record\_id 标记失败 |
| [agents/review/stage2\_outline\_gen.py](../backend/app/agents/review/stage2_outline_gen.py) | 综述架构生成：LLM 输出 `ReviewOutlineContent`（title / abstract\_hint / sections[]），写入 `outline.outline`；paused 等待用户确认 |
| [agents/review/stage3\_chapter\_writing.py](../backend/app/agents/review/stage3_chapter_writing.py) | 章节撰写：按 outline.sections 为每章调用 LLM 写正文；提取 `[cite:paper_id]` 引用格式；更新章节 content / citations / status；自动链接 stage4；stage4 异常由 stage3 捕获并以 stage4 record\_id 标记失败 |
| [agents/review/stage4\_auto\_review.py](../backend/app/agents/review/stage4_auto_review.py) | 自动审查迭代：`review_chapter_once()` 可独立调用；`run()` 遍历所有章节最多 2 轮 LLM 审查+修改；paused 等待用户触发 compile |
| [agents/review/stage5\_compile.py](../backend/app/agents/review/stage5_compile.py) | 综述汇总：LLM 生成摘要+关键词；合并章节+参考文献为完整 Markdown；写入 `outline.outline["compiled_content"]`；project.status → idle |

### backend/app/utils/ — 工具函数

| 文件 | 职责 |
|------|------|
| [utils/ids.py](../backend/app/utils/ids.py) | `new_id(prefix)` — 生成带前缀的 nanoid 短 ID（如 `p_x3k9mz1abcde`） |

### backend/tests/ — 后端测试套件（qa_design §7）

| 文件 | 职责 |
|------|------|
| [backend/pytest.ini](../backend/pytest.ini) | pytest 配置；`asyncio_mode=auto`；testpaths；markers（unit/integration/contract/e2e） |
| [backend/tests/conftest.py](../backend/tests/conftest.py) | 顶层 fixtures：`mock_llm_complete`（正常返回）/ `mock_llm_rate_limit`（429 模拟）/ `mock_llm_raise`（可配置异常）/ `sse_event_type_parser`（解析 SSE 格式） |
| [backend/tests/unit/test_errors.py](../backend/tests/unit/test_errors.py) | 单元测试：`ErrorEnvelope` 字段校验；`make_envelope()` 自动填充（retryable/suggestion/traceback）；`classify_agent_error()` 阶段映射；`classify_llm_error()` 关键词识别；RETRYABLE_CODES/SUGGESTIONS 完整性检查 |
| [backend/tests/unit/test_schemas.py](../backend/tests/unit/test_schemas.py) | 单元测试：`CheckResult`/`ShallowHealthResponse`/`DbHealthResponse`/`DeepHealthResponse`/`PipelineHealthResponse` Pydantic 校验；`ErrorEnvelope` JSON 往返序列化；`InspectResponse.recommendations` 字段 |
| [backend/tests/unit/test_ids.py](../backend/tests/unit/test_ids.py) | 单元测试：`new_id()` 前缀格式、字符集约束、唯一性（500 次）、跨前缀不重叠 |
| [backend/tests/unit/test_base.py](../backend/tests/unit/test_base.py) | 单元测试：`parse_json_response()`（正常/markdown/代码块/无效 JSON）；`emit_sse_event()`（格式/JSON 有效性/队列满降级）；`emit_error_event()`（stage_error 事件类型/code 字段） |
| [backend/tests/integration/conftest.py](../backend/tests/integration/conftest.py) | 集成测试 fixtures：真实 PostgreSQL 引擎（session scoped）；事务回滚隔离 db_session；ASGI httpx client；test_user/admin_user 创建；auth_headers/admin_auth_headers JWT |
| [backend/tests/integration/test_construction_pipeline.py](../backend/tests/integration/test_construction_pipeline.py) | 集成测试：阶段失败时 `stage_records.error` 存储 `ErrorEnvelope` JSON；旧版纯文本错误降级解析；链式阶段失败标记正确 record_id |
| [backend/tests/integration/test_dialogue.py](../backend/tests/integration/test_dialogue.py) | 集成测试：`POST /dialogues` 返回正确结构；LLM 错误时不写入 dialogue_turns；SSE 解析辅助函数格式验证 |
| [backend/tests/integration/test_mode_switch.py](../backend/tests/integration/test_mode_switch.py) | 集成测试：FR-005 空论文库阻止综述/深度研究模式（4xx）；FR-029 非所有者权限拦截；未认证请求 401 |
| [backend/tests/contract/schemathesis.toml](../backend/tests/contract/schemathesis.toml) | Schemathesis 契约测试配置；启用全量检查（status_code/content_type/response_schema conformance）；排除 SSE 流端点；响应时间限制 1000ms |
| [backend/tests/contract/run_contract_tests.sh](../backend/tests/contract/run_contract_tests.sh) | CI 契约测试执行脚本；等待 API 就绪（30s）；生成 JUnit XML + HTML 报告 |

### backend/alembic/ — 数据库迁移

| 文件 | 职责 |
|------|------|
| [alembic/env.py](../backend/alembic/env.py) | 异步迁移环境；从 `app.core.config` 读取 DATABASE\_URL；注册完整 metadata |
| [alembic/script.py.mako](../backend/alembic/script.py.mako) | 迁移文件模板 |
| [alembic/versions/0001\_initial\_schema.py](../backend/alembic/versions/0001_initial_schema.py) | 初始迁移：创建全部 12 张表及索引（对应 schema.sql v1.0） |
| [alembic/versions/0002\_admin\_columns.py](../backend/alembic/versions/0002_admin_columns.py) | 管理员迁移：users 表新增 is\_admin / is\_active 列；创建 system\_configs 表（FR-029） |

### backend/scripts/ — 运维脚本

| 文件 | 职责 |
|------|------|
| [scripts/init\_db.py](../backend/scripts/init_db.py) | 开发环境一键建库；封装 `alembic upgrade head` 并提供友好错误提示 |

---

## src/ — TypeScript 前端 API 客户端层

### src/types/

| 文件 | 职责 |
|------|------|
| [src/types/index.ts](../src/types/index.ts) | 跨模块共享类型定义（唯一权威来源）；枚举联合、12 张表实体接口、JSONB 结构类型、ChromaDB / NetworkX 图类型（含 `GraphNodeType` venue 节点、`GraphEdgeType` in\_venue 边）、业务流程类型 |

### src/api/

所有方法通过 `http` 客户端调用，统一响应解包（`code !== 0` 时抛 `ApiError`）。

| 文件 | 职责 | 对应 api.md 章节 |
|------|------|-----------------|
| [src/api/client.ts](../src/api/client.ts) | 基础 HTTP 客户端；`ApiError`；`tokenStore`（localStorage 令牌管理） | §总体约定 |
| [src/api/auth.ts](../src/api/auth.ts) | `authApi`：注册 / 登录（自动存 token）/ 登出 / 获取&修改当前用户；`RegisterResponse` 含 `is_admin` | §1 |
| [src/api/config.ts](../src/api/config.ts) | `configApi`：LLM / 学术数据库（含 `endpoint`）/ 邮件配置的增删改查与连接测试 | §2 |
| [src/api/projects.ts](../src/api/projects.ts) | `projectsApi`：项目 CRUD / 模式切换 / `archive()` 归档 / 检索历史 / 论文管理（含 `clearPapers()`） / 导出 / 定时配置；`recommendationsApi`：推荐内容列表、发布、点赞、删除 | §3 §5（部分）§9 |
| [src/api/admin.ts](../src/api/admin.ts) | `adminApi`：用户列表 / 账号启停 / 提权 / 删除 / 重置密码；系统 LLM 配置 CRUD + 测试；系统数据库配置读写 | — |
| [src/api/construction.ts](../src/api/construction.ts) | `constructionApi`：启动构建 / 状态查询 / 检索词管理 / 阶段操作 / SSE 流 URL | §4 |
| [src/api/dialogues.ts](../src/api/dialogues.ts) | `dialoguesApi`：对话会话 CRUD / 轮次历史 / 消息发送（SSE fetch）/ 对话摘要 / 知识图谱获取与重建 | §6 |
| [src/api/review.ts](../src/api/review.ts) | `reviewApi`：`getStatus` / 启动综述 / 架构版本管理 / 章节管理 / 汇总编译 / 导出（文件流）/ SSE 流 URL；含 `ReviewStatusResponse` 接口定义 | §7 |
| [src/api/tasks.ts](../src/api/tasks.ts) | `tasksApi`：任务列表 / 暂停 / 恢复 / 取消 | §8 |
| [src/api/inspect.ts](../src/api/inspect.ts) | Inspector & Health API 客户端；`getHealth()` / `getDbHealth()` / `getDeepHealth()` / `getPipelineHealth(projectId)` / `getProjectInspect(projectId)`；完整 TypeScript 类型定义（`CheckResult` / `DeepHealthResponse` / `InspectResponse` 等）；`parseRecommendationSeverity()` 辅助函数（fatal/error/warning/info） | — |
| [src/api/index.ts](../src/api/index.ts) | 统一桶形导出（re-export 所有 API 模块及 `ApiError` / `tokenStore`） | — |

### src/components/

| 文件 | 职责 |
| ---- | ---- |
| [src/components/InspectorPanel/types.ts](../src/components/InspectorPanel/types.ts) | InspectorPanel 组件内部类型：`PanelLoadState`、`InspectorPanelState`、`ParsedRecommendation`、`StageHistoryRow`、`DependencyRow`、`InspectorPanelProps` |
| [src/components/InspectorPanel/InspectorPanel.tsx](../src/components/InspectorPanel/InspectorPanel.tsx) | 项目诊断面板 React 组件（qa_design §8）；并发调用 `/inspect` + `/health/pipeline` + `/health/deep`；渲染建议列表（fatal/error/warning/info 严重级别）、论文库统计、配置状态、外部依赖格、活跃阶段、阶段历史；支持自动刷新（refreshInterval）；无 UI 库依赖，通过 CSS 类名传递样式 |
| [src/components/InspectorPanel/index.ts](../src/components/InspectorPanel/index.ts) | 桶形导出 `InspectorPanel` 组件及相关类型 |

---

## e2e/ — Playwright E2E 测试（qa_design §7）

| 文件 | 职责 |
| ---- | ---- |
| [e2e/playwright.config.ts](../e2e/playwright.config.ts) | Playwright 配置；Chromium 单 worker 串行执行；HTML + JUnit 报告；全局 setup/teardown 钩子 |
| [e2e/global-setup.ts](../e2e/global-setup.ts) | 测试前创建/登录 E2E 用户，将 JWT 写入 `process.env.E2E_JWT` |
| [e2e/global-teardown.ts](../e2e/global-teardown.ts) | 全局清理（预留，当前为空） |
| [e2e/specs/helpers.ts](../e2e/specs/helpers.ts) | 辅助函数：`createTestProject` / `deleteTestProject`（API 调用）；`setAuthToken`（注入 localStorage）；`waitForSseEvent`（等待自定义 SSE CustomEvent） |
| [e2e/specs/e2e-001-auth.spec.ts](../e2e/specs/e2e-001-auth.spec.ts) | E2E-001：登录成功跳转；错误密码显示提示；未认证重定向 |
| [e2e/specs/e2e-002-construction.spec.ts](../e2e/specs/e2e-002-construction.spec.ts) | E2E-002：构建模式启动；LLM 请求 route 拦截（mock 返回）；阶段进度指示器可见 |
| [e2e/specs/e2e-003-review.spec.ts](../e2e/specs/e2e-003-review.spec.ts) | E2E-003：空论文库阻止综述启动；架构确认界面渲染不崩溃 |
| [e2e/specs/e2e-004-dialogue.spec.ts](../e2e/specs/e2e-004-dialogue.spec.ts) | E2E-004：深度研究对话输入发送；LLM 401 错误显示提示 |
| [e2e/specs/e2e-005-inspector-panel.spec.ts](../e2e/specs/e2e-005-inspector-panel.spec.ts) | E2E-005：注入 mock /inspect 响应；LLM 未配置时 Inspector 显示 FATAL 建议；论文库统计数字可见 |
| [e2e/specs/e2e-006-health-degraded.spec.ts](../e2e/specs/e2e-006-health-degraded.spec.ts) | E2E-006：注入 degraded DeepHealthResponse；页面显示降级状态；DB 503 不崩溃 |
| [e2e/specs/e2e-007-sse-error.spec.ts](../e2e/specs/e2e-007-sse-error.spec.ts) | E2E-007：注入 stage_error SSE 事件；LLM API Key 错误码 ERR-LLM-001 在 UI 可见；Inspector 显示 suggestion 文字 |

---

## 文件间依赖关系（关键路径）

```
docs/schema.sql
  └── backend/alembic/versions/0001_initial_schema.py  （DDL 实现）
  └── backend/app/models/                               （ORM 映射）
        └── backend/app/services/                       （业务逻辑）
              └── backend/app/api/v1/                   （HTTP 路由）

docs/api.md
  └── backend/app/schemas/                              （请求/响应 schema）
  └── src/api/                                          （前端 API 客户端）

docs/spec.md
  └── src/types/index.ts                                （共享类型定义）
```

---

## 未完全实现（仍有改进空间）

| 功能 | 位置 | 当前状态 | 剩余工作 |
| ---- | ---- | -------- | -------- |
| 综述导出 PDF | `review.py: export_outline(format=pdf)` → HTTP 501 | ❌ 存根 | 接入 WeasyPrint 或 Pandoc |
| Graph-RAG 向量检索 | `pipeline.py: graph_rag_retrieve()` | ⚠️ 关键词降级 | 接入 ChromaDB embedding + 图多跳扩展（FR-026） |
| ChromaDB 真实向量 | `stage6_storage.py: _sync_chromadb()` | ⚠️ JSON 元数据缓存 | 添加 `chromadb` 依赖，存储真实 embedding |
| PDF base64 解析 | `projects.py: add_paper(pdf_file=...)` | ⚠️ 仅保存文件 | 接入 pypdf 提取标题/作者/摘要 |
