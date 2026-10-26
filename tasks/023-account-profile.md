# Task023：个人账户资料维护

文档版本：v1.0
更新日期：2026-10-26

## 1. 目标与授权

用户2026-10-26接受M-P0-03并授权下一阶段直到里程碑或未明确设计。下一可使用切片为M-P0-04个人资料维护：本人邮箱/显示名编辑、再次读取与登录、冲突和失败恢复。仅FR001本人资料、04 UserPatch；不实现管理员治理、头像上传、密码更改、配置或P1。达到本完整业务成果后提交单一验收包。

## 2. 依据与基线

01 FR001及2026-10-25身份规则；04/04-01 §1/2 UserPatch省略保持、display_name可null、未知字段拒绝，修订428/412；03-01 P06a；08本人权限；07隔离事务。沿用账号治理锁使注册和邮箱变更的跨字段唯一性原子成立。当前显示名硬编码null、没有PATCH /me。HEAD为`7ba2a2c638500eaa43f2137d16a6a0686b663630`；原工作区全部保留；before快照包含未提交/未跟踪文件。M-P0-03接受绑定task022原delivery。

## 3. 修改落点

AccountPort/Store、账户路由、显示名列迁移、BusinessApp资料入口、真实PG/HTTP/浏览器需求测试；状态和使用说明。沿用当前会话，不新增隐式登出、邮箱验证或通知策略。用户名/权限/密码不允许更新。

## 4. 验收规格

AP01：邮箱/显示名部分修改，省略保持、null清空显示名、显示名strip后长度、邮箱展示原文及归一化登录键、空修改不推进修订，重读一致；保持密码/权限/项目/他人信息。
AP02：归一化跨字段身份唯一、同账号用户名邮箱可相同；新邮箱可登录，旧邮箱不能登录（除非仍为用户名）；注册/编辑和并发编辑竞争仅一份成功。
AP03：本人身份/禁用/CSRF/origin；缺修订428、陈旧412、未知/只读/null邮箱/坏格式422；失败不写。
AP04：真实事务故障回滚；迁移保留已有账号、metadata一致、非空显示名降级拒绝及并发保护。
AP05：浏览器显示/编辑/取消/保存/刷新；明确校验可纠正、冲突/未知结果保留草稿并显式核查，跨标签换账号不可提交旧草稿；桌面与窄屏。

需求到用例：AP01→test_ap01_partial_clear_noop_and_protected_facts；AP02→test_ap02_identity_uniqueness_and_login / concurrent_edits_have_one_winner / identity_claim_serializes_with_other_writers；AP03→test_ap03_invalid_rejected_without_writes / revision_and_authorization；AP04→test_ap04_write_failure_rolls_back / migration_preserves_data_and_guards_downgrade / committed_profile_prevents_waiting_downgrade / database_rejects_oversized_display_name；均在backend/tests/integration/test_account_profile.py。AP05→test_account_profile_browser.py的编辑/取消/保存/重读（桌面/窄屏）、冲突/丢响应、换账号场景。另含明确校验可纠正、页面往返保留草稿及未知结果状态。审查补充R2旧邮箱登录确定性交错回归、R3修订129字符拒绝。

## 5. 验证计划与证据

隔离临时PG17及真实HTTP/Chromium，沿用engineering.py integration/check/build。无外部LLM/邮件调用。证据目录docs/workorders/evidence/task023_account_profile_2026-10-26。未执行项不得标通过。

## 6. 业务决策与里程碑

当前无新增业务决定。M-P0-04范围为AP01–05，不代表完整账号治理或配置。S1–S7工程已收口，现提交验收；用户尚未接受M-P0-04。

## 7. 交付报告

本人资料维护已实现：持久显示名列、原子邮箱唯一性/修订检查及浏览器编辑。沿用现有账户治理锁；普通字段写入不会改密码、管理员身份、启用状态、Project或其他账号。UI保留往返草稿，未知结果显式核查后才可再保存。

独立初审R1页面切换丢输入、R2旧邮箱登录竞态、R3修订长度缺上限均已修复并补回归，31项新增集成通过，最终独立31项及全套302项已通过，R1–R3独立复审关闭，无剩余阻断项。S4逐AP覆盖复核补齐并发注册竞争、降级竞争、数据约束、验证纠正与往返状态；S5无必要重构，保留现有事务组件和Profile局部状态。


## 8. 检查点

流程v1.7；S1范围基线、S2实现/需求自验、S3独立初审及R1–R3修复、S4逐AP覆盖修复、S5保持行为无需额外重构、S6最终302项/独立31项及检查构建、S7文档/基线交接全部完成。授权来自本轮用户消息。下一动作是M-P0-04人工验收；按用户本轮指令停在里程碑，不继续依赖本验收的下一业务阶段。配置设计核查不扩大本里程碑。

首轮integration.log：255通过、2失败、38后续清理错误；一项新增身份测试生成了非法邮箱前置，另一项旧test_ps01降级0001后使用含新列的现行metadata读取，导致失败后旧schema使后续清理报错。分别修正测试前置，以及比较全部旧列并另断言新显示名为null；保留原数据保持断言。profile-s2.log修复后28项通过；independent-profile-initial.log独立28项通过但仍指出R1–R3，不算审查通过。profile-repairs.log加入审查回归后31项通过。integration-s3.log为审查修复期间的中间轮，不作为最终源码验证。最终代码/测试绑定final-input，后续只更新文档/证据。


## 9. 最终验收包（2026-10-26）

- 范围：AP01–05本人邮箱/显示名编辑及成功、拒绝、并发、故障恢复。依据现行已定设计，没有新增业务决定。未完成完整FR001/005、头像、密码管理、个人/系统模型或数据源配置、知识构建及生产部署。
- 最终全套`integration-final.log`：302项通过（原271项＋新增31项），239.92秒；run `rpb_test_8684f6961d714b75b984bc415c085660`，临时PG17非管理员、HTTP、真实Chromium。server_stopped/root_removed均true，无外部Provider/邮件调用。源码与测试绑定`final-input/`，文档追加不改变受验行为。
- `check-final.log`：ruff/格式77文件、mypy43源文件、87后端单元、66契约、TypeScript和3前端测试通过；`build-final.log`：wheel和前端构建通过。无依赖或锁文件变化，未重复干净安装。现有Starlette测试客户端弃用警告仍在。
- `independent-review-final.json`：审查者`/root/next_stage_design_review`独立复审关闭R1–R3，31项/271未选择，38.72秒；run `rpb_test_9f61a80091274a73a0556d9df63d717a`清理成功。9个审查源码/测试哈希执行前后无漂移，不声称独立重跑全部302项。
- 迁移`0006_account_profile`增加可空显示名与长度约束；有已保存显示名时拒绝降级，防止丢数据。本片新邮箱可修改路径暴露并修复原登录竞争条件；原注册/Project行为全套回归通过，旧人工接受仍绑定旧基线，本轮新增行为及受影响边界由M-P0-04验收。
- `scope-delta.json`列本轮17个变更/新增文件；`documentation-check.json`记录引用、版本/差异检查。仓库全局diff检查的六个其他设计文件末尾空行来自入场既有改动，保留；本片源文件空白检查通过。
- 最终`delivery/`是完整249文件内容快照（含已有未提交/未跟踪文件），`receipt.json`保存清单摘要和执行证据；此前快照和失败日志不覆盖。

可复现演示：在仓库根执行`python3 scripts/engineering.py build`，再执行`python3 scripts/engineering.py demo --postgres-bin /opt/homebrew/opt/postgresql@17/bin`，打开`http://127.0.0.1:8765/workspace`。注册/登录→个人资料→编辑邮箱和显示名→取消或保存→返回项目再进入验证草稿保留→刷新重读。保存新邮箱后退出，用新邮箱登录；旧邮箱在不等于用户名时不能登录。两标签同时编辑后，旧修订保存应保留草稿并要求显式核查；其他账号占用的邮箱应拒绝且允许纠正。演示只使用临时本地数据库，退出监督进程即清理。

交付状态：设计按现行规则落实；代码完成；自动验证完成；工程收口完成；M-P0-04待人工验收。M-P0-03已接受，见task022第10节。下一阶段配置等仍未启动，不把审查和测试通过当作人工接受。
