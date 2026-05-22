# Data Persistence 设计

文档版本：v1.1  
更新日期：2026-05-20  
依据文档：`00_layers.md`、`01_functional_requirements.md`

## 1. 设计目标

数据设计服务于 Domain Core 和 Application Use Cases，重点保证用户隔离、Project 私有资产、共享论文身份、Knowledge Version 绑定、长任务可恢复和外部存储同步可诊断。

## 2. 存储分工

| 存储 | 用途 | 说明 |
| --- | --- | --- |
| PostgreSQL 或等价关系库 | 账号、配置元数据、Project、Run/Session、论文身份、版本、状态、审计 | 业务事实的权威来源 |
| 文件存储 | PDF、解析文本、导出文件、临时产物 | 通过对象 key 引用，不暴露真实路径 |
| 向量库 | Knowledge Version 或 Project namespace 下的文档向量 | 与关系库通过同步状态关联 |
| 图谱存储 | 论文、作者、关键词、概念、方法节点边 | 可由关系库/图数据库/文件图谱实现 |
| Secret Store | API key、SMTP 密码、系统密钥 | 关系库只保存密钥引用或密文标识 |
| 队列/调度状态 | 异步任务与重试 | MVP 可由关系表承载，后续可替换队列 |

## 3. 关系数据模块

| 模块 | 表/实体 |
| --- | --- |
| 用户与权限 | `users`, `user_sessions`, `audit_logs` |
| 配置 | `user_llm_configs`, `user_data_source_configs`, `user_notification_configs`, `system_configs`, `runtime_config_snapshots` |
| Project | `projects`, `construction_workspaces`, `search_terms` |
| Run/Session | `construction_runs`, `research_sessions`, `research_messages`, `review_runs`, `review_outlines`, `review_chapters`, `review_final_versions` |
| 论文与知识 | `papers`, `project_papers`, `document_assets`, `knowledge_versions`, `knowledge_sync_items`, `citations` |
| 任务与产物 | `locks`, `export_jobs`, `email_push_jobs`, `job_attempts` |
| 协作 | `viewpoints` |

## 4. 身份与隔离

- `papers` 表保存全局论文身份和可复用元数据。
- `project_papers` 保存 Project 私有关联、评分、有效性、推送状态和 AI 分析。
- 文件资产必须绑定 Project 或导出任务，清理时按拥有者和引用关系判断。
- 普通用户查询必须通过 Project 权限过滤。
- 管理员可治理账号和系统配置，但不得读取用户私人密钥明文。

## 5. Knowledge Version 数据规则

`knowledge_versions` 应保存 Project、版本号、来源 Construction Run、发布时间、状态、关系库论文快照范围、向量索引引用、图谱引用和发布诊断摘要。

Research Session 和 Review Run 保存 `knowledge_version_id`，创建后不得静默改写。

## 6. 外部存储一致性

关系库与向量库/图谱/文件存储无法天然同事务提交，采用同步项策略：

| 状态 | 含义 |
| --- | --- |
| `pending` | 已在关系库登记，等待外部写入 |
| `synced` | 外部写入成功并可读取 |
| `failed` | 外部写入失败，有错误分类 |
| `stale` | 外部内容不再匹配当前关系数据 |
| `deleted` | 外部资源已清理或不可再访问 |

发布 Knowledge Version 前，关键同步项必须达到 `synced` 或被明确标记为允许降级。

## 7. 文件与导出生命周期

- PDF、解析文本、Graph 文件和向量 namespace 是 Project 私有资产。
- 已完成导出文件是用户主动生成产物，Project 私人资产清理默认保留。
- 删除导出文件通过导出中心或生命周期策略执行。
- 所有下载/打开入口必须经过鉴权或签名 URL。

## 8. 数据清理

Project 私人资产清理范围包括 Project 私有运行记录、Research Session、Review Run、Project-Paper 关联、Project 私有 PDF、解析文本、图谱、向量索引和临时任务产物。

不得清理全局 `papers` 论文身份、其他 Project 或其他用户仍引用的资源、默认保留的导出文件。

## 9. 迁移与索引要求

- 所有表包含 `created_at` 和 `updated_at`。
- 所有用户可见资源包含 owner 或 Project 权限路径。
- Run/Session 状态、Project 状态、Knowledge Version 状态需要索引。
- `papers` 应对 DOI、arXiv ID、来源 ID 建唯一或部分唯一索引。
- `project_papers` 对 `(project_id, paper_id)` 唯一。
- active Construction Run 唯一性可用部分唯一索引或应用锁双重保证。
