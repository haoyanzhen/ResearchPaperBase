# Task049：M-P0-18 手动论文入库与知识版本发布

文档版本：v1.12
更新日期：2026-11-02

## 8. 最新检查点

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
| 预览确认凭据 | ingestion-proof-test2及proof-review2验证主体、范围、风险、修订、尝试和忙状态；早期仅发放受阻凭据，首版已接可受理凭据 | 首版公开命令已重验并保存；已有基线的确认保持受阻 |
| 确认事务内部原语 | ingestion-accept-test3通过3项，accept-review与accept3-review验证跨主体、取消竞争、真实head比较；同事务保存确认和内容锁 | 首版公开确认已接入既有命令幂等与构建 Worker，浏览器自动验证及首版人工验收通过 |
| 本地模型和构建存储 | 固定E5权重摘要校验、real-e5-inference1真实推理；build-store-test4隔离PG17/pgvector 4项及store4-review独立约束检查通过；vector-seal-test2和vector-review2核对空视图及延迟外键成员 | 首版读回与发布证明已接线，增量基线待实现 |
| PUB-G02 首版构建配置 | 向量构建器取得写资格后、首次分块前持久化配置；封存时比对，重放时核对配置及摘要。见[profile2](../docs/workorders/evidence/task049_ingestion_2026-10-31/profile2/)的六项隔离回归，含配置字段、摘要与成功重放 | 待补确定性交错：分块开始时从独立事务读回冻结配置；封存前篡改配置或撤销资格须拒绝且无可发布结果。首版就绪已用固定tokenizer重分块；增量基线和前述交错仍需专项证据；归PUB-G02，交PUB-G03消费 |
| 图谱抽取和文件存储基础 | graph-provider-test2 24项；provider-review2复验终态缺失反例；filestore-test2 3项与file-review2复验FIFO | 首版内部图谱和文件暂存已接线并局部验证；首版保护转换及发布已验证，显式清理仍开放 |
| FR-026确认、锁定、隔离写入、向量/图谱、发布与故障并发 | 按01 FR-026、02-02 §10、06 A09、07 §5–6逐项落实，含实际持久化及竞争 | 首版公开链路与原子发布已验证，增量及全任务验证未完成 |

### PUB-G04 手动失败记录与清理边界

| 用户结果与写入所有者 | 前置、验收和交接 |
| --- | --- |
| 重新运行。Run 启动入口消费失败记录与预期修订，按当前权限、配置创建关联的新 Run，获槽时冻结新基线。原诊断和人工稿保留 | 11月1日 rerun3 的隔离库与浏览器共21项，含跨Project拒绝、配置失效、修订冲突及同键并发。浏览器用例 test_failed_run_can_start_a_separate_run。P1 原 Run 续连另行跟踪 |
| 显式清理临时数据。生命周期所有者消费手动清理请求，核验归属和依赖，关闭续连资格并记录结果 | 默认持续保留；清理后 Run 仍为 failed，独立待纳入修订、共享对象、已发布版和诊断保留。须补请求契约、重复操作、并发 pin/回收、删除失败重试及隔离持久化证据。交 TRACK-011b/018 |
| 删除历史记录。历史记录所有者处理明确删除请求，已发布版本和必要来源依据继续可读 | 与清理临时数据分别验收。须补精确入口、鉴权、引用保护及失败回滚测试；未经授权不执行删除。生产备份周期、容量与恢复目标仍归 H03 |

## 5. 验证与限制

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
