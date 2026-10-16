# Research Paper Base

文档版本：v1.0
更新日期：2026-10-16

面向深度检索与学术研究的工作空间项目，目标包含论文库构建、基于知识版本的研究对话和文献综述。

**当前处于重建准备阶段，没有可启动的应用。** 旧后端、前端、迁移、测试与依赖环境已按独立审查清理；本轮没有实现新核心，也不再提供旧安装与启动步骤。

## 当前入口

- [项目进度](docs/PROJECT_STATUS.md)
- [现行设计索引](docs/design/README.md)
- [核心重写计划](docs/proposals/core_rewrite_plan_2026-10-16.md)
- [独立审查与拆分结果](docs/proposals/reuse_independent_review_2026-10-16.md)
- [或许有用的逻辑存档](archive/maybe_useful/README.md)
- [实际清理记录](docs/workorders/legacy_cleanup_execution_2026-10-16.md)
- [逐文件处置清单](docs/workorders/legacy_cleanup_manifest_2026-10-16.json)
- [文件职责索引](docs/file_map.md)

## 重建边界

`archive/maybe_useful/` 仅为独立候选片段与规则材料，不是新应用。新实现采用其中内容前应按新契约核验，不恢复旧接口、旧状态机或旧依赖全集。

`docs/design/` 保留设计与 SQL 草案；草案不等于已部署的数据模型。历史报告及工作单用于追溯，不是当前功能验收证据。既有 Git 历史未改写。

新核心的实现与环境安装将在后续独立任务中开始。
