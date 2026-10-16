# Agent & Knowledge Services 设计

文档版本：v1.7
更新日期：2026-10-16
依据文档：`00_layers.md`、`01_functional_requirements.md`

## 1. 设计目标

Agent 与 Knowledge 采用共层方案：二者都位于 Application Use Cases 之下、Infrastructure Adapters 之上。Agent 负责智能行为、生成和流程执行；Knowledge 负责论文资产、检索、版本、证据和可复用知识能力。

推荐依赖方向：

```text
Application Use Cases
  -> services/agents
      -> services/knowledge
          -> Infrastructure Adapters
```

Knowledge 不依赖具体 Agent。

## 2. Agent 服务边界

| Agent | 输入 | 输出 | 不负责 |
| --- | --- | --- | --- |
| Construction Agent | Project 主题、检索词、数据源策略、配置快照 | 候选论文、评分、AI 分析、入库建议、构建结果 | 直接绕过用例发布版本或发送邮件 |
| Research Agent | 用户消息、输出倾向、Knowledge Version、Graph-RAG 证据 | 流式回复、引用、总结草稿 | 修改 Project 知识库 |
| Review Agent | 综述主题、范围、大纲/章节状态、Knowledge Version、证据 | 大纲、章节、审查意见、终稿、参考文献 | 静默覆盖人工编辑内容 |

## 3. Knowledge 服务能力

| 能力 | 职责 | 关联 FR |
| --- | --- | --- |
| Paper Identity | 归一化 DOI/arXiv/URL/来源 ID，完成全局去重 | FR-022 |
| Project Library | 管理 ProjectPaper、有效性、评分、推送状态和 AI 分析 | FR-012, FR-026 |
| Document Assets | 管理 PDF、解析文本、摘要降级、文件访问引用 | FR-024 |
| Vector Index | 写入和查询向量索引，记录同步状态 | FR-026, FR-028 |
| Knowledge Graph | 构建论文、作者、关键词、概念、方法等节点边 | FR-026, FR-031 |
| Graph-RAG Retriever | 基于版本检索证据，返回引用定位 | FR-028, FR-032 |
| Knowledge Version | 发布、稳定绑定、版本变化与证据风险提示、新研究采用检查 | FR-018 |
| Citation & Evidence | 保存引用、证据片段、论文跳转和版本一致性 | FR-031, FR-033 |

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

## 4. Construction Pipeline

检索词管理支持 Project 主题生成建议词、用户编辑、检索词级数据源策略和自动更新开关。新生成或新增检索词默认 `auto_update_enabled=true`；用户后续修改自动更新开关是在该默认态上调整。手动 Run 使用本次 selected 检索词；自动 Run 使用 `auto_update_enabled=true` 的检索词。

多源检索支持 arXiv、OpenAlex、Semantic Scholar、ADS 和后续扩展 Provider。Provider 返回统一候选结构，不把 SDK 原始对象泄漏到应用层。数据源失败应分类为缺失配置、密钥失效、限流、连接失败、权限过期或 Provider 不可用。

去重、评分与筛选使用全局论文身份归一化。评分至少包含主题相关性、来源质量、时间新鲜度、摘要匹配度。候选论文可进入人工确认；自动 Run 只可按安全自动确认策略处理低风险项。

下载解析优先下载 PDF 并解析全文。PDF 缺失或解析失败时使用摘要降级，并记录原因。AI 分析输出一句话总结、亮点、相关性要点、方法与创新；结构化校验失败时不得写入为成功分析。

入库先在本轮隔离候选范围内写 ProjectPaper/ProjectMaterial 修订与文本资产，再写向量库和图谱同步项；不得覆盖已发布证据。发布 Knowledge Version 前校验关系数据、向量索引、图谱和引用定位完整可读。执行边界遵守 [知识库并行构建与版本更新领域附录](02-02_construction_versioning_appendix.md)；本文仍为待细化草案。

论文与 ProjectMaterial 入库确认受理前允许修改候选并使受影响处理失效，受理后锁定。已发布内容只读，不能通过元数据、文件、解析、分析或评分服务绕行修改；须先移除关联并发布，再显式重新导入，重做确认。重复命中当前成员只记备选来源，自动检索不恢复人工排除。筛选等待点返回检索仅追加确认词，来源、时间范围、预算与基线不变，使用剩余额度；服务不提供 P0 原 Run 失败恢复。

移除服务只处理已确认集合与修订，冲突执行终止仅按同次明示预览授权，后出现冲突交应用层重做预览；不得自主取消。有意全清空发布完整一致的空清单/索引/图谱，保留旧版依赖，不把失败或零新增当清空。

构建结果须区分 `published` 与 `no_change`，两者均为 Run 成功结果属性，不增加状态。只有完整核验既有版本且可读知识确无变化才可报告 no_change，不能用零新增、来源失败或未完成处理冒充；首次无已发布版本不适用。no_change 不发布、不切换默认版本、不发送升级提示或空邮件，候选按领域状态机收尾，恢复与清理仍引用 02-04。

## 5. Research Pipeline

- Session 创建时绑定已发布 Knowledge Version，采用新知识创建关联新 Session，不原地切换。
- 每轮用户消息根据输出倾向选择提示策略：创新、实验、总结。
- Graph-RAG 返回证据包，包括论文 ID、片段、定位、置信度和版本。
- 回复必须保存引用列表，引用可跳转到论文详情、PDF 或 Graph 节点。
- 若绑定版本缺失或不可访问，消息发送失败并展示修复路径。

## 6. Review Pipeline

- Review Run 创建时绑定已发布 Knowledge Version，采用新知识创建新版 Review，不在原 Run 混合版本。
- 大纲生成后必须经过用户确认或编辑。
- 章节生成携带绑定版本证据；空证据明确标注，不阻断对象创建或伪造来源。
- 按 FR-033 学术规范审查归属、支持关系和参考信息；机械检查引用链接及版本定位，语义判断只给建议，不计算覆盖率、豁免或 strict 通过分数。
- 终稿汇总生成单一完整 Markdown 正文；摘要、关键词及参考文献投影与正文同修订，无独立导出快照。accepted 当前稿保存后可 P0 下载，完成后只读；拒绝稿不由编辑复活。生成失败/迟到结果不覆盖人工稿。
- P2 版本管理可扩展只读快照、差异、回退和变更摘要。

## 7. Provider 抽象

Agent/Knowledge 只依赖抽象接口：`LlmProvider`、`PaperSearchProvider`、`PdfFetcher`、`PdfParser`、`EmbeddingProvider`、`VectorStore`、`GraphStore`、`FileStore`、`MailSender`。

Provider 必须返回统一错误分类和诊断元数据，不返回密钥明文、真实文件路径或不可序列化 SDK 对象。

## 8. 输出校验

所有 LLM 结构化输出必须校验 JSON/schema 可解析、必填字段存在、引用论文属于当前 Project 和绑定 Knowledge Version、生成内容没有覆盖受保护人工内容。失败时返回可诊断错误，不把半结构化结果当作成功。

本次修订 v1.7（2026-10-16）：同步学术引用、单一终稿、空版研究和论文/资料入库后只读服务边界；实现仍待细化。
