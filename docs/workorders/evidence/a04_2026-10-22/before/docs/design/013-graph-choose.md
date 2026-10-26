# Graph-RAG 与 Agent Memory 知识库选型报告

文档版本：v1.1  
更新日期：2026-06-01  
适用项目大版本：v1  
依据文档：`00_layers.md`、`06_agent_knowledge_services.md`、`07_data_persistence.md`

## 1. 目标

本文对当前 AI Agent / RAG 社区中较热门、且具备“复杂知识概念关联”和“大规模知识记忆能力”的知识库与记忆系统进行对比，为 Research Paper Base 的论文知识库、Graph-RAG 检索、深度研究对话和主题综述能力提供选型参考。

本文重点比较以下维度：

- 概念关联理解能力
- 长文本与大规模知识记忆能力
- 构建复杂程度
- 更新复杂程度
- 开源和部署难度

## 2. 候选系统概览

| 系统 | 类型 | 核心定位 | 典型适用场景 |
| --- | --- | --- | --- |
| Microsoft GraphRAG | Graph-RAG | 静态文档集合的实体、关系、社区摘要和全局/局部检索 | 大规模论文库、领域综述、组织知识库 |
| LightRAG | 轻量 Graph-RAG | 用轻量图结构增强文本索引与检索，并支持增量更新 | 快速 Graph-RAG 原型、本地实验、论文知识库 MVP |
| Graphiti / Zep | Temporal Knowledge Graph / Agent Memory | 面向动态事实和 Agent 记忆的时间感知知识图谱 | 用户记忆、研究兴趣演化、动态业务知识 |
| Cognee | AI Memory / Knowledge Graph | 多数据源转知识图谱，并通过 MCP 暴露给 Agent | 多 Agent 共享记忆、企业/研究资料知识层 |
| Mem0 | Agent Memory Layer | 用户偏好、历史事实、跨会话记忆和可选 graph memory | 个人助手、客服 Agent、用户画像 |
| Letta / MemGPT | Stateful Agent Memory | core / recall / archival 分层记忆和上下文管理 | 长期运行 Agent、上下文工程、持续学习 |

## 3. 对比结论

| 系统 | 概念关联理解 | 长文本记忆 | 构建复杂度 | 更新复杂度 | 开源/部署难度 | 对本项目的适配判断 |
| --- | --- | --- | --- | --- | --- | --- |
| Microsoft GraphRAG | 很强 | 强 | 高 | 高 | 中高 | 适合论文库、综述和领域概念图谱，但不宜作为第一版唯一方案 |
| LightRAG | 强 | 中强 | 中 | 中低 | 中 | 适合 Graph-RAG MVP 和增量构建探索 |
| Graphiti / Zep | 很强 | 强 | 中高 | 低中 | 中高 | 适合动态知识、观点演化和多用户研究兴趣记忆 |
| Cognee | 强 | 强 | 中 | 中 | 中 | 适合多 Agent 共享知识层和 MCP 接入 |
| Mem0 | 中强 | 强 | 低中 | 低 | 低中 | 适合用户偏好、阅读历史、每日推送个性化 |
| Letta / MemGPT | 中 | 很强 | 中 | 中 | 中 | 适合长期运行 Agent 的上下文与记忆管理，不是强图谱系统 |

## 4. 系统分析

### 4.1 Microsoft GraphRAG

Microsoft GraphRAG 的核心思想是避免只对文本 chunk 做向量检索，而是先从文档集合中抽取实体、关系和主题社区，形成知识图谱，再围绕图谱做检索和回答。

其典型流程包括：

1. 从文档中抽取实体和关系。
2. 构建实体关系图。
3. 使用社区发现算法聚合概念群。
4. 为社区生成摘要报告。
5. 查询时结合 local search、global search 和 DRIFT search。

它对复杂概念关联的理解能力最强，适合回答“某领域有哪些研究流派”“多个概念之间如何关联”“一批论文整体表达了什么趋势”等问题。缺点是构建链路重，LLM 抽取、图构建、社区发现和摘要生成都会带来较高成本。对于持续新增论文的项目，增量更新和版本发布也需要较强的工程约束。

对 Research Paper Base 的启示：

- 适合承担高质量 Knowledge Version 的离线图谱构建。
- 适合主题综述和深度研究中的全局问题。
- 不建议在 MVP 中直接采用完整重型流程作为唯一检索路径。

参考：

- https://github.com/microsoft/graphrag
- https://microsoft.github.io/graphrag/

### 4.2 LightRAG

LightRAG 的核心思想是将图结构纳入文本索引和检索流程，但整体比 Microsoft GraphRAG 更轻。它同时保留文本块检索和实体关系检索，并强调增量更新能力。

其典型流程包括：

1. 文档切分和向量化。
2. 抽取实体与关系。
3. 建立轻量图索引。
4. 查询时同时利用低层文本证据和高层实体关系。
5. 新数据进入时执行增量更新。

LightRAG 的概念关联能力弱于完整 GraphRAG，但构建和更新复杂度明显更低。它适合本项目第一阶段验证 Graph-RAG 能力，尤其适合在不引入过重图谱平台的情况下完成论文概念关系检索。

对 Research Paper Base 的启示：

- 适合作为 MVP Graph-RAG 的候选路线。
- 可与现有 Knowledge Version 发布机制结合。
- 后续可演进到更完整的 GraphRAG 或领域定制图谱。

参考：

- https://arxiv.org/abs/2410.05779
- https://github.com/HKUDS/LightRAG

### 4.3 Graphiti / Zep

Graphiti / Zep 的核心思想是面向 Agent 应用构建时间感知知识图谱。与静态文档 GraphRAG 不同，它把对话、JSON、业务事件和文本视为不断进入的 episode，从中抽取实体、关系、事实、来源和时间信息。

其典型能力包括：

- 时间感知实体关系建模。
- 语义检索、BM25、图遍历和 rerank 的混合检索。
- 支持事实变化、历史版本和动态上下文。
- 支持自定义实体类型，适合领域建模。

它很适合回答“这个用户之前关注什么主题”“某个研究方向后来如何变化”“某个事实是否被后续事件修正”等问题。相比 Microsoft GraphRAG，它更适合持续更新的数据；相比 Mem0，它对关系和时间的表达更强。

对 Research Paper Base 的启示：

- 适合记录用户研究兴趣、阅读历史和多用户观点演化。
- 适合补足论文库之外的动态知识，例如用户批注、研究计划、观点变更。
- 若用于论文图谱本体，仍需设计 Paper、Author、Concept、Method、Dataset 等自定义实体。

参考：

- https://help.getzep.com/graphiti/graphiti/overview
- https://help.getzep.com/graphiti/working-with-data/searching

### 4.4 Cognee

Cognee 的核心思想是把文档、聊天、数据库、API 数据等多源信息转成可查询的知识图谱，并通过 MCP 等接口提供给 Agent 读写。它更像面向 Agent 的持久 AI memory 平台，而不是单一 RAG 算法。

其典型流程包括：

1. Capture：接入文件、聊天、数据库或 API。
2. Model：抽取实体、关系、来源和权限。
3. Recall：通过 MCP、LangGraph、Claude Code 等入口给 Agent 使用。

Cognee 的优势是集成形态友好，适合多个 Agent 共享同一个 durable memory。它对复杂概念关联的表达强于普通向量库，但若需要高度定制的学术论文 ontology，仍需要额外建模。

对 Research Paper Base 的启示：

- 适合做 Agent 共享记忆层的参考方案。
- 适合连接外部工具和多 Agent 工作流。
- 如果项目重点是论文图谱质量，仍应保留项目内 Knowledge Graph 的权威建模。

参考：

- https://www.cognee.ai/
- https://docs.cognee.ai/cognee-mcp/mcp-overview

### 4.5 Mem0

Mem0 的核心思想是为 LLM 应用提供通用记忆层。它从对话和事件中提取可记忆事实，通过 user_id、agent_id 或 session 组织记忆，并使用向量检索和可选 graph memory 完成召回。

其典型能力包括：

- 用户偏好和历史事实保存。
- 跨会话记忆。
- 向量数据库存储。
- 可选实体关系图谱。
- 与 LangChain、CrewAI、Vercel AI SDK 等框架集成。

Mem0 的优势是接入快、API 简单，适合用户画像和个性化推送。它的不足是默认并不是严肃的学术知识图谱系统，对复杂概念网络、严格引用来源、事实版本和领域 ontology 的支持不如 GraphRAG / Graphiti。

对 Research Paper Base 的启示：

- 适合用户级记忆，例如研究偏好、订阅主题、阅读历史和每日推送反馈。
- 不适合作为论文知识库的唯一权威图谱。
- 若采用自托管模式，需要关注多租户隔离、安全审计和记忆删除能力。

参考：

- https://docs.mem0.ai/
- https://docs.mem0.ai/open-source/graph_memory/overview

### 4.6 Letta / MemGPT

Letta / MemGPT 的核心思想是把 Agent 记忆作为一等系统能力，通过分层记忆管理上下文。它通常区分 core memory、recall memory 和 archival memory。

其典型记忆层包括：

- Core Memory：始终进入上下文的核心信息，例如 persona、用户画像和任务状态。
- Recall Memory：历史对话记录，可搜索。
- Archival Memory：长期外部存储，用于保存大量长期知识。

Letta 的优势在于长期运行 Agent 的上下文工程能力，而不是知识图谱本身。它适合管理“什么信息应该进入上下文”“什么信息应该外存”“Agent 何时检索或编辑记忆”。如果需要复杂概念关系，通常还要接入外部向量库或图数据库。

对 Research Paper Base 的启示：

- 适合深度研究 Agent 的长期会话状态管理。
- 可用于管理 Research Session 的核心上下文、历史对话和外部知识召回。
- 论文概念图谱仍应由项目 Knowledge Graph 或 Graph-RAG 组件承担。

参考：

- https://docs.letta.com/concepts/memory-management
- https://github.com/letta-ai/letta

## 5. 推荐路线

Research Paper Base 的知识能力不应由单一系统承担。建议拆成三层：

| 层级 | 负责内容 | 推荐候选 |
| --- | --- | --- |
| 论文知识库层 | 论文、作者、概念、方法、数据集、引用、证据片段、Knowledge Version | LightRAG 起步，后续评估 Microsoft GraphRAG |
| 动态研究记忆层 | 用户研究兴趣、批注、观点演化、多用户共享上下文 | Graphiti / Zep 或 Cognee |
| Agent 会话记忆层 | Research Session 状态、用户偏好、推送反馈、长期上下文 | Mem0 或 Letta |

第一阶段建议：

1. 使用 PostgreSQL 保存权威业务事实和 Knowledge Version。
2. 使用 pgvector 或 Qdrant 保存论文片段向量。
3. 使用轻量图结构保存 Paper、Author、Concept、Method、Dataset、Citation 等实体关系。
4. Graph-RAG 检索先采用 LightRAG 式混合检索思想。
5. 用户级偏好和推送反馈暂存在项目数据库，后续再评估 Mem0 / Letta。

第二阶段建议：

1. 对已稳定的 Knowledge Version 引入更完整的 GraphRAG 离线构建。
2. 为多用户观点、批注和兴趣演化引入 temporal graph memory。
3. 将 Agent memory 与 Knowledge Graph 明确隔离，避免用户偏好污染论文事实图谱。

## 6. 项目内契约

为避免后续替换向量库、图数据库、GraphRAG 实现或长期记忆实现时影响 Research / Review / Construction 主流程，本项目应从第一版开始固定 GraphRAG-compatible 契约。Agent 只依赖项目内服务契约，不直接依赖 LightRAG、Graphiti、Mem0、Letta、Neo4j、Qdrant 等具体实现。

推荐边界：

```text
Construction / Research / Review Agent
  -> KnowledgeContextService
      -> VectorRetriever
      -> GraphRetriever
      -> MemoryRetriever
      -> EvidenceStore
```

第一版实现可以保持轻量：

```text
VectorRetriever = PostgreSQL + pgvector
GraphRetriever  = PostgreSQL kg_nodes / kg_edges
MemoryRetriever = PostgreSQL user_memory
EvidenceStore   = PostgreSQL + 文件系统
```

后续替换时只替换 adapter：

```text
VectorRetriever = Qdrant / Milvus / Weaviate
GraphRetriever  = LightRAG / Neo4j / Graphiti / Kuzu
MemoryRetriever = Mem0 / Letta / Graphiti
EvidenceStore   = 仍由项目保存权威证据、引用和版本边界
```

### 6.1 固定领域对象

无论底层实现如何变化，Agent 和应用用例层只认识以下项目内对象：

| 对象 | 职责 | 不应包含 |
| --- | --- | --- |
| KnowledgeVersion | 一次可读取知识库状态，绑定论文集合、向量索引、图谱引用和发布诊断 | 具体向量库或图数据库 SDK 对象 |
| EvidencePack | 一次检索返回给 Agent 的证据包 | 未经权限过滤的原文路径或跨 Project 数据 |
| EvidenceItem | 单条证据，通常对应 paper、chunk、score、来源和定位 | LLM 无来源推断出的裸结论 |
| Citation | 生成内容中可追溯的引用定位 | 只含标题、不含稳定 ID 的弱引用 |
| GraphNode | Paper、Author、Concept、Method、Dataset、Chunk 等节点 | 用户偏好和临时会话状态 |
| GraphEdge | cites、mentions、uses_method、uses_dataset、supports、related_to 等关系 | 无来源、无置信度、无版本边界的关系 |
| MemoryRecord | 用户级长期记忆，例如偏好、阅读反馈、研究兴趣 | 论文事实和项目权威结论 |
| RetrievalTrace | 检索过程记录，用于调试、评估和解释 | 密钥、真实文件路径或 provider 原始响应 |

### 6.2 统一检索结果契约

KnowledgeContextService 对 Agent 返回统一的 EvidencePack。示例结构如下：

```json
{
  "query": "GraphRAG 的评测方法有哪些？",
  "project_id": "project-001",
  "knowledge_version_id": "kv-012",
  "evidence": [
    {
      "paper_id": "paper-001",
      "chunk_id": "chunk-009",
      "text": "用于回答的证据片段",
      "score": 0.87,
      "source": "hybrid",
      "relations": [
        {
          "type": "uses_method",
          "target_type": "Method",
          "target_id": "method-graphrag",
          "confidence": 0.76,
          "source_chunk_id": "chunk-009"
        }
      ]
    }
  ],
  "trace": {
    "vector_hits": 12,
    "keyword_hits": 6,
    "graph_expansions": 8,
    "rerank_model": "configured-reranker"
  }
}
```

契约要求：

- `knowledge_version_id` 必须存在，Research Session 和 Review Run 创建后不得静默切换。
- `EvidenceItem` 必须可追溯到 `paper_id` 和 `chunk_id`，缺少来源时不得作为事实证据。
- `GraphEdge` 必须带来源、置信度和版本边界。
- `RetrievalTrace` 必须能说明向量召回、关键词召回、图扩展和 rerank 的数量或状态。
- 返回给 Agent 的证据必须已完成 Project 权限过滤。

### 6.3 引入 LightRAG 思想

本项目第一版不直接绑定某个 LightRAG 实现，但采纳其轻量混合检索思想：

```text
用户问题
  -> 查询改写 / 意图识别
  -> 低层检索：chunk 向量召回 + 关键词召回
  -> 高层检索：实体、概念、方法、数据集、引用关系扩展
  -> 证据合并、去重、rerank
  -> EvidencePack
  -> Agent 生成回答 / 综述章节
```

在数据形态上，第一版只维护必要轻图谱：

| 节点 | 说明 |
| --- | --- |
| Paper | 论文全局身份 |
| Author | 作者 |
| Concept | 研究概念、主题或问题 |
| Method | 方法、算法、框架 |
| Dataset | 数据集、benchmark、实验对象 |
| Venue | 期刊、会议或来源 |
| Chunk | 可引用文本片段 |

| 边 | 说明 |
| --- | --- |
| Paper cites Paper | 论文引用关系 |
| Paper authored_by Author | 作者关系 |
| Paper mentions Concept | 论文提及概念 |
| Paper uses_method Method | 论文使用或提出方法 |
| Paper uses_dataset Dataset | 论文使用数据集 |
| Chunk belongs_to Paper | 片段归属 |
| Chunk supports Concept | 片段支持某概念或论断 |
| Concept related_to Concept | 概念近邻或弱相关 |

边属性至少包含：

```text
knowledge_version_id
source_chunk_id
confidence
extractor
created_at
```

### 6.4 论文事实与用户记忆隔离

论文事实图谱和用户长期记忆必须分开治理：

```text
论文事实记忆 -> Knowledge Service
用户长期记忆 -> Memory Service
Agent 上下文 -> KnowledgeContextService 聚合二者
```

隔离规则：

- 论文事实图谱只保存可追溯论文、片段、概念和引用证据。
- 用户偏好、阅读历史、批注、推送反馈和研究兴趣写入 Memory Service。
- MemoryRecord 可以影响召回排序和推荐策略，但不得改写 KnowledgeVersion 中的论文事实。
- 多用户共享论文数据集时，用户记忆默认仍属于私人资产，除非后续明确设计共享观点或协作批注。

### 6.5 替换策略

底层实现替换时必须满足：

- 不改变 Research / Review / Construction Agent 的调用契约。
- 不改变 KnowledgeVersion、EvidencePack、Citation 的语义。
- 新实现必须能回填或兼容 RetrievalTrace。
- 迁移期间允许同一 KnowledgeVersion 绑定旧索引；新 KnowledgeVersion 使用新索引，避免静默改写旧会话证据。
- 替换前应准备一组固定问题集，对召回数量、引用覆盖、回答一致性和延迟进行对比。

## 7. 风险与未知

- 图谱质量高度依赖实体和关系抽取质量。论文领域需要自定义 ontology，否则图谱容易变成关键词网络。
- Graph-RAG 构建成本可能明显高于普通向量检索，需要在 Knowledge Version 发布前做成本和耗时控制。
- 动态 memory 与静态论文事实必须分离。用户观点、阅读偏好和论文事实不应写入同一个权威命名空间。
- 多用户共享数据需要明确权限边界。共享论文数据集可以复用，但用户批注、偏好和研究计划默认应属于私人资产。
- 开源 memory 系统仍在快速变化。生产使用前需要补安全审计、数据删除、备份恢复和多租户隔离验证。

## 8. 当前结论

对本项目而言，最稳妥的路线是：

1. MVP 不直接绑定重型 Microsoft GraphRAG，而是采用 LightRAG 式混合检索思路完成 Graph-RAG 基线。
2. 论文事实图谱由项目内 Knowledge Version 管理，作为 Research / Review 的权威知识边界。
3. 用户偏好、阅读历史和推送反馈作为独立 Agent memory，不与论文事实图谱混写。
4. 当论文库规模和综述质量要求上升后，再为稳定版本引入完整 GraphRAG 离线构建。
5. 若后续需要追踪观点和研究兴趣演化，优先评估 Graphiti / Zep 的 temporal knowledge graph。

## 9. 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
| --- | --- | --- | --- |
| v1.0 | 2026-06-01 | 初始新增 Graph-RAG 与 Agent Memory 知识库选型报告 | Codex |
| v1.1 | 2026-06-01 | 新增项目内 GraphRAG-compatible 契约，明确 LightRAG 式轻量混合检索思想和替换策略 | Codex |
