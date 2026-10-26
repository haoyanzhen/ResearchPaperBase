# Task024：个人资料真实用户场景独立测试

文档版本：v1.0
更新日期：2026-10-26

## 1. 目标与授权

用户要求“派发子代理以用户的真实场景为假设，设计各类操作测试用例，进行独立测试”。本轮围绕M-P0-04及受影响的登录/Project交互，由独立测试作者从需求推导新场景并执行；发现已定范围缺陷则修复和独立复验。不启动配置/治理等新业务，也不代替M-P0-04人工接受。

## 2. 依据与基线

01 FR001身份归一化/本人资料，03-01通用返回保留输入/P06a，04/04-01 UserPatch及公共错误，08当前权限；task023只提供既有范围和历史证据，不作为测试预期的唯一来源。入场与task023 delivery249文件逐摘要一致，before/保存全部未提交和未跟踪内容；保留其他工作区修改。

## 3. 修改落点与委派

- `/root/scenario_browser`：自行设计并编写test_profile_user_journeys.py；真实浏览器交错操作、草稿、跨标签和失败恢复，仅可写新测试和browser-*证据。
- `/root/scenario_identity`：自行设计并编写test_profile_identity_scenarios.py；真实PG/HTTP的身份、会话、并发操作序列，仅可写新测试和identity-*证据。
- 主代理整合证据，按实际缺陷做最小业务修复，再安排只读独立审查。测试作者不修改业务代码或彼此文件。

## 4. 场景与追踪

正常、拒绝、失败、并发和禁止副作用均以现行规则为预期；发现未明确语义时不猜测通过。

| ID | 用户操作与预期 | 依据 / 可执行用例（integration目录） |
| --- | --- | --- |
| J01 | 项目编辑中修改个人资料，再返回保存项目；双方草稿/持久值保留 | 03-01返回保留输入；test_profile_user_journeys.py::test_journey_project_draft_survives_successful_profile_save |
| J02 | 两独立会话改邮箱，另一会话仍绑定原账号；退出后旧邮箱拒绝，新邮箱可登录且项目不变 | FR001身份/账号归属；test_journey_new_email_login_preserves_project_and_old_session |
| J03 | 另一用户占用邮箱，拒绝且显示名草稿保留；纠正后可保存 | 01身份唯一/04 PATCH；test_journey_occupied_email_is_correctable_without_losing_name |
| J04 | 真实提交后断响应，首次核查也断网；不自动重发，保留草稿，恢复后核查原结果 | 04未知结果/03交互；test_journey_lost_write_then_failed_read_does_not_enable_resubmit |
| J05 | 已存带空格/大小写邮箱，仅修改显示名，不暗改邮箱原文 | 01已接受身份规则/04省略保持；test_journey_display_name_edit_preserves_saved_email_original |
| J06 | 两标签提交冲突；显式核查后再次编辑，不自动重放旧草稿 | 04修订/03人工输入；test_journey_two_tabs_conflict_reload_then_deliberate_new_edit |
| IS01 | 两用户直接换占用邮箱均拒绝，通过临时邮箱显式交换后账号与项目归属不变 | FR001/08；test_profile_identity_scenarios.py::test_identity_scenario_is01_swap_requires_vacancy_and_preserves_ownership |
| IS02 | Unicode casefold跨用户名/邮箱碰撞拒绝且不泄露他人信息 | 01已接受身份规则/08；test_identity_scenario_is02_unicode_cross_field_collision_rejected |
| IS03 | 两独立会话旧修订即使无改动也拒绝，刷新后部分更新保留前次字段，退出一会话不退出另一会话 | 04修订/FR001当前会话；test_identity_scenario_is03_two_sessions_stale_noop_requires_refresh |
| IS04 | 禁用后旧会话改资料拒绝，重新启用不复活已失效会话，重新登录可保存 | FR001/08；test_identity_scenario_is04_reenable_does_not_resurrect_rejected_session |
| IS05 | 两用户同时交换已占邮箱，明确观察两请求阻塞再释放，均拒绝且双方数据不变 | 01跨字段唯一/07原子写；test_identity_scenario_is05_simultaneous_occupied_swap_is_not_implicit_exchange |
| IS06 | 拿另一用户revision提交本人端点，不获得对方权限，也不改任一账号 | 04/08；test_identity_scenario_is06_foreign_revision_is_not_object_authority |

IS04禁用/重新启用由隔离SQL夹具建立前置，不代表管理员治理入口已实现。J04只截断真实已提交响应或阻断网络，不伪造业务成功。

## 5. 验证计划

证据根docs/workorders/evidence/task024_profile_scenarios_2026-10-26/。沿用engineering.py integration显式PostgreSQL17入口，PYTEST_ADDOPTS限定各自新测试；临时独立PG、非管理员角色、真实HTTP/Chromium；无Provider或邮件调用。失败测试保留，不弱化断言；最终组合/受影响回归和独立复审按实际修改执行。

## 6. 决策与里程碑

M-P0-04仍待人工验收，本轮用户消息是独立测试授权，不是接受。暂无新增业务决定。不单设业务里程碑，结果并入M-P0-04验收证据。

## 7. 报告

两名独立测试作者新增12项操作场景，均通过，未发现业务缺陷。浏览器首轮5通过/1失败是textarea标签定位与内容变化不匹配，改用role textbox并保留原值/持久断言后通过；失败日志browser-initial.log保留。身份首轮6项通过，S4复核后加强IS05双请求等待锁观察；浏览器J04加强全旅程PATCH计数与前后完整投影不变断言，两组均再次通过。

证据：identity-barrier-verified.log 6通过/308未选择，9.26秒，run rpb_test_5ac7215bd97040c5a5f9bfcbd2d81535；browser-verified.log 6通过/308未选择，16.51秒，run rpb_test_aa57730747094f1583d855faa64b84c4；均明确server_stopped/root_removed=true。作者报告分别为identity-report.json、browser-report.json。业务代码、迁移、机器契约和依赖未改，沿用task023经验证的构建，无需重新构建不变产物。


## 8. 检查点

流程v1.7；S1基线/授权完成；S2两位独立作者完成新增测试；S3第三位只读审查/组合12项复验通过；S4覆盖复核加强双请求阻塞及全程写计数，S5复用既有夹具/小帮助函数无需额外抽象；S6全314项/静态复验通过；S7证据/文档/最终基线完成。恢复时核对本单、before及作者日志，不将旧302项结果冒充本轮执行。


## 9. 最终结果与交接

- S1–S7完成。本轮仅新增两份测试文件及四份文档变更，业务代码/既有测试/迁移/机器契约/依赖无变更，见scope-check.json。
- `integration-final.log`：完整314项通过（原302＋新增12），264.53秒，run `rpb_test_9d8bedb192504013a64e4963443e44a1`；临时PG17非管理员、真实HTTP/Chromium，数据库停止及目录清理成功。
- 第三位独立审查者`/root/scenario_review`：组合12项通过/302未选择，25.73秒，run `rpb_test_d49889cac331472ca2d51429388c2c2d`；两处测试观察缺口TC01/TC02已关闭，5个测试/源码哈希前后无漂移，清理成功。证据review-final.json、review-execution.log、review-input.json；不声称其执行了全314项。
- `check-final.log`：ruff/格式79文件、mypy43源文件、87后端单元、66契约、TypeScript/3前端测试通过。构建代码与task023最终构建一致，本次未重复构建/干净安装。现有Starlette弃用警告保留。
- 全套及独立验证绑定`final-input/`代码/测试；后续只有文档更新。最终`delivery/`完整252文件（含已有未提交/未跟踪内容）及receipt.json承接本次补验结果；引用、版本、范围及摘要检查见documentation-check.json。
- 设计：沿用现行规则，无新增未决设计；业务代码：未修改；新增测试：已实现并验证；工程收口：完成；M-P0-04：仍待人工验收，本补验不改变原授权与接受状态。

本轮验证范围内未发现新业务缺陷。测试定位修复与观察增强不修改产品规则；未运行生产、Provider/邮件或尚未实现的管理员治理/Run/知识构建。本报告连同task023提供M-P0-04最新验收证据，不启动下一业务阶段。
