# 权限与安全设计

状态：占位文档，待补齐。

## 分层定位

本文件用于承载认证、授权、角色边界、数据归属、敏感信息保护、审计日志和防枚举策略。

当前相关内容分散在：

- [02_product_requirements.md](02_product_requirements.md)
- [06_data_model.sql](06_data_model.sql)
- [07_api_contract.md](07_api_contract.md)
- [09_quality_observability.md](09_quality_observability.md)
- [12_gap_decisions.md](12_gap_decisions.md)

## 待补内容

- 角色定义：普通用户、项目所有者、管理员
- 权限矩阵：用户、项目、论文关联、系统配置、推荐、导出文件
- 管理员能力边界
- 禁用账号后的 token 失效策略
- 403 与 404 防枚举规则
- API key、SMTP 密码等敏感配置加密和脱敏
- SSE 认证策略
- 审计日志字段和触发条件
- CSRF/CORS 策略

## 当前待确认

详见 [12_gap_decisions.md](12_gap_decisions.md)：

- D-004 SSE 认证方案
- D-010 管理员权限边界
- D-012 推荐点赞与审核
