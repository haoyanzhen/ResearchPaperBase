# Task047 完整实现独立审查

日期：2026-10-30
版本：v1.1
阶段：S3完整范围审查及S6受影响独立复核；不替代S7或M-P0-16人工验收。

## 结论与基线

本轮已审范围未发现仍未闭合的代码阻塞项。独立复现的P2预算来源标记和P1政策撤回后摘要提交均已修复，真实隔离PG反例转绿。代码结论绑定review-s3-final-artifacts.json；核心Worker最终SHA为abcfc5b4d109f5f247353707a6eab91162286d98d81f315a551d2b7cbfc0501a。任务v1.4的最新第1/5/10节按实际SHA阅读，不以版本称号代替原文；最终文档指纹见manifest。

本次审查覆盖pdf_cleanup_capacity/worker/provider/budget、pdf_text_cleanup、paper_processing、run_worker、runs适配/API/domain、ConstructionRuns UI、demo Worker接入、OpenAPI及coverage、新契约说明与LP01–12。包括未跟踪文件。容量设置原review-capacity审查范围实测哈希未变；保真核心及其测试与review-core基线一致。未重复假称审过无关混合工作区改动。

## 发现及修复证据

1. **P1，已闭合：失败来源后撤回资料政策仍可提交摘要。** 原Worker在最后失败之后step=fetch，仅复核账号/Project/候选，跳过已有模型输入的当前资料政策；私有PDF在allow_private下均整理失败，下一tick前改public_only，仍提交degraded摘要。违背task047 §4.3及04-01末节“当前资格/政策失效停止且不能绕道摘要成功”。独立review-s3-policy1 exit1、1条真实PG失败；原文测试和完整日志保留。修复把本组实际文件及分类修订保存为material_dependencies，在resume（覆盖下一源/摘要提交）、dispatch、result重验，完成组后才清除。review-s3-policy2 exit0，原摘要反例、独立下一源反例及原P2共3/3；PL19两交错在最终33项复测通过。无后续派发或业务处理结果提交。
2. **P2，已闭合：组预算耗尽误写当前来源未尝试。** review-worker1真实PG红测证明已完成一个模型批次的来源被标not_attempted。修复对实际已调用的当前源追加budget_exhausted，后续来源保持not_attempted，不绕道摘要成功；PL05及独立原反例在review-s3-db1/db2通过。耗尽测试采用持久预算边界注入，并非真的等待240秒。
3. **文档历史措辞，已更正。** task047 §1“当前仅pypdf已实现”改为“原静态基线仅pypdf；本次LLM实现及验证状态见第10节”，与现行实现和历史范围区分一致。

曾提示首次等待分类缺记录可能逃逸，进一步核对同一代码基线外层except(ProviderFailure,AccountError)后撤回该疑点；PL20已证明受控停止且零模型调用，不列为未解决发现。

## 需求覆盖核查

| 要求 | 独立核查与测试依据 |
| --- | --- |
| LP01 单选引擎/模型 | ConstructionStart枚举拒绝列表/null/未知引擎，省略兼容pypdf；Run冻结单一model_selection，LLM仅将pypdf作为输入准备；PL01/07/12、四协议LCP及PLB01。整理失败不把静态原文伪作LLM成功。 |
| LP02 当前权限/资料政策 | 实际文件先private/unconfirmed，等待分类不派发；分类确认自动续原作业。read/dispatch/result/commit和跨来源依赖检查，PL01/02/10/15/18–20及P1独立反例；取消/撤权不以摘要绕过。 |
| LP03 冻结输入与配置 | 原始候选来源/修订与Run有效输入绑定，配置深拷贝、输出默认4096只在本引擎生效，显式别名保留；容量及budget_limits进入Run快照。CAP01–05、LCP07、PL11/12/16。容量映射不外发，凭据由当前guard读取，不存模型结果。 |
| LP04 文字层限定 | 无文本零模型调用，保留失败文件与明确诊断；CAP06真实PDF含可见文字页、图像页、已有隐形OCR文字层，页码保持1/3，图像不送模型；PL13、PLB01。UI明确“图片中的文字未识别”。不验证OCR正确性。 |
| LP05 保真与完整批次 | unchanged核心验证每个边界ID恰好一次、分隔符枚举、不得附正文、缺批拒绝，原行顺序及页界固定；原文/整理digest和映射独立保存。LC01–08、CAP04/05、LCP03/04、PL01/09，完整文本按需读取。 |
| LP06 取消/重复/迟到 | Run锁下reservation先提交再外呼；租约、attempt和依赖复核；未知结果到期失败，不重发。PL02–04/06/08/15，真实PG确定性交错及commit回滚；结果写入和对象插入同事务。 |
| LP07 重处理/人工保护 | 候选修改沿现有writable/失效机制，处理活动和分类等待不可编辑/确认；旧token拒绝。PL17重新处理保留原PDF/原结果历史，重新生成新修订且不沿用确认；已有PP16/17/19为受影响基础回归，主db7报告包含既有PP/CR。 |
| LP08 来源链/摘要 | 来源顺序冻结、每来源全部批次有效才提交，任意批失败不发布部分全文；PL07失败链仅真实Version 0摘要，PL13无文字降级，PL05组预算阻断不摘要成功；P1修复覆盖权限变更后的切源/降级。 |
| LP09 隔离与作用域 | 静态PDFProvider沿原隔离器准备，模型只收到文本边界prompt，无PDF字节/工具/邮件。processing-text由Project→Run→candidate归属及对象三重范围过滤，no-store；PL21同hash异Project拒绝，独立真实第二Project及对象挂接反例拒绝。平台限制见下。 |
| LP10 不执行文档指令 | 模型仅返回边界建议，JSON额外正文拒绝；四协议无tools/files，React展示转义文本；处理结果保持提案，确认后仅phase=analysis，无FR025调用/知识发布。 |
| LP11 累计预算 | 30/120/240秒、32/64次、零技术重试；持久reservation和单调耗时结算；新组复制Run冻结limits且不继承已耗计数。Budget01–07、PL03/05/14及P2反例。保守字节预检不是精确token或账单保证。 |
| LP12 原文件/来源/映射 | 原始PDF和文本不可变对象，整理结果另建文本对象；查询核digest，选中prepared_document复用真实文件分类与修订。PL01/09/16/21，LC映射与CAP06；同hash不扩大访问权限。 |

## 独立实际执行

所有执行完整log、真实exit、JUnit或普通log摘要均保存于本目录，且实际调用scripts/delivery_summary.py。不是仅引用工具名称。

- review-s3-db1：27/27，exit0。PL01–18参数化、PLB01浏览器真实PDF静态隔离提取（下载/模型mock）与原P2；前后15项SHA无漂移。
- review-s3-unit1：85/85，exit0。核心、容量、预算、四协议Provider；包括CAP06真实混合页与LCP07默认输出发送。
- review-s3-policy1：1条失败、exit1，P1原红测。保留不覆盖。
- review-s3-policy2：3/3，exit0，独立P1两个边界和P2；前后SHA无漂移。
- review-s3-db2：33/33，exit0。PL01–21参数化及4条独立反例；前后16项SHA无漂移。该次不重复PLB01。
- review-s3-contract1：exit0，结构/映射检查通过；工具明确未检查与旧baseline的兼容性，也不证明运行权限或事务。运行API契约由上述真实服务测试另行验证。

隔离PG每次采用scripts/run_storage_tests.py --postgres-bin /opt/homebrew/opt/postgresql@17/bin，PYTEST_ADDOPTS在run.json中保留精确选集；没有连接业务DB。db1/db2/policy1/policy2日志均确认server_stopped=true、root_removed=true。全部模型/下载为mock；浏览器使用项目实际服务和真实pypdf隔离解析。db2之后test_browser_runs仅增加两张局部截图（原行为断言不变），已独立读该delta；不声称新增截图是本代理重跑所得。

主代理日志/真实run及摘要已抽查：cleanup-db6 15/15、unit-all1 428/428、contract-tests1 48、contract2、lint3、types3、frontend2均与记录一致；这些分别属于其执行时基线，不冒称为P1最终修复后的全量结果。最终S6主执行随后完成，其实际结果和产物一致性见下方追加复核。

## 工程限制与交接

本报告支持当前本机切片代码S3及S6受影响复核通过，P1/P2闭合；不代表整个FR-024/025交付，不代表M-P0-16人工接受或S7工程收口。LLM提取是文字排版建议，不能保证静态提取质量、排版语义绝不变化、精确Provider上下文容量或实际费用。未调用真实模型、外部论文服务或邮件。

旧M-P0-15 Windows宿主未实测、Linux容器实测/镜像获取未通过的缺口仍未关闭。当前macOS真实解析、mock模型和浏览器证据不能替代这些平台的实际运行验证。非论文格式、上传替换、AI分析、知识发布不在本次范围。

按AGENTS bootstrap→task entry→工具第5节，用独立review-s3-ledger.json/context review-s3-20261030-1读取；文件变化后定向重读，旧报告保留。初次合并输出的UI diff因工具输出预算截断，随后按准确源码范围重读，不以截断输出完成审查。只写本代理evidence和反例文件，未修改业务源码、任务文档或提交/push。

## S6最终证据追加复核

主cleanup-db-final1真实JUnit为157/157（PL/PP/CR/PS与浏览器），cleanup-unit-final为433/433（unit/architecture），run.json真实exit均0。独立review-s3-close1实际读取JUnit逐testcase检查无failure/error/skipped，验证20个implementation-validation-baseline.json文件当前SHA完全匹配，并核对最终隔离PG清理；exit0，完整log/run及实际delivery_summary保存。主types/lint/format-final实际run/summary均退出0；此前契约48项、contract2和frontend2构建记录已核对。代码未因最后截图测试变化改变；本轮不以截图增量重跑无变化的业务。

已实际view_image查看cleanup-classification.png与cleanup-comparison.png：文件分类默认私人、分类依据和自动继续文案可读；原始两行与整理后单行并列可核对，文字层限制及真实来源说明可见。mobile整体图只作布局参考，390宽无横向溢出由浏览器断言证明，不冒称对缩略长图逐字核验。

review-s3-final-artifacts.json绑定本次审查的25项代码/测试/契约/文档与独立反例；其中主20项实现基线由review-s3-close1再次核验。最终文档收口可另增记录，文档变更不自动扩大本文代码验证范围。本机受控外部mock的完整闭环通过仍不关闭M15 Windows/Linux实测缺口，也不代替用户M16接受。
