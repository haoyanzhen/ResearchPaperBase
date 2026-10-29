# Task042：论文去重评分设计入口

文档版本：v1.2
更新日期：2026-10-29

## 8. 最新检查点

流程v1.9；上下文task042-main-20261028-2。D-CW-03已按用户“去标点、全小写标题”决定关闭；S1–S7已完成本Run去重/纠错切片，M-P0-13于2026-10-29获用户明确接受，见第12节；无本切片未决D。M-P0-12已提交39a38c0；task041/043工作区保留。当前验收包见[交付报告](../docs/workorders/task042_deduplication_delivery_2026-10-29.md)。

最后验证基线verification5（相对4仅6项覆盖补充测试）；运行源码/契约行为/前端未再变。其后仅契约info版本1.9→1.10与任务/状态/证据记录，未改变被审语义。最终23项专项通过；158项受影响回归和25项管理员回归复用verification4通过证据，集合有交叠，不加总为全项目全绿。当前没有全局PaperIdentity表、已发布成员排除或评分流水线。

## 1. 目标与授权

用户2026-10-28：“ok，通过M-P0-12，继续实现下一阶段，直到里程碑进度或遇到未明确设计”。随后明确标题唯一自动判断，原第6节门禁解除。本轮恢复后按可观察行为交付首个完整子成果M-P0-13：检索确认→本Run标题去重→逐来源查看→人工拆分/合并→统计、刷新和取消。不是最初拟议的整个去重评分阶段已完成。

评分、追加词、全局PaperIdentity持久化与已发布ProjectPaper排除、资料、解析/分析、知识版本发布仍待后续实现，保留原分期。它们不能用本Run分组验证宣称覆盖；下一评分切片依赖此里程碑接受。

## 2. 依据与基线

权威依据：[FR-022](../docs/design/01_functional_requirements.md) v1.62、[资产领域](../docs/design/02-03_construction_assets_appendix.md) v1.8、[操作契约](../docs/design/04-01_p0_operation_contracts.md)、[服务](../docs/design/06_agent_knowledge_services.md) v1.17、[持久化](../docs/design/07_data_persistence.md) v1.15，均已同步D-CW-03。自动匹配仅删除Unicode P类标点后lower；不合并空白、不casefold、不增加模糊匹配；空结果保持待处理。外部ID保留追溯，不作为自动判据。人工例外优先，标题不设不可纠正的全局唯一约束。

接受前基线与39a38c0提交见[task040第10节](040-construction-runtime.md#10-m-p0-12人工接受2026-10-28)。本轮before、verification1–5完整源码快照见[证据目录](../docs/workorders/evidence/task042_title_rule_2026-10-28/)，含未跟踪文件；task041流程/工具与本轮不混合提交。

## 3. 修改落点

新增domain/paper_identity.py纯规则及adapters/paper_deduplication.py事务内操作；扩展Run读取/确认/纠错、FastAPI路由、ConstructionRuns表单和机器契约，增加领域/隔离集成/浏览器测试。沿用JSONB Run持久事实，不新增表或迁移。

全部来源保留原始标题/摘要/标识，不拼接摘要。组代表按既有检索顺序确定，仅用于显示；未选取评分或解析文本。人工拆分/合并记录原因、操作者、时间、前后组；目标修订与被操作候选修订同时校验。人工例外可处理无有效自动标题的候选，并保留原始空标题事实；不生成替代标题或评分。取消纯机器候选仍清理正文；出现人工纠错时保留整组来源证据及历史，仍撤销写资格。

## 4. 需求与覆盖

单元缩写PI=backend/tests/unit/test_paper_identity.py；集成PD=backend/tests/integration/test_paper_deduplication.py；PDB=backend/tests/integration/test_browser_runs.py。各场景禁止正式知识/跨Project写入；数据库使用隔离PG并清理。

| 要求/场景 | 可执行依据 | 当前有效证据 |
| --- | --- | --- |
| PI01/02/06 标点/大小写等价、保留符号和空白、不额外转换、归一化幂等 | test_pi01/test_pi02/test_pi06 | check5单元21项专项（含其余PI），277单元总集通过 |
| PI03/04/05 空标题拒绝自动匹配、全部来源保留、DOI/arXiv不决定自动身份 | test_pi03/test_pi04/test_pi05；PD01 | check5、storage-final |
| PD01 确认绑定输入/候选、统计与原始metadata/source/screening不变、不发布 | test_pd01 | storage-final |
| PD02 人工拆分/合并/历史/组成员修订、幂等重放、取消保留人工来源证据 | test_pd02 | storage-final |
| PD03/09/12 确认修订、未知风险、非法/非ASCII/过期token拒绝且无写入 | test_pd03参数化、test_pd09、test_pd12 | storage-final；review-red保留初始失败 |
| PD04/08/13 未存在/自身/无组/真实跨Run目标拒绝、异载荷同键冲突、目标旧修订拒绝、真实跨Run有效token不可移用 | test_pd04/test_pd08/test_pd13 | storage-final |
| PD05/06 回执故障完整回滚；Event确定交错下同候选并发仅一个提交 | test_pd05/test_pd06，真实PG内部commit | storage-final |
| PD07/10/11 自动结果取消清理且保留统计；跨用户/CSRF拒绝；归档保留人工证据且不再可写 | test_pd07/test_pd10/test_pd11 | storage-final |
| PD14/15 空标题人工distinct/match可追溯；缺目标修订/distinct附带目标/空理由拒绝 | test_pd14/test_pd15参数化 | storage-final |
| PDB01 浏览器确认/拆分/合并、响应丢失原键重试、刷新、390px、取消后只读人工历史 | test_pdb01 | storage-final，dedup-mobile.png已视觉检查 |
| 受影响既有Run、Project命令/维护、管理员治理及公共契约无回退 | CR/PC/PM与AG原要求；精确契约兼容断言 | storage3 158项、admin-regression 25项、check5 |

未覆盖业务：全局身份/已有版本成员重复排除、评分与确认、追加检索、解析/发布及自动Run；本轮明确未实现，不属于已覆盖或通过。

## 5. 验证

[证据目录](../docs/workorders/evidence/task042_title_rule_2026-10-28/)保存真实输出；未访问真实LLM、论文源、邮件或业务库。PG17临时Unix socket、非superuser独立角色，所有storage日志均有run_id与server_stopped/root_removed。

- `python3 scripts/engineering.py check`：check5通过ruff/format/mypy、277单元、106脚本/契约、前端类型及4项测试。check1/4发现覆盖清单及旧request-only兼容断言，已精确同步新增契约，未放宽无关断言；check2/3格式/类型错误已修复。
- `npm --prefix frontend run build`：build2通过；随后只改测试和文档，浏览器测试加载此构建。
- `PYTEST_ADDOPTS='-k "test_pd or test_cr or test_pm or test_aa or test_pc"' backend/.venv/bin/python scripts/run_storage_tests.py --postgres-bin /opt/homebrew/opt/postgresql@17/bin`：storage3，158 passed/450 deselected，146.46s；aa未匹配管理员AG，因此另跑下一批，不把不存在匹配计通过。
- `PYTEST_ADDOPTS='-k test_ag' ...`：admin-regression，25 passed/583 deselected，33.70s。
- `PYTEST_ADDOPTS='-k test_pd' ...`：storage-final，23 passed/591 deselected，22.32s，包含PDB01及新增6个覆盖场景；与前批有交叠。verification5仅新增测试，无业务源码漂移，复用未变受影响回归。
- review-red两项失败已保存：旧实现不支持目标修订、非ASCII签名500。新增目标修订绑定和ASCII拒绝后，PD08/09通过；并发、权限和来源保护未弱化。

M-P0-12历史接受仅针对旧检索行为；新增确认/去重入口及取消人工保护本次提交M-P0-13验收。无全项目端到端完成或真实Provider在线验收声明。

## 6. D-CW-03：论文身份冲突及疑似匹配处理

问题：候选DOI命中身份A、arXiv/Provider标识却命中B，或仅标题相同但强标识不一致时，如何决定自动处理和人工修正范围？普通同DOI沿用身份与标题不能唯一约束已明确；缺的是冲突裁决，不是重新讨论这些规则。全局合并会影响多个Project，不能由当前Project用户操作隐式决定。

- A（推荐）：强标识一致且无矛盾时自动匹配；仅标题匹配或强标识冲突进入待人工确认，不自动合并全局身份。用户可在当前Run修正候选元数据、判为不同，或选择同Run候选/同Project资产进行匹配；提交须重新验证强标识一致性与唯一性，不能保留冲突强标识并强行合并。未解决项不得进入解析；保留来源、原值、操作者和决定，禁止改写已发布资产或其他Project。API补同Run候选目标属于本规则落地。
- B：定义标识优先级并自动选胜者，保留冲突记录；需进一步明确DOI/arXiv/Provider的排序、冲突标识处置及既有引用影响。自动化程度更高，但可能误排除不同论文。

A是待批准建议，不是现行规范。仅阻塞依赖身份裁决的去重/评分候选集合与相关确认流程；M-P0-12接受和本地提交已独立完成。无其他独立授权任务待执行。

## 7. 阶段与恢复

S1：批准规则同步，限定首个可用成果及M-P0-13触发点。S2：领域/运行/UI/契约与逐需求用例。S3：review_title_rule独立审查发现目标修订未绑定、非ASCII签名异常两项，修复后verification3增量通过。S4：补真实跨Run、空标题人工例外及负向字段用例，verification5复审通过，矩阵对齐实际ID。S5：保留现有Run JSONB/权限事务/重试UI，不新增全局表、Provider依赖或无关重构，无进一步简化收益。S6：check5/build2及各隔离批次有效通过，未变依赖证据复用依据见第5节；最后仅版本元数据/交付记录变更。S7：限定工程收口，M-P0-13待人工接受。无新增D，不自动提交本里程碑。

## 9. 用户决定与恢复实现（2026-10-28）

用户原话：“可以，这个可以只以去标点符号、全小写的标题来判断是否是同一论文身份”。D-CW-03已关闭，按用户实际标题规则执行，不按第6节历史A/B强标识建议；第6节的等待描述保留为当时记录。独立规范核对认为不同来源内容选择可作为工程细化，没有新增业务门禁。当前成果、缺项和验证以第1/4/5/7/8节为准。

## 10. 最终交接核验（2026-10-29）

110个本地引用与30个锚点、日期/版本、diff whitespace和空暂存区核验通过；contracts-final通过78项请求/响应部分契约、30项请求契约及219个schema检查（该命令未单独提供历史baseline；精确历史兼容回归已在check5脚本集验证）。最终矩阵/验收包由review_title_rule独立核对通过；无未关闭发现。

源码证据：verification5→handoff仅增加交付包、任务/状态记录及OpenAPI版本元数据；业务源码、运行测试和构建源码无漂移。before→handoff保留task041既有修改；最终handoff含未跟踪源码，接受后按它核对提交范围。全项目其他功能仍由状态入口跟踪，不据本切片关闭。

## 12. M-P0-13人工接受（2026-10-29）

用户原话：“ok，通过M-P0-13，继续实现下一阶段，直到里程碑进度或遇到未明确设计”。接受范围为第1/4节及验收包中的本Run去重与人工纠错。接受基线为task042_title_rule_2026-10-28/handoff，业务源码、契约、测试及业务规范无漂移，复用第5节验证与独立审查。隔离索引仅提交该基线业务产物与本接受记录；task041/043和每日整理保留工作区，不push。
