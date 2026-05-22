# Research Paper Base 设计文档集

文档版本：v1.1  
更新日期：2026-05-22  
适用项目大版本：v1  
权威基线：`01_functional_requirements.md`、`00_layers.md`

## 1. 权威性规则

1. `01_functional_requirements.md` 是需求含义、优先级和验收标准的最高依据。
2. `00_layers.md` 是当前架构分层、依赖方向和横切约束的基础蓝本。
3. 本目录其余文件是基于上述两份文档重写后的设计展开；若发生冲突，按 `01_functional_requirements.md` 裁决，并回写修订到相关设计文件。
4. 历史审计文件 `11_design_audit.md` 已废弃，不再迁入新版设计集。
5. 旧式大接口清单、质量控制和数据模型仅保留在 `backup/` 目录作为参考，不作为权威契约。
6. 旧 `12_gap_decisions.md` 的逐项审核结果见 `12_gap_decisions_review.md`；未关闭项应回写到对应新版设计文件。

## 2. 文件结构

| 文件 | 分层定位 | 主要回答 |
| --- | --- | --- |
| `00_layers.md` | 总览 | 系统分几层、层间如何依赖、横切约束是什么 |
| `01_functional_requirements.md` | 需求基线 | 系统必须满足哪些功能、优先级和验收标准 |
| `02_domain_core.md` | Domain Core | Project、Run/Session、论文、版本、内容保护等核心对象和规则 |
| `03_ui_workspace.md` | UI / Workspace | 登录后入口、Project Workspace、信息面板、状态/禁用态和对象切换 |
| `04_api_contracts.md` | API Boundary | HTTP/SSE/API 错误信封、资源命名、权限前置和端点骨架 |
| `05_application_use_cases.md` | Application Use Cases | 写操作入口、业务流程、状态推进、锁、配置快照和幂等 |
| `06_agent_knowledge_services.md` | Agent & Knowledge Services | Construction、Research、Review Agent 与 Knowledge 能力边界 |
| `07_data_persistence.md` | Infrastructure / Data | 关系库、文件、向量、图谱、版本和同步状态的持久化设计 |
| `07_data_schema.sql` | Infrastructure / Data | MVP 关系数据结构草案，供迁移实现参考 |
| `08_security_permissions.md` | AuthZ 横切约束 | 用户隔离、管理员边界、文件访问、密钥和审计 |
| `09_quality_observability.md` | Quality 横切约束 | 测试入口、错误分类、日志、健康检查和诊断快照 |
| `10_operations_deployment.md` | Operations | 本地/MVP 部署、调度、队列、备份、容量和演进策略 |
| `12_gap_decisions_review.md` | 迁移审核 | 依据旧 `12_gap_decisions.md` 逐项核对新版设计吸收情况 |
| `backup/` | 备份参考 | 旧 API 契约、质量控制、数据模型和数据需求，仅供查证 |

## 3. 阅读顺序

新任务优先阅读：

1. `01_functional_requirements.md`
2. `00_layers.md`
3. 与任务所属层对应的设计文件
4. `04_api_contracts.md`、`08_security_permissions.md`、`09_quality_observability.md` 中的横切要求

## 4. 修订要求

- 所有设计文件保持项目大版本 `v1.x`。
- 设计文档只描述稳定边界、流程、规则和骨架；字段枚举和端点细节可随实现补充，但不得违背 FR。
- P0/P1 需求必须能追踪到 UI 入口、应用用例、领域/Agent 规则、数据写入、权限检查和测试入口。
