# 内部模块与执行契约

文档版本：v1.3
更新日期：2026-10-21
依据文档：[00](00_layers.md)、[02](02_domain_core.md)、[04](04_api_contracts.md)、[05](05_application_use_cases.md)、[06](06_agent_knowledge_services.md)

资料读取政策接缝见[08-01 §7](08-01_agent_data_access_policy.md#7-服务接缝与可独立修改范围)。现有ActorContext/ReadContext/写入scope不能被理解为已经实现公开/私人资料判定；Q1–Q4已确认，须补政策与来源依赖的类型化接入；受理修订仅供审计，执行按当前政策，不能冻结资料权限上限。SEC-D01/03按08 §12已决规则实施，认证材料与冻结业务配置分开。

## 1. 范围与维护来源

本文把既定业务边界展开为工程契约，不新增业务状态、权限、HTTP 端点或产品分期，不选定框架、队列或数据库产品。01/02 维护业务含义；04 维护公开字段和用例 ID；本文维护内部调用与写入责任；06 维护知识服务语义；07 维护物理存储和一致性实现。

以下类型为语言无关的具名结构，尚不是可编译模型。`Id<T>`、`Revision<T>` 为不透明标识，`Ref<T>` 为可校验对象引用，`Option<T>` 表示显式可缺省，`List<T>` 表示同类型序列。各操作的具体 payload 按 04-01 逐项映射，不能把通用结构实现为接收任意字段的字典。任务与事件的持久载荷在工程实现时须补齐 schema 和兼容测试；本次不声称已生成代码或已运行架构检查。

## 2. 模块职责与写入所有权

“写者”指有权组织领域校验并提交业务事实的应用模块；repository/适配器是该模块端口的实现，不是另一业务写者。下列为代码职责边界，不要求部署为独立服务。

| 模块 | 拥有的写入入口与数据 | 允许的协作 | 禁止 |
| --- | --- | --- | --- |
| Account / Config | 账号治理、会话、个人/系统配置及审计；解析配置快照 | 为用例提供当前身份、权限事实和脱敏配置 | 以管理员身份直接管理 Project 内容；向服务传明文配置快照 |
| Project | Project 生命周期、归属；协调归档/删除和失权 | 在同一受控裁决边界请求执行模块撤销资格 | 私改 Run 成功结果、研究绑定或已发布资产 |
| Workspace | 用户/Project 下显示上下文和未提交草稿 | 查询所属对象的可访问投影 | 恢复即提交业务内容、推进任务或拥有知识资产 |
| Construction | Workspace 检索配置、补充请求、候选及其决定、Run/attempt；受控提交 ProjectPaper/ProjectMaterial/DocumentAsset 候选修订和版本发布 | 调用身份归一化、解析、Agent、候选同步端口；唯一发起版本发布提交 | 修改已发布内容；把 Agent 提案当人工确认；复用失权 attempt |
| Knowledge / Identity（能力模块） | 提供全局论文身份归一化与登记端口、知识读取、证据解析、候选准备和完整性核验能力；业务提交仍由应用协调 | 身份登记经受控应用入口且只写全局身份；候选写入限应用签发范围；读取使用 ReadContext | 从全局身份暴露 Project 私有资产；自行提交 Run 成功、默认指针或研究绑定 |
| Research | Session、轮次、回复 attempt、消息和其证据关联；创建时版本绑定 | 通过 Knowledge 读取固定版本；通过 Agent 生成提案 | 改知识资产、原地采用新版本或把失败片段变为成功正文 |
| Review | Run、大纲、章节、终稿、审查与确认事实；创建时版本绑定 | 调用 Knowledge/Agent；当前修订的授权 Markdown 读取 | 通过导出覆盖正文、迟到生成覆盖人工稿或隐式完成 Run |
| Execution（技术能力） | 命令去重、任务投递、领取、执行资格记录和持久事件 | 各应用模块在其业务事务中使用；Worker 经应用执行入口提交 | 自行定义统一业务状态机、把投递成功当业务成功 |
| 后续能力 | 调度/邮件/通用导出为 P1，观点/协作为 P2 | 分期启用后调用公开应用端口并保持自身副作用记录 | 因本表预留而提前开放入口或改变 P0 验收 |

跨模块修改只能经公开用例/端口协作；只读组合可以使用受授权的查询端口，不能通过可写 ORM 对象或跨模块 repository 绕过所有者。Project 归档/删除与结果提交的互斥遵循 05 §12，代码模块划分不能把其拆成“先成功、再异步补撤权”的竞态。共享事务上下文由应用协调，不在模块内部擅自 commit。全局身份登记也由调用应用的事务协调，只登记身份事实，不把身份匹配解释为 Project 资产授权。

## 3. 类型化输入与结果

### 3.1 应用入口

| 类型 | 必需结构及约束 |
| --- | --- |
| `ActorContext` | 已验证主体引用、request/correlation ID；注册/登录等公开用例使用明确的公开调用分支。Project 身份和权限不能由客户端自报 |
| `Command<K, P>` | 具名操作 K、ActorContext、类型化目标、P；仅按该操作需要携带预期修订、确认及幂等键。公开字段仍由 04 定义，不要求所有命令统一必填 |
| `Query<K, P>` | 具名操作 K、ActorContext、类型化范围和 P；知识读取固定版本意图，不能有隐含生成、发布或修复副作用 |
| `Outcome<T>` | `Ok<T>` 或 `Err<ApplicationError>`；成功不能夹带未标明的 Provider 失败 |
| `CommandReceipt<T>` | `Completed<T>` 或 `Accepted<TaskRef>`；后者仅在持久受理后返回，不含“可能受理”的伪成功分支 |
| `ApplicationError` | 内部分型 reason、可安全展示的摘要、诊断引用、恢复分类；对外 code/category/retryable/details/recovery 按 04 映射，不能直接序列化内部错误 |

`K` 必须是登记操作，不是客户端可指定的任意函数名；内部 Worker 操作使用独立内部入口，不新增外部端点。每个具名操作同时登记输入、结果、领域依据、归属模块及允许错误，工程实现不得只声明 `Command<object>`。

内部错误至少区分：鉴权/权限拒绝、修订或确认依据失配、执行资格撤销、版本/成员失配、配置不可用、Provider 临时失败、产物无效、持久依赖损坏、提交结果未知。该分类不是新 HTTP 错误码；不可访问对象的错误统一按 04 防枚举规则转换。“提交结果未知”必须先查持久结果，不能自动重新生成或回滚成功业务。

### 3.2 执行与知识上下文

| 类型 | 必需结构及约束 |
| --- | --- |
| `ExecutionContext` | command/task/attempt 引用、触发主体、Project（适用时）、所属业务对象、固定输入修订、配置快照引用、执行资格引用；读取任务另携带持久读取绑定。执行资格须由服务端解析并校验当前有效性 |
| `ReadBinding` | Project、KnowledgeVersion、不可变清单引用及来源 Session/Run/显式浏览意图；可持久化，不携带永久授权 |
| `ReadContext` | 已核验 ReadBinding、当前读取保护句柄；严格承接 06 §3.1。重启后从持久绑定重新取得保护，不序列化进程内句柄作为有效授权 |
| `SupplementWriteScope` | Project、补充请求引用及修订、当前 task/attempt、文件/输入修订和写资格引用；只写所属暂存文件及提取结果，不要求 ConstructionRun、基线或已发布版本，不授予候选/索引/图谱/发布资格 |
| `CandidateWriteScope` | Project、ConstructionRun、attempt、候选引用及修订、基线（首次允许无基线）、写资格引用；只能写该隔离候选，不能用于发布或任意路径写入 |
| `ServiceProposal<T>` | 类型化内容 T、输入/依赖修订引用、产物引用、相关证据引用、校验结果及诊断；所有引用须可回查，不能仅信任 Worker 声明 |
| `CommitDecision<T>` | `Committed<T>`、`AlreadyCommitted<T>` 或 `Err<ApplicationError>`；重复提交读取原持久结果，不能重复推进修订、生成版本或产生通知 |

ReadBinding 和 ReadContext 不替代当前权限校验；空版本是合法绑定，检索结果为空不等于版本错误。异步读取不能因默认版本变化重建绑定。构建基线的冻结时点遵循 05 §7：常规新构建取得槽后固定最新已发布版本，不能强迫所有排队命令提前产生 CandidateWriteScope。

SupplementWriteScope 与 CandidateWriteScope 是不同范围，不互相充当凭证。补充任务的 ExecutionContext 所属对象为 supplement，配置快照仅记录实际所需配置；其 attempt 不要求属于 ConstructionRun。接收临时字节、应用受理后准备、纳入候选及清理的衔接见 [06 §3.4](06_agent_knowledge_services.md#34-独立补充暂存与候选纳入)。

### 3.3 最小内部操作接口

| 操作 | 输入 → 结果 | 负责方与边界 |
| --- | --- | --- |
| `ResolveReadContext` | ActorContext + ReadBinding/允许的版本意图 → Outcome<ReadContext> | 应用授权后调用 Knowledge；默认值仅在允许入口解析一次 |
| `Retrieve / ReadAsset / ResolveEvidence` | ReadContext + 各操作具名查询 → Outcome<同版本证据/资产结果> | Knowledge；详细语义以 06 §3.1–3.2 为准 |
| `PrepareSupplement` | ExecutionContext + SupplementWriteScope + 具名文件/来源输入 → Outcome<ServiceProposal<补充提取结果>> | Knowledge 经获取/解析端口准备；Construction 应用提交，规则见 06 §3.4，不占构建槽 |
| `GenerateCandidateAnalysis` | ExecutionContext + CandidateWriteScope + 已确认处理状态/文本修订 → Outcome<ServiceProposal<PaperAnalysis 或 MaterialAnalysis>> | Agent 按候选 kind 分型，Construction 应用提交；来源不是正式 EvidenceRef，见 06 §4/§8 |
| `PrepareCandidate / ValidateCandidate` | ExecutionContext + CandidateWriteScope + 依赖清单 → Outcome<候选产物/完整性结果> | Knowledge；不能提交发布，实质变化使旧核验失效 |
| `GenerateResearchReply` | ExecutionContext + ReadContext + 已冻结输入/证据 → Outcome<ServiceProposal<回复结果>> | Agent；增量经应用记录，不直接提交成功消息 |
| `GenerateReviewContent` | ExecutionContext + ReadContext + 具名大纲/章节/终稿输入 → Outcome<ServiceProposal<对应内容结果>> | Agent；每类内容为独立类型，不能通过通用 PATCH 写入 |
| `CommitAttemptResult` | ExecutionContext + 对应 ServiceProposal → Outcome<CommitDecision<提交结果>> | 所属应用模块；重查授权、资格、内容保护及输入/依赖修订 |
| `CompleteConstruction` | ExecutionContext + CandidateWriteScope + 完整核验结果 → Outcome<CommitDecision<构建完成结果>> | Construction 应用；published/no_change 按 02-02/05，服务不得预先宣告 published |
| `CancelExecution` | 适用 04 操作映射出的取消命令 → Outcome<既定取消结果> | 所属应用模块先撤销写资格，再请求执行中止；以持久裁决决定响应 |

构建完成结果的 published/no_change 以及响应、任务状态直接复用现行领域与 04 定义，不能增加“部分发布”等业务分支。Review 生成结果不能用模型返回的 accepted 字段绕过应用侧既定接受规则和保护检查。

## 4. 事务、重试与取消责任

| 边界 | 谁负责 | 实施约束 |
| --- | --- | --- |
| 同步受理/编辑 | 应用 + UnitOfWork/所属 repository 端口 | 在保护边界重查条件，原子提交修订、确认消费及必要记录；适配器不私自提交 |
| 异步受理 | 应用 + 持久交接端口 | 命令去重、任务身份、冻结输入和可恢复投递记录一致；构建槽/基线按实际阶段获取 |
| 外部执行 | Agent/Knowledge 经端口 | 不持有覆盖整个推理的数据库事务；产物属于固定任务/候选范围 |
| 结果提交 | 所属应用模块 | 短事务重查当前资格及依据，业务事实和持久事件一致提交；发布默认指针与 Run 成功按 05 原子裁决 |
| 技术重投 | 投递适配器 + 应用领取入口 | 允许重复投递，同一持久命令不重复执行可观察提交；不冒充 P1 用户恢复 |
| Provider 重试 | 应用执行策略，适配器执行有限技术尝试 | 使用原输入/配置/版本，保留诊断，避免 SDK 和 Worker 各自无限重试；不确定外部结果先核验，不假设所有调用幂等 |
| 取消/失权 | 所属应用模块 | 先持久撤销资格，与成功提交排他；Provider 中止仅减少耗费，其失败不能恢复写资格 |
| 任务失败/取消的技术清理与补偿 | 受控应用流程 + 存储端口 | 仅清理所属未发布产物，校验引用和读取保护；失败保留诊断，不撤回已完成业务事实 |

上述技术清理限制不替代 Project 归档/删除及已授权私人资产治理清理；治理用例须按 02 及 05 §12 校验既有授权、预览确认范围、共享引用和依赖保留要求，不扩大删除权限。

自动重试次数、超时与具体持久交接机制尚需实施设计，不在本文猜测默认值。跨关系库/文件/向量/图谱采用隔离准备、校验、受控发布的既定边界；07 需明确其物理实现和故障恢复。公开接口连接断开不构成取消，也不触发重生成。

## 5. 内部事件与协议演进

内部持久事件描述已提交事实，不是任意可执行指令。`schema_version` 是独立的机器载荷版本，不使用设计文档的 v1.x 次版本作运行协议版本。最小信封为 `event_id`、`schema_version`、`event_kind`、`occurred_at`、`correlation_id`、`causation_id`、所属资源引用、适用的 Project 引用及具名 payload；同一事实重投使用同一 event_id。事件不得携带密钥、完整私有正文或物理存储路径。

| 事实类别（内部名称） | 最小 payload | 产生与消费边界 |
| --- | --- | --- |
| `CommandAccepted` | command/task 引用、已存输入引用 | 与受理一致记录，用于可靠投递；消费者仍须领取和校验资格 |
| `AttemptResultCommitted` | attempt、业务资源/修订、结果引用 | 业务结果提交后形成，用于任务投影；失败片段和成功正文保持分型 |
| `ExecutionAuthorityRevoked` | 对象/attempt、资格引用、原因 | 与撤销一致记录；旧 Worker 即使未收到也不能提交 |
| `KnowledgeVersionPublished` | Project、Run、version、变化清单引用 | 仅 published 产生；P0 变化投影，P1 通知按原分期接入 |
| `ConstructionNoChangeCompleted` | Run、核验既有版本、范围/时间引用 | 只用于完成事实和诊断，不触发版本升级或空邮件 |

这些名称不新增 SSE 类型；04-02 是 SSE 的唯一公开协议来源，应用投影时转换并重新校验可见性。事件消费者按 event_id/目标副作用去重；重放不能再次发布、创建业务 Run 或重复通知。内部事件不是事件溯源架构决定，数据库业务记录仍需按 07 设计持久化。

持久任务/事件载荷一旦投入使用即有兼容责任：新增 schema_version 前列出旧载荷的读取/迁移策略；未知版本保留并诊断，不能猜测解析后执行。字段删除、含义改变、默认绑定改变须同步契约、消费者及测试，不能以“内部接口”绕过人工业务裁决。进程内接口可同步修改，但仍必须检查全部调用方和模块边界。

## 6. 工程落地检查

下列检查在新核心建立后实施，本次仅完成设计约束：

- 导入图与端口检查：落实 00 §1.1，禁止领域向外依赖、API 直调 Agent/存储，以及跨模块私有仓储访问。
- 契约检查：具名 Command/Query/Proposal 的字段、空值和错误可校验，公开协议转换符合 04；持久载荷具备版本兼容样例。
- 所有权与竞争验证：取消先提交后拒绝迟到结果；人工编辑先提交后拒绝旧生成；重复消息只提交一次；发布失败不切换指针。
- 知识边界验证：ReadBinding 跨队列保持不变、空版可用、成员/Project 失配拒绝、候选写不能成为正式读取。
- 在明确隔离的数据库和 mock 外部服务中运行上述验证；静态依赖检查不能替代行为或端到端验收。

这些检查细化已有领域验收入口，不改变 P0/P1/P2。完整需求追踪、具体测试命令和执行证据由后续工程任务建立，不把文档示例当成通过结果。

本次修订 v1.1（2026-10-19）：衔接 06 审计修订，补充独立暂存范围、准备及分类分析端口；不修改公开协议或业务状态。

本次修订（2026-10-20）：登记08-01资料策略接缝和08已确认的Provider/凭据规则，不复制未决细节。

本次修订（2026-10-21）：同步资料策略Q1–Q4已确认决定与双向立即生效，详细规则在08-01维护；接口与运行验证未完成。
