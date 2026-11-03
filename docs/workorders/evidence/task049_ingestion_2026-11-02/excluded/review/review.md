# Task049 筛选后全部排除 · S3/S6 独立审查

审查范围为完整手动增量检索后，新增待筛选论文全部由模型或人工排除的 no_change。比较 excluded/baseline 与 candidate4 的 source-manifest，11 项变更与当前文件哈希逐一相符。Git 基线 38b4d73。未修改仓库。

读取按 AGENTS 启动两项定向 read，随后运行 delivery_context.py entry tasks/049-ingestion-publication.md，使用独立 /tmp/excluded-review-ledger.json 和 excl-review 读取工具说明 §5、02-02 §10.4、04-01 §4.1。执行前获取 §5 原文。结合运行时读取 RunStore.waiting / invoke，paper_screening 和 ScoreWorker 状态写入、组证据校验、入库核验确认、no_change.prepare/commit 路径及 UI 按钮与真实浏览器用例。代码与测试覆盖分开判定。

首次发现人工修改者只需非空、当前摘要与模型评分输入不一致仍被接受，独立 PostgreSQL 复现 2 失败（probe1）。修复后发现每个组成员各自生成的时间戳会误拒真实模型排除的重复论文，另在首次确认后理由缺失时入库预览返回 500（probe3）。最终 candidate4 修正四项，均已独立复测。

* 外部探针 /tmp/excl-review/test_excl_review.py，加 3 个仓内专项。由 /tmp/excl-review/run final1 设置 pytest 路径和选择器，经 backend/.venv/bin/python scripts/run_storage_tests.py --postgres-bin /tmp/rpb49-pg17/bin --pgvector 实际执行。在独立 PG17.11、pgvector、非超级用户、Unix socket 下 7/7，退出 0，0 skip，清理成功。各阶段完整日志、XML、退出码及 delivery_summary.py 生成的摘要分别在 /tmp/excl-review/probe1*、probe2*、probe3*、final1*。
* 最终独立浏览器使用同一隔离命令加 -k browser_analysis，PUBLICATION_BROWSER_EVIDENCE_DIR=/tmp/excl-review/browser。手动保存排除理由、浏览器两次确认、核验版本、刷新结果完整运行；同次覆盖首次发布、增量发布、全匹配、零条返回。1/1 退出 0 无 skip，详见 /tmp/excl-review/browser.xml、browser-summary.json 和 browser.log。论文提供方、模型、嵌入与图谱采用确定性测试替身；不证明真实服务质量。
* 最终候选重复模型输入按来源/元数据、组成员、证据与成功结果对应，人工 actor/时间可核对。缺失、不完整、失败、冲突或已过期的判定不能完成核验。负面反例中旧确认 409，误差原因可读；事务原子、写槽、历史版本、重放和晚到写入沿既有 no_change 入口。审查主证据 excluded/affected 142/142 及候选更新后的对应专项，重新检查原测试有效范围。
* 通用 compat 退出 1，要求方向性审查。独立 /tmp/excl-review/compat.py 对 38b4d73 与当前 schema 比较，compat-summary.json 退出 0。历史零条和全匹配响应能通过新旧 schema，排除数须为正，只有新分支携带该字段。冻结旧 schema 且严格屏蔽未知字段的客户端无法校验新分支，需采用更新的契约。UI 与契约同时更新。
* 无开放 S3/S6 工程阻断。此结论限于上述子范围，人工里程碑验收待用户进行。
