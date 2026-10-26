# Task014：B01 Project.Create机器契约切片

文档版本：v1.1
更新日期：2026-10-24

## 1. 目标与授权

用户原文：“继续按 project-delivery 流程推进 B01，核对已有任务单和契约覆盖，确定首个机器契约转写切片，完成本轮交付、自验及独立审查，再提交我审核。”本轮确定POST /projects（Project.Create）为首片，补请求边界、成功元信息和错误响应的机器表达及契约测试，完成S1–S3后交S4。

复用task004的Project创建语义和T01–T10边界，但task004仍为示例，不在其上冒充应用实现。本单独立负责B01机器层及自身A10规格。task005工程骨架已接受；task006 A04已接受；task007 A05尚待接受且本片不消费；task008/010–012限定设计已接受，本同步新建操作不消费Task/确认预览/SSE/图谱。task009/013仅独立规划。无现有B01执行单与本片重叠。

可观察结果：现有JSON Schema工具接受合法创建请求、201/重放及适用错误，拒绝越界写字段、非法幂等键、同步完成null期限和不适用错误；覆盖清单与静态门禁准确反映范围。不实现账号/Project应用、真实HTTP/存储/并发/SDK，不扩大为全B01或FR-008完成。关联TRACK-004、012a/012e；其运行范围继续开放。

## 2. 依据与基线

已核对AGENTS、[状态](../docs/PROJECT_STATUS.md)、[设计索引](../docs/design/README.md)、[实施入口](../docs/IMPLEMENTATION_ENTRY.md)、[B01/A10](../docs/workorders/preimplementation_design_tasks_2026-10-21.md)、[task004](004-project-create-idempotency-example.md)及04系列。

| 规则 | 操作/所有者与本轮表达 |
| --- | --- |
| 01 FR-008；04-01 §3；02 Project/Construction容器 | Project.Create创建Owner为当前主体、默认active；本轮沿ProjectWrite/View，不新增可写Owner/status，不以schema证明容器原子创建。 |
| 04 §3/5；08当前身份/安全投影 | sessionCookie、CSRF、201/Location/no-store；具名错误状态及安全组件绑定，无权限服务实现。 |
| 04 §7；05 §3；07 §6.1；task004 T09/T10 | 幂等键16–128可打印ASCII；同步完成到期非null；真实至少24h、持久E一致、重放当前request_id由后续B03验证。 |
| 04-03及A04 | JSON单一字段来源、错误适用性按操作细分、兼容变化必须定向审核；不扩大其他端点。 |

[入场](../docs/workorders/evidence/task014_b01_2026-10-24/before/source-manifest.json)保存197文件及tar，含未提交/未跟踪内容；[entry](../docs/workorders/evidence/task014_b01_2026-10-24/entry.json)保存授权、HEAD及范围。[旧OpenAPI](../docs/workorders/evidence/task014_b01_2026-10-24/before.openapi.json)来自改动前实际工作树，不用新文件自比，不称全JSON都已人工接受。

## 3. 修改落点与取舍

| 文件 | 职责/边界 |
| --- | --- |
| contracts/p0.openapi.json | 仅Project.Create头/成功meta/错误绑定，新增ProjectCreateMeta；通用IdempotentMeta保持允许异步null。 |
| contracts/p0.coverage.json | 本操作由request-success-partial到request-success-errors-partial，保留GAP-RUNTIME；其余操作不提高覆盖。A07待审核陈旧说明更正为设计已接受/转写未做。 |
| scripts/check_api_contracts.py | 本片错误/成功绑定、头、期限及覆盖漂移门禁，不削弱既有检查。 |
| scripts/tests/test_project_create_contract.py | PC-01–08需求正负例与漂移/兼容回归；纯schema，无业务库或外呼。 |
| scripts/tests/test_public_errors.py | 旧A04快照断言逐项扣除本片已明确变更后继续完整比较；不跳过Project.Create或其他操作。 |
| 04-03、项目状态、本单与审核包 | 当前覆盖、接受边界、兼容方向、证据和S阶段交接。 |

本片无异步Task/SSE或持久命令载荷，因此事件与schema_version/旧载荷处理不适用于本次wire产物；后续B03持久化命令必须独立版本化，不拿OpenAPI info.version冒充持久schema_version。本轮不生成重复手写DTO和路由；先收口机器结构，后续应用消费时另交适配及运行证据。

## 4. A10验收与需求追踪

| 场景/规范 | 前置、动作和反例 | 观察与禁止副作用 | 可执行测试 |
| --- | --- | --- | --- |
| PC-01 / FR-008、04-01 §3 | 合法名称1/200，空白/null/类型/201字符；描述0/10000/10001；Owner/status/修订/force/确认字段 | 合法通过、错误拒绝；不默认填PATCH或调用任何应用 | test_pc01_request_boundaries_and_no_owner_status_revision |
| PC-02 / 04 §2/3/7 | session/CSRF/幂等头必需；key16/128/UUID及15/129/中文/尾换行；JSON创建与Location | 请求结构及头声明准确；尾换行拒绝；无假HTTP执行 | test_pc02_headers_and_creation_transport |
| PC-03 / 04 §7.5/6、task004 T10 | 固定ProjectView+本次meta、可选original_request_id；null/非法期限、缺字段/未知字段/Task | 201具名信封且期限非null；异步通用meta仍容许null，不影响其他操作 | test_pc03_success_meta_requires_real_expiry_and_closed_envelope |
| PC-04 / 04 §5、重放可见性 | 每个本片状态遍历42个公共错误变体 | 仅约定子集通过，不绑定游标/管理员/Provider/版本/修订等无关错误 | test_pc04_exact_errors_and_all_unrelated_variants_rejected |
| PC-05 / A04未知提交结果 | 500/429 outcome=unknown合法核查；强制retryable与原始SQL字段反例 | 受约束恢复与脱敏结构不放宽；不声称自由文本语义脱敏已实现 | test_pc05_safe_failure_projection_and_unknown_outcome |
| PC-06 / 04 §3/5 | 全部响应no-store，429 Retry-After 0合法/负数非法 | 头声明必需且值受约束；真实HTTP发送待实现 | test_pc06_no_store_and_retry_after |
| PC-07 / 04-03 | 深拷贝删401、放宽409子集、移除缓存、Location变可选、覆盖降级或meta回通用 | 检查器必须失败；原JSON字节不被变异测试改写 | test_pc07_drift_guard_rejects_missing_or_widened_bindings |
| PC-08 / 04-03 | 已有操作改变；另与真实入场JSON比较 | 保守兼容门禁报告需定向审核，禁止抹掉失败改自比 | test_pc08_existing_operation_change_still_requires_review |

上述用例均在scripts/tests/test_project_create_contract.py，执行证据见审核包；场景输入及期望来自规则，错误集合显式列出而非从新schema生成正确答案。无数据库或文件存储写入，无并发屏障需要；测试仅深拷贝内存并读取仓库JSON。真实身份、CSRF、重复/并发/原子容器创建、24h保留、跨主体防重放、request_id与持久到期一致性继续由task004运行场景及后续B02/B03承担，未执行。

## 5. 自验与限制

新增负例先对旧JSON/检查器运行，失败日志red.log保留；补齐后green.log暴露尾换行既有缺陷，局部修复后重跑。全契约回归、结构、文档引用/版本、完整快照和实际入场兼容差异均需检查；具体输出在[审核包](../docs/workorders/task014_b01_review_2026-10-24.md)。只运行独立contracts/.venv，不连接业务/Provider，不运行无关应用测试。源码快照包含未提交/未跟踪文件，证据独立保存。

## 6. 人工审核

审核本操作错误适用性、同步期限收紧、幂等键边界修复和兼容非零差异；不改变既定业务语义。建议接受限定机器层交付后进入S5–S7；修订则回S2/S3。2026-10-24用户已接受本片及所列兼容差异，见第9节；其他任务与运行验收不代填。

## 7. 单一报告

[task014审核包](../docs/workorders/task014_b01_review_2026-10-24.md)维护实际命令、正负例、兼容方向、独立发现、快照和限制。

## 8. 顺序交付检查点

唯一队列task014，授权见第1/9节。S1–S7已完成（限定机器契约收口）。S1明确范围及入场；S2新增8组/全量66项契约及结构通过；S3独立复审无剩余阻断项；S4用户于2026-10-24接受本轮交付及POST /projects定向兼容差异；S5逐PC复核无新增缺口；S6无需修改；S7文档/结构/快照和接受基线兼容复验通过。机器产物、检查器及测试与已接受基线完全一致，本次仅更新本单、审核包和项目状态的接受/执行记录。

最终基线和证据见审核包收口节；原入场兼容退出1保留，不改写为通过，也不扩大接受为其他操作或整个JSON历史。当前队列已完成，其他B01切片、B02/B03应用及数据库等运行任务未获本轮授权。

## 9. 人工接受与收口（2026-10-24）

用户原文：“接受 task014 本轮 B01 Project.Create 机器契约限定交付及所列兼容差异，继续按 project-delivery 流程完成 S5–S7，更新任务单和项目状态。”接受PC-01–08及审核包所列POST /projects请求/响应方向差异，绑定delivery清单SHA256 `230a2d99687b18d52a0b1b180a0521c336f8e9ce942e4b4f3fb351879d9915aa`（200文件）。恢复核验无漂移；从该归档提取的accepted.openapi.json SHA256为 `57117f10787b72899818cf6829550cc71e77073298ac437fc6d67791cec18dfa`，只作为可重定位比较产物，不代表用户接受其他操作。

[S5–S7记录](../docs/workorders/task014_b01_review_2026-10-24.md#人工接受后的s5s7执行记录)维护逐项覆盖、简化判断、实际检查和最终快照。原66项契约运行证据对应未变代码，复用而非重复测试；本次重跑结构和两份真实基线兼容检查。没有审核后实质改动，无需新独立审查或重复接受记录本身。机器契约、限定自动验证及人工接受已完成；真实HTTP、身份权限、持久化/去重/原子事务仍未实现或验收。
