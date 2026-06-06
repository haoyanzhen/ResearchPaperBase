# Application Use Cases 设计

文档版本：v1.2
更新日期：2026-06-06
依据文档：`00_layers.md`、`01_functional_requirements.md`

## 1. 设计目标

Application Use Cases 是所有写操作和重要读操作的统一入口。它负责把用户意图转换为可校验、可审计、可恢复的业务操作，并统一执行权限、状态、锁、配置快照、事务和任务提交。

## 2. 用例分组

| 分组 | 用例 | 关联 FR |
| --- | --- | --- |
| 认证与用户 | 注册、登录、登出、读取当前用户、修改基础信息、管理员用户治理 | FR-001, FR-005 |
| 配置 | 保存/测试用户 LLM、保存/测试数据源、保存通知、保存/测试系统配置、解析运行时配置 | FR-002 至 FR-007 |
| Project | 创建、更新基础信息、归档、软删除、私人资产清理、进入 Workspace 前检查 | FR-008 |
| 调度 | 扫描 active Project、创建自动 Construction Run、记录跳过/延后/失败 | FR-009 |
| Workspace | 打开对象、恢复上下文、读取面板、读取知识资产、运行控制 | FR-011 至 FR-018 |
| Construction | 管理检索词、启动 Run、检索、筛选、下载解析、AI 分析、入库建图、发布版本、触发推送 | FR-020 至 FR-027 |
| Research | 创建 Session、发送消息、追加流式回复、保存引用、总结、导出 | FR-028 至 FR-031 |
| Review | 创建 Run、生成大纲、确认大纲、生成章节、审查、终稿、导出、版本历史 | FR-032 至 FR-036 |
| 导出 | 创建导出任务、读取导出状态、下载授权产物 | FR-019, FR-030, FR-034 |
| 观点 | 发布、查看、搜索、删除本人观点、管理员隐藏 | FR-010 |

## 3. 标准用例管线

所有写用例按以下顺序执行：

```text
Authenticate
  -> Authorize
  -> Load Domain Object
  -> Check Project/Run State
  -> Resolve Runtime Config Snapshot when needed
  -> Acquire Lock when needed
  -> Validate Command
  -> Execute Domain / Service Operation
  -> Persist Transactional State
  -> Submit Async Job / Emit Event
  -> Return View Model or Job Handle
```

异步任务回调不得绕过用例直接写业务状态，应通过内部命令或受控 repository 方法推进状态。

## 4. 配置快照

启动 Construction Run、Research Session 首次生成、Review Run 生成任务、Export Job、Email Push Job 前必须保存配置快照。

快照应记录配置来源、LLM provider、base URL 脱敏标识、模型名称、参数、数据源列表、启用状态、访问模式、速率限制、SMTP 来源、系统硬限制版本、任务启动时间、触发者、Project 和 Knowledge Version。

快照不得保存或返回 API key、SMTP 密码、用户密钥或系统密钥明文。

## 5. 锁与并发

| 锁 | 范围 | 保护内容 | 失败行为 |
| --- | --- | --- | --- |
| `project_construction_write_lock` | Project | 同一 Project 只能有一个 active Construction Run 写知识库 | 拒绝启动或调度延后 |
| `scheduler_project_lock` | Project + 调度周期 | 防止重复自动创建 Run | 记录跳过原因 |
| `research_stream_lock` | Research Session | 同一对话一次只追加一个流式回复 | 拒绝第二次发送并提示当前回复 |
| `review_chapter_lock` | Review Run + Chapter | 防止同一章节并发生成/重写 | 拒绝或排队 |
| `review_final_lock` | Review Run | 防止终稿并发汇总或导出源被改写 | 拒绝或排队 |
| `content_overwrite_lock` | 内容对象 | 防止覆盖确认期间内容变化 | 要求刷新后重试 |
| `export_job_lock` | Export 目标 | 避免同一产物重复生成 | 返回已有任务或创建新版本 |

锁必须有超时、持有者、创建时间和诊断信息。

## 6. 状态推进

允许的核心流向：

```text
draft -> queued -> running -> waiting_user -> running -> succeeded
draft -> queued -> running -> failed
draft|queued|running|waiting_user -> cancelled
failed|cancelled|succeeded -> copied_as_new
```

不得把已成功或已取消的历史对象原地改回 running。重试若会改变历史结果，应创建新任务版本或记录明确的 retry attempt。

## 7. Construction 主流程

1. 读取 Construction Workspace 和本次检索词来源。
2. 解析运行时配置和数据源策略。
3. 获取 Project 构建写锁。
4. 检索论文候选。
5. 归一化身份、去重、评分和筛选。
6. 处理人工确认或自动确认策略。
7. 下载 PDF 并解析文本，失败时标记摘要降级。
8. 生成 AI 分析。
9. 写入 ProjectPaper、文本资产、向量索引和图谱。
10. 达到发布条件后发布 Knowledge Version。
11. 触发 Knowledge Version 刷新提示和邮件推送范围。

## 8. Research 主流程

1. 创建 Session 时绑定 Knowledge Version。
2. 发送消息前检查 Project 可用性、Session 状态、配置和 stream lock。
3. 调用 Knowledge Graph-RAG 检索证据。
4. 调用 Agent 生成流式回复。
5. 保存消息、引用、证据定位和生成参数。
6. 释放 stream lock 并更新 Session 状态。

## 9. Review 主流程

1. 创建 Review Run 时绑定 Knowledge Version。
2. 生成大纲并进入用户确认。
3. 用户确认或编辑大纲后逐章生成。
4. 每章生成、审查、用户编辑和重试都受章节锁与内容保护约束。
5. 汇总终稿前校验章节状态、引用和版本一致性。
6. 生成摘要、关键词、参考文献和可导出版本。
7. 导出 Markdown/PDF/Word 时创建 Export Job。

## 10. 幂等与重试

- 用户重复提交启动命令时，若幂等键相同，应返回同一任务。
- 自动调度重复触发时，应按 Project + 调度窗口去重。
- Provider 临时失败可重试，但必须保留 attempt 和错误分类。
- 人工修改后的内容不得因任务重试被静默覆盖。

## 11. 用例测试入口

P0/P1 用例至少覆盖权限拒绝、Project 状态拒绝、配置解析失败、锁冲突、Provider 失败分类、内容覆盖保护、Knowledge Version 绑定和过期提示。
