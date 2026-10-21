# Research Paper Base

文档版本：v1.3
更新日期：2026-10-19

面向深度检索与学术研究的工作空间项目，目标包含论文库构建、基于知识版本的研究对话和文献综述。

**当前处于重建准备阶段，没有可启动的应用。** 旧后端、前端、迁移、测试与依赖环境已按独立审查清理；本轮没有实现新核心，也不再提供旧安装与启动步骤。

## 当前入口

- [项目进度](docs/PROJECT_STATUS.md)
- [现行设计索引](docs/design/README.md)
- [API 机器契约范围与验证命令](docs/design/04-03_machine_contract_governance.md)
- [内部模块与执行契约](docs/design/05-01_internal_module_contracts.md)
- [安全与交付设计细化记录](docs/workorders/security_delivery_refinement_2026-10-19.md)
- [数据、测试与文档清理记录](docs/workorders/data_test_design_cleanup_2026-10-19.md)
- [历史设计归档](docs/archive/design_retirement_2026-10-19/README.md)
- [核心重写计划](docs/proposals/core_rewrite_plan_2026-10-16.md)
- [独立审查与拆分结果](docs/proposals/reuse_independent_review_2026-10-16.md)
- [或许有用的逻辑存档](archive/maybe_useful/README.md)
- [实际清理记录](docs/workorders/legacy_cleanup_execution_2026-10-16.md)
- [逐文件处置清单](docs/workorders/legacy_cleanup_manifest_2026-10-16.json)
- [文件职责索引](docs/file_map.md)

## 重建边界

`archive/maybe_useful/` 仅为独立候选片段与规则材料，不是新应用。新实现采用其中内容前应按新契约核验，不恢复旧接口、旧状态机或旧依赖全集。

`docs/design/` 保留现行设计；旧07 SQL草案已删除，可执行数据结构由后续迁移维护。07为持久化协议，08为安全契约，09为架构/模块及SEC/OPS测试用例，10为运行与交付约束；未决政策在08/10单列。历史报告及工作单用于追溯，不是当前功能验收证据。既有 Git 历史未改写。

新核心的实现与环境安装将在后续独立任务中开始。

2026-10-19：新增独立 API 契约产物及检查工具。其依赖、运行命令和覆盖缺项见上述机器契约入口；这些检查不启动应用，不替代数据库或端到端验收。

本次修订 v1.2（2026-10-19）：同步07/09/10及退役归档入口，未启动应用实现。

本次修订 v1.3（2026-10-19）：同步安全与交付设计入口，未启动应用实现。
