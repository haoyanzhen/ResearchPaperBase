# API 设计文档

Author: haoyanzhen
Date:   2026-04-08

> 分层定位：API 契约层、实时通信契约层。
> 重整入口：参见 `00_index.md`；当前存在待确认的响应 envelope、错误码、SSE 认证和缺失端点问题，详见 `12_gap_decisions.md`。

本文档描述 Research Paper Base 系统的前后端通信设计，包含所有 REST API 接口定义和实时通信协议规范。

---

## 总体约定

### Base URL

```
/api/v1
```

### 认证方式

所有接口（除登录/注册外）需在请求头携带 JWT Token：

```
Authorization: Bearer <token>
```

### 统一响应结构

**成功响应**：

```json
{
  "code": 0,
  "data": { ... },
  "message": "ok"
}
```

**错误响应**：

```json
{
  "code": 40001,
  "data": null,
  "message": "错误描述"
}
```

| HTTP 状态码 | 含义 |
|------------|------|
| 200 | 操作成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 401 | 未认证或 Token 失效 |
| 403 | 无权限访问该资源 |
| 404 | 资源不存在 |
| 409 | 资源冲突（如用户名重复） |
| 422 | 参数校验失败 |
| 500 | 服务器内部错误 |

### 实时通信

LLM 流式输出和任务进度推送使用 **SSE（Server-Sent Events）**，客户端通过 `EventSource` 订阅。

SSE 事件统一格式：

```
event: <event_type>
data: <json_string>
id: <sequence_id>

```

### ViewModel 契约原则

ViewModel 契约用于把多个底层资源整理成前端界面可直接消费的数据结构。它不是数据库 schema，也不是 FR 本体；它是 API 层对 UI 信息架构的传输承接。

原则：

- ViewModel 接口应以页面或组件的读取场景命名，避免暴露底层表结构或内部任务实现。
- ViewModel 可以聚合 Project、任务、论文库、图谱、对话、综述和权限信息，但必须保持只读语义。
- ViewModel 不得返回密钥、未授权文件路径、跨用户数据或仅供服务端内部使用的字段。
- ViewModel 的外层结构应稳定，模式差异通过明确的模式上下文分支表达。
- 模式上下文必须具备可判别的类型标识，便于前端安全选择渲染分支。
- ViewModel 中的字段、枚举、权限标记和错误语义必须在 API 契约中显式定义后才能实现。
- ViewModel 不应替代业务写接口；上传、删除、重建、确认阶段、修改章节等写操作仍应使用对应业务接口。
- 若 ViewModel 聚合多个数据源，应明确缓存、刷新、权限过滤和部分失败时的降级策略。

---

## 1. 认证模块

### POST `/auth/register` — 注册

**Request Body**：

```json
{
  "username": "haoyanzhen",
  "email": "hyz@example.com",
  "password": "plain_password"
}
```

**Response 201**：

```json
{
  "user_id": "u_abc123",
  "username": "haoyanzhen",
  "email": "hyz@example.com",
  "is_admin": false,
  "created_at": "2026-04-08T10:00:00Z"
}
```

> `is_admin`：首位注册用户自动置为 `true`（FR-029），其他用户为 `false`。

---

### POST `/auth/login` — 登录

**Request Body**：

```json
{
  "credential": "haoyanzhen",
  "password": "plain_password"
}
```

> `credential` 接受用户名或邮箱。

**Response 200**：

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "user_id": "u_abc123",
    "username": "haoyanzhen",
    "email": "hyz@example.com",
    "is_admin": false
  }
}
```

---

### POST `/auth/logout` — 登出

无 Request Body。服务端将当前 Token 加入黑名单。

**Response 200**：`{ "message": "logged out" }`

---

### GET `/auth/me` — 获取当前用户信息

**Response 200**：

```json
{
  "user_id": "u_abc123",
  "username": "haoyanzhen",
  "email": "hyz@example.com",
  "is_admin": false,
  "is_active": true,
  "created_at": "2026-04-08T10:00:00Z"
}
```

> 推送配置（定时推送开关、推送间隔）为**研究主题级别**设置，位于 `PATCH /projects/{project_id}/schedule`，不在用户级别。

---

### PATCH `/auth/me` — 修改用户信息

**Request Body**（所有字段可选）：

```json
{
  "username": "new_name",
  "email": "new@example.com",
  "password": "new_password"
}
```

**Response 200**：返回更新后的用户信息（同 GET `/auth/me`）。

---

## 2. 配置模块

### GET `/config/llm` — 获取 LLM 配置列表

**Response 200**：

```json
[
  {
    "provider": "deepseek",
    "url": "https://api.deepseek.com/v1",
    "models": ["deepseek-chat", "deepseek-reasoner"],
    "default_model": "deepseek-chat",
    "temperature": 0.7,
    "max_tokens": 4096,
    "is_active": true
  }
]
```

---

### POST `/config/llm` — 添加 LLM 提供商

**Request Body**：

```json
{
  "provider": "deepseek",
  "url": "https://api.deepseek.com/v1",
  "api_key": "sk-xxx",
  "default_model": "deepseek-chat",
  "temperature": 0.7,
  "max_tokens": 4096
}
```

**Response 201**：返回创建的配置（不含 `api_key` 明文）。

---

### PATCH `/config/llm/{provider}` — 更新 LLM 配置

**Request Body**（所有字段可选）：

```json
{
  "api_key": "sk-new",
  "default_model": "deepseek-reasoner",
  "temperature": 0.5
}
```

**Response 200**：返回更新后的配置。

---

### DELETE `/config/llm/{provider}` — 删除 LLM 配置

**Response 200**：`{ "message": "deleted" }`

---

### POST `/config/llm/{provider}/test` — 测试 LLM 连接

**Response 200**：

```json
{
  "success": true,
  "latency_ms": 312,
  "model_list": ["deepseek-chat", "deepseek-reasoner"]
}
```

---

### GET `/config/databases` — 获取学术数据库配置

**Response 200**：

```json
{
  "arxiv":            { "enabled": true,  "rate_limit": 3 },
  "openalex":         { "enabled": true,  "api_key": null,    "rate_limit": 10 },
  "semantic_scholar": { "enabled": true,  "api_key": "s2-xxx","rate_limit": 5 },
  "ads":              { "enabled": false, "api_key": null,    "rate_limit": 5 }
}
```

---

### PATCH `/config/databases/{db_name}` — 更新学术数据库配置

> `db_name` 取值：`arxiv` / `openalex` / `semantic_scholar` / `ads`

**Request Body**（所有字段可选）：

```json
{
  "enabled": true,
  "api_key": "new-key",
  "rate_limit": 8
}
```

**Response 200**：返回更新后的该数据库配置。

---

### GET `/config/email` — 获取邮件配置

**Response 200**：

```json
{
  "recipients": ["r1@example.com", "r2@example.com"],
  "sender_configured": true
}
```

> 普通用户接口仅返回当前账号的收件人偏好；发件 SMTP / 发件邮箱由管理员在系统配置中统一维护。

---

### PATCH `/config/email` — 更新邮件配置

**Request Body**（所有字段可选）：

```json
{
  "recipients": ["r1@example.com"]
}
```

**Response 200**：返回更新后的个人邮件偏好。

---

### POST `/config/email/test` — 发送测试邮件

使用当前用户的 `recipients`，以及管理员维护的系统级 SMTP / 发件邮箱配置发送测试邮件。

**Response 200**：

```json
{
  "success": true,
  "message": "测试邮件已发送至 r1@example.com"
}
```

---

## 3. 研究主题（Project）模块

### GET `/projects` — 列出我的研究主题

**Query Parameters**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | string | 过滤状态（draft/running/completed 等） |
| `mode` | string | 过滤当前模式 |
| `page` | int | 页码，默认 1 |
| `page_size` | int | 每页数量，默认 20 |

**Response 200**：

```json
{
  "total": 5,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "project_id": "p_abc",
      "name": "深度学习医学图像",
      "mode": "construction",
      "status": "paused",
      "total_papers": 120,
      "valid_papers": 47,
      "created_at": "2026-04-01T08:00:00Z",
      "updated_at": "2026-04-07T15:30:00Z"
    }
  ]
}
```

---

### POST `/projects` — 创建研究主题

**Request Body**：

```json
{
  "name": "深度学习医学图像",
  "description": "聚焦 CNN 在 CT 图像分割中的应用"
}
```

**Response 201**：

```json
{
  "project_id": "p_abc",
  "name": "深度学习医学图像",
  "description": "...",
  "mode": "construction",
  "status": "draft",
  "total_papers": 0,
  "valid_papers": 0,
  "created_at": "2026-04-08T10:00:00Z"
}
```

---

### GET `/projects/{project_id}` — 获取研究主题详情

**Response 200**：返回完整的 project 对象，含 `current_stage`、`push_status` 等字段。

---

### PATCH `/projects/{project_id}` — 更新研究主题基本信息

**Request Body**（所有字段可选）：

```json
{
  "name": "新名称",
  "description": "新描述"
}
```

**Response 200**：返回更新后的 project 对象。

---

### DELETE `/projects/{project_id}` — 删除研究主题

**Response 200**：`{ "message": "deleted" }`

---

### POST `/projects/{project_id}/mode` — 切换研究模式

**Request Body**：

```json
{
  "target_mode": "deep_research",
  "reason": "构建完成，开始深度研究"
}
```

**Response 200**：

```json
{
  "project_id": "p_abc",
  "previous_mode": "construction",
  "current_mode": "deep_research",
  "switched_at": "2026-04-08T11:00:00Z"
}
```

---

## 4. 构建模式

### POST `/projects/{project_id}/construction/start` — 启动构建流程

**Request Body**：

```json
{
  "databases": ["arxiv", "openalex", "semantic_scholar"],
  "score_threshold": 7
}
```

**Response 202**：

```json
{
  "task_id": "task_xyz",
  "project_id": "p_abc",
  "stage": 1,
  "status": "running",
  "message": "检索词生成中..."
}
```

---

### GET `/projects/{project_id}/construction/status` — 获取构建当前状态

**Response 200**：

```json
{
  "current_stage": 3,
  "stage_name": "评分与筛选",
  "status": "paused",
  "stage_result": {
    "total_papers": 230,
    "valid_papers": 52,
    "threshold": 7
  },
  "started_at": "2026-04-08T10:00:00Z"
}
```

---

### GET `/projects/{project_id}/construction/keywords` — 获取检索词列表

**Response 200**：

```json
[
  {
    "keyword_id": "kw_1",
    "search_word": "deep learning medical imaging",
    "boolean_expressions": {
      "arxiv": "ti:deep learning AND abs:medical imaging",
      "openalex": "(deep learning OR CNN) AND medical imaging"
    },
    "is_selected": true,
    "searched_papers_total": 87
  }
]
```

---

### PATCH `/projects/{project_id}/construction/keywords` — 更新检索词（阶段1交互）

**Request Body**：

```json
{
  "keywords": [
    {
      "keyword_id": "kw_1",
      "search_word": "deep learning CT scan",
      "is_selected": true
    },
    {
      "search_word": "用户新增的关键词",
      "is_selected": true
    }
  ]
}
```

**Response 200**：返回更新后的完整关键词列表。

---

### POST `/projects/{project_id}/construction/stages/{stage}/action` — 阶段用户操作

> `stage` 取值：1-6（第7阶段全自动）

**Request Body**：

```json
{
  "action": "confirm",
  "modifications": {}
}
```

| `action` | 含义 | `modifications` |
|----------|------|-----------------|
| `confirm` | 确认本阶段结果，继续执行 | 可选，传入修改内容 |
| `retry` | 重新执行本阶段 | 可选，传入参数调整 |
| `skip` | 跳过本阶段 | 不需要 |

**阶段对应的 `modifications` 结构**：

| stage | 可修改内容 |
|-------|-----------|
| 1 | `{ "keywords": [...] }` — 检索词列表 |
| 2 | `{ "removed_ids": [...] }` — 从结果中移除的论文 ID |
| 3 | `{ "score_overrides": [{"paper_id":"...", "is_valid": true}] }` — 覆盖评分结果 |
| 4 | `{ "retry_ids": [...] }` — 指定重新下载的论文 |
| 5 | `{ "analysis_overrides": [{"paper_id":"...", "summary":"..."}] }` — 覆盖 AI 分析 |
| 6 | 无可修改内容，直接 confirm 进入邮件发送 |

**Response 200**：

```json
{
  "stage": 3,
  "action": "confirm",
  "next_stage": 4,
  "status": "running",
  "message": "已确认，开始下载与解析..."
}
```

---

### GET `/projects/{project_id}/construction/stream` — 构建进度 SSE 流

客户端通过 `EventSource` 订阅此端点，实时接收构建阶段的进度推送。

**SSE 事件类型**：

```
event: stage_start
data: {"stage": 2, "stage_name": "检索与汇总", "started_at": "..."}

event: stage_progress
data: {"stage": 2, "progress": 45, "detail": "已检索 arXiv: 120 篇"}

event: stage_pause
data: {"stage": 2, "status": "paused", "result": {"total": 230, ...}}

event: stage_error
data: {"stage": 2, "error": "OpenAlex API 超时", "retryable": true}

event: pipeline_complete
data: {"total_papers": 230, "valid_papers": 52, "email_sent": true}
```

---

## 5. 论文模块

### GET `/projects/{project_id}/papers` — 获取课题关联论文列表

**Query Parameters**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `is_valid` | bool | 过滤有效/无效论文 |
| `push_status` | bool | 过滤推送状态 |
| `keyword` | string | 标题/摘要关键词搜索 |
| `order_by` | string | 排序字段（`total_score`/`pub_date`/`created_at`） |
| `page` | int | 页码，默认 1 |
| `page_size` | int | 默认 20 |

**Response 200**：

```json
{
  "total": 52,
  "items": [
    {
      "paper_id": "paper_1",
      "title": "A Novel CNN for CT Segmentation",
      "authors": ["John Doe"],
      "pub_date": "2024-03-15",
      "venue": "Nature Medicine",
      "abstract": "...",
      "total_score": 9,
      "reference_score": 5,
      "technical_score": 4,
      "is_valid": true,
      "push_status": false,
      "download_status": "success",
      "ai_analysis": {
        "summary": "提出了一种...",
        "highlights": ["创新点1", "创新点2"],
        "relevance": "与课题高度相关...",
        "methods": "采用 U-Net 变体..."
      }
    }
  ]
}
```

---

### POST `/projects/{project_id}/papers` — 手动添加论文

**Request Body**（三选一）：

```json
{ "doi": "10.1234/example" }
```

```json
{ "arxiv_id": "2401.12345" }
```

```json
{ "pdf_file": "<base64>" }
```

**Response 201**：

```json
{
  "paper_id": "paper_99",
  "title": "解析得到的标题",
  "status": "analyzing",
  "message": "论文已上传，正在解析..."
}
```

---

### GET `/projects/{project_id}/papers/{paper_id}` — 获取论文详情

**Response 200**：返回完整论文对象，含 `pdf_path`、`ai_analysis` 等全部字段。

---

### PATCH `/projects/{project_id}/papers/{paper_id}/score` — 修改论文评分

**Request Body**：

```json
{
  "reference_score": 4,
  "technical_score": 5,
  "scoring_reason": "手动调整：实验设计非常有参考价值"
}
```

**Response 200**：返回更新后的关联记录（含新 `total_score` 和 `is_valid`）。

---

### DELETE `/projects/{project_id}/papers/{paper_id}` — 从课题移除论文

**Response 200**：`{ "message": "removed from project" }`（不删除全局论文记录）

---

## 6. 深度研究模式

### GET `/projects/{project_id}/dialogues` — 获取对话会话列表

**Response 200**：

```json
[
  {
    "dialogue_id": "dlg_1",
    "title": "CNN 与 Transformer 的对比分析",
    "sub_mode": "technical",
    "status": "active",
    "turn_count": 12,
    "summary": "讨论了两类方法的核心差异...",
    "tags": ["架构对比", "注意力机制"],
    "last_active_at": "2026-04-07T20:00:00Z"
  }
]
```

---

### POST `/projects/{project_id}/dialogues` — 新建对话会话

**Request Body**：

```json
{
  "title": "实验方案讨论",
  "sub_mode": "experiment"
}
```

**Response 201**：返回新建的 dialogue 对象，`turn_count` 为 0。

---

### GET `/projects/{project_id}/dialogues/{dialogue_id}` — 获取会话详情

**Response 200**：返回完整 dialogue 对象（含 `summary`、`tags`）。

---

### PATCH `/projects/{project_id}/dialogues/{dialogue_id}` — 更新会话元数据

**Request Body**（所有字段可选）：

```json
{
  "title": "新标题",
  "sub_mode": "theory",
  "tags": ["tag1"],
  "status": "archived"
}
```

**Response 200**：返回更新后的 dialogue 对象。

---

### DELETE `/projects/{project_id}/dialogues/{dialogue_id}` — 删除对话会话

**Response 200**：`{ "message": "deleted" }`

---

### GET `/projects/{project_id}/dialogues/{dialogue_id}/turns` — 获取完整对话历史

**Query Parameters**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `offset` | int | 起始轮次（默认 0，从第1轮开始） |
| `limit` | int | 返回轮次数（默认全部） |

**Response 200**：

```json
[
  {
    "turn_id": "turn_1",
    "turn_index": 1,
    "user_content": "请对比 U-Net 和 TransUNet 的架构差异",
    "assistant_content": "两者的核心差异体现在...",
    "sub_mode_before": "technical",
    "sub_mode_after": "technical",
    "referenced_papers": ["paper_1", "paper_3"],
    "input_tokens": 24,
    "output_tokens": 412,
    "created_at": "2026-04-07T19:00:00Z"
  }
]
```

---

### POST `/projects/{project_id}/dialogues/{dialogue_id}/turns` — 发送消息（SSE 流）

**Request Body**：

```json
{
  "user_content": "TransUNet 在小数据集上的表现如何？",
  "sub_mode": "technical"
}
```

**Response**：`Content-Type: text/event-stream`（SSE 流）

**SSE 事件类型**：

```
event: turn_start
data: {"turn_index": 13, "sub_mode": "technical"}

event: text_delta
data: {"delta": "根据论文 [paper_3] 的实验结果，"}

event: text_delta
data: {"delta": "TransUNet 在 50 样本以下的场景中..."}

event: turn_complete
data: {
  "turn_id": "turn_13",
  "turn_index": 13,
  "assistant_content": "根据论文 [paper_3]...",
  "sub_mode_before": "technical",
  "sub_mode_after": "technical",
  "referenced_papers": ["paper_3"],
  "input_tokens": 31,
  "output_tokens": 287
}
```

---

### POST `/projects/{project_id}/dialogues/{dialogue_id}/summarize` — 生成对话摘要

**Response 200**：

```json
{
  "dialogue_id": "dlg_1",
  "summary": "本次对话聚焦于 CNN 与 Transformer 的架构差异..."
}
```

---

### GET `/projects/{project_id}/graph` — 获取知识图谱数据

**Query Parameters**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `format` | string | 返回格式（`json`/`graphml`），默认 `json` |
| `node_types` | string | 过滤节点类型，逗号分隔（如 `paper,keyword`） |

**Response 200**（`format=json`）：

```json
{
  "nodes": [
    { "id": "paper_1", "type": "paper", "label": "A Novel CNN...", "score": 9 },
    { "id": "keyword_deep_learning", "type": "keyword", "label": "deep learning" }
  ],
  "edges": [
    { "source": "paper_1", "target": "keyword_deep_learning", "type": "HAS_KEYWORD", "weight": 1.0 }
  ],
  "stats": { "node_count": 150, "edge_count": 420 }
}
```

---

### POST `/projects/{project_id}/graph/rebuild` — 重建知识图谱

**Response 202**：

```json
{
  "task_id": "task_graph_rebuild",
  "message": "知识图谱重建任务已提交"
}
```

---

## 7. 综述模式

### GET `/projects/{project_id}/review/status` — 综述模式当前状态

**Response 200**：

```json
{
  "project_id": "p_abc",
  "current_stage": 3,
  "stage_name": "撰写章节内容",
  "stage_status": "running",
  "outline_id": "ol_1",
  "outline_status": "confirmed",
  "total_chapters": 5,
  "completed_chapters": 2
}
```

---

### POST `/projects/{project_id}/review/start` — 启动综述流程

**Request Body**：

```json
{
  "topic_hint": "重点关注近三年的 Transformer 方法"
}
```

**Response 202**：

```json
{
  "task_id": "task_review_abc",
  "outline_id": "ol_1",
  "stage": 1,
  "status": "running"
}
```

---

### GET `/projects/{project_id}/review/outlines` — 获取综述架构版本列表

**Response 200**：

```json
[
  {
    "outline_id": "ol_1",
    "version": 1,
    "status": "confirmed",
    "confirmed_at": "2026-04-05T12:00:00Z",
    "created_at": "2026-04-05T10:00:00Z"
  }
]
```

---

### GET `/projects/{project_id}/review/outlines/{outline_id}` — 获取综述架构详情

**Response 200**：

```json
{
  "outline_id": "ol_1",
  "version": 1,
  "topic_expansion": "本综述聚焦于深度学习在医学图像分割中的应用，重点关注...",
  "outline": {
    "title": "深度学习医学图像分割综述",
    "sections": [
      {
        "index": 1,
        "title": "引言",
        "type": "introduction",
        "key_points": ["研究背景", "研究意义"]
      }
    ]
  },
  "status": "confirmed"
}
```

---

### PATCH `/projects/{project_id}/review/outlines/{outline_id}` — 修改综述架构

**Request Body**（阶段1或阶段2用户交互）：

```json
{
  "topic_expansion": "用户修改后的课题描述",
  "outline": {
    "title": "调整后的综述标题",
    "sections": [ ... ]
  }
}
```

**Response 200**：返回更新后的完整 outline 对象。

---

### POST `/projects/{project_id}/review/outlines/{outline_id}/confirm` — 确认综述架构，进入章节撰写

**Response 200**：

```json
{
  "outline_id": "ol_1",
  "status": "confirmed",
  "confirmed_at": "2026-04-08T10:00:00Z",
  "message": "架构已确认，开始撰写章节内容..."
}
```

---

### GET `/projects/{project_id}/review/outlines/{outline_id}/chapters` — 获取所有章节状态

**Response 200**：

```json
[
  {
    "chapter_id": "ch_1",
    "chapter_index": 1,
    "title": "引言",
    "status": "completed",
    "iteration_count": 2,
    "completed_at": "2026-04-08T11:00:00Z"
  },
  {
    "chapter_id": "ch_2",
    "chapter_index": 2,
    "title": "相关工作",
    "status": "writing",
    "iteration_count": 0
  }
]
```

---

### GET `/projects/{project_id}/review/outlines/{outline_id}/chapters/{chapter_id}` — 获取章节完整内容

**Response 200**：返回完整 chapter 对象，含 `content`、`citations`、`review_history`。

---

### PATCH `/projects/{project_id}/review/outlines/{outline_id}/chapters/{chapter_id}` — 用户修改章节内容

**Request Body**（所有字段可选）：

```json
{
  "content": "用户修改后的章节正文...",
  "citations": [ ... ]
}
```

**Response 200**：返回更新后的 chapter 对象。

---

### POST `/projects/{project_id}/review/outlines/{outline_id}/chapters/{chapter_id}/review` — 触发章节自动审查

**Response 202**：

```json
{
  "chapter_id": "ch_2",
  "status": "reviewing",
  "message": "自动审查已启动"
}
```

审查完成后通过 SSE 流推送结果（见下方 SSE 流端点）。

---

### POST `/projects/{project_id}/review/outlines/{outline_id}/compile` — 汇总成完整综述文章

**Response 202**：

```json
{
  "task_id": "task_compile_abc",
  "message": "正在汇总综述文章..."
}
```

---

### GET `/projects/{project_id}/review/outlines/{outline_id}/export` — 导出综述文章

**Query Parameters**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `format` | string | 导出格式：`markdown` / `pdf` / `docx` |

**Response 200**：返回对应格式的文件流（`Content-Disposition: attachment`）。

---

### GET `/projects/{project_id}/review/stream` — 综述流程进度 SSE 流

**SSE 事件类型**：

```
event: stage_start
data: {"stage": 3, "stage_name": "撰写章节内容"}

event: chapter_writing
data: {"chapter_index": 2, "title": "相关工作", "status": "writing"}

event: chapter_reviewing
data: {"chapter_index": 2, "iteration": 1, "issues": ["引用不足"]}

event: chapter_complete
data: {"chapter_index": 2, "iteration_count": 2}

event: review_text_delta
data: {"chapter_index": 2, "delta": "近年来，Transformer 在..."}

event: pipeline_complete
data: {"outline_id": "ol_1", "total_chapters": 5, "compiled": true}
```

---

## 8. 任务管理模块

### GET `/tasks` — 获取任务列表

**Query Parameters**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | string | 过滤状态（running/paused/completed/failed） |
| `project_id` | string | 过滤特定课题的任务 |

**Response 200**：

```json
[
  {
    "task_id": "task_xyz",
    "project_id": "p_abc",
    "task_type": "construction",
    "status": "running",
    "stage": 2,
    "created_at": "2026-04-08T10:00:00Z"
  }
]
```

---

### POST `/tasks/{task_id}/pause` — 暂停任务

**Response 200**：`{ "task_id": "...", "status": "paused" }`

---

### POST `/tasks/{task_id}/resume` — 恢复任务

**Response 200**：`{ "task_id": "...", "status": "running" }`

---

### POST `/tasks/{task_id}/cancel` — 取消任务

**Response 200**：`{ "task_id": "...", "status": "cancelled" }`

---

## 9. 推荐模块

### GET `/recommendations` — 获取推荐内容列表

**Query Parameters**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `content_type` | string | 过滤类型（insight/conclusion/experiment_design） |
| `keyword` | string | 关键词搜索 |
| `order_by` | string | 排序（`created_at`/`like_count`/`view_count`） |
| `page` | int | 页码，默认 1 |
| `page_size` | int | 默认 20 |

**Response 200**：

```json
{
  "total": 30,
  "items": [
    {
      "rec_id": "rec_1",
      "author_name": "haoyanzhen",
      "contact": "hyz@example.com",
      "content_type": "insight",
      "title": "关于 TransUNet 在小样本场景的局限性",
      "content": "通过深度研究发现...",
      "tags": ["transformer", "small dataset"],
      "like_count": 12,
      "view_count": 87,
      "created_at": "2026-04-07T15:00:00Z"
    }
  ]
}
```

---

### POST `/recommendations` — 发布推荐内容

**Request Body**：

```json
{
  "content_type": "insight",
  "title": "关于 TransUNet 的局限性",
  "content": "通过深度研究发现...",
  "tags": ["transformer"],
  "contact": "hyz@example.com",
  "dialogue_id": "dlg_1"
}
```

**Response 201**：返回创建的推荐内容对象。

---

### DELETE `/recommendations/{rec_id}` — 删除自己的推荐内容

**Response 200**：`{ "message": "deleted" }`

---

### POST `/recommendations/{rec_id}/like` — 点赞

**Response 200**：`{ "rec_id": "...", "like_count": 13 }`

---

## 9. 管理员模块

### GET `/admin/system-config/email` — 获取系统邮件配置

**Response 200**：

```json
{
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "sender_email": "sender@gmail.com",
  "sender_password_configured": true
}
```

---

### PATCH `/admin/system-config/email` — 更新系统邮件配置

**Request Body**（所有字段可选）：

```json
{
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "sender_email": "sender@gmail.com",
  "sender_password": "app_password"
}
```

**Response 200**：返回更新后的系统邮件配置；不返回 `sender_password` 明文。

---

## 10. 前后端通信设计

### 10.1 通信协议选型

| 场景 | 协议 | 原因 |
|------|------|------|
| 普通增删改查 | HTTP REST | 无状态，简单可靠 |
| LLM 流式输出 | SSE（Server-Sent Events） | 单向服务器推送，天然适合流式文本；比 WebSocket 更轻量 |
| 构建/综述流程进度 | SSE | 同上，任务状态推送为单向 |
| 文件上传（PDF） | HTTP Multipart | 标准文件上传 |

### 10.2 SSE 客户端使用约定

```typescript
// 构建模式进度监听示例
const source = new EventSource(
  `/api/v1/projects/${projectId}/construction/stream`,
  { headers: { Authorization: `Bearer ${token}` } }
);

source.addEventListener('stage_pause', (e) => {
  const data = JSON.parse(e.data);
  // 通知前端渲染阶段交互界面
  showStageInteraction(data);
});

source.addEventListener('pipeline_complete', () => {
  source.close();
});

source.onerror = () => {
  source.close();
  // 触发重连逻辑
};
```

```typescript
// 深度研究对话流式输出示例
async function sendMessage(dialogueId: string, content: string) {
  const response = await fetch(
    `/api/v1/projects/${projectId}/dialogues/${dialogueId}/turns`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        Accept: 'text/event-stream',
      },
      body: JSON.stringify({ user_content: content, sub_mode: 'technical' }),
    }
  );

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    // 解析 SSE 数据帧，追加到对话显示区
    parseSSEChunk(decoder.decode(value));
  }
}
```

### 10.3 错误码约定

| code | 含义 |
|------|------|
| 0 | 成功 |
| 40001 | 参数缺失或格式错误 |
| 40101 | Token 缺失 |
| 40102 | Token 失效或过期 |
| 40301 | 无权访问该资源（不属于当前用户） |
| 40401 | 资源不存在 |
| 40901 | 用户名或邮箱已存在 |
| 42201 | 参数校验失败（Pydantic） |
| 42901 | 操作冲突（如：任务已在运行中） |
| 50001 | LLM 调用失败 |
| 50002 | 外部学术 API 调用失败 |
| 50003 | 数据库操作失败 |
| 50099 | 未知服务器错误 |

### 10.4 分页约定

所有列表接口统一使用以下分页参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码（从1开始） |
| `page_size` | int | 20 | 每页数量（最大100） |

响应统一包含：

```json
{
  "total": 150,
  "page": 1,
  "page_size": 20,
  "items": [ ... ]
}
```

---

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0 | 2026-04-08 | 初始版本，覆盖所有功能模块 |
