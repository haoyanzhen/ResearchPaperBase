# Task046：筛选确认与论文解析入口

版本：v1.11
日期：2026-10-30

## 8. 最新检查点

2026-10-30最新裁决：M-P0-16验收时用户明确将Windows/Linux实测移至下一大阶段，当前L0不做；因此解除下述历史平台提交阻塞，缺口未记通过。见task047第12节及PROJECT_STATUS TRACK-023。

流程v1.11；context=task046-platform-20261029-2。用户2026-10-29明确选择D-CW-04 B：“系统先选：按固定顺序选首个可用全文，无全文则选真实摘要，展示来源后由用户确认”。该来源规则已关闭。M-P0-14已本地提交f5d5b19，未push；本片未提交。此前macOS限定基线完成S1–S7及独立审查；用户追加至少Windows/Linux支持和可选提取引擎后，当前S1补充选择语义已明确，S2新增实现与验证进行中，原收口不覆盖新增范围，M-P0-15于2026-10-30获用户明确接受；人工接受不改变未完成的平台实测事实，提交暂缓，见第13节。新增授权、已定语义及平台证据见第10/11节。

M-P0-15限定筛选确认→论文PDF获取/静态解析与真实摘要降级→结果来源/诊断/文件展示及处理确认。不包含AI分析/发布、全局成员、非论文资料、独立补充上传/replace-source；不宣称整个FR024完成。此前macOS收口时业务验证基线为verification10，其后当时仅有交付文档变化；本轮新增业务代码不属于该基线。此前handoff-final-v2快照和delivery-artifacts.json位于evidence；混合工作区其他任务改动保留，未纳入本片提交范围。

这里的verification10及handoff-final-v2是此前macOS限定基线；新增引擎接口与容器运行器已编写，真实平台验证尚未通过，不能引用旧证据宣布新增范围通过。

## 1. 授权与范围

授权顺序：M-P0-14接受核验及本地提交→DD-G06筛选确认与FR-024论文获取解析入口→至可验收里程碑或未明确设计。拟定M-P0-15包括真实PDF获取、文本处理、真实摘要降级、逐来源依据及处理确认；不扩大到全局身份、非论文资料或Knowledge Version发布。未把拟定范围称作已交付。

## 2. 依据与基线

- FR-022与D-CW-03只决定同标题论文身份，不保证不同来源正文一致；FR-024规定PDF优先、真实摘要降级和手动处理确认。
- 02-03第6节及06 A08.1–4要求最终唯一文本来源与不可变修订；04-01已有候选replace-source，04-02规定未发布文件授权读取。
- task042第9节曾由独立审查把来源选择视作工程细化；本轮独立报告也认为可透明提出确定选择再确认，主agent未将其误称用户已批准自动正文选择。
- 已执行AGENTS两条bootstrap、task044/task046 entry、outline与read。实际原文SHA/选择记录见[evidence/main-ledger](../docs/workorders/evidence/task046_processing_gate_2026-10-29/main-ledger.json)；最初/tmp ledger已转入任务目录。DELIVERY_TOOLS第5节于首个验证前读取。宽rg截断仅用于定位，重要条款随后定向读取；不存在路径/不准确section有明确失败并用outline纠正。

## 3. 修改落点

本轮仅修改task044接受记录及验收包、PROJECT_STATUS，新增本任务和证据。M-P0-14代码提交使用已验收产物，不代表本轮新写解析实现。工作区流程、每日整理及历史证据保留。

## 4. 需求与覆盖

场景来自FR024、02-03§6、06 A08、08/08-01及用户B；独立推导27项见[测试清单](../docs/workorders/evidence/task046_processing_gate_2026-10-29/review-test-plan.md)。下表为本片单点矩阵，PP为可执行test_pp前缀（unit/integration），PPB为真实浏览器，脚本PP31验证闭合契约。执行结果统一见第5节，不以表格存在或数量代替通过。

| 需求/独立场景 | 可观察结果及禁止副作用 | 可执行场景 |
| --- | --- | --- |
| TP01/02 筛选确认门禁 | 仅当前有效独立组；未判定/无效不下载；旧token及错误主体无写入 | PP10、14、16、17、30；既有PS筛选回归 |
| TP03/22 幂等与竞争 | 重放同确认返回原决定；异载荷拒绝；并发Worker只派发一次；组提交不重复创建对象 | PP10、13、20、25、30 |
| TP04–08 固定来源选择 | 冻结来源顺序；后续全文优先于早期摘要；全部全文失败后第一真实非空摘要；不融合 | PP03、04、10、18、30；source_attempts展示选择/失败/未尝试 |
| TP09 部分/全部失败 | 部分成功可确认；全部失败无分析入口，参与知识始终false | PP14、18、PP31 |
| TP10 真实提取与文件 | 真实PDF静态提取并持久化；双页中文/换行/字符范围；原PDF按归属下载 | PP01、11、23 |
| TP11/12 解析失败与限额 | 加密、损坏、无文本、不支持隔离如实诊断；50MiB/200k字符/墙钟/内存限制，无截断成功 | PP01、07、09、24、28；共用HTTP deadline LN03/04/06等 |
| TP13–15 安全边界 | 每跳公共IP校验并固定连接地址，内网零连接；不继承Provider内网名单或密钥；解析进程无网络/secret/其他文件读取 | PP02、05、06、08、28；共用HTTP LN02–06 |
| TP16 故障与未知提交 | 获取重试预算0；解析错误继续其他来源；持久失败回滚，不盲重发未知工作 | PP27、29；PP20受理回滚 |
| TP17 下载文件与摘要分离 | 安全保留的无文本PDF不冒充摘要text.document；独立文件归属及私有未确认分类 | PP21、11 |
| TP18/19 权限与迟到 | read/dispatch/commit复验当前账号/Project资格；取消、撤权及租约过期无迟到对象 | PP11、12、15、26；旧CR取消/权限回归 |
| TP20/21 活动互斥与失效 | 活动中编辑/去重/评分拒绝；完成后可改；仅受影响处理失效，失败重评分保留原确认 | PP10、16、18、19、30；PPB01 |
| TP23 确认冻结 | 受理后不重用短期token，Worker核对持久job/输入/候选/权限；修改候选使旧确认拒绝 | PP10、16、17、26、32（受理后确认时钟推进1h仍可提交）；处理不调用当前LLM配置，不声称后续模型资格已通过 |
| TP24 分类与禁止外发 | PDF独立private/unconfirmed；摘要分类不外推；本片没有模型派发或知识发布 | PP11、21、10；后续分析资格明确未实现 |
| TP25/26 UI/文件 | 当前状态/统计、最终来源和诊断、节选、历史、文件安全响应；取消详情不再显示待确认 | PP11、22、PPB01（processing/analysis取消）；PP31 |
| TP27 人工保护/旧行为 | 取消保留人工判断/来源；修改保存确认历史；旧检索/去重/评分受影响回归 | PP12、18、19；CR/DD/PS回归 |

范围外的非论文材料、全局成员、独立补充/替代、OCR、后续分析/RAG/综述中的降级标记及正式发布保持开放。下载支持arXiv标识映射及原始公开PDF链接；非直链网页诚实失败并可摘要降级。非macOS运行时报告parser_unavailable，不无隔离解析。不是跨平台或真实外部Provider端到端验收。

## 5. 验证

上一轮提交最小包，与本阶段S1分列：

- `accepted-diff`：实际snapshot diff与delivery_summary，退出0；相对task044 handoff仅新增本task046，业务/契约/测试modified=0、deleted=0。
- `accepted-evidence`：实际执行task044 verify_closeout，退出0；核对19项产物、版本/引用及check10/build4/storage10有效执行证据；复用review-code-s6独立复审，不重跑旧业务测试。
- `accepted-commit`初次退出1：新文档Markdown尾随空格触发staged diff检查，未产生提交；去除格式尾空格后`accepted-commit2`退出0。隔离索引构造19文件，PROJECT_STATUS从HEAD仅更新对应业务行及版本/日期；逐文件验证提交blob、候选路径集合、提交前后工作文件哈希和原空暂存区。`commit.json`保存完整SHA和清单；无push。
- 最终文档检查见`docs-final`的完整输出、真实退出码及实际delivery_summary。此验证只证明记录和引用/格式一致，不证明解析功能。

以上是S1及上一里程碑提交的历史证据，不作为本次实现验证。当前实现证据全部位于evidence/task046_processing_gate_2026-10-29：

- 实际读取main-ledger context -2/-3、entry/outline/read与工具说明§5；恢复时重读必要原文。entry不支持ledger参数，调用报错后使用正确entry；TS用精确行范围，越界/标题不匹配后用outline/symbol修正，没有把失败或截断当完整读取。
- run_check.py为每次运行保存完整log、command/exit_code、实际delivery_summary；JUnit保存*-tests.xml。storage2/3选择器为`-k "test_pp or test_ps or test_cr or test_dd or test_st08"`，后续run记录亦保存PYTEST_ADDOPTS。PG入口为`backend/.venv/bin/python scripts/run_storage_tests.py --postgres-bin /opt/homebrew/opt/postgresql@17/bin`；显式临时PG17/非superuser/清理，无业务库回退。
- 初轮pdf-unit1隔离bootstrap失败，修复最小根目录元数据访问后真实隔离通过；check1–4格式/类型/契约失败已修；check5/6/8通过但非最终基线。storage1 9/9；storage2 119/124（旧迁移断言及预览schema）；storage3 125/126（预览schema剩余required）失败保留并修复，不能引用为全绿。build1–4通过，最终UI基线为build4。
- S3独立review-unit红测发现坏URL中断降级，修复后review-unit2 22/22；review-storage 23/24发现预览schema并修正oneOf。主agent自审修复字面换行、重复组commit和未解析保留文件分类，补回归；独立发现终态标题已修复并补PPB参数化取消。
- 最终check10退出0：后端315项、脚本117项、前端4项通过，含ruff/format/mypy/架构与契约；build4退出0，构建前后端成功（此后产品源码未变）。storage4为129项127通过2失败，后者是测试复用旧幂等键和未等浏览器提交；修复后storage5 48/48（PP32及全部处理/浏览器、downgrade/upgrade），storage6 2/2（迁移重入/错误目标标记），storage7 1/1（LLM有数据降级保护）全绿。storage4其余受影响CR/DD/PS回归未变且通过，三次补跑覆盖全部失败及新增项；不把重叠数量相加作为覆盖率。
- focused5为3项2过1失败，用安全错误定位PP19为STATE_IDEMPOTENCY_CONFLICT。focused6遗漏-k，意外启动全integration；此时已收集的旧0014头断言仍在内存。范围外追加运行在255秒SIGINT结束，exit2，5个旧迁移期望失败、168通过，JUnit中断计数与进程不一致，不能宣称全项目测试通过；临时PG的server_stopped/root_removed均true。5个失败由storage5/6修后具名重验；其他新增0015头期望全部由storage5/6/7覆盖。未为此放宽数据保存、事务或拒绝断言。
- [独立实现及复审](../docs/workorders/evidence/task046_processing_gate_2026-10-29/review-code.md)通过；实际具名执行和覆盖限制见该报告，review-code-artifacts.json绑定最终业务SHA。docs-closeout/docs-closeout2/docs-closeout3实际执行版本、链接、scope/hash、失败后重验集合及主验证exit核对，并保存log/summary；此文档检查不替代业务测试。旧S1 handoff目录已存在，handoff-final第一次写旧目录失败且保留，改用新handoff-final目录保存最终快照，不覆盖历史。交付记录复核将“4跳”澄清为含初始最多4次请求，最终文档再存handoff-final-v2。
- 没有调用付费LLM、真实论文源或邮件；真实PDF解析/OS隔离/数据库commit和浏览器为本机执行。

## 6. D-CW-04：多来源最终文本选择

**问题**：同标题组中，多份可用PDF或多个原始摘要不一致，哪一份成为后续AI分析/知识构建的唯一最终文本？例如A摘要样本100、B摘要样本1000且各有不同PDF，标题身份合并不能判断两者等价。显示代表、人工合并target、下载先后都没有被现行业务条款明确指定为权威来源。

**方案A（建议）**：保留各来源；只有一份可用文本时按既定全文优先/摘要降级处理，多份不同可用文本时在现有处理确认中明确选一份。确认绑定所选来源/文件/文本修订；不新增独立审批阶段，不自动融合，不声称其他版本错误。影响：增加有差异条目的选择交互；选择完成前对应条目不能进入分析。

**方案B**：按冻结来源的可解释固定顺序取首个可用全文；全部全文不可用时选一份真实原摘要作为降级提案。现有处理确认明确展示所用来源、其他来源及替换途径，再由用户确认。影响：操作较少，但默认取哪份文本受确定顺序影响；绝不称其最新或权威。确切排序和协议由实现记录验证。

**独立意见及主判断**：独立审查未证实必须新增D，认为B在现有手动处理确认下可以工程实施；该意见完整保留。主agent认为从各来源共同评分过渡到唯一证据文本会影响研究范围，依据AGENTS“Changes to business semantics ... require an explicit human decision unless already authorized”及用户本轮遇到未明确设计时停止的指令，提出A/B供明确选择。不是解析器库、超时预算、下载镜像顺序或一般P1重试的确认请求。

仅依赖该选择的流水线实现待定；上一里程碑接受提交、规范核对、证据归档和可恢复记录均已完成。暂不启动其他backlog来替代本轮方向。当前无用户答案，不将超时当批准。

## 7. 阶段交接

S1授权/用户B已闭合；S2实现自验、S3独立缺陷修复及S4逐项覆盖完成。S5保持现有模块分工，以按组持久提交控制PDF内存峰值、复用公共HTTP安全传输；审阅后无额外行为保持重构收益，未制造新任务。S6最终检查与独立复审完成，S7工程收口。下一步是用户M-P0-15验收，不自动启动分析/知识发布或认领完整FR024。用户接受后按实施入口对本片manifest及混合PROJECT_STATUS对应行作最小核验、本地提交；不自动push。

[验收包](../docs/workorders/task046_processing_delivery_2026-10-29.md)提供可观察行为、场景、当前平台限制和证据入口。

## 9. D-CW-04接受与实施细化（2026-10-29）

用户选B，原话见最新检查点。固定顺序沿Run冻结检索来源记录顺序，组内从前到后尝试可定位PDF；相同来源不因完成先后抢占。全部全文失败才取第一份非空真实摘要，不拼接；每次尝试与最终来源可追溯。仅将其称为本轮所用来源，不称最新/权威或其他版本错误。静态解析无模型外发，全文分类独立于标题/摘要分类。当前阶段编辑使依赖确认失效；活动处理与编辑互斥。失败、取消、撤权和迟到结果保持真实诊断且不发布知识。

## 10. 平台与提取引擎补充授权（2026-10-29）

用户要求至少Windows、Linux，并在研究DSH和Open WebUI后明确：“pdf内容提取可以做成一个多选接口，可以另外加LLM解析引擎，这个LLM解析引擎列为下一阶段的设计目标；其他按照你的建议进行”。

- 当前阶段：分离提取引擎和隔离运行器；保留pypdf作为基础静态引擎，统一输入、文本/页码定位、诊断及来源记录接口；补充Windows/Linux运行方案与验证。引擎选择不能绕过资源、文件访问和网络隔离要求。
- 平台方案：Linux评估bwrap；Windows需要满足读取与网络限制，不能直接把只限制写入的ACL方案称为完整隔离。容器运行器可作为部署选项，不要求整个应用容器化；必须区分Windows宿主运行Linux容器和Windows原生运行。能力不足时明确不可用，不静默退回普通子进程。
- 下一阶段设计目标：LLM PDF解析引擎。该授权是设计目标登记，不代表本阶段调用模型、外发文件或已有可用LLM解析能力；后续设计须明确模型配置来源、文件外发与权限、页码/证据定位、错误与费用预算、输出校验及确认后内容保护。
- 已决定：用户异步答复“提供多个引擎选项，每次选一个执行（建议，保留统一扩展接口）”。每次只执行所选引擎，不轮询或聚合其他引擎；D-CW-04的论文来源顺序规则不变。目前仅pypdf实现，后端注册/选择接口不伪造其他可用引擎。
- 恢复之初的环境事实（后续更新见第11节）：主机macOS；`docker version --format '{{json .}}'`退出1，客户端24.0.6存在但Docker daemon不可连接。尚无本轮Linux/Windows实机隔离证据，不宣称跨平台支持完成。
- 恢复读取：实际执行状态/权威性read、task entry、skill执行与恢复、DELIVERY_TOOLS第5节及pdf_processing.py 1–150行定向read；ledger为同目录evidence的main-ledger.json，context见顶部。该时点为设计恢复检查点，当时业务代码未改；旧验证/审查记录保留，新增设计与实现仍需S2–S6证据。
- 本轮初步检查：`run_check.py platform-design1 git diff --check -- docs/PROJECT_STATUS.md tasks/046-paper-processing-gate.md`退出0并实际调用delivery_summary，日志和摘要在原evidence目录。仅证明该命令成功，不代表未跟踪task文件的完整内容检查或新增业务测试通过。一次run_check.py原文读取因行范围超界退出2，未用其输出推断实现；本轮没有运行应用测试。当时请求独立审查设计恢复记录；其后已返回有界通过，新增代码另见第11节。

## 11. 单引擎选择实现与跨平台验证（2026-10-29，进行中）

用户答复关闭第10节选择歧义。新增`pdf_engines.py`静态引擎注册接口（目前pypdf）、`pdf_container.py`独立容器运行器及`deploy/pdf-parser/`构建/部署说明；PDFProvider支持明确选择一个引擎和一个运行器，未知配置拒绝。默认macOS原生Seatbelt，Windows/Linux通过Linux容器；Windows原生ACL/Linux原生bwrap未实现，不把“评估”升级为已经支持。此轮未新增UI选项或LLM调用。

| 新增要求 | 执行场景与证据 | 当前结论 |
| --- | --- | --- |
| 一次仅执行一个引擎；未实现引擎不可用 | PE01/02注册选择、失败不切换、未知配置拒绝 | platform-unit1：与既有PDF回归共31/31通过 |
| Windows/Linux进入受限运行器；能力缺失不在应用进程解析 | PE03/04平台分派及缺CLI | 同上，模拟分派不证明宿主支持 |
| 禁网、无主机挂载、无应用凭据、资源限额及超时清理 | PE05/06检查启动约束、诊断、清理；PC01–03为真实运行入口 | 模拟用例通过；真实运行尚未通过 |
| 真实Windows宿主/Linux运行时 | `backend/tests/runtime/test_pdf_container.py`；Windows需Docker Desktop Linux容器 | 尚缺Windows宿主执行证据 |

Docker已启动，版本24.0.6。`platform-image1/2`构建均退出1：Docker Hub官方Python镜像manifest请求EOF；本机无缓存镜像。实际`platform-runtime1`退出1，3/3失败均因parser_unavailable，未跳过、未当作通过。静态接口与macOS回归`platform-unit1`退出0，31/31；`platform-lint1`退出1为格式长行，随后格式化，待复验。这些命令均通过run_check保存完整日志/退出码并实际调用delivery_summary。

上轮仅文档恢复的独立审查已返回通过（review-platform-ledger.json/context review-platform-records-20261029），不覆盖本轮新代码。新增S3及受影响复审结果见本节末；平台验证失败使S7保持开放，M-P0-15未接受。旧主基线及验证证据保留。

补充验证与修复：parse_pdf统一校验文本类型/长度、诊断及连续页码偏移，PE07拒绝畸形输出；PE08覆盖清理非零/超时不得返回成功，运行器记录具体容器名并明确daemon失联残留处置。PC02已增强为本机随机TCP监听/默认网络控制容器的可连正对照，根目录只读检查改用/tmp写入EROFS；增强后的PC集因缺镜像尚未复跑，不能沿用旧运行失败记录宣称新用例通过。

主`platform-unit3`退出0，44/44（40 PDF单元+4契约）；`platform-lint4`、`platform-types3`、`platform-architecture1`退出0。之前lint1/3长行、types2缺类型注解已修复并以上述复验闭合；contracts1误用backend解释器缺openapi_spec_validator，改用工程入口规定的contracts/.venv解释器执行contracts2，结果以对应日志为准。未改持久化/API/UI，未重跑旧数据库/浏览器批次；本轮仍没有实际Windows宿主或成功Linux容器隔离证据。

S4覆盖复核保留PC01–03及Windows宿主为未通过/未执行，不用PE模拟断言替代。S5保持既有论文来源选择/摘要降级/确认语义，只拆出静态引擎注册与独立容器适配器，无其他业务重构。S6可完成本地静态/单元复验，真实运行环境门槛未满足；S7及M-P0-15仍开放，未提交。

独立复审：`review-runtime.md`及review-runtime4基线SHA已保存，48/48通过（40 PDF单元+8独立反例），清理失败的两条历史红测保留。代码级修复复审通过，真实容器与Windows宿主验证仍阻塞交付。contracts2退出0，完成机器契约/设计指纹检查，不证明运行授权/事务。恢复命令为先构建deploy/pdf-parser镜像，再在Linux运行时及Windows宿主分别执行PC01–03；实测通过后再完成相应复审和S7，不能直接沿用本轮模拟证据。

文档核验：`run_check.py platform-docs1 python3 .../verify_platform_docs.py`退出0并调用delivery_summary，检查本轮四份文档的版本/引用、设计指纹并记录11项platform-artifacts.json；追加本检查点后以platform-docs2复核最终文档哈希。manifest仅用于恢复差异，不代表平台验收。

## 12. FR-024剩余范围与平台交接（2026-10-30）

本节为每日整理的规划，不启动新业务工作。第4/5节保留此前macOS限定验证，第10/11节承接已授权新增平台范围；下表不倒填通过或人工接受。FR-024原文仍是依据，原PP/PE/PC具名矩阵不复制。除PP-G01已有授权外，其余待后续明确授权并实例化任务；本单是FR-024剩余范围的唯一规划归属。

| ID / 精确范围与可观察结果 | 包含/排除、写入所有者、落点及输入输出 | 前置、验收草案、完成与交接缺项 |
| --- | --- | --- |
| PP-G01 单静态引擎与Windows/Linux隔离 | 当前选定引擎＋PDF→文本/明确失败；解析适配器拥有运行器，`pdf_engines.py`/`pdf_container.py`及`deploy/pdf-parser/`已建；不加入自动引擎回退、LLM调用或未定UI选项 | 既有用户授权及第11节PE/PC；真实镜像、Linux容器和Windows宿主可用后验证成功、无网络/主机挂载/凭据、资源耗尽/超时/清理失败；PC01–03和宿主证据未闭合，不以模拟通过收口；交S3/S6与M-P0-15 |
| PP-G02 P0非论文格式逐适配器 | CFG-05线索或FR-023接收文件→文本/状态/路径；资料处理所有者，拟建资料解析适配器；pdf、doc/docx、ppt/pptx、html/htm、md/txt/rst、yaml/yml/json/toml、ipynb及代码逐项保留；不写正式KV，不把表格/多媒体提前纳入文本 | 消费A06/A08、Project文件归属和接收契约；每格式合法/损坏/空文本/不支持诊断、越权/取消/迟到无提交、部分失败不阻断其他对象；P1表格默认不参与KV、P2多媒体未支持诊断分别保留；格式→库/字段/具名测试全矩阵仍缺，B05逐片交接FR-025/026，不以论文PDF测试替代 |
| PP-G03 失败重试及本地PDF替换接入 | 失败论文及用户动作→新的处理修订/诊断；FR-023主责接收/替换命令，本单只消费已接收来源，拟接`paper_processing.py`及Run/补充入口；不新增P0通用Run恢复，不覆盖已发布正文 | 消费A07/A08和FR-023 WriteScope/修订约束；成功/解析失败、重复请求、旧修订、撤权、并发替换和取消迟到，失败保留已有人工内容；精确操作、失效集合、持久字段与具名测试待在接收任务细化，本单保留解析接入缺项，避免两任务各写同一来源 |
| PP-G04 论文/资料详情有权文件入口 | Project作用域文件引用＋当前资格→可访问文件或安全拒绝；资产服务拥有授权读取，基础层详情UI消费，拟扩文件API与详情组件；不共享另一Project私有文件、不以Run下载代表全部详情入口 | 消费实际资产归属及08/08-01；有效访问、删除/缺失/签名过期、跨Project/撤权拒绝且不泄露文件，下载读写竞争按实际存储验证；现有PP11仅论文Run入口证据，资料/详情路由、字段、负例测试仍缺，交FR-012/023 |
| PP-G05 摘要降级来源贯穿消费 | 已确认文本及来源标识→AI分析、向量化/索引输入与论文详情/RAG/综述可识别来源；处理所有者产生事实，FR-026拥有向量化/索引消费及正式发布，各消费者传递/呈现，拟接分析/引用映射；不把摘要标成全文、不改变Session/Review已绑定版本 | 消费FR-025/026/028/033具名接口与版本契约；正文和摘要正反对照、缺标记拒绝或明确诊断、旧版本读取不随新处理改写；向量化/索引输入标记及三个展示面均需验收，消费者路径/持久字段/具名测试尚缺；不因当前Run来源展示通过关闭本项 |
| PP-G06 全量处理统计与侧栏 | 当前处理结果＋待重试/不参与状态→成功/失败/降级等摘要与合法确认；Construction拥有确认资格和投影，UI只读展示/跳转，拟扩`ConstructionRuns.tsx`及侧栏；不重复DD-G06筛选确认、不宣告分析/发布成功 | 消费各已接入处理结果与A07；部分失败仍可确认、全部无可分析结果不得伪造成功、旧token/撤权/修订冲突拒绝、刷新与取消投影一致；现有PP/PPB为论文局部，非论文状态、侧栏全字段/路由及具名测试仍缺，交FR-011/025 |

硬依赖只按实际消费建立：PP-G01可独立完成平台实测；PP-G02逐格式接入，不要求全部格式完成才验证论文路径；PP-G03依赖接收/替换契约而不依赖P1通用重跑；PP-G04消费对应资产归属；PP-G05逐消费者接入，不反向阻塞已定来源选择；PP-G06消费已经实现的结果，但不得把未接入种类标为已覆盖。全量FR-024、FR-023/025与TRACK-008c/012a/012c/012e保持开放。LLM提取引擎按第10节仅为下一阶段设计目标，其模型/政策/费用与验收规格仍待建立。

## 13. M-P0-15人工接受与交接（2026-10-30）

用户原话：“M-P0-15通过，继续下一阶段”。接受本轮已呈现的论文处理、单引擎接口与容器实现成果，保留已披露的平台验证限制；不能推断用户免除了必需验证。接受前快照为`docs/workorders/evidence/task046_acceptance_2026-10-30/accepted-baseline.json`，包括HEAD、候选范围哈希和混合工作区/暂存区状态。

上一轮delivery-artifacts与platform-artifacts合并核对：业务代码/测试/契约与后者覆盖后的接受基线一致；仅task046和PROJECT_STATUS因2026-10-30每日整理变化。第12节为新增规划，不是代码变化或执行授权。暂存区为空，HEAD仍为f5d5b19；不重复运行旧macOS业务测试。复用platform-unit3、lint4/types3/contracts2/architecture1及review-runtime4/报告；PC01–03和Windows宿主缺口不改写通过。

按IMPLEMENTATION_ENTRY“人工接受后的Git提交”中“缺失的必需验证/独立审查不能借此绕过”，本地提交暂缓至平台验证闭合；没有创建commit或push。提交候选清单来自两份旧manifest的并集，仍需精确分离PROJECT_STATUS等混合文档；接受快照不是直接git add清单。当前阶段区分：M人工接受已完成，新增平台S6/S7及提交仍开放。

用户继续下一阶段的授权在[task047](047-llm-pdf-extraction-design.md)承接此前约定的LLM PDF提取设计；先闭合扫描版范围等未明确设计，不自动执行第12节全部规划，也不将设计授权变成真实模型/文件外发授权。恢复context=task046-accept-20261030-1；实际定向read/entry及ledger沿原evidence/main-ledger.json。平台重试与下一阶段设计分别记账。

接受当日平台复试：`accepted-platform-image1`退出1，官方Python镜像manifest仍EOF；未得到新镜像，不重复运行必然缺运行器的PC用例。接受记录核验`accepted-design-docs1`退出0，代码/测试/契约无新增漂移，仅任务和状态记录变化；两项均保存完整日志/实际退出码并由run_check调用delivery_summary。

接受记录独立复核：task047 evidence的review-design.md/review-acceptance-summary.json确认43项接受基线一致，仅记录变化，exit0；认可人工接受与平台工程/提交缺口分列，不将接受迁移为平台实测通过。

## 14. 平台实测分期调整（2026-10-30）

用户在M-P0-16验收时明确“实测缺口写到下一个大阶段（当前L0实现不做）的待办里”。第13节暂缓提交是历史状态，现由该决定解除。Windows宿主实测、Linux容器运行验证在下一大阶段TRACK-023继续跟踪；既有失败证据保留，不称验证通过。已接受M-P0-15产物随M-P0-16合并本地提交。
