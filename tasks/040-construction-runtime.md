# Task040：Construction启动与多源检索

文档版本：v1.3
更新日期：2026-10-28

## 8. 最新检查点

流程v1.9；S1–S7工程已收口，M-P0-12于2026-10-28获人工接受。最终591项验证集合：full2中未变511项通过证据复用，最终受影响80项全部通过；不声称单次591全绿。用户2026-10-28选择D-CW-02 A，承接M-P0-11后继续授权至下一里程碑/未明确设计。task039 handoff362文件无漂移；本轮before完整快照见[evidence](../docs/workorders/evidence/task040_construction_runtime_2026-10-28/before)。保留原工作区；接受后按第10节限定快照提交。

## 1. 目标及边界

M-P0-12：手动retrieval Run启动、固定已确认词与配置、四论文源真实检索协议、结果摘要/逐来源失败、候选读取、retrieval等待、取消与历史；不发布知识版本，不实现去重评分/解析/资料Provider或P1恢复调度。保留FR021其余P0需求，不更改分期。评分采用D-CW-02 A，设计同步不冒充运行交付。

## 2. 依据

01 FR014/016/020/021与D-CW-02、02-02独占槽/候选/取消、02-03 D-CW-01 A、04-01 §4启动/快照/候选、04-02 Task、05 §7、07事务、08配置绑定/立即撤权；实施入口v1.8。

## 3. 修改落点

新增Construction输入、Run存储与0014迁移、Worker、四论文检索适配器、API及Task投影、浏览器ConstructionRuns。扩展来源原子解析、Workspace占槽读取、Project/账号治理的取消与影响绑定；补机器契约、隔离集成/浏览器/协议测试。已接受的0013迁移升级为0014后，历史当前head断言对应更新，仍严格验证完整表集、数据保护与项目创建不启动Run。

## 4. 需求与追踪

测试缩写：CR=backend/tests/integration/test_construction_runs.py；CRB=同目录test_browser_runs.py；unit=backend/tests/unit；contract=scripts/tests/test_construction_contracts.py。每项映射到当前实际产物，未交付范围不计为通过。

| 需求与禁止副作用 | 可执行场景 | 当前证据 |
| --- | --- | --- |
| CR01 仅手动检索、已确认且修订匹配、已测试模型、严格字段；selected来源整词失败，其他词继续 | CR01/02/09/12；unit/test_construction_inputs；contract CR01；既有ST确认/模型资格回归 | integration11 20项通过；check6单元及契约通过 |
| CR02 原子受理、同键重放/异载荷拒绝、queued不占槽、running/waiting独占、失败无孤儿 | CR01/07线程Event确定交错/13注入receipt失败回滚/14数据库唯一约束；CRB02受理后响应500原键核查 | integration11通过 |
| CR03 取得槽时重校验并冻结词/配置，后改不重写历史，无明文密钥投影 | CR01/06/08租约未知不重发；协议单元每页当前凭据；contract闭合运行/配置投影；旧源配置保密回归 | integration11及check6通过；最终受影响80项通过，其余511项复用full2 |
| CR04 四论文协议、半开日期、分页、每源累计预算、词与来源可追溯；拒绝错误响应及不安全XML | unit/test_paper_retrieval全部6例；CR11真实适配器伪HTTP坏ADS与健康源并存；CR18两词单源累计预算；CR01快照/来源 | integration11及check6通过，无真实外呼 |
| CR05 部分成功保留、全失败不进入后续；waiting持续占槽，不伪造succeeded/发布 | CR01/03/11/12/18；CRB01分别显示selected整词拒绝和all_resolvable部分来源拒绝 | integration11通过 |
| CR06 当前权限、跨Project隔离、取消迟到结果、归档/账号禁用即时终结、预览不得扩大影响 | CR04/05/10/15/16；CR17当前修订重复取消、旧修订冲突、同键重放；旧治理删除/撤权共用路径回归 | integration11；integration8的245项通过；最终受影响80项通过，其余511项复用full2 |
| CR07 浏览器启动/历史/快照/来源诊断/窄屏/刷新/退出；未知提交原键重试；候选清理不残留 | CRB01/02，390px截图；CR17/18分页不漏不重、错作用域/取消后游标失效；unit游标过期/修订变更 | integration11通过；截图已由Codex视觉检查 |
| CR08 迁移及拒绝降级、公共错误/Task/分页契约、既有功能不回退 | CR14；TermsClient所有Run成功/错误响应实际schema验证；contract3例；原storage/治理/配置/浏览器全集 | integration8通过；check6通过；最终受影响80项通过，其余511项复用full2 |
| D-CW-02 A 默认0–10/≥7与非法分数不得伪零 | unit初判边界0/6.99/7/10与None/bool/字符串/负值/11/NaN/∞ | 单元通过；仅规则辅助函数，完整评分流水线未实现 |

未交付：补充资料/非论文Provider、追加输入、去重评分及人工修正、解析分析、入库发布、自动运行/后续恢复、现有KV基线接入、Research/Review。它们保持原P0/P1分期；本次不是完整FR014/020/021/022验收。

## 5. 验证

所有数据库写入使用scripts/run_storage_tests.py创建的临时PG17 Unix socket实例、独立非superuser角色；日志含run_id及server_stopped/root_removed，不回退业务DSN。LLM、论文源用fake/受控HTTP，未使用真实Provider、邮箱或生产数据库。

已执行日志见[evidence/logs](../docs/workorders/evidence/task040_construction_runtime_2026-10-28/logs)：

- `python3 scripts/engineering.py check`（check6）：ruff/format/mypy、256单元、83契约脚本、前端类型及4项测试通过。
- `npm --prefix frontend run build`（build3）通过；浏览器加载该构建，后端真实HTTP/持久化，外部Provider受控。
- `PYTEST_ADDOPTS='-k "test_cr"' backend/.venv/bin/python scripts/run_storage_tests.py --postgres-bin /opt/homebrew/opt/postgresql@17/bin`（integration11）：20 passed，571 deselected，21.24s，隔离清理完成。
- integration8：245 passed/345 deselected，覆盖治理、Project命令、存储及当时Run。之后更严格响应契约校验发现权限错误消息不canonical，已修复并由integration11通过。
- full1：568 passed/15 failed；15项为新head/表的旧前提，已准确更新，未删数据保护断言。CR13早期故障注入由HTTP异常边界映射500，测试改为验证注入发生、500以及实际零Run，未弱化回滚要求。
- full2：588 passed/3 failed，702.69s，已停止和清理。3项是CRB01运行时已载入旧单匹配断言而dist更新为两类拒绝、以及PM03 archive/delete仍假定两种修订相等。最终固定源码与构建后，CR+PM共80项全部通过（83.63s），覆盖这3项及影响面；其余511项代码/测试无变化，复用full2通过结果。此为591项有效验证集合，不是单次全绿声明。check6之后补all_resolvable拒绝来源展示与对应CRB01断言，integration11覆盖新UI；check7再次全通过（256单元/83契约/4前端），build-final前后端构建通过。最后PM03两项旧假设改为独立影响修订格式/稳定性，CR15加强范围变更修订断言；CR+PM最终80项全部通过，511项未选。源码和其他测试未变，最终lint/format通过。

独立审查（只读）：review_run_boundaries检查槽/冻结/来源/权限/事务，发现ADS空title、分页节流、每页凭据轮换及两类治理影响绑定，均已修复并增量复审限定通过。review_run_ui_contract发现未知提交重试、候选残留、模型快照/非法输入、分页、重复取消与两类来源拒绝展示，已修复；最后all_resolvable分支已增量复审限定通过。审查不代替实际执行和人工验收。

S5自查：复用已有来源解析、公共分页meta、权限事务与共享限流，未引入Provider SDK/新依赖或无关重构；保留独立Run持久事实与清理边界。

## 6. 决定与里程碑

D-CW-02 A已定；M-P0-12在第1节完整成果及S1–S7完成后提交人工验收。其后评分仍用已定规则，不重复问阈值。

## 7. 状态

设计规则已同步，限定代码已完成，自动验证/独立审查通过，工程已收口；M-P0-12人工接受未完成。后续评分等依赖本里程碑，不自动越过。验收包见[task040交付报告](../docs/workorders/task040_construction_delivery_2026-10-28.md)，最终handoff快照含完整未提交/未跟踪源码；未自动commit/push。


## 9. 工程收口与恢复

S1限定手动检索成果与下一验收点，未把完整FR或backlog当授权；S2实现及基础验证；S3两位独立审查并修复；S4按第4节核对成功/拒绝/失败/并发/权限/绑定/清理；S5复用接缝无额外重构；S6最终check7/build-final、80项受影响验证与511项有效复用；S7记录交接。没有未决业务设计或未关闭工程发现。

记录与复验：115个本地引用、25个锚点检查通过，Git diff whitespace通过。review-final→handoff的源变化仅两处已复审测试加强、任务/状态/验收记录；无运行源码漂移。完整证据保留，不覆盖旧快照。恢复时先核对handoff清单；收到M-P0-12实际接受后按实施入口核对/本地提交，再继续下一授权阶段。

## 10. M-P0-12人工接受（2026-10-28）

用户原话：“ok，通过M-P0-12，继续实现下一阶段，直到里程碑进度或遇到未明确设计”。接受范围为本任务第1节和验收包；历史第6/7/9节的等待状态在此更新，不扩展为完整FR021/022或真实Provider线上验收。

接受基线为task040 handoff。核验当前业务源码、契约、测试与规范无漂移；差异仅task041工程工具/流程和状态记录（新增5、修改6），未纳入本次业务接受。沿用第5节有效验证，不重跑无变化业务测试。采用隔离Git索引提交handoff中相对HEAD的已接受文件，排除未跟踪的.gitignore运行配置；task037接受记录、task039已裁决D-CW-02设计前置一并纳入。task041修改完整保留工作区，不自动push。提交清单与SHA见后续task042检查点。
