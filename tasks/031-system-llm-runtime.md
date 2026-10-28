# Task031：系统LLM管理与显式选择闭环

文档版本：v1.1
更新日期：2026-10-26

## 1. 目标与授权

用户2026-10-26明确“ok，通过M-P0-07，继续实现下一阶段，直到里程碑进度或遇到未明确设计”。接受记录见task029第11节。按task030 N1/N2实现管理员系统LLM CRUD/凭据/发现/逐模型测试，以及普通用户显式选择和失效恢复；目标M-P0-08。不实现系统Source/SMTP、通知、Construction或生产部署。无新增业务裁决。

## 2. 依据与基线

FR002/006/007、02 §2.2平台所有权、03-01 P10b、04-01配置操作、04-02任务读取、04-04参数、05配置编排、05-01配置所有者、07持久化、08 §3/12、09 MOD02/SEC04/08/09。入场task030 delivery304文件逐SHA256无漂移；task029原delivery仅状态文档已有task030规划，业务无漂移。原始快照及entry.json在docs/workorders/evidence/task031_system_llm_2026-10-26/before及同级。保留所有未提交/未跟踪内容。

## 3. 修改落点

系统配置/任务/命令/审计采用独立system_llm表；owner_id列仅记录创建/发起操作者UUID，不授予私人所有权，不级联删除平台资产。复用LLM校验、编排、Worker与编辑UI，固定system作用域及当前管理员授权。模型选项只输出安全字段；普通用户不能读取系统管理和任务。治理撤权终结旧系统测试并绑定预览影响。迁移0010保护有事实时降级；应用组合与本地演示接入系统Worker。契约/测试/README按实际交付同步。

## 4. 验收与需求追踪

SL01权限：管理员跨操作者管理平台资产；普通用户/匿名/CSRF/切号拒绝；私人/系统隔离。
SL02存储：CRUD、部分更新、参数拒绝、密钥set/clear加密、分页、审计原子性、幂等及修订并发。
SL03测试：发现不授可选性、逐模型当前修订测试、Provider失败/超时、迟到/过期结果不激活新配置、无自动收费探测。
SL04选择：合并来源、同名模型区分、user/system显式选择与刷新恢复、无选择不默认系统模型、明文不外泄。
SL05失效：配置修改/凭据轮换/删除后原选择保留身份提示修复，旧任务快照不改，未实现Agent消费者不冒充FR007完整验收。
SL06治理：撤权再授权不能复活旧queued/running测试，三个执行阶段校验；删除创建者保留平台配置、成功事实和审计；预览后新增任务使确认失效。
SL07浏览器：管理员维护/测试，用户选择恢复、冲突/丢响应/切号、失败修复；真实HTTP与隔离PG。
SL08契约/迁移：真实wire投影匹配system任务与配置schema；downgrade有事实拒绝，空链可运行。
具名测试与执行结果在实现后追加，不先宣称覆盖。

## 5. 验证计划

仅隔离PG17、临时文件、真实本机浏览器；Provider默认FakeProvider，禁止真实付费调用和邮件。沿用run_storage_tests.py、engineering.py check/build/clean-install入口，逐需求验收及受影响回归。证据目录保留所有首轮失败、修复、复验及独立结论。

## 6. 人工节点

M-P0-07已接受，M-P0-08未到。S1只读独立设计核查未发现新设计歧义。达到系统配置→逐模型测试→普通用户显式选择→失效修复闭环并完成工程阶段时提交验收包，停止后续业务。

## 7. 当前报告

S1–S7已完成；设计、代码和自动验证完成，工程已收口，M-P0-08待人工验收。单一验收包见docs/workorders/task031_system_llm_delivery_2026-10-26.md；下述进行中描述保留为历史检查点。

## 8. 检查点

流程v1.7。当前授权队列N1→N2，允许连续完成工程阶段；N3及以后不启动。S1已完成，S2进行中，S3–S7待执行。当前基线before完整快照，后续review/delivery保存实际产物；设计审查者/root/system_llm_review只读结论为无新增业务待决，列出的授权/生命周期/机器接缝纳入SL01–08。下一动作完成最小实现和需求测试、独立审查、覆盖复核、简化、最终验证与收口。

## 9. S2–S5记录与覆盖映射

S2最小实现及17项专项PG/浏览器通过，证据system-browser.log；首轮任务投影字符串路径错误修复，测试夹具导入与旧迁移版本预期修复，失败日志保留。S3独立审查/root/system_llm_review发现导航卸载丢草稿/未知命令问题，改为两个固定actor实例，inactive只隐藏渲染、保留状态；SB02新增未知响应导航往返和独立草稿断言。S4复核补跨管理员并发、同名模型两来源隔离、外发前撤权、过期任务不重发；保存新修订清除旧测试详情，SB01补断言待最终重验。

| 需求 | 具名可执行测试（backend/tests/integration） | 观察/隔离 |
| --- | --- | --- |
| SL01管理授权/CSRF/切号/作用域 | test_system_llm.py::test_sl01_management_scope_and_no_secret；test_sl10_same_model_sources_and_private_tasks_stay_isolated | 实际HTTP拒绝、平台/私人配置与任务隔离、DB加密 |
| SL02参数/CRUD/修订/分页/幂等/审计 | test_sl02_revision_validation_pagination_and_idempotency；test_sl09_failed_audit_rolls_back_and_downgrade_refused；test_sl11_two_admins_parallel_revision_and_duplicate_create | 提交持久计数；审计失败回滚；真实PG双请求advisory阻塞后释放 |
| SL03发现/逐模型测试/失败/迟到/超时 | test_sl03_discovery_selection_and_failure；test_sl04_late_result_cannot_activate_and_snapshot_fixed（三参数）；test_sl12_revoke_between_claim_and_outbound_and_expired_no_resend | Provider屏障及FakeProvider调用记录，不请求真实外部服务 |
| SL04/05显式选择、恢复、失效身份/快照 | test_sl03、test_sl04、test_sl10；test_browser_system_llm.py::test_sb01_admin_test_user_select_restore_and_invalidate | 普通用户无自动选择、来源区分、保留原身份、旧输入不变；不替代未来Agent启动验收 |
| SL06治理/平台资产/预览绑定 | test_sl05_revoke_regrant_never_revives_old_task（queued/running）；test_sl06_delete_creator_retains_platform_success_and_audit；test_sl07_new_task_invalidates_revoke_preview；test_sl12 | 确定性交错；账号删除后配置/成功测试/审计仍在，重新授予不复活旧任务 |
| SL07真实浏览器 | test_sb01；test_sb02_lost_create_and_separate_drafts；既有LU/AG/AB全量回归 | 桌面管理员→移动端普通用户；刷新恢复、丢响应同键核查、跨页面草稿保护 |
| SL08机器/迁移 | test_sl08_wire_system_task_and_safe_fields；test_sl09；既有account_storage空迁移链；scripts/tests/test_system_llm_contracts.py两项 | 真实wire校验、secret不在SSE/模型选项；有事实拒绝降级 |

S5：复用已验证的LLM参数编排和UI，平台表与私人表独立以明确清理边界；owner_id在平台表中只记录审计操作者，不作为查询授权条件。保留既有治理事务锁确保系统选择、编辑和撤权有确定顺序；不制造无关重构。新增系统审计result/config_type列，配置操作与审计同事务。S3后除了上述局部UI修复与精确机器文档校准，没有新增业务规则；最终检查/复审进行中。


## 10. 最终收口与恢复入口

本轮S1–S7完成。当前设计/代码/自动验证/工程收口均完成；M-P0-08待人工验收。无新增未决业务设计，不继续N3。S4追加SB03覆盖未知PATCH只读核查，SL10明确个人/系统来源标签，保留全部原行为断言。S6最终独立复审无剩余问题；全量首轮440通过/4失败（3个移动端溢出、1个物理表集合缺新表）已修复，27项影响回归及最终445项完整PG/HTTP/浏览器均通过。187后端、73契约、4前端及类型/构建/干净安装通过。

最终基线：docs/workorders/evidence/task031_system_llm_2026-10-26/delivery，含未提交/未跟踪源码。verification-input在最终全量前固定310文件，结束核对0漂移；此后仅新增验收报告与完成状态/README说明，不改变代码、测试或规范。完整需求追踪见第9节，SB03同属SL07。独立审查只读验证范围和主代理执行范围分开记录；首轮失败及Node25拒绝日志均保留。最终复验和审核包见[单一验收包](../docs/workorders/task031_system_llm_delivery_2026-10-26.md)。

| 阶段 | 最终状态 | 证据 |
| --- | --- | --- |
| S1 | 完成 | 用户M-P0-07接受/继续授权，entry.json及before |
| S2 | 完成 | SL/SB需求测试及最小实现；system-browser.log |
| S3 | 完成 | independent-review.json，R1修复和复审闭合 |
| S4 | 完成 | 第9节映射；SL10–12/SB03及原失败场景修复，affected-final.log 27项 |
| S5 | 完成 | 复用参数/编排/UI，独立系统资产表，无额外重构收益 |
| S6 | 完成 | integration-verified.log 445项；check-delivery/build-verified/clean-install-final；独立受影响复审 |
| S7 | 完成 | delivery快照、验收包、项目状态同步；停止于M-P0-08 |

恢复时先核对delivery及用户M-P0-08决定。已有M-P0-07接受不覆盖新系统任务治理接缝，随本次M-P0-08补充验收。系统Source、SMTP及构建后续仍需按里程碑/授权继续，不从待办自动启动。

## 11. M-P0-08人工接受与继续授权（2026-10-26）

用户明确：“ok，通过M-P0-08，继续实现下一阶段，直到里程碑进度或遇到未明确设计”。接受绑定本任务原delivery的311文件基线，含系统LLM及系统任务治理接缝；本次逐SHA-256核对0漂移，见task032证据目录entry.json。原验收和失败/复验记录保留，本次没有重跑业务测试。M-P0-08现为已接受，前文待验收为历史检查点。

继续授权进入task030 N3系统数据源及解析的S1核查，见[task032](032-system-source-design-gate.md)；到下一业务里程碑或未明确设计停止，不自动授权SMTP、通知或构建实现。
