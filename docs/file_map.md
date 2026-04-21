# 项目文件功能目录

**文档版本**：v1.0 · 2026-04-21
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
| [spec.md](spec.md) | 需求规格说明书（v1.6）；FR-001~FR-028 完整功能需求；**修改需评审** |
| [api.md](api.md) | API 设计文档；所有 HTTP 端点请求/响应格式；前后端接口契约 |
| [schema.sql](schema.sql) | PostgreSQL DDL（v1.0）；12 张表结构、索引、约束；**数据层唯一权威** |
| [ui_design.md](ui_design.md) | 前端界面设计草稿；ASCII 线框图；各页面布局与交互逻辑 |
| [ADR_design.md](ADR_design.md) | 架构决策记录（ADR）；技术选型理由与取舍 |
| [file_map.md](file_map.md) | **本文件**；项目文件功能目录 |
| [VibeCoding_record.md](VibeCoding_record.md) | 开发过程记录；设计演进历史 |
| [media/](media/) | 文档附图（logo、RAG 结构图等） |

---

## backend/ — Python 后端

### 入口与配置

| 文件 | 职责 |
|------|------|
| [backend/app/main.py](../backend/app/main.py) | FastAPI 应用入口；注册路由、CORS 中间件、/health 端点 |
| [backend/requirements.txt](../backend/requirements.txt) | Python 依赖声明 |
| [backend/.env.example](../backend/.env.example) | 环境变量模板（DATABASE\_URL / SECRET\_KEY / APP\_ENV 等） |
| [backend/alembic.ini](../backend/alembic.ini) | Alembic 迁移配置；指向 `alembic/` 脚本目录 |

### backend/app/core/ — 基础设施

| 文件 | 职责 |
|------|------|
| [core/config.py](../backend/app/core/config.py) | 应用配置（pydantic-settings）；从 .env 读取 DATABASE\_URL / SECRET\_KEY 等 |
| [core/database.py](../backend/app/core/database.py) | 异步数据库引擎（asyncpg）；`get_db()` 依赖注入会话工厂 |
| [core/security.py](../backend/app/core/security.py) | JWT 生成/验证；bcrypt 密码哈希；内存 token 黑名单（登出用） |
| [core/deps.py](../backend/app/core/deps.py) | FastAPI 依赖项；`get_current_user()` — Bearer token → User 对象 |

### backend/app/models/ — ORM 数据层

对应 schema.sql 的 12 张表，是数据库结构的 Python 映射。

| 文件 | 对应表（schema.sql 编号） |
|------|--------------------------|
| [models/base.py](../backend/app/models/base.py) | SQLAlchemy `DeclarativeBase` 公共基类 |
| [models/user.py](../backend/app/models/user.py) | `users`(1) · `user_configs`(2) |
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
| [schemas/auth.py](../backend/app/schemas/auth.py) | FR-001 注册/登录/用户信息相关 schema |
| [schemas/config.py](../backend/app/schemas/config.py) | FR-002~004 LLM / 数据库 / 邮件配置相关 schema |
| [schemas/project.py](../backend/app/schemas/project.py) | FR-005~011 项目、论文、任务、导出、定时、推荐相关 schema |

### backend/app/services/ — 业务逻辑层

| 文件 | 职责 |
|------|------|
| [services/auth\_service.py](../backend/app/services/auth_service.py) | 用户注册/认证/信息更新；密码校验；last\_login\_at 更新 |
| [services/config\_service.py](../backend/app/services/config_service.py) | 基于 user\_configs 的 Key-Value 读写；LLM / 数据库 / 邮件配置的序列化与反序列化 |
| [services/project\_service.py](../backend/app/services/project_service.py) | 项目 CRUD；模式切换；论文关联管理；评分更新；推荐 CRUD；定时配置 |

### backend/app/api/v1/ — HTTP 路由层

| 文件 | 覆盖端点 | 对应 FR |
|------|----------|---------|
| [api/v1/router.py](../backend/app/api/v1/router.py) | 注册所有子路由到 `/api/v1` | — |
| [api/v1/auth.py](../backend/app/api/v1/auth.py) | `POST /auth/register` · `login` · `logout` · `GET/PATCH /auth/me` | FR-001 |
| [api/v1/config.py](../backend/app/api/v1/config.py) | `GET/POST/PATCH/DELETE /config/llm` · `/config/databases` · `/config/email` | FR-002~004 |
| [api/v1/projects.py](../backend/app/api/v1/projects.py) | `/projects` CRUD · `/mode` · `/stage-records` · `/papers` · `/export` · `/schedule` · `/recommendations` | FR-005~011 |
| [api/v1/tasks.py](../backend/app/api/v1/tasks.py) | `GET /tasks` · `POST /tasks/{id}/pause·resume·cancel` | FR-008 |

### backend/app/utils/ — 工具函数

| 文件 | 职责 |
|------|------|
| [utils/ids.py](../backend/app/utils/ids.py) | `new_id(prefix)` — 生成带前缀的 nanoid 短 ID（如 `p_x3k9mz1abcde`） |

### backend/alembic/ — 数据库迁移

| 文件 | 职责 |
|------|------|
| [alembic/env.py](../backend/alembic/env.py) | 异步迁移环境；从 `app.core.config` 读取 DATABASE\_URL；注册完整 metadata |
| [alembic/script.py.mako](../backend/alembic/script.py.mako) | 迁移文件模板 |
| [alembic/versions/0001\_initial\_schema.py](../backend/alembic/versions/0001_initial_schema.py) | 初始迁移：创建全部 12 张表及索引（对应 schema.sql v1.0） |

### backend/scripts/ — 运维脚本

| 文件 | 职责 |
|------|------|
| [scripts/init\_db.py](../backend/scripts/init_db.py) | 开发环境一键建库；封装 `alembic upgrade head` 并提供友好错误提示 |

---

## src/ — TypeScript 前端 API 客户端层

### src/types/

| 文件 | 职责 |
|------|------|
| [src/types/index.ts](../src/types/index.ts) | 跨模块共享类型定义（唯一权威来源）；枚举联合、12 张表实体接口、JSONB 结构类型、ChromaDB / NetworkX 图类型、业务流程类型 |

### src/api/

所有方法通过 `http` 客户端调用，统一响应解包（`code !== 0` 时抛 `ApiError`）。

| 文件 | 职责 | 对应 api.md 章节 |
|------|------|-----------------|
| [src/api/client.ts](../src/api/client.ts) | 基础 HTTP 客户端；`ApiError`；`tokenStore`（localStorage 令牌管理） | §总体约定 |
| [src/api/auth.ts](../src/api/auth.ts) | `authApi`：注册 / 登录（自动存 token）/ 登出 / 获取&修改当前用户 | §1 |
| [src/api/config.ts](../src/api/config.ts) | `configApi`：LLM / 学术数据库 / 邮件配置的增删改查与连接测试 | §2 |
| [src/api/projects.ts](../src/api/projects.ts) | `projectsApi`：项目 CRUD / 模式切换 / 检索历史 / 论文管理 / 导出 / 定时配置；`recommendationsApi`：推荐内容列表、发布、点赞、删除 | §3 §5（部分）§9 |
| [src/api/construction.ts](../src/api/construction.ts) | `constructionApi`：启动构建 / 状态查询 / 检索词管理 / 阶段操作 / SSE 流 URL | §4 |
| [src/api/dialogues.ts](../src/api/dialogues.ts) | `dialoguesApi`：对话会话 CRUD / 轮次历史 / 消息发送（SSE fetch）/ 对话摘要 / 知识图谱获取与重建 | §6 |
| [src/api/review.ts](../src/api/review.ts) | `reviewApi`：启动综述 / 架构版本管理 / 章节管理 / 汇总编译 / 导出（文件流）/ SSE 流 URL | §7 |
| [src/api/tasks.ts](../src/api/tasks.ts) | `tasksApi`：任务列表 / 暂停 / 恢复 / 取消 | §8 |
| [src/api/index.ts](../src/api/index.ts) | 统一桶形导出（re-export 所有 API 模块及 `ApiError` / `tokenStore`） | — |

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

## 未实现（存根 / 待后续阶段开发）

| 功能 | 存根位置 | 说明 |
|------|----------|------|
| FR-009 数据导出 Worker | `projects.py: export_data()` | 返回占位 task\_id，实际 Excel/ZIP 生成由 Agent Worker 实现 |
| FR-007 手动添加论文解析 | `projects.py: add_paper()` | 返回占位 paper\_id，实际 DOI/arXiv 抓取与 PDF 解析由 Agent 实现 |
| 构建模式 Agent 链 | — | FR-012~018（7 阶段执行逻辑） |
| 深度研究 Agent 链 | — | FR-025~028（Graph-RAG 对话、摘要生成） |
| 综述模式 Agent 链 | — | FR-019~024（综述生成、章节审查） |
| ChromaDB 向量库操作 | — | 与 papers 写入同事务，Agent 层负责 |
| NetworkX 图数据库操作 | — | 构建模式阶段 6 写入，每日深夜全量重建 |
| 定时调度器 | — | FR-010 next\_push\_at 计算与触发，Celery/APScheduler 实现 |
