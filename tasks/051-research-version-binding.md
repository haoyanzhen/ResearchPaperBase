# Task051 Research 会话创建与恢复

文档版本：v1.2
更新日期：2026-11-05

## 8. 最新检查点

- 流程 v1.11；S7 基础切片工程收口。用户本轮授权“检查项目当前进度，推进下一阶段任务”。按下一阶段计划先推进 Research，未授权部署、真实外部调用或全 backlog。
- 当前 HEAD：12c408b；既有混合工作区保留。task050 已本地提交，提交收尾不与本任务验证混记。
- 当前上下文 next-20261105-root；定向读取 ledger：`docs/workorders/evidence/task051_research/root-ledger.json`。
- 已实际执行 bootstrap 两条 read、task050 entry、计划§2/3、实施入口§2、工具§5、FR018/028、API§6；部分超范围行读取失败后改用有效范围，不计失败项为已读。
- 最近完成：S1/S2实现与自验，S3首轮独立审查；S4补权限、读取副作用、迟到响应与迁移覆盖；S5无收益重构不做。S6最终专项10/10通过，受影响独立复审通过。
- 独立审查：baseline_review 先完成入场，再独立运行5例并审查完整切片；两轮发现轮询覆盖、权限跨通道迟到回填、覆盖缺项，已修复，最终限定复审通过，15个业务产物指纹一致，证据`final-review/`。
- 当前基线：`final/snapshot`完整归档（525文件）及`final2/baseline.json`，后者之后仅前端权限epoch和测试夹具/回归变化；最终源码快照见`final-source/`。旧归档不得充当最终产物。
- 上一任务提交只核验12c408b存在，未重跑旧任务整轮验证。当前基础切片未获业务里程碑接受，不自动commit/push。
- 下一动作：轮次原子版本登记、受控Graph-RAG问答、流式失败恢复及历史引用；不把此基础切片当计划第1/2项完成。后续授权来源仍为本轮推进下一阶段，不要求逐任务审批；涉及新业务裁决或研究里程碑再交用户。

## 1. 目标与授权

2026-11-05 用户要求检查当前进度并推进下一阶段。依据 [下一阶段计划](../docs/workorders/next_stage_2026-11-04.md)，先建立可访问已发布版本上的 Research 会话创建、列表、恢复及后续轮次受理所需的固定版本基础。创建不生成回复、不写知识资产。后续问答仍须完成受控模型、流式失败、引用与浏览器闭环，不能用本基础切片代替。

## 2. 当前依据与基线

[FR018/028](../docs/design/01_functional_requirements.md)、[API §6](../docs/design/04-01_p0_operation_contracts.md)、[内部契约 §3](../docs/design/05-01_internal_module_contracts.md)。现有 Knowledge 已有 project-scoped 版本/默认指针；Research 尚无运行模块。Project 锁与授权采用现有本人 Project 入口，不扩大协作权限。

## 3. 修改落点

Knowledge 读取适配器；Research 存储、迁移、API及前端会话入口；隔离库需求测试和浏览器场景。实际产物清单与指纹在第5节保存。

## 4. 验收规格

| 需求 | 可观察行为/禁止副作用 | 测试与证据 |
| --- | --- | --- |
| R1 | 有可访问已发布版本才可建会话；空版允许且提示无项目证据；候选无法持久成为head | `test_research_create_restore_latest_and_replay`、`test_research_candidate_not_readable`、浏览器创建恢复 |
| R2 | 重复创建命令只建一次，参数冲突拒绝；事务失败无残留；24小时到期后新命令 | create/replay、rollback_duplicate_and_expiry、browser_lost_creation_response |
| R3 | 列表/恢复显示最新默认版，既有会话身份不变；读取不改变业务记录；更新保留焦点草稿，不允许旧响应覆盖 | create/restore、actual_owner_revocation_and_read_no_writes；browser_create_restore_version_notice_and_revocation持有旧轮询跨计时周期 |
| R4 | 无权、跨Project、删除、归档写入拒绝；当前权限不由历史绑定替代；拒绝后旧响应不得回填 | validation_permissions_paging_and_archived、actual_owner_revocation_and_read_no_writes（第二账号和禁用原账号）、browser_rejection_invalidates_late_restore |
| 后续R5（不在本基础切片） | 操作版本与依赖原子登记；历史绑定不随发布改变 | 后续轮次切片，未实现不计覆盖 |
| 后续R6（不在本基础切片） | 完整问答、流式/失败/引用/版本提示 | 后续Research里程碑，未实现不计覆盖 |

| R7 | 迁移空表可退、有数据锁后拒绝；升级故障不留下部分新表 | migration_preserves_populated_data、empty_downgrade_and_failed_upgrade_atomic；既有Project迁移/并发回归 |

## 5. 验证计划与证据

证据根：`docs/workorders/evidence/task051_research/`。先实际定向读工具§5；所有批次记录命令、完整日志、真实退出码及 delivery_summary 输出。测试由 `backend/.venv/bin/python scripts/run_storage_tests.py --postgres-bin /tmp/rpb50-pg17.fyE9zL/bin --pgvector` 创建临时PG17集群；`PYTEST_ADDOPTS`筛选及JUnit绝对路径写在每批run.json。日志保留停止服务/删除临时目录证明，不读取业务数据库。没有调用真实模型/论文源/邮件。

- `api1`：2/4通过，发现未持久cursor secret和错误候选fixture；改独立Research catalog，不修改Construction状态。
- `api2`：4/5通过，浏览器初步通过；候选fixture触发已有deferred seal保护，改断言拒绝提交而不是绕过约束。
- `s3-review`：审查者独立5/5通过，范围及后续缺项见审查记录。
- `final`：129/141通过，发现UTC Z契约及空库降级阻断；修实现和探针，不弱化断言。
- `final2`：142/143通过，包括134项既有Project回归；唯一失败为非法owner转移fixture被现有复合外键拒绝，改用禁用账号模拟现行撤权。不改变产品权限规则。
- `rejection-red`：用本任务归档旧前端复现迟到响应缺陷，finally恢复最终前端并重构建；见独立日志及源码指纹。
- `final3`：最终新增/受影响Research专项10/10通过、0跳过、退出码0；final2之后后端业务/迁移未变，134项既有Project有效结果按指纹复用。
- `unit`：600项中599通过，唯一失败为既有published_papers API越层导入。`architecture-baseline`验证该文件与HEAD逐字相同、原有7条违规一致；不称全局架构通过，不在此任务旁路修复或豁免规则。
- `contract`结构检查通过；`mypy`新增4个源码文件通过；`frontend-tests`4/4通过，前端构建通过；最新lint/引用一致性检查见`closeout/`。

浏览器连接真实API/隔离存储，知识版本为显式合成消费者fixture，不能据此声称重新验证真实Construction发布或Graph-RAG。运输延迟/丢响应/404用于确定性交错；第二账号和禁用权限另外走真实API。截图见`browser/`，已检查布局和移动宽度。

## 6. 业务决策与里程碑验收

既定版本规则无新增业务决定。研究里程碑以计划第1/2项完整链路为触发点，本基础切片不单设业务验收，不宣称FR028完整交付。

## 7. 单一交付报告

会话创建、列表分页、重开与当前知识版本显示基础切片已工程收口。空版可建且明确无项目证据；无版本拒绝；读不生成任务；权限/幂等/回滚/迁移边界及浏览器迟到响应已验证。API/前端、迁移0020、3条机器契约与对应需求测试已实现。

自动验证：final3 10/10；复用final2明确列出的134项既有Project通过项（`reused-regressions.json`，不把原失败整轮改称成功）；前端4/4、构建、契约结构、专项类型/lint通过。独立审查先自跑5例，最终核验10例及15文件一致性后限定通过。架构全局检查仍有与HEAD一致的既有越层导入失败，未关闭该缺口。

设计、实现、验证与接受分列：会话基础设计/代码/限定自动验证及独立审查完成；轮次/问答/引用尚未实现，Research里程碑未到触发点、未获人工接受。本轮保留混合工作区，未commit/push。正式运行环境迁移、真实模型质量和完整研究端到端不在本基础切片通过范围。


## 9. 用户确认与Git交接（2026-11-05）

用户在上述限定交付报告后回复“ok，推送git”，确认本基础切片并明确授权提交和推送。该确认不代表完整Research里程碑已完成。提交携带此前已定的FR-018每轮受理采用最新版本规范与机器契约前置，避免HEAD旧固定Session版本规则与实现冲突；相关计划仍为计划，不交付Review或自定义模块运行能力。

提交前15个最终业务产物指纹与final3一致，复用10项专项、134项既有回归及独立复审，不重跑旧业务。使用隔离索引，排除其他流程、旧任务、nightly及无关工作区改动。候选提交树另做契约、引用和diff检查，结果见push目录。完整源码tar归档留本地，发布核验清单和必要日志。提交SHA与远端一致性写入本地推送回执，不为记录自身SHA循环提交。
