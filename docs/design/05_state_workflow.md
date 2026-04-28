# 状态机与业务流程设计

状态：占位文档，待补齐。

## 分层定位

本文件用于承载 Project、Stage、Task、调度、取消、暂停、恢复、失败补偿等状态与业务流程设计。

当前相关内容分散在：

- [02_product_requirements.md](02_product_requirements.md)
- [03_architecture_decisions.md](03_architecture_decisions.md)
- [06_data_model.sql](06_data_model.sql)
- [07_api_contract.md](07_api_contract.md)
- [12_gap_decisions.md](12_gap_decisions.md)

## 待补内容

- Project 状态机：`idle` / `running` / `paused` / `error` / `archived`
- Stage 状态机：`running` / `paused` / `completed` / `failed`
- Task 模型选择：是否新增独立 `tasks` 表
- 构建模式七阶段流转
- 综述模式五阶段流转
- 模式切换前置检查
- 定时任务调度流程
- 取消、暂停、恢复、重试的幂等语义
- 失败恢复和补偿策略

## 当前待确认

详见 [12_gap_decisions.md](12_gap_decisions.md)：

- D-001 统一 Project / Stage / Task 状态模型
- D-005 构建阶段是否允许跳过
- D-006 深度研究图谱重建入口
