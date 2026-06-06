# Quality & Observability 设计

文档版本：v1.2
更新日期：2026-06-06
依据文档：`00_layers.md`、`01_functional_requirements.md`

## 1. 设计目标

质量与可观测设计保证 P0/P1 用例可测试、长流程可诊断、Provider 失败可分类、内容保护可验证、版本绑定可追踪。

## 2. FR 闭环要求

每个 P0/P1 FR 至少追踪到：

```text
UI / 后台入口
  -> Application Use Case
  -> Domain / Agent / Knowledge Rule
  -> Persistence or External Adapter
  -> AuthZ / State / Lock Check
  -> Test Case
  -> Diagnostic Signal
```

## 3. 测试分层

| 层 | 测试重点 |
| --- | --- |
| Domain | Project 状态、Knowledge Version 绑定、内容保护、最后管理员、论文身份去重 |
| Application | 权限、配置快照、锁、幂等、状态推进、调度跳过 |
| Agent/Knowledge | 检索归一化、评分、解析降级、Graph-RAG 引用、结构化输出校验 |
| Infrastructure | Provider 错误分类、文件签名、向量/图谱同步状态、邮件发送 |
| API | 响应信封、SSE 结束、错误分类、文件不泄漏路径 |
| UI | 禁用态、对象切换、上下文恢复、引用跳转、安全空态 |

## 4. P0 测试清单

- 用户注册登录、禁用账号拒绝、首位管理员并发。
- 用户 LLM/数据源配置保存、连接测试、密钥脱敏。
- 系统配置和硬限制。
- Project 创建、编辑信息、归档、软删除、私人资产清理预览。
- Workspace 进入检查和 Knowledge Version 缺失禁用态。
- Construction Run 单 Project 写锁。
- 多源检索失败分类、去重评分、PDF 解析降级、入库建图、版本发布。
- Research 流式回复锁、引用保存、版本绑定。
- Review 大纲确认、章节写锁、内容覆盖保护、终稿生成。
- 文件访问鉴权。

## 5. P1/P2 测试清单

- 自动调度重复触发、无自动检索词跳过、已有 active Run 延后。
- 邮件推送空邮件保护、多收件人偏好、SMTP 不可用。
- Export Job 生命周期和授权下载。
- Research 总结与导出。
- Review 版本历史、差异和回退。
- 观点广场搜索、删除、管理员隐藏。

## 6. 错误码原则

| 前缀 | 含义 |
| --- | --- |
| `AUTH_` | 认证和会话 |
| `PERMISSION_` | 权限 |
| `STATE_` | 状态不允许 |
| `CONFIG_` | 配置 |
| `LOCK_` | 并发锁 |
| `PROVIDER_` | 外部 Provider |
| `VALIDATION_` | 输入或输出校验 |
| `VERSION_` | Knowledge Version |
| `STORAGE_` | 文件、向量、图谱同步 |

错误必须包含可给用户展示的 message 和可给开发/管理员诊断的 details。

## 7. 日志与指标

日志字段包括 `request_id`、`user_id`、`project_id`、`use_case`、`run_id/session_id/review_run_id/job_id`、`status`、`error_code`、`duration_ms`、`provider`、`attempt`。

不得记录密钥明文、完整 PDF 文本、敏感用户输入或真实文件路径。

建议指标包括 Construction Run 成功率、Provider 限流和失败次数、PDF 解析降级率、Knowledge Version 发布成功率、Research SSE 中断率、Review 章节重试率、邮件推送成功率。

## 8. 诊断快照

Run/Session/Job 详情页和管理员诊断接口可读取脱敏快照：

- 当前状态与阶段。
- 配置快照脱敏摘要。
- 锁信息。
- Provider attempt 和错误分类。
- 同步项状态。
- 最近日志摘要。
- 可恢复动作建议。

普通用户只能读取自己 Project 的诊断；管理员诊断也不得包含用户密钥明文。

## 9. 健康检查

- `GET /health/live`：进程存活。
- `GET /health/ready`：数据库、文件存储、队列基础可用。
- 管理员配置测试：LLM、数据源、SMTP、向量库、图谱存储。

公开健康检查不得泄漏配置细节。

## 10. 验收门槛

- P0 用例有自动化测试或明确测试入口。
- 长任务失败不会只显示“未知错误”。
- Provider 失败不会混入成功结果。
- SSE 必须有结束或错误事件。
- 内容覆盖、版本刷新、锁冲突均可被测试复现。
