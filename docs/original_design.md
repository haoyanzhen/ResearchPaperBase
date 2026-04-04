# design for paper push agent

Author: haoyanzhen
Date:   2026-02-18

## agent逻辑设计

|阶段|执行方式|逻辑说明|
|---|---|---|
|检索词生成|内置调用|将用户课题输入给 LLM，一次性生成搜索关键词，并针对 arXiv、OpenAlex、Semantic Schola、astrophysics data system 生成多种高覆盖率的 Query 列表|
|检索与汇总|工具执行|顺序调用各数据库 API，将检索结果进行解析，得到每一篇论文的标题、作者、出版时间、期刊、摘要等内容，汇总到统一的 List 中|
|评分与筛选|顺序执行|将 List 中的所有文献的标题和摘要进行阅读，对其对研究方向的参考价值进行评分，评分>7则认为有效并筛选出来，对比数据库，得到新增论文|
|下载与解析|顺序执行|按照去重列表，逐一尝试下载 PDF 并解析，作为论文的文本信息。若失败则记录原因并以摘要为该论文的文本信息。|
|总结生成|内置调用|使用长文本模型对论文的文本信息进行一句话总结、亮点解析、相关性要点、技术方法与创新等信息提取|
|格式化与储存|工具执行|对数据库进行增量更新|
|邮件发送|工具执行|提取数据库中未发送过的论文数据，将其转化为 HTML 邮件发送到指定接收邮箱|

## prompt

检索词生成：

```plaintext
Role: 你是一位资深的学术情报专家，精通各个学科的索引逻辑与布尔检索语法。
Task: 请针对用户提供的研究课题，生成一组具备“高覆盖率”和“高查全率”的检索词列表。
Dimension: 请从以下四个维度进行发散：
   - 核心概念及其变体：包含学术全称、缩写、常用别名。
   - 技术路径与方法：实现该课题的具体工艺、算法或理论模型。
   - 关联属性与评价指标：课题关注的核心性能（如稳定性、效率、鲁棒性）。
   - 上位词与下位词：所属的更广领域和具体的细分分支。
Output Format:
请返回一个 JSON 格式，包含：
   - keywords: 按维度分类的关键词列表。
   - boolean_queries: 针对不同数据库（arXiv、OpenAlex、Semantic Schola、astrophysics data system）优化的布尔表达式字符串。
```

评分规则：

```text
Role: 你是一位严谨的学术预审编辑，擅长评估学术论文的潜在研究价值与工程落地可能性。
Task: 根据提供的论文元数据（标题、摘要、期刊、作者），从“参考价值”和“技术借鉴价值”两个维度进行深度打分。
Evaluation Criteria:
   1. 理论价值 (Reference score) [0-7分，最低0分]:
      - +2分：研究内容与目标课题有较大相关性
      - +2分：理论分析完备
      - +2分：逻辑验证或公式推导严谨
      - +1分：来自顶级期刊/会议
      - -1分：内容泛泛而谈，没有突出性成果或创新
      - -2分：东拉西扯，不深化研究问题，不提出新的设想
   2. 技术价值 (Technical score) [0-7分，最低0分]:
      - +2分：技术能够直接用于指定的方向
      - +2分：论证严密，在实际数据上的测试结果符合论证
      - +2分：有相关开源代码/软件
      - +1分：技术的改进思路对于指定方向有借鉴意义
      - -1分：缺乏细节，语焉不详
      - -2分：缺乏必要的科学考虑，方案不严谨
Input Data:
   - Title: [论文标题]
   - Abstract: [摘要文本]
   - Venue: [期刊/会议名称]
Output Format (Strict JSON):
   {
   "reference_score": int,
   "technical_score": int,
   "reasoning": "简短的一句话理由，说明给分的关键点",
   "decision": "Pass" 或 "Reject" (当任一分数 >= 5 或 总分 >= 7 时为 Pass)
   }
```

## 数据库

|字段名|类型|说明|
|---|---|---|
|DOI / ArXiv_ID|String (PK)|唯一标识符，用于绝对去重|
|Title / Authors|String|基础元数据|
|Pub_Date|Date|论文发布日期|
|Title|String|论文标题|
|Abstract|Text|原始摘要|
|AI_Analysis|JSON|存储亮点、大意、创新点等生成内容|
|Fetch_Date|DateTime|Agent 抓取并存入数据库的时间|
|Full_PDF_Path|String|本地 PDF 存储路径（若下载成功）|
|Full_Text_Path|String|本地文本信息存储路径|
|Push_Status|Boolean|是否已推送给用户|
|Addition_Info|String|额外信息|

## RAG(Retrieval Augmented Generation)

可建立两个数据库，一个是用于公用更新的关系型数据库，一个是用于作为LLM大模型读取数据库的向量数据库

|组件|存储内容|用途|
|---|---|---|
|关系型数据库 (SQLite)|DOI、标题、推送状态、抓取时间|负责 流程管理（去重、定时推送、状态追踪）|
|向量数据库 (ChromaDB)|论文全文/摘要的向量数据|负责 知识问答（语义搜索、纵向对比分析）|
