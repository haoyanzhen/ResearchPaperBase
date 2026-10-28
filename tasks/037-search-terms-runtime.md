# Task037：检索词生成审核与长期管理

文档版本：v1.3
更新日期：2026-10-28

## 8. 最新恢复检查点（2026-10-28）

流程v1.8；第1节授权有效，D-CW-01 A已接受，无新增业务待决。当前S7工程已收口，S1–S6完成；独立后端/UI复审问题均闭合。M-P0-11已于2026-10-28获人工接受，Git提交按第9节核对。task038并行流程文档修改完整保留。

本轮证据：[目录](../docs/workorders/evidence/task037_search_terms_2026-10-28/)、[独立结论](../docs/workorders/evidence/task037_search_terms_2026-10-28/independent-review.json)。review01为360文件中途基线，最终基线见[delivery快照](../docs/workorders/evidence/task037_search_terms_2026-10-28/delivery/)。恢复先看第4/5节；全套560通过2失败，均为测试清单/清理适配；最终74项全部通过，497未变场景复用有效通过证据。最终check/build及文档核验通过，不把失败日志称为全绿。本地提交`3e5349e`已完成；下一阶段及当前决定点见[task039](039-construction-retrieval-gate.md)，不要重复提交。

## 1. 授权与目标

承接用户选择D-CW-01 A并继续实现至下一里程碑/未明确设计的授权。M-P0-11包含Project内检索词人工管理、生成候选审核/接受/弃用、逐词确认、来源策略与自动更新开关、生成失败恢复、必要的Project主题资料分类/本人政策及任务读取。P0调度未启用。不交付真实ConstructionRun、多源检索、历史Run快照或完整FR020/021。

## 2. 依据与基线

task036 handoff345文件无漂移；before见evidence/task036_cw01_accepted_2026-10-27。D-CW-01 A已同步01/02/02-03/03-02/04-01/05/09与task030；独立核查确认没有新的业务待决。按01 FR020/017、P43、04-01 §4/10、04-02 Task、05-01资料来源、08-01 Q1–Q4落实；既存Project主题不得伪装本次提交，走既有来源分类和本人政策。保留工作区全部已有修改。

## 3. 修改落点

Construction领域校验、持久词/确认/生成任务/去重/资料依据及迁移、Project生产链接入、HTTP/UI、LLM生成适配、演示Worker、机器契约、隔离集成/浏览器与单元测试。

## 4. 需求与执行证据追踪

以下函数位于[持久HTTP测试](../backend/tests/integration/test_search_terms.py)、[浏览器测试](../backend/tests/integration/test_browser_terms.py)；领域/Provider见[领域单测](../backend/tests/unit/test_search_terms.py)、[协议单测](../backend/tests/unit/test_term_provider.py)，机器契约见[契约测试](../scripts/tests/test_search_term_contracts.py)。第5节维护执行结果，数量不替代场景断言。

| ID | 可观察要求及禁止副作用 | 具名场景/可执行证据 |
| --- | --- | --- |
| ST01 | 本人active Project CRUD；默认auto=true/no enabled；归档只读、跨主体拒绝、分页 | `test_st01_manual_confirm_edit_delete_replay_and_forbidden_side_effects`、`test_st02_project_scope_csrf_archive_and_unknown_fields`、`test_st01_pagination_and_revision_race`、`test_st01_cursor_survives_application_instance`、stb01/stb06 |
| ST02 | 修订及token绑定主体/目标/TTL；修改使确认失效；冻结内容/修改来源；回滚无部分写 | st01 manual、`test_st02_confirmation_survives_process_restart_and_rejects_malformed`、`test_st02_confirmation_expiry_target_scope_and_transaction_rollback`、`test_st05_accept_generated_preserves_source_history_and_discard_minimal`、stb03/stb05 |
| ST03 | all_resolvable默认、selected显式引用不替换；自动开关不触发调度 | `test_st03_invalid_source_policy_has_no_write`、`test_st03_selected_refs_persist_exactly_without_resolution_or_schedule`、领域A裁决/默认/非法策略用例、stb06；真实Run解析不在本片 |
| ST04 | 显式模型生成持久Task、冻结配置不含密钥；并发只派发一次；未知请求/过期lease不重发 | `test_st04_generate_review_discard_and_no_repeated_suggestions`、`test_st04_multiple_projects_commit_to_claimed_project_only`、`test_st04_expired_running_attempt_is_not_resent`、`test_st04_model_deleted_at_boundary_never_commits`、`test_st04_concurrent_workers_dispatch_once_and_receipt_replay`、四协议及非法Provider响应单测 |
| ST05 | 接受候选需明确确认；弃用删正文保留hash/回执；批量遇冲突保留完成项与剩余选择 | st04 generate、st05 accept、`test_st06_audit_provenance_and_no_overwrite`、stb04双候选部分成功/412恢复；保留人工词，不隐式覆盖 |
| ST06 | 既存主题historical_input分类确认+本人政策；本次追加文字只绑定该命令；read/dispatch/commit重查与审计 | `test_st06_unclassified_topic_never_implicitly_authorized`、`test_st06_policy_tightening_prevents_dispatch_or_commit`、`test_st06_disabled_then_enabled_account_cannot_revive_task`、`test_st06_rejected_read_or_dispatch_has_current_audit`、`test_st06_audit_provenance_and_no_overwrite`；stb04真实UI分类与风险确认 |
| ST07 | 刷新/任务恢复/错误修复/移动端/切号不串数据；不丢人工草稿 | stb01手工确认修改/重载/移动端/退出切号；stb02响应丢失同键；stb03并发412；stb04分页轮询/批量/失败后手工输入及重载；stb05删除后保留草稿另存；stb06来源与归档只读；`test_st07_recent_task_projection_uses_creation_time_after_jsonb_roundtrip` |
| ST08 | schema迁移/降级保护/清理；wire封闭字段/状态绑定；既有能力回归 | `test_st08_nonempty_migration_downgrade_refused_and_project_cleanup_cascades`、`test_st08_public_transport_error_is_bound`、TermsClient逐成功/错误wire校验；test_ps存储/全套回归、check/build与契约负例 |

本片保留的后续需求：真实Construction Run selected门槛、多源检索和Run冻结输入、知识版本发布、完整Workspace全局布局及跨模式资产侧栏、P1调度不在M-P0-11交付；不可用本片证明完整FR020/021或整个资料政策已实现。页面提供当前检索词配置摘要与逐词来源/确认状态，不宣称完整跨模式侧栏完成。

## 5. 验证与工程记录

使用全新隔离PostgreSQL17、Unix socket、非超级用户测试角色；runner清除业务环境变量，每次报告server_stopped/root_removed。所有LLM/论文源/邮件均fake或本地受控协议，未调用真实供应商。生产迁移与旧数据未执行。

- 完整回归首轮`logs/rpb-terms-full1.log`：562项中560通过、2失败（旧Project表清单缺0013新表；新增迁移测试清理缺既有依赖记录），不是全通过。新增表清单精确增加construction_term_states，清理遵循既有外键顺序，不削弱断言。
- `logs/rpb-terms-test15.log`：35通过1失败（来源浏览器测试复用已轮换CSRF）；`test16`修正取当前CSRF后1通过。更早真实失败及修复日志保留，不作为最终通过证据。
- `logs/rpb-terms-engineering9.log`：lint/format/mypy、237项后端单元/架构测试、80项契约脚本、前端类型检查和4项组件测试通过。`logs/rpb-terms-finalbuild2.log`构建通过。
- 最终隔离复验`logs/rpb-terms-final-integration.log`：74通过、497未选；覆盖本片36项及受影响Project存储用例（selector的实际选集为准），两个全量失败已闭合。497未变场景复用full1有效通过证据，总当前收集范围571项；不声称单次571全绿。最终`logs/rpb-terms-final-check.log`通过：237后端单元/架构、80契约脚本、4前端组件，lint/format/mypy/类型检查通过；构建使用`logs/rpb-terms-finalbuild2.log`。172项本地链接/锚点、文档版本日期、审查哈希和diff检查通过（最终计数见docs-checks.json）；delivery快照绑定最终产物。

S3后端/UI均经独立只读subagent复审闭合，具体问题和限定结论见independent-review.json。S4按ST01–08补齐跨实例、21任务重读、拒绝审计、两候选部分成功、真实资料风险UI、并发删除草稿、来源归档场景。S5统一aggregate/CW表保存以消除修订双源，删除未使用state字段；保留简单Project aggregate+事务锁方案，避免本片引入无需求的额外仓储层。S6只复验改动及受影响依赖，未改动回归复用full1有效结果。

## 6. 人工节点

D-CW-01 A已决。检索词候选API、来源注册生产链接入是现行规则的工程细化，不新开权限决定。完成本片S1–S7后提交M-P0-11并停止。

## 7. 当前状态

设计、代码、自动验证、独立复审及S7工程收口已完成；M-P0-11等待人工验收。真实供应商/生产未验证，不声称完整FR020/021完成。未提交Git、未push；收到实际里程碑接受后按现行流程核对范围再创建本地提交。


## 9. M-P0-11人工接受与提交范围（2026-10-28）

用户原话：“ok，通过M-P0-11，继续实现下一阶段，直到里程碑进度或遇到未明确设计”。接受限定于本片验收包；入场核对delivery全部361文件，0漂移。历史待验收文字保留为当时状态；本次未重跑历史业务测试。

本地提交包含M-P0-11产物与必要前置：task029/031/033/035分别已获M-P0-07/08/09/10接受（各任务接受节），其未提交代码是本片依赖，明确纳入本次清单，不称为本次新验收或分别追补历史提交。task038已授权并工程收口的流程记录随必要文档纳入；不包含下一阶段业务代码。按delivery清单逐路径暂存，检查暂存区、内容摘要和diff；证据目录单独保留工作区，不夹带历史运行截图。接受快照与提交清单见[本轮目录](../docs/workorders/evidence/task039_construction_retrieval_gate_2026-10-28/)。提交SHA在后续检查点记录，不循环amend。

本地提交完成：`3e5349e90bb54241c5b5026b35be3475c144124b`，111个明确源文件/文档路径；暂存区提交后为空，提交树逐文件与暂存前实际内容一致。3份被忽略的本地.gitignore未纳入；历史证据和运行截图仍保留工作区。提交后的SHA记录为纯交接追加，不amend。下一阶段见[task039](039-construction-retrieval-gate.md)。
