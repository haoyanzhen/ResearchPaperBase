# Domain Reference

文档版本：v1.6
更新日期：2026-10-16
来源文档：[Domain Core](02_domain_core.md)、[知识库版本附录](02-02_construction_versioning_appendix.md)、[构建资产附录](02-03_construction_assets_appendix.md)、[运行恢复附录](02-04_run_recovery_appendix.md)
用途：作为 Domain Core 的聚合边界、领域对象、关键链路和 FR 映射速查文件。本文是主文及其同规格领域附录的派生速查，不独立定义规则；如有冲突，以对应领域规范及 FR 为准。

详细规则阅读索引：

- paused ConstructionRun 持续持有 Project 独占构建资格；取消清除、继续沿用原实例、重跑创建新实例接管的规则见 [02-02 §3.1](02-02_construction_versioning_appendix.md#31-构建槽不变量) 和 [02-04 §3](02-04_run_recovery_appendix.md#3-重试重连与重跑)。

| 专题 | 领域规范来源 |
| --- | --- |
| 聚合边界、跨模块接口及其他领域规则 | [Domain Core](02_domain_core.md) |
| 知识库版本、证据、发布、构建槽、并行构建和版本采用 | [02-02 知识库版本附录](02-02_construction_versioning_appendix.md) |
| 检索输入、论文/资料身份、去重筛选、补充、解析与分析确认 | [02-03 构建资产附录](02-03_construction_assets_appendix.md) |
| 重试、重连、重跑、断点、清理和回复恢复 | [02-04 运行恢复附录](02-04_run_recovery_appendix.md) |

## 1. 聚合边界速查

| 聚合边界 | 主责 | 核心对象 | 不负责 |
| --- | --- | --- | --- |
| `Account / Config` | 账号身份、权限治理、用户私有配置、平台级配置和运行配置解析 | User、AdminRole、UserProfile、PasswordResetRequest、AccountAuditRecord、UserLlmConfig、UserDataSourceConfig、UserNotificationConfig、NotificationRecipient、SystemConfig、SystemConfigAuditRecord、RuntimeConfigSnapshot | 不承载 Project 资产、Run/Session 状态或知识库版本 |
| `Project / Workspace` | 长期研究容器、权限和用户工作现场恢复 | Project、ProjectPermission、ProjectWorkspace、WorkspaceContext、WorkspacePanelState、WorkspaceInputDraft、WorkspaceObjectRef、ProcessStep | Workspace 不拥有知识资产，不改变 Run/Session/KnowledgeVersion 业务状态 |
| `ConstructionWorkspace / ConstructionRun` | 论文和 Project 资料发现、筛选、补充、入库和知识库写入 | ConstructionWorkspace、ConstructionRun、SearchTermSet、SearchTermVersion、SelectedSearchTerms、AutoUpdateSearchTerms、DataSourcePolicy、ConstructionRunConfigSnapshot、CandidatePaper、CandidateMaterial、DeduplicationDecision、MaterialDeduplicationDecision、PaperScreeningDecision、MaterialScreeningDecision、ManualPaperSupplementRequest、ManualMaterialSupplementRequest、AutoConfirmationPolicy、ConstructionCheckpoint | 不负责 Research/Review 消费知识，也不作为只读知识资产入口 |
| `PaperIdentity` | 全局论文身份归一化 | PaperIdentity、ExternalPaperIdentifier | 不承载 Project 内评分、有效性、上传文件、推送状态或 AI 分析 |
| `ProjectPaper` | 某篇论文在某个 Project 内的私有资产和使用状态 | ProjectPaper、DocumentAsset、DocumentProcessingState、PaperAnalysis | 不改变全局论文身份，不自动暴露资产给其他 Project |
| `ProjectMaterial` | 非论文资料在某个 Project 内的私有资产和使用状态 | ProjectMaterial、MaterialProcessingState、MaterialAnalysis、ContentFormat | 不维护全局资料身份，不自动暴露资产给其他 Project，不让 candidate_sources 参与知识构建 |
| `KnowledgeVersion / Evidence` | 可读取知识版本、引用证据和只读跳转 | KnowledgeVersion、KnowledgeVersionDependency、CitationEvidence、GraphEntityRef、TextSourceKind、KnowledgeSyncState | Graph 和向量索引是可读资产投影与同步状态，不是独立聚合根 |
| `ResearchSession` | 深研对话、检索上下文、回复尝试和引用上下文 | ResearchSession、ResearchTurn、ResearchMessage、ResearchResponseAttempt、ResearchRetrievalContext、ResearchOutputPreference、ResearchSummary、ResearchCitationContext、ResearchSessionMetadata | 不修改论文库或 Project 资料库，不上传论文/资料，不触发图谱写入 |
| `ReviewRun` | 综述输入、大纲、章节、当前终稿、下载和最小追溯 | ReviewRun、ReviewRunBrief、ReviewOutline、ReviewOutlineAssessment、ReviewOutlineVersion、ReviewChapter、ReviewChapterEvidenceContext、ReviewChapterTrace、ReviewFinalIssue、ReviewFinalDraft、ReviewVersionSnapshot | 不跨 ReviewRun 合并历史，不绕过 KnowledgeVersion 和引用证据约束 |
| `ExportJob` | 授权读取和导出产物生成 | ExportJob、ExportScopeSnapshot、ExportFileResult、ExportFailureReason | 不绕过 Review 当前稿 accepted、权限与修订规则 |
| `EmailPushJob` | 邮件推送范围、论文/资料项和收件人发送结果 | EmailPushJob、EmailPushScope、EmailPushPaperItem、EmailPushMaterialItem、EmailPushRecipientResult | 邮件失败不回滚论文或资料入库，不发送空邮件 |
| `Viewpoint` | 观点发布、可见性、治理状态和研究对象引用 | Viewpoint、ViewpointVisibility、ViewpointModerationState、ViewpointReference | 不属于 Project Workspace，不改变被引用 Project/Paper/Topic/Review 状态 |

## 2. 领域对象索引

| 对象 | 类型 | 所属边界 | 说明 | 关联 FR |
| --- | --- | --- | --- | --- |
| `User` | 实体 | Account / Config | 登录、权限和资源归属主体 | FR-001 |
| `AdminRole` | 实体/角色 | Account / Config | 管理员能力标识和最后管理员保护 | FR-005 |
| `UserProfile` | 实体 | Account / Config | 用户基础信息 | FR-001, FR-005 |
| `PasswordResetRequest` | 实体 | Account / Config | 密码重置验证请求 | FR-001, FR-005 |
| `AccountAuditRecord` | 决策/审计记录 | Account / Config | 账号治理审计事实 | FR-005 |
| `UserLlmConfig` | 配置 | Account / Config | 用户私有 LLM 配置 | FR-002 |
| `UserDataSourceConfig` | 配置 | Account / Config | 用户私有研究数据源配置 | FR-003 |
| `UserNotificationConfig` | 配置 | Account / Config | 用户通知偏好 | FR-004 |
| `NotificationRecipient` | 配置 | Account / Config | 用户收件邮箱配置 | FR-004 |
| `SystemConfig` | 配置 | Account / Config | 平台默认能力和硬限制 | FR-006 |
| `RuntimeConfigSnapshot` | 配置快照 | Account / Config | Run/Session/Job 启动前的脱敏配置事实 | FR-007 |
| `Project` | 实体 | Project / Workspace | 长期研究容器 | FR-008 |
| `ProjectPermission` | 授权事实 | Project / Workspace | Project 访问、使用、删除权限 | FR-008 |
| `ProjectWorkspace` | 实体/容器 | Project / Workspace | Project 顶层工作区 | FR-011, FR-014 |
| `ConstructionWorkspace` | 实体/容器 | ConstructionWorkspace / ConstructionRun | Project 唯一构建配置容器 | FR-011, FR-014, FR-020 |
| `WorkspaceContext` | 状态 | Project / Workspace | 用户打开 Workspace 时的恢复上下文 | FR-013 |
| `WorkspacePanelState` | 状态 | Project / Workspace | 面板打开、折叠、焦点和筛选状态 | FR-013 |
| `WorkspaceInputDraft` | 草稿 | Project / Workspace | 未提交输入草稿 | FR-013, FR-017 |
| `ConstructionRun` | 实体/运行 | ConstructionWorkspace / ConstructionRun | 一次手动或自动构建执行 | FR-009, FR-014, FR-020~027 |
| `ResearchSession` | 实体/会话 | ResearchSession | 开放式 Graph-RAG 研究会话 | FR-028~031 |
| `ReviewRun` | 实体/运行 | ReviewRun | 流程式综述写作运行 | FR-032~036 |
| `ExportJob` | 任务对象 | ExportJob | Project/Run/Session 导出任务 | FR-019, FR-030, FR-034 |
| `EmailPushJob` | 任务对象 | EmailPushJob | 论文和 Project 资料邮件推送任务 | FR-004, FR-009, FR-027 |
| `SearchTermSet` | 实体/集合 | ConstructionWorkspace / ConstructionRun | Project 检索词集合 | FR-020 |
| `SearchTermVersion` | 快照 | ConstructionWorkspace / ConstructionRun | 检索词内容快照 | FR-020 |
| `SelectedSearchTerms` | 值对象 | ConstructionWorkspace / ConstructionRun | 手动 Run 本次选择的检索词集合 | FR-014, FR-021 |
| `AutoUpdateSearchTerms` | 值对象 | ConstructionWorkspace / ConstructionRun | 自动 Run 使用的检索词集合 | FR-009, FR-021 |
| `DataSourcePolicy` | 值对象 | ConstructionWorkspace / ConstructionRun | 检索词级数据源策略 | FR-020, FR-021 |
| `ConstructionRunConfigSnapshot` | 配置快照 | ConstructionWorkspace / ConstructionRun | ConstructionRun 启动配置快照 | FR-009, FR-014, FR-021 |
| `CandidatePaper` | 实体/候选 | ConstructionWorkspace / ConstructionRun | 检索得到的候选论文 | FR-021, FR-022 |
| `DeduplicationDecision` | 决策记录 | ConstructionWorkspace / ConstructionRun | 候选论文身份归一化决策 | FR-022 |
| `PaperScreeningDecision` | 决策记录 | ConstructionWorkspace / ConstructionRun | 论文评分与筛选决策 | FR-022 |
| `ManualPaperSupplementRequest` | 实体/请求 | ConstructionWorkspace / ConstructionRun | 用户手动补充论文请求 | FR-023 |
| `CandidateMaterial` | 实体/候选 | ConstructionWorkspace / ConstructionRun | 检索得到的候选 Project 资料 | FR-021, FR-022 |
| `MaterialDeduplicationDecision` | 决策记录 | ConstructionWorkspace / ConstructionRun | 候选资料 Project 内标题与格式组去重决策 | FR-022 |
| `MaterialScreeningDecision` | 决策记录 | ConstructionWorkspace / ConstructionRun | 资料评分与筛选决策 | FR-022 |
| `ManualMaterialSupplementRequest` | 实体/请求 | ConstructionWorkspace / ConstructionRun | 用户手动补充 Project 资料请求 | FR-023 |
| `AutoConfirmationPolicy` | 决策策略 | ConstructionWorkspace / ConstructionRun | 自动 ConstructionRun 的低风险等待点处理策略 | FR-009 |
| `ConstructionCheckpoint` | 状态 | ConstructionWorkspace / ConstructionRun | 构建断点续连状态 | FR-015, FR-026 |
| `PaperIdentity` | 实体 | PaperIdentity | 全局论文身份 | FR-022, FR-023 |
| `ExternalPaperIdentifier` | 值对象 | PaperIdentity | DOI、arXiv ID、URL 等外部标识 | FR-023 |
| `ProjectPaper` | 实体 | ProjectPaper | Project 私有论文关联 | FR-012, FR-022, FR-026 |
| `DocumentAsset` | 实体/资产 | ProjectPaper | PDF、远程文件或解析文本资产 | FR-012, FR-023, FR-024 |
| `DocumentProcessingState` | 状态 | ProjectPaper | 论文全文获取和可用文本来源状态 | FR-024 |
| `PaperAnalysis` | 实体/内容 | ProjectPaper | Project 私有论文结构化 AI 分析 | FR-025 |
| `ProjectMaterial` | 实体 | ProjectMaterial | Project 私有非论文资料条目 | FR-012, FR-022, FR-026 |
| `ContentFormat` | 值对象 | ProjectMaterial | Project 资料文件或内容格式及相似格式组 | FR-021, FR-023, FR-024 |
| `MaterialProcessingState` | 状态 | ProjectMaterial | Project 资料文件获取和文本可用状态 | FR-024 |
| `MaterialAnalysis` | 实体/内容 | ProjectMaterial | Project 私有资料轻量 AI 分析 | FR-025 |
| `KnowledgeVersion` | 实体/版本 | KnowledgeVersion / Evidence | Project 可读取知识库边界 | FR-018, FR-026, FR-028, FR-032 |
| `KnowledgeVersionDependency` | 依赖记录 | KnowledgeVersion / Evidence | Run/Session 对 KnowledgeVersion 的依赖 | FR-018 |
| `KnowledgeSyncState` | 状态 | KnowledgeVersion / Evidence | 关系库、向量库、图谱同步状态 | FR-026 |
| `CitationEvidence` | 证据 | KnowledgeVersion / Evidence | 引用证据 | FR-031, FR-033 |
| `GraphEntityRef` | 引用 | KnowledgeVersion / Evidence | Graph 节点或边引用 | FR-012, FR-031, FR-033 |
| `TextSourceKind` | 值对象 | KnowledgeVersion / Evidence | 文本来源类型 | FR-024, FR-028, FR-033 |
| `ResearchTurn` | 实体/轮次 | ResearchSession | 一轮用户提问与 AI 回复容器 | FR-028, FR-030 |
| `ResearchMessage` | 实体/消息 | ResearchSession | 单条对话文本 | FR-028, FR-030 |
| `ResearchResponseAttempt` | 实体/尝试 | ResearchSession | 一次 AI 回复尝试 | FR-028 |
| `ResearchRetrievalContext` | 上下文 | ResearchSession | Graph-RAG 检索上下文 | FR-028, FR-031 |
| `ResearchOutputPreference` | 值对象 | ResearchSession | 深研输出倾向 | FR-029 |
| `ResearchSummary` | 内容 | ResearchSession | 对话总结 | FR-030 |
| `ResearchCitationContext` | 上下文 | ResearchSession | 深研引用上下文 | FR-031 |
| `ResearchSessionMetadata` | 只读投影 | ResearchSession | 深研会话列表与检索元数据 | FR-030 |
| `ReviewRunBrief` | 输入 | ReviewRun | 综述任务输入简报 | FR-032 |
| `ReviewOutline` | 内容 | ReviewRun | 综述架构 | FR-032 |
| `ReviewOutlineAssessment` | 决策/评估 | ReviewRun | 大纲支撑与自审结果 | FR-032 |
| `ReviewOutlineVersion` | 快照 | ReviewRun | 大纲版本记录 | FR-032, FR-035, FR-036 |
| `ReviewChapter` | 内容 | ReviewRun | 章节内容 | FR-033 |
| `ReviewChapterEvidenceContext` | 上下文 | ReviewRun | 章节撰写证据上下文 | FR-033 |
| `ReviewChapterTrace` | 追溯记录 | ReviewRun | 章节最小追溯 | FR-033, FR-035 |
| `ReviewFinalIssue` | 审查记录 | ReviewRun | 终稿审查问题 | FR-034 |
| `ReviewFinalDraft` | 内容 | ReviewRun | 综述终稿 | FR-034 |
| `ReviewVersionSnapshot` | 快照 | ReviewRun | P2 历史快照 | FR-036 |
| `ExportScopeSnapshot` | 快照 | ExportJob | 导出范围快照 | FR-019, FR-030, FR-034 |
| `ExportFileResult` | 结果 | ExportJob | 导出文件结果 | FR-019 |
| `ExportFailureReason` | 值对象 | ExportJob | 导出失败分类 | FR-019 |
| `EmailPushScope` | 快照 | EmailPushJob | 邮件推送范围 | FR-004, FR-009, FR-027 |
| `EmailPushPaperItem` | 项目 | EmailPushJob | 邮件推送论文项 | FR-004, FR-027 |
| `EmailPushMaterialItem` | 项目 | EmailPushJob | 邮件推送资料项 | FR-004, FR-027 |
| `EmailPushRecipientResult` | 结果 | EmailPushJob | 收件人发送结果 | FR-004 |
| `Viewpoint` | 实体/内容 | Viewpoint | 观点内容 | FR-010 |
| `ViewpointVisibility` | 值对象 | Viewpoint | 观点可见性 | FR-010 |
| `ViewpointModerationState` | 状态 | Viewpoint | 观点治理状态 | FR-010 |
| `ViewpointReference` | 引用 | Viewpoint | 观点引用目标 | FR-010 |

## 3. 关键链路速查

### 3.1 论文进入知识库

```text
CandidatePaper
 -> DeduplicationDecision
 -> PaperIdentity
 -> ProjectPaper
 -> DocumentAsset / DocumentProcessingState
 -> PaperAnalysis
 -> KnowledgeSyncState
 -> KnowledgeVersion
 -> CitationEvidence
```

### 3.2 Project 资料进入知识库

```text
CandidateMaterial
 -> MaterialDeduplicationDecision
 -> MaterialScreeningDecision
 -> ProjectMaterial
 -> DocumentAsset / MaterialProcessingState
 -> MaterialAnalysis
 -> KnowledgeSyncState
 -> KnowledgeVersion
 -> CitationEvidence
```

### 3.3 Research 会话

```text
ResearchSession
 -> ResearchTurn
 -> ResearchRetrievalContext
 -> ResearchResponseAttempt
 -> ResearchMessage
 -> ResearchCitationContext
```

### 3.4 Review 写作

```text
ReviewRunBrief
 -> ReviewOutline / ReviewOutlineAssessment
 -> ReviewChapterEvidenceContext
 -> ReviewChapter
 -> ReviewFinalDraft
 -> 当前已保存稿 Markdown 下载
```

### 3.5 导出与邮件

```text
ExportJob
 -> ExportScopeSnapshot
 -> ExportFileResult / ExportFailureReason
```

```text
EmailPushJob
 -> EmailPushScope
 -> EmailPushPaperItem / EmailPushMaterialItem
 -> EmailPushRecipientResult
```

## 4. 跨边界规则索引

- `Workspace` 只恢复用户操作现场，不拥有 Project 知识资产，也不改变 Run、Session 或 KnowledgeVersion 的业务状态。
- `PaperIdentity` 只负责全局身份归一化；Project 内评分、有效性、推送、文件和 AI 分析属于 `ProjectPaper`。
- `ProjectMaterial` 是 Project-scoped 轻量资料条目；不建立全局资料身份，不维护业务类型字段，只由 `content_format` 表达文件类型。
- `ProjectMaterial` 的 Project 内去重与重复来源处理见 [02-03 构建资产附录](02-03_construction_assets_appendix.md)；版本参与范围承接 [02-02 知识库版本附录](02-02_construction_versioning_appendix.md)。
- `DocumentAsset` 受 Project 授权边界约束；同一 `PaperIdentity` 跨 Project 共享时，不得自动暴露上传文件。
- `DocumentAsset` 承载 Project 资料文件时同样受 Project 授权边界约束；不得因标题或格式相似自动暴露给其他 Project。
- `ConstructionRun` 的写入资格与构建槽接口见 [02-02 知识库版本附录](02-02_construction_versioning_appendix.md)。
- `ConstructionRun` 成功结果区分 `published` 与 `no_change`，后者关联核验既有版本且不发布、不切换默认版本。failed 放弃恢复仍保留 failed；排队不占槽、暂停继续保槽、重跑新 Run 定向接管。状态机与候选转换统一见 [02-02 第 10 章](02-02_construction_versioning_appendix.md#10-构建与知识版本状态机)，恢复条件由 02-04 承载。
- `ResearchSession` 和 `ReviewRun` 承接知识库版本绑定与版本采用接口；稳定绑定、旧依赖、确认边界和冲突裁决统一见 [02-02 知识库版本附录](02-02_construction_versioning_appendix.md)。
- 引用跳转承接 [02-02 知识库版本附录](02-02_construction_versioning_appendix.md) 的 Project、KnowledgeVersion、Evidence 校验及安全空态接口。
- Graph 和向量索引是 `KnowledgeVersion` 的可读资产投影与同步状态，不是独立聚合根。
- Project 知识资产面板、Research 引用跳转和 Review 引用跳转都是只读探索入口，不得触发上传、删除、解析、入库、推送或图谱写入。
- 人工修改内容不得被 Agent 静默覆盖；重新生成涉及人工确认或人工修改内容时必须要求用户确认。
- 导出只能包含用户有权限访问的 Project、Run/Session 和文件；导出不得绕过 Review 当前稿 accepted、权限与修订规则。
- 邮件推送只包含当前 Project 中未推送且用户有权限接收的有效论文和有效 Project 资料；空邮件不得发送，发送失败不得回滚论文或资料入库。
- `Viewpoint` 独立于 Project Workspace；`ViewpointReference` 可以引用研究对象，但不得改变被引用对象状态。

## 5. FR 到 Domain 边界映射

| FR | 主领域边界 | 关键对象 |
| --- | --- | --- |
| FR-001 | Account / Config | User、UserProfile、PasswordResetRequest |
| FR-002 | Account / Config | UserLlmConfig、RuntimeConfigSnapshot |
| FR-003 | Account / Config, ConstructionWorkspace / ConstructionRun | UserDataSourceConfig、DataSourcePolicy、RuntimeConfigSnapshot |
| FR-004 | Account / Config, EmailPushJob | UserNotificationConfig、NotificationRecipient、EmailPushRecipientResult |
| FR-005 | Account / Config | AdminRole、AccountAuditRecord |
| FR-006 | Account / Config | SystemConfig、SystemConfigAuditRecord |
| FR-007 | Account / Config | RuntimeConfigSnapshot |
| FR-008 | Project / Workspace | Project、ProjectPermission |
| FR-009 | ConstructionWorkspace / ConstructionRun, EmailPushJob | AutoUpdateSearchTerms、AutoConfirmationPolicy、EmailPushScope |
| FR-010 | Viewpoint | Viewpoint、ViewpointVisibility、ViewpointModerationState、ViewpointReference |
| FR-011 | Project / Workspace | ProjectWorkspace、ConstructionWorkspace、WorkspaceObjectRef |
| FR-012 | Project / Workspace, ProjectPaper, ProjectMaterial, KnowledgeVersion / Evidence | ProjectKnowledgeAssetPanel、ProjectPaper、ProjectMaterial、DocumentAccessRef、ProjectGraphView |
| FR-013 | Project / Workspace | WorkspaceContext、WorkspacePanelState、WorkspaceInputDraft |
| FR-014 | Project / Workspace, ConstructionWorkspace / ConstructionRun, ResearchSession, ReviewRun | ConstructionRun、ResearchSession、ReviewRun |
| FR-015 | ConstructionWorkspace / ConstructionRun, ResearchSession, ReviewRun | ConstructionCheckpoint、ResearchResponseAttempt、ReviewChapterTrace |
| FR-016 | Project / Workspace | ProcessStep |
| FR-017 | Cross-boundary | 内容来源优先级、ContentOverwriteRequested |
| FR-018 | KnowledgeVersion / Evidence, ResearchSession, ReviewRun | KnowledgeVersion、KnowledgeVersionDependency |
| FR-019 | ExportJob, ReviewRun | ExportJob、ExportScopeSnapshot |
| FR-020 | ConstructionWorkspace / ConstructionRun | SearchTermSet、SearchTermVersion、DataSourcePolicy |
| FR-021 | ConstructionWorkspace / ConstructionRun | SelectedSearchTerms、AutoUpdateSearchTerms、CandidatePaper、CandidateMaterial、ContentFormat |
| FR-022 | ConstructionWorkspace / ConstructionRun, PaperIdentity, ProjectPaper, ProjectMaterial | CandidatePaper、CandidateMaterial、DeduplicationDecision、MaterialDeduplicationDecision、PaperScreeningDecision、MaterialScreeningDecision |
| FR-023 | ConstructionWorkspace / ConstructionRun, PaperIdentity, ProjectPaper, ProjectMaterial | ManualPaperSupplementRequest、ManualMaterialSupplementRequest、ExternalPaperIdentifier、DocumentAsset |
| FR-024 | ProjectPaper, ProjectMaterial | DocumentAsset、DocumentProcessingState、MaterialProcessingState、TextSourceKind |
| FR-025 | ProjectPaper, ProjectMaterial | PaperAnalysis、MaterialAnalysis |
| FR-026 | ConstructionWorkspace / ConstructionRun, ProjectPaper, ProjectMaterial, KnowledgeVersion / Evidence | KnowledgeSyncState、KnowledgeVersion、GraphEntityRef |
| FR-027 | EmailPushJob, ProjectPaper, ProjectMaterial | EmailPushJob、EmailPushPaperItem、EmailPushMaterialItem、ProjectPaper、ProjectMaterial |
| FR-028 | ResearchSession, KnowledgeVersion / Evidence | ResearchSession、ResearchTurn、ResearchRetrievalContext |
| FR-029 | ResearchSession | ResearchOutputPreference |
| FR-030 | ResearchSession, ExportJob | ResearchSummary、ResearchSessionMetadata、ExportJob |
| FR-031 | ResearchSession, KnowledgeVersion / Evidence, ProjectPaper, ProjectMaterial | ResearchCitationContext、CitationEvidence、GraphEntityRef |
| FR-032 | ReviewRun, KnowledgeVersion / Evidence | ReviewRunBrief、ReviewOutline、ReviewOutlineAssessment |
| FR-033 | ReviewRun, KnowledgeVersion / Evidence, ProjectPaper, ProjectMaterial | ReviewChapterEvidenceContext、ReviewChapter、CitationEvidence |
| FR-034 | ReviewRun, ExportJob | ReviewFinalDraft、ReviewFinalIssue |
| FR-035 | ReviewRun | ReviewChapterTrace、ReviewOutlineVersion |
| FR-036 | ReviewRun | ReviewVersionSnapshot |

## 6. 参考优先级

1. 完整领域规则以 `02_domain_core.md` 及 `02-02`、`02-03`、`02-04` 同规格专题附录为准；需求含义与验收仍以 `01_functional_requirements.md` 为最高依据。
2. 功能需求编号、优先级和分层追踪通过 `01-01-FR-reference.md` 速查，冲突时以 `01_functional_requirements.md` 为准。
3. 本文只提供领域对象和聚合边界速查，不定义 API、数据库字段、Provider SDK、队列实现或文件存储实现。

本次修订 v1.6（2026-10-16）：按R2-A移除独立ReviewExportableVersion速查对象，保留当前稿与知识版本规则。
