# Agent & Knowledge Services 设计

文档版本：v1.14
更新日期：2026-10-23
依据文档：`00_layers.md`、`01_functional_requirements.md`

资料分类与派生内容策略见[08-01](08-01_agent_data_access_policy.md)。补充/候选、嵌入、检索和历史上下文均有接入点，不能仅过滤文件下载；Q1–Q4已确认，后续读取/外发/提交均核验当前政策；扩权不重做步骤，收紧不静默剪历史。Provider访问与当前凭据解析遵循08 §12已确认规则，具体网络/认证实现仍需验证。

## 1. 设计目标

Agent 与 Knowledge 采用共层方案：二者都位于 Application Use Cases 之下、Infrastructure Adapters 之上。Agent 负责智能行为、生成和流程执行；Knowledge 负责论文资产、检索、版本、证据和可复用知识能力。

源码依赖方向（运行时经端口调用适配器）：

```text
Application Use Cases
  -> services/agents
      -> services/knowledge
          -> Knowledge ports <- Infrastructure Adapters
```

Knowledge 不依赖具体 Agent；Agent 的 LLM/来源等能力也通过自身端口注入。两者不导入具体适配器或应用用例，领域层不依赖二者。模块写入归属与最小类型见 [05-01 内部契约](05-01_internal_module_contracts.md)。本文细化工程边界及补充接收、候选处理、证据和确认的既定规则；具体适配器、持久化映射和运行验证仍待完成，不表示服务已实现或整体定稿。

## 2. Agent 服务边界

| Agent | 输入 | 输出 | 不负责 |
| --- | --- | --- | --- |
| Construction Agent | Project 主题、检索词、数据源策略、补充/候选输入、配置快照 | 论文/资料候选提案、评分、分类 AI 分析、入库建议、构建结果提案 | 直接绕过用例发布版本或发送邮件 |
| Research Agent | 用户消息、Knowledge Version、Graph-RAG 证据；输出倾向为 P1 | 流式回复、引用；总结草稿为 P1 | 修改 Project 知识库 |
| Review Agent | 综述主题、范围、大纲/章节状态、Knowledge Version、证据 | 大纲、章节、审查意见、终稿、参考文献 | 静默覆盖人工编辑内容 |

## 3. Knowledge 服务能力

| 能力 | 职责 | 关联 FR |
| --- | --- | --- |
| Paper Identity | 归一化 DOI/arXiv/URL/来源 ID，完成全局去重 | FR-022 |
| Project Library | 提供 ProjectPaper/ProjectMaterial 的候选处理与只读投影，包括有效性、评分和分类分析；业务提交归应用；推送状态按只读投影展示，邮件执行仍为 P1 | FR-012, FR-026 |
| Document Assets | 提供论文 PDF、支持格式资料、解析文本、摘要降级及文件访问引用，区分补充暂存、候选和已发布范围 | FR-024 |
| Vector Index | 写入和查询向量索引，记录同步状态 | FR-026, FR-028 |
| Knowledge Graph | 构建论文、作者、关键词、概念、方法等节点边 | FR-026, FR-031 |
| Graph-RAG Retriever | 基于版本检索证据，返回引用定位 | FR-028, FR-032 |
| Knowledge Version | 发布准备、稳定绑定读取解析、版本变化与证据风险提示、新研究采用检查；应用负责提交发布与绑定 | FR-018 |
| Citation & Evidence | 解析论文/资料证据片段、文件与图谱跳转，校验版本一致性；引用关联由所属应用保存 | FR-031, FR-033 |

### 3.1 版本读取与存储适配契约

本节落实 [领域快照边界](02-02_construction_versioning_appendix.md#25-不可变逻辑快照与资产复用边界)，其余未细化服务仍为草案。下列名称为内部语义契约，不强制语言签名或新增 HTTP 端点。

| 契约 | 必需输入与返回 | 边界 |
| --- | --- | --- |
| ResolveReadContext | 已鉴权主体、Project、来源对象或显式版本；返回固定的版本/清单标识及受保护读取句柄 | 对象绑定优先且必须与显式版本一致；只允许普通浏览入口解析默认值；句柄不代替后续授权 |
| ReadAsset / ResolveEvidence | ReadContext、资产或证据标识；返回实际版本、资产修订、来源及定位 | 服务端解析清单成员；拒绝跨 Project/版本拼接；不读取当前资产替代历史资产 |
| Retrieve / TraverseGraph | ReadContext、已校验查询/过滤/分页参数；返回同版本证据及游标 | 检索候选、排序、扩展节点和边均受版本约束；适配器不能退回 Project 全局最新集合 |
| PrepareCandidate / ValidateCandidate | 构建写资格、候选修订、基线、依赖清单；返回产物引用和完整性证明 | 只写隔离候选；候选变化使相关验证失效；不能由读取服务隐式修复或发布 |

ReadContext 在任务、子任务和恢复记录中稳定传递；缓存按 Project、版本/清单、资产修订及影响结果的查询配置区分，命中后仍校验当前访问权，不复用旧授权结论。相同文件内容哈希不能作为访问凭证。

VectorStore/GraphStore 必须声明版本隔离、不可变读取和就绪核验能力；不满足能力的适配器拒绝启用，不以宽松过滤降级。初始实现使用版本隔离的索引/图谱视图，Provider 更换不得改变上层读取语义。内部错误区分版本不匹配、成员缺失、依赖不可用和权限失败；对外按 04 安全错误规则映射，不泄露不可访问对象是否存在。

### 3.2 引用解析与版本摘要投影

ResolveEvidence 按当前授权/Project 范围→绑定版本成员→不可变修订→片段/图谱定位与完整性→受控文件入口顺序校验；内部诊断区分临时故障、凭据过期、缺失、失配和撤权，公开映射遵守 04 防枚举规则。禁止通过搜索最新版补齐。RiskNotice 从已有带来源/时间的风险记录投影，不新增自动风险采集或支持性裁决服务。

采用新版本后的生成流程只把旧引用作为背景，在目标 ReadContext 重新检索/解析后保存新 EvidenceRef；复用相同内容也形成目标版本身份，保留允许的来源关联，不复制人工确认。版本摘要按冻结清单统计论文主文本来源，检索范围按来源 ConstructionRun 事实投影，动态可用性和风险独立计算；累计快照不能用最后一次检索窗口代表。对外字段唯一来源见 [04-01 §5.1](04-01_p0_operation_contracts.md#51-版本摘要与引用解析补充)。

空版本是合法 ReadContext：允许浏览、新建 Research/Review，检索返回空证据并明确提示，不按成员数拒绝创建、不自动选择历史版，也不伪造引用。

### 3.3 结果提案与端口实现

异步服务执行携带 [05-01](05-01_internal_module_contracts.md) 的 ExecutionContext；同步正式知识查询使用 ActorContext 与本章 ReadContext，无须制造 command/task/attempt。研究读取使用固定 ReadContext；补充准备使用 SupplementWriteScope，候选准备使用 CandidateWriteScope。补充/候选文件只读入口按 04-02 校验所属请求或 Run，不强造已发布版本。读取句柄不等于授权，也不提供写能力；写资格不能用作跨 Project 读取凭据。

服务仅返回类型化结果、产物引用或安全错误；流式增量经应用记录/投影，不由 Agent 直接写 HTTP/SSE。服务不得自己确认人工内容、推进 Run 成功、发布版本、保存最终正文或发送发布通知。独立生成失败保留可诊断结果，不覆盖已保存正文。

候选文件、向量和图谱的准备只写所属隔离候选空间并返回就绪/完整性依据；校验依据绑定候选修订，不能作为永久有效的发布凭据。独立补充的文件和提取结果使用下节暂存范围，不具备向量/图谱写入或发布资格。应用在最终短事务重新校验资格、确认和基线。外部产物清理由受控应用流程调用；任务失败/取消的技术清理仅处理所属未发布产物，不能由 Provider 自行删除共享或已发布依赖。Project 治理清理仍按既有领域授权、范围和依赖保留规则执行。具体事务与物理映射留给 07，不要求将长时间推理纳入数据库事务。

### 3.4 独立补充暂存与候选纳入

本节承接 [04-02 单文件接收](04-02_transport_task_file_contracts.md#4-单文件上传与补充处理)及[未发布文件读取](04-02_transport_task_file_contracts.md#51-未发布文件读取)，不新增公开端点或确认门槛。

- 接收阶段可为校验、计算幂等指纹暂存字节；这些字节不具有业务确认或候选写资格。通过基础接收后由应用持久受理 supplement/task 并关联文件，异步准备使用与 Project、supplement 修订和当前 attempt 绑定的 SupplementWriteScope。失败或重复请求的无归属临时字节由接收流程清理，不产生重复请求或重复解析。
- `PrepareSupplement` 只获取/提取所属文件及元数据、标题草稿、可用文本和诊断，返回类型化提案，由 Construction 应用提交补充处理结果；没有 Run 时也合法，不占构建槽，不要求 KnowledgeVersion。只有实际调用 LLM 时才需要相应模型配置，普通静态解析不强制选择模型。
- 基础接收成功不等于深度解析成功；解析到多候选、元数据冲突或缺标题时按 04 的补充详情/编辑/确认流程处理，不自动确认。深度解析失败保留请求和诊断；安全可读原文件仍可经补充专用入口读取，不能据此进入研究检索。
- 纳入由应用按 05 §7 固定已确认补充及其有效修订，再建立到 Run/候选的来源关系并签发 CandidateWriteScope。可复用经核验的不可变文件/提取产物，但须重新验证归属、输入及处理依据，不能继承不适用的处理或分析确认。运行开始后新增补充默认待下轮，不能因存在 active Run 就改写其输入。
- 补充暂存资格不能直接升级为候选/发布资格；任何被撤销资格的迟到提案均拒绝提交。纳入与清理须互斥核验依赖，不能先查一次引用就删除文件。取消 Run 只清理其可清理残留，不删除独立待纳入补充、人工内容或被其他有效依赖使用的文件。保留期限和物理回收方案仍由 07/运维细化，不在本节新增自动删除期限。

### 3.5 受控读取、上下文与缓存入口（A06）

所有Agent使用入口遵循：可信主体和Project→业务范围/固定输入及资格→当前政策→实际来源/当前分类及依赖闭包→受控操作。类型见[05-01 §3.4](05-01_internal_module_contracts.md#34-资料判定类型与可信生产链a06)，裁决见[05 §3.3](05_application_use_cases.md#33-当前资料政策的受理派发与提交裁决a06)。人工查看与必要静态接收单独走原权限及文件安全检查，不把Agent开关当作下载权限。

| 入口 | 范围及输入检查 | 输出/失败与追踪 |
| --- | --- | --- |
| ResolveReadContext、ReadAsset、ResolveEvidence | 固定ReadBinding与保护；Agent用途在每次实际读取重验来源及当前分类，人工用途仍核验Project/版本/生命周期 | 同版受保护结果或安全错误；不以latest修复，空版合法。IC-02/05/10/12 |
| Retrieve、VectorStore查询 | 查询文本本身先核验来源；版本/Project/政策允许集合在top-k及排序前限定；嵌入查询前也检查输入 | 合法子集及available_subset；空子集不声称全库无结果，不把故障当空。IC-02/07/10 |
| TraverseGraph、GraphStore聚合 | 每步节点/边按完整来源闭包校验；不可隔离的混合聚合整体排除；节点身份合并不丢来源 | 仅允许事实与同版定位；依赖不完整不进入上下文。IC-01/02/06 |
| 缓存命中（检索、正文、图谱、工具、生成） | 重新取得当前身份/范围/政策/分类及闭包；验证完整查询范围依据，不能只检查命中条目 | 不匹配则下一次正常操作重算或取匹配项；不得自动重做已结束步骤。IC-02/07/09 |
| PrepareSupplement、静态解析 | SupplementWriteScope及文件修订；静态安全接收/必要提取不要求模型或已发布版；一旦LLM辅助标题/元数据则先确认文件分类并检查政策 | 静态提取继承文件来源，不自动public；上传不签文字scope。IC-05/06/12 |
| GenerateCandidateAnalysis、PrepareCandidate、ValidateCandidate | CandidateWriteScope、处理/确认修订和原冻结输入；嵌入/图谱/分析每个模型入口核验全部实际输入 | 独立提案与依赖，不成为正式EvidenceRef；分类放宽不加入新补充。IC-01/03/10 |
| 检索词建议、Project主题辅助 | 无版本具名输入范围；当前文字与既存主题/词/草稿分开解析，工具调用仍过受控端口 | 无需伪造版本/引用；自动历史输入不继承文字例外。IC-05/11 |
| GenerateResearchReply、GenerateReviewContent及后续摘要能力 | 固定ReadContext、当前明确文字和全部必需历史/摘要/草稿/工具结果；Review原大纲/章节/确认修订仍有效 | 必需混合历史受限明确阻断，保留原稿；不能剪历史、换版或自动重新总结。IC-04/10/11 |
| LlmProvider、EmbeddingProvider的实际派发 | 仅接收不可变PreparedInputBundle；应用在真实发送边界重新核验，Provider适配器不增补检索或历史 | DispatchEvidence关联实际包，失败不形成可采纳结果；网络/凭据独立校验。IC-03/08/09 |
| 服务提案与应用提交 | 实际输入依赖与派发记录随提案回传；应用验证其与可信轨迹一致及当前资格 | ServiceProposal不是提交凭证，应用原子裁决；重复/未知按原结果核验。IC-03/09/10/12 |

缓存的**内容可复用性**和**当前查询范围完整性**分开判定：条目可读不意味着旧top-k足够回答新范围查询。缓存依据至少关联主体/Project、原ReadBinding或补充/候选范围、内容/包及查询配置、当时政策修订、分类与依赖依据，以及能证明查询候选全集仍相同的范围依据。任一依据变化而不能证明匹配，则该次正常检索重新计算；不指定必须使用何种缓存键或全局epoch。扩权时旧公开缓存不能冒充包含私人来源的完整新范围，收紧时旧私人条目不得先读入上下文再过滤。

依赖闭包完整性必须来自输入生产链：静态提取登记源文件；切片登记正文；向量登记实际嵌入文本；节点/边登记全部参与事实；生成记录实际包（包括未引用输入）；摘要/工具/缓存保留递归来源。已登记依赖与不可变输入包不一致时拒绝复用/提交，不能由LLM补一个“公开”标签。来源变更可惰性传播，但每次操作要沿当前来源记录重验；若闭包不可解析则明确受限/故障，不能等后台刷新期间放行。可信本次文字的例外与派生后再用规则仅由05-01 §3.5维护。

## 4. Construction Pipeline

检索词管理支持 Project 主题生成建议词、用户编辑、检索词级数据源策略和自动更新开关。新生成或新增检索词默认 `auto_update_enabled=true`；用户后续修改自动更新开关是在该默认态上调整。手动 Run 使用本次 selected 检索词；自动 Run 使用 `auto_update_enabled=true` 的检索词。

多源检索支持 arXiv、OpenAlex、Semantic Scholar、ADS 和后续扩展 Provider。Provider 返回统一候选结构，不把 SDK 原始对象泄漏到应用层。数据源失败应分类为缺失配置、密钥失效、限流、连接失败、权限过期或 Provider 不可用。

论文去重使用全局论文身份归一化，评分包含主题相关性、来源质量、时间新鲜度、摘要匹配度。资料按 Project 内归一化标题及 content_format/相似格式组识别重复或疑似重复，记录 MaterialDeduplicationDecision/MaterialScreeningDecision，不套用论文身份或强制作者、年份、语言、provider。标题归一化及轻量元数据遵循 [02-03 §5](02-03_construction_assets_appendix.md#5-手动补充与资产边界)。两类候选均保留人工调整和误合并修正依据；手动 Run 确认筛选后才能进入下载解析，自动 Run 仅按 P1 安全自动确认策略处理。

论文优先获取 PDF 并解析全文；缺失或失败时，只有实际可用摘要才能作为降级文本，并记录原因及来源，不能生成摘要冒充原文。资料按实际格式静态提取文本，不套用论文摘要降级；获取/解析失败或无可用文本时记录失败或不可用结果，不伪造文本。两类处理分别收敛到 DocumentProcessingState/MaterialProcessingState，后续分析只使用其最终可用文本及修订。

P0 资料格式及能力白名单以 [04-02 §4.2](04-02_transport_task_file_contracts.md#42-基础校验与解析边界)为唯一协议来源，包含 PDF、Office 文档/演示文稿、HTML、文本、结构化文本、notebook 和已声明的代码格式；doc/ppt 不降为 P1。数据表仍 P1，多媒体仍 P2；不运行宏、脚本或 notebook/code。缺解析器只能记录未满足能力和诊断，不能宣称支持或伪造成功。

手动 Run 必须先确认处理摘要、失败/降级/不参与知识构建项，才能分析。`GenerateCandidateAnalysis` 接收 ExecutionContext、CandidateWriteScope、已确认的处理状态及文本修订，按 kind 返回 PaperAnalysis 或 MaterialAnalysis 提案：论文为一句话总结、亮点、相关性要点、方法与创新；资料仅要求 important_summary、relevance_points，字段由 04-01 维护，不强制论文方法/创新字段。结构化失败不记成功，手动确认分析后才进入入库预览；自动确认继续受既有 P1 策略限制。候选编辑、处理互斥及受影响确认失效按 02-03 §6 执行。

有限技术重试使用同一有效输入、文件和配置依据，记录 attempt/诊断；过期结果不得替代当前处理状态。深度解析失败、无可用文本或输出结构失败均不自动确认、不进入正式证据。P0 不因此增加原 Run retry/reconnect/rerun 或补充专用重试端点；公开操作仍限 04，通用恢复沿用 02-04 的 P1 规则。

入库先在本轮隔离候选范围内写 ProjectPaper/ProjectMaterial 修订与文本资产，再写向量库和图谱同步项；不得覆盖已发布证据。发布 Knowledge Version 前校验关系数据、向量索引、图谱和引用定位完整可读。执行边界遵守 [知识库并行构建与版本更新领域附录](02-02_construction_versioning_appendix.md)；本文仍为待细化草案。

论文与 ProjectMaterial 入库确认受理前允许修改候选并使受影响处理失效，受理后锁定。已发布内容只读，不能通过元数据、文件、解析、分析或评分服务绕行修改；须先移除关联并发布，再显式重新导入，重做确认。重复命中当前成员只记备选来源，自动检索不恢复人工排除。筛选等待点返回检索仅追加确认词，来源、时间范围、预算与基线不变，使用剩余额度；服务不提供 P0 原 Run 失败恢复。

移除服务只处理已确认集合与修订，冲突执行终止仅按同次明示预览授权，后出现冲突交应用层重做预览；不得自主取消。有意全清空发布完整一致的空清单/索引/图谱，保留旧版依赖，不把失败或零新增当清空。

构建结果须区分 `published` 与 `no_change`，两者均为 Run 成功结果属性，不增加状态。只有完整核验既有版本且可读知识确无变化才可报告 no_change，不能用零新增、来源失败或未完成处理冒充；首次无已发布版本不适用。no_change 不发布、不切换默认版本、不发送升级提示或空邮件，候选按领域状态机收尾，恢复与清理仍引用 02-04。

## 5. Research Pipeline

- Session 创建时绑定已发布 Knowledge Version，采用新知识创建关联新 Session，不原地切换。
- P0 普通回复不依赖输出倾向设置；创新、实验、总结三类倾向为 FR-029 的 P1 能力，启用后仅影响后续回复，不改历史或版本绑定。
- Graph-RAG 返回同版本论文/资料证据包，正式引用使用 04-01 EvidenceRef（asset_kind=paper/material），包含资产身份、不可变修订依据、文本来源、片段/图谱定位及版本；内部检索评分不作为引用充分性或确认门槛。
- 应用保存回复及引用列表，引用可跳转到论文/资料详情、授权文件或 Graph 节点。无证据时列表可为空；空检索须按 04-01 的明确选项决定是否继续普通回复并标记无引用上下文，不把检索失败当空结果继续。
- 若绑定版本缺失或不可访问，消息发送失败并展示修复路径。

## 6. Review Pipeline

- Review Run 创建时绑定已发布 Knowledge Version，采用新知识创建新版 Review，不在原 Run 混合版本。
- 大纲生成后允许编辑，但编辑不等于确认。只有绑定当前大纲修订和本 Run 知识版本的有效用户确认，才允许生成章节；编辑使受影响旧确认及下游依据失效，保留旧成果。低支撑提示不增加确认阻断门槛，生成/提交仍重查修订和确认有效性。
- 章节生成携带绑定版本证据；空证据明确标注，不阻断对象创建或伪造来源。
- 按 FR-033 学术规范审查归属、支持关系和参考信息；机械检查引用链接及版本定位，语义判断只给建议，不计算覆盖率、豁免或 strict 通过分数。
- 终稿汇总生成单一完整 Markdown 正文；摘要、关键词及参考文献投影与正文同修订，无独立导出快照。accepted 当前稿保存后可 P0 下载，完成后只读；拒绝稿不由编辑复活。生成失败/迟到结果不覆盖人工稿。
- P2 版本管理可扩展只读快照、差异、回退和变更摘要。

## 7. Provider 抽象

Agent/Knowledge 只依赖抽象接口：`LlmProvider`、`PaperSearchProvider`、`PdfFetcher`、`PdfParser`、`MaterialFetcher`、`MaterialParser`、`EmbeddingProvider`、`VectorStore`、`GraphStore`、`FileStore`；`MailSender` 按 P1 邮件能力启用，不授权 Agent 自行发送通知。

MaterialFetcher 接收经应用校验的来源及补充/候选写入范围，遵守 04-02 的 URL 获取限制；MaterialParser 接收所属不可变文件引用、识别格式及解析参数，按已实现格式路由静态解析器，返回可用文本引用、定位、输入修订和诊断。PDF 实现可复用，但 kind=material 仍返回资料处理/轻量分析语义。提取结果由应用映射到既定处理状态；解析器不能确认、发布或修改业务状态。端口不指定具体库，不用 FileStore 的字节读取能力冒充多格式解析能力。

Provider 必须返回统一错误分类和诊断元数据，不返回密钥明文、真实文件路径或不可序列化 SDK 对象。

## 8. 输出校验

所有 LLM 结构化输出均按具名操作校验 JSON/schema、必填字段及类型，服务返回独立提案；应用提交时另校验当前权限、执行资格、输入修订和人工内容保护。来源校验必须按使用场景区分，不能以统一“已发布版本成员”门槛阻断发布前处理：

| 输出场景 | 校验依据 | 禁止 |
| --- | --- | --- |
| 检索词建议等无证据输出 | 所属 Project/Workspace、实际输入修订和生成配置 | 强造 KnowledgeVersion 或 EvidenceRef；生成即人工确认 |
| 独立补充提取/元数据或标题草稿 | SupplementWriteScope、请求/文件修订及实际提取来源 | 要求已有 Run/已发布版本；将草稿或临时文本视为正式证据 |
| 论文/资料候选分析 | CandidateWriteScope、固定候选/处理文本修订、当前有效处理确认及来源归属 | 要求新候选已在基线成员内；跨候选拼接未经本次输入授权的文本；将分析提案视为已确认 |
| Research/Review 正式证据 | ReadContext、Project、绑定版本清单、paper/material 资产修订、定位及当前授权 | 从补充/未发布候选、其他 Project 或其他版本补齐；缺失时回退 latest |

首次构建无已发布版本不阻断合法候选分析；构建需要读取已发布基线证据时，该读取仍单独使用 ReadContext。补充/候选来源引用与正式 EvidenceRef 分型，不通过修改版本字段相互转换。空版本或经明确选择继续的空检索允许无证据输出，明确说明且不伪造引用。结构化或来源校验失败返回可诊断错误，不把半成品写为成功；此要求不改变 04-01 允许保存人工正文坏标记并提示问题的规则，越权证据读取/关联仍拒绝。

## 9. 本轮一致性验证入口

下列为后续实现验证要求，本次仅作设计复核，不代表自动化或端到端验收通过：

- 大纲仅编辑未确认、确认后再编辑：章节生成不能使用缺失/过期确认。
- 无 Run 上传及 active Run 期间上传：分别保持独立 supplement；跨 Project 写入拒绝，取消 Run 不误清理独立补充。
- 首次候选分析不要求已发布版本；过期/跨候选输入拒绝，Research/Review 不能读取未发布候选。
- 非 PDF 的 P0 资料从静态解析、处理确认、轻量分析、入库确认到发布后引用解析；补充失败、缺标题、解析不可用、重复资料、资料引用越权均有明确结果。doc/ppt 能力另须实际验证，单一格式通过不代表全部格式支持。
- P0 无输出倾向设置时普通回复正常；空证据明确提示、空列表合法、检索失败不冒充空检索。

本次修订 v1.7（2026-10-16）：同步学术引用、单一终稿、空版研究和论文/资料入库后只读服务边界；实现仍待细化。

本次修订 v1.8（2026-10-19）：明确端口依赖、ReadContext 与写资格分离、服务结果提案和应用提交职责；其余细化及实现仍待完成。

本次修订 v1.9（2026-10-19）：按 A01–A05 审计补齐大纲确认、独立补充暂存资格、分类输出校验、资料解析/分析/引用及 P1 输出倾向；保持 01–04 业务规则和公开协议不变，仅文档修订。

本次修订（2026-10-20）：登记08-01资料策略接缝和08已确认的Provider/凭据规则，不复制未决细节。

本次修订（2026-10-21）：同步资料策略Q1–Q4已确认决定与双向立即生效，详细规则在08-01维护；接口与运行验证未完成。

## A08 补充、处理与分析具名服务载荷

本节为尚未机器转写的内部类型唯一来源，公开投影见04-01的A08节；ID/Revision/Time沿04-01。字段均必填，只有明确null可空；联合只允许自身分支字段，空数组显式[]。引用不是外部可写对象或任意存储路径；ServiceProposal和执行上下文沿05-01，全部产物由Construction应用提交。

### A08.1 不可变输入与结果

`ScopedFileRef={project_id:ID,document_asset_id:ID,file_revision:Revision,content_digest:string}`，摘要由受控存储计算并校验实际字节，不接受客户端宣称；存储key/凭据不进入此投影。必须实际归属SupplementWriteScope或CandidateWriteScope，跨Project同哈希不能授权复用。

`PreparedTextRef={project_id:ID,text_revision_id:ID,content_digest:string,text_length_chars:integer,source_kind:full_text|abstract_fallback|user_text|material_text,document:ScopedFileRef|null,source:SourceRef,dependency_set:InputDependencySet,locations:PreparedTextLocations}`。文本长度按Unicode码点且>0；空白/无可用文本不能构造本类型；原文不内联。全文/资料文件提取必须有document；真实元数据摘要和已有合法人工替代文字允许null，均须可追溯来源及不可变内容修订。SourceRef来自04-01，依赖来自A06；引用不等于正式EvidenceRef、不绕过当前政策。user_text只消费既有受控输入能力，不新增上传文字端点。

`PreparedTextLocations={text_revision_id:ID,mapping_revision:Revision,segments:PreparedTextSegment[]}`；`PreparedTextSegment={segment_id:ID,start_offset:integer,end_offset:integer,source_locator:EvidenceLocator|null}`。segments非空、按start排序且不重叠，0≤start<end≤text_length_chars，offset均为当前文本Unicode码点；text_revision_id与正文引用一致，mapping_revision绑定文件/文本修订。source_locator复用04-01的已知联合，存在时必须可校验到同一document/来源；无法提供原页/段落时null，仍以规范文本范围定位，不虚构页码。至少覆盖全部将供后续切片/引用使用的可用文字；无对应映射的片段不得标为已验证定位。映射仅内部处理产物，正式EvidenceRef仍须发布版核验，不把暂存定位作为研究证据。

`SupplementInput`是封闭联合：`{kind:paper|material,channel:upload,file:ScopedFileRef}`或`{kind:paper|material,channel:identifier,source:NormalizedSupplementSource}`。`NormalizedSupplementSource={type:doi|arxiv_id|url,value:string}`，规则沿SupplementCreate（material仅url），服务端归一化但保存原提交值用于审计；归一化不证明来源可访问。接收阶段与准备阶段分别执行对应权限/安全核验。

`PrepareSupplementInput={execution:ExecutionContext,scope:SupplementWriteScope,input_revision:Revision,input:SupplementInput}`。execution、scope、实际请求及文件/来源修订必须一致；不含Run/KV前提。输入的kind与请求不一致拒绝；模型配置只在实际模型使用前校验，必要静态提取无需模型。

`SupplementPreparation={supplement_id:ID,input_revision:Revision,metadata_candidates:MetadataCandidate[],resolution_status:pending|resolved|ambiguous|failed,processing:ProcessingResult,diagnostics:PreparationDiagnostic[]}`。MetadataCandidate复用04-01，候选ID在同一请求/提取修订内稳定，重新提取不能把旧选择套到另一候选。结果不携带confirmation_status或可执行确认token。返回`Outcome<ServiceProposal<SupplementPreparation>>`：可诊断的解析失败可作为持久结果提案，授权/资格失效或不能可信提交则Err<ApplicationError>；应用据下表决定Task终态，不能仅以Outcome成功推断解析成功。

`ProcessingResult`为以下封闭联合（kind必须与输入一致）：

- `kind=paper`：`processing_revision:Revision,input_revision:Revision,document:ScopedFileRef|null,status:available|degraded|failed|unsupported,text:PreparedTextRef|null,diagnostics:PreparationDiagnostic[]`。
- `kind=material`：同名字段；status仅available|failed|unsupported，不允许degraded/abstract_fallback，available时text.source_kind=material_text。

available/degraded必须text非null；failed/unsupported必须text=null。result.document与text.document在有text时必须完全相等，所有project_id、文件修订及输入归属与scope/input_revision一致；摘要源内容修订也纳入冻结依赖。

processing_revision由应用为本次受控处理结果分配并持久绑定，服务端提案使用待提交修订，不能由模型/客户端选择或复用；相同持久结果重放复用该修订。paper available只对应full_text或既有合法user_text；degraded仅真实非空abstract_fallback，且诊断必须解释全文缺失/失败。failed/unsupported必须text=null，不能携带旧成功文本冒充本次结果。document可在失败时保留安全已收文件；其存在不表示文本可用。此结果只表达最终处理，pending/processing由应用基于受理/执行事实投影，不由解析器伪造。

`PreparationDiagnostic={category:acquisition|format|parse|metadata|analysis|integrity|policy,reason:PreparationReason,message:string,source:SourceRef|null,diagnostic_ref:ID|null}`，message为脱敏摘要；内部诊断ID不赋予公开读取权。PreparationReason闭合为source_unavailable、transient_failure、unsupported_format、parser_unavailable、corrupt_content、encrypted_content、safety_limit、no_usable_text、missing_title、ambiguous_metadata、metadata_conflict、invalid_analysis、input_changed、scope_invalid、dependency_invalid、material_restricted。category按实际阶段选择，reason保持精确；这不是新增PublicError码。

### A08.2 确定映射与提交

| 输入/事实 | 补充与处理投影 | 下一步及禁止副作用 |
| --- | --- | --- |
| 基础大小/格式/内容识别/安全接收失败 | 沿04-02的413/415/422；无成功受理句柄 | 无已确认资产、无业务解析链；临时字节按接收流程清理 |
| 已受理但尚未完成准备 | resolution=pending、processing=pending/processing | Task queued/running；不提前可确认/可检索 |
| 元数据唯一且足够、文本可用 | resolution=resolved；处理available或论文degraded | 准备Task可succeeded，但补充unconfirmed/pending；待原确认入口 |
| 多候选或关键元数据冲突 | resolution=ambiguous，候选及冲突具名 | 准备Task可succeeded但结果需人选/修正，不自动确认；旧选择修订拒绝 |
| 缺资料标题/论文关键元数据 | 保留草稿，resolution=ambiguous；无候选可保留[] | 原CorrectSupplement补足/选择后重新校验；缺标题不得confirm；LLM草稿仍未确认 |
| 深度获取/解析失败或资料无文本 | processing=failed、text=null；解析诊断持久保留；metadata能独立解决时resolution仍可resolved，否则failed | 准备Task=failed（若无其他致命失败，纯元数据歧义不计失败）；安全原文件仍可读，不能以resolution推导处理可用 |
| 论文PDF不可得/解析失败但有真实摘要 | processing=degraded、abstract_fallback及诊断；resolution独立判定 | Task可succeeded并展示降级；不生成摘要冒充来源，进入Run后仍须处理确认 |
| P0格式解析器未就绪 | processing=unsupported、reason=parser_unavailable；resolution独立判定 | Task=failed；记录P0实现缺口，不自动把doc/ppt移到P1、不伪造成功 |
| 已有Project成员重复/疑似重复 | 元数据解析结果不等于纳入决定；应用去重并形成既有决策 | 确认不创建重复活动成员，命中已发布成员只记备选来源/提示先移除；不改旧文件、分析或人工决定 |
| 已确认补充被Run选中并冻结 | inclusion processing，固定supplement确认修订及文件/文本/元数据修订；签发新CandidateWriteScope | 复用经验证不可变提取结果但不继承处理/分析确认；新补充默认下轮 |
| Run失败/取消，或补充被编辑/撤权 | 不将inclusion改为published；保留可追溯assigned_run及独立补充记录 | 迟到结果不得提交；不凭Task状态重新排队或删除独立补充，后续纳入遵循既有构建入口 |
| 正式发布 | 本次实际纳入成员才标published并记录version；重复/未纳入者不假报published | 只有Construction成功发布切换知识状态，解析服务无发布资格 |

PDF-only准备顺序沿FR-023与04-02 §4.2：先本地提取，有DOI/arXiv/可信标题等查询锚点才调用可用外部数据源；关键元数据仍不足时可在A06政策允许且配置可用后使用LLM草稿，Assessment见04-01。无锚点不盲发文件给外部源；无LLM资格仍可沿人工修正，不提升草稿为确认。

resolution与processing是两个轴：元数据resolved并不保证可用文本，failed解析也不抹除合法元数据。当前修正能解决的元数据缺口沿既有edit/confirm处理；需重新下载/解析的失败不新增P0专用重试入口。用户可沿既有SubmitSupplement/UploadSupplement重新上传或改用标识，形成独立新请求（新命令幂等身份），保留旧失败记录；同键重放旧请求不得伪造新尝试。应用TaskError按A04映射实际失败，公开失败data和安全诊断由04-01定义；不从内部reason拼HTTP错误码。

候选处理的DocumentProcessingState/MaterialProcessingState由应用保存ProcessingResult和输入/确认关系。手动Run先确认筛选，再核验或准备文本，确认包括失败/降级/不参与项的处理摘要，才允许可用文本候选进入分析；无文本候选可列不参与，但不得生成分析或进入向量/图谱。无检索revision_only按原依赖链不伪造筛选结果。独立补充的预提取不是Run处理确认，复用必须重验本次依赖。

### A08.3 分析输入、结构与修订

`CandidateAnalysisInput={execution:ExecutionContext,scope:CandidateWriteScope,candidate_id:ID,candidate_revision:Revision,kind:paper|material,processing_revision:Revision,processing_confirmation_revision:Revision,text:PreparedTextRef}`。所有引用匹配当前候选、冻结输入和有效处理确认；任务已锁定、文本来源/修订过时、无可用文本、资料范围不可用均不得派发模型。paper degraded可分析但始终保留摘要来源标记。

`CandidateAnalysisProposal={candidate_id:ID,candidate_revision:Revision,kind:paper|material,processing_revision:Revision,processing_confirmation_revision:Revision,text_revision_id:ID,analysis:PaperAnalysis|MaterialAnalysis,dependency_set:InputDependencySet}`，kind选择唯一analysis结构，字段/长度沿04-01。ServiceProposal包裹后由应用核验全部实际模型输入依赖；结构错误、跨kind字段、伪空成功和旧依据拒绝提交，不清除旧人工稿。PaperAnalysis和MaterialAnalysis各自全部字段必填；数组可为空但不能靠空数组/固定套话谎称提取到证据；没有依据的信息按现行内容要求明确说明，不编造方法/创新。模型不返回确认、发布或内容锁状态。

`AnalysisBasis={analysis_revision:Revision,processing_revision:Revision,processing_confirmation_revision:Revision,text_revision_id:ID,candidate_revision:Revision}`由应用在成功提交时登记；analysis_revision指本次分析内容修订，candidate_revision指该分析依据的候选修订，不能循环引用提交后的新候选修订。人工编辑形成新的分析修订并保留该处理依据；确认只接受当前有效分析。输入/处理变更使依赖结果和确认失效，保存旧稿用于原有诊断/保护不等于仍可用；入库确认受理后锁定。该结构不承诺P2完整历史版本功能。

### A08.4 解析能力与有限技术重试

格式清单唯一在04-02 §4.2；每一格式必须以真实解析样本验收，下面为适配器能力要求，不代表已经实现或选定库。

| P0格式组 | 静态提取与定位最低要求 | 必须验证的失败/安全样本 |
| --- | --- | --- |
| pdf | 论文/资料分型，提取实际文字、页或文本范围；保留文件修订 | 损坏/加密/扫描无文本；论文可真实摘要降级，资料无摘要分支；不以OCR已实现为前提 |
| doc/docx | 文档段落/表内可提取文字和稳定文本定位；旧二进制doc也必须验证 | 不可用转换器、损坏/加密；不执行宏/嵌入对象，不漏报P0能力缺口 |
| ppt/pptx | 幻灯片可提取文字按稳定顺序转换文本，并保存定位对应 | 无文本/损坏/加密、旧ppt能力；不播放或执行嵌入内容 |
| html/htm | 提取静态可见文本，保留原来源与文本范围 | 不运行脚本、不跟随页面嵌入资源或表单；无正文不能成功 |
| md/txt/rst | 按确定编码解码，保留段落/文本范围 | 解码失败、空白、恶意链接；不执行指令或抓外链 |
| yaml/yml/json/toml | 静态键值文本及稳定范围，保留实际内容 | 畸形结构、超限/别名膨胀；安全解析，不构造任意对象 |
| ipynb | 按cell顺序静态读取文本，明确代码/markdown/已保存输出来源 | 不运行cell；不把已保存输出当本次执行证据；忽略非文本并说明范围 |
| py及明确登记的其他代码 | 静态源文本和稳定范围 | 不执行/import代码、不安装依赖；二进制/解码失败拒绝 |

解析定位统一产出文本修订及已有EvidenceLocator可表达的page/paragraph/text_range，不借A08增加公开slide/cell locator枚举；原slide/cell到文本映射保留内部诊断，未来引用须经发布版转换。capabilities只报告实际实现，缺少任何基础P0格式仍是开放验收缺口。P1表格文件、P2多媒体不提前纳入。

技术重试由单一应用策略控制：同一task/attempt与不变输入/配置/资格，adapter不得嵌套无限重试。`PreparationRetryBudget={max_retries:integer,timeout_ms:integer}`由服务端部署配置冻结；max_retries有限且≥0、timeout_ms>0，具体值在实现/容量验证时登记，不设产品新门槛。仅确认可安全重试的瞬时获取/解析基础设施故障可用剩余预算；内容损坏/加密/无文本、格式不支持、缺解析器、模型结构无效、政策/权限/修订变化不能用原请求盲重试。外部结果或业务提交未知先核查持久结果，重复结果幂等提交；重试耗尽留安全诊断和失败，不新建用户恢复入口。每次尝试重验当前授权/资料使用，静态处理与模型使用按A06分流。


## A09 首版知识构建与Graph-RAG方案

本节是task012首版方案的维护位置，待人工审核，未实现/安装或性能验收。沿用A01/A02单部署、A06当前资料策略、A08最终文本与定位；H01由2026-10-23用户明确推进A09的指令恢复，仅P0知识构建/检索/存储选型。013为历史候选参考，不采纳其MemoryRetriever/user_memory，不引入跨Project知识或新的后台自动任务。

### A09.1 选择与兼容性

首版采用PostgreSQL 17 + pgvector 0.8维护线的精确余弦检索，图谱采用同库不可变节点/断言/证据关联表和有界邻接查询，原始文件与文本仍用A02本地FileStore。不直接嵌入第三方GraphRAG运行框架，不新建图数据库或远程向量服务。具体补丁、驱动、模型权重/运行库在实施锁定并做干净安装；本轮不下载模型、不连接业务库、不发真实推理请求。

| 候选 | 官方可核对能力 | 本项目适配判断与决定 |
| --- | --- | --- |
| PostgreSQL + pgvector + 关系图谱 | pgvector支持精确/近似距离检索；PostgreSQL支持递归查询/物化CTE | 采用。复用既有部署和事务，Project/视图约束可共同核验；图遍历需自建有界查询，精确扫描成本随允许集增长，容量待实测 |
| Qdrant + 独立图存储 | Qdrant提供payload过滤；向量过滤不自动提供图谱/业务事务 | 保留替换路径。本轮不增加服务；需额外证明不可变视图、读屏障、政策过滤与跨存储失败恢复 |
| Neo4j + 向量存储 | Cypher可表达图查询 | 保留替换路径。图语言不能代替项目版本/依赖规则，额外部署/权限/回收成本暂不引入 |
| LightRAG框架 | 双层图/文本检索与可替换存储 | 借鉴混合召回思路，不直接采纳其可变workspace生命周期；必须另证版本固定、受控写入及当前政策，框架workspace隔离不等于KnowledgeVersion隔离 |
| Microsoft GraphRAG | local结合实体图与原文，global使用社区报告 | 不作为首版执行框架。首版无全库社区报告预计算；广泛综述仍按已有Review流程多次同版检索，不把局部结果说成全库穷尽 |

查证于2026-10-23：[pgvector官方](https://github.com/pgvector/pgvector)、[PostgreSQL 17 CTE](https://www.postgresql.org/docs/17/queries-with.html)、[Qdrant filtering](https://qdrant.tech/documentation/search/filtering/)、[Neo4j Cypher](https://neo4j.com/docs/cypher-manual/current/queries/)、[LightRAG官方](https://github.com/HKUDS/LightRAG)、[GraphRAG查询](https://microsoft.github.io/graphrag/query/overview/)、[GraphRAG构建](https://microsoft.github.io/graphrag/index/default_dataflow/)。上述为能力依据，不是项目兼容/质量结论；表中采用判断为本项目工程推断。

嵌入初始profile选择本地`intfloat/multilingual-e5-base`：768维、query/passage前缀分别编码、平均池化及L2归一化；实现时严格使用`query: `和`passage: `，单输入含前缀/特殊token不得超过512。依据[作者模型卡](https://huggingface.co/intfloat/multilingual-e5-base)；多语种支持不证明本项目中英论文质量。模型MIT许可需随权重保留，下载/许可/准确revision及摘要由实施记录。本地EmbeddingProvider为独立受控进程端口，可使用单独锁定的推理环境，避免假定PyTorch等已兼容应用CPython 3.14；API/Worker仍保持A02环境。IPC只限本部署，启动检查实际模型/维度/摘要；不开放第三方托管推理、不自动回落到付费端点。它仍是Agent资料使用，每次嵌入/查询均按A06校验；本轮不分配GPU或承诺容量。

`EmbeddingProfile={profile_id,model_id,weights_revision,weights_digest,tokenizer_revision,dimension,normalization,distance,query_prefix,passage_prefix,runtime_digest}`，全必填；初值dimension=768、normalization=l2、distance=cosine。profile_id为全配置不可变摘要身份；零向量/NaN/维度错误拒绝。旧版本查询必须用原向量profile，权重不可用报依赖不可用，不用新模型查询旧向量。更换模型/分块/抽取规则只能创建新的构建产物和版本；保留旧读取依赖。该profile是部署能力而非新增用户模型选择字段，构建LLM抽取继续使用Run冻结的既有配置与当前凭据。

### A09.2 输入、分块与可定位证据

构建只消费本次允许纳入且按既定规则确认的paper/material最终文本、元数据及确认分析；输入分别沿CandidateWriteScope和受保护基线ReadContext，不把独立SupplementWriteScope当索引资格。失败/排除文本、版本外candidate_sources、会话偏好/草稿/Memory不进入知识索引。分析用于辅助抽取时记录实际依赖，但事实支持必须回到最终文本/具名元数据；不能把生成分析当来源事实。

`BuildProfile={embedding_profile_id,chunker_revision,extractor_schema_revision,extractor_prompt_revision,extractor_config_digest,graph_rules_revision,lexical_revision}`；`KnowledgeBuildInput={execution,scope,candidate_manifest_digest,input_revision,base_version_id:null|ID,build_profile,confirmed_inputs:BuildAssetInput[]}`。`BuildAssetInput={asset_kind:paper|material,asset_id,asset_revision,processing_revision,processing_confirmation_revision,text:PreparedTextRef,analysis_basis:AnalysisBasis|null,metadata_revision}`。BuildProfile身份为全部字段的规范化摘要；extractor_config_digest覆盖Run冻结的解析模型ID/可取得的模型修订、Provider配置修订及影响输出的参数，不含凭据；无法证明相同模型/config时禁止按旧profile复用。凭据轮换继续按08重解析，不把密钥持久化。字段全部必填，ID/Revision沿04；实际输入还含A06完整InputDependencySet，由应用核验，不信任模型宣称的输入集合。入库确认/合法纯移除路径沿原用例，不为被排除资产强造文本或分析。

首版chunker采用固定E5 tokenizer：按段落/句子边界优先，正文目标最多384 token，长段以token边界拆，前片尾最多64 token重叠；每次至少向前推进，空白不建片段。实际编码前再次计含前缀token，超过512拒绝/重分块，不静默截断。跨页可切分或分列原定位，不合并不同text_revision/asset；摘要始终标abstract_fallback。文本使用A08规范文本原样切片，不为了检索归一化改写引用文本；token偏移映射回Unicode码点，组合字符、中文、emoji必须测试。

`ChunkRecord={chunk_id,project_id,asset_kind,asset_id,asset_revision,text_revision_id,start_offset,end_offset,text_digest,source_kind,locator_segments:PreparedTextSegment[],dependency_set,chunker_revision}`；内容为规范文本[start,end)，start<end，所有locator须同文本且覆盖所用片段。应用分配ID，语义去重键为Project/资产修订/文本修订/范围/chunker，重复投递复用；重叠片段可分别保存但包装上下文时去重。来自同一字节的跨Project资产不能复用访问身份。已发布引用通过04-01 EvidenceRef分配版本专属身份，不能把chunk_id当通用公开证据ID。

### A09.3 最小图谱与来源

所有节点和边均属于Project及不可变graph_view；不能指向全局可变“最新图”。最小节点kind：paper、material、chunk、author、concept、method、dataset、keyword。paper关联全局PaperIdentity仅作身份辅助，访问仍限Project成员；作者按有依据标识或本来源名称区分，不因同名合并人物。无资料作者时不制造author。

边为类型化断言：chunk→paper/material的belongs_to；paper→author的authored_by；paper→paper的cites（目标必须也在当前清单，外部参考仅作来源文字）；paper/material/chunk→concept/keyword的mentions；paper/material→method的uses_method和→dataset的uses_dataset；concept/method/dataset之间related_to仅表示有原文支持的关联，不推断因果/支持结论。相似向量只用于排序，不能生成无依据related_to；结构归属边不是语义事实。

`GraphNodeRecord={node_id,project_id,graph_view_id,kind,identity_key,label_variants:GraphLabel[]}`；`GraphLabel={label,source:GraphSupport,dependency_set}`。`GraphAssertion={edge_id,project_id,graph_view_id,source_node_id,target_node_id,predicate,supports:GraphSupport[],confidence:number|null,extractor_revision,dependency_set}`。`GraphSupport`为`{kind:text,chunk_id,text_revision_id,start_offset,end_offset}`或`{kind:metadata,asset_id,asset_revision,metadata_revision,field}`。只支持上述闭合节点/谓词；每个语义断言至少一个实际支持，文字支持必须校验原文范围，元数据支持只允许authored_by、身份/已核验引用等可由对应字段直接得出的事实。confidence是抽取估计不等于事实可信或发布质量门槛；无法落地支持的提案拒绝，不补造引文。

LLM用固定schema从已允许chunk抽取实体/关系，输入限制每次单chunk及明确的本资产元数据，返回端点候选、谓词、原文span和估计值；应用校验span、类型和支持，保存抽取依赖。注入文字被当数据，不能执行SQL/工具、发布或指示访问其他来源。无实体/关系是合法空抽取，记录已执行且校验通过；错误/超时/无效结构是失败，不能拿空图冒充成功。结构节点/归属边始终由确定性映射产生。

身份按kind分别定义：paper/material使用Project内asset_id+asset_revision，不能按同标题合并；chunk使用chunk_id；author只在有同一已核验外部作者标识时合并，否则使用来源asset_revision+作者序号，两个同名作者保持独立。concept/method/dataset/keyword可按同Project+kind+规范化标签精确聚合（Unicode NFKC、casefold、压缩空白），这里只表示同标签召回分组，不是同名实体真实同一的断言；原文限定/来源保留，不能据此自动推理等价或因果。别名/同义词不由模糊LLM自动合并，保留多标签或独立节点及证据供后续评估。字典identity_key仅索引身份，标签及关系保留各来源断言，不存混合来源的无依赖总摘要。读取时先过滤每条label/assertion的完整依赖，再构造允许图；同节点的私人标签不使公共标签泄漏，也不能以一条公共支持洗白混合生成断言。一个断言由多个输入共同推导则按全输入依赖判定，只有分别生成的独立断言才可分别授权。无允许标签/支持的节点不可作为扩展桥梁或排名信号。

### A09.4 检索、图扩展与证据包

`KnowledgeQuery={read_context,query_text,query_profile_id,filters,context_budget}`。filters只收原操作允许的资产范围，不能自行指定另版/候选。先核验ReadContext/读取保护及当前资料政策，形成允许集A（清单成员+文本/标签/边完整依赖），之后再召回、排序和图遍历；政策拒绝必需历史与允许子集检索分别按A06处理。不能先全局top-k后过滤，不能通过受限节点度数/标签或边影响公共结果。每次真正读取/交付模型前按A06重验；若允许集变化，重新计算当前请求，有限重算耗尽安全失败，不能在旧top-k删掉几项当完整结果。

首版查询profile初值（工程参数，可版本化调优，不是产品质量门槛）：向量top40、词法top40、种子实体最多20、图深度最多2、总扩展边200、每节点最多20边、最终片段最多12。所有值必须有硬上限和诊断；环通过visited(node,depth/path)去重，排序稳定以ID作平局键。向量分支只对A内768维profile兼容行精确余弦排序；SQL先物化允许集合再ORDER/LIMIT，首版不建HNSW/IVFFlat近似索引。官方明确近似扫描后过滤可能不足额；以后ANN若引入需隔离分区与运行计划/召回对照，不能只加WHERE就宣称满足约束。

词法初值使用本地确定性规范化词项：Unicode字母数字词、汉字相邻二元组及单字，保留原chunk引用；按允许集中的词频/逆文档频率排序，不以全库私有统计影响分值。空词项分支返回空而非故障。向量与词法结果按RRF合并，rank从1起，score=sum(1/(60+rank))，稳定平局按chunk_id；种子实体来自前20命中chunk的允许mentions/uses等断言及查询词与允许标签精确匹配。

对这些种子在允许图上有界BFS；导航可沿允许谓词的入边/出边两个方向（含asset→method的反向邻接），方向只用于寻路，不把uses_method逆向解释成事实谓词。每条路径按实际访问顺序保存node_ids，edge_ids始终引用原有向断言，必须逐项校验相邻节点与原边端点，不要求原边方向与访问方向一致；禁止生成反向虚构断言。由共享方法可到达另一资产，再回取该资产的允许文本。回取每条路径关联的支持chunk，以及可用的邻居资产chunks；不以图摘要代替原文。元数据支持边可用于上述内部导航（同样核验字段与依赖），但首版不将这类路径作为模型可见关系证据；回取的文本项仍标graph通道，graph_paths可为空。仅当整条路径的所有边都有实际原文支持且其支持摘录均进入pack时才输出GraphPath。metadata不伪造chunk/excerpt或文字证据，内部诊断保留导航依据，公开资产信息沿原AssetView。每条路径的每一步及端点标签都须允许，同一版本/graph_view；不能穿过受限中间节点再返回公共尾端。图候选按最短跳数、种子rank、ID排序，作为第三路RRF合并；同资产/重叠范围按文本修订合并去重，保留所有实际路径来源。首版不依赖额外付费reranker；第三路无命中是合法，存储异常则整体retrieval=failed，不静默退为向量成功。可记录普通向量对照用于评测，但不以它冒充Graph-RAG运行完成。

`EvidencePack={project_id,knowledge_version_id,manifest_digest,query_profile_id,embedding_profile_id,outcome:found|empty,items:EvidenceItem[],material_use_notices:MaterialUseNotice[],trace:RetrievalTrace}`。失败返回既有Outcome Err<ApplicationError>而非empty包。`EvidenceItem={evidence:EvidenceRef,excerpt:string,source_kind,chunk_id,score:number,channels:(vector|lexical|graph)[],graph_paths:GraphPath[]}`；`GraphPath={graph_view_id,node_ids:ID[],edge_ids:ID[],support_evidence_ids:ID[]}`。所有支持证据必须是同版、当前允许且可解析的EvidenceRef；内部trace记录路径指向未入最终pack的支持时，交给模型的路径不得保留无正文依据的关系。EvidenceRef创建/保存由Research/Review应用经Knowledge校验，查询本身不写知识库。graph_paths是召回解释，不等于论断支持度认证；语义建议沿FR-033。

`RetrievalTrace={profile_id,vector_count,lexical_count,graph_seed_count,graph_edge_count,graph_chunk_count,selected_count,scope_limited:boolean,budget_limited:boolean,graph_status:completed,diagnostic_ref:ID|null}`，成功的计数均非负且只计允许范围；安全UI只投影必要提示，不公开受限来源数量、原query或内部诊断；运行耗时/模型token另记最小诊断。graph_status=completed包括合法零扩展，不包括异常跳过。

空清单：验证合法绑定/完整空视图后不必调用嵌入/LLM，返回empty；非空集允许子集为零时返回empty并MaterialUseNotice，不声称整个库无资料。真实检索失败不得进入Research无证据继续分支；Review低支撑/空结果不新增创建门槛，原流程不变。用户主动无证据继续只沿原确认入口。

### A09.5 上下文与失败边界

B=min(调用者明确预算,目标生成模型实际context_limit-output_reserve-system_and_required_history_tokens-current_query_and_tool_wrapper_tokens-safety_margin)，不得用字符数假装token数。current_query_and_tool_wrapper_tokens包括本轮完整问题、固定工具/消息模板；每项excerpt、引用标记和路径包装另外计入证据项成本，不能漏算或重复减。B≤0安全预算失败，不发超限请求。必需历史先按A06核验并计入，禁止静默裁剪受限历史；历史太长或无法证明模型/tokenizer能力时安全拒绝当前生成，沿已有错误/编辑入口，不自动总结或开Memory。embedding-query超512时按相同tokenizer分成连续窗口（每窗含prefix≤512），对归一化向量平均后再归一化，零结果拒绝；整条用户query保持原样计入生成预算，无偷偷截断。初始窗口上限16并随query_profile冻结，超限沿已有输入/配置错误，不裁掉后半问题。

按最终排序将完整证据项放入B，优先原文而非关系描述；一条图路径须连同所有实际支持摘录、引文元信息整体计费，装不下则丢整条路径并记录budget_limited，不能保留无支持图结论。对重叠片段合并后重新生成准确excerpt范围及EvidenceRef；不能继续用旧范围冒充裁切后的引用。B不足以容纳任何已召回证据时返回明确预算失败，不伪装empty；空库真正empty仍走原无证据规则。查询预算只限制本轮证据范围，不删知识资产，不是发布阈值。

缺模型/维度不符、向量或图不可用、引用校验失败、pin失效、输入依赖不完整分别记录内部错误并按A04已有安全语义映射；不新增公共码或自动恢复端点，不换最新版本，不以缓存掩盖损坏。新默认发布不影响本查询绑定；本次查询/派发必须可复现原profile及实际允许范围摘要。缓存键至少Project/版本清单/query摘要/两个profile/过滤/预算/当前政策和依赖判定身份，命中仍校验A06；扩权后旧子集缓存不能冒充完整范围。

### A09.6 构建、增量与完整就绪

CandidateWriteScope下先冻结BuildProfile，构建清单为完整目标集合。incremental复用仅限同Project、同不可变资产/文本/输入依赖、chunker/embedding/extractor配置完全相同且当前允许的产物；新增/删除后重建完整视图成员及图支持关联，删除最后支持的断言/标签从新视图消失，旧视图不变。rebuild对当前确认集合重新构建，不读写旧图，不解释为P0失败重跑。多来源混合派生物只有全部实际依赖和配置匹配才可复用；资料政策变化引起的限制不授权静默少建确认目标，必要输入受限则失败或走既有人工修订/排除路径。

空的目标集合必须仍有明确空manifest/vector_view/graph_view以及零计数证明；有意全移除发布空版，不能记no_change。非空文本没有抽取到语义边可成功，但要证明每个目标chunk的抽取任务成功且零结果已校验；模型失败不能伪造此状态。无变化必须完成全量清单、来源修订和配置/产物等价核验且有既有版；profile或可读产物变化不满足no_change。只零新增或查询失败不是无变化。

`KnowledgeReadyProof={project_id,run_id,attempt_id,candidate_revision,manifest_digest,build_profile_id,vector_view_id,graph_view_id,object_digests,counts,validated_at,read_barrier_id,dependency_set_digest}`。counts逐类包括清单资产/可用文本/chunk/vector/节点/断言/支持及成功抽取chunk，要求所有需嵌入chunk一对一向量、每个支持可解析、图端点及视图完整；不要求造非零语义边。object_digests与计数来自实际读回/校验而非Worker自报。就绪proof绑定完整文件/文本/向量/图及配置，不能只一个synced布尔；提交还需07原子重验，不是永久写授权。

发布流程：应用保存隔离产物→封存不可变视图→读回核验/保护→短事务重验Project/槽/attempt/当前政策/候选/确认/基线→原子登记版本、清单、默认指针、Run结果和outbox。不能在事务内LLM推理。取消/治理/编辑先提交则proof失效；响应丢失先查唯一发布决定；发布后依赖故障报同版不可用，不回退/拼接。具体首版存储约束见07 A09，实施测试见09 A09。

