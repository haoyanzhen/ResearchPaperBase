# 运维部署与演进设计

状态：占位文档，待补齐。

## 分层定位

本文件用于承载环境变量、依赖服务、部署拓扑、数据库迁移、备份恢复、日志采集、容量规划和版本演进策略。

当前相关内容分散在：

- [02_product_requirements.md](02_product_requirements.md)
- [../file_map.md](../file_map.md)
- [09_quality_observability.md](09_quality_observability.md)
- [12_gap_decisions.md](12_gap_decisions.md)

## 待补内容

- 本地开发部署
- Docker Compose 部署
- 生产环境部署建议
- 环境变量清单
- PostgreSQL / ChromaDB / 文件存储 / GraphML 持久化策略
- Alembic 迁移和回滚流程
- 定时任务部署形态
- 备份和恢复
- 日志采集、监控、告警
- 容量估算和成本控制
- 版本升级策略

## 当前待确认

详见 [12_gap_decisions.md](12_gap_decisions.md)：

- D-008 PostgreSQL 与 ChromaDB 一致性策略
- D-009 文件存储和导出生命周期
- D-015 部署与迁移文档
