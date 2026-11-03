# Task049：M-P0-18 手动论文入库与知识版本发布

文档版本：v1.27
更新日期：2026-11-03

## 8. 最新检查点

2026-11-03 用户明确验收通过 M-P0-18 手动论文构建范围，要求将筛选全部排除、配置或依赖变化后的重建、显式移除和临时资产回收合并为一次本地提交。接受基线为 excluded/candidate4 及 remaining/delivery-source。提交前按实施入口核对已审业务文件与索引，复用既有验证和独立审查；核验清单见[提交范围](../docs/workorders/evidence/task049_manual_acceptance_2026-11-03/scope.json)。

2026-11-02 用户授权继续实现三项剩余工作。依次交付手动论文构建的配置或依赖重建、Construction 显式移除知识成员、临时资产清理与回收。前两项定义正式引用及其历史保留范围，回收须验证这些引用。全排除子范围仍按上一检查点等待人工验收。本次未收到 Git 提交或整体验收指令。
三项手动论文实现已完成工程验证和独立复审，等待人工验收。可在构建面板选择「按当前配置与依赖重建」、预览单篇或全部移除，或在失败 Run 详情确认清理。验收截图见[重建](../docs/workorders/evidence/task049_ingestion_2026-11-02/remaining/browser-final/rebuild.png)、[移除清单](../docs/workorders/evidence/task049_ingestion_2026-11-02/remaining/browser-final/removal.png)、[空版本](../docs/workorders/evidence/task049_ingestion_2026-11-02/remaining/browser-final/empty-version.png)、[回收结果](../docs/workorders/evidence/task049_ingestion_2026-11-02/remaining/browser-final/cleanup.png)。非论文资料、显式重新导入、Research/Review 对空版的消费与历史版本保留政策另行跟踪。


2026-11-02 用户接受检索完整返回零条并要求一次 Git 提交。已本地提交 `38b4d73`，父提交 `240034e`。提交前按 zero-retrieval/verified 核对业务内容，复用该切片的最终验证及独立审查；只暂存零条实现与相关验收记录，提交后核对树和暂存区。[提交核验](../docs/workorders/evidence/task049_ingestion_2026-11-02/zero-acceptance/summary.json)。

用户随后授权手动增量检索有结果但筛选全部排除。已完成现有纯论文基线上，完整检索有结果、去重后至少有一篇待筛选且全部判定无效的场景，包括同时命中既有论文和多个来源重复同一篇。先确认排除范围，在入库预览核对每篇排除理由，再确认核验既有版本。成功记录 succeeded/no_change，无新版或发布事件并释放写槽。改动筛选会使原确认失效，待判定、评分失败、当前依据与已评分输入不符时不能完成排除核验。此子范围已工程验证，待用户验收，未提交。[浏览器入库预览](../docs/workorders/evidence/task049_ingestion_2026-11-02/excluded/browser-final/excluded.png)。

2026-11-02 用户明确接受全匹配 no_change，要求提交一次并继续处理检索返回零条。全匹配已本地提交 `240034e`，父提交 `2795d91`。验收基线、候选文件与提交树经核对，原有流程及其他任务改动留在工作区。[提交核验记录](../docs/workorders/evidence/task049_ingestion_2026-11-02/matched-acceptance/summary.json)。

前一子范围实现手动增量检索完整返回零条且有既有纯论文基线的场景。用户可以查看零条及其基线，确认范围后再确认核验。只有既有资产、文本、向量及图谱核验通过，Run 才记录 succeeded/no_change 并释放写槽，版本和默认指针保持原值。旧零条记录缺少严格分页证明，继续留在原流程。检索完整返回零条子范围于 2026-11-02 获用户明确验收通过。[浏览器截图](../docs/workorders/evidence/task049_ingestion_2026-11-02/zero-retrieval/browser-final/zero-results.png)。

2026-11-02 用户要求继续推进。已完成手动普通增量检索中「来源完整返回、至少一条候选且全部命中冻结纯论文基线」的 no_change 成功决定。用户可修正去重，也可确认匹配范围，再确认核验既有版本。系统检查受保护论文与文件、文本分块和定位、模型配置、向量及证据图谱。成功时同一事务记录所核验的版本、范围和时间，将候选标为已废弃／核验无变化，释放本 Run 写槽。版本、默认指针与发布事件保持原值。工程收口，2026-11-02 用户明确验收通过本全匹配子范围。[浏览器核验结果](../docs/workorders/evidence/task049_ingestion_2026-11-02/no-change-completion/browser-final/no-change.png)。尚未覆盖来源真正返回零条、筛选后全部排除、配置变化后的重建及清理。

2026-11-02 用户接受普通手动增量发布，本地提交 `2795d91`（M-P0-18 限定范围）。核对提交树和接受基线的 24 个业务文件，一致；原工作区的流程、历史记录及其他任务改动保留。此次授权的一次提交已完成。[提交后核验](../docs/workorders/evidence/task049_ingestion_2026-11-02/accepted-increment/postcommit/summary.json)。

此前零新增预览切片。筛选等待中，只有完整取回本轮来源且每条候选都已匹配冻结版本的论文时，Run 详情显示候选条数及不同基线论文数。用户仍可拆分误合并，拆分后预览消失。此阶段没有入库确认、知识状态写入或成功决定。[浏览器实测](../docs/workorders/evidence/task049_ingestion_2026-11-02/no-change-preview/browser-verified/baseline-match.png)。其后续正式核验见本页最新检查点。

2026-11-02 用户继续授权 task049。手动增量检索已接通入库预览确认、构建 Worker、就绪证明和原子发布。适用范围是保留基线全部论文，至少新增一篇确认论文，配置和依赖兼容。浏览器验证同一 Project 的第二次发布：预览列出基线和新增数量，新版读出新旧两篇论文，旧版继续按原修订读取人工分析。2026-11-02 用户明确接受「手动论文增量发布」子范围并要求本地提交；整体里程碑、零新增/no_change、清理、显式移除与重算仍开放。首版人工接受基线仍为 `a07f21d`。

此前内部候选图谱已验证只抽取新增片段，同时保留每篇论文自己的支持与定位。

前一切片完成增量向量构建。普通增量检索有新增论文且配置和依赖匹配时，内部向量构建器已能从永久发布引用读取基线视图，引用旧 embedding ID，只为新增文本计算向量，并封存完整的候选视图。撤权或保留文本损坏会阻止封存，默认版本仍指向原版。

前一切片完成论文保留清单的内部确认与暂存核验。

上一切片承接 PUB-G02 的冻结配置与迟到写入。已从正常 Worker 入口验证，向量执行凭据变化后，旧结果无法封存，也无法通过失败处理结束当前 Run 或释放槽位。本子项工程收口，首版人工接受基线仍为 `a07f21d`。


2026-11-01 用户指定的手动论文首版子验收点已跑通，2026-11-02 用户明确验收通过。新 Project 的浏览器入库确认走既有幂等命令，获槽的 Worker 构建，独立连接比对分块、对象与封存视图，冻结清单及就绪证明，短事务重验当前身份、来源政策、基线、attempt/epoch/租约和依赖保护；一次登记版本、正式 pin、默认指针、永久视图引用及发布事件、Run 成功并释放槽。浏览器打开该版后从不可变论文修订读取人工分析。当前范围是手动论文首版，图谱质量、后续增量/no_change、显式清理/历史删除、非论文与全里程碑验收另行跟踪。失败记录保留与重新运行沿已批准规则。

入场完整源码快照：[baseline](../docs/workorders/evidence/task049_ingestion_2026-10-30/baseline/)，436文件，包含未提交及未跟踪源文件；初始工作树完整清单位于同目录上层`initial-git-status.txt`。定向读取context为`m18-20261030-b`，工具步骤实际读取及指纹记录在`root-ledger.json`。前序A09设计曾获限定人工接受，06文档“待人工审核”是遗留状态文字，运行能力未验证；不能将设计接受视为实现通过。不得清理或覆盖入场混合改动。

## 1. 授权与范围

本任务范围以用户指令与FR-026、02-02、04-01、06 A09、07的现行约束为依据。优先分小切片完成入库预览与后续构建能力，逐项记录测试与审查；不得以预览或mock图谱冒充完整发布。里程碑验收场景、具体需求矩阵及依赖随S1继续细化。

## 4. 需求追踪

| 范围 | 场景与证据 | 状态 |
| --- | --- | --- |
| FR-026手动入库预览 | 确认分析子集、跳过、失败、来源失败、摘要降级、阻断确认；隔离PG及浏览器`focused1`、响应schema由TermsClient校验 | 局部实现，限定复审通过；更多边界及最终全量覆盖待复核 |
| A09文本分块 | Unicode原文偏移、段落边界、最多384正文token和64重叠、编码上限失败；chunking-test2 4项通过，独立反例及修复复审、真实E5 tokenizer烟测通过 | 已接首版内部向量构建；完整定位闭包和增量版本待验证 |
| 构建槽与迟到写入 | slot-test5 6项和slot-regression3隔离PG 202项通过；独立复验迁移、取消、迟到写入、租约过期保持槽位 | 首版已接发布并复验过期执行者保槽；增量发布竞争待覆盖 |
| 候选锁的基础防护 | candidate-guard-test2单元4项、candidate-guard-test3数据库2项；guard3-review2独立验证旧快照并发及取消后锁保持 | 手动首版公开受理已接锁；确认与编辑竞争仍待专项验证 |
| 预览确认凭据 | ingestion-proof-test2及proof-review2验证主体、范围、风险、修订、尝试和忙状态；早期仅发放受阻凭据，首版已接可受理凭据 | 普通兼容纯论文增量现已开放确认，非增量重建与零新增入口仍受限 |
| 确认事务内部原语 | ingestion-accept-test3通过3项，accept-review与accept3-review验证跨主体、取消竞争、真实head比较；同事务保存确认和内容锁 | 首版公开确认已接入既有命令幂等与构建 Worker，浏览器自动验证及首版人工验收通过 |
| 本地模型和构建存储 | 固定E5权重摘要校验、real-e5-inference1真实推理；build-store-test4隔离PG17/pgvector 4项及store4-review独立约束检查通过；vector-seal-test2和vector-review2核对空视图及延迟外键成员 | 首版读回与发布证明已接线，增量向量保留见下项 |
| 增量论文成员保留 | 确认核对已绑定版本清单、实际论文修订和版本 pin，冻结全部资产与修订配对；暂存重验 pin，拒绝遗漏、换配或未支持的输入 | 仅常规检索与纯论文基线，兼容向量、图谱及发布见下项 |
| 增量向量成员 | test_incremental_vector_members 从真正发布的首版启动第二次检索，在内部受理后核验新旧向量成员并集、重放无模型调用、历史视图及默认指针；配置改变、撤权和保留文本丢失均拒绝 | 兼容配置且有新增论文的常规增量分支已工程收口；依赖或配置变化后的重算及 no_change 另验，兼容增量发布见下项 |
| 增量图谱成员 | test_incremental_graph_members 通过实际首版和第二次检索验证共同实体归并、各论文独立支持、零新增语义断言、历史成员逐行守恒及重放；旧标题单独撤权、不一致的证明、迟到 claim 均阻止写入 | 有新增且完整保留基线的内部视图工程收口。兼容增量发布见下项；删除/替换、rebuild 另行跟踪 |
| 零新增预览 | test_preview_is_bound_to_candidates_sources_and_pins、test_baseline_match_blocks_processing_and_allows_explicit_correction 及浏览器 test_pab01 验证多个来源记录命中一个资产、歧义/人工修正、来源拒绝、结果不完整和旧记录无分页证据。检查 Run、指针、槽和事件无预览副作用 | 预览本身保持只读；全匹配场景的人工确认与成功决定见下项 |
| S28–S30 有结果且筛选全部排除 | test_excluded_preview_requires_current_verdict_for_each_new_group、test_no_change_completion[excluded/model_excluded] 及 test_pab01 覆盖混合匹配、模型重复组、人工理由、失效与冲突、重签确认和基线事务；保留原版本、事件、索引/图谱、重放及槽释放断言 | 当前子范围待人工验收 |
| S28–S30 所有来源完整返回零条 | 四种来源适配器的正常零条、矛盾分页与部分响应；test_zero_retrieval_requires_complete_frozen_sources 覆盖来源未完成、日期排除、旧证明及错误计数；首次无基线和错误供应商计数走原等待/失败；test_no_change_completion[zero] 及 test_pab01 经确认和基线核验后检查原子收尾、重放、默认版本及无发布事件 | 已验证，零条子范围已获人工接受 |
| S28–S30 全部检索候选命中基线 | test_no_change_completion、浏览器 test_pab01 验证两次确认、冻结范围、时限及归属、完整图文与向量读回、读回后撤权/文件替换、取消先后顺序、失败回滚、重复执行、后续新版本及归档后查证 | 本全匹配子范围已获人工接受 |
| 增量论文公开发布 | test_incremental_publication 及浏览器 test_pab01 验证普通命令重放、完整清单/对象/视图、保留全文 PDF、同版读取、事务故障回滚、默认指针竞争、准备后撤权、凭据替换和证明篡改 | 受控模型、隔离库及浏览器通过；本子范围获用户限定接受 |
| PUB-G02 首版构建配置 | 向量构建器取得写资格后、首次分块前持久化配置；封存时比对，重放时核对配置及摘要。见[profile2](../docs/workorders/evidence/task049_ingestion_2026-10-31/profile2/)的六项隔离回归，含配置字段、摘要与成功重放 | 首次分块从独立事务读回冻结配置；模型派发前或封存前改变配置、执行状态或尝试归属均拒绝，Run 和槽位保留。见第5节 vector-fence。增量基线仍开放 |
| 图谱抽取和文件存储基础 | graph-provider-test2 24项；provider-review2复验终态缺失反例；filestore-test2 3项与file-review2复验FIFO | 首版内部图谱和文件暂存已接线并局部验证；首版保护转换及发布已验证，显式清理仍开放 |
| FR-026确认、锁定、隔离写入、向量/图谱、发布与故障并发 | 按01 FR-026、02-02 §10、06 A09、07 §5–6逐项落实，含实际持久化及竞争 | 首版和兼容纯论文增量发布已自动验证；增量子范围已获接受，全任务仍未完成 |

### 剩余手动论文切片

| 用户操作及边界 | 执行用例 |
| --- | --- |
| 显式按变更的配置/来源依赖重建。等价输入核验旧版，真实变化发布完整新版，撤权或文件损坏保留原版 | test_rebuild_publication、test_no_change_completion、test_browser_analysis |
| 单条、批量、全部移除，确认绑定基线、目标修订和冲突运行。纯移除无需模型，清空发布可读空版，旧版和历史分析保留 | test_association_removal、test_browser_analysis |
| 失败构建默认保留，可确认放弃后回收。取消及成功构建异步回收可释放对象。复核归属、共享引用和在途保护，删除失败可重试 | test_run_temporary_cleanup、test_browser_analysis |

### PUB-G04 手动失败记录与清理边界

| 用户结果与写入所有者 | 前置、验收和交接 |
| --- | --- |
| 重新运行。Run 启动入口消费失败记录与预期修订，按当前权限、配置创建关联的新 Run，获槽时冻结新基线。原诊断和人工稿保留 | 11月1日 rerun3 的隔离库与浏览器共21项，含跨Project拒绝、配置失效、修订冲突及同键并发。浏览器用例 test_failed_run_can_start_a_separate_run。P1 原 Run 续连另行跟踪 |
| 显式清理临时数据。生命周期所有者消费手动清理请求，核验归属和依赖，关闭续连资格并记录结果 | 默认持续保留；清理后 Run 仍为 failed，独立待纳入修订、共享对象、已发布版和诊断保留。本轮已补请求契约、重复操作、并发 pin/回收和删除失败重试。隔离数据库证据见 remaining-cleanup；更长周期的历史留存政策归 TRACK-011b/018 |
| 删除历史记录。历史记录所有者处理明确删除请求，已发布版本和必要来源依据继续可读 | 与清理临时数据分别验收。须补精确入口、鉴权、引用保护及失败回滚测试；未经授权不执行删除。生产备份周期、容量与恢复目标仍归 H03 |

## 5. 验证与限制

本轮从状态概览、设计权威性和 task049 entry 启动，按 DELIVERY_TOOLS §5 读取 02-02 §3.3、07 §5.3 和实施入口。各阶段实际命令、退出码、JUnit 或完整日志及 delivery_summary 见[整体验证](../docs/workorders/evidence/task049_ingestion_2026-11-02/remaining/)、[重建](../docs/workorders/evidence/task049_ingestion_2026-11-02/remaining-rebuild/)、[移除](../docs/workorders/evidence/task049_ingestion_2026-11-02/remaining-remove/)和[回收](../docs/workorders/evidence/task049_ingestion_2026-11-02/remaining-cleanup/)。每个目录的 ledger 为独立定向读取记录。浏览器专项 browser2 由界面启动显式重建、确认等价结果，明确清理失败 Run、查询清理结果，再确认移除全部论文、读取空版及旧版人工分析。

S3 独立反例定位到等价重建未复核模型服务身份、移除会打开待排除的失效来源、旧分块上的孤立向量和写盘后登记回滚。修复后分别在 remaining-rebuild/removal-agent-review/fixed.json、remaining-remove/rebuild-review/review.json、remaining-cleanup/rebuild-review/review.json 复核；清理探针还在文件已删除后注入真实 SQL 错误，确认诊断及重试生效。S4–S5 补保留成员检查、冻结依赖与双向 pin 竞争，移除 Worker 可在未配置本地 E5 时独立工作。S6–S7 使用隔离 PG17/pgvector、受控供应商及模型。remaining/affected 133/133、final 46/46、最后带真实浏览器和移除专项的 browser-final 11/11，测试实例均已移除；unit1 后端单元 559/559；前端构建、4 项测试通过。各批次有重叠。完整后端静态检查发现既有 knowledge_build_tables.py 的两条 E501；本次改动文件 Ruff 及全后端 mypy 通过。1.24 契约增加清理和移除响应、revision_only 快照和清理终态。严格按旧枚举和封闭响应校验的客户端需同步，保守兼容门标出的两处操作和两处 schema 见 remaining/compatibility。全局工具测试 118 项中 117 项通过；旧 A04 的 ER08 对 ModelOption 上下文窗口字段的断言在本轮入场前契约同样失败，见 remaining/legacy-contract。本轮未改该字段。


[全部排除执行记录](../docs/workorders/evidence/task049_ingestion_2026-11-02/excluded/)包含 baseline、candidate4 及最终差异。S1 实际执行状态与权威性 read、task049 entry，按 excluded context 和 ledger 定向读 02-02 §10.4、工具 §5。S2–S5 复用既有筛选、确认签名与 no_change 事务。新增计数以去重论文组为单位。人工排除核对修改者与时戳；模型排除比对本次实际评分任务、组内全部论文来源和元数据、冻结配置、阈值、理由及结果。变更判断前的人工确认留存于 Run 历史。模型输入在组内只需校验一次，成员写入时戳可各自不同。

独立测试检出错误修改者、评分后摘要被替换仍可确认、丢失理由时入库预览返回内部错误，以及正常模型重复组误拒。相应入仓回归及独立探针均通过。首轮模型夹具重复确认已确认主题触发幂等冲突，修正夹具后通过。S6–S7 在 candidate4 上完成 142/142 项受影响集成测试（独立 PG17/pgvector，包含真实浏览器，已清理）、558/558 项后端单元测试、前端构建及 4 项测试、契约核验、Ruff 与 134 个后端源文件的 mypy。独立专项复验 7/7，另有独立浏览器复验 1/1 及契约方向性检查，见 review/review.md。JUnit 与普通日志均按真实退出码运行 delivery_summary，命令见 final、unit-final、frontend、contract、static-final。对照 38b4d73 的兼容检查标记 RetrievalRunView，1.22 仅在存在排除时新增 excluded_paper_count；严格拒绝未知响应字段的旧客户端需要升级。本次使用受控供应商与模型，不涉及真实模型质量、显式移除或重建。

[零条执行记录](../docs/workorders/evidence/task049_ingestion_2026-11-02/zero-retrieval/)与全匹配提交包分列。S1 实际执行 delivery_context 状态与设计权威性 read、task049 entry、02-02 §10.4 和工具 §5 定向 read（zero context、ledger.json），以 240034e 后工作区 baseline 开始。S2–S5 复用原有两次确认、冻结范围摘要及既有版本事务，不产生候选论文。独立探针复现空页仍有下一页/来源标记 partialResults 却签发完成证明；修复适配器，严格证明版本随本轮检索持久化，不追认旧零条。独立复验供应商测试及探针 25/25，隔离数据库 3/3。首轮反例直接写入数据库的布尔跳过数量触发公开响应 schema 拒绝；现在 worker 在写入前拒绝错误计数，并从正常入口验证失败收尾。

S6–S7 全部后端单元 558/558，受影响 PostgreSQL 17/pgvector 集成 96/96，含真实浏览器；验证后实例已移除。最终类型注解与单测字节串整理后专项 4/4，Ruff、mypy、前端构建与 4 项前端测试、契约检查通过。实际退出码及 delivery_summary 的 JUnit 或普通日志摘要见 final、verified-focused、unit-verified、frontend、static-final、contract2 和 review。兼容性对照标记 RetrievalRunView；实际仅两项预览计数的下限从 1 调到 0，严格校验旧响应的客户端需要 API 1.21。供应商及模型使用受控输入。该轮工程收口后零条实现已获接受并提交；后续筛选排除见本页最新检查点。

[全匹配 no_change 执行证据](../docs/workorders/evidence/task049_ingestion_2026-11-02/no-change-completion/)记录完整工作区、baseline 与 candidate2/candidate3 快照。S1 执行状态/权威性 read、task049 entry，使用 nc-completion / ledger 定向读取授权、02-02 §10.4、06 A09.6 及工具 §5。S2 沿用已有确认命令，首阶段签名绑定实际范围，第二阶段记录人工决定与候选快照。就绪时读回永久 pin、正文/PDF、分块定位、注册 profile、向量和图谱，短事务重验权限、head、claim、attempt/租约、人工依据、文件身份与证明摘要。S3 独立测试复现旧实现准备后确认快照被换仍成功、已归档可读项目重放被写权限阻断，修复后四项隔离 PG 独立复测通过，见 review/final-summary.json。S4 覆盖失败、过时基线、准备后文件同尺寸改写、确认/证明失配、坏计数、取消、迟到执行者、原子回滚及重放。S5 复用既有发布校验，提交阶段核对文件身份和时间戳，避免重复加载全文。

S6 的 final/run.json 与 JUnit（candidate2）记录 110 项受影响集成回归通过；candidate3 仅调整导入顺序，final-focused 对其重跑 12 项 no_change 用例通过。两轮均使用隔离 PG17/pgvector，库已停止移除；所有 JUnit 均按真实退出码运行 delivery_summary。unit-final 的 548 项后端单元、前端构建及 4 项测试、static4 的 Ruff/134 个后端源文件 mypy、契约检查均通过。guard 记录了缺少 SQL 选择列导致的四个失败；browser-test 读取旧构建未找到核验结果区。修复并构建后的真实浏览器在 final 通过。对照本轮入场基线，保守兼容检查指出 RetrievalRunView 枚举扩展；严格校验响应的客户端需要契约 1.20。S7 结论仅覆盖上述全匹配场景，使用受控模型，未测大库吞吐。本轮没有新的 Git 提交。

[零新增预览的执行证据](../docs/workorders/evidence/task049_ingestion_2026-11-02/no-change-preview/)以 `2795d91` 为新 S1，沿用已读启动状态、设计权威性，并执行 task049 entry 和新上下文 nochange-nov2 的 DELIVERY_TOOLS §5、06 A09.6、02-02 §10.4 定向读取。S2 根据冻结检索词和来源配置逐项比对分页完成证据、来源结果及原始候选，再核对去重组、真实基线 pin 和修订。S3 独立审查复现提前空页错误；page-red 的失败用例及独立 probe 保存原行为。分页器遇总数漂移、提前空页、超限或相同来源记录重复不出具穷尽证据；没有稳定标识的条目保持可用，旧 Run 不补写证据。S4 用真实适配器、受控 HTTP 与隔离 PG 对照完整页和提前空页，两例独立复测通过。S5 详情可选字段驱动 UI，读取不修改候选、执行资格或版本状态。一次测试的 rejected 来源缺少契约必填字段，source-proof 记录该失败，已补正确夹具。S6 最终 candidate3 的 final2/run.json 及对应 JUnit 运行 delivery_summary，63 项受影响集成回归通过，unit-final 的 548 项后端单元通过，无跳过；前端构建及 4 项测试、static3 的 Ruff/mypy 和契约检查通过。对照 2795d91 的兼容检查返回 1，contract-scope 单独核对仅 RetrievalRunView 增加可选投影。使用旧版严格响应 schema 的客户端需升级到 1.19 才可接受含该字段的详情。S7 仅完成只读预览；本阶段未提交。

[手动增量发布执行证据](../docs/workorders/evidence/task049_ingestion_2026-11-02/incremental-publication/)含入场工作树、baseline / candidate3、完整日志和实际退出码。S1 执行状态/权威性 read、task049 entry；publication-Nov2 独立 ledger 记录授权、06 A09.6、DELIVERY_TOOLS §5 的定向读取。S2 覆盖真实首版与第二次检索，复用现有确认与查看入口；完整论文/文本/文件读回后，Worker 携带预期证明摘要进入提交事务。S3 独立探针在早期实现复现过期发布凭据仍能设 head、被改写的视图 ID 能进入事件。修复提交和构建失败路径的执行凭据校验，证明重放绑定已发布记录。S4 补入 PDF 丢失、计数与本地摘要一起被改写、模型在途失败和真实 head 竞争。review/final3-summary.json 的四项独立 PG 复验通过。S5 复用相同来源许可检查，提交事务只比较元数据和保护引用，不重读文件字节。

S6 在启用 pgvector 的临时 PostgreSQL 17 上运行 final2/run.json 的命令，使用受控模型。对 final2/tests.xml 执行 delivery_summary，共 97 项通过、无跳过；库已停止移除。backend 目录运行 `.venv/bin/python -m pytest tests/unit -q --junitxml=…`，unit/summary.json 记录 542 项通过。frontend 构建、4 项 Vitest、API 契约静态检查及 static2 的 Ruff/132 源文件 mypy 均通过。早期 static 与 final-static 的类型、行宽失败已保留。本轮未评估真实模型质量或发送发布邮件。S7 工程收口；人工验收材料见[增量预览](../docs/workorders/evidence/task049_ingestion_2026-11-02/incremental-publication/browser-final/preview.png)、[新版本](../docs/workorders/evidence/task049_ingestion_2026-11-02/incremental-publication/browser-final/incremental.png)和[原版本](../docs/workorders/evidence/task049_ingestion_2026-11-02/incremental-publication/browser-final/original.png)。

增量图谱的[执行证据](../docs/workorders/evidence/task049_ingestion_2026-11-02/incremental-graph/)保留初始工作树、baseline / candidate4 快照及最终 JUnit 和退出码。S1 用状态/设计索引 read、task049 entry、context graph-Nov2 的独立 ledger 读取任务授权、06 A09.6 和 DELIVERY_TOOLS §5。S2 用受控抽取器与真实隔离 PG17/pgvector 构建两次 Run。S3 独立审查要求额外核对发布证明的依赖摘要、候选修订及四类图谱计数；review 的独立事务探针复验替换执行凭据后旧结果不能写图或释放槽。S4 检查元数据来源与正文来源分离时的撤权、空抽取、重放及旧版不变。S5 模型派发仅重验基线元数据、来源及当前权限，完整文件/视图读回留在开始和封存事务。final2/final3 的故障注入触发器跨测试污染，已替换为本例 engine listener 并在 finally 移除。S6 最终执行 final4/run.json 中的隔离命令，对 JUnit 运行 delivery_summary，38 项通过，无跳过，隔离库已移除；static6 的 Ruff 与后端 mypy 通过。S7 结论仅覆盖本内部切片；本轮使用模拟模型，未测真实抽取质量或大图性能。

增量向量的[本轮证据](../docs/workorders/evidence/task049_ingestion_2026-11-02/incremental-vector/)记录实际源码快照、退出码、日志与摘要。S1 执行状态/权威性 read、task049 entry，再以 ledger.json / vector-Nov2 读取授权、06 A09.6 及 DELIVERY_TOOLS §5。S2 在隔离 PG17/pgvector 内发布首版、运行第二次检索，使用受控嵌入与图谱服务。前两次测试夹具分别命中检索节流和命令键复用，修复隔离夹具后 slice3 正常运行。S3 独立审查发现必须先重验旧来源再读文本及向量；修复过程 candidate / affected 因残留旧变量出现四例失败。S4 增加撤权后读取监测、文件丢失反例；S5 复用原有封存校验和同事务成员写入，模型派发仅重验当前权限及输入，不逐片重新扫描旧向量。S6 对 candidate2 的 final/tests.xml 实际执行 delivery_summary，32 项通过、无跳过，隔离库已移除。static2 的 Ruff 与后端 mypy 通过。review/fix-summary.json 记录独立探针在撤权后零次读取旧文本。本切片仅封存候选向量视图，使用受控模型，未进入增量发布或人工验收。

增量保留清单的[执行证据](../docs/workorders/evidence/task049_ingestion_2026-11-02/incremental-baseline/)含完整入场状态、baseline / candidate3 快照、实际命令、退出码及摘要。执行状态与设计索引 read、task049 entry，再用 context increment-Nov2 定向读取授权、06 A09.6 及 DELIVERY_TOOLS §5，见 ledger.json。red 复现错误接受缺失成员的缓存；digest-red 复现清单自带摘要矛盾时仍通过检索确认。S3 独立审查补入非论文资料、未支持输入与旧首版兼容场景；review/ 的隔离探针验证交换配对被拒绝和新旧摘要格式共存。S4 核对确认前后写入、旧版指针和 pin，S5 暂存按项目/版本只读取 pin 指向的两列身份。S6 的 final3/run.json 使用隔离 PG17/pgvector、模拟服务，JUnit 执行 delivery_summary，28 项通过、无跳过，数据库已移除。final2 的 1 项失败定位到原契约漏列 410；本轮补齐阶段确认和论文列表两处，api-contract3 检查通过。api-compat 的保守比较退出 1，compatibility-scope 已单独核对操作与共享契约的差异仅为这两处新增 410 响应。Ruff 和后端 mypy 通过。S7 仅收口内部成员保留切片；首版接受不延伸到增量或 no_change。

PUB-G02 冻结配置专项。按 `delivery_context.py entry tasks/049-ingestion-publication.md` 恢复，定向读取授权、DELIVERY_TOOLS §5 及 06 A09.6（context cont-one）。[本轮证据](../docs/workorders/evidence/task049_ingestion_2026-11-02/vector-fence/)保留 ledger、入场与 candidate3 快照。旧实现 red3 四例中三例错误封存；red/red2 因本机 PostgreSQL 缺少 vector 扩展未进入测试。改用现有隔离 PG17/pgvector，按 final3/run.json 的命令及 PYTEST_ADDOPTS 执行，再对 JUnit 运行 `delivery_summary.py --exit-code 0`，20 项通过、无跳过，数据库已移除。模型受控。独立审查发现外层 Worker 会把过期结果记作 Run 失败；修复后以独立的 unknown 状态交错在修复前后分别得到失败和通过，详见 review。S4 核对正常封存、重放、真实失败及迟到写入的禁止副作用，S5 复用同一冻结凭据比较；static3 的 Ruff 与全后端 mypy 通过。

执行说明第5节通过delivery_context实际读取，记录见root-ledger；完整命令、退出码及delivery_summary结果在[evidence](../docs/workorders/evidence/task049_ingestion_2026-10-30/)：preview-test1通过1项；preview-test2因确认对象机器契约不匹配失败并保留，补契约后preview-test3/4通过；前一快照regression1隔离PG/浏览器116项通过；preview-finalcandidate-snapshot上focused1为2项通过、0跳过，build2和lint3退出0。contract1及contract-tests1使用backend环境缺少openapi_spec_validator失败；contract-tests2误用契约环境的pytest未安装而未生成JUnit；contract2在正确环境发现覆盖清单未同步而失败。同步后contract3通过（87个部分操作、28个仅请求；未做旧版兼容比较），contract-tests3的48项unittest通过。独立S3发现确认投影、失败漏报和契约/覆盖问题；复审再发现过期筛选及来源错误遗漏；修复后独立复审限定通过，独立ledger和反例日志保存在evidence；清单补充后的受影响复审通过（reviewer-contract-ledger）。上述只证明预览切片，未完成本任务完整S3/S4/S6。真实模型和pgvector隔离烟测已通过，完整构建和发布未验证。

回归中的原有浏览器测试覆盖了入场时已存在且未跟踪的`docs/workorders/evidence/task048_next_stage_2026-10-30/analysis-mobile.png`；原始字节未纳入源码快照，无法证明可恢复。已改用pytest临时目录以防后续再次覆盖，不能将新截图冒充原验收证据。

本轮恢复context为`task049-cont-20261030`，原文读取保存在continuation-ledger。旧contract-final-snapshot仅状态与任务记录两处漂移（/tmp/rpb49-cont-drift.json）；独立初查ledger为publication-review-ledger。分块S3发现段落换行被忽略，chunking-test2修复复验4项通过，chunk-paragraph-review2、chunk-probe-review2及chunk-review2-ledger记录独立复审。slot-test1日志、JUnit和实际退出码保存在同名evidence。隔离真实依赖准备中：Docker拉取pgvector镜像因registry EOF失败；尝试临时PostgreSQL源码与独立E5运行环境，不安装到业务数据库；不能将这些准备视为已验证或业务交付。

本轮后续采用临时源码编译PG17和pgvector 0.8.1，测试数据库由隔离fixture创建清理；E5权重下载和固定摘要检查见e5-download1，真实CPU推理见real-e5-inference1。slot-regression3、version-test1、build-store-test4、embedding-test6、graph-provider-test2、filestore-test2、vector-seal-test2及current-unit2均保留完整日志、退出码和实际delivery_summary调用结果；对应独立反例/复审见slotlease-review-probes、version-review-*、store4-review、provider-initial-review、provider-review2、file-review2和vector-review2。独立审查发现图抽取缺失完成状态误接受，以及向量封存遗漏延迟外键成员，均已修复并复验；封存原语不构成完整发布证明。这些是局部验证，不代替S3总体审查或端到端验收。current-storage1因发现旧浏览器用例会写入历史截图而中断（退出130；检查未发现本次截图写入）；临时数据库服务已停止。后续需隔离浏览器证据输出并重跑，不能将中断日志中的失败或未运行用例判为通过。

后续browser-isolation-snapshot解压到独立副本，构建browser-copy-build成功，browser-copy-test1浏览器回归89项通过，截图只写该副本。current-storage2为修复前的非浏览器诊断运行，进行中即发现旧测试固定迁移头0015；已保留明确降级目标并更新当前head断言到0018，migration-assertions-test1的19项通过，独立复核未发现弱化。current-unit3 511项通过。独立审查发现候选锁不应依赖仍有效的确认，且回退阶段确认和后台任务须检查该锁；candidate-guard3-snapshot分离锁定事实、加后台防护和持久化单向检查，真实并发复验见guard3-review2。未来受理事务仍须原子设置该锁与确认并重读槽及Run。e5-review独立运行真实worker并验证向量、Unicode定位与输入拒绝；该测试不代替完整构建。其他进行中的回归必须以实际完成报告为准。

current-storage2最终660项中12项失败：10项旧head断言、1项Project创建旧表断言和1项demo隔离库缺pgvector。已修正并以migration-assertions-test1、regression-fixes-test1及独立复核验证受影响行为；regression-full1在独立源码副本进行，不代表后续代码自动覆盖。预览令牌新增完整候选和预览绑定，proof-review2发现评分进行中遗漏，已补阻断并独立复验。E5本地进程客户端在real-e5-client1通过真实模型分块/向量烟测，embedding-client-test3验证模拟协议与错误；独立审查发现缺失程序及极大向量数字错误映射，已修复，客户端仍未接入受控构建，审查和完整验证进行中。

regression-full1的副本错误地复用原工作区虚拟环境符号链接，其嵌套demo调用uv将可编辑安装指向副本；analysis-lineage-test1因加载旧副本而失败，不能作为当前源码证据。已执行`uv sync --locked --directory backend`恢复原可编辑安装，并验证导入路径；后续测试显式设置当前源码PYTHONPATH，未来副本须使用独立虚拟环境。regression-full1自身显式指向副本PYTHONPATH，其源码基线及局限单独记录。分析修订新增私有来源记录，真实事务复验及完整来源门禁仍待完成；未知来源不能推定已验证。

regression-full1最终750项通过，属于regression-full-snapshot而非后续新代码。分析溯源的实际缺口由analysis-origin复现；analysis-lineage-test5及lineage6-review验证生成任务和人工继承、来源全集、分类/政策审计及畸形记录拒绝，该门禁尚未与完整构建接线，首次人工填稿的可信来源登记仍待实现。内部受理原语在ingestion-accept-test3及accept3-review验证真实head和写槽，空选集只允许已有真实基线继续检查，不视为no_change。向量IPC的短授权交接与异常竞争在embedding-client-test4及client-race2复验，real-e5-client2通过真实推理；图谱封存在graph-seal-test1及graphseal-review完成限定检查。graph-seal-test1的摘要包装器因字段拼写错误退出1，已保留错误，实际pytest退出0且随后对其JUnit执行delivery_summary；上述局部结果均不能代替最终端到端审查。

论文身份和Project私有修订处于隔离存储实现中。paperstore-review复现了仅用JSON清单无法保护修订删除；paper-store6-snapshot改为版本草稿同事务插入pin并封存、禁止未封存提交及设head，paper-store-test6的5项和paperseal-review/base限定复验通过。xmin方案子事务失败反例保存在paperpin-xmin；它已替换，不可将旧方案报告为通过。尚须发布事务核对清单与pin全集、当前授权和所有其他对象保护。独立设计核查确认既有Project论文应在下载、解析和分析前匹配并排除，且人工误合并修正优先；原实现只覆盖同一Run，已开始补基线成员匹配，跨Run决定持久化仍未完成。

基线成员已按固定Project版本和受保护修订读取并接入检索确认后的去重；baseline-dedup-test2隔离数据库7项通过，dedup-review5复验人工拆分与审计继承，baseline-affected1因执行中源码漂移出现1项失败，不能作为最终基线。paper-stage-test3的4项验证确认后的隔离论文暂存、原attempt/取消后拒绝和重复调用；paperstage-review2/4复验未发布身份不影响其他Project、旧attempt/过期租约及跨主体/Project拒绝。暂存内容仍引用Run所有的文本/文件，必须复制成Project不可变对象并保护后才能发布。最终发布须在全局身份裁决锁下重验并发暂存和清单引用。2026-10-30用户澄清：其他Project同标题人工区分不应提示或阻断当前Project的新候选；当前Project正常去重并新增关联。已回写01及02-03，暂存引入Project专属未决身份，不宣称与其他身份相同或不同；已核对02-02 §3.3：移除后必须明确确认重新纳入，当前缺少该命令及证明，因此普通检索命中当前Project历史身份时暂拒绝，完整重导后沿用身份的流程仍待接入。identity-decision1因测试夹具未限定本Project计数失败，identity-decision2的7项通过但其中重导场景缺少确认，不代表完整规则；发布时并发全局裁决及完整独立审查仍待完成。

内部向量构建接入固定E5及隔离pgvector，向量重放、并发claim、策略撤销、失败/租约处理分别见vector-builder-test7、vectorpolicy-review3、vectorlease-review2及vectorcancel-review；对象复制、完整性与定位局部结果见object-stage-test3及object-locators-test1，但目前缺少与物理回收互斥的持久依赖保护，不能据此发布。图谱构建与封存、成功/空结果/失败、重放及双来源元数据依赖的当前快照为graph-builder3-snapshot，graph-builder3隔离PostgreSQL 7项通过，graph-affected1受影响回归87项通过；real-graph-builder1以真实本地E5和模拟图谱服务通过1项。独立审查复现图谱抽取向外发送不属于正文依赖的元数据，以及标题标签漏记原始来源；现已移除外发元数据并单独绑定标题/作者来源、分类及政策，独立复验graph-meta-review2和graph-revoke-review均为2项通过，后者验证撤销元数据来源后重放在再次调用模型前拒绝。图构建领取前失败尚须由执行器落终态；首次人工填写分析缺少可信来源登记，确认前元数据人工编辑的既有需求及其可信新来源/修订、分类和下游失效尚未实现（独立审查指出现有候选PATCH仅支持筛选/分析），增量基线构建、发布前全量依赖/清单检查、回收互斥、原子发布、前端接线、完整要求测试和总体独立审查均未完成。上述测试为局部证据，不能代表里程碑验收。

本轮阅读delivery_context的执行步骤及设计原文见continuation-ledger、context `task049-userdecision-20261030`；identity-decision2-snapshot记录此次测试完整源码，隔离PG/pgvector、完整日志、退出码和delivery_summary报告在identity-decision2；随后identity-decision3-snapshot修正未经确认的历史恢复，identity-decision3受影响回归53项通过。独立审查发现当前Run的distinct决定不能代替历史重导确认，identity-decision4-snapshot补充该门禁和真实数据库反例，identity-decision4受影响回归53项通过，identity-review-final2独立复验3项通过；发布并发身份裁决不在其覆盖范围。identity-doccheck1的diff空白检查退出0。

对象依赖保护进行中：object-protection1首次53项中1项因新增表未更新schema清单而失败，修正后object-protection2隔离PG回归53项通过；独立object-review1以两事务、pg_blocking_pids确认取得在途pin与标记回收的双向互斥；object-review-version1验证版本pin与回收竞争，object-review-cascade1限定验证项目级联与取消重放。独立审查指出pin不能单独作为资格证明，随后object-protection3-snapshot禁止直接更新/删除pin并新增回归，object-protection3 53项通过，object-pin-guard-review1独立验证直接更新/删除拒绝及Project级联，1项通过；随后object-protection4-snapshot在向量/图谱读取时锁生命周期并检查Project、Run、attempt及slot epoch的在途pin；object-protection4隔离PG回归53项通过；独立审查指出等待生命周期锁及文件读取期间租约可能到期，object-protection6-snapshot补锁后、读取后及提交前时间检查，含读取跨到期不落对象/pin的回归，object-protection6隔离PG 55项通过，object-lease-review3及object-lease-slow-review1各1项独立复验通过；独立审查随后发现回收状态检查前可能读取已有文件，object-protection7-snapshot调整为生命周期锁内安装及读取，object-protection7隔离PG 55项通过，object-reclaim-review1独立验证已标记回收时拒绝且不读取/写入文件；当前源码级联和锁顺序独立复核进行中。本地文件写入和fsync期间持有治理/Project/Run锁，需在完整清理与延迟故障审查中进一步评估。受控释放仍待实现。新增在途保护不等于完整生命周期：取消/失效释放、CleanupJob、外部幂等删除、正式版本保护转换和发布就绪重验仍未实现；不得据此开放发布。

图谱输入闭包推进：chunk-closure1-snapshot新增正文范围连续覆盖、Unicode片段摘要、文本修订/依赖和页码定位检查，chunk-closure-unit1的7项、chunk-closure-pg1的9项通过；独立审查指出须检查整篇论文缺少全部分块，chunk-closure2-snapshot加全部确认资产集合校验及空白正文拒绝，chunk-closure-pg2的9项通过，整篇缺失在chunk-asset-review1独立PG故障注入中拒绝，real-chunk-closure1真实E5复验1项通过；chunk-closure3-snapshot增加chunker修订绑定，chunk-closure-unit2 8项及chunk-closure-pg3 9项通过。独立审查指出此闭包不独立重算token上限和重叠，仍须就绪证明绑定profile并验证；此检查不是完整就绪证明。

2026-10-31 恢复后用 delivery_context entry 定位本任务并读取 DELIVERY_TOOLS §5（context task049-1031-a）。构建与重放共用同一 BuildProfile 生成函数，绑定嵌入、分块、抽取 schema、提示词、冻结配置摘要、图谱规则和词法修订。隔离 PostgreSQL/pgvector 的 profile1 六项通过，完整快照、日志、真实退出码和 delivery_summary 结果见 [profile1](../docs/workorders/evidence/task049_ingestion_2026-10-31/profile1/)。此切片不构成发布就绪证明。H03 的失败中间产物超时清理期限已询问用户，显式放弃与其他发布工程可独立推进。
独立审查发现原先在嵌入完成后才生成 BuildProfile。已改为在进程提供嵌入配置后、首次分块前持写资格保存完整配置及摘要，提交时重新比对。修正后的 [profile2](../docs/workorders/evidence/task049_ingestion_2026-10-31/profile2/) 隔离回归六项通过。词法修订仅标识规则，完整就绪证明及发布仍待实现。

2026-11-01 重新运行验证按 DELIVERY_TOOLS §5 执行。rerun3 固定快照运行隔离 PostgreSQL 与浏览器测试 21 项通过，包括跨 Project 拒绝、失效配置、修订冲突、并发同键只建立一次及原失败详情保持。前端构建、类型及同步规范指纹后的契约检查通过。独立设计与代码审查确认进入现有启动鉴权、Project 锁、幂等与获槽冻结路径。证据见 [rerun3](../docs/workorders/evidence/task049_ingestion_2026-11-01/rerun3/summary.json)。

图谱来源读回按 06 A09.6 及 DELIVERY_TOOLS §5 定向读取（nov1-graph-read），使用 graph-source3/snapshot 与隔离 PostgreSQL/pgvector。执行 -k “test_pgvector_scoped_members_and_sealed_views or test_internal_confirmation_atomically_freezes_candidate_without_publishing”，7 项通过，实际退出码 0，已对 JUnit 执行 delivery_summary。[本次证据](../docs/workorders/evidence/task049_ingestion_2026-11-01/graph-source3/summary.json)。独立代码复核确认当前构建调用方读取受保护正文，并在封存与重放核对摘要、范围、标签及元数据来源。审查者未独立重跑此快照。关系语义核查、全量就绪和发布级当前授权仍需分别验证。

首版端到端及审查（2026-11-01）：按 delivery_context 读取执行工具 §5，context firstpub-nov1。固定快照、完整日志、退出码与 delivery_summary 存在 [本轮证据](../docs/workorders/evidence/task049_ingestion_2026-11-01/)。first-publication1 首次浏览器成功后独立审查发现暂存身份竞争、响应契约和领取失联诊断缺口。first-publication3/4 的失败包含过时成功态枚举、结束时间格式和测试变量，first-publication6/7 的失败分别涉及元数据表清单和跨 Project 测试创建请求，均保留日志。最终路径补齐受保护文件及图谱/向量存储读回、固定 tokenizer 重新切分、准备后撤权拒绝、提交失败回滚、版本决定重放、过期执行者结果未知且保槽、永久视图引用和同版分页。first-publication8 使用真实本地 E5 与受控图谱，reviewer-browser-independent8 独立执行模拟嵌入端到端，对同版人工稿、跨 Project 读取拒绝和发布后取消拒绝均通过。独立隔离库重跑回滚/重放及发布引用保护见 publication-review-independent。发布事件投递本身、生产运行及完整图谱质量不在这个子验收点。

最终受影响回归 first-publication-final 的 72 项全部通过，129 个后端源文件 mypy 检查通过。相关前序快照后端单元 542 项通过、契约套件修正允许操作后 56 项通过。首版请求的交付物已到人工验收点，未进行人工验收后的 Git 提交。

## 2026-11-02 首版发布子范围人工接受

用户明确接受浏览器确认、首版原子发布与同版本读取，并授权本地提交。接受基线为 first-publication-final，72 项受影响回归及上述独立复验有效。提交前业务源码与最终快照逐文件一致。增量构建、no_change、显式清理及整个 M-P0-18 的验收继续开放。

## 手动论文增量发布子范围人工接受（2026-11-02）

用户指令为“ok，验收通过，并进行一次git提交。然后继续推进”。接受基线为 incremental-publication/candidate3；97 项集成回归、542 项后端单元、4 项前端测试及 4 项独立探针沿用原执行证据。提交前从 a07f21d 检查空暂存区，逐文件比对业务产物，混合状态文件只选取本业务范围。实际核验见[提交记录](../docs/workorders/evidence/task049_ingestion_2026-11-02/accepted-increment/)。

全匹配提交核验使用 no-change-completion/candidate3 及最终测试和独立审查证据；本次只更新验收记录，沿用原业务验证。核验清单见 matched-acceptance/scope.json。

本次零条验收提交复用 zero-retrieval/verified、final、unit-verified 及独立复验证据。提交核对见 zero-acceptance/scope.json。
