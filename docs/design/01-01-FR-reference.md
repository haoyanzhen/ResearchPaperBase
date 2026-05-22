# FR Reference

文档版本：v1.1  
更新日期：2026-05-21  
来源文档：`01_functional_requirements.md`  
用途：作为功能需求编号、优先级和编号重整关系的参考中间文件。若本文与 `01_functional_requirements.md` 冲突，以 `01_functional_requirements.md` 为准。

## 1. 功能需求清单

| 需求编号 | 所属层/模式 | 需求名称 | 优先级 | 说明 |
| --- | --- | --- | --- | --- |
| FR-001 | 基础层 | 用户账号与认证 | P0 | 注册、登录、登出、当前用户信息、账号状态 |
| FR-002 | 基础层 | 用户 LLM 配置管理 | P0 | 用户维护个人 LLM provider、模型、密钥和参数 |
| FR-003 | 基础层 | 用户论文数据库 API 配置管理 | P0 | 用户维护 arXiv/OpenAlex/Semantic Scholar/ADS 等数据源配置 |
| FR-004 | 基础层 | 用户邮件与通知配置 | P1 | 用户维护个人收件人和通知偏好 |
| FR-005 | 基础层/管理员模块 | 管理员账号管理 | P0 | 首位用户为管理员，维护用户账号状态和管理员权限 |
| FR-006 | 基础层/管理员模块 | 管理员系统级配置管理 | P0 | 维护系统默认 LLM、论文数据库 API、SMTP 和安全配置 |
| FR-007 | 基础层 | 用户配置与系统配置解析规则 | P0 | 定义用户配置、系统默认配置、硬限制、密钥隔离和运行时取值优先级 |
| FR-008 | 基础层 | 系统级页面入口与 Project 可用性约束 | P0 | 管理系统级页面入口、Project 状态、Project 列表/维护入口和进入 Project Workspace 的可用性约束 |
| FR-009 | 基础层 | 系统级自动构建调度与推送触发 | P1 | 系统级调度器扫描 active Project 的 Construction Workspace，创建自动 Construction Run，并向邮件推送流程提供新增有效论文范围 |
| FR-010 | 基础层 | 观点广场 | P2 | 独立系统级观点发布与查看页面，禁止评论和讨论，仅展示联系信息 |
| FR-011 | 基础层-项目工作台 | Project Workspace 内部入口、框架与对象切换 | P0 | 管理 Project 状态展示、Construction Workspace 入口、Run/Session 列表、对象打开/切换、主体流程栏和信息面板 |
| FR-012 | 基础层-项目工作台 | Project 知识资产面板 | P0 | 只读查看 Project 论文库、论文详情、PDF 访问入口、Graph 图谱和 Knowledge Version |
| FR-013 | 基础层-项目工作台 | Workspace 上下文管理与恢复 | P0 | P0 恢复上次打开对象、基础面板状态和输入草稿；更细粒度的滚动、日志和步骤落点恢复作为 P1 增强 |
| FR-014 | 基础层-项目工作台 | Run/Session 实例操作 | P0 | P0 提供进入、创建、继续和历史查看；复制、重跑、归档、删除为 P1 受控增强 |
| FR-015 | 基础层-项目工作台 | Run/Session 状态展示与运行控制 | P0 | P0 查看状态、阶段、错误、等待项、日志摘要并支持取消；暂停、恢复、重试为 P1 受控增强 |
| FR-016 | 基础层-项目工作台 | 流程式 Agent 步骤容器 | P0 | 承载构建、综述等流程式 Agent 的当前步骤页面、步骤状态、步骤动作和步骤结果查看 |
| FR-017 | 基础层-项目工作台 | 内容修改保护基座 | P0 | 提供跨 Agent 的通用内容保护规则，区分 Agent 草稿、人工确认和人工修改状态，防止静默覆盖 |
| FR-018 | 基础层-项目工作台 | 知识库版本刷新提示与不打断规则 | P0 | 新 Knowledge Version 发布后提示刷新；active Research Session / Review Run 不被打断，已完成内容不自动改写 |
| FR-019 | 基础层-项目工作台 | Project/Run/Session 导出 | P1 | 按 Project 或具体 Run/Session 导出论文库数据、PDF 集合、对话、总结或综述产物 |
| FR-020 | 构建模式 | 检索词生成与构建检索词管理 | P0 | 管理 Project 检索词、检索词级数据源策略和自动更新开关 |
| FR-021 | 构建模式 | 多源论文检索 | P0 | 手动 Run 使用本次 selected 检索词，自动 Run 使用自动更新检索词，并按检索词级数据源策略检索 |
| FR-022 | 构建模式 | 论文去重、评分与筛选 | P0 | 对候选论文去重、评分、筛选有效论文，支持用户确认与调整 |
| FR-023 | 构建模式 | 论文补充与手动上传 | P1 | 用户通过 PDF、DOI、arXiv ID 或 URL 补充论文 |
| FR-024 | 构建模式 | PDF 下载与文本解析 | P0 | 自动下载 PDF、解析文本，失败时降级使用摘要 |
| FR-025 | 构建模式 | 论文 AI 分析生成 | P0 | 生成一句话总结、亮点、相关性要点、方法与创新 |
| FR-026 | 构建模式 | 知识库入库与图谱构建 | P0 | 将有效论文写入 Project 知识库、向量库和知识图谱 |
| FR-027 | 构建模式 | 邮件推送服务 | P1 | 将未推送有效论文生成邮件并发送给用户收件人 |
| FR-028 | 深度研究模式 | Graph-RAG 对话式研究 | P0 | 基于 Project 知识库进行多轮流式研究对话 |
| FR-029 | 深度研究模式 | 深度研究输出倾向设置 | P1 | 提供输出倾向设置按钮，用户可通过选择不同倾向控制整体对话风格 |
| FR-030 | 深度研究模式 | 对话历史、总结文件与导出 | P1 | 保存研究过程，生成总结文件并支持导出 |
| FR-031 | 深度研究模式 | 研究引用与图谱跳转 | P1 | 从对话引用跳转到论文详情、PDF 和基础层 Graph 图谱 |
| FR-032 | 主题综述模式 | 综述架构设计 | P0 | Agent 生成综述主题、范围和章节架构，用户审查确认 |
| FR-033 | 主题综述模式 | 章节撰写、引用与修订 | P0 | Agent 逐章撰写并引用 Project 论文库，用户审查、编辑或重试 |
| FR-034 | 主题综述模式 | 综述汇总、终审与可导出版本生成 | P0 | 汇总章节，执行终审，生成摘要、关键词、参考文献和最终可导出版本 |
| FR-035 | 主题综述模式 | 综述最小追溯管理 | P0 | Review Run 主流程所需的最小追溯：大纲、章节、审查和终稿状态 |
| FR-036 | 主题综述模式 | 综述版本管理与变更摘要增强 | P2 | Review Run 版本历史、只读快照、差异、回退和用户更改摘要 |

## 2. FR 编号重整映射表

> 本表保留重整前后的编号关系，用于后续修改其他设计文件时查询；正式需求编号以“新编号”为准。

| 旧编号 | 新编号 | 需求名称 | 所属层/模式 |
| --- | --- | --- | --- |
| FR-001 | FR-001 | 用户账号与认证 | 基础层 |
| FR-002 | FR-002 | 用户 LLM 配置管理 | 基础层 |
| FR-003 | FR-003 | 用户论文数据库 API 配置管理 | 基础层 |
| FR-004 | FR-004 | 用户邮件与通知配置 | 基础层 |
| FR-005 | FR-005 | 管理员账号管理 | 基础层/管理员模块 |
| FR-006 | FR-006 | 管理员系统级配置管理 | 基础层/管理员模块 |
| FR-007 | FR-007 | 用户配置与系统配置解析规则 | 基础层 |
| FR-008 | FR-008 | 系统级页面入口与 Project 可用性约束 | 基础层 |
| FR-013 | FR-009 | 系统级自动构建调度与推送触发 | 基础层 |
| FR-014 | FR-010 | 观点广场 | 基础层 |
| FR-WORKSPACE-001 | FR-011 | Project Workspace 内部入口、框架与对象切换 | 基础层-项目工作台 |
| FR-WORKSPACE-002 | FR-012 | Project 知识资产面板 | 基础层-项目工作台 |
| FR-WORKSPACE-003 | FR-013 | Workspace 上下文管理与恢复 | 基础层-项目工作台 |
| FR-WORKSPACE-004 | FR-014 | Run/Session 实例操作 | 基础层-项目工作台 |
| FR-WORKSPACE-005 | FR-015 | Run/Session 状态展示与运行控制 | 基础层-项目工作台 |
| FR-WORKSPACE-006 | FR-016 | 流程式 Agent 步骤容器 | 基础层-项目工作台 |
| FR-WORKSPACE-007 | FR-017 | 内容修改保护基座 | 基础层-项目工作台 |
| FR-WORKSPACE-008 | FR-018 | 知识库版本刷新提示与不打断规则 | 基础层-项目工作台 |
| FR-WORKSPACE-009 | FR-019 | Project/Run/Session 导出 | 基础层-项目工作台 |
| FR-015 | FR-020 | 检索词生成与构建检索词管理 | 构建模式 |
| FR-016 | FR-021 | 多源论文检索 | 构建模式 |
| FR-017 | FR-022 | 论文去重、评分与筛选 | 构建模式 |
| FR-018 | FR-023 | 论文补充与手动上传 | 构建模式 |
| FR-019 | FR-024 | PDF 下载与文本解析 | 构建模式 |
| FR-020 | FR-025 | 论文 AI 分析生成 | 构建模式 |
| FR-021 | FR-026 | 知识库入库与图谱构建 | 构建模式 |
| FR-022 | FR-027 | 邮件推送服务 | 构建模式 |
| FR-023 | FR-028 | Graph-RAG 对话式研究 | 深度研究模式 |
| FR-024 | FR-029 | 深度研究输出倾向设置 | 深度研究模式 |
| FR-025 | FR-030 | 对话历史、总结文件与导出 | 深度研究模式 |
| FR-026 | FR-031 | 研究引用与图谱跳转 | 深度研究模式 |
| FR-027 | FR-032 | 综述架构设计 | 主题综述模式 |
| FR-028 | FR-033 | 章节撰写、引用与修订 | 主题综述模式 |
| FR-029 | FR-034 | 综述汇总、终审与可导出版本生成 | 主题综述模式 |
| FR-030 | FR-035 | 综述最小追溯管理 | 主题综述模式 |
| FR-031 | FR-036 | 综述版本管理与变更摘要增强 | 主题综述模式 |

## 3. FR 分层追踪表

本章包含两类映射：

- `3.1 闭环映射`：回答一个 FR 完整落地时需要经过哪些层。
- `3.2 主责-协作映射`：回答一个 FR 的核心设计主要由哪些文件负责，哪些文件只提供配合或横切约束。

### 3.1 闭环映射

本表按当前分层文件建立 FR 到设计文件的闭环追踪关系。P0/P1 FR 应形成 UI、API、应用用例、领域/Agent、数据、安全和 QA 闭环；P2 FR 可先保留扩展点，但不得阻塞 P0/P1。

文件简称：

| 简称 | 文件 |
| --- | --- |
| Domain | `02_domain_core.md` |
| UI | `03_ui_workspace.md` |
| API | `04_api_contracts.md` |
| App | `05_application_use_cases.md` |
| Agent/Knowledge | `06_agent_knowledge_services.md` |
| Data | `07_data_persistence.md`, `07_data_schema.sql` |
| Security | `08_security_permissions.md` |
| QA | `09_quality_observability.md` |
| Ops | `10_operations_deployment.md` |

| FR | 优先级 | UI | API | 应用/流程 | 领域/Agent | 数据 | 权限/安全 | QA/运维 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FR-001 | P0 | UI | API | App | Domain | Data | Security | QA | 初版映射 |
| FR-002 | P0 | UI | API | App | Domain | Data | Security | QA | 初版映射 |
| FR-003 | P0 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA | 初版映射 |
| FR-004 | P1 | UI | API | App | Domain | Data | Security | QA, Ops | 初版映射 |
| FR-005 | P0 | UI | API | App | Domain | Data | Security | QA | 初版映射 |
| FR-006 | P0 | UI | API | App | Domain | Data | Security | QA, Ops | 初版映射 |
| FR-007 | P0 | UI | API | App | Domain | Data | Security | QA | 初版映射 |
| FR-008 | P0 | UI | API | App | Domain | Data | Security | QA | 初版映射 |
| FR-009 | P1 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA, Ops | 初版映射 |
| FR-010 | P2 | UI | API | App | Domain | Data | Security | QA | P2 扩展映射 |
| FR-011 | P0 | UI | API | App | Domain | Data | Security | QA | 初版映射 |
| FR-012 | P0 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA | 初版映射 |
| FR-013 | P0 | UI | API | App | Domain | Data | Security | QA | 初版映射 |
| FR-014 | P0 | UI | API | App | Domain | Data | Security | QA | 初版映射 |
| FR-015 | P0 | UI | API | App | Domain | Data | Security | QA | 初版映射 |
| FR-016 | P0 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA | 初版映射 |
| FR-017 | P0 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA | 初版映射 |
| FR-018 | P0 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA | 初版映射 |
| FR-019 | P1 | UI | API | App | Domain | Data | Security | QA, Ops | 初版映射 |
| FR-020 | P0 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA | 初版映射 |
| FR-021 | P0 | UI | API | App | Agent/Knowledge | Data | Security | QA, Ops | 初版映射 |
| FR-022 | P0 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA | 初版映射 |
| FR-023 | P1 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA, Ops | 初版映射 |
| FR-024 | P0 | UI | API | App | Agent/Knowledge | Data | Security | QA, Ops | 初版映射 |
| FR-025 | P0 | UI | API | App | Agent/Knowledge | Data | Security | QA | 初版映射 |
| FR-026 | P0 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA, Ops | 初版映射 |
| FR-027 | P1 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA, Ops | 初版映射 |
| FR-028 | P0 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA | 初版映射 |
| FR-029 | P1 | UI | API | App | Agent/Knowledge | Data | Security | QA | 初版映射 |
| FR-030 | P1 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA, Ops | 初版映射 |
| FR-031 | P1 | UI | API | App | Agent/Knowledge | Data | Security | QA | 初版映射 |
| FR-032 | P0 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA | 初版映射 |
| FR-033 | P0 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA | 初版映射 |
| FR-034 | P0 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA, Ops | 初版映射 |
| FR-035 | P0 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA | 初版映射 |
| FR-036 | P2 | UI | API | App | Domain, Agent/Knowledge | Data | Security | QA | P2 扩展映射 |

### 3.2 主责-协作映射

本表用于设计分工和后续逐文件编写。`主责文件` 承载该 FR 的核心设计；`协作文件` 提供接口、状态、数据或体验配合；`横切文件` 提供权限、安全、测试、运维等通用约束。

| FR | 优先级 | 主责文件 | 协作文件 | 横切文件 | 状态 |
| --- | --- | --- | --- | --- | --- |
| FR-001 | P0 | `02_domain_core.md`, `05_application_use_cases.md`, `08_security_permissions.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `07_data_persistence.md` | `09_quality_observability.md` | 初版映射 |
| FR-002 | P0 | `05_application_use_cases.md`, `08_security_permissions.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `07_data_persistence.md` | `09_quality_observability.md` | 初版映射 |
| FR-003 | P0 | `05_application_use_cases.md`, `06_agent_knowledge_services.md`, `08_security_permissions.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `07_data_persistence.md` | `09_quality_observability.md` | 初版映射 |
| FR-004 | P1 | `05_application_use_cases.md`, `10_operations_deployment.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-005 | P0 | `02_domain_core.md`, `05_application_use_cases.md`, `08_security_permissions.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `07_data_persistence.md` | `09_quality_observability.md` | 初版映射 |
| FR-006 | P0 | `05_application_use_cases.md`, `08_security_permissions.md`, `10_operations_deployment.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `07_data_persistence.md` | `09_quality_observability.md` | 初版映射 |
| FR-007 | P0 | `02_domain_core.md`, `05_application_use_cases.md`, `08_security_permissions.md` | `04_api_contracts.md`, `07_data_persistence.md` | `09_quality_observability.md` | 初版映射 |
| FR-008 | P0 | `02_domain_core.md`, `03_ui_workspace.md`, `05_application_use_cases.md` | `04_api_contracts.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-009 | P1 | `05_application_use_cases.md`, `10_operations_deployment.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `06_agent_knowledge_services.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-010 | P2 | `03_ui_workspace.md`, `05_application_use_cases.md` | `02_domain_core.md`, `04_api_contracts.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | P2 扩展映射 |
| FR-011 | P0 | `03_ui_workspace.md`, `05_application_use_cases.md` | `02_domain_core.md`, `04_api_contracts.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-012 | P0 | `03_ui_workspace.md`, `06_agent_knowledge_services.md`, `07_data_persistence.md` | `04_api_contracts.md`, `05_application_use_cases.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-013 | P0 | `03_ui_workspace.md`, `05_application_use_cases.md` | `04_api_contracts.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-014 | P0 | `03_ui_workspace.md`, `05_application_use_cases.md` | `02_domain_core.md`, `04_api_contracts.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-015 | P0 | `03_ui_workspace.md`, `05_application_use_cases.md` | `02_domain_core.md`, `04_api_contracts.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-016 | P0 | `03_ui_workspace.md`, `05_application_use_cases.md`, `06_agent_knowledge_services.md` | `04_api_contracts.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-017 | P0 | `02_domain_core.md`, `05_application_use_cases.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `06_agent_knowledge_services.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-018 | P0 | `02_domain_core.md`, `03_ui_workspace.md`, `05_application_use_cases.md` | `04_api_contracts.md`, `06_agent_knowledge_services.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-019 | P1 | `05_application_use_cases.md`, `07_data_persistence.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `10_operations_deployment.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-020 | P0 | `06_agent_knowledge_services.md`, `05_application_use_cases.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-021 | P0 | `06_agent_knowledge_services.md`, `05_application_use_cases.md` | `04_api_contracts.md`, `07_data_persistence.md`, `10_operations_deployment.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-022 | P0 | `06_agent_knowledge_services.md`, `02_domain_core.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `05_application_use_cases.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-023 | P1 | `06_agent_knowledge_services.md`, `07_data_persistence.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `05_application_use_cases.md` | `08_security_permissions.md`, `09_quality_observability.md`, `10_operations_deployment.md` | 初版映射 |
| FR-024 | P0 | `06_agent_knowledge_services.md`, `07_data_persistence.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `05_application_use_cases.md`, `10_operations_deployment.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-025 | P0 | `06_agent_knowledge_services.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `05_application_use_cases.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-026 | P0 | `06_agent_knowledge_services.md`, `07_data_persistence.md` | `02_domain_core.md`, `03_ui_workspace.md`, `04_api_contracts.md`, `05_application_use_cases.md`, `10_operations_deployment.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-027 | P1 | `05_application_use_cases.md`, `10_operations_deployment.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `06_agent_knowledge_services.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-028 | P0 | `06_agent_knowledge_services.md`, `05_application_use_cases.md` | `02_domain_core.md`, `03_ui_workspace.md`, `04_api_contracts.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-029 | P1 | `03_ui_workspace.md`, `06_agent_knowledge_services.md` | `04_api_contracts.md`, `05_application_use_cases.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-030 | P1 | `05_application_use_cases.md`, `07_data_persistence.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `06_agent_knowledge_services.md`, `10_operations_deployment.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-031 | P1 | `03_ui_workspace.md`, `06_agent_knowledge_services.md` | `04_api_contracts.md`, `05_application_use_cases.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-032 | P0 | `06_agent_knowledge_services.md`, `05_application_use_cases.md` | `02_domain_core.md`, `03_ui_workspace.md`, `04_api_contracts.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-033 | P0 | `06_agent_knowledge_services.md`, `05_application_use_cases.md` | `02_domain_core.md`, `03_ui_workspace.md`, `04_api_contracts.md`, `07_data_persistence.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-034 | P0 | `06_agent_knowledge_services.md`, `05_application_use_cases.md`, `07_data_persistence.md` | `02_domain_core.md`, `03_ui_workspace.md`, `04_api_contracts.md`, `10_operations_deployment.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-035 | P0 | `02_domain_core.md`, `05_application_use_cases.md`, `07_data_persistence.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `06_agent_knowledge_services.md` | `08_security_permissions.md`, `09_quality_observability.md` | 初版映射 |
| FR-036 | P2 | `06_agent_knowledge_services.md`, `07_data_persistence.md` | `02_domain_core.md`, `03_ui_workspace.md`, `04_api_contracts.md`, `05_application_use_cases.md` | `08_security_permissions.md`, `09_quality_observability.md` | P2 扩展映射 |

### 3.3 能力族到分层文件

| FR 范围 | 主设计文件 | 协作设计文件 |
| --- | --- | --- |
| FR-001~007 账号、配置、管理员 | `02_domain_core.md`, `05_application_use_cases.md`, `08_security_permissions.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `07_data_persistence.md`, `09_quality_observability.md`, `10_operations_deployment.md` |
| FR-008~019 Project Workspace 通用能力 | `03_ui_workspace.md`, `04_api_contracts.md`, `05_application_use_cases.md`, `02_domain_core.md` | `06_agent_knowledge_services.md`, `07_data_persistence.md`, `08_security_permissions.md`, `09_quality_observability.md`, `10_operations_deployment.md` |
| FR-020~027 构建模式 | `06_agent_knowledge_services.md`, `05_application_use_cases.md`, `07_data_persistence.md` | `03_ui_workspace.md`, `04_api_contracts.md`, `02_domain_core.md`, `08_security_permissions.md`, `09_quality_observability.md`, `10_operations_deployment.md` |
| FR-028~031 深度研究模式 | `06_agent_knowledge_services.md`, `03_ui_workspace.md`, `05_application_use_cases.md` | `04_api_contracts.md`, `02_domain_core.md`, `07_data_persistence.md`, `08_security_permissions.md`, `09_quality_observability.md` |
| FR-032~036 主题综述模式 | `06_agent_knowledge_services.md`, `03_ui_workspace.md`, `05_application_use_cases.md` | `04_api_contracts.md`, `02_domain_core.md`, `07_data_persistence.md`, `08_security_permissions.md`, `09_quality_observability.md`, `10_operations_deployment.md` |
