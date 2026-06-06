# 12 Gap Decisions 设计审查

文档版本：v1.3
更新日期：2026-06-06
依据文档：`00_layers.md`、`01-01-FR-reference.md`、`02_domain_core.md`  
适用项目大版本：v1

## 1. 审核目的

本文逐项核对旧 `12_gap_decisions.md` 中 D-001 至 D-015 的建议，在当前分层总览、FR 参考和 Domain Core 设计中是否仍成立。

本次审查只判断以下三份设计文件是否已经吸收相关领域规则或分层边界：

- `00_layers.md`
- `01-01-FR-reference.md`
- `02_domain_core.md`

本文不审查代码、SQL schema、API 端点、具体响应字段、SSE 协议细节、UI 线框、QA 实现状态、运维部署脚本或数据迁移方案。超出上述三份文档职责的条目，只标记为“转交下游设计”，不再作为 Domain Core 缺口保留。

状态说明：

| 状态 | 含义 |
| --- | --- |
| 已吸收 | 当前三份设计已明确采纳或等价解决 |
| 部分吸收 | 当前三份设计已有领域规则或分层边界，但仍需下游设计细化 |
| 转交下游设计 | 该项属于 API、UI、数据、QA 或 Ops 等下游设计职责，不应在本文继续按 Domain Core 缺口追踪 |
| 不再追踪 | 旧建议已不属于当前 FR 或当前设计范围 |

## 2. 逐项审核

| 决策项 | 旧建议 | 当前状态 | 当前落点 | 后续处理 |
| --- | --- | --- | --- | --- |
| D-001 状态模型 | 短期按旧数据模型统一，后续可新增 tasks | 已吸收 | `02_domain_core.md` 已定义 Project 状态 `active/archived/deleted`、Run/Session 通用状态 `draft/queued/running/paused/waiting_user/succeeded/failed/cancelled/archived`，并定义构建写锁、调度锁、Research 流式锁和 Review 锁；Project 不提供 paused 状态，deleted 不进入 Workspace | 数据库约束、API 枚举和是否新增通用任务表转交下游设计 |
| D-002 REST 响应结构 | 统一 `{code,data,message}` | 转交下游设计 | `00_layers.md` 明确 API 端点、请求响应字段、错误码和 SSE 协议由 `04_api_contracts.md` 维护 | 本文不再追踪响应信封格式 |
| D-003 错误码体系 | 统一 `ERR-*` 字符串码 | 转交下游设计 | `00_layers.md` 要求 API Boundary 统一权限、Project 状态、配置、锁冲突和 Provider 失败响应；`02_domain_core.md` 要求错误进入可诊断分类 | 具体错误码格式转交 API/QA 设计 |
| D-004 SSE 认证方案 | 对话用 fetch stream；进度流用 Cookie 或短期 stream token | 转交下游设计 | `00_layers.md` 将 HTTP/SSE 入口、认证入口、断线恢复约定交给 API Boundary | 本文不再按领域缺口追踪 SSE 认证细节 |
| D-005 构建阶段是否允许跳过 | 删除通用 skip | 已吸收 | `02_domain_core.md` 要求 `waiting_user` 不得静默跳过高风险确认；邮件无未推送有效论文时不得发送空邮件，必须记录跳过原因 | 保留非阶段跳过语义；不得恢复通用 Construction stage skip |
| D-006 深度研究图谱重建入口 | 移到构建或维护能力 | 已吸收 | `02_domain_core.md` 明确图谱创建、增量更新、重建和修复只能由 ConstructionRun 触发；ResearchSession、ReviewRun 和只读知识资产入口不得触发图谱写入 | 未来若增加手动维护入口，仍必须挂在 Construction 或受控维护路径下 |
| D-007 文件上传契约 | DOI/arXiv/URL 用 JSON，PDF 用 multipart | 部分吸收 | `01-01-FR-reference.md` 的 FR-023 定义 PDF、DOI、arXiv ID、URL 补充论文；`02_domain_core.md` 已定义 `ManualPaperSupplementRequest`、`ExternalPaperIdentifier`、`DocumentAsset`、PDF-only 元数据确认和用户上传授权边界 | API 载体、大小上限、批量上传、解析进度和失败项结构转交 API/Data 设计 |
| D-008 PostgreSQL 与 ChromaDB 一致性 | Outbox/同步项策略 | 部分吸收 | `00_layers.md` 要求关系库、向量库、图谱不同事务提交时必须记录同步状态、补偿任务或失败项；`02_domain_core.md` 定义 `KnowledgeSyncState`，并要求未同步或失败数据不得标记为可检索或图谱可用 | outbox/sync item 表、修复任务和检索过滤规则转交 Data/Application 设计 |
| D-009 文件存储和导出生命周期 | 本地文件系统，预留对象存储；导出默认保留 | 部分吸收 | `00_layers.md` 要求 PDF、Graph、导出文件通过鉴权或签名访问且不暴露真实路径；`02_domain_core.md` 定义 `DocumentAccessRef`、`ExportJob` 和导出过期/清理/失败分类，且 Project 私人资产清理默认不删除已完成导出结果 | 保留时长、下载链接有效期、对象 key 和清理任务细节转交 Data/Ops/API 设计 |
| D-010 管理员权限边界 | 管理员默认不能读用户项目内容 | 已吸收 | `02_domain_core.md` 明确管理员只治理账号和系统配置，不得查看用户私人密钥明文；用户只能访问自己有权限的 Project、Run/Session、论文关联、导出和诊断 | 若未来提供管理员协助诊断，需要新增临时授权和审计规则 |
| D-011 综述版本管理模型 | 新增完整文章版本 | 部分吸收 | `01-01-FR-reference.md` 将 FR-036 定为 P2；`02_domain_core.md` 已定义 `ReviewExportableVersion`、`ReviewVersionSnapshot`，并要求新终稿/新可导出版本形成独立状态记录，历史版本回退需二次确认且生成新的当前版本 | diff、rollback、merge、标签和注释等交互/API/数据细节转交下游设计 |
| D-012 推荐点赞与审核 | 新增点赞关系和审核字段 | 不再追踪 | 当前 FR 只保留观点广场；`02_domain_core.md` 定义 `Viewpoint` 发布、作者删除、管理员隐藏、登录可见、禁止评论/回复/讨论串和搜索筛选可见性 | 点赞不是当前三份设计中的需求，不再作为缺口保留；若恢复点赞，应先回写 FR |
| D-013 UI 设计系统和响应式范围 | 桌面+平板，移动端降级 | 转交下游设计 | `00_layers.md` 只定义 UI / Workspace 层职责和边界，不维护设计 token、断点、ARIA 或具体响应式验收 | 转交 `03_ui_workspace.md` 或后续 UI 规范 |
| D-014 QA 文档职责拆分 | 拆成 QA 规范和实现状态 | 转交下游设计 | `00_layers.md` 要求 P0/P1 用例进入测试和诊断闭环，但不维护 QA 文档拆分方案 | 转交 `09_quality_observability.md` 或实现状态文档 |
| D-015 部署与迁移文档 | Docker Compose 部署文档 | 转交下游设计 | `00_layers.md` 只保留运维部署演进空间，包括替换外部适配器、统一调度、文件生命周期、备份恢复和水平扩展 | 转交 `10_operations_deployment.md` 和实际部署材料 |

## 3. 下游细化参考

本轮仍需下游细化的设计项已拆分到 `12-00_gap_downstream_reference.md`。本文只保留逐项审查结论。

## 4. 备份与废弃说明

- 旧 `11_design_audit.md` 不迁入新版设计集，按用户要求废弃。
- 旧 API 契约、质量控制、数据模型和数据需求已放入 `backup/`，仅作为查证和补细节的参考材料。
- 本文只保存旧 gap 到当前设计职责的迁移判断，不恢复旧文档的权威地位。

## 5. 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
| --- | --- | --- | --- |
| v1.0 | 2026-05-22 | 初始迁移审核，按旧 D-001 至 D-015 对新版设计集做宽范围核对 | Codex |
| v1.1 | 2026-05-29 | 按 `00_layers.md`、`01-01-FR-reference.md`、`02_domain_core.md` 重新审查，删除代码/API/schema/UI/QA/Ops 细节中的过期判断，并将下游职责从领域缺口中拆出 | Codex |
| v1.2 | 2026-05-29 | 将下游细化项拆分为 `12-00_gap_downstream_reference.md`，本文仅保留逐项审查结论 | Codex |
