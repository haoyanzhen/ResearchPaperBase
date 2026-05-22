# Agent & Knowledge Services 设计

文档版本：v1.1  
更新日期：2026-05-20  
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
| Knowledge Version | 发布、读取、绑定、过期提示和刷新检查 | FR-018 |
| Citation & Evidence | 保存引用、证据片段、论文跳转和版本一致性 | FR-031, FR-033 |

## 4. Construction Pipeline

检索词管理支持 Project 主题生成建议词、用户编辑、启用/禁用、检索词级数据源策略和自动更新开关。手动 Run 使用本次 selected 检索词；自动 Run 使用 `auto_update_enabled=true` 的检索词。

多源检索支持 arXiv、OpenAlex、Semantic Scholar、ADS 和后续扩展 Provider。Provider 返回统一候选结构，不把 SDK 原始对象泄漏到应用层。数据源失败应分类为缺失配置、密钥失效、限流、连接失败、权限过期或 Provider 不可用。

去重、评分与筛选使用全局论文身份归一化。评分至少包含主题相关性、来源质量、时间新鲜度、摘要匹配度。候选论文可进入人工确认；自动 Run 只可按安全自动确认策略处理低风险项。

下载解析优先下载 PDF 并解析全文。PDF 缺失或解析失败时使用摘要降级，并记录原因。AI 分析输出一句话总结、亮点、相关性要点、方法与创新；结构化校验失败时不得写入为成功分析。

入库先写 ProjectPaper 与文本资产，再写向量库和图谱同步项。发布 Knowledge Version 前校验关系数据、向量索引、图谱和引用定位是否满足可读取条件。

## 5. Research Pipeline

- Session 创建时绑定 Knowledge Version。
- 每轮用户消息根据输出倾向选择提示策略：创新、实验、总结。
- Graph-RAG 返回证据包，包括论文 ID、片段、定位、置信度和版本。
- 回复必须保存引用列表，引用可跳转到论文详情、PDF 或 Graph 节点。
- 若绑定版本缺失或不可访问，消息发送失败并展示修复路径。

## 6. Review Pipeline

- Review Run 创建时绑定 Knowledge Version。
- 大纲生成后必须经过用户确认或编辑。
- 章节生成必须携带引用证据。
- 审查阶段检查章节结构、引用覆盖、重复内容、事实一致性和版本一致性。
- 终稿汇总生成摘要、关键词、参考文献和可导出正文。
- P2 版本管理可扩展只读快照、差异、回退和变更摘要。

## 7. Provider 抽象

Agent/Knowledge 只依赖抽象接口：`LlmProvider`、`PaperSearchProvider`、`PdfFetcher`、`PdfParser`、`EmbeddingProvider`、`VectorStore`、`GraphStore`、`FileStore`、`MailSender`。

Provider 必须返回统一错误分类和诊断元数据，不返回密钥明文、真实文件路径或不可序列化 SDK 对象。

## 8. 输出校验

所有 LLM 结构化输出必须校验 JSON/schema 可解析、必填字段存在、引用论文属于当前 Project 和绑定 Knowledge Version、生成内容没有覆盖受保护人工内容。失败时返回可诊断错误，不把半结构化结果当作成功。
