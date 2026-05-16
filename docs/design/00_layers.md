# Research Paper Base 分层设计总览

文档版本：v1.0  
更新日期：2026-05-16  
依据文档：`01_functional_requirements.md`、`00-05-layers-design-summary.md`  
用途：作为当前阶段分层设计的总览入口，明确最小必要架构、层间职责、横切约束和后续修订方向。

## 0. 文档控制

本文将原 `00_index.md` 从“旧设计文件索引与现状盘点”更新为“当前分层设计总览”。本次更新只处理分层设计本身，暂不维护以下内容：

- 各类设计文件的完整索引和权威性声明。
- API 端点、请求响应字段、错误码和 SSE 协议。
- 数据库表字段、迁移脚本和具体存储约束。
- 已实现/未实现状态流水账。

当前基线采用 `00-05-layers-design-summary.md` 的共层方案：五个核心层加四个横切约束。也就是保留清晰边界，但不把早期架构拆成过多顶层。

### 0.1 更新前后设计内容映射表

| 更新前设计内容 | 更新后承载位置 | 处理方式 |
| --- | --- | --- |
| 文档索引、文件权威性说明 | 暂不在本文维护 | 后续可由 README 或独立文档索引承载 |
| 产品与领域层 | `Domain Core`、`Application Use Cases` | 保留 Project、Run/Session、Knowledge Version 等核心概念，移除旧实体清单式描述 |
| 信息架构与用户流程层 | `UI / Workspace` | 保留 System Shell、Project Workspace、对象切换、只读知识面板等体验边界 |
| 状态机与业务流程层 | `Application Use Cases`、`State & Locks` | 状态推进、任务启动、锁、幂等等统一归入应用编排和横切约束 |
| 数据模型层 | `Domain Core`、`Agent & Knowledge Services`、`Infrastructure Adapters` | 不在总览中展开表结构，只保留知识资产、版本、同步状态和适配边界 |
| API 契约层 | `Application Use Cases` | 本文只定义应用入口职责，不展开接口清单 |
| UI 与交互层 | `UI / Workspace` | 与信息架构合并为前端体验层 |
| 权限与安全层 | `AuthZ` 横切约束 | 权限、安全、文件访问和 archived 只读作为统一横切规则 |
| 质量、测试与可观测层 | 设计闭环与后续增强 | 暂不作为独立核心层，但每条 P0/P1 FR 必须保留测试和诊断入口 |
| 运维、部署与演进层 | `Infrastructure Adapters` 与后续运维设计 | 当前只保留适配边界、部署风险和演进方向 |
| 追踪矩阵 | FR 设计闭环 | 不维护旧式大表，改为按能力族确认闭环链路 |
| 下一步修订建议 | MVP 落地顺序 | 从“修补旧文件”改为“围绕新分层逐步重写下游设计” |

## 1. 设计基线

当前项目推荐采用轻量但边界明确的共层方案：

```text
UI / Workspace
  ↓
Application Use Cases
  ↓
Domain Core
  ↓
Agent & Knowledge Services
  ↓
Infrastructure Adapters

横切约束：AuthZ / State & Locks / Runtime Config Snapshot / Content & Version Protection
```

基本原则：

- `01_functional_requirements.md` 仍是需求含义和验收标准的最高依据。
- 上层通过下层提供的能力完成用例，下层不反向依赖上层页面、接口或具体 Agent UI。
- 同层可以包含多个有明确边界的能力目录，例如 `agents/` 与 `knowledge/` 同属服务层，但依赖方向必须保持清楚。
- P0/P1 能力优先形成产品闭环；P2 能力先保留扩展点，不提前扩大架构体量。

## 2. 产品与领域层

产品核心仍是以 Project 为长期研究容器的学术研究工作台，而不是单一论文检索工具。领域层应稳定表达以下对象和规则：

核心对象：

- `User`
- `Config`
- `Project`
- `ConstructionWorkspace`
- `ConstructionRun`
- `ResearchSession`
- `ReviewRun`
- `PaperIdentity`
- `ProjectPaper`
- `KnowledgeVersion`
- `ContentProtectionRecord`
- `ExportJob`
- `EmailPushJob`
- `Viewpoint`

关键规则：

- Project 是长期容器，不等于某个 Agent 模式。
- 每个 Project 有且仅有一个 Construction Workspace。
- 同一 Project 同一时间只允许一个 active Construction Run 写知识库。
- Research Session 和 Review Run 创建时绑定某个 Knowledge Version，后续不被新版本静默切换。
- 人工修改优先于人工确认，人工确认优先于 Agent 草稿。
- 全局论文身份与 Project 私有关联分离，避免共享论文被误删。

领域层不依赖数据库、Web 框架、任务队列、LLM SDK、论文源 SDK、SMTP 或具体文件存储。它可以定义抽象能力，但具体实现由基础设施适配层承担。

## 3. 信息架构与用户流程层

`UI / Workspace` 层负责用户可见的信息架构和工作台体验。

主要职责：

- 提供登录后系统入口、Project 列表、配置入口、管理员入口和观点广场入口。
- 提供 Project Workspace Shell，承载 Construction Workspace、Research Session、Review Run 的入口、切换和上下文恢复。
- 展示 Run/Session 状态、阶段、等待项、错误、引用、知识库版本提示和只读知识资产面板。
- 展示后端返回的禁用原因，例如无可用 Knowledge Version、Project 已归档、权限不足、任务冲突或配置不可用。

边界：

- 前端不直接修改论文库、向量库、图谱、Knowledge Version 或运行状态。
- 只读知识资产面板只允许查看、筛选、跳转和下载授权资源。
- 前端禁用态只改善体验，最终判定必须由应用编排和权限约束兜底。

## 4. 应用编排与业务流程层

`Application Use Cases` 是所有写操作和重要读操作的统一入口。它把用户意图转成可校验、可审计、可恢复的业务操作。

主要职责：

- 编排 Project 创建、配置保存、启动 Construction Run、发送 Research 消息、推进 Review Run、导出、邮件推送等用例。
- 统一执行权限检查、Project 状态检查、运行时配置解析、配置快照、状态推进、并发锁、失败诊断和任务提交。
- 统一手动触发与自动调度入口，避免同一业务规则在不同路径中分叉。
- 管理事务边界、幂等控制和失败后的可恢复状态。

边界：

- 不承载 LLM 生成、论文源访问、PDF 解析、向量化或图谱算法细节。
- 不把数据库表结构、Provider SDK 类型或外部错误结构泄漏给 UI。
- 不让基础设施适配器绕过用例直接写业务状态。

## 5. Agent 与 Knowledge 共层设计

`Agent` 和 `Knowledge` 采用共层方案：它们同属 `Agent & Knowledge Services`，但内部边界必须明确。

推荐依赖方向：

```text
Application Use Cases
  ↓
services/
  agents/       # 行为、流程、生成、分析
    ↓
  knowledge/    # 论文资产、检索、版本、引用证据
  ↓
Infrastructure Adapters
```

`agents/` 负责智能行为和流程：

- Construction：检索词、论文检索、去重评分、PDF 下载解析、AI 分析、入库建议、向量化、图谱构建、Knowledge Version 发布准备。
- Research：基于绑定 Knowledge Version 的 Graph-RAG 检索、流式回答、引用保存和跳转来源。
- Review：大纲、章节、审查、终稿和可导出版本生成。

`knowledge/` 负责知识资产和证据基础：

- 论文身份解析和全局去重。
- Project 论文库与私有关联。
- PDF 文本资产、摘要降级标记和可检索状态。
- 向量索引、知识图谱、Graph-RAG 检索。
- Knowledge Version 发布、绑定、刷新提示。
- Citation & Evidence 的引用定位和版本一致性。

共层但分边界的原因：

- 二者抽象高度接近，都位于应用编排之下、基础设施之上。
- 当前项目体量不大，先共层可以减少目录和接口开销。
- Knowledge 是可复用基础能力，Agent 可以使用 Knowledge，但 Knowledge 不应依赖具体 Construction、Research 或 Review。
- 如果后续 Knowledge 被更多 Agent、导出、搜索、UI 面板稳定复用，可自然拆成独立层。

## 6. 数据、检索与外部适配层

`Infrastructure Adapters` 负责外部系统和底层技术实现，不能承载业务规则。

主要适配能力：

- 关系数据库。
- 文件存储。
- 向量库。
- 图谱存储。
- LLM Provider。
- 论文源 Provider。
- PDF 下载和解析。
- SMTP。
- Scheduler。
- Queue。
- Secret Store。
- 导出器。

数据和检索相关约束：

- 关系库、向量库、图谱无法天然同事务提交时，必须记录同步状态、补偿任务或失败项。
- Knowledge Version 只有在达到发布条件后才能作为 Research / Review 的读取边界。
- PDF、Graph、导出文件等资源必须通过鉴权或签名访问，不暴露真实文件路径。
- 外部错误必须转换为可诊断分类，例如缺失配置、密钥失效、限流、连接失败、权限过期、文件缺失、解析失败或同步失败。

## 7. 权限、安全与横切治理层

以下能力不建议早期拆成独立顶层，但必须作为所有层共同遵守的横切约束。

| 横切约束 | 最小必要内容 | 初期实现建议 |
| --- | --- | --- |
| AuthZ | 用户隔离、管理员边界、Project 权限、文件签名访问、archived 只读 | 先在 Application Use Cases 统一校验，UI 只负责展示原因 |
| State & Locks | Project 状态、Run/Session 状态、任务状态、Project 写锁、流式回复锁、章节锁、调度锁 | 先覆盖 Construction 写锁、Research 流式锁、Review 章节锁和 Project archived/deleted 约束 |
| Runtime Config Snapshot | 用户配置、系统默认、硬限制、LLM/数据源/SMTP/检索词策略快照 | 所有 Run/Session/Job 启动前生成快照，禁止 Agent 内部分散回落 |
| Content & Version Protection | 人工修改保护、覆盖确认、Knowledge Version 绑定、旧版本刷新提示 | 先实现 Research/Review 绑定版本和 Review 内容覆盖确认，再扩展差异对比 |

这些约束应体现在用例、领域规则、存储状态、测试和 UI 禁用原因中，而不是只写在前端按钮或文档备注里。

## 8. 质量、测试与可观测层

质量、测试与可观测不作为当前架构的独立核心层，但必须进入 P0/P1 设计闭环。

最低要求：

- 每个 P0/P1 用例至少能追踪到 UI 入口、应用用例、领域或 Agent 规则、知识或数据写入、权限检查和测试入口。
- 长流程必须记录可诊断状态，包括运行中、等待用户、失败、取消、部分成功、降级和可重试信息。
- 外部 Provider 失败不得静默混入成功结果。
- LLM 输出、引用、章节、综述终稿等内容必须有结构化校验入口。
- 手动修改、覆盖确认、版本刷新等高风险动作必须具备测试用例。

后续可以再把审计、健康检查、日志、指标、告警和 Inspector 设计展开为独立质量与可观测文档。

## 9. 运维、部署与演进层

运维部署当前不作为分层设计的主轴，但架构必须预留以下演进空间：

- 替换 LLM Provider、论文源 Provider、向量库、图谱存储和文件存储。
- 将长任务迁移到独立 Worker 或队列。
- 对自动构建、导出、邮件推送和补偿任务做统一调度。
- 对 PDF、解析文本、向量索引、图谱和导出文件做独立生命周期管理。
- 后续补充备份恢复、容量估算、成本控制、日志采集和告警策略。

早期实现应优先保证适配器边界清晰，而不是提前建设完整运维平台。

## 10. FR 追踪与设计闭环

P0/P1 FR 必须至少形成以下闭环：

```text
UI 入口
  -> Application Command/Query
  -> Domain / Agent Rule
  -> Knowledge / Data Persistence
  -> Permission / State / Lock Check
  -> Diagnostics / Audit Hook
  -> QA Case
```

能力族落位建议：

| FR 范围 | 主落位 | 协作落位 |
| --- | --- | --- |
| FR-001~007 账号、配置、管理员 | `Domain Core`、`Application Use Cases`、横切约束 | `UI / Workspace`、`Infrastructure Adapters` |
| FR-008~019 Project Workspace 通用能力 | `UI / Workspace`、`Application Use Cases`、`Domain Core` | `Agent & Knowledge Services`、横切约束 |
| FR-020~027 构建模式 | `agents/construction`、`knowledge/` | `Application Use Cases`、`Infrastructure Adapters`、横切约束 |
| FR-028~031 深度研究模式 | `agents/research`、`knowledge/` | `UI / Workspace`、`Application Use Cases`、横切约束 |
| FR-032~036 主题综述模式 | `agents/review`、`knowledge/` | `UI / Workspace`、`Application Use Cases`、横切约束 |

## 11. 下一步修订建议

建议按以下顺序推进后续设计，而不是继续在旧总览中修补接口或文件索引：

1. 以本文为分层基线，重写领域模型设计，稳定 Project、Run/Session、Knowledge Version、Paper 和内容保护规则。
2. 重写状态流程设计，统一 Project、Run/Session、Stage、Task、锁、等待用户、失败、取消和刷新语义。
3. 重写数据与知识资产设计，明确关系库、文件、向量、图谱、Knowledge Version 和同步失败处理。
4. 重写 API 契约，按 Application Command/Query 组织接口，而不是按数据库表裸露 CRUD。
5. 重写 UI / Workspace 设计，聚焦 System Shell、Project Workspace、Agent Workbench 和只读 Knowledge Asset Panel。
6. 补齐权限、安全、质量、可观测和运维设计，优先覆盖 P0/P1 闭环。

MVP 实施顺序：

1. Identity、Config、Project、AuthZ、Runtime Config Snapshot。
2. Project Workspace Shell、对象切换、状态展示和只读知识资产面板。
3. 手动 Construction Run 主流程和 Knowledge Version 发布。
4. Research Session 的 Graph-RAG 对话、流式回复互斥和引用跳转。
5. Review Run 的大纲、章节、人工确认、终稿和可导出版本。
6. 自动构建调度、邮件推送、导出中心、审计和可观测增强。
7. 观点广场增强、综述版本差异、批量上传、重跑策略、成本仪表盘等 P2 能力。
