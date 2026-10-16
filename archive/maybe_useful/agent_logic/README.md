# Agent 片段存档

版本：v1.0；日期：2026-10-16；分类：**或许有用**。

此目录只是独立片段存档，不是新核心。仅使用 Python 标准库；不连接 ORM、HTTP、数据库、文件、配置、模型或状态机，不保留旧接口。没有复制整个旧模块、流水线或 YAML。未来是否采用及如何集成需要另行决定。

## 来源与实际拆分

来源定位为提取前工作区的路径及行号，历史行号不代表删除后仍有源文件。

| 审查编号 | 旧来源函数 | 留存函数 | 局部修正与舍弃 |
| --- | --- | --- | --- |
| AG-X01 | `backend/app/agents/base.py:120` `parse_json_response` | `decode_json_text` | 仅完整外围、独占行的 json/无语言 fence 可剥离；正文不改写；拒绝非标准 NaN/Infinity。不带 LLMClient、重试、配置或队列。 |
| AG-X02 | `backend/app/agents/construction/stage2_retrieval.py:148` `_parse_semantic_scholar` | `semantic_scholar_fields` | 只取单条记录字段映射；增加类型诊断、来源、Provider ID、批次、原始记录深拷贝及日期精度；不将年份伪造成 1 月 1 日，不将来源名伪造成 venue。不保留解析整个响应、请求、分页、去重和保存逻辑。 |
| AG-X03 | `backend/app/agents/deep_research/pipeline.py:154` `extract_referenced_papers` | `filter_citation_markers` | 首次出现顺序去重，返回允许与未知两组。不查询知识版本、不构造图谱、不读取历史对话。 |
| AG-X04 | `backend/app/services/construction_service.py:504` `_build_email_html` | `render_paper_email` | 仅表格、论文标题/作者/刊物/日期/摘要布局；所有插值 HTML 转义，长文本允许换行；不带查询、发送、状态回写和“已自动发送”声明。 |

## 输入输出和限制

- JSON 输入为字符串，输出为 Python JSON 值；非法输入抛错。没有 Schema、输入大小或嵌套深度限制，未来调用方须按业务验证，不能直接接受为模型执行结果。
- 字段映射输入为已解码的 JSON 对象及非空检索批次字符串，输出普通 dict。缺失/非法字段保留为空并给出 `warnings`；这不是可入库候选认证。支持有效日日期或整型年份精度，不做 DOI/arXiv 规范化，不改变 arXiv 版本号；保留 `raw_record` 可能占内存，不能直接对用户展示。未联网核验当前 Provider 规范。
- 引用过滤输入为文本和允许 ID 集合。允许集合应由未来调用方从绑定版本获得。本片段只识别单行方括号标记，普通 Markdown 标签也可能被列为未知；不提供 Markdown AST 或嵌套语法语义，不证明引用证据充分。
- 邮件布局输入为项目名和普通论文 dict 列表（`title`、`authors` 列表、`venue`、`publication_date`、`summary`）。输入应由调用方规范化。空列表仍可渲染，发送与否应另做判断。没有链接或可执行插值，没有邮件客户端兼容性/视觉验收；长文本测试仅证明内容保留与换行样式存在。

## 离线验证

仓库根目录执行：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s archive/maybe_useful/agent_logic -p 'test_*.py' -v
```

12 项测试覆盖普通/外围 fence/非法 JSON、正文 fence 保留、来源与原文独立快照、null/错误类型、日期精度/冲突、作者坏结构、引用顺序/未知 ID/精确匹配、邮件所有插值转义/空列表/超长文本。测试不调用真实服务，不导入旧项目，不读取凭据或业务数据。
