# Task 006：A04 公共错误与恢复提示契约

文档版本：v1.2
更新日期：2026-10-22

## 1. 目标、授权与下一轮边界

用户于2026-10-22同意从A04推进，并要求新建task、约束下一轮范围。建单轮只建立任务单和状态入口；用户随后明确“开始task006”，本执行轮限于本单的契约设计、机器转写、契约测试及必要文档同步，不启动业务实现。

可观察结果：API、Task和UI的实现者能根据同一公共错误契约，确定安全展示字段、可空值、重试含义与恢复建议；对无权访问对象不暴露存在性，对提交结果未知不建议直接重新生成或换幂等键执行。

- 类型：设计与机器契约实现；关联A04、限定的B01、TRACK-004。A10仅实例化本单契约验收，不扩展为业务切片。
- 开始条件：A01基线可定位；读取当前工作区和有效规范。已有A01–A03及骨架的人工接受仍待审核，本任务不代填批准，也不将其变成独立契约设计的全局阻塞。
- 包含：公共错误原因映射、details/recovery具名结构、必填/可空规则、安全正负例、适用HTTP/Task/UI语义对应、机器覆盖与兼容审查、需求追踪及执行证据。
- 排除：A05–A09、Project创建幂等业务实现（Task 004仍为示例）、账号/权限服务、数据库和迁移、真实Worker、前端错误组件、完整Task/SSE/ConfirmationPreview结构、SDK或服务端DTO生成、Graph-RAG/Memory、生产部署及真实外部服务调用。
- 不改变：业务状态、权限边界、知识版本绑定、人工内容保护、已定P0/P1/P2和用户恢复入口。H01未被本次授权解锁，TRACK-005继续延期。

完成本单即停止并提交审核；不得因契约检查通过自动进入A05、A06或Project业务实现。执行本单内常规修复和复验无需重复询问。

## 2. 当前依据与基线

先读[AGENTS](../AGENTS.md)、[项目状态](../docs/PROJECT_STATUS.md)、[实施入口](../docs/IMPLEMENTATION_ENTRY.md)和[设计索引](../docs/design/README.md)。

| 规范与当前版本 | 采用规则与责任 |
| --- | --- |
| [A04定义](../docs/workorders/preimplementation_design_tasks_2026-10-21.md) v1.1 §3 | 公共错误安全词表和恢复提示闭合；仅阻塞实际消费这些结构的实现 |
| [04](../docs/design/04_api_contracts.md) v1.11 §5–7 | 公共信封、HTTP/category/code、修订确认与幂等规则；API边界对外投影 |
| [04-01](../docs/design/04-01_p0_operation_contracts.md) v1.6 §8.4及各操作专用错误 | 既有操作前置和安全恢复语义；不新增操作 |
| [04-02](../docs/design/04-02_transport_task_file_contracts.md) v1.5 | 异步失败通过Task投影；事件恢复不能变为业务重跑 |
| [04-03](../docs/design/04-03_machine_contract_governance.md) v1.1 §1–3 | 机器字段单一来源、真实覆盖与保守兼容门禁 |
| [08](../docs/design/08_security_permissions.md) v1.8 §3/5/8/10 | 授权、防枚举、脱敏及对外错误边界 |
| [09](../docs/design/09_quality_observability.md) v1.16 §2/4.4/6/7 | 需求追踪、安全反例及证据限制 |

涉及业务含义时继续核对01/02及相关UI附录。下一轮须在本表补齐实际涉及的FR子条目和已有ARC/MOD/API-R/SEC/TTF编号，不凭编号猜含义；本单ER编号只用于任务局部场景。

建单时HEAD为 `7ba2a2c638500eaa43f2137d16a6a0686b663630`，工作树已有大量修改及未跟踪的工程骨架。上一轮只读核验骨架交付清单85项摘要匹配，没有重跑工程测试。本单不把该记录作为A04验证证据。

下一轮修改前必须保存：当前HEAD、工作树状态、相关已跟踪与未跟踪文件的内容快照/差异及SHA-256、修改前OpenAPI与覆盖清单。建议证据目录为 `docs/workorders/evidence/a04_<执行日期>/`。先核对受审JSON来源；当前快照仅为修改前比较输入，未审查不得称为批准基线。既有修改必须保留。

## 3. 允许修改的落点

| 文件/产物 | 最小修改职责 |
| --- | --- |
| contracts/p0.openapi.json、contracts/p0.coverage.json | 公共错误具名结构、所需引用/响应和准确覆盖；已有成功响应及请求语义不借机重写 |
| scripts/check_api_contracts.py、scripts/tests/test_api_contracts.py | 必要的错误结构、组合约束、负例及漂移/兼容回归；需要时新增专用契约测试文件 |
| docs/design/04_api_contracts.md、04-01_p0_operation_contracts.md、04-03_machine_contract_governance.md | 原因到安全错误的映射、跨字段语义与覆盖限制；字段迁入JSON后移除重复维护 |
| docs/design/04-02_transport_task_file_contracts.md、08_security_permissions.md、09_quality_observability.md | 仅本次错误模型引用、投影与安全验收必要衔接；不填补其他任务的结构缺项 |
| 本任务、docs/PROJECT_STATUS.md、证据目录 | 追踪、实际结果、差异、审核与剩余缺项 |

03及05系列作为只读一致性核对来源；若发现需要改变交互或内部业务契约的缺口，先记录影响，不借A04扩大实现。源码backend/frontend、依赖与锁文件不在本任务修改范围。新增契约样例可以放入专用测试fixture目录，不能包含真实密钥或私人资料。

## 4. 验收规格与追踪

以下全部为契约层验收，无法单靠schema证明的运行时授权/事务行为明确留到对应业务切片。用例须从规范推导，不能用当前实现反推预期。

| 需求/场景 | 输入与预期 | 禁止副作用/反例 | 计划测试与证据 |
| --- | --- | --- | --- |
| ER-01 / 04 §5 | 逐个具名变体提供合法样例，明确必填、可空、枚举和嵌套结构 | 拒绝缺必填、错误类型、未知字段和不允许的变体组合；不得用任意object掩盖缺项 | 待编写公共错误schema正负例，待执行 |
| ER-02 / 08防枚举 | 不存在和不可披露对象使用一致的安全对外形态 | 不含对象存在性、其他Project标识、无权资源链接、私有内容 | 映射表审查及合成正负例；真实授权运行验证不在本单 |
| ER-03 / 04脱敏 | 内部Provider/存储失败映射为安全错误及request_id | 拒绝原始响应、SQL、堆栈、密钥、路径、字段原值进入约定输出；任意字符串的泄漏不能假称由schema全面保证 | 字段白名单测试、含敏感标记的合成投影样例审查；生产脱敏待实现 |
| ER-04 / 04 §6 | 修订冲突/缺修订/确认失效按既定规则提示刷新依据或补前置 | 不自动覆盖人工内容、扩大确认范围或将已受理确认误作失效 | 错误与恢复动作组合正负例，语义映射审查，待执行 |
| ER-05 / 04 §7 | 可重试技术失败、依赖不可用、提交结果未知有明确区别 | retryable不得表示业务重跑；未知结果不得建议换键、直接重生成或重复创建 | 重试/恢复映射表及组合样例，待执行；不新增业务状态 |
| ER-06 / A04恢复边界 | 无可用恢复动作时可为null；已有合法动作明确前提 | 不暴露未授权动作、不增加P0重跑入口、建议本身不执行操作 | 动作枚举/空值/非法动作测试，P0权限语义审查，待执行 |
| ER-07 / 04-02 | 同一原因在同步HTTP、异步Task与UI说明中含义一致；异步失败Task GET仍按现有规则响应 | 不把Task状态当业务状态、不把异步错误改为Task读取失败、不重跑恢复事件流 | 三种载体映射与适用结构样例，待执行；完整Task/SSE实现排除 |
| ER-08 / 04-03 | 本轮覆盖准确，已有请求/成功响应约束回归通过，兼容差异可解释 | 不弱化断言、不删除旧覆盖、不自动刷新摘要冒充语义审查、不用新JSON自比 | 原契约回归、结构/漂移检查、修改前后及受审基线比较，待执行 |

下一轮在本表或紧邻的追踪表补齐每项的规范子条目、具体测试路径/用例名和当前执行报告；每个纳入范围的公共错误变体均须有正负场景。无法确定的语义列出具体缺口，只暂停依赖部分；未闭合不得宣称A04全部完成。

## 5. 验证计划与交付门槛

使用独立契约Python环境，依赖来自 `contracts/requirements.txt`，不加载业务数据库、Provider或邮件配置。以下是现有入口的计划命令，本任务尚未执行：

```sh
<契约环境>/bin/python scripts/check_api_contracts.py
<契约环境>/bin/python -m unittest discover -s scripts/tests -p 'test_api_contracts.py' -v
<契约环境>/bin/python scripts/check_api_contracts.py --baseline <已核对来源的旧OpenAPI绝对路径>
```

新增测试文件若未被上述模式包含，须增加实际运行命令。保守兼容门禁可能因预期错误结构变更返回非零：记录差异、方向、影响与定向审查结论，不删基线或弱化检查使其变绿；未经处理的兼容问题继续标明未解决。

交付前还须核对：所有ER场景及受影响原用例、引用/版本/日期、JSON与Markdown单一维护、Task/UI语义、防枚举和恢复权限边界、限定diff及已有修改保留情况。证据绑定当前文件摘要，写明静态检查、契约测试、未执行运行验收的区别。只运行与修改有关的检查，无需以未修改应用的全量构建代替契约验收。

成功门槛：本范围规则有明确落点；全部可测契约要求及回归通过；兼容差异完成所需审查且如实记录；无未处理阻断缺口；交付单一审核包。API、真实数据库、UI、Worker和端到端业务验收仍未完成，TRACK-004仅更新A04子范围。

## 6. 决策与人工审核

目前无新增业务决定。若必须增加恢复操作、改变权限/状态/分期等，列出问题、规范证据、选项与影响、推荐及仅被阻塞部分，等待人类决定；独立工作继续。不要重新询问已确认政策，也不要自动恢复H01。

人工审核包包含：原因映射表、具名schema与正负例、API/Task/UI对应、兼容diff、需求追踪、实际命令/结果及未覆盖项。重点抽查ER-02/03防泄漏、ER-04人工保护、ER-05未知结果和ER-06恢复权限。

审核者/日期：待人工填写；接受基线/范围：待填写；审核结论：未审核。

当前状态：A04公共错误设计及机器契约已交付，契约自动验证通过；兼容门禁预期非零，定向技术审查已记录；人工接受未记录。建单历史证据见第7节，执行轮结果见第8节。

## 7. 本轮建单验证

本轮仅新增本任务并同步项目状态；未修改业务规范、机器契约或应用代码。已执行只读文档检查：本任务及项目状态共62个本地引用目标存在；ER-01–08场景齐全；版本、日期及行尾空白检查通过；项目状态的限定 `git diff --check` 通过。未执行应用或契约测试，因本轮未修改这些产物；不将任务规格视为A04已完成。

## 8. 执行轮交付（2026-10-22）

单一审核包：[交付与兼容审查](../docs/workorders/evidence/a04_2026-10-22/review.md)。第2节规范版本表及第4–5节的“待编写/待执行”描述保留为建单输入；当前执行状态由本节和包内日志替代。变更后04/04-01/04-02/04-03/08/09分别为v1.12/v1.7/v1.6/v1.2/v1.9/v1.17。未变更业务规则、原成功响应/请求或应用源码。

| 局部要求 | 已核对规范子条目及既有验收入口 | 可执行场景与当前证据 |
| --- | --- | --- |
| ER-01 | 04 §5/5.1；ARC-08 | `test_er01_every_variant_required_null_types_unknown_and_category`：42个变体合法空值、必填/类型/未知字段/错误类别/非法动作/HTTP分类；public-errors.log通过 |
| ER-02 | FR-008 Project可用性约束、04 §4、08 §3；ARC-02、SEC-01/02、TTF-02/07 | `test_er02_unavailable_indistinguishable`：合成缺失/越权统一形态，禁止私有details及差异消息；通过；真实鉴权待业务切片 |
| ER-03 | FR-002/007凭据保护、08 §5/12.2、04 §5；SEC-04/05 | `test_er03_closed_details_and_sanitization_limit`：拒绝六类原始诊断字段，安全原因正例；明确自由文本不保证脱敏；通过 |
| ER-04 | FR-017验收“人工修改不会静默覆盖”“重新生成需确认”、04 §6；ARC-04/07、SEC-03、API-R03/05 | `test_er04_revision_confirmation_and_no_overwrite`：修订/确认动作、引用/缺字段/force反例；通过；已受理确认不因TTL失效按04 §5.1审查，实际执行未验证 |
| ER-05 | FR-015功能范围“结果未明显示核验中”、04 §7第2–5项；ARC-03、TTF-01 | `test_er05_submission_unknown_and_safe_retry`：五类技术错误的已知未受理/未知结果、组合反例、禁换键和重跑；通过；真实提交与竞争仍未执行 |
| ER-06 | FR-014/015 P0/P1分期、FR-017确认保护、03-04冲突/恢复交互、04 §5.1 | `test_er06_named_details_and_action_boundaries`及ER-01/05：具名字段、无动作可空、配置/认证/游标建议、不新增执行入口；通过；实际动作资格待实现 |
| ER-07 | FR-015错误展示与FR-028流式回复、04 §3、04-02 §2/3；ARC-07、TTF-06/13 | `test_er07_shared_carriers_not_task_http_failure`：共享错误、Task/SSE禁止直接请求重试；通过；Task GET 200语义按04-02审查，无完整Task运行验收 |
| ER-08 | 04-03 §1–3；ARC-08 | `test_er08_existing_requests_success_and_bindings_preserved` + 原`ContractTests`15项：全部旧schema及操作除错误引用外保持相等；通过；兼容门禁83项审查见审核包 |

测试文件为 `scripts/tests/test_public_errors.py`（上述8方法）及 `scripts/tests/test_api_contracts.py`（原15方法，未改断言）。独立契约环境运行命令、退出码和完整日志在审核包；结构检查159 schemas、126源行、42请求/成功局部操作+40仅请求操作、5/6事件payload通过。`--baseline`退出1已保留，不能宣称无差异兼容通过。原成功/请求不变不代表新增错误全部运行安全。

静态可判定要求已执行通过；运行时授权/脱敏、并发与事务、确认生命周期、UI动作执行均不在本单实现范围。逐端点错误响应绑定、完整Task/SSE/ConfirmationPreview仍由覆盖清单跟踪。无新增人类决策问题；下一步为人工审核本包，不自动开始后续任务。审核者、接受范围及基线仍待人工填写。

工作区并行变化：最终摘要核对发现README、task005及若干骨架测试/脚本与开始时不同，具体列表见审核包preservation.json；本任务未写入或回滚这些文件，来源待核实，不纳入A04接受基线。契约相关受审文件及执行证据单独绑定摘要。


## 9. 需求测试覆盖复核与补齐（2026-10-22）

用户授权检查task006实现范围并补足需求测试。复核结论：原8方法覆盖基本正负例，但未完整验证具名嵌套边界、全部合法动作的跨错误码误用、全部HTTP分组互斥和技术重试组合，因此原覆盖不足。新增[需求测试](../scripts/tests/test_public_error_requirements.py)8方法；保留原23方法和全部既有断言，未改机器契约、检查器、业务源码或业务规则。当前单一复核入口为[覆盖补齐报告](../docs/workorders/task006_coverage_closure_2026-10-22.md)，原第8节审核包作为历史交付证据保留。

| 需求 | 本次补齐的可执行测试（PublicErrorRequirementTests） | 可观察断言与限定 |
| --- | --- | --- |
| ER-01 | `test_er01_er04_er06_all_actions_and_details_are_reason_specific`、`test_er01_er03_nested_required_types_and_whitelists`、`test_er01_er03_field_paths_enums_and_array_boundaries`、`test_er01_er07_all_http_statuses_and_envelope_boundaries` | 42变体×10动作、42变体×5非空details；必填/类型/空值/消息长度；字段数组1/100接受、0/101拒绝；每种HTTP分组两两排斥 |
| ER-02 | `test_er02_er06_recovery_labels_and_closed_objects`及动作矩阵 | 404拒绝所有具名details和非空动作；保留原固定消息反例；无生产映射器，不将合成缺失/越权样例相等当真实防枚举验证 |
| ER-03 | `test_er01_er03_nested_required_types_and_whitelists`、`test_er01_er03_field_paths_enums_and_array_boundaries`、`test_er03_er04_reference_and_revision_boundaries` | 嵌套对象拒绝诊断字段；原因枚举、字段路径、URL边界；URL语法不证明授权，自由文本脱敏仍未实现 |
| ER-04 | 动作矩阵及`test_er03_er04_reference_and_revision_boundaries` | 修订/确认/版本错误仅接受各自建议；修订1/128接受、0/129拒绝；运行时确认和人工保护仍待业务切片 |
| ER-05 | `test_er05_er07_complete_submission_retry_truth_table` | 5技术错误×3结果×2重试标志×3建议=90组合；未知结果只能核查；同组合验证PublicError/TaskError/ErrorPayload |
| ER-06 | 动作矩阵及`test_er02_er06_recovery_labels_and_closed_objects` | 全部合法建议正例、其他已存在动作反例、固定标签/必填/未知字段；不新增恢复入口 |
| ER-07 | `test_er01_er07_all_http_statuses_and_envelope_boundaries`及90组合测试 | 42变体跨16状态分组、Task/SSE基本正例与已受理禁重试；信封及request_id边界；不声明完整Task GET/UI运行通过 |
| ER-08 | `test_er08_error_coverage_and_response_drift_rejected`及原ContractTests/ER-08 | 错误覆盖遗漏、响应错绑拒绝；删除错误/Task约束或429组件触发兼容审查；原请求/成功响应回归保留 |

以上规范来源沿用第8节逐项映射；枚举、长度、具名结构按04 §5.1指定的机器字段契约写成固定预期，未从schema动态生成期望。新增测试由既有工程入口的unittest discover自动发现。当前执行日志、命令、输入快照和SHA-256见报告；契约测试通过不替代人工接受或端到端验收。
