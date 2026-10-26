# 质量保障与错误诊断设计文档

**文档版本**：v1.0 · 2026-04-24
**关联文档**：02_product_requirements.md v1.7 / 07_api_contract.md / ../file_map.md v1.8
**覆盖范围**：全部 FR-001~FR-029；三模式流水线；SSE 实时通信层；数据库层

> 分层定位：质量、测试与可观测层。
> 重整入口：参见 `00_index.md`；本文负责验证、诊断和可观测性，不应作为业务字段、状态枚举或 API 响应的唯一权威。

---

## 1. 设计目标

本文档面向 Research Paper Base 系统的完整 QA 体系，解决三类核心问题：

| 类别 | 问题 | 目标 |
|------|------|------|
| **状态可观测** | 任意时刻无法判断系统/流水线处于哪个阶段、是否健康 | 提供多粒度实时状态探针 |
| **错误可诊断** | 错误发生后只能看到 "failed"，不知道根因在哪里 | 实时、结构化、带上下文的错误信封 |
| **质量可验证** | 无法验证各 FR 的逻辑正确性，尤其是 Agent 行为 | 分层测试策略覆盖单元/集成/端到端 |

---

## 2. 多方案对比

### 方案 A — 中心化错误总线

所有错误经统一消息队列路由到前端同一 SSE 频道。

```
Agent Stage → ErrorBus (asyncio.Queue) → GET /stream → 前端
```

**优点**：前端只订阅一个端点；实现最简单。
**缺点**：错误与正常事件混流，难以区分；缺少根因上下文；诊断需要额外日志查询。

**适用场景**：小型单阶段系统，错误类型单一。

---

### 方案 B — 分层诊断协议（结构化错误信封 + 诊断快照端点）

每层均输出带完整上下文的结构化错误信封；SSE 实时推送；`/inspect` 端点提供诊断快照。

```
Agent Stage
  ├─ SSE: stage_error{code, msg, trace, retryable, suggestion}  →  前端 Inspector Panel
  └─ DB:  stage_records.error(JSON)                            →  /inspect 端点按需查询
```

**优点**：错误自描述（含错误码、建议操作）；可追溯（DB 持久化）；前端可渲染结构化诊断卡片；支持区分可重试/不可重试。
**缺点**：需要定义完整错误码体系；前端需实现 Inspector 组件。

**适用场景**：多阶段流水线 + 实时用户交互（本系统主场景）。

---

### 方案 C — 端到端契约测试驱动

以 OpenAPI 契约为基准，自动校验请求/响应格式；健康探针周期性验证所有外部依赖。

```
OpenAPI Schema → schemathesis 自动测试
外部 API       → /health/deep 周期探针
```

**优点**：无需人工编写接口测试；发现回归早。
**缺点**：仅覆盖接口层，不覆盖 Agent 业务逻辑；不适合实时错误推送。

**适用场景**：CI/CD 回归防御层，与方案 A/B 组合使用。

---

### 选用方案

**采用方案 B 为主体设计，方案 C 作为 CI 层补充。**

方案 B 具备实时性（SSE 推送）、细致性（结构化错误信封含 traceback 和 suggestion）、可诊断性（`/inspect` 快照端点），与系统的多阶段流水线架构高度契合，是唯一能在错误发生的毫秒级内将完整根因信息传达给用户和开发者的方案。

---

## 3. 错误码体系

### 3.1 错误码分类

```
ERR-{层}-{模块}-{序号}

层：
  SYS  系统/基础设施层（数据库连接、配置缺失等）
  AUTH 认证/权限层
  LLM  LLM API 调用层
  EXT  外部 API 层（学术数据库、邮件服务）
  AGT  Agent 业务逻辑层
  VAL  数据验证层
```

### 3.2 完整错误码表

#### 系统层 (SYS)

| 错误码 | 名称 | 含义 | 可重试 | 建议操作 |
|--------|------|------|--------|----------|
| `ERR-SYS-DB-001` | DB_CONNECTION_FAILED | PostgreSQL 连接失败 | ✓ | 检查 DATABASE_URL 配置；确认数据库服务运行 |
| `ERR-SYS-DB-002` | DB_QUERY_TIMEOUT | 查询超时（>30s） | ✓ | 检查慢查询；考虑添加索引 |
| `ERR-SYS-DB-003` | DB_CONSTRAINT_VIOLATION | 唯一约束冲突 | ✗ | 检查重复提交逻辑 |
| `ERR-SYS-DB-004` | DB_DETACHED_INSTANCE | ORM 对象脱离 Session | ✗ | BackgroundTask 使用独立 AsyncSession |
| `ERR-SYS-CFG-001` | CONFIG_MISSING | 必要配置项缺失 | ✗ | 在设置界面补充 LLM/数据库配置 |
| `ERR-SYS-CFG-002` | CONFIG_INVALID_FORMAT | 配置值格式非法 | ✗ | 检查 config_value JSON 格式 |

#### 认证层 (AUTH)

| 错误码 | 名称 | 含义 | 可重试 | 建议操作 |
|--------|------|------|--------|----------|
| `ERR-AUTH-001` | TOKEN_EXPIRED | JWT 已过期 | ✗ | 重新登录 |
| `ERR-AUTH-002` | TOKEN_INVALID | JWT 签名无效 | ✗ | 清除本地 token，重新登录 |
| `ERR-AUTH-003` | ACCOUNT_DISABLED | 账号已被管理员禁用 | ✗ | 联系管理员 |
| `ERR-AUTH-004` | FORBIDDEN | 无权限（非管理员访问管理接口） | ✗ | 确认账号权限 |

#### LLM 层 (LLM)

| 错误码 | 名称 | 含义 | 可重试 | 建议操作 |
|--------|------|------|--------|----------|
| `ERR-LLM-001` | API_KEY_INVALID | API 密钥无效或已过期 | ✗ | 在配置界面更新 API 密钥 |
| `ERR-LLM-002` | RATE_LIMIT_EXCEEDED` | 达到速率限制 | ✓ | 等待后自动重试；建议配置备用模型 |
| `ERR-LLM-003` | CONTEXT_TOO_LONG | 输入超过模型上下文窗口 | ✗ | 缩短对话历史或论文上下文长度 |
| `ERR-LLM-004` | JSON_PARSE_FAILED | LLM 输出无法解析为预期 JSON | ✓ | 自动重试（最多3次）；检查 prompt 格式约束 |
| `ERR-LLM-005` | TIMEOUT` | LLM 调用超时（>120s） | ✓ | 检查网络连接；考虑切换更快的模型 |
| `ERR-LLM-006` | NO_CONFIG` | 用户和系统均无 LLM 配置 | ✗ | 在设置界面配置 LLM 或联系管理员 |

#### 外部 API 层 (EXT)

| 错误码 | 名称 | 含义 | 可重试 | 建议操作 |
|--------|------|------|--------|----------|
| `ERR-EXT-ARXIV-001` | ARXIV_UNREACHABLE | arXiv API 不可达 | ✓ | 检查网络；arXiv 可能临时维护 |
| `ERR-EXT-ARXIV-002` | ARXIV_RATE_LIMIT` | 超过 arXiv 访问频率限制 | ✓ | 降低 batch_size；增加请求间隔 |
| `ERR-EXT-OA-001` | OPENALEX_KEY_INVALID` | OpenAlex API 密钥无效 | ✗ | 更新 OpenAlex API 配置 |
| `ERR-EXT-SS-001` | SEMANTIC_SCHOLAR_TIMEOUT` | Semantic Scholar 超时 | ✓ | 自动重试 |
| `ERR-EXT-ADS-001` | ADS_KEY_INVALID` | ADS API 密钥无效 | ✗ | 更新 ADS API 配置 |
| `ERR-EXT-PDF-001` | PDF_DOWNLOAD_FAILED` | PDF 下载失败（HTTP 非200） | ✓ | 尝试 Unpaywall 备用源；最终使用摘要替代 |
| `ERR-EXT-PDF-002` | PDF_PARSE_ERROR` | pypdf 解析失败（损坏/加密文件） | ✗ | 自动降级使用摘要替代 |
| `ERR-EXT-SMTP-001` | SMTP_AUTH_FAILED` | SMTP 认证失败 | ✗ | 检查邮件配置；更新应用密码 |
| `ERR-EXT-SMTP-002` | SMTP_SEND_FAILED` | 邮件发送失败 | ✓ | 重试；检查收件人地址有效性 |

#### Agent 业务层 (AGT)

| 错误码 | 名称 | 含义 | 可重试 | 建议操作 | 关联 FR |
|--------|------|------|--------|----------|---------|
| `ERR-AGT-C1-001` | KEYWORD_GEN_EMPTY` | 检索词生成结果为空 | ✓ | 丰富课题描述后重试 | FR-012 |
| `ERR-AGT-C2-001` | RETRIEVAL_ALL_FAILED` | 所有数据源检索均失败 | ✓ | 检查各数据库 API 配置 | FR-012 |
| `ERR-AGT-C2-002` | RETRIEVAL_PARTIAL` | 部分数据源检索失败（警告） | — | 仅警告，继续使用成功数据源 | FR-012 |
| `ERR-AGT-C3-001` | SCORING_BATCH_FAILED` | 批次评分全部失败 | ✓ | 检查 LLM 配置；缩小 batch_size | FR-013 |
| `ERR-AGT-C4-001` | DOWNLOAD_ALL_FAILED` | 本批次 PDF 全部下载失败 | ✓ | 降级使用摘要；检查网络 | FR-015 |
| `ERR-AGT-C5-001` | ANALYSIS_BATCH_FAILED` | AI 分析批次全部失败 | ✓ | 检查 LLM；降低并发数 | FR-016 |
| `ERR-AGT-R1-001` | TOPIC_EXPANSION_EMPTY` | 课题扩写结果为空 | ✓ | 补充课题描述后重试 | FR-020 |
| `ERR-AGT-R2-001` | OUTLINE_INVALID_JSON` | 架构生成 JSON 解析失败 | ✓ | 自动重试最多3次 | FR-020 |
| `ERR-AGT-R3-001` | CHAPTER_WRITE_FAILED` | 章节撰写失败 | ✓ | 重新触发章节任务 | FR-021 |
| `ERR-AGT-R4-001` | REVIEW_LOOP_EXCEEDED` | 审查迭代超过上限 | ✗ | 手动接受当前版本 | FR-022 |
| `ERR-AGT-D1-001` | GRAPH_RAG_NO_RESULTS` | Graph-RAG 未检索到任何论文 | ✗ | 先运行构建模式补充论文库 | FR-026 |
| `ERR-AGT-D2-001` | SUMMARY_INVALID_JSON` | 总结 JSON 解析失败 | ✓ | 自动重试 | FR-028 |

#### 数据验证层 (VAL)

| 错误码 | 名称 | 含义 | 可重试 | 建议操作 |
|--------|------|------|--------|----------|
| `ERR-VAL-001` | PROJECT_NOT_FOUND` | 项目不存在或无权限 | ✗ | 确认 project_id 和登录用户 |
| `ERR-VAL-002` | EMPTY_PAPER_LIBRARY` | 有效论文数为0，无法进入深度研究/综述模式 | ✗ | 先完成构建模式（FR-005 前置检查） |
| `ERR-VAL-003` | TASK_ALREADY_RUNNING` | 项目已有运行中任务 | ✗ | 等待任务完成或取消后重试 |
| `ERR-VAL-004` | DIALOGUE_ARCHIVED` | 对话已归档，无法发送消息 | ✗ | 创建新对话会话 |
| `ERR-VAL-005` | OUTLINE_NOT_CONFIRMED` | 综述架构未确认，无法触发章节撰写 | ✗ | 先确认架构 |

---

## 4. 结构化错误信封

### 4.1 标准错误信封（ErrorEnvelope）

所有 Agent 层错误、SSE 错误事件、DB `stage_records.error` 字段均使用此统一结构：

```json
{
  "code": "ERR-LLM-004",
  "message": "LLM 输出无法解析为预期 JSON：期望包含 'sections' 字段的对象，实际收到字符串",
  "detail": {
    "stage": 2,
    "attempt": 2,
    "max_attempts": 3,
    "raw_output_preview": "\"这是一个综述架构：...\"",
    "prompt_key": "review_outline_gen"
  },
  "traceback": "Traceback (most recent call last):\n  File \".../stage2_outline_gen.py\", line 87...",
  "retryable": true,
  "suggestion": "系统将在 3 秒后自动重试（第 2/3 次）。若持续失败，请检查 LLM 配置或简化课题描述。",
  "occurred_at": "2026-04-24T10:23:45.123Z",
  "project_id": "proj_abc123",
  "stage_record_id": "sr_xyz789"
}
```

### 4.2 SSE 错误事件协议

#### 4.2.1 构建模式 / 综述模式（BackgroundTask → Queue → SSE）

```
event: stage_error
data: {<ErrorEnvelope>}

event: stage_warning
data: {"code": "ERR-AGT-C2-002", "message": "Semantic Scholar 检索失败，已使用其余3个数据源继续", ...}

event: stage_progress
data: {"stage": 3, "current": 45, "total": 120, "message": "正在评分第 45/120 篇论文..."}

event: stage_complete
data: {"stage": 3, "result": {...}}
```

#### 4.2.2 深度研究模式（StreamingResponse 内联）

```
event: turn_start
data: {"turn_index": 3, "sub_mode": "technical", "sub_mode_name": "技术讨论"}

event: text_delta
data: {"delta": "根据检索到的 5 篇相关论文，以下是对您问题的技术分析：\n\n"}

event: turn_complete
data: {"turn_id": "tu_abc", "referenced_papers": ["p_001", "p_002"], ...}

event: error
data: {"code": "ERR-LLM-002", "message": "LLM 速率限制，请稍后重试", "retryable": true, "suggestion": "..."}
```

#### 4.2.3 警告与错误区分原则

| 事件类型 | 含义 | 前端处理 |
|----------|------|----------|
| `stage_warning` | 部分失败但流程可继续（如单个数据源超时）| 显示黄色提示条，不中断 |
| `stage_error` | 当前阶段失败，流程中止 | 显示红色错误卡片，提供"重试"按钮 |
| `error`（对话） | 本轮对话失败 | 显示内联错误气泡，允许重新发送 |

---

## 5. 健康检查体系

### 5.1 探针层级

```
GET /health          →  浅层探针（进程存活）
GET /health/db       →  数据库连通性探针
GET /health/deep     →  全依赖探针（LLM + 外部 API + SMTP）
GET /health/pipeline →  流水线状态快照（运行中/暂停的阶段记录）
```

### 5.2 各探针规范

#### `/health`（浅层）

响应时间目标：< 50ms

```json
{"status": "ok", "version": "1.0.0", "timestamp": "2026-04-24T10:00:00Z"}
```

失败条件：FastAPI 进程不响应（由 Docker/K8s 使用）。

---

#### `/health/db`（数据库层）

响应时间目标：< 200ms

```json
{
  "status": "ok",
  "checks": {
    "postgresql": {
      "status": "ok",
      "latency_ms": 12,
      "pool_size": 10,
      "pool_checked_out": 2
    }
  }
}
```

失败时：

```json
{
  "status": "degraded",
  "checks": {
    "postgresql": {
      "status": "error",
      "code": "ERR-SYS-DB-001",
      "message": "asyncpg 连接失败：Connection refused at 127.0.0.1:5432",
      "last_success_at": "2026-04-24T09:58:30Z"
    }
  }
}
```

---

#### `/health/deep`（全依赖，需认证）

响应时间目标：< 5s（并发探测所有外部依赖）

```json
{
  "status": "degraded",
  "checks": {
    "llm_primary": {
      "status": "ok",
      "provider": "deepseek",
      "model": "deepseek-chat",
      "latency_ms": 843
    },
    "llm_fallback": {
      "status": "not_configured",
      "message": "未配置备用 LLM，建议管理员设置系统级备用模型"
    },
    "arxiv": {
      "status": "ok",
      "latency_ms": 312
    },
    "openalex": {
      "status": "error",
      "code": "ERR-EXT-OA-001",
      "message": "HTTP 403：API 密钥无效",
      "suggestion": "在设置 → 论文数据库中更新 OpenAlex API 密钥"
    },
    "semantic_scholar": {
      "status": "ok",
      "latency_ms": 520
    },
    "ads": {
      "status": "not_configured"
    },
    "smtp": {
      "status": "ok",
      "host": "smtp.gmail.com",
      "latency_ms": 230
    }
  },
  "summary": "1 个依赖异常（openalex），构建模式将跳过该数据源"
}
```

**状态枚举**：`ok` / `degraded` / `error` / `not_configured`

整体 `status` 计算规则：
- 全部 `ok` → `ok`
- 有 `not_configured`（无 `error`） → `ok`（非必需依赖未配置不报错）
- LLM 主模型为 `error` → `error`（系统不可用）
- 其他依赖有 `error` → `degraded`（降级运行）

---

#### `/health/pipeline/{project_id}`（流水线状态，需认证）

```json
{
  "project_id": "proj_abc123",
  "project_status": "paused",
  "mode": "construction",
  "active_stages": [
    {
      "stage_record_id": "sr_xyz",
      "stage": 2,
      "mode": "construction",
      "status": "paused",
      "started_at": "2026-04-24T09:50:00Z",
      "paused_at": "2026-04-24T09:52:30Z",
      "elapsed_seconds": 150,
      "result_preview": {
        "total_retrieved": 87,
        "after_dedup": 71
      },
      "pending_user_action": "confirm_retrieval_results"
    }
  ],
  "last_error": null
}
```

---

### 5.3 前端健康状态展示规范

| 系统状态 | 界面表现 |
|----------|----------|
| 全部 `ok` | 状态栏绿色圆点，无提示 |
| `degraded` | 状态栏黄色三角，点击展开具体降级项（如"OpenAlex 不可用，已跳过"） |
| LLM `error` | 顶部红色横幅：「LLM 服务不可用，请前往设置检查 API 配置」，阻断所有 AI 功能入口 |
| DB `error` | 全屏错误页：「数据库连接失败，请联系管理员」 |

---

## 6. 诊断快照端点（Inspector）

### 6.1 端点定义

```
GET /projects/{project_id}/inspect
```

返回当前项目的完整诊断快照，供开发者和高级用户排查问题。**需管理员权限或项目所有者身份。**

### 6.2 响应结构

```json
{
  "snapshot_at": "2026-04-24T10:30:00Z",
  "project": {
    "id": "proj_abc123",
    "name": "Transformer 优化方法研究",
    "mode": "construction",
    "status": "error",
    "total_papers": 87,
    "valid_papers": 0
  },
  "stage_history": [
    {
      "stage_record_id": "sr_001",
      "stage": 1,
      "mode": "construction",
      "status": "completed",
      "started_at": "...",
      "completed_at": "...",
      "elapsed_seconds": 12,
      "result": {"keywords_generated": 4, "keyword_ids": ["kw_a", "kw_b", "kw_c", "kw_d"]}
    },
    {
      "stage_record_id": "sr_002",
      "stage": 2,
      "mode": "construction",
      "status": "completed",
      "elapsed_seconds": 95,
      "result": {"total_retrieved": 87, "after_dedup": 71, "by_source": {"arxiv": 42, "openalex": 29}}
    },
    {
      "stage_record_id": "sr_003",
      "stage": 3,
      "mode": "construction",
      "status": "failed",
      "started_at": "2026-04-24T09:55:00Z",
      "failed_at": "2026-04-24T10:02:18Z",
      "elapsed_seconds": 438,
      "error": {
        "code": "ERR-LLM-002",
        "message": "OpenAI API 速率限制：已超过 RPM 上限",
        "detail": {
          "attempt": 3,
          "max_attempts": 3,
          "last_batch_index": 23,
          "papers_scored": 23,
          "papers_total": 71
        },
        "retryable": true,
        "suggestion": "等待 60 秒后重试，或切换到 DeepSeek 等速率更高的模型"
      }
    }
  ],
  "keyword_summary": {
    "total": 4,
    "selected": 4,
    "is_searched": true
  },
  "paper_summary": {
    "total_in_db": 87,
    "valid": 0,
    "download_success": 0,
    "ai_analyzed": 0
  },
  "config_status": {
    "llm_configured": true,
    "llm_provider": "openai",
    "email_configured": true,
    "arxiv_configured": true,
    "openalex_configured": false
  },
  "recommendations": [
    "阶段3（评分与筛选）因 LLM 速率限制失败，建议：切换到 DeepSeek 或降低 batch_size 后点击「重试」",
    "OpenAlex 未配置，构建模式仅使用 arXiv 数据源，覆盖度可能不足"
  ]
}
```

### 6.3 `recommendations` 生成规则

诊断端点在返回数据时，根据以下规则自动生成人类可读的修复建议：

| 触发条件 | 建议文本模板 |
|----------|-------------|
| 最近一次 stage_record 状态为 failed | `"阶段{N}（{name}）因 {error.code} 失败，建议：{error.suggestion}"` |
| `valid_papers == 0` 且 mode 非 construction | `"有效论文库为空，无法使用{当前模式}，请先完成构建模式"` |
| LLM 未配置 | `"未配置 LLM，所有 AI 功能不可用，请前往设置配置模型"` |
| 任意外部 API 未配置 | `"{api_name} 未配置，构建模式将跳过该数据源"` |
| `total_papers > 0` 且 `valid_papers == 0` | `"已检索到 {N} 篇论文但均未通过评分，建议调低评分阈值或检查评分提示词"` |

---

## 7. 分层测试策略

### 7.1 测试层级全景

```
┌─────────────────────────────────────────────────────┐
│  E2E 测试（Playwright）                              │  ← FR 验收
│  覆盖：三模式切换 / 构建流水线 / 对话 SSE / 综述导出  │
├─────────────────────────────────────────────────────┤
│  集成测试（pytest + real PostgreSQL）                 │  ← 跨层验证
│  覆盖：Service + Agent + DB 联合行为                  │
├─────────────────────────────────────────────────────┤
│  单元测试（pytest）                                   │  ← 逻辑验证
│  覆盖：Schema 验证 / 工具函数 / LLM Mock              │
├─────────────────────────────────────────────────────┤
│  契约测试（schemathesis）                             │  ← 接口回归
│  覆盖：OpenAPI 自动 fuzz 测试                         │
└─────────────────────────────────────────────────────┘
```

### 7.2 单元测试

#### 7.2.1 覆盖范围

| 模块 | 测试文件 | 关键测试点 |
|------|----------|-----------|
| `schemas/` | `test_schemas.py` | Pydantic 字段验证、可选字段默认值、枚举合法值 |
| `utils/ids.py` | `test_ids.py` | new_id 前缀格式、唯一性 |
| `services/dialogue_service.py` | `test_dialogue_service.py` | `_derive_sub_mode` 默认值、`_parse_summary` 异常处理 |
| `agents/deep_research/pipeline.py` | `test_pipeline.py` | `graph_rag_retrieve` 关键词匹配逻辑、`extract_referenced_papers` 格式 |
| `agents/base.py` | `test_base.py` | `parse_json_response` 各种异常 JSON、`_sse` 格式 |

#### 7.2.2 LLM Mock 规范

```python
# conftest.py
import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def mock_llm_complete(monkeypatch):
    """Mock LLM 调用，返回预设 JSON 字符串，不消耗 API 额度。"""
    async def _fake_complete(messages, **kwargs):
        return '{"keywords": ["attention mechanism", "transformer optimization"]}'
    
    monkeypatch.setattr("app.agents.base.LLMClient.complete", _fake_complete)
    return _fake_complete

@pytest.fixture
def mock_llm_rate_limit(monkeypatch):
    """模拟 LLM 速率限制错误，验证重试逻辑。"""
    call_count = {"n": 0}
    async def _rate_limit_then_ok(messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise Exception("Rate limit exceeded")
        return '{"result": "ok"}'
    monkeypatch.setattr("app.agents.base.LLMClient.complete", _rate_limit_then_ok)
    return call_count
```

### 7.3 集成测试

#### 7.3.1 测试数据库策略

```python
# conftest.py（集成测试）
@pytest.fixture(scope="session")
async def test_db():
    """使用真实 PostgreSQL 测试数据库（不 mock），测试后回滚。"""
    engine = create_async_engine(settings.TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
```

**禁止在集成测试中 mock 数据库**（参照 02_product_requirements.md §4.2 数据完整性要求，数据库 mock 会掩盖真实约束冲突，历史上已导致生产事故）。

#### 7.3.2 关键集成测试用例

**构建模式流水线**

```python
# test_construction_pipeline.py

async def test_stage1_to_stage2_chain(test_db, mock_llm_complete, mock_arxiv_api):
    """验证 stage1 生成检索词后自动触发 stage2，stage2 record 正确关联。"""
    project = await create_test_project(test_db)
    record1 = await create_stage_record(test_db, project.id, stage=1)
    
    await run_stage(project.id, "test_user", stage=1, record_id=record1.id)
    
    # stage1 完成后 stage2 应自动启动
    record2 = await get_latest_stage_record(test_db, project.id, stage=2)
    assert record2 is not None
    assert record2.status in ("completed", "paused")
    
    keywords = await list_keywords(test_db, project.id)
    assert len(keywords) >= 1

async def test_stage1_failure_marks_correct_record(test_db, mock_llm_rate_limit):
    """验证 stage1 触发 stage2 时，stage2 失败应标记 stage2 的 record，不影响 stage1。"""
    project = await create_test_project(test_db)
    record1 = await create_stage_record(test_db, project.id, stage=1)
    
    await run_stage(project.id, "test_user", stage=1, record_id=record1.id)
    
    await test_db.refresh(record1)
    assert record1.status == "completed"  # stage1 本身应完成
    
    record2 = await get_latest_stage_record(test_db, project.id, stage=2)
    assert record2.status == "failed"     # stage2 失败
    assert "Rate limit" in record2.error
```

**深度研究模式对话**

```python
# test_dialogue.py

async def test_run_dialogue_turn_sse_sequence(test_db, mock_llm_complete):
    """验证单轮对话 SSE 事件顺序：turn_start → text_delta(≥1) → turn_complete。"""
    dialogue = await create_test_dialogue(test_db)
    
    events = []
    async for event_str in run_dialogue_turn(
        db=test_db, user_id="u1", project_id="p1",
        dialogue=dialogue, user_content="什么是 Transformer？", sub_mode="technical"
    ):
        event_type = parse_sse_event_type(event_str)
        events.append(event_type)
    
    assert events[0] == "turn_start"
    assert "text_delta" in events
    assert events[-1] == "turn_complete"
    
    # 验证 DB 持久化
    turn = await get_latest_turn(test_db, dialogue.id)
    assert turn is not None
    assert turn.sub_mode == "technical"
    assert turn.user_content == "什么是 Transformer？"

async def test_run_dialogue_turn_llm_error_yields_error_event(test_db, mock_llm_raise):
    """验证 LLM 异常时 SSE 推送 error 事件，不写入 DB。"""
    dialogue = await create_test_dialogue(test_db)
    
    events = []
    async for event_str in run_dialogue_turn(...):
        events.append(event_str)
    
    assert any('"event": "error"' in e or 'event: error' in e for e in events)
    
    turn_count_after = await count_turns(test_db, dialogue.id)
    assert turn_count_after == 0  # 失败时不应写入 turn
```

**权限与前置检查**

```python
# test_mode_switch.py

async def test_switch_to_deep_research_blocked_when_no_valid_papers(client, auth_headers):
    """FR-005：有效论文数为0时，切换到深度研究模式应返回400。"""
    project = await create_project_with_zero_valid_papers()
    
    response = await client.post(
        f"/api/v1/projects/{project.id}/mode",
        json={"target_mode": "deep_research"},
        headers=auth_headers
    )
    
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "ERR-VAL-002"
    assert "有效论文" in data["message"]

async def test_admin_only_endpoint_returns_403_for_normal_user(client, user_headers):
    """FR-029：普通用户访问管理员接口应返回403，包含 ERR-AUTH-004。"""
    response = await client.get("/api/v1/admin/users", headers=user_headers)
    
    assert response.status_code == 403
    assert response.json()["data"]["code"] == "ERR-AUTH-004"
```

### 7.4 契约测试（CI 层）

使用 `schemathesis` 对 FastAPI 自动生成的 OpenAPI Schema 进行 fuzz 测试：

```bash
# CI 命令
schemathesis run http://localhost:8000/openapi.json \
  --auth-type=bearer \
  --header "Authorization: Bearer $TEST_TOKEN" \
  --checks=all \
  --max-response-time=1000 \
  --validate-schema=true \
  --junit-xml=report.xml
```

覆盖检查项：
- 响应状态码与 OpenAPI 定义一致
- 响应 JSON 结构与 schema 匹配
- 单个 API 响应时间 < 1000ms（对应 spec §4.1）
- 非预期输入（空值、超长字段、非法枚举）不返回 5xx

### 7.5 端到端测试（E2E）

使用 Playwright，关键场景：

| 场景编号 | 场景描述 | 关联 FR | 验证点 |
|----------|---------|---------|--------|
| E2E-001 | 首位用户注册后自动成为管理员 | FR-029 | 登录后能看到管理员菜单 |
| E2E-002 | 完整构建模式流水线（7阶段） | FR-012~018 | 每阶段暂停点均出现；邮件发送成功 |
| E2E-003 | 有效论文为0时切换深度研究模式 | FR-005 | 弹出拦截提示；不跳转 |
| E2E-004 | 深度研究模式 SSE 对话流 | FR-026 | 回复逐字显示；引用论文高亮 |
| E2E-005 | 综述模式完整流程 | FR-020~023 | 架构确认→章节撰写→汇总导出 |
| E2E-006 | LLM 配置错误时的错误提示 | FR-002 | Inspector 面板显示 ERR-LLM-001 |
| E2E-007 | 管理员禁用用户后该用户下次请求返回 401 | FR-029 | 禁用后 API 返回 401 |

---

## 8. 前端 Inspector Panel 规范

### 8.1 触发条件

以下任一条件触发 Inspector Panel 展开：
- 收到 `stage_error` SSE 事件
- 项目 `status` 变为 `error`
- 用户主动点击状态栏的"诊断"按钮

### 8.2 面板内容结构

```
┌─ Inspector Panel ──────────────────────────────────────┐
│ ● 项目：Transformer 优化方法研究                         │
│ ✗ 阶段 3（评分与筛选）失败  2026-04-24 10:02:18         │
│                                                          │
│ 错误码：ERR-LLM-002                                      │
│ 原因：OpenAI API 速率限制，已重试 3 次仍失败             │
│                                                          │
│ 进度：已评分 23/71 篇论文                                │
│                                                          │
│ 建议修复步骤：                                           │
│  1. 前往「设置 → LLM 配置」切换到 DeepSeek 或本地模型    │
│  2. 或等待 60 秒后点击「重试阶段 3」                      │
│  3. 或降低批次大小（当前 batch_size: 10，建议改为 5）    │
│                                                          │
│ [重试阶段 3]  [查看完整诊断]  [切换 LLM]  [关闭]        │
└────────────────────────────────────────────────────────┘
```

### 8.3 错误严重级别与颜色规范

| 级别 | 颜色 | 触发条件 | UI 行为 |
|------|------|----------|---------|
| `fatal` | 红色 | LLM 无配置；DB 连接失败 | 全屏遮罩，阻断操作 |
| `error` | 橙红色 | 阶段失败；流水线中止 | Inspector Panel 自动弹出 |
| `warning` | 黄色 | 部分数据源失败；降级运行 | 状态栏黄色提示，不中断 |
| `info` | 蓝色 | 阶段进度、等待用户操作 | 内联进度条 |

---

## 9. 日志规范

### 9.1 结构化日志格式

所有后端日志使用 JSON 结构输出，便于日志聚合工具（ELK / Grafana Loki）解析：

```json
{
  "timestamp": "2026-04-24T10:02:18.456Z",
  "level": "ERROR",
  "logger": "app.agents.construction.stage3_scoring",
  "message": "LLM 批次评分失败",
  "project_id": "proj_abc123",
  "user_id": "u_xyz",
  "stage": 3,
  "stage_record_id": "sr_003",
  "error_code": "ERR-LLM-002",
  "attempt": 3,
  "max_attempts": 3,
  "batch_index": 23,
  "elapsed_seconds": 438,
  "exc_info": true
}
```

### 9.2 关键日志埋点位置

| 位置 | 日志级别 | 必须包含字段 |
|------|----------|-------------|
| 每个 stage `run()` 入口 | INFO | project_id, stage, stage_record_id |
| LLM `complete()` 调用前 | DEBUG | prompt_key, message_count, estimated_tokens |
| LLM `complete()` 调用后 | DEBUG | latency_ms, output_tokens |
| 任意 stage 标记 failed | ERROR | 完整 ErrorEnvelope |
| SSE 事件推送 | DEBUG | event_type, project_id |
| 外部 API 调用失败 | WARNING | api_name, status_code, latency_ms |
| DB 事务提交 | DEBUG | table_name, operation, affected_rows |

### 9.3 日志级别使用规范

| 级别 | 使用场景 |
|------|----------|
| `DEBUG` | LLM 调用详情、SSE 事件推送、DB 操作（开发环境默认开启，生产关闭） |
| `INFO` | 阶段开始/完成、用户登录/登出、任务创建 |
| `WARNING` | 部分依赖不可用但不影响主流程、LLM 重试成功、PDF 下载失败降级摘要 |
| `ERROR` | 阶段失败、LLM 重试耗尽、DB 操作异常 |
| `CRITICAL` | DB 完全不可达、进程级异常 |

---

## 10. 验收检查清单

以下检查项应在每次功能发布前逐一验证。

**图例**：✅ 已实现 · ⚠️ 部分实现 · ❌ 未实现 · 🔁 需运行时验证

---

### 10.1 健康检查层

- ✅ `GET /health` 在 50ms 内响应 200
  - `health_shallow()` 不访问数据库，仅返回进程存活信息
- ✅ `GET /health/db` 在 DB 故障时返回 503 + `ERR-SYS-DB-001`
  - `health.py:158-176`：catch 后返回 `JSONResponse(503)` + `AppErrorCode.DB_CONNECTION_FAILED`
- ✅ `GET /health/deep` 并发探测所有外部依赖，5s 内返回
  - `asyncio.gather` 并发探测 LLM×2 + arXiv/OpenAlex/SS/ADS + SMTP，均设 5s timeout
- ✅ 健康检查不需要认证（`/health`, `/health/db`），`/health/deep` 需认证
  - `/health` 和 `/health/db` 无 `Depends(get_current_user)`；`/health/deep` 和 `/health/pipeline/{id}` 有

### 10.2 错误信封层

- ✅ 所有 `stage_error` SSE 事件包含：code, message, retryable, suggestion
  - `emit_error_event()` 发送完整 `ErrorEnvelope.model_dump()`，含所有字段
- ✅ `stage_records.error` 字段存储完整 ErrorEnvelope JSON（非裸字符串）
  - `construction/__init__.py` 和 `review/__init__.py` 均调用 `mark_stage_failed(db, id, envelope.model_dump_json())`
  - 旧记录（裸字符串）在 `/inspect` 和 `/health/pipeline` 读取时降级处理
- ⚠️ `retryable: true` 的错误在前端显示「重试」按钮
  - `InspectorPanel.tsx` 仅显示文字标签 `(可重试)`；实际重试按钮（绑定 API 调用）**尚未实现**
- ❌ `retryable: false` 的错误在前端显示「查看帮助」而非「重试」
  - InspectorPanel 未区分 `retryable:false` 场景的操作按钮，**尚未实现**
- ✅ 对话 SSE `error` 事件不写入 DB（turn 不存在）
  - `dialogue_agent.py`：`db.add(turn)` + `db.commit()` 在 LLM 成功返回后才执行；LLM 异常不触发写入

### 10.3 诊断快照层

- ✅ `GET /projects/{id}/inspect` 返回完整 `stage_history`（含 error 字段）
  - `inspect.py:_build_history_item()` 解析 `record.error`（JSON 或裸字符串），填充 `StageHistoryItem`
- ✅ `recommendations` 数组包含针对当前错误状态的具体修复建议
  - `inspect.py:_generate_recommendations()` 按优先级生成 fatal/error/warning/info 建议
- ⚠️ 非项目所有者和非管理员访问返回 403
  - **实现为 404**（不是 403），以防止项目 ID 枚举攻击（`inspect.py:71-73`）
  - 这是有意的安全设计偏差，符合 qa_design §6 的安全要求；如需对齐 403 可修改

### 10.4 测试覆盖层

- 🔁 单元测试覆盖率 ≥ 80%（core/models/schemas/utils）
  - 已创建 4 个单元测试文件覆盖 `errors`/`schemas`/`ids`/`base`；实际覆盖率需运行 `pytest --cov` 验证
- ✅ 集成测试覆盖所有 stage 的成功路径和失败路径
  - `test_construction_pipeline.py`：ErrorEnvelope 写入、旧格式降级、链式阶段 record 正确标记
  - `test_dialogue.py`：LLM 错误不写 turns；`test_mode_switch.py`：FR-005/FR-029 权限
- ✅ E2E 测试覆盖 7 个关键场景（E2E-001 ~ E2E-007）
  - `e2e/specs/` 包含 7 个 Playwright spec 文件（auth/construction/review/dialogue/inspector/health/sse-error）
- 🔁 契约测试无 5xx 响应
  - `schemathesis.toml` + `run_contract_tests.sh` 已配置；需启动真实服务后执行验证

### 10.5 前端 Inspector 层

- ❌ 收到 `stage_error` 后 Inspector Panel 在 200ms 内自动弹出
  - `InspectorPanel.tsx` 通过 `open` prop 控制显示，无内置 SSE 监听器；**需宿主页面监听 `stage_error` 并设置 `open=true`**
- ✅ Inspector Panel 显示错误码、人类可读原因、修复建议
  - `StageHistoryRow` 渲染 `error.code + error.message`；`RecommendationItem` 渲染 recommendations
- ❌ `fatal` 级错误触发全屏遮罩，阻断所有操作入口
  - InspectorPanel 无全屏遮罩逻辑；`fatal` 级别仅通过 CSS 类 `.inspector-rec--fatal` 高亮显示，**尚未实现**
- ❌ 修复后（重试成功）Inspector Panel 自动收起
  - 无阶段状态轮询或重试成功回调，**尚未实现**

---

### 汇总

| 分类 | 总项 | 完成 | 部分 | 未完成 | 待验证 |
| ---- | ---- | ---- | ---- | ------ | ------ |
| 10.1 健康检查层 | 4 | 4 | 0 | 0 | 0 |
| 10.2 错误信封层 | 5 | 3 | 1 | 1 | 0 |
| 10.3 诊断快照层 | 3 | 2 | 1 | 0 | 0 |
| 10.4 测试覆盖层 | 4 | 2 | 0 | 0 | 2 |
| 10.5 前端 Inspector 层 | 4 | 1 | 0 | 3 | 0 |
| **合计** | **20** | **12** | **2** | **4** | **2** |

**待完成的核心工作（按优先级）：**

1. **10.5.1** — 宿主页面监听 SSE `stage_error` 事件 → 设置 `InspectorPanel open=true`
2. **10.5.3** — `fatal` 级错误全屏遮罩组件（宿主页面集成）
3. **10.2.3/4** — 前端重试按钮 / 查看帮助按钮（绑定 `POST /stages/{stage}/action` retry）
4. **10.5.4** — 重试成功后关闭 Inspector Panel（轮询或 SSE `stage_complete` 触发）

---

## 附录 A：错误码速查表

```
ERR-SYS-DB-{001-004}    数据库层
ERR-SYS-CFG-{001-002}   配置层
ERR-AUTH-{001-004}       认证/权限层
ERR-LLM-{001-006}        LLM API 层
ERR-EXT-ARXIV-{001-002}  arXiv
ERR-EXT-OA-{001}         OpenAlex
ERR-EXT-SS-{001}         Semantic Scholar
ERR-EXT-ADS-{001}        ADS
ERR-EXT-PDF-{001-002}    PDF 下载/解析
ERR-EXT-SMTP-{001-002}   邮件发送
ERR-AGT-C{1-5}-{nnn}     构建模式 Agent（C1=检索词 C2=检索 C3=评分 C4=下载 C5=分析）
ERR-AGT-R{1-4}-{nnn}     综述模式 Agent（R1=扩写 R2=架构 R3=撰写 R4=审查）
ERR-AGT-D{1-2}-{nnn}     深度研究模式 Agent（D1=GraphRAG D2=总结）
ERR-VAL-{001-005}         业务验证层
```

## 附录 B：与 file_map.md 的对应关系

| 本文档章节 | 对应实现文件 |
|-----------|-------------|
| §3 错误码体系 | `backend/app/agents/base.py`（ErrorEnvelope 定义） |
| §4 SSE 错误事件 | `backend/app/agents/construction/__init__.py`、`dialogue_agent.py` |
| §5 健康检查端点 | `backend/app/api/v1/`（待实现：`health.py`） |
| §6 诊断快照端点 | `backend/app/api/v1/`（待实现：inspect 路由） |
| §7.2 单元测试 | `backend/tests/unit/` |
| §7.3 集成测试 | `backend/tests/integration/` |
| §7.4 契约测试 | `backend/tests/contract/`（CI pipeline） |
| §7.5 E2E 测试 | `e2e/`（Playwright） |
| §8 Inspector Panel | `frontend/components/InspectorPanel/`（前端待实现） |
| §9 日志规范 | `backend/app/core/logging.py`（待实现） |
