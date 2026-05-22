# 12 Gap Decisions 迁移审核

文档版本：v1.0  
更新日期：2026-05-22  
依据文档：当前工作树 `docs/design/12_gap_decisions.md`、新版 `docs/design` 文档集  
适用项目大版本：v1

## 1. 审核目的

本文逐项核对旧 `12_gap_decisions.md` 中 D-001 至 D-015 的建议是否已被新版 Codex 工作树吸收。本文只记录审核结论，不替代新版设计文件；需要关闭的缺口应回写到对应设计文件。

状态说明：

| 状态 | 含义 |
| --- | --- |
| 已吸收 | 新版设计已明确采纳或等价解决 |
| 部分吸收 | 新版设计已有方向，但仍缺少字段、接口、枚举或验收细节 |
| 未吸收 | 新版设计仍缺少该决策或与旧建议冲突 |
| 改采新方案 | 新版设计有意采用不同方案，需要确认是否接受 |

## 2. 逐项审核

| 决策项 | 旧建议 | 新版审核状态 | 新版落点 | 仍需处理 |
| --- | --- | --- | --- | --- |
| D-001 状态模型 | 短期按旧数据模型统一，后续可新增 tasks | 部分吸收 | `02_domain_core.md` 定义 Project 状态为 `active/paused/archived/deleted`，Run/Session 通用状态含 `draft/queued/running/waiting_user/succeeded/failed/cancelled/archived`；`05_application_use_cases.md` 定义核心流向 | `07_data_schema.sql` 多数 `status` 字段未加 CHECK；`04_api_contracts.md` 未集中列出状态枚举；是否需要通用 `tasks` 表仍未决定 |
| D-002 REST 响应结构 | 统一 `{code,data,message}` | 改采新方案 | `04_api_contracts.md` 改用成功 `{data,meta}`、失败 `{error,meta}` | 需要确认新版 envelope 是否正式替代旧建议，并补充列表分页、文件流例外和 SSE payload 例外 |
| D-003 错误码体系 | 统一 `ERR-*` 字符串码 | 改采新方案 | `04_api_contracts.md` 使用 `CONFIG_MISSING` 类错误码；`09_quality_observability.md` 使用 `AUTH_`、`CONFIG_`、`PROVIDER_` 等前缀 | API、QA、实现测试需统一一个错误码格式；若不用 `ERR-*`，应明确迁移理由和兼容策略 |
| D-004 SSE 认证方案 | 对话用 fetch stream；进度流用 Cookie 或短期 stream token | 未吸收 | `04_api_contracts.md` 仅说明客户端必须已认证，未定义认证机制 | 必须补充 EventSource 不能带 Authorization header 的处理方式、token 有效期、CSRF/重放防护和断线重连规则 |
| D-005 构建阶段是否允许跳过 | 删除通用 skip | 已吸收 | `04_api_contracts.md` 不再提供阶段 `skip` 动作；`02_domain_core.md` 要求不得静默跳过高风险确认 | 保留“调度跳过/空邮件跳过”等非阶段跳过语义，文档需避免与 Construction stage skip 混淆 |
| D-006 深度研究图谱重建入口 | 移到构建或维护能力 | 已吸收 | `02_domain_core.md` 明确图谱写入只能由 ConstructionRun 触发；`03_ui_workspace.md` 禁止知识资产面板图谱重建 | 若未来提供手动修复/重建，需要只放在 Construction 或管理员维护路径，并加锁与诊断 |
| D-007 文件上传契约 | DOI/arXiv/URL 用 JSON，PDF 用 multipart | 未吸收 | `04_api_contracts.md` 当前只有文件访问端点，没有手动上传/补充论文契约 | 需要补充 PDF multipart、元数据 JSON、大小上限、批量上传、解析进度和失败项结构 |
| D-008 PostgreSQL 与 ChromaDB 一致性 | Outbox/同步项策略 | 部分吸收 | `07_data_persistence.md` 定义外部存储同步项状态，并要求发布 Knowledge Version 前关键同步项为 `synced` 或明确降级 | `07_data_schema.sql` 缺少 `knowledge_sync_items` 或 outbox 表；API/QA 也未定义修复任务和只检索 synced 数据的规则 |
| D-009 文件存储和导出生命周期 | 本地文件系统，预留对象存储；导出默认保留 | 部分吸收 | `07_data_persistence.md` 定义文件/导出生命周期，`08_security_permissions.md` 定义对象 key 与授权访问，`04_api_contracts.md` 有 export endpoints | 缺少保留时长、下载链接有效期、清理任务状态、软删除后提示策略和对象 key 命名规范 |
| D-010 管理员权限边界 | 管理员默认不能读用户项目内容 | 已吸收 | `08_security_permissions.md` 明确管理员不默认拥有其他用户 Project，MVP 不提供越权查看 | 若后续需要管理员协助诊断，应新增用户临时授权和审计机制 |
| D-011 综述版本管理模型 | 新增完整文章版本 | 部分吸收 | `02_domain_core.md` 有 `ReviewVersionSnapshot`、`ReviewExportableVersion`；`03_ui_workspace.md` 保留版本历史线框 | `07_data_schema.sql` 缺少 `review_versions`/`review_final_versions` 表；`04_api_contracts.md` 缺少 diff、rollback、merge、标签/注释接口 |
| D-012 推荐点赞与审核 | 新增点赞关系和审核字段 | 部分吸收 | 新版统一为 `Viewpoint`；`04_api_contracts.md` 有管理员隐藏观点；`08_security_permissions.md` 有管理员隐藏权限 | `07_data_schema.sql` 无点赞关系；是否保留点赞、是否默认公开、是否支持取消点赞仍未定 |
| D-013 UI 设计系统和响应式范围 | 桌面+平板，移动端降级 | 部分吸收 | `03_ui_workspace.md` 已迁入 P01-P42 线框，并把验收改为桌面和平板/窄屏可用 | 仍缺设计 token、断点、键盘焦点、ARIA、加载/空/错误态细化和移动端降级文案 |
| D-014 QA 文档职责拆分 | 拆成 QA 规范和实现状态 | 部分吸收 | `09_quality_observability.md` 已成为规范性文档，旧实现状态作为 backup 保留 | 若项目已有实现状态追踪需求，应新增 `docs/implementation_status.md` 或等价文档 |
| D-015 部署与迁移文档 | Docker Compose 部署文档 | 部分吸收 | `10_operations_deployment.md` 覆盖 MVP 拓扑、环境配置、调度、容量、备份和演进 | 仍缺可执行 Docker Compose、迁移/回滚流程、种子数据、Nginx/HTTPS 示例和 ChromaDB 部署形态选择 |

## 3. 高优先级未关闭项

1. D-004：SSE 认证机制必须尽快回写到 `04_api_contracts.md`，否则前端实现仍会踩到 EventSource header 限制。
2. D-007：手动论文补充/上传契约仍缺失，会影响 UI 线框中的论文补充能力落地。
3. D-008：同步项策略只有文字，没有 schema 支撑，Knowledge Version 发布条件还不可实现。
4. D-011：Review 完整版本模型只有领域概念，没有数据表和 API。
5. D-002/D-003：新版响应信封和错误码已偏离旧建议，需要人工确认后固定为新权威。

## 4. 备份与废弃说明

- 旧 `11_design_audit.md` 不迁入新版设计集，按用户要求废弃。
- 旧 API 契约、质量控制、数据模型和数据需求已放入 `backup/`，仅作为查证和补细节的参考材料。
- 本文审核完成后，建议按高优先级未关闭项依次回写新版设计文件，而不是恢复旧文档的权威地位。
