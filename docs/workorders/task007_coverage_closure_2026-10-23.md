# Task007 需求覆盖独立审计与补齐

文档版本：v1.0
更新日期：2026-10-23

## 结论与范围

原有测试不足以证明task007全部可测契约要求。本轮按任务第6节N-T01–08逐项从04公共协议、04-01 §10、08-01及03附录推导预期，新增8个测试方法，补齐已识别的机器契约覆盖缺口；发现并修复五端点48个错误响应漏声明`Cache-Control: no-store`。58项合并契约测试、75项后端回归及结构检查通过。不将此结论表述为所有业务需求已覆盖或端到端验收通过。

任务第1–5节R01–R04工程历史也纳入复核：包边界正反例、Worker无输出/半行/提前退出的有限等待与清理、精确200与201反例、空/二进制/无末尾换行快照及清单缺少/篡改/多余/不可覆盖均已有可执行测试，本轮75项后端测试覆盖这些回归。未改变工程源码，未重复干净安装、wheel构建或浏览器交付验证；这些历史证据不算本轮重新执行。

## 实际工作树与变更归属

入场存在大量已修改和未跟踪文件，均保留。读取时两个分类POST仍引用通用读取类型；既有`test_material_policy_review_regressions.py`已经出现。运行前检测到其他工作将分类成功收窄、要求非空幂等期限并调整原测试；因此保存的`before.openapi.json`与首轮15项测试是并行修复后的快照，不能声称本轮复现或修复了旧R01/R02。该修复及主动文字澄清由[独立修复记录](task007_fixes_2026-10-23.md)维护。

本轮归属：新增`scripts/tests/test_material_policy_coverage.py`；OpenAPI五个资料端点的48个错误响应增加no-store，版本1.4.0→1.5.0；本报告、task007及状态入口登记。未改变请求、权限、分类政策、业务状态或新开A06。`pre-cache.openapi.json`是本轮缓存声明修复的准确前态；旧报告和旧日志不覆盖。

## 需求到测试的逐项追踪

新方法均在`test_material_policy_coverage.MaterialPolicyCoverageTests`。既有主类在`test_material_policy_contracts.MaterialPolicyContractTests`；R01/R02在`test_material_policy_review_regressions.MaterialPolicyReviewRegressionTests`。下表的“通过”仅指机器契约与声明，运行限制见下一节。

| 任务需求 / 规范 | 既有覆盖与本轮补齐 | 可执行定位 |
| --- | --- | --- |
| N-T01 / DAP-01/03：作用域、仅公开默认投影、风险同意 | 既有两模式风险组合、禁写他人主体；新增GET/PUT允许关闭后保留旧风险时间、初始null与开启非null；五操作scope精确断言 | `test_nt01_policy_read_and_update_preserve_prior_risk_audit`、`test_nt04_nt08_parameters_are_required_in_correct_locations`；既有`test_nt01_scope_and_risk_combinations` |
| N-T02 / DAP-04/09：分类/确认独立、确认事实 | 既有public/private×confirmed/unconfirmed×事实；并行回归确保两个POST必须confirmed及非空完整事实，GET仍可未确认；本轮嵌套成功字段验证 | `test_nt08_success_envelopes_and_nested_required_fields`；既有`test_nt02_classification_confirmation_is_independent`、`test_r01_each_mutation_requires_confirmed_fact` |
| N-T03 / DAP-02/06：具体来源、Owner显式依据、正文保护 | 既有禁止DOI/hash/content/force、普通ProjectPatch/Workspace绕过；新增逐实际写端点的缺字段/错类型/伪造主体、来源及确认token反例，确认事实依据长度和确认人格式 | `test_nt03_nt08_each_write_validates_actual_request_binding`、`test_nt05_nt08_readonly_revisions_identities_and_fact_boundaries`；既有`test_nt03_identity_basis_and_no_metadata_bypass` |
| N-T04 / FR-008、04：归档、越权、修订冲突 | 既有五操作授权、全部适用/不适用错误码绑定；新增路径UUID与必需头的准确位置/required、幂等键16/128正例及15/129/非ASCII反例；404/500禁止来源诊断与成功数据混入 | `test_nt04_nt08_parameters_are_required_in_correct_locations`、`test_nt04_nt07_errors_cannot_carry_success_or_source_diagnostics`；既有`test_nt07_exact_error_reasons_and_status_envelopes` |
| N-T05 / DAP-07/12/13/14：新修订、当前三边界、冻结范围 | 既有请求修订边界及non-reusable/read/dispatch/commit/preserves声明；新增所有响应的revision及具体内容revision 1/128正例、空/129反例 | `test_nt05_nt08_readonly_revisions_identities_and_fact_boundaries`；既有`test_nt05_nonreusable_revisions_and_frozen_scope_contract` |
| N-T06 / DAP-05/08/15：可信来源及受限提示 | 既有6类来源、scope、dependency组合与6类notice；新增三个来源响应端点实际嵌套绑定的6×3×3组合，包含伪造scope格式；确认完整依赖不等于public的设计约束 | `test_nt06_provenance_variants_remain_bound_in_each_source_response`；既有`test_nt06_provenance_and_restricted_notice_variants` |
| N-T07 / A04、04 §4/7：同步结果、错误、Task、幂等及缓存 | 既有200/无202/无伪Task、错误子集及TaskError限制；并行回归补非空UTC期限/重放original_request_id；本轮补全五操作成功和所有错误响应no-store、错误/成功信封不可互换 | `test_nt07_private_responses_never_advertise_shared_caching`、`test_nt04_nt07_errors_cannot_carry_success_or_source_diagnostics`；既有`test_r02_each_mutation_requires_nonnull_utc_expiry` |
| N-T08 / 04-03：必填/空值/枚举/类型/未知字段/准确覆盖 | 既有对象级反例、删除操作/开放写字段/错绑错误的漂移与兼容检查；本轮从各端点引用验证实际请求、响应meta/data/source/provenance/confirmation嵌套必填及未知字段，不只测游离组件；合法nullable保持 | `test_nt03_nt08_each_write_validates_actual_request_binding`、`test_nt08_success_envelopes_and_nested_required_fields`及上述边界方法；既有三个nt08方法及覆盖/兼容删除回归 |

## 发现、修复与证据

证据根：[task007_coverage_2026-10-23](evidence/task007_coverage_2026-10-23/tests.log)。

- 缓存声明遗漏依据04 §4的私人业务响应no-store要求。修复前新增8方法中7通过、缓存方法48个子场景失败，见`regression-before.log`；修复仅增加错误响应头声明，429的Retry-After保留。最早`new-tests.log`还包含测试编写时对合法nullable scope的错误预期，该预期已按08-01“非当前提交scope=null”纠正，不把它算实现缺陷。
- `tests.log`：`contracts/.venv/bin/python -m unittest discover -s scripts/tests -p 'test_*.py' -v`，58方法通过，无跳过（原46、并行4、本轮8）。
- `backend.log`：`backend/.venv/bin/python -m pytest backend/tests -q`，75通过，保留1项上游Starlette/httpx弃用警告；不连接业务数据库。
- `structure.log`：`contracts/.venv/bin/python scripts/check_api_contracts.py`通过，47 request/success partial + 40 request-only、172 schemas、131来源行、5/6 SSE。剩余覆盖限制保持。
- `mutations.json`及`mutation-check.py`：仅在内存中删除请求修订、使CSRF可选、扩大scope、删除成功来源必填、放宽内容修订、移除来源组合约束、移除错误no-store，共7种变异均被新断言识别，不写工作区契约。
- `compatibility.log`：以`pre-cache.openapi.json`运行`check_api_contracts.py --baseline`退出1，报告五操作改变。逐项JSON差异核对仅48处错误头新增及info版本升级；属于既有规范的生产端约束补齐，不改变响应body或旧错误码。门禁不支持自动判定方向，非零结果保留，不标整体兼容通过。历史A04差异的处置不在本次重新裁决。
- `delivery/`保存交付源快照及SHA清单，`snapshot.log`核验完整重构；`documents.json`核验本轮文档链接/版本/日期。全量Git diff含其他既有改动，不作为本轮独占成果。

## 设计核对及明确未覆盖的运行要求

逐项对照04-01 §10.1–10.3与03-01设置/03-02分类/03-04受限提示：默认/历史无分类保守投影、静态接收先于分类且模型外发后置、Owner放宽依据、确认与更正状态前置、授权/归档先于重放、PUT丢响应先GET、GET只读、同键同参重放/异参冲突、冲突保留草稿、安全404、当前政策双向生效与不换版/不剪历史/不自动重跑均有设计约定。主动文字例外已由并行修复澄清，不增加确认制度；P1 DAP-16–18仅核对不被P0改变。

这些语义不能用schema或文字匹配测试证明实际成立。以下仍未实现/未运行，不能记为通过：

| 需求族 | 必须补的运行验收 | 交接 |
| --- | --- | --- |
| N-T01/02/03/04 | 真正Owner/管理员/跨Project/归档授权；默认创建与读取持久恢复；static接收及首次外发门槛；充分依据验证；人工内容、旧版本/引用不变；普通metadata拒绝 | 后续API/持久化实现，TRACK-012c/d、021 |
| N-T04/05/07 | 同键重放不再执行及原事实返回；异参冲突；授权先于重放；至少24小时幂等保留；旧修订拒绝且无副作用；原子提交/失败回滚；ABA、派发/提交交错与缓存重验 | A06及后续隔离数据库/确定交错测试 |
| N-T06 | 应用签发scope并绑定主体/Project/命令；全部实际输入依赖；历史/上传不能冒充主动文字；受限历史阻断与允许子集不换版 | A06/A07/A08与消费实现 |
| N-T01–08 UI与HTTP | 风险/Provider提示、只读按钮、错误草稿保留、不自动重交、实际HTTP响应头与安全脱敏、真实Task投影和端到端行为 | 后续前后端实现及浏览器验收 |

本次没有数据库写入、LLM、论文源、邮件或部署；纯schema测试不代替上述运行验收。不启动task008，不新增产品决定，人工接受尚待用户明确。
