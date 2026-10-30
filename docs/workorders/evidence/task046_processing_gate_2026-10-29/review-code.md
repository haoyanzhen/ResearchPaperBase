# task046 S3/S6 独立实现审查

日期：2026-10-29；版本：v1.0；context：review-code-046-20261029。

## 结论

限定M-P0-15实现及修复复审通过：本报告所列最终代码未发现仍开放的可行动业务或安全缺陷。独立发现的坏URL降级失败、终态标题误导、预览schema不匹配以及source_attempts契约缺项均已修复；相关独立回归已通过。额外覆盖缺项TP23已补PP32并由本审查者独立执行通过。

此结论是限定代码和场景审查，不替代主agent最终受影响全套检查、文档核验、工程收口或用户M-P0-15接受。不宣称完整FR-024、跨平台解析、真实外部Provider端到端、AI/RAG/发布完成。

## 实际产物基线与读取

初始review-code-baseline完整405文件快照包括未提交/未跟踪产物；以f5d5b19识别本片增量但不只审HEAD。主实现与审查并行，review-code-s3-delta记录10个修复文件；review-code-final-baseline再次保存405文件。review-code-final-delta记录后续测试/文档变化。最终受审业务/契约/专项测试SHA见review-code-artifacts.json，不能把早期快照当最终绿测基线。

实际审查：paper_processing/pdf_processing/processing_tables、新0015迁移、runs/API/run_worker、screening/scoring/dedup、HTTPProvider、ConstructionRuns、OpenAPI及PP单元/存储/浏览器测试；新源文件完整定向分段读取，修改文件以f5d5b19差异并补关键上下文核对。六份账号/LLM/SMTP/系统源测试新差异仅将0014头断言换为0015，未弱化原数据/拒绝断言，已单独查看；其完整执行由主agent迁移回归负责。无关流程/整理修改未认领审查。

遵循AGENTS两条bootstrap、task entry、独立ledger/context及DELIVERY_TOOLS§5。原文与源码SHA和选择范围见review-code-ledger.json。少数路径/符号/末行猜测无效后改用outline/具名symbol；宽检索截断仅作定位，不作为已读完整原文。初次系统python运行storage入口help缺psycopg，仅为入口探测失败；实际全部PG验证使用backend/.venv/bin/python，未回退业务数据库。

## 发现、修复与独立证据

| 编号 | 发现及影响 | 修复/复审证据 |
| --- | --- | --- |
| RC01 P2 | PDFProvider.prepare只捕获ProviderFailure；坏port URL产生ValueError跳出整组，后续全文/真实摘要都丢失 | review-unit红测真实失败；逐链接捕获安全ValueError后review-unit2中的独立test_review_bad_url_preserves_fallback通过，正式PP27补坏URL分支 |
| RC02 P2 | ScoringPreview只放宽kind，但confirmation_invalidation仍要求content_change字段，合法重评分预览不符合公开schema | review-storage PP19真实失败；改两个封闭oneOf分支，review-storage3的PP19通过 |
| RC03 P2 | 详情标题先看processing/analysis phase，取消终态仍显示待确认/待分析 | 标题先判终态；独立review-storage3的PPB01 processing/analysis两分支均通过 |
| RC04 契约覆盖 | 前端直接遍历source_attempts，但schema允许省略 | 列required并补PP31负例；review-contract 4/4通过 |
| RC05 覆盖 | 受理后token过期仍有效的正例原无具名测试（不是已证明代码bug） | 新PP32推进确认模块时钟1h、保持执行lease有效，验证持久结果；review-storage4 1/1通过 |

主agent并行自审修复字面反斜杠换行、重复组commit去重及保留失败PDF独立分类。本审查者检查了对应修复与PP23/25/21等；独立真实换行用例执行时已含修复且通过，不伪造“本审查红测先失败”的记录。

review-storage2新增两个失败被保留并定位：PP19错误复用post helper的固定幂等键，返回STATE_IDEMPOTENCY_CONFLICT；review-storage-debug只包装测试post输出安全错误以查明，未改应用行为。PPB第二次click后未等待请求结束就执行Worker。修复为新意图各自显式uuid、等待可观察processing状态；未弱化原断言。review-storage3 3/3重新通过。

## 独立执行结果

| 证据前缀 | 实际结果 | 用途/限定 |
| --- | --- | --- |
| review-unit | 16项：15通过、1失败，退出1 | 初始坏URL红测；旧失败保留 |
| review-unit2 | 22/22，退出0 | 当前PDF专项及2项独立回归，真实解析/OS隔离；外部服务mock |
| review-storage | 24项：23通过、1失败，退出1 | 首次PP存储/浏览器，schema缺陷 |
| review-storage2 | 27项：25通过、2失败，退出1 | 修后PP及新增场景，发现测试键/异步等待问题 |
| review-storage-debug | 1项失败，退出1 | PP19 409定位为幂等键冲突，不称业务权限失败 |
| review-storage3 | 3/3，退出0 | 修后PP19与两个PPB分支，保留原业务断言 |
| review-storage4 | 1/1，退出0 | PP32 token到期后持久确认有效 |
| review-contract | 4/4，退出0 | PP31及相关现行契约断言 |

每项均保存完整.log、真实-run.json、JUnit.xml及实际delivery_summary的-summary.json。PG命令统一通过scripts/run_storage_tests.py创建独立PG17、非superuser、无TCP业务库连接，结束清理事实保留在日志；筛选PYTEST_ADDOPTS明确记录。不同轮次包含重叠用例，不相加声称总覆盖率。未运行全项目测试或真实论文源/LLM/邮件。

## 需求覆盖与实现判断

依据用户B、FR024、02-03§6、06 A08、05确认/迟到规则和08隔离规则，交叉核对review-test-plan的27组场景与task046现矩阵：

- 固定来源逐组冻结，先全部候选全文路径后才真实非空摘要，保留未尝试/失败/选中状态；不存在摘要融合或显示代表直接成为权威文本。实际全文和fallback文件与最终摘要文档身份分开。
- 筛选/处理确认绑定当前等待项与修订；活动编辑互斥，后续人工变更回筛选并撤销受影响处理确认；未变组复用，失败重评分保留既有确认。处理确认不等于分类确认或参与知识发布。
- 文件/全文分类不继承公开摘要；API逐Project/Run/候选归属、当前权限及文件digest读取，缺文件410；处理链无模型派发或知识发布。
- 下载每跳地址校验/固定连接IP、请求不带凭据，限次/大小/时间；解析在macOS sandbox-exec子进程限制网络、文件和资源。真实隔离探针、Unicode页范围、损坏/加密/无字/超限与缺隔离运行时均具名验证；其他OS报告能力缺失而非无隔离退回。
- 接收、Worker及commit事务检查当前权限/资格；真实commit交错、重复Worker、撤权/取消/lease、持久失败回滚覆盖，不以mock事务代替。
- UI明确本轮来源、真实摘要降级、不可用和历史，不把analysis等待标作已完成分析。无可用文本无下一确认；部分失败不新增整Run全成功门槛。

余项依然开放：非论文资料、全局已发布成员、独立补充上传/替换、用户业务重试、AI/RAG/综述的实际消费与来源标记、正式知识发布。当前下载仅arXiv映射/原始公开PDF链接，普通网页可失败后降级；不宣称全站解析或跨平台能力。后续消费者必须继续实现当前分类/依赖权限检查，不因本片确认已完成而绕过。

主agent仍应核对最终主验证结果与该SHA清单的差异、版本引用及验收包，再作工程收口；本报告没有生成用户接受记录。
