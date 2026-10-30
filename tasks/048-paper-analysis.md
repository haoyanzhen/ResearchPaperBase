# Task048：论文 AI 分析与人工确认

文档版本：v1.4
更新日期：2026-10-30

## 8. 最新检查点

流程v1.11；S1–S7工程完成；M-P0-17于2026-10-30获用户明确接受并授权Git提交。授权来自2026-10-30用户“继续实现下一阶段，直到里程碑进度或遇到未明确设计”，承接已接受并提交的M-P0-15/16（1d93f42）。论文分析生成、人工补全/覆盖保护、确认闭环已完成；正式入库与非论文范围未推进。无新增待决设计。

最终208项隔离持久化/浏览器、517项单元/架构、48项契约通过，类型/静态/格式/构建有效；S3两缺陷修复并由原红测复验闭合，S6独立复审通过。当前测试基线final-test-snapshot，零测试漂移证明final-tested-drift.json；最终交接基线handoff-snapshot仅追加本任务/状态记录，不改变业务规则。主agent恢复context `next-20261030-root-recovery2`，实际原文读取与摘要调用在root-ledger及各批次run.json/summary，见第5节。S7文档引用/版本/一致性核验记录closeout-check。初始混合改动保留；本轮按明确接受执行精确本地提交，未授权push；提交SHA在后续检查点记录。

## 1. 目标与授权

对已确认最终文本生成论文五字段结构化分析，支持失败诊断、人工补全、显式重生成覆盖确认、分析阶段确认。仅当前已交付的论文手动Run；非论文接收/解析、正式入库发布、Research/Review、P1自动Run与TRACK-023不在此切片。首次可用闭环形成后提交M-P0-17验收。

## 2. 当前依据与基线

FR-017/025；02-03第6节；02-02第2.3/5/10节；04-01第4节及PaperAnalysis；06 A08.3；04-04参数契约。实际paper_processing.confirm仅进入analysis，runs.waiting和UI仍禁用分析。

独立设计核查：部分失败已有跳过/失败预览规则，不需要新增持久排除语义；分析保留冻结Provider参数及未设置省略规则，不能套用仅PDF整理的4096缺省。长文不静默截断、拼接或自动改成摘要，超限明确失败。完整内容预算不能被称作精确token证明。

## 3. 修改落点

候选分析领域校验`backend/src/rpb/modules/construction/domain/analysis.py`；分析命令/Provider/Worker在`backend/src/rpb/adapters/paper_analysis*.py`；Run/API及Demo Worker接线；`frontend/src/PaperAnalysis.tsx`及ConstructionRuns；机器契约；两个单元测试文件、集成test_paper_analysis和test_browser_analysis。已有browser_runs仅随已开放分析更新标题期望。复用当前权限/来源政策、事务和幂等机制。

## 4. 验收规格与最终覆盖

| ID | 要求及禁止副作用 | 当前有效测试与证据 |
| --- | --- | --- |
| PA01 | 五字段/类型/长度严格校验，缺字段、NUL和格式错不成为成功；不得混入资料类型字段 | 领域67例、Provider17例在unit4通过；PA18完整Unicode上限、PA24五字段NUL人工422/模型安全失败，final-regression通过 |
| PA02 | 只读本Run已确认最终文本和Project主题；来源标记/修订可追溯；摘要不冒充全文 | PA10摘要、PA22实际PDF独立分类与最终全文，final-regression通过 |
| PA03 | 生成、重试、失败保留原稿；人工编辑/确认优先，覆盖须当前修订授权 | PA11/13/14失败、拒绝、旧token、取消；PA21确认后覆盖保留历史；PA24异常输出不破坏人工稿，final-regression通过 |
| PA04 | 读取/派发/提交当前资格、分类、配置身份核验；撤权/取消/过期/重复/并发不产生越权或双提交 | PA10/14–19/23真实持久化、9个撤权时点、Worker交错、租约过期、跨Run/CSRF、回执失败回滚、冻结参数与凭据轮换；受影响PD/PS/PP/CR/FR旧回归，final-regression通过 |
| PA05 | 人工补全、编辑来源追踪；确认当前有效结果，旧token及输入变化拒绝；无成功不能伪造成功 | PA10–13、PA20成功子集且失败不被持久排除；PA12补全后错误清除/历史任务保留；独立原红测转绿，final-regression与review-storage2通过 |
| PA06 | 浏览器生成/编辑/确认/拒绝覆盖/刷新，成功失败与人工状态统计；不发布知识版本 | PAB01实际浏览器+HTTP+PG：标量与多行数组、添加/移除、刷新保留、移动端无横溢；PA12/20统计与PA10不发布断言，final-regression通过 |

## 5. 最终验证与证据

证据目录：`docs/workorders/evidence/task048_next_stage_2026-10-30/`。业务稳定基线`final-test-snapshot`包含436文件（含未跟踪文件），`final-tested-drift.json`核验测试前后零漂移。完整命令/退出码在各批次run.json，输出在output.log，普通日志及JUnit均实际调用delivery_summary，不能只凭测试数量判断需求覆盖。

| 批次 | 实际结果与有效性 |
| --- | --- |
| final-regression | 208/208持久化与浏览器通过，536项不在本次-k集合，无跳过；exit0；JUnit及摘要齐全；隔离PostgreSQL17.11临时socket、受限角色，测试后停服/删除，无业务数据库回退 |
| unit4 | 517/517单元/架构通过，exit0；之后仅增强浏览器测试和交接记录，相关实现/fixture/依赖未改，证据有效 |
| contract-tests3 / contract3 | 48/48契约测试通过；86个request/success partial及28个request-only操作校验通过；未执行相对旧契约的兼容性比较，不声称整体接口完成 |
| static4 / types4 / format3；final-static / final-format | ruff、103个源码mypy与177文件格式检查通过；最终浏览器测试改动后再验ruff/格式 |
| build4 | TypeScript与Vite构建通过；review-snapshot到final-test-snapshot前端源码/依赖无差异，独立S6核验可复用 |
| 独立审查 | review-s3.md保留两项初始发现及修复；原3个红测不改断言在review-storage2转绿，30/30通过；最终复审见review-s6.md |

复现持久化/浏览器：在仓库根使用`PYTEST_ADDOPTS='-k "test_pa or test_pp or test_ps or test_pd or test_plb or test_cr or test_fr"' backend/.venv/bin/python scripts/run_storage_tests.py --postgres-bin /opt/homebrew/opt/postgresql@17/bin`；启动器隔离数据库并清理。单元：`uv run --directory backend --locked pytest tests/unit tests/architecture`。前端：`npm --prefix frontend run build`。正式再次验证应按DELIVERY_TOOLS第5节使用新的日志/JUnit路径、基线、实际退出码与delivery_summary，不能覆盖本次历史报告。

所有外部模型、文件Provider均mock。真实模型内容质量/费用、生产运行、正式知识发布、非论文、Windows/Linux平台实测不在本次验证内；平台项仍按用户决定留在TRACK-023。容量预检只做保守估计，未知Provider默认输出无法预先证明总预算，不自动截断、切分或套用PDF专用4096默认。仅观察到既有Starlette/httpx弃用告警，没有隐去失败或跳过必需用例。

## 6. 业务决策与里程碑

M-P0-17为手动Run论文五字段分析、人工补全/覆盖保护和分析确认的完整切片；不是整个FR-025或Construction发布闭环完成。无新增未明确设计需要裁决。达到本切片验收点后停止扩展正式入库等后续范围；人工接受尚未发生，不自动提交或push。

验收场景：在已确认处理结果的论文候选上生成分析，核对摘要/全文来源；编辑总结及多行要点后保存并刷新；重新生成时取消覆盖，确认人工稿仍保留；仅确认有效分析后显示“分析已确认，等待入库能力”，不出现发布知识版本。对应可复现PAB01与PA10–24，不用mock结果代替真实模型质量判断。

## 7. 交接

恢复使用本任务entry，换新context、定向读取必要原文，并比对最终handoff-snapshot（含实际未提交/未跟踪文件）。S3/S6报告及第5节为有效证据入口。M-P0-17等待人工接受；接受后按实施入口最小核验包精确本地提交，保留初始混合工作区。已接受M-P0-15/16的commit为1d93f42，不重复提交。当前未承接正式入库/非论文/平台延期范围。

### S2执行记录

早期root目录调用ruff/mypy未完整采用backend配置；static2/types2已改用`uv run --directory backend --locked`，发现1个import分组及require_revision应直接从llm导入，待当前稳定回归批次结束统一修复，再复验。static1的76个分组报告是错误工作目录，不据此改无关源码。普通日志由run_check.py调用delivery_summary --log；JUnit另以实际退出码执行delivery_summary，输出以*-junit-summary.json保存。storage1的-k test_pa意外匹配既有paper测试，93项因未同步新投影契约失败；没有削弱测试，后续更新闭合契约并重验。storage2/3修复确认枚举与Z时间；storage4两项测试夹具/断言定位修正：使用真实commands.name注入回执故障，公开错误沿既定PROVIDER_FAILED映射且额外核验内部PROVIDER_RESULT_UNKNOWN。storage5 19/19含上述回归已通过。

S3正式审查开始；独立设计审查reviewer-design-audit.md仅论证按现有规范可实现，不可代替实现审查。正式审查必须完整覆盖本切片新代码/规范/测试及受影响旧路径。

### S2完成与S3审查基线

最新基线review-snapshot；上次完整S2快照s2-snapshot只供增量比对，不作为业务接受。regression1为202项中200通过/2失败（完整日志保存）；失败是既有PD01旧等待ID应先于修订拒绝，以及新编辑框显式label缺失。代码修复，不放宽断言，regression2 23/23覆盖两失败及全部新增PA/PAB；storage6额外PA23验证冻结参数/当前轮换凭据且不持久化密钥，1/1通过。unit3 512/512，contract-tests2 48/48，contract2、static3、types3、format2、build4通过。源文件改动后普通日志/JUnit摘要均实际执行，受影响修复不将旧失败清零。

容量只做保守预检，未知Provider默认输出无法预先证明总预算，超限仍失败；不提供自动分块或新输出上限。非论文、真实模型质量/费用、正式发布和其他平台实测未验证。待独立审查后完成S4逐需求复核、S5简化和S6复验；不能将本记录当M-P0-17接受。


### S3修复与恢复记录（2026-10-30）

恢复context `next-20261030-root-recovery2`，实际运行task entry、task/工具第5节/skill/实施入口第2节及02-03第6节、06 A08.3定向读取，见root-ledger；恢复diff与review-snapshot一致。entry误带read专用ledger参数、section简写歧义均失败后改用正确命令，没有以失败读取替代原文。独立审查完整报告见review-s3.md；review-storage1保留三个红测：NUL使PG写入异常并可能中断Worker、人工补全被旧失败作业覆盖错误。

已修复领域/机器契约的NUL拒绝（人工422、生成安全失败且原稿保留），以及按当前候选revision过滤已解决失败；历史任务不删除。PA24五字段及PA12补全投影回归：fixes1 6/6；unit4 517/517；contract-tests3 48/48；contract3/static4/types4/format3通过，普通日志与JUnit摘要已实际执行。稳定基线review-fixes-snapshot及8文件差异review-fixes-diff.json。独立原红测复验待review-storage2完成，不能先记闭合。

### S4覆盖复核与S5维护性

逐PA01–06复核输入、结构、人工保护、权限时点、失败/重复/并发、处理依据失效、事务回滚及实际浏览器；PA01补上NUL持久化反例，PA05/06补上人工解决旧失败后的投影。PAB01加强数组项多行、添加、移除、刷新保留断言，待最终回归。现有PA10–23及相关旧PD/PS/PP/CR/FR覆盖受影响既有要求；未将mock当真实模型质量验收。容量默认沿原Provider，非论文/正式发布保持范围外，无新增业务决定。S5将latest_errors在统计/候选投影中各计算一次，避免逐候选反复排序；其余沿既有Worker/投影结构，不新增抽象或无关重构。


### S6最终复验与S7收口（2026-10-30）

独立S3两问题闭合后，S4覆盖复核和S5维护性检查完成；以final-test-snapshot运行最终208项受影响回归，通过且零漂移。S6独立复审见review-s6.md：核对最终JUnit、实际exit0、PG清理、有效旧证据及未变前端/依赖，当前无未闭合缺陷。两次审查不代替人工里程碑接受。之后仅补本文件和PROJECT_STATUS状态，按实施入口纯记录差异可复用业务审查，不无限循环复审。

S7已完成本次授权切片，验收场景/覆盖/风险见第4–6节。最终文档检查命令由run_check.py捕获完整输出/退出码并实际调用delivery_summary，见closeout-check；handoff-snapshot保存最终产物。用户尚未答复M-P0-17接受，不创建commit、不推进依赖此成果的正式入库阶段。


## 9. M-P0-17人工接受与Git交接（2026-10-30）

用户原话：“接受 M-P0-17，进行git提交。”接受范围为本任务第4–6节及handoff-snapshot，不扩展到正式入库、非论文或真实模型质量。接受时HEAD为1d93f4205daa9b695ff1ac29651331f803a44133，暂存区为空；commit-acceptance-diff.json核验436文件零漂移。初次git status终端输出被截断，随后完整清单保存commit-pre-status.txt，不将截断视为完整检查。

本轮context为commit048-1，实际执行bootstrap、entry、提交规则/工具第5节及证据索引定向读取；commit-ledger.json保存读取证据。复用208项持久化/浏览器、517项单元/架构、48项契约及S3/S6通过结论，没有重跑未变业务测试或重新完整业务审查。仅接受记录/状态文字改变，进行引用、版本及提交树核验，完整日志与真实退出码由run_check.py保存并执行delivery_summary。

提交只含M-P0-17实现、契约、测试、必要文档与精选验证/审查证据。原混合工作区流程文件、旧任务和运行产物保留，不纳入本次提交。完整快照归档和早期日志仍在本地evidence；最终manifest、结果及审查报告纳入提交。具体清单和blob核验见commit-scope.json、commit-preflight.json；提交后比对SHA、实际路径、内容与无关文件保护见commit-post.json。不push，不为写入自身SHA循环amend。
