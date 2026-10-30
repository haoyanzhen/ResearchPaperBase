# Task048 S3 独立实现审查

日期：2026-10-30；版本：v1.1；审查context：review048-s3-1。

结论：**S3完成，两项发现已修复并独立复验闭合；当前无未闭合实现缺陷**。初始审查发现两个可复现缺陷，原始红测与以下发现记录保留；修复复核见末节。未发现应新增人类业务决定的事项。审查范围为任务048授权的手动Run论文分析切片，不含资料分析、正式知识发布、自动Run或真实模型质量。

## 产物与审查证据

基线HEAD为1d93f42；审查绑定review-snapshot/source-manifest.json的436个实际文件（含未跟踪），不是只看HEAD。独立测试后对manifest核验零漂移，记录review-s3-drift.json。原有混合工作区修改按initial-git-status.txt区分；审查仅新增本目录ledger、探针与报告，未改源码/规范。

已独立执行状态/权威性bootstrap、task048 entry及DELIVERY_TOOLS §5；原文定向读取记录在reviewer-implementation-ledger.json。个别任务/TS文件范围超尾和猜测符号/路径读取失败已明确报错，随后按outline/wc/实际路径成功定位；未将失败或截断输出当完整依据。完整新分析domain、adapter、Worker、Provider及前端组件均已读取；进一步检查runs/paper_screening/API/bootstrap/demo接线diff、HTTPProvider派发锁、TermWorker授权校验、分类来源、契约结构差异和全部新增PA/PAB测试。

实际独立验证：

- review-unit1：uv run --directory backend --locked pytest tests/unit/test_paper_analysis.py tests/unit/test_analysis_provider.py，79/79通过，exit0；完整日志、JUnit、run.json、delivery_summary摘要齐全。
- review-storage1：通过scripts/run_storage_tests.py新建隔离PostgreSQL17、临时socket/受限角色，未读取业务数据库配置；默认mock Provider。PYTEST_ADDOPTS加载review048_probes插件，将探针挂到已有integration父节点以复用隔离fixtures。25项中原有22项通过、3个独立反例失败，exit1。完整日志、JUnit、run.json、delivery_summary摘要保存；日志确认server_stopped/root_removed，未运行真实Provider。
- 核查主agent实际run.json与summary：unit3 exit0且独立JUnit摘要512通过，contract-tests2 exit0，regression1 exit1（200通过/2失败），regression2 exit0（23通过），storage6 exit0（1通过），static3/types3/format2/build4/contract2 exit0。失败历史保留，未将旧失败清零。主运行器先保存完整日志和实际退出码，再运行delivery_summary；JUnit另有*-junit-summary.json。

## R048-1 [P1] NUL分析内容通过校验并使后台Worker异常退出

精确位置：backend/src/rpb/modules/construction/domain/analysis.py:12–25；影响提交位置backend/src/rpb/adapters/paper_analysis_worker.py:189–193；后台接线scripts/run_business_demo.py:134–159。

构造五字段均合法的JSON，仅methods为`valid text\u0000suffix`。UTF-8编码成功，但PostgreSQL JSONB不接受NUL。人工PATCH返回500 STORAGE_INTERNAL_FAILURE；生成路径则先通过paper_analysis校验，再在最终persist抛sqlalchemy.exc.DataError/psycopg.errors.UntranslatableCharacter（\u0000 cannot be converted to text），异常逃出run_once，任务不能正常记录失败。在当前demo唯一后台线程中没有捕获这次异常，线程会终止，影响后续所有后台作业。

复现：review048_probes.py的test_review048_nul_manual_is_controlled及test_review048_nul_generated_is_terminal_not_worker_crash，均在review-storage1真实隔离持久化中失败；完整stack在JUnit/output.log中。此反例不依赖真实模型偶发输出：Provider mock返回已验证的实际字符串即可确定复现。

依据：FR025格式错误/部分生成失败必须记录失败且允许重试/人工补全；06 A08.3结构错误不得提交且不清旧人工稿；PA01严格字段校验及PA03/04失败/提交完整性。建议在共享分析校验中对所有文字字段及数组元素明确拒绝存储不支持字符，人工路径受控422，模型路径记PROVIDER_RESPONSE_INVALID并保留原稿。至少补scalar/array、人工/模型、旧人工稿保留和下一作业仍可执行的回归。不建议靠吞掉全部数据库异常把真正存储故障伪装为内容错误。

## R048-2 [P2] 人工补全成功后历史失败重新覆盖当前投影

精确位置：backend/src/rpb/adapters/paper_analysis.py:290–308，backend/src/rpb/adapters/runs.py:434–436；可见影响frontend/src/PaperAnalysis.tsx:13。

步骤：首次模型返回缺字段→任务failed→人工保存完整五字段（200）→重新读取候选。analysis_current为true、当前内容为人工稿，但analysis_error仍是PROVIDER_RESPONSE_INVALID。save_content已经清空错误，candidates投影又以latest_errors无条件覆回；summary.failed也按同一历史作业计算。界面会继续告知“分析失败…可…人工补全”，与已完成补全矛盾。用户为了清除错误可能被迫重新调用模型，甚至授权覆盖刚保存的人工内容。

复现：test_review048_manual_completion_clears_current_failure在review-storage1失败；实际analysis_error字符串保存在JUnit。该测试在候选断言处已失败；统计问题同时由summary实现直接确认，应将统计断言另行完整执行作为修复验收。

依据：FR025完成/失败/待确认/人工修改状态应如实展示，人工补全有效；PA05/06。建议按失败作业所绑定候选修订与当前修订匹配过滤当前错误，保留独立任务历史。不能仅以valid(c)过滤，否则失败重生成应保留的当前错误会被误隐藏。补全、处理依据改变、新生成成功等各路径需与“失败重生成保留旧有效稿”区别。

## 逐要求与边界复核

| 要求 | 独立核查结果与限制 |
| --- | --- |
| PA01五字段/字段类型/长度/非法输出 | 单元79通过，四协议及截断/密钥回显有覆盖；NUL持久化缺口见R048-1 |
| PA02最终文本/摘要标记/输入依据 | PA10、PA22真实持久化通过；实际全文单独分类，Provider只取已确认文本与主题；未做真实模型质量判断 |
| PA03人工保护/重生成/保留旧稿 | PA11/13/14/21通过，保护预览绑定候选/处理修订且失效请求拒绝；NUL异常需补失败收尾保护 |
| PA04当前权限/分类/凭据/并发 | PA15–19、23通过，9个撤权交错、双Worker、取消/过期、跨Run/CSRF、回执失败回滚均覆盖；HTTP authorize只在实际发送时持锁，提交再核验；没有真实Provider调用 |
| PA05补全/当前确认/成功子集 | PA12/13/20通过，失败项不形成持久排除，未成功不能确认；补全后当前失败投影缺口见R048-2 |
| PA06浏览器与统计 | 独立读取PAB01及主regression2通过证据；本审查未另运行浏览器。BusinessApp:363按actor+Project remount，prepareAnalysis的mounted保护不产生跨项目串入。NUL与旧失败状态是当前缺口 |

在已审查范围内未发现静默更换冻结模型、绕过覆盖确认、跨Project正式知识写入或自动把失败项持久排除。输入改变后失效稿以retained_analysis投影，不混作当前analysis/basis；正式入库按钮未开放。未知结果/租约过期无自动重发；当前切片仅单次完整文本调用，未设输出上限保留Provider默认，不虚称精确总token保证。

## 后续复核范围

修复两项后保留红测历史，独立复验上述探针及受影响分析测试；R048-2还应执行统计断言/浏览器人工补全状态。S4测试追踪补上这两个已证实场景，S5/S6在新产物基线上进行。此报告不是S7或M-P0-17人工接受。


## 修复增量独立复核（2026-10-30）

复核基线review-fixes-snapshot，原审查基线到修复基线共8文件变化：领域校验、analysis投影、Run投影、单元/集成测试、两份机器契约及04-01同步。独立重读受影响原文与实现；当前修改没有扩大业务语义或更改输出缺省。

- R048-1闭合：五类字段统一拒绝NUL；人工422，模型输出记录失败而不异常逃出。PA24五字段真实PG回归验证旧人工内容/候选修订不变、任务failed、下一次Worker空转正常。原独立两个NUL红测无需改断言即转绿。
- R048-2闭合：latest_errors仅选候选修订匹配的失败作业，Run投影与summary共用该判断；人工补全换修订后不再误报，独立探针已实际执行到failed==0断言且通过。原PA11及新增PA24仍验证失败重生成保留有效稿时当前错误可见，不靠valid(c)粗略屏蔽失败。
- review-storage2：与初始相同隔离启动器、同一独立探针，选择全部PA1/PA2，30/30通过、exit0，完整日志/JUnit/run.json/delivery_summary已保存。覆盖原22项、新增PA24五字段与原3独立红测；原review-storage1保留。
- summary和候选循环将latest_errors每次计算一次，代码核对为行为保持的简化。
- 主agent随后仅加强PAB01数组项编辑/添加/移除及刷新后保留断言；独立已读取新增测试，最终浏览器运行结果由S6提供，本审查不把阅读冒充执行。

修复后漂移记录review-s3-fixes-drift.json：仅backend/tests/integration/test_browser_analysis.py测试增强与tasks/048-paper-analysis.md交接记录变更，产品逻辑仍对应修复快照。最终S6基线已由主agent保存为final-test-snapshot。S3现无未闭合发现，可继续S6最终受影响回归和里程碑交付。该结论不代表最终回归已执行，也不代表M-P0-17人工接受。
