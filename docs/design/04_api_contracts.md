# API Contracts 设计

文档版本：v1.1  
更新日期：2026-05-20  
依据文档：`00_layers.md`、`01_functional_requirements.md`

## 1. 设计目标

API 层暴露 Application Use Cases，不承载业务规则。所有接口必须经过认证、授权、Project 状态检查和统一错误处理。本文定义契约骨架，具体字段随实现补充但不得违背 FR。

## 2. 通用约定

- 路径前缀：`/api/v1`
- 请求/响应：JSON，文件下载使用授权 URL 或流式响应。
- 时间：ISO 8601。
- ID：UUID。
- 分页：`page_size`、`cursor`。
- 幂等：启动任务、调度触发、导出、邮件推送可接受 `Idempotency-Key`。

## 3. 响应信封

成功：

```json
{
  "data": {},
  "meta": {
    "request_id": "uuid"
  }
}
```

失败：

```json
{
  "error": {
    "code": "CONFIG_MISSING",
    "message": "用户需要选择可用模型",
    "category": "configuration",
    "details": {},
    "recovery": {
      "action": "open_user_llm_settings",
      "label": "前往模型设置"
    }
  },
  "meta": {
    "request_id": "uuid"
  }
}
```

## 4. 错误分类

| 分类 | 示例 |
| --- | --- |
| `auth` | 未登录、会话失效、账号禁用 |
| `permission` | 非 owner 访问 Project、非管理员访问系统配置 |
| `state` | archived 只读、deleted 不可进入、Run 已结束 |
| `configuration` | LLM 缺失、数据源失效、SMTP 不可用、超出白名单 |
| `lock_conflict` | active Construction Run 已存在、Research 流式回复中、章节锁冲突 |
| `provider` | 数据源限流、LLM 失败、PDF 下载失败、解析失败 |
| `validation` | 输入字段缺失、结构化输出校验失败 |
| `version` | Knowledge Version 缺失、过期、不可访问 |
| `storage` | 文件缺失、签名过期、外部同步失败 |

## 5. 端点骨架

认证与用户：

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /me`
- `PATCH /me`

配置：

- `GET /me/llm-configs`
- `POST /me/llm-configs`
- `PATCH /me/llm-configs/{config_id}`
- `DELETE /me/llm-configs/{config_id}`
- `POST /me/llm-configs/{config_id}/test`
- `GET /me/data-source-configs`
- `POST /me/data-source-configs`
- `PATCH /me/data-source-configs/{config_id}`
- `DELETE /me/data-source-configs/{config_id}`
- `POST /me/data-source-configs/{config_id}/test`
- `GET /me/notification-config`
- `PUT /me/notification-config`
- `POST /me/notification-config/test-email`

管理员：

- `GET /admin/users`
- `PATCH /admin/users/{user_id}`
- `POST /admin/users/{user_id}/reset-password`
- `GET /admin/system-config`
- `PUT /admin/system-config`
- `POST /admin/system-config/test`

Project：

- `GET /projects`
- `POST /projects`
- `GET /projects/{project_id}`
- `PATCH /projects/{project_id}`
- `POST /projects/{project_id}/pause`
- `POST /projects/{project_id}/resume`
- `POST /projects/{project_id}/archive`
- `DELETE /projects/{project_id}`
- `POST /projects/{project_id}/cleanup-preview`
- `POST /projects/{project_id}/cleanup-confirm`
- `GET /projects/{project_id}/workspace`

Construction：

- `GET /projects/{project_id}/construction-workspace`
- `PATCH /projects/{project_id}/construction-workspace`
- `GET /projects/{project_id}/construction-workspace/search-terms`
- `POST /projects/{project_id}/construction-workspace/search-terms`
- `PATCH /projects/{project_id}/construction-workspace/search-terms/{term_id}`
- `DELETE /projects/{project_id}/construction-workspace/search-terms/{term_id}`
- `POST /projects/{project_id}/construction-runs`
- `GET /projects/{project_id}/construction-runs`
- `GET /projects/{project_id}/construction-runs/{run_id}`
- `POST /projects/{project_id}/construction-runs/{run_id}/cancel`
- `POST /projects/{project_id}/construction-runs/{run_id}/confirm`

知识资产：

- `GET /projects/{project_id}/papers`
- `GET /projects/{project_id}/papers/{project_paper_id}`
- `GET /projects/{project_id}/papers/{project_paper_id}/file-access`
- `GET /projects/{project_id}/graph`
- `GET /projects/{project_id}/knowledge-versions`
- `GET /projects/{project_id}/knowledge-versions/{version_id}`

Research：

- `GET /projects/{project_id}/research-sessions`
- `POST /projects/{project_id}/research-sessions`
- `GET /projects/{project_id}/research-sessions/{session_id}`
- `POST /projects/{project_id}/research-sessions/{session_id}/messages`
- `GET /projects/{project_id}/research-sessions/{session_id}/events`
- `POST /projects/{project_id}/research-sessions/{session_id}/cancel-stream`
- `POST /projects/{project_id}/research-sessions/{session_id}/summary`

Review：

- `GET /projects/{project_id}/review-runs`
- `POST /projects/{project_id}/review-runs`
- `GET /projects/{project_id}/review-runs/{run_id}`
- `POST /projects/{project_id}/review-runs/{run_id}/outline`
- `POST /projects/{project_id}/review-runs/{run_id}/outline/confirm`
- `POST /projects/{project_id}/review-runs/{run_id}/chapters/{chapter_id}/generate`
- `PATCH /projects/{project_id}/review-runs/{run_id}/chapters/{chapter_id}`
- `POST /projects/{project_id}/review-runs/{run_id}/finalize`

导出、邮件、观点：

- `POST /exports`
- `GET /exports/{export_job_id}`
- `GET /exports/{export_job_id}/file-access`
- `GET /projects/{project_id}/email-push-jobs`
- `POST /projects/{project_id}/email-push-jobs/{job_id}/send`
- `GET /viewpoints`
- `POST /viewpoints`
- `DELETE /viewpoints/{viewpoint_id}`
- `POST /admin/viewpoints/{viewpoint_id}/hide`

## 6. SSE 约定

Research 流式回复和长任务事件使用 SSE。客户端必须已认证，服务端按 Project/Session 权限过滤。事件类型包括 `status`、`delta`、`citation`、`warning`、`error`、`done`。断线重连可使用 `Last-Event-ID`。结束事件必须写入最终状态，避免 UI 永久 loading。

## 7. API 验收要求

- 每个写端点能映射到一个 Application Use Case。
- archived/deleted/无权限/锁冲突/配置失败返回统一错误信封。
- 文件访问不暴露真实路径。
- 密钥字段只返回脱敏标识。
- 长任务启动返回任务 ID、状态和诊断入口。
