# Task033：系统数据源与逐Provider个人优先解析

文档版本：v1.1
更新日期：2026-10-26

## 1. 目标与授权

承接用户M-P0-08通过/继续至里程碑或未明确设计授权，以及task032 D-SOURCE-02选择B并强调个人四源API能力。实现系统四源CRUD/启停/凭据/持久测试、平台权限与治理边界、逐Provider个人优先解析和个人多源回归。目标M-P0-09；不实现SMTP、非论文Provider或Construction消费者。

## 2. 基线及依据

task032 handoff312文件无漂移，before及entry.json见docs/workorders/evidence/task033_system_sources_2026-10-26。保留已有未提交/未跟踪工作。依据01 FR003/006/007/020、02配置不变量、02-03策略、03-01 P06c/P10c、04-01配置、05/05-01执行、07持久化、08权限/凭据及09要求；D-SOURCE-02决定已同步。

## 3. 修改落点

source平台表与迁移、SourceStore/Worker/API、配置任务路由、账号治理接缝、应用组合、本地演示、SourceSettings/导航；解析服务仅返回脱敏来源与诊断，不引入虚构Construction端到端。个人既有配置能力必须保留并用四源持久化与浏览器验证。

## 4. 需求场景

SS01 平台CRUD与权限：跨管理员、普通用户拒绝、CSRF/切号、私人配置不可见、加密无明文。
SS02 持久性：幂等/冲突/修订/分页/密钥更新清除、审计失败原子回滚、确定性并发。
SS03 持久测试：匿名/缺密钥/Provider失败/限流、修订过期/迟到/租约过期不误激活，禁用可测试但不可运行。
SS04 治理：撤权三个执行阶段、撤权再授予不能复活、删除创建者保留平台资产/审计、预览绑定新任务。
SS05 逐Provider：无个人用系统、个人arXiv+系统OpenAlex、个人禁用/失败不回落、多个实例保留、删除后可回落、显式原ID失效拒绝、系统密钥无明文、快照不受更新影响。
SS06 个人多源：四源不同API配置独立CRUD/凭据/启停、本人隔离、arXiv匿名，浏览器添加/切换/刷新恢复。
SS07 UI恢复：系统配置维护测试、私人/系统独立草稿、未知响应同键核查、切号/移动端。
SS08 机器/迁移：wire匹配配置与任务schema、空链迁移/有事实降级拒绝。
实现后补具名测试与实际证据；不能以规划场景冒充覆盖。

## 5. 验证

仅隔离PG17/临时目录、本机浏览器，FakeProvider，禁止真实外部请求或邮件。执行scripts/run_storage_tests.py及engineering.py check/build和scripts/verify_skeleton_delivery.py干净安装；保留首轮失败与复验记录。独立审查自行读实际产物及反例。

## 6. 人工节点

D-SOURCE-02已决，无新业务问题。M-P0-09在系统管理/测试、个人多源能力和解析边界工程完成后提交；真实Construction快照消费仍不在本片验收。

## 7. 当前报告

S1–S7已完成；设计已决定、代码与自动验证完成、工程已收口，M-P0-09待人工验收。下述运行中状态为历史检查点。

## 8. 检查点

流程v1.7。当前只授权N3；S1基线/范围已核对，S2开始，S3–S7待执行。下一动作最小实现与需求测试、独立审查、覆盖复核/简化/最终复验，完成后停止于M-P0-09。


## 9. S2–S5执行与需求追踪

S2最小实现完成。系统Source表与个人表分离，操作者UUID无账号级联；复用Source校验/编辑/Worker，当前管理员授权三阶段检查、撤权终结持久任务、治理预览绑定活动任务。解析为内部只读接缝，按Provider选择集合，返回来源/配置修订/凭据修订引用及诊断；不返回密钥、不隐式外发、不把untested当不可用。真实Construction启动和持久冻结尚未接入。

初次过滤词ss过宽，执行中主动中断并确认隔离库清理；随后专项首轮16通过/4失败（旧前端构建缺按钮、确认过期错误预期写成412、迁移测试未绑定活连接），按04确认过期409规则校准测试并补精确错误码，修复夹具后26项专项通过。原日志保留，不用修改产品规则获取通过。

| 需求 | 可执行测试（backend/tests/integration） | 观察 |
| --- | --- | --- |
| SS01权限与平台资产 | test_system_sources.py::test_ss01_scope_secret_contract_and_audit；SS07/08；SSB01 | HTTP拒绝、加密DB、跨作用域不可读、平台创建者删除后资产保留 |
| SS02 CRUD/幂等/并发/回滚 | test_ss02_crud_revision_keys_pagination_and_duplicates；test_ss09_audit_rollback_and_downgrade_refusal；test_ss11_two_admins_parallel_revision_and_duplicate_create | 故障注入审计回滚；真实PG advisory屏障确保两命令同时等待，提交后1成功1冲突 |
| SS03连接任务/失败/迟到/限流 | test_ss05_failed_personal_source_never_falls_back（三参数）；test_ss06_disabled_test_missing_key_and_revision_invalidation；test_ss10_expired_task_and_late_config_result；test_ss14_shared_system_rate_cannot_be_bypassed_by_other_admin | FakeSource调用记录与屏障、租约过期不重发、不同管理员共享平台预算 |
| SS04治理 | test_ss07_revocation_regrant_and_late_results（三执行阶段）；test_ss08_creator_delete_retains_platform_and_preview_binds_jobs | 撤权再授予不复活、任务治理错误不污染连接事实、预览后新任务使确认409过期 |
| SS05逐Provider解析/身份 | test_ss03_precedence_multiple_instances_disabled_deleted_and_selected；test_ss05；test_ss12_invalid_policy_returns_validation_error（四参数）；test_ss13_foreign_selection_and_actor_mismatch_are_rejected | 默认/selected、多实例、全部个人禁用不回落、删除恢复、混合个人/系统身份、快照返回值保持原值；不冒充持久Run冻结验收 |
| SS06个人四源API | test_ss04_personal_provider_api_configuration_independent（四Provider）；test_browser_system_sources.py::test_ssb03_four_personal_api_configs_persist_separately | 四源独立入口/凭据、管理员不可读取他人私人配置、刷新恢复、密钥不回显；arXiv匿名 |
| SS07浏览器 | test_ssb01_platform_test_refresh_disable_and_regular_user；test_ssb02_unknown_create_and_separate_drafts；SSB03 | 真实浏览器/HTTP/PG，移动端无溢出、系统测试、未知提交原键恢复、个人/系统独立草稿 |
| SS08机器/迁移 | SS01真实wire、SS09降级拒绝；既有account/project空迁移链；scripts/tests/test_system_source_contracts.py | SystemSourceTaskView真实投影；现有错误契约不被扩宽 |

S3独立审查R1–R4已修复并最终只读复审闭合，见independent-review.json；审查者未代执行PG/浏览器验收。S4补齐SS03混合selected/全部禁用及SS14跨管理员限流，保留所有原断言。S5复用个人/系统源Store、Worker、编辑器，平台表保留独立生命周期；无进一步无关重构收益。

S6当前全量集成、静态/契约/前端及干净安装运行中，尚未工程收口。完整首次集成发现一个旧测试迁移头预期仍为0010，已更新至新增0011；待最终结果与受影响复验。证据源快照verification-input保存最新代码，后续若变化须重新绑定。


S6追加：71项SS/SSB与账号回归通过，SS15缺配置诊断和SSB04未知PATCH恢复纳入。首次完整回归为443通过/2失败/28错误；两个失败是旧0010迁移头预期，28错误来自旧SL09在事务内捕获预期拒绝后提交了此前空表降级，污染后续夹具。已将SL09/SS09异常断言移到事务外，使事务先回滚，并新增head与system_source_audit仍存在断言；四项迁移专项通过。独立增量复审确认不削弱原断言。中间完整重跑主动中断并清理，最终固定release-input再执行integration-release.log；结果待完成，不沿用失败轮次为通过证据。


## 10. 最终工程收口与M-P0-09交接

S1–S7完成。最终integration-release.log为474通过（534.69秒），包括全部PG/HTTP/浏览器及新增SS/SSB；隔离PG17实例server_stopped/root_removed均true。check-release.log为187后端/74契约/4前端通过，Ruff/mypy/TypeScript通过；build-release及clean-install-release通过，Node24离线干净安装、锁拒绝、安装wheel启停完成。无真实云LLM/论文Provider/邮件访问，受控本地适配器测试不替代真实供应商兼容验收。

最终执行输入为release-input319文件，结束核对代码、测试、机器契约、规范0漂移；其后仅任务状态、报告和项目入口证据追加。最终delivery320文件完整内容快照包含既有未提交/未跟踪源码，不重置工作区。单一验收包见[task033交付报告](../docs/workorders/task033_system_sources_delivery_2026-10-26.md)。S3/S6所有问题及文档增量复审闭合，见independent-review.json。

S4追加SS15缺配置诊断及SSB04未知PATCH导航恢复，已包含最终474项；逐需求映射沿第9节（SS15属SS05、SSB04属SS07）。S5除清理重复UI状态赋值外无需进一步改动，行为与断言保持；S6迁移测试事务隔离修复已独立复审并通过完整回归。

| 阶段 | 最终状态 | 依据 |
| --- | --- | --- |
| S1 | 完成 | D-SOURCE-02 B实际决定、个人四源补充、312文件无漂移 |
| S2 | 完成 | 系统Source闭环及SS/SSB需求导向测试 |
| S3 | 完成 | 独立发现与修复R1–R4闭合 |
| S4 | 完成 | 第9节映射，SS03/14/15与SSB04补验，无本片未解决必需缺项 |
| S5 | 完成 | 复用Store/Worker/UI，平台生命周期分离，无其他简化收益 |
| S6 | 完成 | 最终474项及静态/构建/安装；迁移修复和文档受影响复审 |
| S7 | 完成 | delivery快照、验收包、状态入口；停止于M-P0-09 |

当前设计/代码/自动验证/工程收口完成；M-P0-09待人工接受，不把M-P0-08接受扩展到本片。无新增业务待决。恢复时先核对delivery及用户验收/继续指令；SMTP、通知、非论文扩展和Construction消费者尚未交付，不提前启动。所有首轮失败、中断、清理和修复记录保留。


## 11. M-P0-09接受与继续授权

2026-10-26用户明确回复“ok，通过M-P0-09，继续实现下一阶段，直到里程碑进度或遇到未明确设计”。接受绑定本任务第10节原delivery320文件；本轮逐SHA-256核对0漂移，证据见[task034 entry](../docs/workorders/evidence/task034_smtp_design_gate_2026-10-26/entry.json)。本次不重新运行或重报原474项测试为新执行。

M-P0-09现已人工接受，范围仅原交付系统数据源/个人多源及内部解析接缝；真实Construction消费者、SMTP/安全配置和P1通知未被本次接受覆盖。继续授权进入[task034](034-smtp-security-design-gate.md)的N4设计核查，遇未明确设计保存检查点；此前“待接受”为历史状态。
