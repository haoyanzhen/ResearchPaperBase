# 运维部署与演进设计

状态：占位文档，待补齐。

## 分层定位

本文件用于承载环境变量、依赖服务、部署拓扑、数据库迁移、备份恢复、日志采集、容量规划和版本演进策略。

当前相关内容分散在：

- [02_product_requirements.md](02_product_requirements.md)
- [../file_map.md](../file_map.md)
- [09_quality_observability.md](09_quality_observability.md)
- [12_gap_decisions.md](12_gap_decisions.md)

## 合规与运行约束

### 外部学术数据库使用

- 系统必须遵守 arXiv、OpenAlex、Semantic Scholar、ADS 等外部学术数据库的 API 使用条款。
- 系统必须遵守各数据源的速率限制、认证要求、引用要求和禁止用途。
- 自动构建任务应具备失败降级和重试上限，避免因调度错误造成对外部 API 的异常请求压力。

### 隐私与数据保护

- 系统必须保护用户账号、Project、个人配置、研究对话、导出文件和通知收件人信息。
- 用户级 API key、系统级 API key、SMTP 密钥等敏感配置不得明文返回前端或写入日志。
- 管理员操作用户账号、系统级配置和密钥类配置时，应保留可审计记录。

### 版权与论文文件使用

- 系统下载、缓存、解析和导出论文 PDF 时，必须遵守论文来源和出版方的版权约束。
- 论文 PDF 导出、ZIP 打包和本地缓存应限制在用户有权限访问的 Project 范围内。
- 下载失败或版权限制导致无法获取全文时，应允许使用摘要作为降级文本，不应绕过来源限制。

### 成本与容量约束

- LLM API 月度预算、同时在线用户数、单次任务论文数量、Graph-RAG 检索性能和图谱构建性能以 [02_product_requirements.md](02_product_requirements.md) 的非功能需求为准。
- 部署方案应为 LLM 调用、外部 API 调用、PDF 存储、导出文件和任务日志设置容量上限或清理策略。

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
