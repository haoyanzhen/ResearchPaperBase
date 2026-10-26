# 内部模块与执行契约

文档版本：v1.8
更新日期：2026-10-23
依据文档：[00](00_layers.md)、[02](02_domain_core.md)、[04](04_api_contracts.md)、[05](05_application_use_cases.md)、[06](06_agent_knowledge_services.md)

资料读取政策接缝见[08-01 §7](08-01_agent_data_access_policy.md#7-服务接缝与可独立修改范围)。现有ActorContext/ReadContext/写入scope不能被理解为已经实现公开/私人资料判定；Q1–Q4已确认，类型化接入见§3.4–3.5，运行实现仍待完成；受理修订仅供审计，执行按当前政策，不能冻结资料权限上限。SEC-D01/03按08 §12已决规则实施，认证材料与冻结业务配置分开。

## 1. 范围与维护来源

本文把既定业务边界展开为工程契约，不新增业务状态、权限、HTTP 端点或产品分期，不选定框架、队列或数据库产品。01/02 维护业务含义；04 维护公开字段和用例 ID；本文维护内部调用与写入责任；06 维护知识服务语义；07 维护物理存储和一致性实现。

以下类型为语言无关的具名结构，尚不是可编译模型。`Id<T>`、`Revision<T>` 为不透明标识，`Ref<T>` 为可校验对象引用，`Option<T>` 表示显式可缺省，`List<T>` 表示同类型序列。各操作的具体 payload 按 04-01 逐项映射，不能把通用结构实现为接收任意字段的字典。任务与事件的持久载荷在工程实现时须补齐 schema 和兼容测试；本次不声称已生成代码或已运行架构检查。

具体工程选择和规划代码位置见[00-01](00-01_engineering_baseline.md)，本文件的语言无关契约不因此变成已生成代码。

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

### 3.4 资料判定类型与可信生产链（A06）

政策唯一来源仍为[08-01](08-01_agent_data_access_policy.md)，本节定义内部必需结构，不新增机器schema。以下字段均必需，只有标明Option的项可空；空集合只表示经过完整枚举确实无该类输入，不等于来源未知。类型化分支必须互斥，不接受任意metadata或客户端allow标记。

| 类型 | 必需事实 / 生产者 → 消费者 | 生命周期、可空与拒绝语义 |
| --- | --- | --- |
| `MaterialPolicyBasis` | actor、Project、mode、policy_revision、Option<risk_acknowledged_at>；Project应用读取本人政策记录 → 判定端口 | 每次边界重新读取；缺记录用A05稳定public_only初始修订，不写Workspace；从未发生风险同意时风险时间可空（包括只写public_only后的记录），allow_private须非空，关闭后保留最近一次风险同意时间。受理副本只审计 |
| `MaterialSourceRef` | Project、source_id、content_revision；接收/内容所属应用登记 → Knowledge及判定端口 | 标识具体不可变内容，不能用DOI/哈希代替；每次验证归属和修订。不是已发布EvidenceRef，不强制补充/候选有版本 |
| `CurrentClassification` | source、classification、confirmation_status、classification_revision、Option<confirmation_fact>；Construction经既有分类用例提交 → 判定端口 | confirmed须有完整basis/确认主体/时间；unconfirmed的fact为空；无分类按A05保守未确认投影，不创建public事实。分类修订不等于内容修订 |
| `SubmissionScope` | scope_id、actor、Project、command、明确文字的source/content_revision、接收依据引用；当前文字接收应用 → 来源解析及派发/提交校验 | 仅本次明确提交文字；与持久命令一致登记，同命令重放复用，不能重放新授权。无Task的同步用例仍有服务端操作身份，不制造Task；结束后仅审计，失权不复活。上传文件无此分支 |
| `InputProvenance` | source、kind、Option<SubmissionScope引用>、dependency_status；应用根据接收记录/历史归属/服务输入追踪生成 → 各读取及生成端口 | kind对应A05六种来源；current_submission须scope和complete，其他scope为空，unknown须unknown。Worker/客户端给出的kind只是不可信声明，须从服务端记录重建 |
| `InputDependencySet` | 产物/包身份及修订、全部实际直接输入引用、递归闭包引用及校验依据、complete/incomplete/unknown；Knowledge追踪实际读取和组装输入，所属应用校验登记 → 读取/派发/提交端口 | 包括问题、系统拼入的主题、历史、摘要、工具结果、草稿、检索正文；引用列表不代替输入清单。每条边固定内容修订，当前分类单独查询；缺边/不可解析/循环不能证明完整，拒绝推定公开 |
| `MaterialUseRequest` | actor、Project、purpose（agent_read/context/dispatch/commit）、具名操作、分型业务范围、实际输入依赖、Option<ExecutionContext>；应用/受控服务 → 判定端口 | 范围为ReadBinding、SupplementWriteScope、CandidateWriteScope或无版本的具名输入范围；按操作分型，不能随意互换。同步读取无ExecutionContext，异步执行必须有；此类型用于Agent资料使用及其结果提交，必要静态保存按05 §3.3分流；不能凭purpose绕过权限 |
| `MaterialUseDecision` | Allowed（basis、全部分类修订依据、输入闭包摘要、范围、边界标识、可用范围提示）或 Denied（内部原因、安全提示、诊断引用）；应用调用判定端口 → 受控操作 | 仅本次边界有效，不是持久授权票；缺事实/读取失败不能返回Allowed。内部拒绝不附无权来源明细；修订变化要求重判而非直接终止全部任务 |
| `PreparedInputBundle` | 包id/不可变修订、实际载荷受保护引用、InputDependencySet、原业务范围、配置引用、组装判定依据；Agent/Knowledge组装 → 应用派发入口 | 不放凭据；包不可原地增加工具结果或历史。任何变化重新组装和核验；组装通过不等于允许发送 |
| `DispatchEvidence` | 派发身份、包修订、attempt/操作身份、Provider配置引用、实际裁决依据、派发阶段及时间；受控派发端口 → 应用审计/结果提交 | 阶段为技术事实（未交付、进入不可撤回、结果已知或未知），不是业务状态。不保存正文/凭据；队列入队不算派发。未知先核验，不盲重发 |

`EvaluateMaterialUse(MaterialUseRequest)`返回Outcome<MaterialUseDecision>：应用负责授权及业务资格，策略能力读取可信政策/分类/来源端口并返回判定；Infrastructure只实现受控查询和裁决，不取得业务写权。Project应用拥有本人政策选择，Construction拥有来源分类安全元数据写入口（不意味着改写Research/Review内容）；Research/Review及Construction各自登记所属产物依赖。没有新增独立业务服务或公开操作。

`ReadContext`关联本次MaterialUseRequest及判定依据，但仍只携带原ReadBinding与读取保护；下一次受控读取须重判。ExecutionContext关联受理政策修订（仅审计），ServiceProposal追加实际InputDependencySet及适用的DispatchEvidence引用，应用核对服务端调用轨迹和包修订，不能只相信Worker自报“complete”。静态提取无外呼时DispatchEvidence列表为空，不能伪造一次模型调用。

### 3.5 来源例外、依赖与A05逐项对应

| A05事实/字段 | 内部消费与约束 |
| --- | --- |
| MaterialPolicyView.user_id/project_id/mode/revision/risk_acknowledged_at | 映射MaterialPolicyBasis；读取主体来自认证/持久触发者，不能由任务执行机器账号或另一个成员替代；风险事实不扩大网络或模型配置授权 |
| MaterialSourceIdentity.project_id/source_id/content_revision | 映射MaterialSourceRef；内容哈希只验证内容，不验证权限；完整详情注册交A08，不新增任意注册端点 |
| MaterialClassificationView.classification/confirmation_status/revision/confirmation | 映射CurrentClassification；GET可未确认，confirm/correct成功必须confirmed；政策、分类、内容、业务编辑四类修订不得混用 |
| MaterialClassificationFact.basis/confirmed_by/confirmed_at | 核验来源依据和服务端确认事实，不能只检查非空字符串；来源/确认不能由LLM签发 |
| MaterialProvenance.kind/submission_scope_id/dependency_status | InputProvenance的安全只读投影；scope_id仅指向服务端事实，不是客户端可转移凭证；complete只说明依赖完整，不说明允许使用 |
| 分类POST的meta.idempotency_expires_at及original_request_id | 原命令去重记录的安全投影；两POST成功/重放均有非空期限，至少24小时按04执行，不用分类revision/SubmissionScope替代去重身份；重放旧事实不回写当前分类 |
| MaterialUseNotice.reason/message | 内部理由经可见性检查转换为A05词汇；available_subset仅说明检索范围受限，其余拒绝不带敏感来源明细；Task完整字段留A07 |

本次可信文字例外只对同主体、同Project、同命令和同内容修订的直接文字输入有效，仍核验当前账号/业务资格。包中其余来源逐项按当前分类判定；粘贴文字不授权自动抓取原文件。再次自动读取该文字时重建为historical_input且scope为空，不继承例外。派生产物本身不取得SubmissionScope：本次生成结果提交可以核验原命令实际直接文字输入及其例外；以后把该产物作为输入（包括同命令的下一次自动读取）仍须走派生来源及完整依赖判定，不能把上次例外或complete当作public。若来源缺分类/依赖，按未确认/受限处理；不自动弹新确认或发明来源注册操作，交已有合法入口与A07/A08承载。

合法例：新补充仅静态提取，不要求版本或模型；用户本次明确文字加已确认公开证据可进入本命令输入包。非法例：上传文件复制scope、跨命令复用文字scope、历史摘要只列公开引用却隐去私人批注、同哈希跨Project复用判定，均在读取/派发前拒绝。由全部公开依赖构成的派生产物可证明允许，但任何显式当前私人限制仍优先；混合不可分割产物整体判定，不以模型声称脱敏解除限制。

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

本次修订（2026-10-21）：衔接A01–A03工程/审核入口；未改变业务规则或宣称运行验收通过。

## A07 任务投影、预览与公开事件接缝

公开字段唯一见[04-01 §1.1–1.2](04-01_p0_operation_contracts.md#11-confirmationpreview具名影响与保留项a07设计)及[04-02](04-02_transport_task_file_contracts.md)。以下为内部职责，不新增公共命令或业务状态。

| 生产者 → 消费者 | 输入与输出 | 必须维持的约束 |
| --- | --- | --- |
| 各用例受理 → Task投影 | 持久command/attempt、目标及祖先、固定ReadBinding → TaskHandle/TaskView | 目标在受理时固定；尚未产生的终稿以Run定位，生成后不改原target；账号治理无Project内容权限 |
| 业务读取 → 等待投影 | 当前等待实体/修订、当前主体与能力 → TaskWaitingRef[] | 先校验Task和祖先权限，再返回合法读取入口与动作交集；内容待确认不等于技术Task挂起，无活跃任务不制造Task |
| 预览应用 → 确认校验/命令受理 | 当前目标、动作参数、完整影响集/修订 → ConfirmationPreview | 服务端持久或可验证绑定精确影响；预览不写业务状态；正常受理按04幂等优先级处理，首次受理重验token、范围、修订、权限、锁；受理后使用持久确认依据 |
| 业务提交/任务执行 → 快照与SSE投影 | 已提交状态、增量/引用/安全错误、A06安全资料提示 → 同提交TaskView/适用output/事件 | 07事务边界下原子保存游标和所有相应投影；不可先发送后落库。资料提示不泄漏来源依赖且不变成可执行授权 |
| 当前可见性服务 → 查询与回放 | 当前账号/Project资格、流绑定及引用 → 安全投影或拒绝 | 每次读取/订阅及持续连接检查；内部事件不直接透传，旧token/私有内部诊断不得进入公开日志或回放 |

内部事件event_id与公开事件event_id不假定一对一：一个提交可投影多个公开事件。持久记录公开事件身份及每attempt顺序，重投同一投影复用身份；内部schema_version不冒充公开信封版本。重新读取/订阅是纯查询，不领取执行资格、不派发Provider、不新建attempt。若投影异步实现，必须返回同一已投影提交的完整快照，不能让新游标越过未投影正文；具体存储方案留工程任务。

本次v1.6仅完成接缝设计。所有权、原子性、撤权、重复和迟到提交仍需隔离持久化测试，见09的A07验收交接。

## A08 具名服务接口落点

PrepareSupplement精化为`PrepareSupplementInput → Outcome<ServiceProposal<SupplementPreparation>>`；GenerateCandidateAnalysis精化为`CandidateAnalysisInput → Outcome<ServiceProposal<CandidateAnalysisProposal>>`。全部具名结构由[06 A08](06_agent_knowledge_services.md#a08-补充处理与分析具名服务载荷)维护，不再由调用方自行补object。ProcessingResult的paper/material分支分别落DocumentProcessingState/MaterialProcessingState；公开读取按04-01的ProcessingBasis/AnalysisBasis投影，不直接序列化内部输入依赖或文件摘要。

应用核验实际scope类别、对象/Project/输入与当前资格，再允许提交；两个WriteScope即便文件相同也不能互换。补充纳入必须另建候选范围与固定来源映射，不能把解析器成功当纳入或确认。重试沿06 A08.4有限预算，当前policy/静态处理分流沿A06；补充详情及Task事件沿A07，不新增运行状态。


## A09 知识构建与读取接缝

[06 A09](06_agent_knowledge_services.md#a09-首版知识构建与graph-rag方案)维护KnowledgeBuildInput/BuildProfile、ChunkRecord、GraphAssertion、KnowledgeReadyProof、KnowledgeQuery及EvidencePack具名结构；PrepareCandidate返回隔离产物，ValidateCandidate读回生成就绪证明，CompleteConstruction仍是唯一发布入口。Retrieve/TraverseGraph只接收固定ReadContext，不使用SupplementWriteScope，不接受模型自报的版本/授权。Graph路径需返回原文支持，同版empty与Err分型；模型dispatch前及新结果提交继续沿A06核验，A09不绕过04公共错误和A07任务边界。

