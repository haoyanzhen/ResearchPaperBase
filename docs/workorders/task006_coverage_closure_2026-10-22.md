# Task006 需求测试覆盖补齐报告

文档版本：v1.0
更新日期：2026-10-22

## 结论与变更范围

[task006](../../tasks/006-public-error-recovery-contract.md)原有测试不足以覆盖其全部已实现的静态契约边界。本次补齐已识别缺口，新增[8组需求测试](../../scripts/tests/test_public_error_requirements.py)，原23方法保持不变，全部31方法通过。未发现需要修改现有机器契约的缺陷。测试期望来自04 §5/5.1及其指定的字段契约，动作/原因/长度均为固定测试输入，不从被测schema生成预期。

本次仅新增测试、更新任务单/项目状态及保存证据。未修改contracts、检查器、依赖或backend/frontend；不扩展task006业务范围。人工接受仍待记录。

## 缺口、追踪与结果

逐项规范来源及方法名见[task006 §8–9](../../tasks/006-public-error-recovery-contract.md#9-需求测试覆盖复核与补齐2026-10-22)。

| 缺口 | 补充验证 | 结果 |
| --- | --- | --- |
| 原42变体以空details/recovery为主；未验证全部合法建议或其他合法动作误配 | 42×10动作矩阵、42×5具名details矩阵；固定标签/缺字段/非法附加参数 | 通过 |
| 嵌套类型、长度、枚举及边界覆盖有限 | 6种具名嵌套对象的必填/类型/白名单；字段路径和6个字段原因、10个依赖原因、2个提交结果；数组1/100及0/101；消息、修订、URL上下限和危险URL | 通过 |
| 只抽取部分技术重试反例和一种Task拒绝 | 5类技术错误的90组合，每组合同时验证公共错误、Task与SSE；未知结果拒绝直接重试 | 通过 |
| 每变体只抽一个错误HTTP分组 | 42×16 HTTP分组矩阵，信封/meta/request_id及Task/SSE边界 | 通过 |
| 错误契约新增检查分支缺少专用漂移反例 | 覆盖变体遗漏、503响应错绑拒绝，删除Task/错误schema及429组件触发兼容检查 | 通过 |

ER-02原合成原因映射未执行任何生产投影，本次明确不把样例相等视为防枚举运行证明。实际授权、公开字段来源、自由文本脱敏、恢复动作资格、同键重放/并发/确认生命周期、Task GET 200及UI行为均待相应业务切片，不在task006已实现范围。逐端点响应绑定、完整Task/SSE/ConfirmationPreview仍按原覆盖清单保留缺项。本次不执行数据库或外部服务，也不宣称业务端到端通过。

## 当前执行证据

证据目录：[task006_coverage_2026-10-22](evidence/task006_coverage_2026-10-22/commands.json)。复用独立契约环境 `/tmp/rpb-a04-contract`，已核对jsonschema 4.23.0和openapi-spec-validator 0.7.2与requirements一致，完整版本见[dependencies.log](evidence/task006_coverage_2026-10-22/dependencies.log)。

| 命令（Python前缀为上述环境/bin/python） | 实际结果 | 日志 |
| --- | --- | --- |
| `-m unittest discover -s scripts/tests -v` | 退出0，31方法通过；包括原15+原公共错误8+新增8 | [tests.log](evidence/task006_coverage_2026-10-22/tests.log) |
| `scripts/check_api_contracts.py` | 退出0；159 schemas、126源行、42部分请求/成功操作、40仅请求操作、5/6事件payload | [structure.log](evidence/task006_coverage_2026-10-22/structure.log) |
| `scripts/check_api_contracts.py --baseline docs/workorders/evidence/a04_2026-10-22/reviewed-p0.openapi.json` | 退出1，83项历史差异；本次未改JSON，未出现新兼容差异 | [compatibility.log](evidence/task006_coverage_2026-10-22/compatibility.log) |

83项差异的方向及限定技术审查沿用[原审核包](evidence/a04_2026-10-22/review.md#兼容差异逐类处置)：82操作x-errors及1个SSE映射扩展。非零门禁保留，不能记作兼容无差异或人工批准。

修改前相关文件内容、SHA-256、HEAD和工作树状态保存在证据目录before/及before-sha256.json；本轮差异见[delivery.patch](evidence/task006_coverage_2026-10-22/delivery.patch)，当前输入及交付摘要见[delivery-sha256.json](evidence/task006_coverage_2026-10-22/delivery-sha256.json)。本次摘要不替换原审核包的历史摘要。文档引用、版本、行尾和原契约/测试保留核验见[document-check.json](evidence/task006_coverage_2026-10-22/document-check.json)。工程统一入口已使用全量unittest discover，无需修改以发现新文件。
