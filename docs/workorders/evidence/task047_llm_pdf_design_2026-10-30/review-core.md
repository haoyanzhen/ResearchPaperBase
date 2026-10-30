# Task047文字整理核心与Provider独立代码审查

版本：v1.0
日期：2026-10-30

## 结论

四个新增文件的局部S3及缺陷修复复审通过：pdf_text_cleanup.py、pdf_cleanup_provider.py及各自单元测试。发现一项P2 Gemini思考内容/最终提案混淆，已由主代理修复，独立原红测转绿。**不代表完整LP或M-P0-16通过**：新引擎未注册/未接入Run、UI、分类保存自动继续、持久预算、撤权/取消/迟到提交或处理确认；D-PDF-03容量策略仍待用户实际决定。无需用此审查重开已定D-PDF-01/02。

独立context review-core-20261030、review-core-ledger.json。执行两条bootstrap、task entry及outline，读DELIVERY_TOOLS §5、task047已接受设计和第9节、四个完整小文件（跨分批/验证/协议异常边界需完整）、受影响HTTPProvider.request与compile_for_model。工作区四文件均为未跟踪产物，审查以实际字节而非HEAD绑定；最终SHA在review-core-artifacts.json。

## P2缺陷及闭合证据

pdf_cleanup_provider.py原Gemini分支无条件拼接parts[*].text。现行配置允许thinkingConfig.includeThoughts；合法thought摘要加最终JSON被误判无效，而只有thought:true包含合法JSON时被接受为最终提案。与“不把非最终输出当成功提案”、四协议沿原模型参数运行的要求不符。

独立review_core_probes.py两条反例复现：test_gemini_thought_summary_not_parsed_as_final_answer与test_gemini_thought_only_cannot_become_final_proposal。依据[Google官方Gemini thinking文档](https://ai.google.dev/gemini-api/docs/generate-content/thinking)：includeThoughts可返回思考摘要，调用者以part.thought区分它与回答。只查阅官方协议文档，未请求真实模型或发送资料。

修复SHA 7f6ac67bcc4fde498d0b66aca21c6878d6cb3a8e1c10213ae1fa7fcf40f6a258仅把thought非true的text拼成最终答复；thought-only变成空JSON而安全拒绝，不关闭或改写用户thinking参数。主LCP06两条回归与独立原红测均通过。

## 核查结果

- prepare在任何模型派发前完成全部输入与分批规划；字节上限标注为字节，不声称模型token容量。源页连续范围、整数非bool页号、固定末尾页换行、全文覆盖及20万字符边界均检查。
- 每个同页相邻行边界恰好进入一个batch，批次共享末/首上下文行但不重复重建。validate按输入顺序要求精确字段、精确ID与有限separator；reconstruct仅使用原始行，保留原行和页序、重算Unicode码点偏移/digest及原始行映射，超输出限额失败、不返回部分结果。
- 独立CRLF、前后空行、Unicode/emoji和Unicode行分隔符probe验证不改分隔建议时逐字符相等、映射回原行一致；原项目LC01–08覆盖分批接缝、缺批、非法结构、长行和输出膨胀。CR属于原行内容被保留，不声称将其标准化或修复排版。
- 四协议仅构造文本请求，沿显式model/参数和受控HTTP授权回调；无隐式探测、重试或换模型。传递min(调用剩余时限,配置时限)，HTTP底层另有连接/DNS/读取总deadline及1MiB响应上限。底层权限与网络验证仍是既有依赖，不把mock HTTP当实网验证。
- 截断/错误状态、畸形响应、非法最终JSON、越界边界、凭据回声均安全失败。独立四协议回声probe确认异常只含稳定错误码，不暴露模拟凭据；未验证真实凭据或任何外部端点。

## 实际执行

1. review-core1：真实exit1，62项60通过、2失败，均上述Gemini反例；保存执行前基线、完整log、JUnit、run.json及实际delivery_summary。
2. review-core2：真实exit0，**64/64，无skip**（54项目核心/Provider单元＋10独立probe），包含两条原红测。命令为backend/.venv/bin/python -m pytest backend/tests/unit/test_pdf_text_cleanup.py backend/tests/unit/test_pdf_cleanup_provider.py docs/workorders/evidence/task047_llm_pdf_design_2026-10-30/review_core_probes.py -q --junitxml=docs/workorders/evidence/task047_llm_pdf_design_2026-10-30/review-core2.xml。摘要与退出码一致。

测试全部模拟HTTP、无业务数据库、LLM、邮件或文件外发。没有改业务文件或共享任务文档；只写独立测试/报告/evidence。未重复旧平台/浏览器/数据库测试。

## 接入前仍须覆盖

D-PDF-03决定真实容量保证及分批配置；当前max_input_bytes不得升级成token保证。模型输入包含协议包装/输出容量与实际Provider限制，仍需按决定落实。引擎选择/配置资格应在整个作业入口校验，即使单行文档无需模型边界建议、计划零batch，也不能绕过引擎可用性/分类/政策。

来源/Project/Run修订、返回结果与具体派发的身份绑定由后续应用层负责，纯函数局部p1:l1等ID不赋予跨来源复用资格。LP02/03/06/07/08/09/11/12完整义务仍需真实持久化和确定性交错、分类自动继续、取消/权限变更、Worker重启预算不清零/未知外呼不重发、组预算与摘要分支、UI/token确认回归。当前单次适配与纯函数不持有这些权限或状态，不能用64项计数宣布上述需求覆盖。M-P0-15平台缺口也未由本轮关闭。

最终测试增量：仅LCP06补显式includeThoughts=True配置和请求保留断言，业务源码未变；已定向读取并运行review-core3，真实exit0、2/2，实际JUnit摘要已保存。最终测试SHA 1d3d94c50418a85f61c1a8190a52d79bc4c6fcb088f34a16e3d2fce1125a5e50，review-core-artifacts.json同步该最终测试；不把64项旧批次声称为该增量后的全量重跑。
