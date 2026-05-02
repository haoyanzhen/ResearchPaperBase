# 数据需求设计

> 分层定位：数据模型层、数据存储层、数据一致性说明。
> 本文承接从早期需求文档迁出的原“第 6 章 数据需求”，并按 `01_functional_requirements.md` 当前 FR 更新数据边界。
> 字段、索引、约束和删除语义的最终实现契约以 `06_data_model.sql` 为准；本文作为数据层解释性设计与多数据库协同说明。

## 6. 数据需求

### 6.0 当前数据层边界更新

本节承接 `01_functional_requirements.md` v1.19 与 `05_state_workflow.md` 的设计调整，用于说明当前数据层应支持的核心边界。现有表结构仍需在 `06_data_model.sql` 中进一步落地。

#### Project、Construction Workspace 与 Run/Session

- Project 是长期研究容器，应保存 Project 基础信息、所属用户、Project 状态和默认 `knowledge_version_id`。
- Project 状态应表达研究主题是否参与自动追踪，建议采用 `active`、`paused`、`archived`、`deleted`。
- Project 不应通过单一 `mode` 字段表达三模式互斥；Construction Run、Research Session、Review Run 应作为独立实例记录管理。
- 每个 Project 有且仅有一个 Construction Workspace，用于保存长期构建配置。
- Construction Workspace 保存检索词、检索词级数据源策略、自动更新开关和最近构建摘要，不生成 Knowledge Version。
- 每次手动或自动构建都应生成一条 Construction Run 记录。
- Construction Run 应保存启动时配置快照，包括 selected 检索词、检索词数据源策略、解析后的数据源、运行时配置来源和启动方式。
- Research Session 应保存其绑定的 `knowledge_version_id`、对话历史、引用和总结。
- Review Run 应保存其绑定的 `knowledge_version_id`、大纲、章节、审查记录和导出产物。

#### Knowledge Version 与稳定引用

- 每个成功 Construction Run 应生成新的 Knowledge Version。
- Knowledge Version 表示一次成功构建后可供 Research Session 和 Review Run 检索的知识库状态，包括关系型论文集合、向量索引和 Graph 状态。
- `paper_id` 必须作为全局稳定论文身份，跨 Knowledge Version 不变。
- Project 与 Paper 的关联 `id` 必须作为当前 Project 内稳定引用身份，跨 Knowledge Version 不变。
- Research 回复、Review 章节和导出产物中的论文引用应绑定稳定 Project-Paper 关联 `id` 和 `paper_id`。
- 只要稳定 ID 不变，旧文本引用不会因后续 Knowledge Version 更新而指向错误论文。
- 旧 Knowledge Version 的可清理条件由 `05_state_workflow.md` 定义；数据层必须保证清理旧版本不会破坏已完成文本中的稳定引用。

#### 增量构建数据原则

- 候选论文进入新增流水线前必须进行 identity resolution。
- 若候选论文命中已有 `paper_id`，应标记为已存在并从本次新增处理流水线中排除。
- 若候选论文已存在当前 Project-Paper 关联，关联 `id` 应保持不变。
- 未命中已有论文和当前 Project-Paper 关联的候选论文，才进入下载、解析、AI 分析、入库、向量化、Graph 更新和推送流程。
- 自动 Construction Run 只推送本次新增且有效的论文。

---

### 6.1 关系型数据库

#### 用户表 (users)

**说明**：存储系统用户基本信息，每个用户唯一。

| 字段名        | 类型      | 长度 | 必填 | 约束          | 说明                                    |
|---------------|-----------|------|------|---------------|-----------------------------------------|
| id            | VARCHAR   | 50   | 是   | PRIMARY KEY   | 用户唯一标识符                          |
| username      | VARCHAR   | 50   | 是   | UNIQUE        | 用户名，全局唯一                        |
| email         | VARCHAR   | 100  | 是   | UNIQUE        | 邮箱，全局唯一                          |
| password_hash | VARCHAR   | 255  | 是   | -             | 密码哈希值                              |
| is_admin      | BOOLEAN   | -    | 是   | DEFAULT FALSE | 是否为管理员；首位注册用户自动置为 TRUE |
| is_active     | BOOLEAN   | -    | 是   | DEFAULT TRUE  | 账号是否启用；管理员禁用后置为 FALSE    |
| created_at    | DATETIME  | -    | 是   | -             | 创建时间                                |
| updated_at    | DATETIME  | -    | 是   | -             | 最后更新时间                            |
| last_login_at | DATETIME  | -    | 否   | -             | 最后登录时间                            |

**索引**：
- PRIMARY KEY (id)
- UNIQUE INDEX idx_username (username)
- UNIQUE INDEX idx_email (email)
- INDEX idx_is_admin (is_admin)
- INDEX idx_created_at (created_at)

---

#### 用户配置表 (user_configs)

**说明**：存储用户相关的配置信息，包括系统默认配置和用户自定义配置。每一行保存一个配置项，每个配置项唯一。

| 字段名            | 类型      | 长度 | 必填 | 约束           | 说明                                                        |
|-------------------|-----------|------|------|----------------|-------------------------------------------------------------|
| id                | VARCHAR   | 50   | 是   | PRIMARY KEY    | 配置唯一标识符                                              |
| user_id           | VARCHAR   | 50   | 是   | FOREIGN KEY    | 用户ID，关联users表                                         |
| config_name       | VARCHAR   | 100  | 是   | -              | 配置名称（如：llm.model、database.arxiv.endpoint等）         |
| config_value      | TEXT      | -    | 是   | -              | 配置值（JSON格式存储复杂配置）                              |
| is_system_default | BOOLEAN   | -    | 是   | DEFAULT FALSE  | 是否为系统默认配置                                         |
| created_at        | DATETIME  | -    | 是   | -              | 创建时间                                                    |
| updated_at        | DATETIME  | -    | 是   | -              | 最后更新时间                                                |

**约束**：
- PRIMARY KEY (id)
- FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE

**配置示例**：
```
config_name: llm.provider.deepseek.url
config_value: {"url":"https://api.deepseek.com/v1", "api_key": "***"}

config_name: email.smtp.host
config_value: "smtp.gmail.com"

config_name: email.recipients
config_value: ["user1@example.com", "user2@example.com"]
```

---

#### 系统配置表 (system_configs)

**说明**：存储管理员设置的系统级全局配置（FR-006）。与 `user_configs` 结构对应，区别在于本表无 `user_id`，配置对所有用户生效。普通用户无个人配置时，系统回落读取本表同名配置项。

| 字段名            | 类型     | 长度 | 必填 | 约束          | 说明                                              |
|-------------------|----------|------|------|---------------|---------------------------------------------------|
| id                | VARCHAR  | 50   | 是   | PRIMARY KEY   | 配置唯一标识符                                    |
| config_name       | VARCHAR  | 100  | 是   | UNIQUE        | 配置名称（与 user_configs.config_name 命名一致）  |
| config_value      | TEXT     | -    | 是   | -             | 配置值（JSON 格式存储复杂配置）                   |
| description       | VARCHAR  | 255  | 否   | -             | 配置项说明（供管理员界面展示）                    |
| updated_by        | VARCHAR  | 50   | 否   | FOREIGN KEY   | 最后修改的管理员用户 ID，关联 users 表            |
| created_at        | DATETIME | -    | 是   | -             | 创建时间                                          |
| updated_at        | DATETIME | -    | 是   | -             | 最后更新时间                                      |

**约束**：
- PRIMARY KEY (id)
- UNIQUE INDEX idx_config_name (config_name)
- FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL

**配置示例**：

```
config_name: system.llm.default
config_value: {"provider":"openai","model":"gpt-4o","api_key":"***","base_url":"https://api.openai.com/v1","priority":1}

config_name: system.database.arxiv
config_value: {"endpoint":"https://export.arxiv.org/api/query","api_key":null,"rate_limit":3}

config_name: system.database.semantic_scholar
config_value: {"endpoint":"https://api.semanticscholar.org/graph/v1","api_key":"***","rate_limit":100}
```

---

#### 研究主题表 (projects)

**说明**：存储用户创建的各个研究主题（Project）及其可用性状态，每个研究主题唯一。这是系统的核心实体，所有功能都围绕研究主题展开。Project 不保存唯一当前模式，也不保存某个 Agent 的运行状态。

| 字段名        | 类型      | 长度 | 必填 | 约束                    | 说明                                                      |
|---------------|-----------|------|------|-------------------------|-----------------------------------------------------------|
| id            | VARCHAR   | 50   | 是   | PRIMARY KEY             | 研究主题唯一标识符（project_id）                          |
| user_id       | VARCHAR   | 50   | 是   | FOREIGN KEY             | 用户ID，关联users表                                       |
| name          | VARCHAR   | 255  | 是   | -                       | 研究主题名称                                              |
| description   | TEXT      | -    | 否   | -                       | 研究主题描述                                              |
| status        | VARCHAR   | 20   | 是   | DEFAULT 'active'        | Project 可用性状态（active/paused/archived/deleted）      |
| default_knowledge_version_id | VARCHAR | 50 | 否 | FOREIGN KEY | 当前 Project 默认知识库版本 ID                            |
| total_papers  | INTEGER   | -    | -    | DEFAULT 0               | 总论文数                                                  |
| valid_papers  | INTEGER   | -    | -    | DEFAULT 0               | 有效论文数                                                |
| auto_push     | BOOLEAN   | -    | 否   | DEPRECATED              | 旧设计字段；自动更新应迁移到 Construction Workspace 检索词级配置 |
| push_interval | TINYINT   | -    | 否   | DEPRECATED              | 旧设计字段；调度周期应迁移到系统级 scheduler 配置         |
| last_push_at  | DATETIME  | -    | 否   | -                       | 上次成功推送时间                                          |
| next_push_at  | DATETIME  | -    | 否   | -                       | 下次计划推送时间（由调度器写入）                          |
| created_at    | DATETIME  | -    | 是   | -                       | 创建时间                                                  |
| updated_at    | DATETIME  | -    | 是   | -                       | 最后更新时间                                              |

**约束**：
- PRIMARY KEY (id)
- FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
- INDEX idx_user_id (user_id)
- INDEX idx_status (status)
- INDEX idx_default_knowledge_version_id (default_knowledge_version_id)
- INDEX idx_next_push_at (next_push_at)
- INDEX idx_created_at (created_at)

**设计说明**：

- 以 project_id 为核心标识符，所有相关数据表都通过 project_id 关联
- Project 不再使用 `mode` 字段作为三模式互斥权威来源。
- 当前执行阶段**不在本表存储**，应通过查询 Construction Run、Research Session、Review Run 及其步骤记录获取。
- `valid_papers` 为 0 或不存在可用 Knowledge Version 时，不允许新建 Research Session 或 Review Run。
- 自动更新是否执行由 Project `status`、系统级 scheduler 配置、Construction Workspace 检索词级 `auto_update_enabled` 共同决定。

**`status` 字段状态说明与触发条件**：

| 状态 | 含义 | 触发条件 |
| --- | --- | --- |
| `active` | Project 处于活跃研究状态 | Project 创建时初始值；用户恢复自动追踪时写入 |
| `paused` | Project 暂停自动追踪 | 用户暂停 Project 自动追踪时写入 |
| `archived` | Project 已归档保留 | 用户主动归档 Project 时写入 |
| `deleted` | Project 删除态 | 用户删除 Project 或执行软删除时写入 |

> **注意**：Construction Run、Research Session、Review Run 的运行中、等待、失败、取消等状态不写入 Project `status`，应由独立实例记录维护。

---

#### 检索词表 (keywords)

**说明**：存储每个研究主题的检索词，每一行为一个检索词，支持多个数据库的布尔表达式。

| 字段名 | 类型 | 长度 | 必填 | 约束 | 说明 |
|---------------------|-----------|------|------|----------------|-----------------------------------------------------------|
| id                  | VARCHAR   | 50   | 是   | PRIMARY KEY    | 检索词唯一标识符                                          |
| project_id          | VARCHAR   | 50   | 是   | FOREIGN KEY    | 研究主题ID，关联projects表                               |
| search_word         | VARCHAR   | 500  | 是   | -              | 检索词                                                    |
| boolean_expressions | JSON      | -    | -    | -              | 各数据库的布尔表达式                                      |
| searched_papers_arxiv           | TINYINT   | -    | -    | DEFAULT 0      | 在arXiv检索到的论文数量                             |
| searched_papers_openalex        | TINYINT   | -    | -    | DEFAULT 0      | 在openalex检索到的论文数量                          |
| searched_papers_semanticscholar | TINYINT   | -    | -    | DEFAULT 0      | 在semanticscholar检索到的论文数量                   |
| searched_papers_ads | TINYINT   | -    | -    | DEFAULT 0      | 在ADS检索到的论文数量                                     |
| searched_papers_total | TINYINT   | -    | -    | DEFAULT 0      | 总共检索到的论文数量                                     |
| is_searched         | BOOLEAN   | -    | -    | DEFAULT FALSE  | 是否执行过搜索                                            |
| is_selected         | BOOLEAN   | -    | -    | DEFAULT TRUE   | 是否被选中使用                                            |
| created_at          | DATETIME  | -    | 是   | -              | 创建时间                                                  |
| last_search_at      | DATETIME  | -    | 是   | -              | 最后搜索时间                                              |

**约束**：
- PRIMARY KEY (id)
- FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
- INDEX idx_project_id (project_id)

**boolean_expressions示例**：
```json
{
  "arxiv": "ti:deep learning AND abs:medical imaging",
  "openalex": "(deep learning OR CNN) AND medical imaging",
  "semantic_scholar": "deep learning AND medical imaging",
  "ads": "deep learning AND medical AND imaging"
}
```

---

#### 论文表 (papers)

**说明**：存储所有论文的元数据，每篇论文唯一，支持多课题关联。

| 字段名 | 类型 | 长度 | 必填 | 约束 | 说明 |
|-------------------|-----------|------|------|----------------|-----------------------------------------------------------|
| id                | VARCHAR   | 50   | 是   | PRIMARY KEY    | 论文唯一标识符                                            |
| doi               | VARCHAR   | 100  | 否   | UNIQUE         | DOI，数字对象标识符                                       |
| arxiv_id          | VARCHAR   | 50   | 否   | UNIQUE         | ArXiv ID                                                  |
| title             | TEXT      | -    | 是   | UNIQUE         | 论文标题（小写格式）                                        |
| authors           | TEXT      | -    | 否   | -              | 作者列表（JSON格式）                                       |
| pub_date          | DATE      | -    | 否   | -              | 发布日期                                                  |
| venue             | VARCHAR   | 200  | 否   | -              | 期刊/会议名称                                             |
| abstract          | TEXT      | -    | 否   | -              | 摘要                                                      |
| source            | VARCHAR   | 50   | 否   | -              | 检索来源（arxiv/openalex/semantic_scholar/ads）            |
| retrieved_at      | DATETIME  | -    | 是   | -              | 检索时间                                                  |
| download_status   | VARCHAR   | 20   | -    | DEFAULT "not_downloaded" | 下载状态（not_downloaded/success/failed）       |
| pdf_path          | VARCHAR   | 500  | 否   | -              | PDF文件本地路径                                           |
| text_path         | VARCHAR   | 500  | 否   | -              | 文本文件本地路径                                          |
| download_error    | TEXT      | -    | 否   | -              | 下载错误信息                                              |
| ai_analysis_status| VARCHAR   | 20   | -    | DEFAULT "not_analyzed" | AI分析状态（not_analyzed/success/failed）         |
| ai_analysis       | JSON      | -    | 否   | -              | AI分析结果                                                |
| created_at        | DATETIME  | -    | 是   | -              | 创建时间                                                  |
| updated_at        | DATETIME  | -    | 是   | -              | 最后更新时间                                              |

**约束**：
- PRIMARY KEY (id)
- UNIQUE INDEX idx_doi (doi)
- UNIQUE INDEX idx_arxiv_id (arxiv_id)
- UNIQUE INDEX idx_title (title)
- INDEX idx_pub_date (pub_date)
- INDEX idx_source (source)

---

#### 研究主题-论文关联表 (project_paper_relations)

**说明**：保存研究主题与论文的关联关系以及论文在该研究主题中的评分和状态。

| 字段名 | 类型 | 长度 | 必填 | 约束 | 说明 |
|-----------------|-----------|------|------|----------------|-----------------------------------------------------------|
| id               | VARCHAR   | 50   | 是   | PRIMARY KEY    | 关联唯一标识符                                            |
| project_id       | VARCHAR   | 50   | 是   | FOREIGN KEY    | 研究主题ID，关联projects表                                |
| paper_id         | VARCHAR   | 50   | 是   | FOREIGN KEY    | 论文ID，关联papers表                                     |
| reference_score  | INTEGER   | -    | -    | -              | 参考价值评分（0-5）                                       |
| technical_score  | INTEGER   | -    | -    | -              | 技术价值评分（0-5）                                       |
| total_score      | INTEGER   | -    | -    | -              | 总分（0-10）                                             |
| scoring_reason   | TEXT      | -    | 否   | -              | 评分理由                                                  |
| is_valid         | BOOLEAN   | -    | -    | DEFAULT FALSE  | 是否有效（总分≥7）；评分完成后显式置为TRUE                |
| push_status      | BOOLEAN   | -    | -    | DEFAULT FALSE  | 是否已推送给该研究主题                                    |
| pushed_at        | DATETIME  | -    | 否   | -              | 推送时间                                                  |
| created_at       | DATETIME  | -    | 是   | -              | 创建时间                                                  |
| updated_at       | DATETIME  | -    | 是   | -              | 最后更新时间                                              |

**约束**：
- PRIMARY KEY (id)
- FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
- FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
- UNIQUE INDEX idx_project_paper (project_id, paper_id)
- INDEX idx_project_id (project_id)
- INDEX idx_paper_id (paper_id)
- INDEX idx_is_valid (is_valid)
- INDEX idx_push_status (push_status)

---

#### 阶段记录表 (stage_records)

**说明**：记录课题在构建模式和综述模式各执行阶段的详细信息。深度研究模式不使用此表（无固定阶段流程）。`mode` 字段区分阶段编号的语义：构建模式共7个阶段，综述模式共5个阶段。

| 字段名 | 类型 | 长度 | 必填 | 约束 | 说明 |
|--------------|-----------|------|------|----------------|-----------------------------------------------------------|
| id           | VARCHAR   | 50   | 是   | PRIMARY KEY    | 记录唯一标识符                                            |
| project_id   | VARCHAR   | 50   | 是   | FOREIGN KEY    | 课题ID，关联projects表                                    |
| mode         | VARCHAR   | 20   | 是   | -              | 所属模式（construction/review）                           |
| stage        | TINYINT   | -    | 是   | -              | 执行阶段（构建模式：1-7；综述模式：1-5）                  |
| status       | VARCHAR   | 20   | 是   | -              | 状态（running/paused/completed/failed）                   |
| started_at   | DATETIME  | -    | 是   | -              | 开始时间                                                  |
| completed_at | DATETIME  | -    | 否   | -              | 完成时间                                                  |
| paused_at    | DATETIME  | -    | 否   | -              | 暂停时间                                                  |
| resumed_at   | DATETIME  | -    | 否   | -              | 恢复时间                                                  |
| failed_at    | DATETIME  | -    | 否   | -              | 失败时间                                                  |
| result       | JSON      | -    | 否   | -              | 阶段结果数据                                              |
| error        | TEXT      | -    | 否   | -              | 错误信息                                                  |
| user_actions | JSON      | -    | 否   | -              | 用户操作记录（编辑/跳过/重新执行等）                      |
| created_at   | DATETIME  | -    | 是   | -              | 创建时间                                                  |

**约束**：
- PRIMARY KEY (id)
- FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
- INDEX idx_project_id (project_id)
- INDEX idx_mode (mode)
- INDEX idx_stage (stage)
- INDEX idx_status (status)

**构建模式阶段编号说明**（mode = 'construction'）：

| stage | 含义 |
|-------|------|
| 1 | 检索词生成 |
| 2 | 检索与汇总 |
| 3 | 评分与筛选 |
| 4 | 下载与解析 |
| 5 | 总结生成 |
| 6 | 格式化与储存 |
| 7 | 邮件发送（全自动，无用户交互暂停） |

**综述模式阶段编号说明**（mode = 'review'）：

| stage | 含义 |
|-------|------|
| 1 | 扩写课题内容并通过用户确认 |
| 2 | 生成综述架构并通过用户修改 |
| 3 | 撰写章节内容 |
| 4 | 自动审查迭代 |
| 5 | 汇总成综述文章 |

---

#### 深度研究对话表 (research_dialogues)

**说明**：存储深度研究模式下的对话会话列表。每次用户开启一次主题性探讨即创建一条记录。一个课题可包含多个对话会话，每个会话的完整对话历史在 `dialogue_turns` 表中以轮次为单位存储。

| 字段名 | 类型 | 长度 | 必填 | 约束 | 说明 |
|-----------------|-----------|------|------|----------------|-----------------------------------------------------------|
| id              | VARCHAR   | 50   | 是   | PRIMARY KEY    | 对话会话唯一标识符                                        |
| project_id      | VARCHAR   | 50   | 是   | FOREIGN KEY    | 课题ID，关联projects表                                    |
| title           | VARCHAR   | 255  | 否   | -              | 对话标题（用户自定义或由首轮用户输入自动生成）            |
| status          | VARCHAR   | 20   | 是   | DEFAULT 'active' | 状态（active/archived）                                 |
| turn_count      | INTEGER   | -    | 是   | DEFAULT 0      | 已完成的对话轮次数                                        |
| summary         | TEXT      | -    | 否   | -              | Agent自动生成的对话摘要                                   |
| tags            | JSON      | -    | 否   | -              | 用户标签列表（JSON数组）                                  |
| created_at      | DATETIME  | -    | 是   | -              | 创建时间                                                  |
| updated_at      | DATETIME  | -    | 是   | -              | 最后更新时间                                              |
| last_active_at  | DATETIME  | -    | 是   | -              | 最后活跃时间                                              |

**约束**：
- PRIMARY KEY (id)
- FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
- INDEX idx_project_id (project_id)
- INDEX idx_status (status)
- INDEX idx_last_active_at (last_active_at)

---

#### 对话轮次表 (dialogue_turns)

**说明**：以轮次为单位完整记录对话历史，每行对应一轮对话（用户发言一次 + Agent 回复一次）。`turn_index` 从 1 开始自增，保证轮次顺序可还原。`referenced_papers` 和 `graph_nodes_used` 属于 Agent 回复的元数据。

| 字段名 | 类型 | 长度 | 必填 | 约束 | 说明 |
|--------------------|-----------|------|------|--------------|-----------------------------------------------------------|
| id                 | VARCHAR   | 50   | 是   | PRIMARY KEY  | 轮次唯一标识符                                            |
| dialogue_id        | VARCHAR   | 50   | 是   | FOREIGN KEY  | 对话会话ID，关联research_dialogues表                      |
| project_id         | VARCHAR   | 50   | 是   | FOREIGN KEY  | 课题ID，关联projects表（冗余存储，便于直接查询）          |
| turn_index         | INTEGER   | -    | 是   | -            | 轮次序号（会话内从1开始自增）                             |
| sub_mode           | VARCHAR   | 20   | 是   | -            | 本轮采用的子模式（theory/technical/experiment）         |
| user_content       | TEXT      | -    | 是   | -            | 用户输入的原始内容                                        |
| assistant_content  | TEXT      | -    | 是   | -            | Agent 回复的原始内容                                      |
| referenced_papers  | JSON      | -    | 否   | -            | Agent回复引用的论文ID列表（JSON数组）                     |
| graph_nodes_used   | JSON      | -    | 否   | -            | Graph-RAG检索命中的知识图谱节点ID列表                     |
| input_tokens       | INTEGER   | -    | 否   | -            | 用户输入token数（用于成本追踪）                           |
| output_tokens      | INTEGER   | -    | 否   | -            | Agent回复token数（用于成本追踪）                          |
| created_at         | DATETIME  | -    | 是   | -            | 本轮创建时间（即用户发送消息的时间）                      |

**约束**：
- PRIMARY KEY (id)
- FOREIGN KEY (dialogue_id) REFERENCES research_dialogues(id) ON DELETE CASCADE
- FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
- UNIQUE INDEX idx_dialogue_turn (dialogue_id, turn_index)
- INDEX idx_dialogue_id (dialogue_id)
- INDEX idx_project_id (project_id)
- INDEX idx_created_at (created_at)

---

#### 综述架构表 (review_outlines)

**说明**：存储综述模式下生成的综述架构版本。每次用户发起新的综述流程或手动创建版本时生成一条记录，通过版本号追踪修改历史。`status` 为 `confirmed` 时，对应的章节撰写才可以开始。

| 字段名 | 类型 | 长度 | 必填 | 约束 | 说明 |
|---------------------|-----------|------|------|----------------|-----------------------------------------------------------|
| id                  | VARCHAR   | 50   | 是   | PRIMARY KEY    | 架构唯一标识符                                            |
| project_id          | VARCHAR   | 50   | 是   | FOREIGN KEY    | 课题ID，关联projects表                                    |
| version             | INTEGER   | -    | 是   | DEFAULT 1      | 版本号（同一课题内自增）                                  |
| topic_expansion     | TEXT      | -    | 否   | -              | 阶段1：扩写后的课题描述（用户确认后填入）                 |
| outline             | JSON      | -    | 否   | -              | 阶段2：综述章节架构（见下方结构说明）                     |
| status              | VARCHAR   | 20   | 是   | DEFAULT 'draft' | 状态（draft/confirmed/archived）                        |
| confirmed_at        | DATETIME  | -    | 否   | -              | 用户确认架构的时间                                        |
| created_at          | DATETIME  | -    | 是   | -              | 创建时间                                                  |
| updated_at          | DATETIME  | -    | 是   | -              | 最后更新时间                                              |

**约束**：
- PRIMARY KEY (id)
- FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
- UNIQUE INDEX idx_project_version (project_id, version)
- INDEX idx_project_id (project_id)
- INDEX idx_status (status)

**`outline` 字段结构示例**：

```json
{
  "title": "深度学习在天文图像分析中的应用综述",
  "abstract_hint": "综述的核心观点和结构概述",
  "sections": [
    {
      "index": 1,
      "title": "引言",
      "type": "introduction",
      "key_points": ["研究背景", "研究意义", "文章结构"]
    },
    {
      "index": 2,
      "title": "相关工作",
      "type": "related_work",
      "key_points": ["传统方法综述", "深度学习方法演进"]
    }
  ]
}
```

---

#### 综述章节表 (review_chapters)

**说明**：存储综述模式下各章节的撰写内容及审查迭代记录。与 `review_outlines` 关联，每个章节独立追踪撰写状态和迭代历史。`iteration_count` 记录自动审查迭代次数，`review_history` 保存每次审查的修改建议和结果。

| 字段名 | 类型 | 长度 | 必填 | 约束 | 说明 |
|------------------|-----------|------|------|----------------|-----------------------------------------------------------|
| id               | VARCHAR   | 50   | 是   | PRIMARY KEY    | 章节唯一标识符                                            |
| outline_id       | VARCHAR   | 50   | 是   | FOREIGN KEY    | 关联review_outlines表                                     |
| project_id       | VARCHAR   | 50   | 是   | FOREIGN KEY    | 课题ID，关联projects表（冗余存储，便于直接查询）          |
| chapter_index    | TINYINT   | -    | 是   | -              | 章节序号（与outline中的section.index对应）                |
| title            | VARCHAR   | 255  | 是   | -              | 章节标题                                                  |
| content          | TEXT      | -    | 否   | -              | 章节正文内容（Markdown格式）                              |
| citations        | JSON      | -    | 否   | -              | 本章引用论文列表（含paper_id和引用格式）                  |
| iteration_count  | TINYINT   | -    | 是   | DEFAULT 0      | 自动审查迭代次数                                          |
| review_history   | JSON      | -    | 否   | -              | 每次审查的建议与结果列表（见下方结构说明）                |
| status           | VARCHAR   | 20   | 是   | DEFAULT 'pending' | 状态（pending/writing/reviewing/completed）            |
| completed_at     | DATETIME  | -    | 否   | -              | 章节完成时间                                              |
| created_at       | DATETIME  | -    | 是   | -              | 创建时间                                                  |
| updated_at       | DATETIME  | -    | 是   | -              | 最后更新时间                                              |

**约束**：
- PRIMARY KEY (id)
- FOREIGN KEY (outline_id) REFERENCES review_outlines(id) ON DELETE CASCADE
- FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
- UNIQUE INDEX idx_outline_chapter (outline_id, chapter_index)
- INDEX idx_outline_id (outline_id)
- INDEX idx_project_id (project_id)
- INDEX idx_status (status)

**`citations` 字段结构示例**：

```json
[
  {
    "paper_id": "paper_123",
    "citation_key": "doe2024novel",
    "format_apa": "Doe, J. (2024). Novel Method for X. Nature.",
    "context": "如 [doe2024novel] 所提出的方法"
  }
]
```

**`review_history` 字段结构示例**：

```json
[
  {
    "iteration": 1,
    "reviewed_at": "2026-04-08T10:00:00",
    "issues": ["引用数量不足", "逻辑过渡不自然"],
    "suggestions": ["补充近三年相关工作引用", "在第二段末尾增加过渡句"],
    "accepted": true,
    "revised_at": "2026-04-08T10:05:00"
  }
]
```

---

#### 6.1.2 数据库关系图

```
users (用户表)
    ↓ 1:N
user_configs (用户配置表)

users (用户表, is_admin=TRUE)
    ↓ 写入
system_configs (系统配置表，全局回落配置)

users (用户表)
    ↓ 1:N
projects (研究主题表)
    ↓ 1:N
keywords (检索词表)

projects (研究主题表)
    ↓ 1:N
stage_records (阶段记录表，mode区分构建模式/综述模式)

projects (研究主题表)
    ↓ 1:N
research_dialogues (深度研究对话表)
    ↓ 1:N
dialogue_turns (对话轮次表，每行=用户+Agent各一次)

research_dialogues (深度研究对话表)
    ↓ 1:N
recommendations (推荐模块表)

projects (研究主题表)
    ↓ 1:N
review_outlines (综述架构表)
    ↓ 1:N
review_chapters (综述章节表)

papers (论文表)
    ↓ 1:N
project_paper_relations (研究主题-论文关联表)
    ↑ N:1
projects (研究主题表)
```


---

### 6.2 向量数据库（ChromaDB）

#### 6.2.1 Collection设计

本系统使用ChromaDB作为向量数据库，用于存储论文内容的向量表示，支持Graph-RAG检索。

**Collection命名规范**：`project_{project_id}_vectors`

**Collection结构**：

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| **id** | STRING | 向量文档唯一标识符 | `paper_{paper_id}_chunk_{chunk_id}` |
| **embedding** | FLOAT_ARRAY | 文本向量表示（1536维） | `[0.123, -0.456, 0.789, ...]` |
| **metadata** | JSON | 文档元数据 | 见下方metadata结构 |
| **document** | STRING | 原始文本内容 | `"This paper proposes a novel method..."` |

**metadata结构**：

```json
{
  "paper_id": "paper_123",
  "project_id": "project_456",
  "chunk_id": 1,
  "chunk_type": "abstract|content|conclusion",
  "section": "Introduction",
  "start_char": 0,
  "end_char": 500,
  "authors": ["John Doe", "Jane Smith"],
  "pub_date": "2024-01-15",
  "venue": "Nature",
  "title": "Novel Method for X",
  "doi": "10.1234/example.doi",
  "keywords": ["deep learning", "medical imaging"],
  "is_valid": true,
  "total_score": 8,
  "reference_score": 4,
  "technical_score": 4
}
```

#### 6.2.2 向量化策略

**文本分块策略**：

| 分块类型 | 分块大小 | 重叠大小 | 适用场景 |
|---------|---------|---------|----------|
| **摘要分块** | 500字符 | 0字符 | 论文摘要单独存储 |
| **内容分块** | 1000字符 | 200字符 | 论文正文内容 |
| **结论分块** | 800字符 | 100字符 | 论文结论部分 |

**向量生成配置**：

| 配置项 | 值 | 说明 |
|--------|---|------|
| **嵌入模型** | OpenAI text-embedding-ada-002 | 1536维向量 |
| **备用模型** | sentence-transformers/all-MiniLM-L6-v2 | 本地备选方案 |
| **归一化** | L2归一化 | 提高检索准确性 |
| **批处理大小** | 100 | 向量化批处理大小 |

#### 6.2.3 检索策略

**Graph-RAG检索流程**：

1. **初始检索**：基于查询向量进行相似度检索
2. **图扩展**：基于检索结果在知识图谱中扩展相关节点
3. **重排序**：结合图结构和相似度进行重排序
4. **上下文构建**：选择最相关的文档片段构建上下文

**检索参数配置**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **top_k** | 10 | 初始检索返回结果数 |
| **similarity_threshold** | 0.7 | 相似度阈值 |
| **graph_expansion_depth** | 2 | 图扩展深度 |
| **max_context_length** | 28000 | 最大上下文长度（token），约 70 页文本内容 |

#### 6.2.4 Collection管理

**创建Collection**：

```python
# 为每个研究主题创建独立的Collection
collection_name = f"project_{project_id}_vectors"
collection = chroma_client.create_collection(
    name=collection_name,
    metadata={
        "project_id": project_id,
        "created_at": datetime.now().isoformat(),
        "embedding_model": "text-embedding-ada-002"
    }
)
```

**删除Collection**：

```python
# 研究主题删除时删除对应的Collection
chroma_client.delete_collection(name=f"project_{project_id}_vectors")
```

**索引优化**：

- 使用HNSW索引提高检索速度
- 设置ef_construction=200，ef_search=50
- 定期优化索引结构

---

#### 6.2.5 向量数据库关系图

```
projects (研究主题表)
    ↓ 1:1
ChromaDB Collection: project_{project_id}_vectors
    ↓ 1:N
Vector Documents (论文向量文档)
    ├─ paper_{paper_id}_chunk_{chunk_id}
    ├─ metadata: {paper_id, project_id, chunk_id, ...}
    ├─ embedding: [1536维向量]
    └─ document: "原始文本内容"

papers (论文表)
    ↓ 1:N
Vector Documents (一个论文多个向量块)
```

---

### 6.3 图数据库（NetworkX）

#### 6.3.1 知识图谱结构

本系统使用NetworkX构建论文知识图谱，支持Graph-RAG检索和知识发现。

**图谱类型**：有向多重图（DiGraph）

**节点类型**：

| 节点类型 | 标识符格式 | 属性字段 | 说明 |
|---------|-----------|---------|------|
| **论文节点** | `paper_{paper_id}` | 见论文节点属性 | 表示单篇论文 |
| **作者节点** | `author_{author_name_normalized}` | 见作者节点属性 | 表示论文作者 |
| **关键词节点** | `keyword_{keyword_normalized}` | 见关键词节点属性 | 表示研究关键词 |
| **概念节点** | `concept_{concept_name_normalized}` | 见概念节点属性 | 表示研究概念 |
| **方法节点** | `method_{method_name_normalized}` | 见方法节点属性 | 表示研究方法 |

**论文节点属性**：

```python
{
    "node_type": "paper",
    "paper_id": "paper_123",
    "project_id": "project_456",
    "title": "Novel Method for X",
    "authors": ["author_john_doe", "author_jane_smith"],
    "pub_date": "2024-01-15",
    "venue": "Nature",
    "doi": "10.1234/example.doi",
    "abstract": "This paper proposes...",
    "total_score": 8,
    "is_valid": true,
    "keywords": ["keyword_deep_learning", "keyword_medical_imaging"],
    "chunk_count": 15,
    "citations": []
}
```

**作者节点属性**：

```python
{
    "node_type": "author",
    "author_name": "John Doe",
    "normalized_name": "john_doe",
    "paper_count": 5,
    "affiliation": "MIT",
    "h_index": 25,
    "papers": ["paper_123", "paper_456"]
}
```

**关键词节点属性**：

```python
{
    "node_type": "keyword",
    "keyword": "deep learning",
    "normalized_keyword": "deep_learning",
    "paper_count": 150,
    "related_keywords": ["machine_learning", "neural_networks"],
    "growth_trend": 0.8
}
```

**概念节点属性**：

```python
{
    "node_type": "concept",
    "concept_name": "convolutional neural network",
    "normalized_name": "convolutional_neural_network",
    "definition": "A type of deep neural network...",
    "paper_count": 80,
    "related_concepts": ["deep_learning", "computer_vision"]
}
```

**方法节点属性**：

```python
{
    "node_type": "method",
    "method_name": "transfer learning",
    "normalized_name": "transfer_learning",
    "description": "A research technique...",
    "paper_count": 45,
    "related_methods": ["fine_tuning", "domain_adaptation"]
}
```

#### 6.3.2 边关系类型

**边类型定义**：

| 边类型 | 方向 | 权重 | 说明 |
|--------|------|------|------|
| **AUTHORED_BY** | 论文→作者 | 1.0 | 论文由作者撰写 |
| **HAS_KEYWORD** | 论文→关键词 | 1.0 | 论文包含关键词 |
| **MENTIONS_CONCEPT** | 论文→概念 | 相似度 | 论文提及概念 |
| **USES_METHOD** | 论文→方法 | 相关性 | 论文使用方法 |
| **CITES** | 论文→论文 | 引用强度 | 论文引用关系 |
| **COLLABORATES_WITH** | 作者→作者 | 合作次数 | 作者合作关系 |
| **RELATED_TO** | 关键词→关键词 | 相关度 | 关键词关联关系 |
| **SIMILAR_TO** | 概念→概念 | 相似度 | 概念相似关系 |

**边属性示例**：

```python
# CITES边属性
{
    "edge_type": "cites",
    "source_paper": "paper_123",
    "target_paper": "paper_456",
    "citation_count": 5,
    "citation_context": "as proposed in [456]",
    "strength": 0.8
}

# COLLABORATES_WITH边属性
{
    "edge_type": "collaborates_with",
    "source_author": "author_john_doe",
    "target_author": "author_jane_smith",
    "collaboration_count": 3,
    "papers_together": ["paper_123", "paper_456", "paper_789"]
}
```

#### 6.3.3 图谱构建流程

**构建步骤**：

1. **节点创建**：从论文元数据中提取实体并创建对应节点
2. **边建立**：根据实体关系建立边连接
3. **属性填充**：为节点和边填充详细属性
4. **权重计算**：计算边的权重（引用强度、相关度等）
5. **图优化**：移除孤立节点，优化图结构

**构建算法**：

```python
def build_knowledge_graph(project_id, papers):
    """
    构建研究主题的知识图谱

    Args:
        project_id: 研究主题ID
        papers: 论文列表

    Returns:
        NetworkX DiGraph对象
    """
    G = nx.DiGraph()

    # 1. 创建论文节点
    for paper in papers:
        paper_node_id = f"paper_{paper['id']}"
        G.add_node(paper_node_id, **paper)

        # 2. 创建作者节点和边
        for author in paper['authors']:
            author_node_id = f"author_{normalize_name(author)}"
            G.add_node(author_node_id, node_type='author', author_name=author)
            G.add_edge(paper_node_id, author_node_id,
                      edge_type='authored_by', weight=1.0)

        # 3. 创建关键词节点和边
        for keyword in paper['keywords']:
            keyword_node_id = f"keyword_{normalize_name(keyword)}"
            G.add_node(keyword_node_id, node_type='keyword', keyword=keyword)
            G.add_edge(paper_node_id, keyword_node_id,
                      edge_type='has_keyword', weight=1.0)

        # 4. 创建引用边
        for citation in paper['citations']:
            citation_node_id = f"paper_{citation['paper_id']}"
            G.add_edge(paper_node_id, citation_node_id,
                      edge_type='cites',
                      strength=citation['strength'])

    # 5. 计算图统计指标
    calculate_graph_metrics(G)

    return G
```

#### 6.3.4 图谱分析功能

**中心性分析**：

| 指标 | 计算方法 | 应用场景 |
|------|---------|----------|
| **度中心性** | `nx.degree_centrality()` | 识别重要论文 |
| **接近中心性** | `nx.closeness_centrality()` | 识别中心论文 |
| **介数中心性** | `nx.betweenness_centrality()` | 识别桥梁论文 |
| **PageRank** | `nx.pagerank()` | 识别影响力论文 |

**社区发现**：

| 算法 | 参数 | 应用场景 |
|------|------|----------|
| **Louvain** | resolution=1.0 | 发现研究社区 |
| **Label Propagation** | - | 快速社区划分 |
| **Connected Components** | - | 识别孤立群体 |

**路径分析**：

| 功能 | 算法 | 应用场景 |
|------|------|----------|
| **最短路径** | `nx.shortest_path()` | 论文关联链 |
| **所有路径** | `nx.all_simple_paths()` | 全面关联分析 |
| **子图提取** | `nx.subgraph()` | 局部知识提取 |

#### 6.3.5 图谱持久化

**存储格式**：

| 格式 | 文件扩展名 | 优点 | 缺点 |
|------|-----------|------|------|
| **GraphML** | .graphml | 标准格式，支持属性 | 文件较大 |
| **GML** | .gml | 人类可读 | 性能较低 |
| **Pickle** | .pkl | 二进制，性能高 | 不跨平台 |
| **JSON** | .json | 通用格式 | 需要自定义序列化 |

**推荐方案**：使用GraphML格式存储

```python
# 保存图谱
nx.write_graphml(G, f"data/graphs/project_{project_id}.graphml")

# 加载图谱
G = nx.read_graphml(f"data/graphs/project_{project_id}.graphml")
```

**存储路径结构**：

```
data/
├── graphs/
│   ├── project_{project_id}.graphml
│   └── project_{project_id}_metrics.json
└── backups/
    └── project_{project_id}_backup_{timestamp}.graphml
```

#### 6.3.6 图谱更新策略

**增量更新**：

1. **新论文添加**：
   - 创建新节点
   - 建立边连接
   - 更新图统计

2. **论文删除**：
   - 删除节点及相关边
   - 重新计算图指标

3. **关系更新**：
   - 更新边权重
   - 添加新关系

**全量重建**：

- 每日深夜由后台调度器自动触发，仅在有论文变更时执行
- 全量重建时间（验收基准）：< 60秒（500篇论文）

---

#### 6.3.7 图数据库关系图

```
papers (论文表)
    ↓ 1:1
NetworkX Graph: project_{project_id}.graphml
    ↓ 节点关系
Knowledge Graph Nodes (知识图谱节点)
    ├─ 论文节点 (paper_{paper_id})
    ├─ 作者节点 (author_{author_name})
    ├─ 关键词节点 (keyword_{keyword})
    ├─ 概念节点 (concept_{concept})
    └─ 方法节点 (method_{method})

Knowledge Graph Edges (知识图谱边)
    ├─ AUTHORED_BY (论文→作者)
    ├─ HAS_KEYWORD (论文→关键词)
    ├─ MENTIONS_CONCEPT (论文→概念)
    ├─ USES_METHOD (论文→方法)
    ├─ CITES (论文→论文)
    ├─ COLLABORATES_WITH (作者→作者)
    ├─ RELATED_TO (关键词→关键词)
    └─ SIMILAR_TO (概念→概念)
```

---

### 6.4 数据字典说明

#### 6.4.1 设计原则

1. **用户隔离**：所有用户数据通过user_id关联，确保多用户数据隔离
2. **配置灵活**：user_configs表采用键值对方式存储配置，支持动态扩展
3. **论文复用**：papers表独立存储论文元数据，通过关联表实现多课题共享可行性
4. **状态追踪**：每个课题都有完整的阶段记录，支持执行过程追踪
5. **评分独立**：论文评分存储在关联表中，同一论文在不同课题中的评分相互独立

#### 6.4.2 数据一致性保证

1. **外键约束**：所有关联表都使用外键约束确保数据完整性
2. **级联删除**：用户删除时，级联删除其所有相关数据
3. **唯一约束**：关键字段（如DOI、ArXiv ID）设置唯一约束避免重复
4. **索引优化**：为常用查询字段创建索引，提高查询性能

#### 6.4.3 配置管理策略

1. **系统默认配置**：is_system_default=TRUE的配置为系统默认值
2. **用户自定义配置**：用户可覆盖默认配置，优先使用用户配置
3. **配置加载顺序**：用户配置 > 系统默认配置
4. **配置分类**：通过config_name的命名约定实现配置分类（如llm.xxx、database.xxx、email.xxx）

#### 6.4.4 三数据库协同设计原则

1. **数据分层存储**：
   - PostgreSQL存储结构化数据和元数据
   - ChromaDB存储向量表示，支持语义检索
   - NetworkX存储实体关系，支持图推理

2. **同步机制**：
   - **PostgreSQL ↔ ChromaDB（强一致）**：论文数据写入 PostgreSQL 后，在同一事务上下文中同步写入 ChromaDB；任意一方写入失败则立即回滚双方操作，不允许任何部分成功状态
   - **NetworkX（最终一致）**：图数据库不要求与前两者实时同步，允许有一定滞后；新增论文时可仅进行局部增量更新（添加相关节点和边）；系统每日深夜在后台自动对所有项目执行全量图重建（仅在有论文变更时触发）

3. **查询优化**：
   - 元数据查询使用PostgreSQL
   - 语义检索使用ChromaDB
   - 关系推理使用NetworkX
   - 组合查询通过三数据库协同实现

4. **性能保障**：
   - ChromaDB检索响应时间 < 3秒
   - NetworkX图谱构建时间 < 10秒（50篇论文）
   - PostgreSQL查询响应时间 < 1秒

5. **一致性保证**：
   - 使用 project_id 作为统一关联键
   - PostgreSQL 与 ChromaDB 保持强一致，任意写入失败立即回滚
   - NetworkX 图数据库保持最终一致，每日深夜全量重建，日间仅做增量更新

#### 6.4.5 三数据库协同关系图

```
┌─────────────────────────────────────────────────────────┐
│                    PostgreSQL (关系型数据库)             │
│  users | projects | papers | keywords | relations      │
└─────────────────────────────────────────────────────────┘
                          ↓ 同步
┌─────────────────────────────────────────────────────────┐
│                    ChromaDB (向量数据库)                │
│  project_{project_id}_vectors Collection                │
│  - 存储论文内容的向量表示                               │
│  - 支持语义检索和相似度匹配                              │
└─────────────────────────────────────────────────────────┘
                          ↓ 同步
┌─────────────────────────────────────────────────────────┐
│                    NetworkX (图数据库)                  │
│  project_{project_id}.graphml 知识图谱                  │
│  - 存储论文实体关系                                      │
│  - 支持Graph-RAG检索和知识发现                          │
└─────────────────────────────────────────────────────────┘

协同工作流程：
1. PostgreSQL存储论文元数据和结构化数据
2. ChromaDB存储论文内容的向量表示，支持语义检索
3. NetworkX构建知识图谱，支持关系推理和Graph-RAG
4. 三数据库通过project_id关联，保证数据一致性
```

---
