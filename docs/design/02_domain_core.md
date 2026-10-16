# Domain Core 设计

文档版本：v1.24
更新日期：2026-10-16
依据文档：`00_layers.md`、`01_functional_requirements.md`、`01-01-FR-reference.md`  
用途：从 FR 中提炼 Research Paper Base 的核心业务对象、对象关系、状态、生命周期和不变量。本文不定义 UI 布局、API 路径、数据库字段、Provider SDK、队列实现或文件存储实现。

## 1. 设计边界

Domain Core 回答“这个业务世界如何成立”。它必须覆盖所有 P0/P1 FR 背后的稳定业务概念和不可绕过规则，用于开发的标准规则。

冲突裁决：

1. 本文与 `01_functional_requirements.md` 冲突时，以 FR 为准。
2. 本文只定义业务事实和规则；接口由 `04_api_contracts.md` 定义，流程编排由 `05_application_use_cases.md` 定义，Agent/Knowledge 算法由 `06_agent_knowledge_services.md` 定义，持久化由 `07_data_persistence.md` 和 `07_data_schema.sql` 定义。
3. 本文定义状态含义、合法性及不变量；按 FR-017，命令触发的内容状态转换、校验顺序、冲突响应和执行流程由后续 `05` 细化，不得反向改变领域规则。`04` 与 04-01/04-02 本轮形成 P0 接口基线，05 衔接其执行约束，局部未决不得反向改变本领域规则；06–10/SQL 整体仍待细化。速查、SQL 和调研不独立定义业务规则。
4. 本文中的“必须”表示领域不变量，任何 UI、API、后台任务、Agent 或适配器实现都不得绕过。
5. 本文与以下主要模块附录共同构成 Domain Core 规范，具有相同的设计规格和规则效力，共同受 FR 约束；模块详细规则在对应附录维护，正文及其他模块承接接口，不重复定义，不定义数据库、API 或队列实现。

| 模块 | 规范入口 | 规则范围 |
| --- | --- | --- |
| Knowledge / Evidence | [02-02 知识库并行构建与版本更新](02-02_construction_versioning_appendix.md) | 版本对象、发布、并行构建、读取、采用、确认、冲突与历史保留 |
| Construction 资产入库 | [02-03 资产入库](02-03_construction_assets_appendix.md) | 检索、身份、去重筛选、手动补充、文本处理与分析确认 |
| Run / Session 恢复 | [02-04 运行恢复](02-04_run_recovery_appendix.md) | 重试、重连、重跑、构建断点、回复恢复与临时产物清理 |

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
| `ReviewRun` | ReviewRun、ReviewRunBrief、ReviewOutline、ReviewOutlineAssessment、ReviewOutlineVersion、ReviewChapter、ReviewChapterEvidenceContext、ReviewChapterTrace、ReviewFinalIssue、ReviewFinalDraft、ReviewVersionSnapshot | 综述写作输入、大纲、章节、终稿和下载边界；ReviewVersionSnapshot 是 P2 历史快照 |
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
| `archived` | 是 | 只读；导出可作为受控读型产物生成 | 否 | 历史保留状态，不允许新建、启动、继续生成、上传、删除、重跑或采用新版本等写操作 |
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
- API-D04 A：管理命令生效立即撤销影响范围内的执行写资格，异步安全终止且不要求先手动取消。尚未终态的受影响执行安全终止后 cancelled 并记录原因；原 succeeded/failed/cancelled 保持结果。清理失败独立追溯，不恢复授权。Research 只取消 attempt，不终结 Session；Construction 槽先撤销写资格再释放，详见 02-02。
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
| `ReviewRun` | 流程式写作运行 | Knowledge Version 消费者 | 创建时绑定 Knowledge Version；大纲、章节和终稿受内容保护和写锁约束 | FR-032~036 |
| `ExportJob` | 异步产物任务 | 授权读取者 | 导出范围必须绑定用户有权限访问的 Project/Run/Session；不得绕过 Review 终稿生成规则 | FR-019, FR-030, FR-034 |
| `EmailPushJob` | 邮件推送任务 | 授权通知者 | 只推送当前 Project 中未推送且用户有权限接收的有效论文和有效 Project 资料；空邮件不得发送 | FR-004, FR-009, FR-027 |
| `AutoConfirmationPolicy` | 自动 ConstructionRun 的人工等待点处理策略 | 决策确定者 | 只能处理可安全自动确认、跳过、降级或局部失败的无人值守等待点；不得让自动 Run 等待用户响应 | FR-009 |

### 3.2 通用状态

| 状态 | 含义 | 领域约束 |
| --- | --- | --- |
| `draft` | 已创建但未启动 | 可编辑配置，可启动或删除 |
| `queued` | 已提交等待执行 | 可取消，应可诊断排队原因；ConstructionRun 不占构建槽，资源忙保持排队，不可执行按版本附录失败 |
| `running` | 后台任务或流式回复执行中 | 可查看阶段，可按规则取消 |
| `paused` | Run 的所有异步运行任务均已暂停 | 只适用于流程式 Run；paused ConstructionRun 保留 Project 独占构建资格；显式继续沿用同一实例，显式取消终止该实例写资格并清除占槽，显式重跑以新 Run 实例安全接管；Session 不触发暂停态 |
| `waiting_user` | 等待人工确认、补充或修复 | 不得静默跳过高风险确认 |
| `succeeded` | 成功完成 | 结果只读保留；ConstructionRun 区分 published/no_change 结果属性，无变化成功不产生新版本；可导出或复制配置创建新实例 |
| `failed` | 失败并带诊断原因 | 原有成功内容不得被失败任务破坏；ConstructionRun 可按可信恢复条件经 queued 以新 attempt 继续；放弃恢复保持 failed 并记录放弃/清理，不转 cancelled |
| `cancelled` | 用户或系统取消 | 不得写入成功态半成品 |
| `archived` | 会话或运行归档 | 不得继续追加消息、回复、总结或生成结果 |

状态不变量（FR-015）：

- 已成功、已取消、已归档的历史对象不得被原地改回 running，也不能借新 attempt 绕过该限制；允许重试的对象应记录新 attempt，需要重跑时应创建新实例或新运行结果。
- ConstructionRun、执行 attempt、候选与发布版本的职责、全部合法转换及发布/取消竞争由[版本附录第 10 章](02-02_construction_versioning_appendix.md#10-构建与知识版本状态机)定义。候选使用准备中/待发布/已发布/已废弃；waiting_user 暂停后继续恢复等待项；paused 显式重跑旧 Run cancelled 并关联新 Run，定向交接原槽。新状态细节不改变恢复能力原有分期。
- 暂停是 Run 状态，不是 Session 状态；只有当 ConstructionRun 或 ReviewRun 中所有异步运行任务均暂停时，该 Run 才能进入 `paused`。
- ResearchSession 不触发暂停态；其后端流式回复可取消、失败、重试或重连，但 Session 本身不因单次回复控制变为 `paused`。
- 通用重试、重连和重跑承接[运行恢复附录第 3 章](02-04_run_recovery_appendix.md#3-重试重连与重跑)的 P1 受控能力；FR-018 版本采用专用创建的 P0 边界见[版本附录第 2.4 节](02-02_construction_versioning_appendix.md#24-读取与采用接口)。
- 取消、暂停、恢复、重试、重连、重跑、复制、删除、归档等操作必须受权限、状态和内容保护规则约束。
- P1 的复制、重试、重连、重跑、归档、删除不得破坏原实例。
- 同一个 Project 的历史 Construction Run 只能从 ConstructionWorkspace 内部承载，不与 ResearchSession / ReviewRun 平级作为 Workspace 总入口。

### 3.3 重试、重连与重跑

操作语义、断点一致性与清理规则见[运行恢复附录第 3 章](02-04_run_recovery_appendix.md#3-重试重连与重跑)。FR-018 版本采用专用操作及其与通用重跑的边界见[版本附录第 2.4 节](02-02_construction_versioning_appendix.md#24-读取与采用接口)。

### 3.4 锁与互斥

| 互斥点 | 保护对象 | 不变量 |
| --- | --- | --- |
| Project 构建写锁 | Project 知识库 | 同一 Project 只允许一个 ConstructionRun 占用构建槽并取得写资格，paused 仍占槽 |
| 调度锁 | Project + 调度窗口 | 重复调度不得创建重复 automatic ConstructionRun |
| Research 流式锁 | ResearchSession | 同一 Session 一次只允许一个流式回复追加 |
| Review 章节锁 | ReviewRun + Chapter | 同一章节不得同时存在多个生成、审查、保存或重新生成任务写入当前内容 |
| Review 终稿锁 | ReviewRun Final | 终稿汇总、终审、保存和完成不得并发改写同一最终稿 |
| 内容覆盖锁 | 受保护内容 | 覆盖确认期间内容变化时必须要求刷新后重试 |

构建槽、暂停占槽与写资格交接规则见[版本附录第 3.1 节](02-02_construction_versioning_appendix.md#31-构建槽不变量)。

## 4. Construction 领域模型

Construction 的领域主链路、对象、检索与候选处理、手动补充、文本处理和分析确认见[资产入库附录](02-03_construction_assets_appendix.md)。

知识版本、资产纳入与图谱写入承接[版本附录第 2–3 章](02-02_construction_versioning_appendix.md#2-业务对象与关系)；ConstructionCheckpoint、断点续连和清理承接[运行恢复附录第 4 章](02-04_run_recovery_appendix.md#4-construction-断点与清理)。

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

版本投影、详情补齐限制、引用跳转校验和构建期间读取规则见[版本附录第 2.4 节](02-02_construction_versioning_appendix.md#24-读取与采用接口)。

- ProjectKnowledgeAssetPanel 只能读取当前用户满足 `access` 权限的 Project 资产；P2 共享未实现前不得展示其他 Owner 的 Project 资产。
- ProjectPaperLibraryView 的统计、列表、详情和筛选结果必须全部限定在当前 Project 的 ProjectPaper 范围内，不得直接展示全局 PaperIdentity 中未关联到当前 Project 的论文。
- ProjectPaperFilter 不改变论文库内容、评分、有效性、推送状态、AI 分析或引用状态；筛选为空时只能返回空结果或安全空态。
- ProjectMaterialLibraryView 的统计、列表、详情和筛选结果必须全部限定在当前 Project 的 ProjectMaterial 范围内，不得展示其他 Project 的资料条目。
- ProjectMaterialFilter 不改变资料库内容、有效性、推送状态、处理状态、重要摘要或引用状态；筛选为空时只能返回空结果或安全空态。
- DocumentAccessRef 必须由授权检查和受控访问机制生成；PDF、Project 资料文件或远程文件缺失、过期、未授权或解析失败时必须进入 KnowledgeAssetEmptyState。
- 论文详情、Project 资料详情与 Graph 节点之间的互跳只能改变只读查看焦点，不得触发上传、删除、重新下载、重新解析、重新评分、重新分析、入库、推送、图谱增量更新、图谱重建或修复。
- KnowledgeAssetEmptyState 可以给出返回 ConstructionWorkspace、显式采用新版本、等待构建完成或联系管理员等下一步建议，但建议本身不得绕过对应权限和写入入口。

## 6. Knowledge 与 Evidence 领域模型

KnowledgeVersion、KnowledgeVersionDependency、CitationEvidence、GraphEntityRef、TextSourceKind 和 KnowledgeSyncState 的对象定义与不变量见[版本附录第 2 章](02-02_construction_versioning_appendix.md#2-业务对象与关系)。

构建发布、并行冲突、版本采用、历史证据保留和访问例外统一由[版本附录第 3–10 章](02-02_construction_versioning_appendix.md#3-构建默认行为)定义；其他模块按其读写接口承接。

## 7. Research Session 领域规则

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `ResearchTurn` | ResearchSession 内的一轮用户提问与 AI 回复容器 | 保存用户输入、当前采纳的 AI 回复、失败/取消状态、引用和重跑关系；失败轮次也必须保留供用户决定是否采纳或重跑 | FR-028, FR-030 |
| `ResearchMessage` | ResearchSession 内的单条对话文本 | 区分用户文本和 AI 回复文本；P1 可被用户编辑或删除单条文本，删除不得级联影响其他轮次或其他文本 | FR-028, FR-030 |
| `ResearchSessionMetadata` | 深研会话列表与检索元数据 | 保存标题、标签、摘要、最后活跃时间和归档状态；搜索筛选结果只能包含当前用户有权限访问的 Session | FR-030 |
| `ResearchRetrievalContext` | Graph-RAG 检索上下文 | 绑定 ResearchTurn、KnowledgeVersion、检索 query、命中论文/资料文段、Graph 节点、空检索或失败状态 | FR-028, FR-031 |
| `ResearchOutputPreference` | 输出倾向 | 创新、实验、总结；只影响后续回复，不改写历史 | FR-029 |
| `ResearchSummary` | 对话总结 | 生成失败不得覆盖已有成功总结 | FR-030 |
| `ResearchCitationContext` | 深研引用上下文 | 展示引用论文/资料、文段来源、文件入口、图谱节点和绑定版本 | FR-031 |

Research 不变量：

创建条件、版本绑定、Graph-RAG 读取、采用新版本和引用降级承接[版本附录第 2.4 节](02-02_construction_versioning_appendix.md#24-读取与采用接口)。ResearchResponseAttempt 对象及失败保留、互斥、重连与清理见[运行恢复附录第 2、5 章](02-04_run_recovery_appendix.md#5-research-回复恢复)。

- Graph-RAG 检索为空时，可继续普通回复，但必须明确标记无引用上下文。
- P1 用户可编辑或删除单条 ResearchMessage；删除只影响该文本的可见性或采纳状态，不得删除同一 Session 中其他轮次、其他文本、引用证据或诊断日志。
- ResearchSession 归档后不得继续追加用户消息、Agent 回复或总结生成结果。
- ResearchSession 的标题、标签、摘要和最后活跃时间不得与其绑定 KnowledgeVersion、消息历史或归档状态相互矛盾。
- ResearchSession 搜索、筛选和历史列表不得暴露无权限 Session，也不得返回其他 Project 的私有对话。
- 输出倾向切换不得清空对话上下文，不得改变 KnowledgeVersion 绑定，不得改写历史消息、引用或总结。
- ResearchSession 不得修改论文库或 Project 资料库、上传论文/资料、移除论文/资料关联或触发图谱重建。

API-D02 B 已采纳：P0 持久保存并可读取失败输入、未采纳片段及诊断；消息编辑/删除、失败片段编辑/采纳属 P1，不将片段显示视为采纳。

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
| `ReviewVersionSnapshot` | P2 历史快照 | 可用于版本列表、只读快照、差异、回退和用户更改摘要 | FR-036 |

Review 不变量：

创建条件、单 KnowledgeVersion 绑定和新版本采用承接[版本附录第 2.4 节](02-02_construction_versioning_appendix.md#24-读取与采用接口)。

- ReviewRunBrief 必须绑定 ReviewRun；KnowledgeVersion 绑定与输入简报读取边界承接[版本附录第 2.4 节](02-02_construction_versioning_appendix.md#24-读取与采用接口)。
- 大纲确认前不得自动撰写章节。
- ReviewOutlineAssessment 必须记录低支撑章节、低支撑原因和建议补充方向；低支撑信息作为输入进入 Review 内部审查和多 Agent 迭代，不单独作为写入阻断。
- 用户可确认低支撑章节的大纲，但系统必须记录低支撑风险、内部迭代结果和用户确认。
- ReviewRun 内同一章节不得同时存在多个生成、审查或保存任务写入当前内容。
- 每章撰写前必须形成 ReviewChapterEvidenceContext；引用范围承接[版本附录第 2.4 节](02-02_construction_versioning_appendix.md#24-读取与采用接口)。
- 引用遵循学术规范，机械完整性检查及审查问题用于提示，不以段落/数量覆盖率或 Agent 评分阻断确认；具体规则见第 8.1 节。
- 审查结果必须与当时的章节版本、章节内容状态或修订次数关联，不得覆盖其他章节。
- 所有必需章节完成并确认后才能汇总最终文章；可选章节缺失不得阻断汇总。
- 终稿生成完成后默认进入 accepted 并入库状态，同时保留 ReviewFinalIssue 供用户审核；用户显式拒绝该终稿时改为 rejected 并停止下载，清理对应托管生成文件，保留状态、问题和诊断；已经下载的用户副本不能远程撤回。
- 用户重跑 Review 生成新大纲、章节或终稿时，不得删除既有 accepted 并已入库版本；新版本形成独立状态记录，知识绑定承接[版本附录第 2.4 节](02-02_construction_versioning_appendix.md#24-读取与采用接口)。
- 当前 accepted 终稿保存后即可读取和下载；不维护独立可导出快照生命周期。
- Review 最小追溯以 ReviewRun 为边界，不跨 ReviewRun 合并历史。
- P2 历史版本回退必须二次确认，并生成新的当前版本；不得删除原历史版本。
- 用户更改摘要只能作为辅助说明，不得替代原始内容、修改元数据、人工确认、权限判断或验收依据。

### 8.1 已采纳的 Review 边界

2026-10-16 人工采纳 R1-A/R2-A，替代旧 D03 严格覆盖及 D06 独立导出快照规则。

- 借用观点、数据、方法、文字及图表须清楚标明来源；连续陈述来源清楚且未变时不要求逐句/逐段重复。引用须支持所述内容，优先核对原始来源，准确呈现元数据、已知撤稿/更正/预印本状态；直接引文准确标示及定位，摘要证据不冒充全文，原创推论与来源事实区分。格式遵循目标刊物；P0 采用一致编号与完整参考信息，不新增样式配置平台。
- 机械检查仅核对文内标记、参考条目和证据身份/版本/定位；章节审查与终审指出可能缺来源、误引和支持不足的位置及建议。不提供 strict 开关、覆盖率、阈值或豁免。不将未发现链接问题宣称为学术规范全面通过。
- 保存人工正文不因建议或坏标记失败；保留问题但不把坏标记注册为有效证据。越权、跨 Project/绑定版本或伪造证据关联硬性拒绝，系统不读取不可访问证据注入正文；人工文字不要求反查出处权限。审查绑定内容修订，旧审查不冒充当前结论。
- 终稿默认 accepted 不结束 Run；无活动子任务时以 waiting_user 等待操作。仅可继续的 Run 内 accepted 稿可编辑，保存不复活 rejected。单一 Markdown 全文为唯一可写正文，摘要/关键词/参考文献投影由同一修订派生；保存保留修订、修改人/时间/来源和最小追溯，不要求保存每次编辑完整历史。
- 保存后直接下载当前稿；下载固定一次一致读取及指定修订，不调用模型，不增加独立导出快照。重新生成独立完成后检查原修订与人工覆盖授权，失败/迟到结果不覆盖已保存稿，不删除其他独立 accepted 成果。P1 格式转换固定任务输入仍属内部执行一致性。
- 用户显式完成时原子核验 Run、稿件及来源修订：无活动任务、当前稿 accepted、大纲与必需章节来源未因后续改变失效；允许保留终审建议，终稿编辑不反向失效章节确认。成功后 succeeded 只读，下载到本地再编辑；P0 不提供 reopen、复制 Run 或本地回传。完成不是接受或下载的前置。

## 9. 内容保护与人工修改

关联 FR：FR-017、FR-035、FR-036。

内容来源优先级：

```text
manual_edit > manual_confirm > agent_draft
```

适用内容：

- 检索词、入库确认受理前的候选筛选结果、论文/资料有效性、论文 AI 分析和资料重要摘要；确认后锁定及已发布只读不因人工保护优先级而放宽。
- ResearchSession 标题、标签、单条对话文本、采纳的 AI 回复和总结文件。
- ReviewRun 输入简报、大纲、章节正文、审查建议处理状态、终稿内容和接受状态。

内容保护不变量：

- 人工修改内容不得被 Agent 静默覆盖。
- 重新生成涉及人工确认或人工修改内容时必须要求用户确认；确认绑定所审阅的具体内容与修订，实质变化后失效。不同任务的旧结果不得覆盖较新人工修改；原确认不得给新生成内容或新证据背书。
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
- 导出综述时不得绕过 ReviewRun 的终稿生成、默认接受、显式拒绝状态和当前稿一致读取规则；P0 支持单稿 Markdown 下载，通用导出及格式转换为 P1。
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
| `ProjectMaterialCandidateSourceRecorded` | 候选资料重复命中并记录独立备选来源线索，不改已发布资料内容 |
| `KnowledgeVersionPublished` | 新 KnowledgeVersion 发布 |
| `KnowledgeVersionAdoptionRequested` | 用户确认目标版本并请求创建关联研究会话或新版综述，不改写原对象绑定 |
| `ResearchSessionCreated` | ResearchSession 创建并绑定 KnowledgeVersion |
| `ResearchSessionMetadataChanged` | 深研会话标题、标签、摘要、最后活跃时间或归档状态变更 |
| `ResearchTurnRecorded` | 对话轮次保存，包括成功、失败、中断或取消 |
| `ResearchMessageChanged` | 单条对话文本被用户编辑、删除或采纳状态变化 |
| `ResearchResponseAttemptCompleted` | AI 回复尝试成功、失败、中断或取消 |
| `ReviewRunCreated` | ReviewRun 创建并绑定 KnowledgeVersion |
| `ReviewOutlineConfirmed` | 综述大纲确认 |
| `ReviewChapterUpdated` | 章节生成、编辑、审查或确认 |
| `ReviewFinalAccepted` | 终稿默认接受并入库 |
| `ReviewFinalRejected` | 用户显式拒绝终稿 |
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
| FR-032~036 | ReviewRun、ReviewRunBrief、ReviewOutline、ReviewOutlineAssessment、ReviewChapter、ReviewChapterEvidenceContext、ReviewFinalIssue、ReviewFinalDraft、ReviewChapterTrace、ReviewVersionSnapshot |

待后续实现校验：

- 首位管理员并发授予和最后管理员保护。
- 管理员账号治理范围、删除用户级联私人数据、不得修改用户 Project 权限和不得查看用户 Project 内容。
- 配置解析快照不保存密钥明文，且系统默认不静默替换用户显式选择。
- Project archived/deleted 状态的只读和不可进入规则。
- 同一 Project 构建槽唯一性（含 paused Run）与旧运行写资格终止。
- 自动调度重复触发和 Project 调度锁。
- KnowledgeVersion 完整可见发布、旧研究不阻止新构建、最新基线默认与 D01 自动更新授权、版本采用新对象和领域附录验收场景。
- Run 暂停占槽和安全交接、P1 通用重试/重连/重跑语义、P0 Research/Review 版本采用专用创建、断点临时文件清理和 Review Run 单版本重跑规则。
- 人工修改覆盖保护和失败生成回滚。
- 摘要降级文本在论文详情、Research 引用和 Review 引用中的来源标记。
- Project 资料的标题与 `content_format_group` 去重、`candidate_sources` 不参与知识构建、P1 数据表默认不进入 KnowledgeVersion。
- Review 同章写入互斥、学术引用与建议式审查、终稿默认接受/显式拒绝、当前稿下载和最小追溯。
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
| v1.17 | 2026-10-16 | 明确领域/执行权威边界、paused 构建槽与安全交接、P0 版本刷新专用重跑及 D01 待讨论；保留第 8 章默认接受规则 | Codex |
| v1.18 | 2026-10-16 | 新增知识库并行构建与版本更新领域附录；取消旧研究阻塞构建，解决 D01 自动授权，统一 Research/Review 新版本采用、冻结输入、人工保护、完整发布与保留边界 | Codex |
| v1.19 | 2026-10-16 | 将知识版本规则集中到 02-02，将资产入库和运行恢复拆入 02-03、02-04；正文保留模块接口和规范索引 | Codex |
| v1.20 | 2026-10-16 | 明确 paused ConstructionRun 保留独占构建资格，并区分显式取消、同实例继续与新实例重跑 | Codex |

### 本轮文档修订

- v1.21（2026-10-16）：仅更新 P0 API/应用设计职责承接状态，不修改领域对象、状态或不变量；未决分支见 [API 工作单](../workorders/api_p0_design_review_2026-10-16.md)。

- v1.22（2026-10-16）：承接人工采纳的构建状态机与 published/no_change 成功结果；明确排队不占槽、失败恢复与放弃语义、暂停等待及重跑关系；恢复算法继续由 02-04 承载。

本次修订 v1.23（2026-10-16）：承接 D02–D06 的分期、严格引用、治理终止、Review 完成及快照分离；细则不预先生效。

本次修订 v1.24（2026-10-16）：落实人工采纳 R1–R4 及补充决定：学术引用与简化终稿、关联移除发布、空版本消费、确认后锁定及论文/资料重新导入边界；仅设计同步。
