# 分层设计文档群

本文档群按照 Web App 设计分层组织。旧根目录文档保留为兼容入口，新设计维护应优先编辑本目录文件。

| 层级 | 文档 |
| --- | --- |
| 模板 | [01_design_layer_template.md](01_design_layer_template.md) |
| 分层总览 | [00_index.md](00_index.md) |
| 产品与需求层 | [02_product_requirements.md](02_product_requirements.md) |
| 架构决策层 | [03_architecture_decisions.md](03_architecture_decisions.md) |
| 信息架构与 UI 交互层 | [04_information_architecture_ui.md](04_information_architecture_ui.md) |
| 状态机与业务流程层 | [05_state_workflow.md](05_state_workflow.md) |
| 数据模型层 | [06_data_model.sql](06_data_model.sql), [06_data_requirements.md](06_data_requirements.md) |
| API 契约层 | [07_api_contract.md](07_api_contract.md) |
| 权限与安全层 | [08_security_permissions.md](08_security_permissions.md) |
| QA 与可观测层 | [09_quality_observability.md](09_quality_observability.md) |
| 运维部署与演进层 | [10_operations_deployment.md](10_operations_deployment.md) |
| 设计审计层 | [11_design_audit.md](11_design_audit.md) |
| 待确认决策层 | [12_gap_decisions.md](12_gap_decisions.md) |

兼容入口：

- `../spec.md` -> `02_product_requirements.md`
- `../ADR_design.md` -> `03_architecture_decisions.md`
- `../ui_design.md` -> `04_information_architecture_ui.md`
- `../schema.sql` -> `06_data_model.sql`
- `../api.md` -> `07_api_contract.md`
- `../qa_design.md` -> `09_quality_observability.md`
- `../design_layer_template.md` -> `01_design_layer_template.md`
- `../design_layers.md` -> `00_index.md`
- `../design_audit.md` -> `11_design_audit.md`
- `../design_gap_decisions.md` -> `12_gap_decisions.md`
