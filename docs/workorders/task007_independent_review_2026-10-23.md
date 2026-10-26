# Task007 A05 独立审核

文档版本：v1.0
更新日期：2026-10-23

## 结论与受审范围

用户要求派subagent重点审核需求覆盖、契约一致性、权限边界和测试证据。三位subagent分别执行需求、契约/安全、测试/证据只读审查，主代理复现后合并为 **2项P2待修问题及1项文档澄清建议**。本次没有修改实现、契约或测试，不记人工接受。

受审范围是[task007](../../tasks/007-skeleton-review-fixes.md)第6–7节A05及当前工作树的实际文件（含未跟踪文件），不是仅HEAD。第1–5节为已完成的骨架修复历史，不作为本次新交付重复审核。入场175个源文件逐一匹配原A05交付清单，无漂移；旧证据未覆盖。报告登记后PROJECT_STATUS因本次状态更新改变，不能将该变化误报为原交付篡改。

## R01 / P2：分类写成功仍接受未确认结果

位置：[OpenAPI](../../contracts/p0.openapi.json) 7010–7012行（confirm）和7507–7509行（correct），[测试](../../scripts/tests/test_material_policy_contracts.py) 27、88–93行。

两个分类POST的200 data直接引用通用MaterialClassificationView。该类型需要支持GET返回未确认来源，但也被用于两个写操作，导致以下组合通过写成功响应校验：

```json
{"confirmation_status":"unconfirmed","confirmation":null}
```

复现使用现有测试VIEW补齐其余合法字段，并按实际端点200信封验证；confirm、correct均返回True。测试90–91行还把该未确认VIEW当作两个写操作成功正例，不能发现确认记录漏写或成功状态错误。

依据：[04-01](../design/04-01_p0_operation_contracts.md)435–442行要求confirm完成分类确认，correct仅对已确认记录更正；对应N-T02/N-T07/N-T08。这是可以在当前契约层表达的成功后置条件，不依赖数据库或A06实现。

建议保持GET泛型；两个写成功响应收窄为confirmed及非空确认事实，使用已确认对象作成功正例，并分别增加未确认/null响应反例。不要通过收紧通用读取schema使未确认来源无法展示。

## R02 / P2：同步幂等POST允许缺失或空的去重期限

位置：[OpenAPI](../../contracts/p0.openapi.json)7013–7015、7510–7512行，及通用Meta的7974行起；同一[测试](../../scripts/tests/test_material_policy_contracts.py)91行只提供request_id。

两个POST均有副作用、要求Idempotency-Key且同步完成，但成功信封引用只要求request_id的通用Meta。使用合法已确认data时，下列两种meta在confirm/correct均通过：

```json
{"request_id":"00000000-0000-4000-8000-000000000001"}
{"request_id":"00000000-0000-4000-8000-000000000001","idempotency_expires_at":null}
```

依据：[04 §7](../design/04_api_contracts.md#7-幂等与可靠受理)199行要求已受理响应给出去重最早失效时间，非终态才可为null。这两个操作同步200、不创建Task；通用Meta无法表达这个端点约束。缺失期限使消费者无法依约判断去重窗口，现有正例又掩盖该遗漏。

建议仅为两个POST成功meta要求非空Time；GET/PUT不增加该要求。补缺失、null、错误格式反例及UTC时间正例。至少24小时的真实保留/淘汰仍是后续持久化运行测试，不用schema假装证明。

## C01：明确本次主动文字与分类门槛的关系

[04-01](../design/04-01_p0_operation_contracts.md)444行称“分类先于任何模型/嵌入外发”，448行在current_submission段又写“该投影不替代分类”。[08-01](../design/08-01_agent_data_access_policy.md)107行已明确：本次主动提交文字供本任务使用，不额外弹确认。

需求与权限审核者均建议澄清。主审将其单列C01而非确定的权限漏洞：444行仍处于上传/检索来源分类段，448及03-04也已承认文字例外，因此不能据此断言运行实现必然增加确认或发生越权。但建议明确分类门槛的适用范围、可信本次主动文字无需额外分类确认，并强调例外不延伸至历史自动取用或上传文件。直接落实既有Q1即可，不需要重新决定政策。

## 需求、权限与未验证范围

N-T01–08均有设计/测试映射；本次发现上述可测成功响应覆盖遗漏。用户×Project、P0 Owner、归档只读、安全404、禁止客户端指定审计主体、私人放宽依据、当前限制与不可变正文分离、修订不可复用和固定版本/输入保护均有明确约束，未发现另一项可确定的扩权问题。

可信scope签发、原子read/dispatch/commit、真实授权/隔离/持久化、缓存传播、Provider派发和UI/端到端明确不在A05实现范围；完整Task/来源详情留A06–A08。审核不把这些授权外工作列为缺陷，也不以静态通过推定运行安全。P1/P2未被本次授权启动。

## 实际执行与证据

证据目录：[task007_independent_review_2026-10-23](evidence/task007_independent_review_2026-10-23/entry-check.json)。使用既有独立环境`/tmp/rpb-a05-contracts/bin/python`，未访问数据库、LLM、论文源或邮件服务。

| 检查 | 本次结果 |
| --- | --- |
| `scripts/check_api_contracts.py` | 退出0：47请求/成功局部+40仅请求，170 schemas，131源行，5/6 SSE；[日志](evidence/task007_independent_review_2026-10-23/structure.txt) |
| `-m unittest discover -s scripts/tests -p 'test_*.py' -v` | 退出0，46方法/无跳过（Material11方法）；[日志](evidence/task007_independent_review_2026-10-23/tests.txt)；证据审核subagent另独立重跑46方法通过 |
| R01/R02反例 | 六种端点/非法输出组合全部被当前schema接受；[可运行脚本](evidence/task007_independent_review_2026-10-23/reproduce_success.py)、[结果](evidence/task007_independent_review_2026-10-23/success-counterexample.txt) |
| 快照与旧证据 | 入场171/交付175文件tar与SHA完全匹配；当前175源文件与交付一致；23个原证据文件摘要匹配，证据专项独立核验 |
| 兼容检查 | 对A05入场基线退出1/3行，对原始A04基线退出1/83行，逐行与历史差异一致；[命令记录](evidence/task007_independent_review_2026-10-23/compatibility-commands.json) |
| 并行修复归属 | A04四个修复schema与其verified-scope相同；没有将其归为A05新增成果 |

原测试通过及证据真实不消除R01/R02；这两项需要新增反例后修复、复验并记录新的兼容差异。原3/83项非零兼容门禁不是新的审核缺陷，仍保留方向审查与人工接受边界。

## 独立审核分工与处置

- requirements_review：核对N-T01–08与政策/UI/契约；独立复现R01，提出主动文字歧义。
- contract_security_review：核对权限、错误与幂等；独立复现R01/R02，交叉核对C01。
- evidence_review：核对测试、清单、tar、摘要及兼容差异；独立复现R01，重跑46方法通过，未发现其他证据真实性问题。
- 主代理：复现R01/R02全部组合、重跑结构/46方法及两组兼容检查，合并去重并登记项目状态。

修复尚未执行。修复后应让对应反例先能证明当前缺陷，再验证收窄后的正确响应；重跑全部受影响契约测试、结构检查和准确基线兼容审查。人工审核者、日期、接受范围及结论仍待填写。本次只交付审核，不自动启动task008或应用实现。

收尾并行变化：入场之后检测到task006任务单新增人工验收记录（该文件由其他工作更新，本轮未写入）；其范围不包含A05。当前源文件相对原A05交付的差异因此包含task006任务单及PROJECT_STATUS，入场无漂移结论仍成立；A05受审schema、测试和规范没有变化，原证据摘要仍一致。本轮保留这些并行记录。
