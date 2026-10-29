# Task044：论文评分与人工判断保护

文档版本：v1.1
更新日期：2026-10-29

## 8. 最新检查点

流程v1.10；当前上下文task044-main-20261029-2。S1–S7已完成本限定切片工程收口，M-P0-14于2026-10-29获本轮用户明确接受，无新增设计待决项。用户本轮接受M-P0-13并授权继续下一阶段至里程碑或未明确设计；M-P0-13已本地提交cb9b28f，未push。M-P0-14包括Run内论文评分/理由/阈值、分来源输入及模型依据、人工评分/有效性调整、受保护重评、统计和浏览器流程；不包含解析确认、全局成员、非论文资料及知识发布。

恢复入口：[验收包](../docs/workorders/task044_screening_delivery_2026-10-29.md)、本单第4/5节、[独立复审](../docs/workorders/evidence/task044_screening_gate_2026-10-29/review-code-s6.md)、evidence内handoff快照与milestone-paths.json。verification12为最终业务验证基线；handoff只增加收口记录，task045并行流程文档变更保留且不属于本任务。恢复须更换context并定向重读必要原文、比对快照，不能只凭完成标签。

实际工具采用：AGENTS两条bootstrap、entry task042/task044、outline/read及main-ledger；恢复后context从task044-main-20261029切换为task044-main-20261029-2并重读所需原文。verification各轮实际snapshot、run_check记录命令/退出码并调用delivery_summary；首次storage1缺单独前置快照不复用为最终通过证据。错误路径/范围读取通过outline纠正；日志尾部截断与完整日志分别保留，不假称全文已读。来源及合并政策独立核查不代替S3代码审查。

## 1. 目标与授权

用户2026-10-29：“ok，通过M-P0-13，继续实现下一阶段，直到里程碑进度或遇到未明确设计”。本轮顺序为M-P0-13接受核对和本地提交→DD-G02/03评分切片S1→设计明确后实现至M-P0-14；若遇未明确设计按指令保存待决项。DD-G01/04/05、解析发布及完整FR-022不因本次评分切片自动完成。

## 2. 依据与基线

- [FR-022](../docs/design/01_functional_requirements.md#fr-022-论文与资料去重评分与筛选)：标题/摘要等输入，理论/技术/Project相关性理由，0–10分、阈值7、失败保持未判定。
- [task042第3节](042-paper-deduplication-gate.md#3-修改落点)：所有来源保留原文，组代表仅显示，未选择评分/解析文本；第11节DD-G02明确要求S1核对来源文本规则。
- [06第4节](../docs/design/06_agent_knowledge_services.md#4-construction-pipeline)和[04-01](../docs/design/04-01_p0_operation_contracts.md)：冻结模型、人工保护与输入修订，不从组代表推定评分来源。
- 实际paper_deduplication.refresh按候选顺序确定组代表，不融合元数据。M-P0-13源码与handoff无漂移；全部实际差异见accepted-diff.json。

## 3. 修改落点

实际修改paper_screening（命令、来源注册、人工调整、覆盖预览、统计）、paper_scoring_worker（四协议评分与读取/派发/提交重验）、runs/API（Task及候选入口）、paper_deduplication（旧依据失效）、ConstructionRuns（分类/评分/人工调整/确认）、run_business_demo（接入Worker）。复用现有Run JSONB和Project来源状态表，没有新增物理表或迁移；不可变输入及评分任务随受理事务持久化。contracts增量闭合对应有限请求/响应；完整解析确认、发布及一般Task仍不在范围。

## 4. 需求与覆盖

| 规则及场景 | 可执行测试 | 有效证据 |
| --- | --- | --- |
| 同身份组一次评分、各来源原文/缺失摘要、不伪造融合摘要；0/7/10及默认阈值、理由、冻结模型依据 | PS01；test_scoring_protocol_and_boundaries | storage10、check10；四协议18项Provider单测 |
| 非法结构/分数/空输出/凭据回显不产生伪0；部分成功与超时 | PS02、PS11、PS15；test_scoring_invalid_output_has_no_fake_score | storage10、check10 |
| 来源先分类；当前政策、账号和Project资格在读取/派发/提交重验 | PS03、PS07、PS19九种确定性交错 | storage10；独立复审21项包含PS19 |
| 人工编辑评分/有效性、最小来源/人/时间/状态；阈值来源展示；仅valid不编造分数、仅score按阈值 | PS04、PS12、PSB02；ScreeningContracts | storage10、check10、独立复审 |
| 完整覆盖预览、取消确认无副作用、失败保留；token绑定当前修订/目标集/Run/actor/到期 | PS04、PS05、PS11、PS12、PS18五种绑定反例、PSB01 | storage10、独立复审 |
| 纯预览无需幂等键，不写回执/任务/候选；CSRF及权限仍校验 | PS17、PS13；ScreeningContracts | storage10、check10、原独立反例复验 |
| 取消撤销执行资格、迟到结果不写入；纯机器三次重评后清理文本；授权重评后仍保留人工历史 | PS05、PS11、PS14、PS15 | storage10、原独立反例复验 |
| 合并保留双方旧判断且失效，不选择胜者；显式新判断同步；双方判断及追溯可见 | PS06、PSB02；既有PD拆分/回滚/统计 | storage9未受Meta失败影响项、storage10、独立复审 |
| 幂等重放、活动互斥、并发Worker无重复派发；实际回执写失败全回滚 | PS01、PS04、PS08、PS09 | storage10 |
| 非法目标/修订/替换模型、跨用户/CSRF拒绝无副作用；冻结参数但凭据使用当前版本 | PS10、PS13、PS16 | storage10 |
| 真实浏览器分类→评分→理由→人工编辑→取消覆盖→刷新，移动无横向溢出 | PSB01、PSB02 | build4、storage10；两张移动截图已查看 |
| 已接受去重/检索、检索词、Project维护及管理员撤权受影响回归 | PD/CR/ST/PM/AG测试集合 | storage9共244项中239通过，5个失败均由storage10修复复验；不加总重叠用例 |

S4逐项复核以上成功、拒绝、失败、并发、权限、修订与人工保护，补充PS17–19及PSB02均已有通过证据，没有本切片必需覆盖缺项。FR017的候选入库确认、FR022全局已有成员/资料/返回检索/解析入库等未实现范围仍明确开放，不以本切片代替完整FR验收。真实供应商内容质量与线上集成未测。

## 5. 验证

统一证据目录：[task044 evidence](../docs/workorders/evidence/task044_screening_gate_2026-10-29)。每个批次有完整.log、实际-run.json和执行delivery_summary得到的-summary.json；存储测试有本轮JUnit。

- **check10退出0**：295后端单元、116脚本、4前端测试，以及ruff/mypy/架构/契约/TypeScript检查。**build4退出0**：后端包及前端构建成功。
- **storage9**：244项，239通过、5失败；4项为已移除幂等回执后Preview机器Meta尚未同步，1项为新增“最后人工修改”文字使旧模糊浏览器定位不唯一。**storage10退出0，79/79**：修正Meta及精确定位后重跑全部test_ps；包含全部失败路径及新增PS17/18/19、PSB02。未改变既有应用/断言语义来迎合测试。
- **独立复审**：[review-code-s6](../docs/workorders/evidence/task044_screening_gate_2026-10-29/review-code-s6.md)。原3个失败反例原样通过，独立21项集成/浏览器与3项契约全通过，R1–R5及P3闭合。
- 存储运行使用显式临时PostgreSQL17、非superuser角色与Unix socket；每项fixture隔离清理，包含真实服务提交。主/独立运行均记录server_stopped/root_removed；没有回退到业务数据库。模型/论文源/邮件使用替身，无真实外发或付费调用。
- verification12绑定最终业务源码、测试、契约及配置；相较verification11仅修正Preview Meta/文案、PSB01精确定位并新增3项契约测试，UI仍为build4。此前失败与修复历史保留在第7节，不能替代最终证据。最后handoff只追加记录与文档核验，复用未变化业务证据，不机械重跑。
- 可复现命令：`python3 scripts/engineering.py check`、`python3 scripts/engineering.py build`；隔离业务测试使用`PYTEST_ADDOPTS='-k "test_ps"' backend/.venv/bin/python scripts/run_storage_tests.py --postgres-bin /opt/homebrew/opt/postgresql@17/bin`。本次执行额外使用唯一JUnit路径，精确命令见storage10-run.json；复跑应使用新日志/报告路径。

M-P0-13接受时snapshot diff退出0仅证明差异清单生成；其业务产物未漂移，因此复用task042原有效业务证据并完成接受提交，没有因本轮接受重跑旧交付。

## 6. 业务决策与里程碑

无新增D。各来源分别保留标题/摘要作为结构化输入；无摘要如实记录，不伪造文本或0分。人工合并冲突保留原决定并标示旧范围依赖失效，新范围通过现有人工编辑或显式覆盖重评分重新确定，不让目标候选或显示顺序决定有效性。已有D-CW-02/03继续生效，不重复问评分尺度或身份规则。M-P0-14现已达到完整限定业务成果触发点，工程收口后提交一次验收，未获用户答复不得标人工接受。

## 7. 阶段与交接

M-P0-13已人工接受。本任务S1/S2完成；S3独立审查发现R1–R5后回S2修复，受影响验证和独立复审已闭合；S4逐需求复核完成；S5检查重复与分支，保护函数分离及统一Task错误投影已简化，未扩大为跨Provider重构；S6复核最终基线与有效证据，S4/S5之后无业务变更，复用独立复审；S7保存handoff、验收包、范围清单和状态。M-P0-14等待人工验收，没有新D。

独立入口核查纠正了主agent初始担忧：task042第9节已有“来源选择为工程细化”的结论；不存在新人工门禁。M-P0-13已提交cb9b28f，保持原范围。


### S2迭代与差异（2026-10-29）

- storage3为222项：219通过、3失败。浏览器辅助client的旧CSRF改为真实UI主题分类；PD05已增加操作前持久原文快照，继续同时断言HTTP投影不变与真实持久候选不变，未删除回滚断言；PS09按应用真实500响应验证注入已触发及回滚，不误期望HTTP层抛内部异常。
- storage4为103项：101通过、2失败。浏览器有效性select补明确可访问名称；第二次评分预览测试必须使用新幂等键（旧helper默认固定key），不修改产品幂等语义。
- 自审修复模型回显凭据被拒绝后仍残留于内部job.results的风险；PS11检查持久Run无明文密钥，并测试显式覆盖成功保留历史。取消无人工内容的机器评分同时清理job.input/results文本副本，PS14复核；人工内容及其依据保持保留。
- check6通过295单元、契约检查，113脚本中旧评分操作兼容断言失败；精确加入新响应/错误集合/FR与actor header断言并保留历史request相等检查，contracts1中8项通过。check7遇未改动SMTP本地stub的2秒超时（294通过、1失败），需在非并行负载下复验，未削弱超时断言。
- verification6及build3已保存。storage5复跑评分、去重/检索浏览器、机器取消；这不是整体FR-022验证。评分来源/合并工程决策独立证据见review-source-policy.json、review-merge-scoring-policy.md；它们不是本轮代码S3。

### S2完成与S3交接

verification10为代码审查基线。storage5：65/65；storage8：2/2（PS15/16）。storage6/7失败来自测试误用无序任务列表及把内部错误码当公开错误码；现按受理status_url及持久内部错误分别断言，未削弱过期结果不得写入要求。check8仅导入空行失败，check9完整工程检查退出0（295单元、113脚本、4前端，以及类型/契约/架构检查）；build3有效。check9日志摘要有尾部截断，完整日志保留，非声明全文已读。恢复context已切换为task044-main-20261029-2，实际entry/read与新verification8–10见ledger及run/summary。两次错误section/range通过outline纠正，不以失败读取判定规则缺失。S3要求独立读取当前完整任务产物、规范与反例。

### S3发现与修复批次

首次完整审查绑定verification10，见[review-code-s3](../docs/workorders/evidence/task044_screening_gate_2026-10-29/review-code-s3.md)：5项P2（机器历史误保护、纯预览错误回执、合并旧判断不可见、仅有效性编辑受阻、首次人工阈值展示），没有新D。独立66项中63通过、3个反例失败，18项Provider通过。已修复保护/保留判断分离、纯预览分支、UI展示与编辑；评分错误统一安全文案，收窄评分Task复制残余。verification11/build4后运行storage9完整受影响集合。PS11/14加强机器多次评分与人工历史取消保护；新增PS17纯预览无回执、PS18五种token绑定反例、PS19九种权限边界交错、PSB02仅有效性/仅评分/合并双方判断可见。纯预览Meta仍需同步为非幂等响应后做契约复验，不宣称本批已全部闭合。

### 最终工程收口

S3后的修复详见第5节有效证据和review-code-s6；第7节之前的“执行中/待同步”均为对应历史批次状态。纯预览Meta现已同步且PS17和契约核验通过。S5保留现有Provider协议适配结构，跨模块抽象会扩大已接受检索词路径的影响，当前没有行为保持收益足以支持额外重构。handoff之后等待M-P0-14接受；后续解析/入库为新的限定业务切片，不以本次通过自动宣称实现。

## 9. M-P0-14人工接受（2026-10-29）

用户：“ok，通过M-P0-14，继续实现下一阶段，直到里程碑进度或遇到未明确设计”。接受范围为本单限定评分与人工保护切片；接受基线为handoff及verification12。task046的accepted-diff实际核对handoff后业务/契约/测试无漂移，仅新增task046记录；accepted-evidence核验19项产物、版本引用及check10/build4/storage10执行证据通过，复用review-code-s6有效独立复审。本次未重跑旧业务测试。接受记录与本地提交按实施入口v1.11最小包执行，混合PROJECT_STATUS按HEAD构造仅业务状态补丁；流程与每日整理修改保留。提交SHA在后续检查点记录，未push。下一阶段S1独立记账于task046，不把其设计核查列作本阶段重新验证。
