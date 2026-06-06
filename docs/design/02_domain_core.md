# Domain Core 设计

文档版本：v1.16
更新日期：2026-06-06
依据文档：`00_layers.md`、`01_functional_requirements.md`、`01-01-FR-reference.md`  
用途：从 FR 中提炼 Research Paper Base 的核心业务对象、对象关系、状态、生命周期和不变量。本文不定义 UI 布局、API 路径、数据库字段、Provider SDK、队列实现或文件存储实现。

## 1. 设计边界

Domain Core 回答“这个业务世界如何成立”。它必须覆盖所有 P0/P1 FR 背后的稳定业务概念和不可绕过规则，用于开发的标准规则。

冲突裁决：

1. 本文与 `01_functional_requirements.md` 冲突时，以 FR 为准。
2. 本文只定义业务事实和规则；接口由 `04_api_contracts.md` 定义，流程编排由 `05_application_use_cases.md` 定义，Agent/Knowledge 算法由 `06_agent_knowledge_services.md` 定义，持久化由 `07_data_persistence.md` 和 `07_data_schema.sql` 定义。
3. 本文中的“必须”表示领域不变量，任何 UI、API、后台任务、Agent 或适配器实现都不得绕过。

## 2. 核心领域模型

### 2.1 核心对象分类与聚合边界

Domain Core 中的对象按职责分为以下类型：

- 领域实体：拥有业务身份、生命周期和不变量，例如 `Project`、`ConstructionRun`、`ResearchSession`、`ReviewRun`、`ProjectPaper`、`ProjectMaterial`。
- 值对象：依附于实体或决策使用，不独立拥有生命周期，例如 `ExternalPaperIdentifier`、`DataSourcePolicy`、`TextSourceKind`、`ContentFormat`。
- 决策记录：保存 Agent 或人工判断的业务事实和依据，例如 `DeduplicationDecision`、`PaperScreeningDecision`、`MaterialDeduplicationDecision`。
- 配置快照：固化任务启动时的脱敏配置事实，例如 `RuntimeConfigSnapshot`、`ConstructionRunConfigSnapshot`。
- 只读投影：面向 Workspace 或列表展示的读取模型，例如 `ProjectPaperLibraryView`、`ProjectMaterialLibraryView`、`ProjectGraphView`、`ResearchSessionMetadata`。
- 任务对象：描述异步产物、通知或后台执行的业务边界，例如 `ExportJob`、`EmailPushJob`。

主要聚合边界：

| 聚合边界 | 承载对象 | 领域含义 |
| --- | --- | --- |
| `Account / Config` | User、AdminRole、UserProfile、PasswordResetRequest、AccountAuditRecord、UserLlmConfig、UserDataSourceConfig、UserNotificationConfig、NotificationRecipient、SystemConfig、SystemConfigAuditRecord、RuntimeConfigSnapshot | 账号身份、权限治理、用户私有配置、平台级配置和运行配置解析边界；SystemConfig 是平台级配置，不属于单个 User |
| `Project / Workspace` | Project、ProjectPermission、ProjectWorkspace、WorkspaceContext、WorkspacePanelState、WorkspaceInputDraft | 长期研究容器和用户工作现场恢复边界 |
| `ConstructionWorkspace / ConstructionRun` | ConstructionWorkspace、ConstructionRun、SearchTermSet、SearchTermVersion、SelectedSearchTerms、AutoUpdateSearchTerms、DataSourcePolicy、ConstructionRunConfigSnapshot、CandidatePaper、CandidateMaterial、DeduplicationDecision、PaperScreeningDecision、MaterialDeduplicationDecision、MaterialScreeningDecision、ManualPaperSupplementRequest、ManualMaterialSupplementRequest、AutoConfirmationPolicy、ConstructionCheckpoint | 论文和 Project 资料发现、筛选、入库和知识库写入边界；检索词集合归 ConstructionWorkspace，单次选择、候选、决策和断点归 ConstructionRun |
| `PaperIdentity` | PaperIdentity、ExternalPaperIdentifier | 全局论文身份归一化边界；只回答候选论文是否指向同一篇真实论文 |
| `ProjectPaper` | ProjectPaper、DocumentAsset、DocumentProcessingState、PaperAnalysis | Project 私有论文资产边界；承载评分、有效性、推送状态、用户上传资产、文本可用状态和已确认分析 |
| `ProjectMaterial` | ProjectMaterial、MaterialProcessingState、MaterialAnalysis、ContentFormat | Project 私有非论文资料资产边界；承载项目资料库编号、轻量元数据、标题与格式组去重、备选来源、处理状态和已确认重要摘要 |
| `KnowledgeVersion / Evidence` | KnowledgeVersion、KnowledgeVersionDependency、CitationEvidence、GraphEntityRef、TextSourceKind、KnowledgeSyncState | 可读取知识版本、引用证据和只读跳转边界；Graph 和向量索引是 KnowledgeVersion 的可读资产投影与同步状态，不是独立聚合根 |
| `ResearchSession` | ResearchSession、ResearchTurn、ResearchMessage、ResearchResponseAttempt、ResearchRetrievalContext、ResearchOutputPreference、ResearchSummary、ResearchCitationContext、ResearchSessionMetadata | 深研对话、检索上下文和回复尝试边界；ResearchSessionMetadata 是只读投影 |
| `ReviewRun` | ReviewRun、ReviewRunBrief、ReviewOutline、ReviewOutlineAssessment、ReviewOutlineVersion、ReviewChapter、ReviewChapterEvidenceContext、ReviewChapterTrace、ReviewFinalIssue、ReviewFinalDraft、ReviewExportableVersion、ReviewVersionSnapshot | 综述写作输入、大纲、章节、终稿和导出版本边界；ReviewVersionSnapshot 是 P2 历史快照 |
| `ExportJob` | ExportJob、ExportScopeSnapshot、ExportFileResult、ExportFailureReason | 授权读取和导出产物生成边界 |
| `EmailPushJob` | EmailPushJob、EmailPushScope、EmailPushPaperItem、EmailPushMaterialItem、EmailPushRecipientResult | 邮件推送范围、论文/资料项和收件人发送结果边界 |
| `Viewpoint` | Viewpoint、ViewpointVisibility、ViewpointModerationState、ViewpointReference | 观点广场内容发布、可见性、治理状态和研究对象引用边界 |

### 2.2 账号、权限与配置

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `User` | 登录、权限和资源归属主体 | 用户有启用/禁用/删除等账号状态；禁用账号不得访问受保护资源；管理员删除用户会删除该用户相关 Project 与关联私人数据 | FR-001, FR-005 |
| `AdminRole` | 管理员能力标识 | 首位注册用户自动成为管理员；系统必须至少保留一个启用管理员 | FR-005 |
| `UserProfile` | 用户基础信息 | 用户可维护自己的基础信息；MVP 管理员只能在账号治理边界内查看基础状态和修改用户邮箱，不得修改用户 Project 权限 | FR-001, FR-005 |
| `PasswordResetRequest` | 密码重置验证请求 | 密码找回或管理员触发重置必须经过安全验证流程；MVP 管理员重置密码可由系统生成新密码并允许管理员复制转交；未实现时不得形成可用入口 | FR-001, FR-005 |
| `AccountAuditRecord` | 账号治理审计事实 | 管理员禁用、删除、重置密码、修改邮箱、授权或撤销管理员权限时必须记录操作者、目标用户、动作、时间和结果；审计日志查询后台为 P2 | FR-005 |
| `UserLlmConfig` | 用户私有 LLM 配置 | 用户配置只归本人使用；密钥不得明文暴露；配置变更不得修改系统默认配置 | FR-002 |
| `UserDataSourceConfig` | 用户私有研究数据源配置 | 论文数据源和非论文资料来源可启用/禁用；匿名访问、必填密钥、限流和失效状态必须可区分 | FR-003 |
| `UserNotificationConfig` | 用户收件人与通知偏好 | 用户收件人和推送偏好不改变调度周期，也不得绕过邮件推送范围规则 | FR-004 |
| `NotificationRecipient` | 用户收件邮箱配置 | 每个收件邮箱独立保存论文/资料推送开关、通知偏好和验证/测试结果；测试失败不得改变已保存偏好 | FR-004 |
| `SystemConfig` | 管理员维护的平台默认能力和限制 | MVP 包含系统默认 LLM、数据源、邮件发送配置、基础连接和基础安全限制；P1 包含模型白名单、数据源范围、速率上限和并发上限；P2 包含调度控制、系统状态面板和系统诊断后台 | FR-006 |
| `SystemConfigAuditRecord` | 系统配置审计事实 | 系统配置变更必须记录操作者、时间、配置类型和结果；不得泄露系统级密钥明文 | FR-006 |
| `RuntimeConfigSnapshot` | 任务启动时解析后的脱敏配置事实 | Agent/Job 启动前必须生成；不得保存或返回密钥明文；系统默认不得静默替换用户显式选择 | FR-007 |

配置不变量：

- 密码不得明文存储、明文返回或在保存后恢复为明文。
- 首位注册用户的管理员授予必须具备并发保护；任何管理员权限变更、禁用或删除操作都不得破坏最后一个启用管理员账号。
- 禁用账号的既有会话在下一次鉴权或刷新时必须失效；被禁用用户只能访问无需账号身份的公开入口。
- 管理员不得查看用户私人 LLM、数据源、通知配置中的密钥或私密配置明文；账号治理只允许访问必要基础账号信息、修改用户邮箱、重置密码、启用/禁用/删除账号和授予/撤销管理员权限。
- 管理员不得更改用户 Project 权限，也不得代替用户管理 Project 授权。
- 管理员删除用户会删除该用户相关 Project 与关联私人数据；该删除不得破坏全局论文身份、其他用户数据或其他 Project 引用。
- 用户个人 LLM 或数据源配置存在且有效时，系统默认配置不得静默覆盖它。
- 用户未显式选择当前模型时，Agent 任务不得静默回落到系统默认模型；必须要求用户选择或修复配置。
- 用户已有显式选择的模型或数据源在系统默认变化后不得被静默替换；只有启动校验失败时才提示处理。
- 研究数据源解析遵循用户个人配置优先；仅用户缺失搜索研究数据源配置时才回落系统默认配置。
- MVP 基础安全限制优先于用户配置；P1 模型白名单、允许数据源范围、速率上限、并发上限实现后同样优先于用户配置，不满足时任务不得静默继续。
- 邮件运行时配置由用户收件人/偏好与系统邮件发送能力组合而成。
- 多收件人配置下，每个收件人是否接收论文/资料推送、接收内容维度和失败/成功通知偏好必须独立生效。
- 系统邮件发送能力缺失或不可用时，测试邮件和邮件推送必须失败为可诊断状态，不得修改用户已保存通知偏好。
- 配置解析失败必须阻止对应任务启动，并在 MVP 阶段保留缺失配置、密钥不可用、数据源禁用、连接不可用等诊断分类；P1 限制能力实现后，还必须保留超出白名单、速率或并发超过上限等诊断分类。

### 2.3 Project 与 Workspace

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `Project` | 长期研究容器 | Project 是 Construction、Research、Review 的共同上下文；用户默认拥有自己 Project 的全部权限 | FR-008 |
| `ProjectPermission` | Project 授权事实 | 权限分为访问、使用和删除；Owner 在账号有效时必须始终拥有自己 Project 的全部权限；跨用户访问/使用授权为 P2 预留能力 | FR-008 |
| `ProjectWorkspace` | Project 顶层工作区 | 置顶承载当前 Project 的唯一 ConstructionWorkspace、ResearchSession 列表和 ReviewRun 列表；不直接平铺历史 ConstructionRun | FR-011, FR-014 |
| `ConstructionWorkspace` | Project 唯一构建配置容器 | 每个 Project 有且仅有一个；与 ResearchSession、ReviewRun 作为 ProjectWorkspace 顶层并列对象；内部承载 SearchTermSet、自动更新设置和历史 ConstructionRun | FR-011, FR-014, FR-020 |
| `WorkspaceContext` | 用户打开 Project Workspace 时的恢复上下文 | 按用户、Project、对象类型和对象 ID 保存；失效时必须降级到安全空态 | FR-013 |
| `WorkspacePanelState` | Workspace 基础面板状态 | 只保存当前用户在当前 Project 下的面板打开、折叠、焦点和基础筛选状态；不得影响 Project 资产、Run/Session 状态或知识库版本 | FR-013 |
| `WorkspaceInputDraft` | Workspace 输入草稿 | 按用户、Project、对象类型和对象 ID 保存未提交输入；只能恢复为草稿，不得自动提交、启动任务或覆盖已确认内容 | FR-013, FR-017 |
| `WorkspaceObjectRef` | Workspace 当前打开对象引用 | 只能指向当前 Project 的 ConstructionWorkspace、ResearchSession 或 ReviewRun | FR-011, FR-014 |
| `ProcessStep` | 流程式 Agent 的业务步骤状态与结果摘要 | 只记录业务阶段、等待项、错误分类和结果摘要；步骤动作必须能追溯到对应 Agent FR，不得提供无法追溯的写操作或承载 UI 展示细节 | FR-016 |

Project 状态：

| 状态 | 可进入 Workspace | 可写交互 | 自动调度 | 领域含义 |
| --- | --- | --- | --- | --- |
| `active` | 是 | 是 | 取决于 ConstructionWorkspace 自动更新设置 | 正常研究状态 |
| `archived` | 是 | 只读；导出可作为受控读型产物生成 | 否 | 历史保留状态，不允许新建、启动、继续生成、上传、删除、重跑或刷新依赖等写操作 |
| `deleted` | 否 | 否 | 否 | 软删除状态，默认不在普通 Project 列表展示 |

Project 不变量：

- Workspace 状态只恢复用户操作现场，不拥有 Project 知识资产，也不得改变 Run、Session 或 KnowledgeVersion 的业务状态。
- Project 权限只分为 `access`、`use`、`delete` 三类：`access` 允许进入 Workspace 和查看 Project 资产；`use` 允许创建、启动、继续或操作 Run/Session、上传补充资料和触发生成等互动能力；`delete` 允许软删除 Project、清理 Project 私人资产或执行等效高风险删除操作。
- Project Owner 默认拥有自己 Project 的 `access`、`use`、`delete` 全部权限；只要 Owner 账号处于有效状态，这些默认权限不得被撤销、降级或被共享授权配置覆盖。
- 将 Project 的 `access` 或 `use` 权限授权给其他用户属于 P2 共享协作能力；未实现时不得阻塞 Owner 对自己 Project 的 P0 创建、进入、使用和管理主流程。
- P0 阶段未实现共享协作授权时，非 Owner 用户不得访问或使用他人 Project。
- Project 只定义 `active`、`archived`、`deleted` 生命周期状态；不得用 Project `paused` 表达自动更新停用。
- 自动更新启停属于 ConstructionWorkspace 配置，不改变 Project 状态，也不得影响 ResearchSession、ReviewRun 或手动 ConstructionRun 的可用性。
- Project 归档、软删除和私人资产清理必须经过权限校验。
- `deleted` 是软删除，不得物理破坏其他 Project、全局论文记录或其他用户数据；deleted Project 不得进入 Workspace，也不得在 Workspace 内作为可见 Project 状态展示。
- Project 私人资产清理只可清理该 Project 独占的运行记录、Run/Session、Project-Paper 关联、ProjectMaterial 关联、文件资产、解析文本、向量索引、图谱文件和临时产物。
- Project 私人资产清理不得删除全局论文身份、其他 Project 仍引用的共享论文、其他 Project 仍引用的资料文件、其他用户数据或默认保留的已完成导出文件。
- ProjectWorkspace 的顶层对象结构固定为：当前 Project 唯一 ConstructionWorkspace、ResearchSession 列表和 ReviewRun 列表；历史 ConstructionRun 只能作为 ConstructionWorkspace 内部对象查看，不得与 ResearchSession 或 ReviewRun 平级展示为 ProjectWorkspace 顶层对象。
- ConstructionWorkspace 只承载构建配置、自动更新设置、历史 ConstructionRun、构建诊断和构建结果入口；它本身不得被当作一次运行、KnowledgeVersion 或可复制实例。
- Workspace 上下文恢复不得自动触发重跑、重新生成、重新检索、导出或覆盖。
- 已删除、无权限、归档只读或状态不允许继续的上下文不得恢复为可写状态。
- WorkspaceContext 只能恢复当前用户有权访问的当前 Project 对象；目标对象不存在、已删除、越权、类型不匹配或 Project 状态不允许时，必须降级到安全空态并保留可诊断原因。
- WorkspacePanelState 只能影响显示偏好和只读筛选焦点；不得改变论文有效性、评分、推送状态、KnowledgeVersion、Run/Session 状态或任何 Agent 步骤结果。
- WorkspaceInputDraft 只能保存用户尚未提交的输入文本、选项草稿或局部编辑草稿；恢复后仍必须由用户显式提交或确认，且不得覆盖人工确认或人工修改内容。
- 更细粒度的滚动位置、日志定位和步骤落点恢复属于 P1 增强；未实现时不得影响 P0 的对象恢复、基础面板状态和输入草稿恢复。

## 3. Run / Session 生命周期

### 3.1 实例类型

| 对象 | 类型 | 读写角色 | 核心规则 | 关联 FR |
| --- | --- | --- | --- | --- |
| `ConstructionRun` | 流程式运行 | Project 知识库写入者 | 一次手动或自动构建执行；同一 Project 同时只能有一个 active 写入者 | FR-009, FR-014, FR-020~027 |
| `ResearchSession` | 开放式会话 | Knowledge Version 消费者 | 创建时绑定 Knowledge Version；同一 Session 一次只能有一个流式回复追加 | FR-028~031 |
| `ReviewRun` | 流程式写作运行 | Knowledge Version 消费者 | 创建时绑定 Knowledge Version；大纲、章节、终稿和可导出版本受内容保护和写锁约束 | FR-032~036 |
| `ExportJob` | 异步产物任务 | 授权读取者 | 导出范围必须绑定用户有权限访问的 Project/Run/Session；不得绕过 Review 终稿生成规则 | FR-019, FR-030, FR-034 |
| `EmailPushJob` | 邮件推送任务 | 授权通知者 | 只推送当前 Project 中未推送且用户有权限接收的有效论文和有效 Project 资料；空邮件不得发送 | FR-004, FR-009, FR-027 |
| `AutoConfirmationPolicy` | 自动 ConstructionRun 的人工等待点处理策略 | 决策确定者 | 只能处理可安全自动确认、跳过、降级或局部失败的无人值守等待点；不得让自动 Run 等待用户响应 | FR-009 |

### 3.2 通用状态

| 状态 | 含义 | 领域约束 |
| --- | --- | --- |
| `draft` | 已创建但未启动 | 可编辑配置，可启动或删除 |
| `queued` | 已提交等待执行 | 可取消，应可诊断排队原因 |
| `running` | 后台任务或流式回复执行中 | 可查看阶段，可按规则取消 |
| `paused` | Run 的所有异步运行任务均已暂停 | 只适用于流程式 Run；Session 不触发暂停态 |
| `waiting_user` | 等待人工确认、补充或修复 | 不得静默跳过高风险确认 |
| `succeeded` | 成功完成 | 结果只读保留，可导出或复制配置创建新实例 |
| `failed` | 失败并带诊断原因 | 原有成功内容不得被失败任务破坏 |
| `cancelled` | 用户或系统取消 | 不得写入成功态半成品 |
| `archived` | 会话或运行归档 | 不得继续追加消息、回复、总结或生成结果 |

状态不变量（FR-015）：

- 已成功、已取消、已归档的历史对象不得被原地改回 running；需要重试时应记录新 attempt，需要重跑时应创建新实例或新运行结果。
- 暂停是 Run 状态，不是 Session 状态；只有当 ConstructionRun 或 ReviewRun 中所有异步运行任务均暂停时，该 Run 才能进入 `paused`。
- ResearchSession 不触发暂停态；其后端流式回复可取消、失败、重试或重连，但 Session 本身不因单次回复控制变为 `paused`。
- 重试、重连和重跑均为 P1 受控能力：重试是重新尝试后端运行一次，重连是从断点继续，重跑是按原实例原始输入、配置和数据从头开始运行。
- 取消、暂停、恢复、重试、重连、重跑、复制、删除、归档等操作必须受权限、状态和内容保护规则约束。
- P1 的复制、重试、重连、重跑、归档、删除不得破坏原实例。
- 同一个 Project 的历史 Construction Run 只能从 ConstructionWorkspace 内部承载，不与 ResearchSession / ReviewRun 平级作为 Workspace 总入口。

### 3.3 重试、重连与重跑

| 操作 | 优先级 | 领域含义 | 领域约束 |
| --- | --- | --- | --- |
| `retry` / 重试 | P1 | 对同一后端运行单元重新尝试执行一次 | 必须记录新的 attempt、失败原因、重试次数和结果；不得覆盖原失败诊断 |
| `reconnect` / 重连 | P1 | 基于断点从未完成位置继续执行 | 必须依赖完整状态记录、可续连位置、中间临时文件引用和一致性校验；断点不可信时不得继续 |
| `rerun` / 重跑 | P1 | 按原实例的原始输入、配置和数据从头开始运行 | 必须保留原实例；新运行不得复用原未完成中间写入作为成功结果 |

重连不变量：

- 可重连对象必须记录运行阶段、子任务状态、已提交正式数据、未提交临时数据、临时文件引用、断点位置、失败原因、重试次数、操作者决策和清理状态。
- 重连前必须校验断点、正式数据和中间临时文件仍然一致；临时文件缺失、损坏、越权、过期或与状态记录不匹配时，不得继续重连，只能失败、重试或重跑。
- 重连只能从已成功写入且状态一致的位置之后继续；不得重复写入已成功子内容，也不得跳过未完成子内容。
- 重连完成并生成正式数据后，系统必须清理已完成链路不再需要的临时文件，并保留清理结果；清理失败不得把临时文件冒充为正式资产。
- 取消、失败超时或用户选择不继续时，未发布中间写入和可续连临时文件必须按运行类型进入清理流程；清理不得破坏已发布 KnowledgeVersion、已确认内容或其他 Run/Session 资产。

### 3.4 锁与互斥

| 互斥点 | 保护对象 | 不变量 |
| --- | --- | --- |
| Project 构建写锁 | Project 知识库 | 同一 Project 同时只允许一个 active ConstructionRun 写入知识库 |
| 调度锁 | Project + 调度窗口 | 重复调度不得创建重复 automatic ConstructionRun |
| Research 流式锁 | ResearchSession | 同一 Session 一次只允许一个流式回复追加 |
| Review 章节锁 | ReviewRun + Chapter | 同一章节不得同时存在多个生成、审查、保存或重新生成任务写入当前内容 |
| Review 终稿锁 | ReviewRun Final | 终稿汇总、终审和可导出版本生成不得并发改写同一最终稿 |
| 内容覆盖锁 | 受保护内容 | 覆盖确认期间内容变化时必须要求刷新后重试 |

## 4. Construction 领域模型

论文进入 Project 知识库的领域主链路：

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

非论文 Project 资料进入 Project 知识库的领域主链路：

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

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `SearchTermSet` | Project 检索词集合 | 属于 ConstructionWorkspace；用于手动 selected 构建和自动更新；每条检索词应能够单独管理，包括编辑、删除、是否参与自动更新等 | FR-020 |
| `SearchTermVersion` | ConstructionWorkspace 内的检索词内容快照 | 保存自然语言关键词、布尔表达式、同义词/缩写、排除词、生成理由、预期覆盖方向、确认时间、修改来源、自动更新开关和数据源策略；新生成或新增检索词默认 `auto_update_enabled=true` | FR-020 |
| `SelectedSearchTerms` | 单次手动 ConstructionRun 本次选择的检索词集合 | 不改变检索词自身的自动更新开关 | FR-014, FR-021 |
| `AutoUpdateSearchTerms` | 自动 Run 使用的检索词集合 | 只包含 `auto_update_enabled=true` 的检索词 | FR-009, FR-021 |
| `DataSourcePolicy` | 检索词级数据源策略 | 未显式选择时默认使用用户和系统当前可解析的全部数据源 | FR-020, FR-021 |
| `ConstructionRunConfigSnapshot` | ConstructionRun 启动配置快照 | 固化本次检索词内容、检索词来源、数据源策略、解析后数据源、配置来源、检索时间范围、返回数量上限和触发方式 | FR-009, FR-014, FR-021 |
| `CandidatePaper` | 检索得到的候选论文 | 必须记录来源检索词、来源数据源和基础元数据；论文元数据保持严格结构 | FR-021, FR-022 |
| `CandidateMaterial` | 检索得到的候选非论文 Project 资料 | 必须记录来源检索词、来源数据源或资料来源、标题或待补充标题状态、`content_format`、URL/文件线索和最小可追溯信息 | FR-021, FR-022 |
| `DeduplicationDecision` | 候选论文身份归一化决策 | 记录候选论文与 PaperIdentity 或既有 ProjectPaper 的匹配依据、冲突、操作者/Agent 来源、误合并撤销状态 | FR-022 |
| `MaterialDeduplicationDecision` | 候选资料 Project 内去重决策 | 记录候选资料与既有 ProjectMaterial 的标题、`content_format_group`、相似度、重复/疑似重复判断、`candidate_sources` 写入结果、操作者/Agent 来源和误合并撤销状态 | FR-022 |
| `PaperScreeningDecision` | 论文评分与筛选决策 | 记录评分、有效性、评分阈值来源、人工调整、确认状态和可追溯理由；确认前不得进入下载解析 | FR-022 |
| `MaterialScreeningDecision` | 资料评分与筛选决策 | 记录评分、有效性、评分阈值来源、人工调整、确认状态和可追溯理由；确认前不得进入文件获取解析 | FR-022 |
| `ManualPaperSupplementRequest` | 用户手动补充论文请求 | 记录补充方式、提交人、来源值、解析结果、确认状态和失败原因；不得在用户确认前写入 ProjectPaper | FR-023 |
| `ManualMaterialSupplementRequest` | 用户手动补充 Project 资料请求 | 记录补充方式、提交人、来源值、`content_format`、解析结果、标题草稿/确认状态和失败原因；不得在用户确认前写入 ProjectMaterial | FR-023 |
| `PaperIdentity` | 全局论文身份 | 使用 DOI、arXiv ID、外部 ID、标准化标题等归一化；跨 Project 共享 | FR-022, FR-023 |
| `ExternalPaperIdentifier` | DOI、arXiv ID、URL 等外部标识 | 必须归一化类型和值，并记录解析来源；解析到多个候选或关键元数据冲突时必须要求用户确认 | FR-023 |
| `ProjectPaper` | Project 私有论文关联 | 同一 Project 不得重复关联同一论文；保存有效性、评分、推送状态和分析结果 | FR-012, FR-022, FR-026 |
| `ProjectMaterial` | Project 私有非论文资料条目 | 同一 Project 内按 `normalized_title + content_format_group` 去重；保存项目资料库编号、标题、`content_format`、主来源、`candidate_sources`、有效性、推送状态和重要摘要 | FR-012, FR-022, FR-026 |
| `ContentFormat` | Project 资料文件或内容格式 | 表达资料文件类型和相似格式组；P0 支持文档、演示、HTML、Markdown/纯文本、类字典、Notebook 和代码文件；P1 数据表默认不参与 KnowledgeVersion；P2 多媒体为扩展 | FR-021, FR-023, FR-024 |
| `DocumentAsset` | PDF、远程文件、Project 资料文件或解析文本资产 | 记录访问引用、资产来源、解析状态、失败原因、摘要降级或不参与知识构建标记；用户上传资产必须绑定提交人和 Project 授权边界 | FR-012, FR-023, FR-024 |
| `DocumentProcessingState` | 论文全文获取和可用文本来源状态 | 记录下载、解析、用户上传替代、重试后的最终可用文本来源；全文解析与摘要降级必须可区分 | FR-024 |
| `MaterialProcessingState` | Project 资料文件获取和文本可用状态 | 记录下载/上传、解析、格式支持、可用文本来源、不参与 KnowledgeVersion、失败原因和重试结果 | FR-024 |
| `PaperAnalysis` | Project 私有论文结构化 AI 分析 | 绑定 ProjectPaper、TextSourceKind 和 DocumentProcessingState；至少包含一句话总结、亮点、相关性要点、方法与创新；可被人工编辑和确认 | FR-025 |
| `MaterialAnalysis` | Project 私有资料轻量 AI 分析 | 绑定 ProjectMaterial、TextSourceKind 和 MaterialProcessingState；至少包含重要信息摘要和 Project 相关性要点；Agent 生成标题、来源或摘要必须可区分草稿/确认状态 | FR-025 |
| `KnowledgeSyncState` | 关系库、向量库、图谱同步状态 | 未同步或失败数据不得标记为可检索或图谱可用 | FR-026 |
| `ConstructionCheckpoint` | 构建断点续连状态 | 记录 ConstructionRun 子内容写入进度、重试次数、失败原因、可续连位置、中间临时文件引用、清理状态和用户继续/停止决策；不得替代错误日志 | FR-015, FR-026 |

Construction 不变量：

- 手动 ConstructionRun 使用用户本次 selected 检索词集合；自动 ConstructionRun 使用 AutoUpdateSearchTerms，即当前由用户维护配置后仍满足 `auto_update_enabled=true` 的检索词集合。
- 历史 ConstructionRun 必须能基于 ConstructionRunConfigSnapshot 复现当时的检索词内容、数据源策略和启动参数，即使当前检索词已被修改或删除。
- 检索词未确认时，手动构建不得进入多源检索阶段。
- 检索词生成失败时，用户手动输入并确认的检索词应形成同等可追溯的 SearchTermVersion。
- 新生成或新增的 SearchTermVersion 默认参与系统自动更新；用户编辑检索词、调整数据源策略或关闭自动更新，均是在 `auto_update_enabled=true` 默认态基础上修改。
- 不存在独立的检索词 `enabled` 领域状态；手动构建是否使用某个检索词只由本次 SelectedSearchTerms 决定，自动构建是否使用只由 `auto_update_enabled` 决定。
- 删除检索词只影响之后按检索词检索时的可选集合和自动更新集合；不得删除历史 Run、候选论文、候选资料、ProjectPaper、ProjectMaterial、KnowledgeVersion、图谱、向量或其他已生成内容；历史回溯只能读取当时的 ConstructionRunConfigSnapshot。
- 所有实际数据源均失败或不可解析时，不得进入去重、评分与筛选阶段。
- 单个数据源失败不得破坏其他成功数据源结果；失败数据源、失败原因和受影响检索词必须可诊断。
- 命中当前 Project 已有关联论文的候选项不得进入下载、解析、AI 分析、入库、图谱更新或推送流程。
- 命中当前 Project 已有 ProjectMaterial 的候选资料不得创建新资料条目；重复来源只能写入既有资料的 `candidate_sources`，且 `candidate_sources` 不参与 KnowledgeVersion、引用、向量化或 Graph 构建。
- 论文去重、评分、筛选和人工修正必须形成 DeduplicationDecision 或 PaperScreeningDecision；评分阈值来源、去重依据、人工调整和误合并撤销必须可追溯到 ConstructionRun、候选论文和操作者。
- Project 资料去重、评分、筛选和人工修正必须形成 MaterialDeduplicationDecision 或 MaterialScreeningDecision；标题归一化、`content_format_group`、人工调整和误合并撤销必须可追溯到 ConstructionRun、候选资料和操作者。
- 用户确认筛选结果后，候选论文和候选资料才能进入下载解析流程。
- 手动补充论文必须形成 ManualPaperSupplementRequest；补充方式至少区分 PDF 上传、DOI、arXiv ID 和 URL，且必须绑定提交用户、目标 Project 和提交时间。
- DOI、arXiv ID 或 URL 补充必须先归一化为 ExternalPaperIdentifier，再解析为 CandidatePaper 或 PaperIdentity；解析失败、解析到多个候选或关键元数据冲突时，不得自动入库，必须等待用户确认或修正。
- PDF-only 上传必须先从 PDF 本身提取候选元数据；关键元数据不足时必须要求用户补充或确认 LLM 元数据草稿，LLM 草稿不得直接成为用户已确认元数据。
- 非论文资料只要求轻量元数据，包括项目资料库编号、标题、`normalized_title`、`content_format`、主来源、`candidate_sources`、重要摘要、处理状态和来源 ConstructionRun；不得要求作者、时间、语言或 provider 必填。
- 非论文资料不维护业务类型字段；文件类型只由 `content_format` 表达。
- ProjectMaterial 的 `normalized_title` 至少执行去首尾空格、大小写归一、连续空白合并和常见文件扩展名移除。
- 同一 Project 内，当非论文资料标题相同或相似，且 `content_format` 相同或属于相似格式组时，必须视为重复或疑似重复，不得静默创建重复 ProjectMaterial。
- 非论文资料标题缺失时不得自动确认入库；用户可补充标题，或由 Agent 生成待确认标题草稿。
- P0 Project 资料支持 `pdf`、`doc/docx`、`ppt/pptx`、`html/htm`、`md/txt/rst`、`yaml/yml/json/toml`、`ipynb` 和 `py` 等代码文件参与后续解析、分析和 KnowledgeVersion 构建。
- P1 数据表资料可入库和使用，但默认不得标记为参与 KnowledgeVersion 构建；P2 多媒体资料可作为文件资产管理，解析和知识构建能力后续扩展。
- 用户上传 PDF、Project 资料文件或远程文件形成的 DocumentAsset 只能服务于其有 `use` 权限的 Project；不得因为同一 PaperIdentity 或相似资料跨 Project 出现而自动暴露上传文件给其他 Project 或用户。
- 手动补充命中当前 Project 已有关联论文时，只能作为补充资产、元数据修正候选或安全空态提示处理；不得创建重复 ProjectPaper。
- 手动补充命中当前 Project 已有 ProjectMaterial 时，只能作为备选来源、元数据修正候选或安全空态提示处理；不得创建重复 ProjectMaterial。
- 从当前 Project 移除论文关联不得删除全局论文身份，也不得影响其他 Project。
- 从当前 Project 移除 ProjectMaterial 不得影响其他 Project 的资料或文件资产。
- PDF 下载、文本解析、用户上传替代和重试结果必须收敛为一个可追溯的 DocumentProcessingState；后续 AI 分析、向量化、RAG 和综述引用只能读取其标记的最终可用文本来源。
- Project 资料文件获取、文本解析、格式支持、不参与 KnowledgeVersion 和重试结果必须收敛为一个可追溯的 MaterialProcessingState；后续 AI 分析、向量化、RAG 和综述引用只能读取其标记的最终可用文本来源。
- 摘要降级文本可进入后续分析、向量化或 RAG，但必须标记为摘要降级来源，不能冒充全文解析。
- 下载解析阶段完成后，手动 ConstructionRun 必须由用户确认 DocumentProcessingState/MaterialProcessingState 摘要、失败项、摘要降级项和不参与知识构建项，才能进入 AI 分析阶段；自动 ConstructionRun 可由 AutoConfirmationPolicy 处理低风险确认，或对单项执行跳过、摘要降级和局部失败。
- 手动 ConstructionRun 中，用户确认后的 PaperAnalysis 才能作为入库、深研和综述上下文使用；自动 ConstructionRun 中，AutoConfirmationPolicy 确认后的 PaperAnalysis 可进入后续流程。
- 手动 ConstructionRun 中，用户确认后的 MaterialAnalysis 才能作为入库、深研和综述上下文使用；自动 ConstructionRun 中，AutoConfirmationPolicy 确认后的 MaterialAnalysis 可进入后续流程。
- 手动 ConstructionRun 入库前必须展示即将写入的有效论文、有效 Project 资料、跳过项、失败项、摘要降级项、不参与知识构建项和风险提示；未确认入库预览时不得写入 Project 知识库、向量库或图谱。自动 ConstructionRun 可由 AutoConfirmationPolicy 确认低风险入库预览，遇到高风险项不得静默入库，也不得等待用户响应；能跳过则跳过，能降级则降级，能局部失败则局部失败，只有无法保证不污染已发布知识库、向量库或图谱时才整体失败。
- ConstructionRun 写入 ProjectPaper、ProjectMaterial、DocumentAsset、向量项、图谱项和 KnowledgeVersion 相关状态失败时，必须保留可诊断失败原因和一致性边界；失败写入不得发布新的 KnowledgeVersion，也不得污染已发布知识版本。具体自动重试次数和后台清理编排由应用层定义。
- 用户选择重连继续构建时，新的 ConstructionRun attempt 必须基于 ConstructionCheckpoint 从已成功写入且状态一致的位置断点续连；不得重复写入已成功子内容或跳过未完成子内容。
- ConstructionCheckpoint 必须记录正式写入进度、未发布中间写入、中间临时文件引用、可续连位置、失败原因、重试次数和清理状态；断点或临时文件不一致时不得重连。
- 手动 ConstructionRun 中，用户选择不继续构建、取消失败 Run，或超过应用层定义的等待窗口仍无操作时，系统应删除所有可续连 ConstructionCheckpoint、失败 Run 的未发布中间写入和不再需要的中间临时文件，将 Project 回归到本次 Run 启动前的已发布知识状态；系统只保留失败记录、错误日志和历史 Run 诊断。自动 ConstructionRun 达到应用层失败清理条件时必须执行同等清理，不等待用户操作。
- ConstructionRun 重连成功并发布新的 KnowledgeVersion 后，必须将临时文件收敛为正式 DocumentAsset、ProjectMaterial、向量、Graph 或日志诊断引用，随后清理不再需要的临时文件；清理结果必须可诊断。
- 图谱创建、增量更新、重建和修复只能由 ConstructionRun 触发；ResearchSession、ReviewRun 和只读知识资产入口不得触发图谱写入。
- 首次成功 ConstructionRun 触发图谱创建；之后的手动 ConstructionRun 默认只触发本次新增或变更论文和 P0 Project 资料所需的图谱增量更新，只有用户在 Construction 面板维护入口明确选择重建时才触发图谱重建；自动 ConstructionRun 作为无人值守维护窗口，在自动检索、入库和向量同步达到可发布条件后，应对当前 Project 图谱执行重建或修复性重建；若本次及上次成功重建后无知识库变更，可跳过重建。

## 5. Project 知识资产面板领域模型

Project 知识资产面板是 Workspace 中提供 Project 原生知识信息的主要只读侧边栏。它不拥有知识资产，也不执行写入；它以当前用户权限、当前 Project、默认 KnowledgeVersion 和当前打开 Run/Session 绑定 KnowledgeVersion 为边界，组织论文库、Project 资料库、文件入口、Graph 图谱和版本信息。

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `ProjectKnowledgeAssetPanel` | Workspace 知识资产只读侧边栏 | 聚合当前 Project 的论文库投影、Project 资料库投影、Graph 投影、文件访问入口、默认 KnowledgeVersion 和当前 Run/Session 绑定 KnowledgeVersion | FR-012, FR-011, FR-018 |
| `ProjectPaperLibraryView` | Project 论文库只读投影 | 只能展示当前 Project 可访问论文的统计、列表、详情、评分、有效性、推送状态、引用状态和已确认 AI 分析 | FR-012 |
| `ProjectPaperFilter` | 论文库筛选条件 | 筛选只作用于当前 Project 可访问论文；支持标题、摘要、作者、来源、评分、有效性、推送状态和引用状态 | FR-012 |
| `PaperAssetDetail` | 论文详情只读上下文 | 汇总 ProjectPaper、PaperIdentity、DocumentAsset、DocumentProcessingState、PaperAnalysis 和关联 Graph 节点引用 | FR-012, FR-024, FR-025 |
| `ProjectMaterialLibraryView` | Project 资料库只读投影 | 只能展示当前 Project 可访问 Project 资料的统计、列表、详情、`content_format`、处理状态、主来源、`candidate_sources`、推送状态、引用状态和已确认重要摘要 | FR-012 |
| `ProjectMaterialFilter` | Project 资料库筛选条件 | 筛选只作用于当前 Project 可访问资料；支持标题、来源、`content_format`、处理状态和是否参与 KnowledgeVersion | FR-012 |
| `MaterialAssetDetail` | Project 资料详情只读上下文 | 汇总 ProjectMaterial、DocumentAsset、MaterialProcessingState、MaterialAnalysis 和关联 Graph 节点引用 | FR-012, FR-024, FR-025 |
| `DocumentAccessRef` | PDF、Project 资料文件或远程文件访问引用 | 只暴露鉴权后可打开的受控访问引用或安全空态；不得暴露真实文件路径或无权限远程地址 | FR-012, FR-024 |
| `ProjectGraphView` | Project Graph 只读投影 | 只能展示当前 Project、指定 KnowledgeVersion 范围内可访问的论文、Project 资料、作者、关键词、概念、方法等节点和关系边 | FR-012, FR-026, FR-031, FR-033 |
| `KnowledgeAssetEmptyState` | 知识资产安全空态 | 记录 Graph、文件、KnowledgeVersion、论文、Project 资料或引用目标缺失、过期、越权、版本不匹配等原因和可用下一步建议 | FR-012, FR-013, FR-031 |

知识资产面板不变量：

- ProjectKnowledgeAssetPanel 只能读取当前用户满足 `access` 权限的 Project 资产；P2 共享未实现前不得展示其他 Owner 的 Project 资产。
- ProjectPaperLibraryView 的统计、列表、详情和筛选结果必须全部限定在当前 Project 的 ProjectPaper 范围内，不得直接展示全局 PaperIdentity 中未关联到当前 Project 的论文。
- ProjectPaperFilter 不改变论文库内容、评分、有效性、推送状态、AI 分析或引用状态；筛选为空时只能返回空结果或安全空态。
- PaperAssetDetail 只能展示用户有权访问的 ProjectPaper、DocumentAsset、已确认 PaperAnalysis 和可映射 GraphEntityRef；缺失任一部分时不得拼接其他 Project 或其他 KnowledgeVersion 的上下文补齐。
- ProjectMaterialLibraryView 的统计、列表、详情和筛选结果必须全部限定在当前 Project 的 ProjectMaterial 范围内，不得展示其他 Project 的资料条目。
- ProjectMaterialFilter 不改变资料库内容、有效性、推送状态、处理状态、重要摘要或引用状态；筛选为空时只能返回空结果或安全空态。
- MaterialAssetDetail 只能展示用户有权访问的 ProjectMaterial、DocumentAsset、已确认 MaterialAnalysis 和可映射 GraphEntityRef；缺失任一部分时不得拼接其他 Project 或其他 KnowledgeVersion 的上下文补齐。
- DocumentAccessRef 必须由授权检查和受控访问机制生成；PDF、Project 资料文件或远程文件缺失、过期、未授权或解析失败时必须进入 KnowledgeAssetEmptyState。
- ProjectGraphView 必须绑定 Project 和 KnowledgeVersion；默认展示 Project 当前默认 KnowledgeVersion，来自 ResearchSession 或 ReviewRun 的引用跳转必须尊重其绑定 KnowledgeVersion。
- 论文详情、Project 资料详情与 Graph 节点之间的互跳只能改变只读查看焦点，不得触发上传、删除、重新下载、重新解析、重新评分、重新分析、入库、推送、图谱增量更新、图谱重建或修复。
- ResearchSession 或 ReviewRun 的引用跳转到知识资产面板时，必须校验引用的 Project、KnowledgeVersion、论文/资料、文段和 GraphEntityRef；越权、缺失、过期或版本不匹配时只能进入 KnowledgeAssetEmptyState。
- KnowledgeAssetEmptyState 可以给出返回 ConstructionWorkspace、刷新依赖、等待构建完成或联系管理员等下一步建议，但建议本身不得绕过对应权限和写入入口。
- ConstructionRun 正在写入新的 KnowledgeVersion 时，知识资产面板可继续展示已发布的默认版本或当前 Run/Session 绑定版本，并提示默认知识库正在更新；不得读取未发布半成品作为可用资产。

## 6. Knowledge 与 Evidence 领域模型

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `KnowledgeVersion` | Project 可读取知识库边界 | 由成功 ConstructionRun 发布；Research/Review 创建时绑定 | FR-018, FR-026, FR-028, FR-032 |
| `KnowledgeVersionDependency` | Run/Session 对 KnowledgeVersion 的依赖 | 记录对象、绑定版本、状态和可刷新状态 | FR-018 |
| `CitationEvidence` | Knowledge / Evidence 内的引用证据 | 必须映射到当前 Project、绑定 KnowledgeVersion 和可访问论文/资料/片段/图谱节点 | FR-031, FR-033 |
| `GraphEntityRef` | Knowledge / Evidence 内的 Graph 节点或边引用 | 只读跳转上下文，不得触发图谱写入 | FR-012, FR-031, FR-033 |
| `TextSourceKind` | 文本来源类型 | 至少区分全文解析、摘要降级、用户上传/补全文本、Project 资料解析文本和不参与 KnowledgeVersion 等来源 | FR-024, FR-028, FR-033 |

Knowledge 不变量：

- KnowledgeVersion 固化 ConstructionRun 会修改并发布的全部可读知识内容，包括 ProjectPaper 关联与状态、ProjectMaterial 关联与状态、DocumentAsset、DocumentProcessingState/MaterialProcessingState 的可用文本来源、PaperAnalysis、MaterialAnalysis、向量索引、Graph 节点与边、引用定位和同步状态。
- P1 数据表和 P2 多媒体可作为 ProjectMaterial 入库，但默认不进入 Graph-RAG KnowledgeVersion；未参与版本的资料不得被标记为可检索证据。
- KnowledgeVersion 只能在关系库入库、向量同步和 Graph 创建/更新/重建完成后发布；Graph 未完成、失败或仍有待续连 ConstructionCheckpoint 时，不得发布新的 KnowledgeVersion。
- ConstructionRun 失败时不得产生新的 KnowledgeVersion；手动失败 Run 的未发布中间写入只能用于断点续连，用户取消或超时未处理后必须清理，并恢复到 Run 启动前的已发布 KnowledgeVersion 边界；自动 ConstructionRun 不得进入等待用户处理状态，达到应用层失败清理条件后必须直接清理未发布中间写入和临时文件。
- Project 默认 KnowledgeVersion 只更新到最新成功发布版本。
- ResearchSession 和 ReviewRun 创建时默认绑定 Project 当前默认 KnowledgeVersion；绑定后不得被系统静默改写。
- 新 KnowledgeVersion 发布后，active ResearchSession / ReviewRun 不被中断，不被强制切换，已完成内容不自动改写。
- 用户可拒绝或稍后刷新旧版本依赖；拒绝或稍后刷新时，对象继续绑定旧 KnowledgeVersion，并持续展示旧版本依赖状态。
- 多个实例依赖旧 KnowledgeVersion 时，系统必须能逐项识别对象、状态、当前绑定版本和可刷新状态。
- 存在旧版本依赖时再次启动 ConstructionRun，必须进行版本基线预检查；用户未刷新可刷新依赖且未明确确认使用 Project 默认最新 KnowledgeVersion 作为构建基线时，不得启动新的 ConstructionRun。
- 旧版本依赖不得被隐式作为新 ConstructionRun 的写入基线。
- 引用跳转必须尊重引用产生时绑定的 Project、KnowledgeVersion 和 Evidence；论文、Project 资料、文段、文件或 Graph 节点缺失、越权、过期或版本不匹配时只能进入安全空态。

## 7. Research Session 领域规则

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `ResearchTurn` | ResearchSession 内的一轮用户提问与 AI 回复容器 | 保存用户输入、当前采纳的 AI 回复、失败/取消状态、引用和重跑关系；失败轮次也必须保留供用户决定是否采纳或重跑 | FR-028, FR-030 |
| `ResearchMessage` | ResearchSession 内的单条对话文本 | 区分用户文本和 AI 回复文本；可被用户编辑或删除单条文本，删除不得级联影响其他轮次或其他文本 | FR-028, FR-030 |
| `ResearchSessionMetadata` | 深研会话列表与检索元数据 | 保存标题、标签、摘要、最后活跃时间和归档状态；搜索筛选结果只能包含当前用户有权限访问的 Session | FR-030 |
| `ResearchResponseAttempt` | ResearchSession 内的一次 AI 回复尝试 | 记录 running/succeeded/failed/cancelled 等结果、诊断原因、部分回复、是否被用户采纳和所属 ResearchTurn；每个 AI 回复可重跑并生成新 attempt | FR-028 |
| `ResearchRetrievalContext` | Graph-RAG 检索上下文 | 绑定 ResearchTurn、KnowledgeVersion、检索 query、命中论文/资料文段、Graph 节点、空检索或失败状态 | FR-028, FR-031 |
| `ResearchOutputPreference` | 输出倾向 | 创新、实验、总结；只影响后续回复，不改写历史 | FR-029 |
| `ResearchSummary` | 对话总结 | 生成失败不得覆盖已有成功总结 | FR-030 |
| `ResearchCitationContext` | 深研引用上下文 | 展示引用论文/资料、文段来源、文件入口、图谱节点和绑定版本 | FR-031 |

Research 不变量：

- 无可用 KnowledgeVersion 时不得创建新的 ResearchSession。
- 每个 ResearchTurn 基于该 Session 绑定的 KnowledgeVersion 执行 Graph-RAG 检索，并保存 ResearchRetrievalContext。
- 流式回复中断、用户取消、检索失败或 LLM 失败时，ResearchTurn、用户输入、失败状态和可诊断原因必须保留；部分 AI 回复只能作为未采纳的 ResearchResponseAttempt 保存，由用户决定编辑、采纳、删除或重跑。
- Graph-RAG 检索为空时，可继续普通回复，但必须明确标记无引用上下文。
- 同一 ResearchSession 一次只能有一个 active ResearchResponseAttempt；同一 AI 回复重跑必须生成新的 ResearchResponseAttempt，不得覆盖原 attempt 的诊断状态。
- ResearchResponseAttempt 的重连必须基于流式回复游标、已保存部分回复、检索上下文、模型配置快照和临时输出状态；断点不可信时不得把部分回复保存为成功回复。
- ResearchResponseAttempt 完成后，未被采纳且不再需要的临时流式片段应进入清理流程；已采纳回复和诊断记录不得被清理流程破坏。
- 用户可编辑或删除单条 ResearchMessage；删除只影响该文本的可见性或采纳状态，不得删除同一 Session 中其他轮次、其他文本、引用证据或诊断日志。
- ResearchSession 存在 active ResearchResponseAttempt 时不得刷新绑定 KnowledgeVersion；版本刷新只能在无运行回复时由用户按 FR-018 确认。
- 引用展示缺失、过期、越权或版本不匹配时，只能降级 ResearchCitationContext 或进入安全空态；不得改写原 ResearchMessage 或 ResearchTurn。
- ResearchSession 归档后不得继续追加用户消息、Agent 回复或总结生成结果。
- ResearchSession 的标题、标签、摘要和最后活跃时间不得与其绑定 KnowledgeVersion、消息历史或归档状态相互矛盾。
- ResearchSession 搜索、筛选和历史列表不得暴露无权限 Session，也不得返回其他 Project 的私有对话。
- 输出倾向切换不得清空对话上下文，不得改变 KnowledgeVersion 绑定，不得改写历史消息、引用或总结。
- ResearchSession 不得修改论文库或 Project 资料库、上传论文/资料、移除论文/资料关联或触发图谱重建。

## 8. Review Run 领域规则

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `ReviewRunBrief` | 综述任务输入简报 | 保存原始主题、扩写后的研究范围、背景、用户要求和绑定 KnowledgeVersion；作为大纲生成输入 | FR-032 |
| `ReviewOutline` | ReviewRun 内的综述架构 | 绑定 ReviewRun 和 KnowledgeVersion；确认前不得自动撰写章节 | FR-032 |
| `ReviewOutlineAssessment` | 大纲支撑与自审结果 | 记录覆盖度、章节顺序、主题边界、每章知识资产支撑度、低支撑原因和建议补充方向；低支撑信息进入 Review 内部审查迭代 | FR-032 |
| `ReviewOutlineVersion` | 大纲版本记录 | 确认记录绑定当前大纲版本和 ReviewRun 的 KnowledgeVersion | FR-032, FR-035, FR-036 |
| `ReviewChapter` | ReviewRun 内的章节内容 | 基于已确认大纲和绑定 KnowledgeVersion 生成；章节内容包含可追溯引用 | FR-033 |
| `ReviewChapterEvidenceContext` | 章节撰写证据上下文 | 绑定章节、KnowledgeVersion、检索 query、引用论文/资料、引用文段和相关 Graph 节点；用于章节生成和引用跳转 | FR-033 |
| `ReviewChapterTrace` | 章节最小追溯 | 记录最后修改人、时间、来源动作、内容状态、审查历史和修订次数 | FR-033, FR-035 |
| `ReviewFinalIssue` | 终稿审查问题 | 记录全文一致性、重复内容、引用完整性和格式问题及处理状态；状态保留用于用户审核 | FR-034 |
| `ReviewFinalDraft` | ReviewRun 内的综述终稿 | 由已确认必需章节汇总；生成完成后默认接受并入库，用户显式拒绝时改为拒绝状态 | FR-034 |
| `ReviewExportableVersion` | 可导出版本 | 由已接受终稿生成；导出内容必须与该版本一致；用户显式拒绝该版本时删除本地文件并保留状态记录 | FR-019, FR-034 |
| `ReviewVersionSnapshot` | P2 历史快照 | 可用于版本列表、只读快照、差异、回退和用户更改摘要 | FR-036 |

Review 不变量：

- 无可用 KnowledgeVersion 时不得创建新的 ReviewRun。
- 新建 ReviewRun 默认绑定 Project 当前默认 KnowledgeVersion。
- ReviewRun 采用单 KnowledgeVersion 设计；同一 ReviewRun 的输入简报、大纲、章节、终稿和可导出版本必须使用同一个绑定 KnowledgeVersion，不支持同 Run 内混合版本生成。
- 用户对 ReviewRun 执行 KnowledgeVersion 刷新时，系统不得在原 Run 内切换版本继续写作；应基于当前 Run 已有的用户输入主题创建重跑路径，并从头生成新的 ReviewRun 或新运行结果。
- ReviewRunBrief 必须绑定 ReviewRun 和 KnowledgeVersion；大纲生成、自审和章节撰写不得使用未绑定或其他 Project 的输入简报。
- 大纲确认前不得自动撰写章节。
- ReviewOutlineAssessment 必须记录低支撑章节、低支撑原因和建议补充方向；低支撑信息作为输入进入 Review 内部审查和多 Agent 迭代，不单独作为写入阻断。
- 用户可确认低支撑章节的大纲，但系统必须记录低支撑风险、内部迭代结果和用户确认。
- ReviewRun 内同一章节不得同时存在多个生成、审查或保存任务写入当前内容。
- 每章撰写前必须形成 ReviewChapterEvidenceContext；章节正文中的引用必须来自该章节绑定 KnowledgeVersion 下可访问的论文、Project 资料、文段或 Graph 节点。
- 章节引用必须能映射到当前 Project 论文库或 Project 资料库，并绑定 ReviewRun 的 KnowledgeVersion。
- 引用不足默认提示风险但不强制阻断章节确认；启用严格引用覆盖要求时，引用不足必须阻断确认，直到用户处理或显式降低要求。
- 审查结果必须与当时的章节版本、章节内容状态或修订次数关联，不得覆盖其他章节。
- 所有必需章节完成并确认后才能汇总最终文章；可选章节缺失不得阻断汇总。
- 终稿生成完成后默认进入 accepted 并入库状态，同时保留 ReviewFinalIssue 供用户审核；用户显式拒绝该版本时，终稿和可导出版本改为 rejected，删除对应本地文件，但保留状态、问题和诊断记录。
- 用户重跑 Review 生成新大纲、章节、终稿或可导出版本时，不得删除既有 accepted 并已入库版本；新版本形成独立状态记录，并且只能使用单一绑定 KnowledgeVersion。
- 可导出版本至少区分未生成、生成中、已接受可导出、已拒绝、生成失败和已过期需重新生成。
- Review 最小追溯以 ReviewRun 为边界，不跨 ReviewRun 合并历史。
- P2 历史版本回退必须二次确认，并生成新的当前版本；不得删除原历史版本。
- 用户更改摘要只能作为辅助说明，不得替代原始内容、修改元数据、人工确认、权限判断或验收依据。

## 9. 内容保护与人工修改

关联 FR：FR-017、FR-035、FR-036。

内容来源优先级：

```text
manual_edit > manual_confirm > agent_draft
```

适用内容：

- 检索词、筛选结果、论文/资料有效性、论文 AI 分析和资料重要摘要。
- ResearchSession 标题、标签、单条对话文本、采纳的 AI 回复和总结文件。
- ReviewRun 输入简报、大纲、章节正文、审查建议处理状态、终稿和可导出版本状态。

内容保护不变量：

- 人工修改内容不得被 Agent 静默覆盖。
- 重新生成涉及人工确认或人工修改内容时必须要求用户确认。
- 用户必须能识别内容是 Agent 草稿、人工确认还是人工修改。
- 最小修改历史至少能追溯最后修改人、时间、来源动作和当前内容状态。
- 失败或取消的重新生成不得破坏原内容。
- 未实现版本列表、版本差异或回退时，不得影响 P0 人工修改保护和重新生成确认。

## 10. 导出、邮件与观点

### 10.1 导出

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `ExportScopeSnapshot` | 导出范围快照 | 固化导出发起时用户有权读取的 Project、Run/Session、文件和内容范围 | FR-019, FR-030, FR-034 |
| `ExportFileResult` | 导出文件结果 | 记录每个导出文件的生成、跳过、失败、过期或清理状态 | FR-019 |
| `ExportFailureReason` | 导出失败分类 | 区分缺失文件、无权限、生成失败、过期和清理等可诊断原因 | FR-019 |

导出不变量：

- 导出内容只能包含用户有权限访问的 Project、Run/Session 和文件。
- 导出 Project 私人资产时，缺失文件、无权限文件或生成失败项应记录为跳过项或失败项，不得导致可导出部分整体失败。
- 导出综述时不得绕过 ReviewRun 的终稿生成、默认接受入库、显式拒绝状态和可导出版本规则。
- 大文件或多文件导出必须作为可诊断任务处理，并记录导出范围快照、文件生成结果、过期或清理状态、失败分类。
- Project 私人资产清理默认不删除已完成导出结果。

### 10.2 邮件推送

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `EmailPushScope` | 邮件推送范围 | 固化本次可推送的 Project、ConstructionRun、新增有效论文/资料和授权接收边界 | FR-004, FR-009, FR-027 |
| `EmailPushPaperItem` | 邮件推送论文项 | 记录论文、来源检索词、来源数据源、有效性、推送资格和发送结果关联 | FR-004, FR-027 |
| `EmailPushMaterialItem` | 邮件推送资料项 | 记录 Project 资料、来源检索词、来源数据源或资料来源、`content_format`、有效性、推送资格和发送结果关联 | FR-004, FR-027 |
| `EmailPushRecipientResult` | 收件人发送结果 | 按收件人记录成功、失败、跳过和失败原因；部分成功不得污染失败项状态 | FR-004 |

邮件推送不变量：

- 自动 ConstructionRun 成功后，邮件推送范围来自本次新增有效论文和 Project 资料范围。
- 手动 ConstructionRun 完成后，用户可预览并手动触发首次发送。
- 邮件只包含当前 Project 中未推送且用户有权限接收的有效论文和有效 Project 资料。
- 邮件内容必须按论文和 Project 资料分组展示。
- 无未推送有效论文或有效 Project 资料时不得发送空邮件，必须记录跳过原因。
- 邮件发送失败不得回滚已完成的论文或 Project 资料入库。
- 推送状态必须与发送结果一致；发送失败论文或 Project 资料不得标记为已推送，部分成功时必须区分成功项和失败项。
- 邮件内容应能追溯论文和 Project 资料来源检索词和来源数据源；Project 资料还应展示 `content_format`。

### 10.3 观点广场

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `Viewpoint` | 观点内容 | 至少包含类型、标题、正文、标签、联系信息、作者和发布状态 | FR-010 |
| `ViewpointVisibility` | 观点可见性 | 限定观点可被哪些已登录且有权访问观点广场的用户看到 | FR-010 |
| `ViewpointModerationState` | 观点治理状态 | 区分正常、作者删除和管理员隐藏；隐藏需记录原因并向作者发送说明邮件；删除或隐藏后普通用户不得继续看到，作者可见隐藏状态和原因；恢复隐藏观点为 P2 | FR-010 |
| `ViewpointReference` | 观点引用目标 | 可关联 Project、Paper、Topic 或 Review；引用不得改变被引用对象状态 | FR-010 |

观点不变量：

- Viewpoint 内容必须至少区分类型、标题、正文、标签和联系信息。
- Viewpoint 独立于 Project Workspace；从 Workspace 跳转到观点广场不得改变当前 Project 的 Run/Session 状态。
- Viewpoint 当前不作为 Project Workspace 内部对象；后续可通过 ViewpointReference 关联 Project、Paper、Topic 或 Review，但不得反向改变被引用对象的状态。
- 观点默认只对系统内已登录且有权访问观点广场的用户可见。
- 用户可删除自己的观点；管理员可隐藏观点；删除或隐藏后普通用户不得继续看到。
- 管理员隐藏观点必须记录隐藏原因，作者本人可继续看到隐藏状态和原因，系统应向作者发送说明邮件。
- 恢复被管理员隐藏的观点属于 P2 治理能力；恢复后可见性按观点原公开范围重新生效。
- 本版本不引入评论、回复、讨论串、实时聊天或复杂协作能力。
- 联系信息只允许用户名或邮箱，不得展示其他私密联系方式。
- 观点搜索和筛选只能返回当前用户有权查看且未被删除或隐藏的观点。

## 11. 权限、安全与只读边界

领域权限不变量：

- 用户只能访问自己有权限的 Project、Run/Session、论文关联、Project 资料、导出和诊断；Project 权限必须先满足 `access` 才能查看，满足 `use` 才能执行互动写操作，满足 `delete` 才能执行软删除或私人资产清理。
- 用户账号有效时，系统必须保证其对自己 Project 的 `access`、`use`、`delete` 全部权限始终存在。
- P2 共享协作授权未实现前，Project 权限不得把他人 Project 暴露给非 Owner 用户，也不得成为 Owner 自用 P0 主流程的前置阻塞。
- 管理员可治理账号和系统配置，但不得查看用户私人密钥明文。
- 管理员不默认拥有用户 Project 的访问、使用或删除权限，不得查看用户 Project 内容或更改用户 Project 权限。
- 管理员只能查看系统级脱敏诊断；用户侧错误即使由用户配置或操作导致，也必须由后端上报为脱敏系统诊断后，管理员才能在 P2 系统诊断后台查看。
- 非管理员不得访问管理员用户治理和系统配置能力。
- PDF、远程文件、Graph、导出文件等资源不得暴露真实文件路径或无权限远程地址。
- Project 知识资产面板、Research 引用跳转、Review 引用跳转均为只读探索入口，不得上传、删除、重新下载、重新解析、重新评分、重新分析、入库、推送或图谱重建。
- 高风险操作必须具备影响范围预览、二次确认或明确覆盖确认，包括 Project 私人资产清理、删除/归档、管理员权限变更、内容覆盖、清空 Project 论文关联、清空 Project 资料关联和历史版本回退。

## 12. 领域事件

领域层应至少发出以下事件，供应用层提交任务、通知、审计、诊断或 UI 刷新：

| 事件 | 触发条件 |
| --- | --- |
| `UserRegistered` | 用户注册成功 |
| `AdminRoleGranted` | 首位管理员授予或管理员权限变更 |
| `AdminRoleRevoked` | 管理员权限撤销成功 |
| `UserDisabled` | 用户账号被禁用 |
| `UserEnabled` | 用户账号被重新启用 |
| `UserDeleted` | 管理员删除普通用户账号及其相关 Project 与关联私人数据 |
| `PasswordResetRequested` | 用户找回密码或管理员触发密码重置 |
| `AccountAuditRecorded` | 账号治理动作写入审计记录 |
| `SystemConfigChanged` | 管理员修改系统默认配置或硬限制 |
| `SystemConfigAuditRecorded` | 系统配置变更写入审计记录 |
| `RuntimeConfigSnapshotCreated` | Run/Session/Job 启动前配置解析成功 |
| `NotificationRecipientChanged` | 用户修改收件邮箱、推送开关或通知偏好 |
| `NotificationTestFailed` | 测试邮件失败且偏好保持不变 |
| `ProjectCreated` | Project 创建 |
| `ProjectStatusChanged` | Project 归档或软删除 |
| `ProjectPrivateAssetsCleanupRequested` | 用户确认 Project 私人资产清理 |
| `ConstructionRunStarted` | ConstructionRun 启动 |
| `ConstructionRunWaitingUser` | 构建流程等待人工确认或修复 |
| `ConstructionRunCompleted` | ConstructionRun 成功完成 |
| `ProjectMaterialAdded` | Project 资料条目成功入库 |
| `ProjectMaterialCandidateSourceRecorded` | 候选资料重复命中并记录到既有资料的 candidate_sources |
| `KnowledgeVersionPublished` | 新 KnowledgeVersion 发布 |
| `KnowledgeVersionRefreshRequested` | 用户打开或确认版本刷新 |
| `ResearchSessionCreated` | ResearchSession 创建并绑定 KnowledgeVersion |
| `ResearchSessionMetadataChanged` | 深研会话标题、标签、摘要、最后活跃时间或归档状态变更 |
| `ResearchTurnRecorded` | 对话轮次保存，包括成功、失败、中断或取消 |
| `ResearchMessageChanged` | 单条对话文本被用户编辑、删除或采纳状态变化 |
| `ResearchResponseAttemptCompleted` | AI 回复尝试成功、失败、中断或取消 |
| `ReviewRunCreated` | ReviewRun 创建并绑定 KnowledgeVersion |
| `ReviewOutlineConfirmed` | 综述大纲确认 |
| `ReviewChapterUpdated` | 章节生成、编辑、审查或确认 |
| `ReviewFinalAccepted` | 终稿默认接受并入库 |
| `ReviewFinalRejected` | 用户显式拒绝终稿或可导出版本 |
| `ContentOverwriteRequested` | 重新生成涉及人工确认或人工修改内容 |
| `ExportJobRequested` | 导出任务创建 |
| `EmailPushRequested` | 邮件推送任务创建 |
| `ViewpointPublished` | 观点发布 |
| `ViewpointDeleted` | 作者删除观点 |
| `ViewpointHidden` | 管理员隐藏观点并记录原因 |
| `ViewpointHiddenNoticeSent` | 观点隐藏说明邮件已发送给作者 |
| `ViewpointRestored` | P2 管理员恢复被隐藏观点 |

事件不携带密钥明文、真实文件路径、外部服务原始敏感错误信息或其他用户数据。

## 13. FR 覆盖检查

| FR 范围 | Domain 覆盖点 |
| --- | --- |
| FR-001~007 | User、UserProfile、AdminRole、PasswordResetRequest、AccountAuditRecord、User/System Config、NotificationRecipient、SystemConfigAuditRecord、RuntimeConfigSnapshot、配置解析与密钥隔离不变量 |
| FR-008~009, FR-011~019 | Project、ProjectWorkspace、ConstructionWorkspace、WorkspaceContext、ProjectKnowledgeAssetPanel、ProjectPaperLibraryView、ProjectMaterialLibraryView、ProjectGraphView、DocumentAccessRef、KnowledgeAssetEmptyState、Run/Session、状态、锁、KnowledgeVersion、内容保护、ExportJob、ExportScopeSnapshot、ExportFileResult、ExportFailureReason、导出不变量 |
| FR-010 | Viewpoint、ViewpointVisibility、ViewpointModerationState、ViewpointReference、观点可见性和治理不变量 |
| FR-020~027 | ConstructionWorkspace、ConstructionRunConfigSnapshot、SearchTermVersion、CandidatePaper、CandidateMaterial、DeduplicationDecision、MaterialDeduplicationDecision、PaperScreeningDecision、MaterialScreeningDecision、ManualPaperSupplementRequest、ManualMaterialSupplementRequest、PaperIdentity、ProjectPaper、ProjectMaterial、ContentFormat、DocumentAsset、PaperAnalysis、MaterialAnalysis、KnowledgeSyncState、ConstructionCheckpoint、EmailPushJob、EmailPushScope、EmailPushPaperItem、EmailPushMaterialItem、EmailPushRecipientResult |
| FR-028~031 | ResearchSession、ResearchTurn、ResearchSessionMetadata、ResearchMessage、ResearchResponseAttempt、ResearchRetrievalContext、ResearchOutputPreference、ResearchSummary、ResearchCitationContext、CitationEvidence |
| FR-032~036 | ReviewRun、ReviewRunBrief、ReviewOutline、ReviewOutlineAssessment、ReviewChapter、ReviewChapterEvidenceContext、ReviewFinalIssue、ReviewFinalDraft、ReviewExportableVersion、ReviewChapterTrace、ReviewVersionSnapshot |

待后续实现校验：

- 首位管理员并发授予和最后管理员保护。
- 管理员账号治理范围、删除用户级联私人数据、不得修改用户 Project 权限和不得查看用户 Project 内容。
- 配置解析快照不保存密钥明文，且系统默认不静默替换用户显式选择。
- Project archived/deleted 状态的只读和不可进入规则。
- 同一 Project active ConstructionRun 唯一性。
- 自动调度重复触发和 Project 调度锁。
- KnowledgeVersion 发布条件、旧版本依赖和再次构建基线预检查。
- Run 暂停态、P1 重试/重连/重跑语义、断点临时文件清理和 Review Run 单版本重跑规则。
- 人工修改覆盖保护和失败生成回滚。
- 摘要降级文本在论文详情、Research 引用和 Review 引用中的来源标记。
- Project 资料的标题与 `content_format_group` 去重、`candidate_sources` 不参与知识构建、P1 数据表默认不进入 KnowledgeVersion。
- Review 同章写入互斥、严格引用覆盖、终稿默认接受/显式拒绝和最小追溯。
- Project 私人资产清理不破坏全局论文身份、导出结果和其他 Project 引用。
- Project 私人资产清理不破坏其他 Project 仍引用的资料文件或资料条目。
- 观点搜索筛选、删除、管理员隐藏、隐藏原因作者可见、说明邮件发送和 P2 恢复不暴露无权限或已隐藏内容。

## 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|---------|--------|
| v1.0 | 2026-05-20 | 初始 Domain Core 骨架，定义核心聚合、Project 状态、Run/Session 通用状态、Knowledge Version、内容保护和领域事件 | Codex |
| v1.1 | 2026-05-20 | 按新版分层文档集调整文件定位，与 `00_layers.md` 和 `01_functional_requirements.md` 对齐 | Codex |
| v1.2 | 2026-05-21 | 依据 `01_functional_requirements.md` 重写结构，补齐配置、Workspace、Construction、Knowledge/Evidence、Research、Review、导出、邮件、观点、安全边界和 FR 覆盖检查 | Codex |
| v1.3 | 2026-05-21 | 补齐账号审计、密码重置、通知收件人、检索词解释字段、Research 会话元数据、观点内容结构和对应领域事件 | Codex |
| v1.4 | 2026-05-22 | 轻量补强步骤状态、自动确认策略、文档处理状态和 Review 追踪命名一致性 | Codex |
| v1.5 | 2026-05-22 | 按 `FR-008` 新 Project 权限定义补充访问、使用、删除三类权限和 Owner 默认全权限不变量 | Codex |
| v1.6 | 2026-05-25 | 逐条审查并明确边界 | haoyanzhen |
| v1.7 | 2026-05-25 | 将 `FR-012` Project 知识资产面板提升为独立领域模型，补充只读资产投影、筛选、Graph 版本边界、文件访问引用和安全空态规则 | Codex |
| v1.8 | 2026-05-26 | 补强 `FR-013` Workspace 上下文恢复和 `FR-023` 手动补充论文的显式领域对象与不变量 | Codex |
| v1.9 | 2026-05-26 | 收束自动 ConstructionRun 检索词领域规则：新检索词默认参与自动更新，自动 Run 仍仅使用 `auto_update_enabled=true` 集合 | Codex |
| v1.10 | 2026-05-27 | 明确 ProjectWorkspace 顶层架构，补充 ConstructionRun 配置快照、去重筛选决策、确认门槛、Graph 发布条件和构建断点续连规则 | Codex |
| v1.11 | 2026-05-27 | 补强 Research 失败轮次保留、单条文本编辑删除和 AI 回复重跑；补充 Review 输入简报、大纲评估、章节证据上下文和默认接受/显式拒绝终稿规则 | Codex |
| v1.12 | 2026-05-29 | 收敛 Domain Core 聚合边界，区分领域实体、值对象、只读投影、配置快照和任务对象；弱化实现细节，强化 Paper-Knowledge-Evidence 主链路 | Codex |
| v1.13 | 2026-06-01 | 同步管理员能力分层：收束账号治理、系统配置 MVP/P1/P2 边界、管理员系统级诊断限制、用户删除级联私人数据和观点隐藏通知/恢复规则 | Codex |
| v1.14 | 2026-06-01 | 补强 Run 暂停态、P1 重试/重连/重跑语义、断点临时文件清理、自动 Construction Run 无等待策略和 Review Run 单版本规则 | Codex |
| v1.15 | 2026-06-06 | 移除 Project 级 paused 状态，明确自动更新启停归 ConstructionWorkspace 配置承载，不改变 Project 生命周期状态；deleted Project 不进入 Workspace。 | Codex |
| v1.16 | 2026-06-06 | 同步非论文 Project 资料入库领域模型：新增 ProjectMaterial、候选资料、资料去重筛选、轻量元数据、content_format、candidate_sources、资料分析、知识版本和邮件推送边界。 | Codex |
