# Operations & Deployment 设计

文档版本：v1.1  
更新日期：2026-05-20  
依据文档：`00_layers.md`、`01_functional_requirements.md`

## 1. 设计目标

运维设计覆盖 MVP 运行拓扑、配置、调度、队列、存储、备份、清理和后续演进。早期优先保证适配器边界清晰、长任务可恢复、数据不误删。

## 2. MVP 拓扑

```text
Web App
  -> API Server
  -> Relational DB
  -> File Storage
  -> Vector Store
  -> Graph Store
  -> Worker / Scheduler
  -> External Providers
```

MVP 可将 API、Worker、Scheduler 部署在同一服务内，但代码边界必须保留，后续可拆分。

## 3. 环境配置

必需配置包括数据库连接、文件存储位置或对象存储桶、Secret Store 或密钥加密配置、系统管理员初始化策略、会话签名密钥、Worker 并发上限、Scheduler 全局开关和周期。

管理员维护系统默认 LLM、系统默认数据源、SMTP、模型白名单、允许数据源范围、系统速率和并发硬限制。

## 4. 调度与后台任务

后台任务类型：

- 自动 Construction Run 调度。
- Construction Pipeline。
- PDF 下载解析。
- 向量化和图谱构建。
- Email Push。
- Export Job。
- Project 私人资产清理。
- 外部存储同步补偿。

调度要求：

- 只扫描 active Project。
- Project 级调度锁防止重复创建。
- 同一 Project active Construction Run 冲突时跳过或延后。
- 每次调度记录创建、跳过、延后和失败原因。

## 5. 容量基线

最小 MVP 估算：20 用户、每用户 10 个 Project、每 Project 100 篇论文、PDF 平均 10 MB。粗略文件容量 20 GB PDF 起步，建议预留 50 GB 以上用于解析文本、图谱、向量索引、导出和临时文件。

需要定期观察 PDF 存储增长、向量索引大小、Graph 文件或图数据库大小、导出文件保留量、Provider 调用成本和限流。

## 6. 备份与恢复

最低要求：

- 关系库定期备份。
- 文件存储可按 Project 和对象 key 恢复。
- Secret Store 备份与主库分开管理。
- 向量库和图谱可由 Knowledge Version 关联数据重建，或定期快照。

恢复后必须校验 Project 权限、Knowledge Version 可用性、文件签名访问、向量/图谱同步状态。

## 7. 清理策略

清理类型：

- Project 私人资产清理：用户确认后执行。
- 临时文件清理：按过期时间自动清理。
- 失败任务残留清理：保留诊断摘要后清理临时产物。
- 导出文件生命周期：默认保留，后续可按策略过期。
- 无引用全局论文身份清理：不属于 MVP 默认行为，需单独规则。

任何清理不得破坏其他 Project、其他用户或全局共享论文身份。

## 8. 部署演进

演进顺序：单服务 + 内嵌 Worker、API 与 Worker 分离、独立 Scheduler、独立队列和重试系统、独立对象存储/向量库/图数据库、集中日志/指标/告警和管理员 Inspector。

## 9. 运维风险

| 风险 | 缓解 |
| --- | --- |
| Provider 限流导致任务失败 | 配置速率上限、重试、调度延后 |
| PDF 下载占满磁盘 | 存储配额、清理策略、容量告警 |
| 向量/图谱与关系库不一致 | 同步项、补偿任务、发布前校验 |
| 自动调度重复执行 | Project 调度锁和幂等键 |
| 密钥泄漏 | Secret Store、脱敏日志、快照不保存明文 |
| 清理误删共享论文 | 全局论文与 Project 私有关联分离 |

## 10. 发布检查

- 数据迁移可回滚或可重跑。
- P0 环境变量齐全。
- 管理员账号初始化路径可用。
- 数据库、文件存储、Worker、Scheduler 健康检查通过。
- 至少一次 Construction -> Knowledge Version -> Research/Review 读链路验证通过。
