# Domain Core 设计

文档版本：v1.5  
更新日期：2026-05-22  
依据文档：`00_layers.md`、`01_functional_requirements.md`、`01-01-FR-reference.md`  
用途：从 FR 中提炼 Research Paper Base 的核心业务对象、对象关系、状态、生命周期和不变量。本文不定义 UI 布局、API 路径、数据库字段、Provider SDK、队列实现或文件存储实现。

## 1. 设计边界

Domain Core 回答“这个业务世界如何成立”。它必须覆盖所有 P0/P1 FR 背后的稳定业务概念和不可绕过规则，但不逐字复写 FR 的用户交互和验收细节。

冲突裁决：

1. 本文与 `01_functional_requirements.md` 冲突时，以 FR 为准。
2. 本文只定义业务事实和规则；接口由 `04_api_contracts.md` 定义，流程编排由 `05_application_use_cases.md` 定义，Agent/Knowledge 算法由 `06_agent_knowledge_services.md` 定义，持久化由 `07_data_persistence.md` 和 `07_data_schema.sql` 定义。
3. 本文中的“必须”表示领域不变量，任何 UI、API、后台任务、Agent 或适配器实现都不得绕过。

## 2. 核心领域模型

### 2.1 账号、权限与配置

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `User` | 登录、权限和资源归属主体 | 用户有启用/禁用/删除等账号状态；禁用账号不得访问受保护资源 | FR-001 |
| `AdminRole` | 管理员能力标识 | 首位注册用户自动成为管理员；系统必须至少保留一个启用管理员 | FR-005 |
| `UserProfile` | 用户基础信息 | 用户可维护自己的基础信息；用户信息长期留存；管理员只能在账号治理边界内修改其他用户基础信息 | FR-001, FR-005 |
| `PasswordResetRequest` | 密码重置验证请求 | 密码找回或管理员触发重置必须经过安全验证流程；未实现时不得形成可用入口 | FR-001, FR-005 |
| `AccountAuditRecord` | 账号治理审计事实 | 管理员禁用、删除、重置密码、授权或撤销管理员权限时必须记录操作者、目标用户、动作、时间和结果 | FR-005 |
| `UserLlmConfig` | 用户私有 LLM 配置 | 用户配置只归本人使用；密钥不得明文暴露；配置变更不得修改系统默认配置 | FR-002 |
| `UserDataSourceConfig` | 用户私有论文数据源配置 | 数据源可启用/禁用；匿名访问、必填密钥、限流和失效状态必须可区分 | FR-003 |
| `UserNotificationConfig` | 用户收件人与通知偏好 | 用户收件人和推送偏好不改变调度周期，也不得绕过邮件推送范围规则 | FR-004 |
| `NotificationRecipient` | 用户收件邮箱配置 | 每个收件邮箱独立保存论文推送开关、通知偏好和验证/测试结果；测试失败不得改变已保存偏好 | FR-004 |
| `SystemConfig` | 管理员维护的平台默认能力和硬限制 | 包含系统默认 LLM、数据源、SMTP、模型白名单、数据源范围、速率上限、并发上限和调度开关 | FR-006 |
| `SystemConfigAuditRecord` | 系统配置审计事实 | 系统配置变更必须记录操作者、时间、配置类型和结果；不得泄露系统级密钥明文 | FR-006 |
| `RuntimeConfigSnapshot` | 任务启动时解析后的脱敏配置事实 | Agent/Job 启动前必须生成；不得保存或返回密钥明文；系统默认不得静默替换用户显式选择 | FR-007 |

配置不变量：

- 密码不得明文存储、明文返回或在保存后恢复为明文。
- 首位注册用户的管理员授予必须具备并发保护；任何管理员权限变更、禁用或删除操作都不得破坏最后一个启用管理员账号。
- 禁用账号的既有会话在下一次鉴权或刷新时必须失效；被禁用用户只能访问无需账号身份的公开入口。
- 管理员不得查看用户私人 LLM、数据源、通知配置中的密钥或私密配置明文；账号治理只允许访问必要基础账号信息。
- 用户个人 LLM 或数据源配置存在且有效时，系统默认配置不得静默覆盖它。
- 用户未显式选择当前模型时，Agent 任务不得静默回落到系统默认模型；必须要求用户选择或修复配置。
- 用户已有显式选择的模型或数据源在系统默认变化后不得被静默替换；只有启动校验失败时才提示处理。
- 论文数据源解析遵循用户个人配置优先；仅用户缺失搜索论文数据库 API 配置时才回落系统默认配置。
- 系统硬限制优先于用户配置。模型白名单、允许数据源范围、速率上限、并发上限不满足时，任务不得静默继续。
- 邮件运行时配置由用户收件人/偏好与系统 SMTP 发件能力组合而成。
- 多收件人配置下，每个收件人是否接收论文推送、接收内容维度和失败/成功通知偏好必须独立生效。
- 系统 SMTP 缺失或不可用时，测试邮件和邮件推送必须失败为可诊断状态，不得修改用户已保存通知偏好。
- 配置解析失败必须阻止对应任务启动，并保留缺失配置、密钥不可用、超出白名单、数据源禁用、速率/并发超过上限等诊断分类。

### 2.2 Project 与 Workspace

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `Project` | 长期研究容器 | Project 是 Construction、Research、Review 的共同上下文；用户默认拥有自己 Project 的全部权限 | FR-008 |
| `ProjectPermission` | Project 授权事实 | 权限分为访问、使用和删除；Owner 在账号有效时必须始终拥有自己 Project 的全部权限；跨用户访问/使用授权为 P2 预留能力 | FR-008 |
| `ConstructionWorkspace` | Project 唯一构建配置容器 | 每个 Project 有且仅有一个；不等同于一次构建运行 | FR-011, FR-020 |
| `WorkspaceContext` | 用户打开 Project Workspace 时的恢复上下文 | 按用户、Project、对象类型和对象 ID 保存；失效时必须降级到安全空态 | FR-013 |
| `WorkspaceObjectRef` | Workspace 当前打开对象引用 | 只能指向当前 Project 的 ConstructionWorkspace、ResearchSession 或 ReviewRun | FR-011, FR-014 |
| `ProcessStep` | 流程式 Agent 的业务步骤状态与结果摘要 | 只记录业务阶段、等待项、错误分类和结果摘要；步骤动作必须能追溯到对应 Agent FR，不得提供无法追溯的写操作或承载 UI 展示细节 | FR-016 |

Project 状态：

| 状态 | 可进入 Workspace | 可写交互 | 自动调度 | 领域含义 |
| --- | --- | --- | --- | --- |
| `active` | 是 | 是 | 是 | 正常研究状态 |
| `paused` | 是 | 是 | 否 | 用户暂停自动追踪，保留手动交互 |
| `archived` | 是 | 只读；导出可作为受控读型产物生成 | 否 | 历史保留状态，不允许新建、启动、继续生成、上传、删除、重跑或刷新依赖等写操作 |
| `deleted` | 否 | 否 | 否 | 软删除状态，默认不在普通 Project 列表展示 |

Project 不变量：

- Project 权限只分为 `access`、`use`、`delete` 三类：`access` 允许进入 Workspace 和查看 Project 资产；`use` 允许创建、启动、继续或操作 Run/Session、上传补充资料和触发生成等互动能力；`delete` 允许软删除 Project、清理 Project 私人资产或执行等效高风险删除操作。
- Project Owner 默认拥有自己 Project 的 `access`、`use`、`delete` 全部权限；只要 Owner 账号处于有效状态，这些默认权限不得被撤销、降级或被共享授权配置覆盖。
- 将 Project 的 `access` 或 `use` 权限授权给其他用户属于 P2 共享协作能力；未实现时不得阻塞 Owner 对自己 Project 的 P0 创建、进入、使用和管理主流程。
- P0 阶段未实现共享协作授权时，非 Owner 用户不得访问或使用他人 Project。
- Project 状态切换、归档、软删除和私人资产清理必须经过权限校验。
- `deleted` 是软删除，不得物理破坏其他 Project、全局论文记录或其他用户数据。
- Project 私人资产清理只可清理该 Project 独占的运行记录、Run/Session、Project-Paper 关联、PDF、解析文本、向量索引、图谱文件和临时产物。
- Project 私人资产清理不得删除全局论文身份、其他 Project 仍引用的共享论文、其他用户数据或默认保留的已完成导出文件。
- Workspace 上下文恢复不得自动触发重跑、重新生成、重新检索、导出或覆盖。
- 已删除、无权限、归档只读或状态不允许继续的上下文不得恢复为可写状态。

## 3. Run / Session 生命周期

### 3.1 实例类型

| 对象 | 类型 | 读写角色 | 核心规则 | 关联 FR |
| --- | --- | --- | --- | --- |
| `ConstructionRun` | 流程式运行 | Project 知识库写入者 | 一次手动或自动构建执行；同一 Project 同时只能有一个 active 写入者 | FR-009, FR-014, FR-020~027 |
| `ResearchSession` | 开放式会话 | Knowledge Version 消费者 | 创建时绑定 Knowledge Version；同一 Session 一次只能有一个流式回复追加 | FR-028~031 |
| `ReviewRun` | 流程式写作运行 | Knowledge Version 消费者 | 创建时绑定 Knowledge Version；大纲、章节、终稿和可导出版本受内容保护和写锁约束 | FR-032~036 |
| `ExportJob` | 异步产物任务 | 授权读取者 | 导出范围必须绑定用户有权限访问的 Project/Run/Session；不得绕过 Review 终稿生成规则 | FR-019, FR-030, FR-034 |
| `EmailPushJob` | 邮件推送任务 | 授权通知者 | 只推送当前 Project 中未推送且用户有权限接收的有效论文；空邮件不得发送 | FR-004, FR-009, FR-027 |
| `Viewpoint` | 观点广场内容 | 独立于 Project Workspace；包含类型、标题、正文、标签和允许范围内的联系信息；禁止评论；作者可删除，管理员可隐藏 | FR-010 |
| `AutoConfirmationPolicy` | 自动 ConstructionRun 的人工等待点处理策略 | 只能处理可安全自动确认的低风险等待点；遇到必须人工判断的风险项时必须转入 waiting_user 或 failed | FR-009 |

### 3.2 通用状态

| 状态 | 含义 | 领域约束 |
| --- | --- | --- |
| `draft` | 已创建但未启动 | 可编辑配置，可启动或删除 |
| `queued` | 已提交等待执行 | 可取消，应可诊断排队原因 |
| `running` | 后台任务或流式回复执行中 | 可查看阶段，可按规则取消 |
| `waiting_user` | 等待人工确认、补充或修复 | 不得静默跳过高风险确认 |
| `succeeded` | 成功完成 | 结果只读保留，可导出或复制配置创建新实例 |
| `failed` | 失败并带诊断原因 | 原有成功内容不得被失败任务破坏 |
| `cancelled` | 用户或系统取消 | 不得写入成功态半成品 |
| `archived` | 会话或运行归档 | 不得继续追加消息、回复、总结或生成结果 |

状态不变量（FR-015）：

- 已成功、已取消、已归档的历史对象不得被原地改回 running；需要重试时应记录新 attempt 或创建新实例。
- 取消、暂停、恢复、重试、复制、删除、归档等操作必须受权限、状态和内容保护规则约束。
- P1 的复制、重跑、归档、删除不得破坏原实例。
- 同一个 Project 的历史 Construction Run 只能从 ConstructionWorkspace 内部承载，不与 ResearchSession / ReviewRun 平级作为 Workspace 总入口。

### 3.3 锁与互斥

| 互斥点 | 保护对象 | 不变量 |
| --- | --- | --- |
| Project 构建写锁 | Project 知识库 | 同一 Project 同时只允许一个 active ConstructionRun 写入知识库 |
| 调度锁 | Project + 调度窗口 | 重复调度不得创建重复 automatic ConstructionRun |
| Research 流式锁 | ResearchSession | 同一 Session 一次只允许一个流式回复追加 |
| Review 章节锁 | ReviewRun + Chapter | 同一章节不得同时存在多个生成、审查、保存或重新生成任务写入当前内容 |
| Review 终稿锁 | ReviewRun Final | 终稿汇总、终审和可导出版本生成不得并发改写同一最终稿 |
| 内容覆盖锁 | 受保护内容 | 覆盖确认期间内容变化时必须要求刷新后重试 |

## 4. Construction 领域模型

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `SearchTermSet` | Project 检索词集合 | 属于 ConstructionWorkspace；用于手动 selected 构建和自动更新 | FR-020 |
| `SearchTermVersion` | 检索词内容快照 | 保存自然语言关键词、布尔表达式、同义词/缩写、排除词、生成理由、预期覆盖方向、确认时间、修改来源、自动更新开关和数据源策略 | FR-020 |
| `SelectedSearchTerms` | 手动 Run 本次选择的检索词集合 | 不改变检索词自身的自动更新开关 | FR-014, FR-021 |
| `AutoUpdateSearchTerms` | 自动 Run 使用的检索词集合 | 只包含 `auto_update_enabled=true` 的检索词 | FR-009, FR-021 |
| `DataSourcePolicy` | 检索词级数据源策略 | 未显式选择时默认使用用户和系统当前可解析的全部数据源 | FR-020, FR-021 |
| `CandidatePaper` | 检索得到的候选论文 | 必须记录来源检索词、来源数据源和基础元数据 | FR-021, FR-022 |
| `PaperIdentity` | 全局论文身份 | 使用 DOI、arXiv ID、外部 ID、标准化标题等归一化；跨 Project 共享 | FR-022, FR-023 |
| `ProjectPaper` | Project 私有论文关联 | 同一 Project 不得重复关联同一论文；保存有效性、评分、推送状态和分析结果 | FR-012, FR-022, FR-026 |
| `DocumentAsset` | PDF、远程文件或解析文本资产 | 记录访问引用、解析状态、失败原因和摘要降级标记 | FR-012, FR-024 |
| `DocumentProcessingState` | 论文全文获取和可用文本来源状态 | 记录下载、解析、用户上传替代、重试后的最终可用文本来源；全文解析与摘要降级必须可区分 | FR-024 |
| `PaperAnalysis` | 论文结构化 AI 分析 | 至少包含一句话总结、亮点、相关性要点、方法与创新；可被人工编辑和确认 | FR-025 |
| `KnowledgeSyncState` | 关系库、向量库、图谱同步状态 | 未同步或失败数据不得标记为可检索或图谱可用 | FR-026 |

Construction 不变量：

- 手动 ConstructionRun 使用用户本次 selected 检索词集合；自动 ConstructionRun 使用自动更新检索词集合。
- 历史 ConstructionRun 必须能基于启动时配置快照复现当时的检索词内容和数据源策略，即使当前检索词已被修改或删除。
- 检索词未确认时，手动构建不得进入多源检索阶段。
- 检索词生成失败时，用户手动输入并确认的检索词应形成同等可追溯的 SearchTermVersion。
- 不存在独立的检索词 `enabled` 领域状态；手动构建是否使用某个检索词只由本次 SelectedSearchTerms 决定，自动构建是否使用只由 `auto_update_enabled` 决定。
- 自动 ConstructionRun 不得借自动确认策略越过人工确认门槛；自动确认策略无法安全处理的等待项必须进入 `waiting_user` 或 `failed`。
- 所有实际数据源均失败或不可解析时，不得进入去重、评分与筛选阶段。
- 单个数据源失败不得破坏其他成功数据源结果；失败数据源、失败原因和受影响检索词必须可诊断。
- 命中当前 Project 已有关联论文的候选项不得进入下载、解析、AI 分析、入库、图谱更新或推送流程。
- 用户确认筛选结果后，候选论文才能进入下载解析和后续入库流程。
- PDF-only 上传必须先从 PDF 本身提取候选元数据；关键元数据不足时必须要求用户补充或确认 LLM 元数据草稿，LLM 草稿不得直接成为用户已确认元数据。
- 从当前 Project 移除论文关联不得删除全局论文身份，也不得影响其他 Project。
- PDF 下载、文本解析、用户上传替代和重试结果必须收敛为一个可追溯的 DocumentProcessingState；后续 AI 分析、向量化、RAG 和综述引用只能读取其标记的最终可用文本来源。
- 摘要降级文本可进入后续分析、向量化或 RAG，但必须标记为摘要降级来源，不能冒充全文解析。
- 用户确认后的 PaperAnalysis 才能作为入库、深研和综述上下文使用。
- 图谱创建、增量更新、重建和修复只能由 ConstructionRun 触发；ResearchSession、ReviewRun 和只读知识资产入口不得触发图谱写入。

## 5. Knowledge 与 Evidence 领域模型

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `KnowledgeVersion` | Project 可读取知识库边界 | 由成功 ConstructionRun 发布；Research/Review 创建时绑定 | FR-018, FR-026, FR-028, FR-032 |
| `KnowledgeVersionDependency` | Run/Session 对 KnowledgeVersion 的依赖 | 记录对象、绑定版本、状态和可刷新状态 | FR-018 |
| `CitationEvidence` | 引用证据 | 必须映射到当前 Project、绑定 KnowledgeVersion 和可访问论文/片段/图谱节点 | FR-031, FR-033 |
| `GraphEntityRef` | Graph 节点或边引用 | 只读跳转上下文，不得触发图谱写入 | FR-012, FR-031, FR-033 |
| `TextSourceKind` | 文本来源类型 | 至少区分全文解析、摘要降级、用户上传/补全文本等来源 | FR-024, FR-028, FR-033 |

Knowledge 不变量：

- KnowledgeVersion 只能在关系库入库、向量同步和必要图谱更新达到可发布条件后发布。
- Project 默认 KnowledgeVersion 只更新到最新成功发布版本。
- ResearchSession 和 ReviewRun 创建时默认绑定 Project 当前默认 KnowledgeVersion；绑定后不得被系统静默改写。
- 新 KnowledgeVersion 发布后，active ResearchSession / ReviewRun 不被中断，不被强制切换，已完成内容不自动改写。
- 用户可拒绝或稍后刷新旧版本依赖；拒绝或稍后刷新时，对象继续绑定旧 KnowledgeVersion，并持续展示旧版本依赖状态。
- 多个实例依赖旧 KnowledgeVersion 时，系统必须能逐项识别对象、状态、当前绑定版本和可刷新状态。
- 存在旧版本依赖时再次启动 ConstructionRun，必须进行版本基线预检查；用户未刷新可刷新依赖且未明确确认使用 Project 默认最新 KnowledgeVersion 作为构建基线时，不得启动新的 ConstructionRun。
- 旧版本依赖不得被隐式作为新 ConstructionRun 的写入基线。
- 引用跳转必须尊重引用产生时绑定的 KnowledgeVersion；缺失、越权、过期或版本不匹配时只能进入安全空态。

## 6. Research Session 领域规则

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `ResearchMessage` | 对话轮次消息 | 成功轮次保存用户输入、Agent 回复和引用；失败或取消不得写入成功态半成品 | FR-028 |
| `ResearchSessionMetadata` | 深研会话列表与检索元数据 | 保存标题、标签、摘要、最后活跃时间和归档状态；搜索筛选结果只能包含当前用户有权限访问的 Session | FR-030 |
| `ResearchStreamAttempt` | 一次流式回复尝试 | 记录 running/succeeded/failed/cancelled 等结果和诊断原因 | FR-028 |
| `ResearchOutputPreference` | 输出倾向 | 创新、实验、总结；只影响后续回复，不改写历史 | FR-029 |
| `ResearchSummary` | 对话总结 | 生成失败不得覆盖已有成功总结 | FR-030 |
| `ResearchCitationContext` | 深研引用上下文 | 展示引用论文、文段来源、图谱节点和绑定版本 | FR-031 |

Research 不变量：

- 无可用 KnowledgeVersion 时不得创建新的 ResearchSession。
- 每轮对话基于该 Session 绑定的 KnowledgeVersion 执行 Graph-RAG 检索。
- 流式回复中断、用户取消、检索失败或 LLM 失败时，用户输入和失败状态可追溯，但 Agent 半成品不得作为成功回复写入。
- Graph-RAG 检索为空时，可继续普通回复，但必须明确标记无引用上下文。
- ResearchSession 归档后不得继续追加用户消息、Agent 回复或总结生成结果。
- ResearchSession 的标题、标签、摘要和最后活跃时间不得与其绑定 KnowledgeVersion、消息历史或归档状态相互矛盾。
- ResearchSession 搜索、筛选和历史列表不得暴露无权限 Session，也不得返回其他 Project 的私有对话。
- 输出倾向切换不得清空对话上下文，不得改变 KnowledgeVersion 绑定，不得改写历史消息、引用或总结。
- ResearchSession 不得修改论文库、上传论文、移除论文关联或触发图谱重建。

## 7. Review Run 领域规则

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `ReviewOutline` | 综述架构 | 绑定 ReviewRun 和 KnowledgeVersion；确认前不得自动撰写章节 | FR-032 |
| `ReviewOutlineVersion` | 大纲版本记录 | 确认记录绑定当前大纲版本和 ReviewRun 的 KnowledgeVersion | FR-032, FR-035, FR-036 |
| `ReviewChapter` | 章节内容 | 基于已确认大纲和绑定 KnowledgeVersion 生成；章节内容包含可追溯引用 | FR-033 |
| `ReviewChapterTrace` | 章节最小追溯 | 记录最后修改人、时间、来源动作、内容状态、审查历史和修订次数 | FR-033, FR-035 |
| `ReviewFinalDraft` | 综述终稿 | 由已确认必需章节汇总；终审问题处理后才能确认最终稿 | FR-034 |
| `ReviewExportableVersion` | 可导出版本 | 由确认后的最终稿生成；导出内容必须与该版本一致 | FR-019, FR-034 |
| `ReviewVersionSnapshot` | P2 历史快照 | 可用于版本列表、只读快照、差异、回退和用户更改摘要 | FR-036 |

Review 不变量：

- 无可用 KnowledgeVersion 时不得创建新的 ReviewRun。
- 新建 ReviewRun 默认绑定 Project 当前默认 KnowledgeVersion。
- 大纲确认前不得自动撰写章节。
- 用户可确认低支撑章节的大纲，但系统必须记录低支撑风险和用户确认。
- ReviewRun 内同一章节不得同时存在多个生成、审查或保存任务写入当前内容。
- 章节引用必须能映射到当前 Project 论文库和 ReviewRun 绑定 KnowledgeVersion。
- 引用不足默认提示风险但不强制阻断章节确认；启用严格引用覆盖要求时，引用不足必须阻断确认，直到用户处理或显式降低要求。
- 审查结果必须与当时的章节版本、章节内容状态或修订次数关联，不得覆盖其他章节。
- 所有必需章节完成并确认后才能汇总最终文章；可选章节缺失不得阻断汇总。
- 终稿确认前必须展示未解决终审问题；用户处理或确认忽略后必须记录处理状态。
- 可导出版本至少区分未生成、生成中、已生成待确认、已确认可导出、生成失败和已过期需重新生成。
- Review 最小追溯以 ReviewRun 为边界，不跨 ReviewRun 合并历史。
- P2 历史版本回退必须二次确认，并生成新的当前版本；不得删除原历史版本。
- 用户更改摘要只能作为辅助说明，不得替代原始内容、修改元数据、人工确认、权限判断或验收依据。

## 8. 内容保护与人工修改

关联 FR：FR-017、FR-035、FR-036。

内容来源优先级：

```text
manual_edit > manual_confirm > agent_draft
```

适用内容：

- 检索词、筛选结果、论文有效性和 AI 分析。
- ResearchSession 标题、标签、总结文件。
- ReviewRun 大纲、章节正文、审查建议处理状态和最终稿。

内容保护不变量：

- 人工修改内容不得被 Agent 静默覆盖。
- 重新生成涉及人工确认或人工修改内容时必须要求用户确认。
- 用户必须能识别内容是 Agent 草稿、人工确认还是人工修改。
- 最小修改历史至少能追溯最后修改人、时间、来源动作和当前内容状态。
- 失败或取消的重新生成不得破坏原内容。
- 未实现版本列表、版本差异或回退时，不得影响 P0 人工修改保护和重新生成确认。

## 9. 导出、邮件与观点

### 9.1 导出

导出不变量：

- 导出内容只能包含用户有权限访问的 Project、Run/Session 和文件。
- 导出 Project 私人资产时，缺失文件、无权限文件或生成失败项应记录为跳过项或失败项，不得导致可导出部分整体失败。
- 导出中心不得绕过 ReviewRun 的终稿生成、终审和可导出版本确认规则。
- 大文件或多文件导出必须作为可诊断任务处理，并记录导出范围快照、文件生成结果、过期或清理状态、失败分类。
- Project 私人资产清理默认不删除已完成导出结果。

### 9.2 邮件推送

邮件推送不变量：

- 自动 ConstructionRun 成功后，邮件推送范围来自本次新增有效论文范围。
- 手动 ConstructionRun 完成后，用户可预览并手动触发首次发送。
- 邮件只包含当前 Project 中未推送且用户有权限接收的有效论文。
- 无未推送有效论文时不得发送空邮件，必须记录跳过原因。
- 邮件发送失败不得回滚已完成的论文入库。
- 推送状态必须与发送结果一致；发送失败论文不得标记为已推送，部分成功时必须区分成功项和失败项。
- 邮件内容应能追溯论文来源检索词和来源数据源。

### 9.3 观点广场

观点不变量：

- Viewpoint 内容必须至少区分类型、标题、正文、标签和联系信息。
- Viewpoint 独立于 Project Workspace；从 Workspace 跳转到观点广场不得改变当前 Project 的 Run/Session 状态。
- 观点默认只对系统内已登录且有权访问观点广场的用户可见。
- 用户可删除自己的观点；管理员可隐藏观点；删除或隐藏后普通用户不得继续看到。
- 观点禁止评论、回复、讨论串和实时聊天。
- 联系信息只允许用户名或邮箱，不得展示其他私密联系方式。
- 观点搜索和筛选只能返回当前用户有权查看且未被删除或隐藏的观点。

## 10. 权限、安全与只读边界

领域权限不变量：

- 用户只能访问自己有权限的 Project、Run/Session、论文关联、导出和诊断；Project 权限必须先满足 `access` 才能查看，满足 `use` 才能执行互动写操作，满足 `delete` 才能执行软删除或私人资产清理。
- 用户账号有效时，系统必须保证其对自己 Project 的 `access`、`use`、`delete` 全部权限始终存在。
- P2 共享协作授权未实现前，Project 权限不得把他人 Project 暴露给非 Owner 用户，也不得成为 Owner 自用 P0 主流程的前置阻塞。
- 管理员可治理账号和系统配置，但不得查看用户私人密钥明文。
- 非管理员不得访问管理员用户治理和系统配置能力。
- PDF、远程文件、Graph、导出文件等资源不得暴露真实文件路径或无权限远程地址。
- Project 知识资产面板、Research 引用跳转、Review 引用跳转均为只读探索入口，不得上传、删除、重新下载、重新解析、重新评分、重新分析、入库、推送或图谱重建。
- 高风险操作必须具备影响范围预览、二次确认或明确覆盖确认，包括 Project 私人资产清理、删除/归档、管理员权限变更、内容覆盖、清空 Project 论文关联和历史版本回退。

## 11. 领域事件

领域层应至少发出以下事件，供应用层提交任务、通知、审计、诊断或 UI 刷新：

| 事件 | 触发条件 |
| --- | --- |
| `UserRegistered` | 用户注册成功 |
| `AdminRoleGranted` | 首位管理员授予或管理员权限变更 |
| `AdminRoleRevoked` | 管理员权限撤销成功 |
| `UserDisabled` | 用户账号被禁用 |
| `UserEnabled` | 用户账号被重新启用 |
| `UserDeleted` | 管理员删除普通用户账号 |
| `PasswordResetRequested` | 用户找回密码或管理员触发密码重置 |
| `AccountAuditRecorded` | 账号治理动作写入审计记录 |
| `SystemConfigChanged` | 管理员修改系统默认配置或硬限制 |
| `SystemConfigAuditRecorded` | 系统配置变更写入审计记录 |
| `RuntimeConfigSnapshotCreated` | Run/Session/Job 启动前配置解析成功 |
| `NotificationRecipientChanged` | 用户修改收件邮箱、推送开关或通知偏好 |
| `NotificationTestFailed` | 测试邮件失败且偏好保持不变 |
| `ProjectCreated` | Project 创建 |
| `ProjectStatusChanged` | Project 暂停、恢复、归档或软删除 |
| `ProjectPrivateAssetsCleanupRequested` | 用户确认 Project 私人资产清理 |
| `ConstructionRunStarted` | ConstructionRun 启动 |
| `ConstructionRunWaitingUser` | 构建流程等待人工确认或修复 |
| `ConstructionRunCompleted` | ConstructionRun 成功完成 |
| `KnowledgeVersionPublished` | 新 KnowledgeVersion 发布 |
| `KnowledgeVersionRefreshRequested` | 用户打开或确认版本刷新 |
| `ResearchSessionCreated` | ResearchSession 创建并绑定 KnowledgeVersion |
| `ResearchSessionMetadataChanged` | 深研会话标题、标签、摘要、最后活跃时间或归档状态变更 |
| `ResearchMessageAppended` | 成功对话轮次保存 |
| `ResearchStreamFailed` | 流式回复失败、中断或取消 |
| `ReviewRunCreated` | ReviewRun 创建并绑定 KnowledgeVersion |
| `ReviewOutlineConfirmed` | 综述大纲确认 |
| `ReviewChapterUpdated` | 章节生成、编辑、审查或确认 |
| `ReviewFinalConfirmed` | 终稿确认 |
| `ContentOverwriteRequested` | 重新生成涉及人工确认或人工修改内容 |
| `ExportJobRequested` | 导出任务创建 |
| `EmailPushRequested` | 邮件推送任务创建 |
| `ViewpointPublished` | 观点发布 |
| `ViewpointDeleted` | 作者删除观点 |
| `ViewpointHidden` | 管理员隐藏观点 |

事件不携带密钥明文、真实文件路径、Provider 原始错误对象或其他用户数据。

## 12. FR 覆盖检查

| FR 范围 | Domain 覆盖点 |
| --- | --- |
| FR-001~007 | User、UserProfile、AdminRole、PasswordResetRequest、AccountAuditRecord、User/System Config、NotificationRecipient、SystemConfigAuditRecord、RuntimeConfigSnapshot、配置解析与密钥隔离不变量 |
| FR-008~019 | Project、Workspace、Run/Session、状态、锁、KnowledgeVersion、内容保护、导出不变量 |
| FR-020~027 | ConstructionWorkspace、SearchTermVersion、CandidatePaper、PaperIdentity、ProjectPaper、DocumentAsset、PaperAnalysis、KnowledgeSyncState、EmailPushJob |
| FR-028~031 | ResearchSession、ResearchSessionMetadata、ResearchMessage、ResearchStreamAttempt、ResearchOutputPreference、ResearchSummary、CitationEvidence |
| FR-032~036 | ReviewRun、ReviewOutline、ReviewChapter、ReviewFinalDraft、ReviewExportableVersion、ReviewChapterTrace、ReviewVersionSnapshot |

待后续实现校验：

- 首位管理员并发授予和最后管理员保护。
- 配置解析快照不保存密钥明文，且系统默认不静默替换用户显式选择。
- Project archived/deleted 状态的只读和不可进入规则。
- 同一 Project active ConstructionRun 唯一性。
- 自动调度重复触发和 Project 调度锁。
- KnowledgeVersion 发布条件、旧版本依赖和再次构建基线预检查。
- 人工修改覆盖保护和失败生成回滚。
- 摘要降级文本在论文详情、Research 引用和 Review 引用中的来源标记。
- Review 同章写入互斥、严格引用覆盖、终稿确认和最小追溯。
- Project 私人资产清理不破坏全局论文身份、导出结果和其他 Project 引用。
- 观点搜索筛选、删除和管理员隐藏不暴露无权限或已隐藏内容。

## 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|---------|--------|
| v1.0 | 2026-05-20 | 初始 Domain Core 骨架，定义核心聚合、Project 状态、Run/Session 通用状态、Knowledge Version、内容保护和领域事件 | Codex |
| v1.1 | 2026-05-20 | 按新版分层文档集调整文件定位，与 `00_layers.md` 和 `01_functional_requirements.md` 对齐 | Codex |
| v1.2 | 2026-05-21 | 依据 `01_functional_requirements.md` 重写结构，补齐配置、Workspace、Construction、Knowledge/Evidence、Research、Review、导出、邮件、观点、安全边界和 FR 覆盖检查 | Codex |
| v1.3 | 2026-05-21 | 补齐账号审计、密码重置、通知收件人、检索词解释字段、Research 会话元数据、观点内容结构和对应领域事件 | Codex |
| v1.4 | 2026-05-22 | 轻量补强步骤状态、自动确认策略、文档处理状态和 Review 追踪命名一致性 | Codex |
| v1.5 | 2026-05-22 | 按 `FR-008` 新 Project 权限定义补充访问、使用、删除三类权限和 Owner 默认全权限不变量 | Codex |
