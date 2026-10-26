# Task015：B02 Account基础物理模型与首条迁移

文档版本：v1.1
更新日期：2026-10-25

## 1. 目标与授权

用户授权：“继续按 project-delivery 流程推进 B02，核对已有任务单和前置依赖，确定首个物理模型与迁移切片，完成本轮交付、自验及独立审查，再提交我审核。”入场按流程v1.6计划S1–S3后交S4；执行中流程更新为v1.7，最终阶段及验收点见第9节；后续任务未授权。

核对tasks/001–014，无B02执行单。task004为示例；task009/013为规划；task014仅Project.Create机器契约。Project.owner依赖Account身份，因此本轮选Account聚合的基础持久记录为先行切片，不建缺失Account外键的Project表。A02逻辑持久化及工程基线有可用规范，task005 A10已限定接受；不依赖A05待接受部分，也不消费A06/A08/A09资料/知识规则。本轮不把A02文档核对冒充整份人工接受。

可观察结果：显式运行隔离PostgreSQL 17测试后，版本化迁移建立Account表，独立连接可读取已提交身份与状态；规范化键重复被数据库拒绝，失败迁移可诊断及重跑，测试进程结束不留临时数据库。关联TRACK-007a/b/c，仅Account基础字段/迁移子集。

不包含注册/登录/会话、首位或最后管理员裁决、账户删除、规范化算法、密码哈希服务、HTTP错误映射、Project及知识资产、生产目标或旧数据迁移。不是FR-001、完整Account聚合或整体B02验收。

## 2. 依据与入场基线

已读AGENTS、PROJECT_STATUS v1.60、设计索引、IMPLEMENTATION_ENTRY v1.6及B02工作清单；需求01 FR-001、领域02 v1.26 Account聚合、03-01账户页、04-01账户操作、05应用顺序、07 v1.13 §3/4/9、08 v1.9 §2、工程基线00-01 §5。

| 规范子条目 | 本轮落实及所有者 |
| --- | --- |
| 07 §3身份UUID、不透明revision、UTC时间；Account最小事实 | adapters.account SQLAlchemy元数据；账号身份、原始显示字段、规范化键、hash、enabled/admin、修订、时间。 |
| 07 §3登录标识唯一；04-01注册重复冲突 | username_key/email_key各自非空唯一，使用C精确比较；物理拒绝与约束名可诊断。规范化及跨用户名/邮箱的歧义解析留注册切片，不自行规定大小写规则。 |
| 08 §2/FR-001密码不明文保存 | 只有password_hash列，无原密码或会话token列；测试用合成hash占位。数据库Text不能判断字符串是否真实hash，真实哈希及拒绝明文输入须后续认证应用验证，本轮不宣称密码安全端到端完成。 |
| 07版本化迁移；00-01 §5/AGENTS隔离 | 唯一Alembic链、真实PG17、显式独立实例/库/角色、连接后核验运行标识、内部commit与物理清理；不读取业务连接。 |

入场[200文件快照](../docs/workorders/evidence/task015_b02_2026-10-25/before/source-manifest.json)及同目录source.tar.gz包括所有既有未提交/未跟踪产物；HEAD 7ba2a2c638500eaa43f2137d16a6a0686b663630。此前空迁移链、integration明确拒绝；未恢复旧SQL或旧数据。

## 3. 修改落点与工程选择

- `backend/src/rpb/adapters/account.py`：存储元数据，API DTO不充当ORM对象；无应用接入、无create_all调用。
- `backend/migrations/versions/0001_account.py`：冻结首版DDL；不导入可变模型；空表可降级，有数据拒绝而保留版本及数据。
- `backend/migrations/env.py`：只消费显式Connection和运行ID，校验库/角色/标识/非管理员；无从环境创建连接的回退。
- `scripts/run_storage_tests.py`：临时PG17集群、SCRAM、0700根/0600凭据、无TCP监听；父夹具建库，子测试只获本次非管理员角色；停止失败保留目录供诊断。
- `scripts/engineering.py`、`backend/pyproject.toml`、conftest：默认无库检查与显式集成分开；缺目标失败；README记录适用命令。
- 集成测试、任务及状态：逐场景证据，保留所有原有骨架拒绝/无存储测试。

Account可变对象的revision由未来写入者在更新时提供新值；本轮测试其持久性，不宣称已实现CAS/不可复用历史。不可变知识修订和Project复合归属对本表不适用，仍由后续B02切片负责。enabled/is_admin无自动默认，物理存储不代替首位管理员治理。未建立未消费的Repository/UoW抽象。

技术参考：[PostgreSQL initdb](https://www.postgresql.org/docs/17/app-initdb.html)、[Alembic显式共享连接](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands)；本项目采用版本化迁移，不采用create_all初始化。

## 4. 验收规格与需求追踪

测试路径统一为`backend/tests/integration/test_account_storage.py`，函数前缀`test_acNN_`对应下表；真实事务、约束及锁，不用SQLite/mock替代。

| 场景/规则 | 动作与可观察结果 | 禁止副作用/屏障 | 证据 |
| --- | --- | --- | --- |
| AC01 迁移与索引一致 | 从空库升级，metadata差异为空；重复升级保留已提交数据和revision head；核对列与检查约束 | 不重复建表、不丢数据、不加明文密码列 | integration日志 |
| AC02 最小事实持久化 | 服务端UUID/修订/UTC；commit后独立连接读更新状态/新修订/时间/合成hash | 不改变创建时间及身份 | 同上 |
| AC03 登录键唯一/事务 | 分别重复username_key/email_key，SQLSTATE23505及对应具名约束；同事务先写的其他行回滚 | 只留原先已提交行 | 同上 |
| AC04 必需键/hash | 键/hash的null和空字符串拒绝；其他必需字段显式null拒绝，无持久行 | 无部分提交 | 同上 |
| AC05 唯一性并发 | 两连接同键；观察pg_blocking_pids确定等待胜者事务后commit；败者23505 | 每种键只产生一行；8秒锁超时防挂起 | 同上 |
| AC06 降级保护 | 有数据拒绝，版本及行保持；空表down/up成功；真实未提交writer与降级争锁，writer提交后降级拒绝且行保留 | 不自动删账号数据 | 同上 |
| AC07 故障恢复 | CREATE之后故障注入，表与版本回滚，再upgrade成功 | 不留半迁移 | 同上 |
| AC08 错误运行标识 | 不匹配ID时拒绝DDL，原表/版本保持；核对角色无super/createDB/createRole | 不误迁移非本轮库 | 同上 |
| AC11 子测试凭据边界 | `test_fixture_cleanup.py`断言管理员密码文件已删除，descriptor仅测试凭据；测试密码不能登录fixture_admin | 不向子测试交付管理员凭据 | integration-final日志 |
| AC10 测试失败清理 | `test_fixture_cleanup.py`在真实建库后模拟子测试退出9/超时，两次均停止进程并移除根目录 | 内部建库commit不逃逸清理 | integration日志 |
| AC09 原骨架受影响边界 | 原test_startup及test_skeleton_requirements保留；默认integration及ambient DATABASE_URL拒绝且无连接；API/Worker保持无DB | 不借存储切片接入业务服务 | backend日志 |

未覆盖：规范化算法及登录歧义、哈希实现、权限、首位管理员并发、CAS、Session、Project归属、不可变修订、端到端；均不在本轮存储规格，不关闭对应项目需求。数据库唯一索引不证明注册完整行为。

## 5. 自验及证据

证据根：`docs/workorders/evidence/task015_b02_2026-10-25/`。当前执行证据：

| 命令（仓库根） | 实际结果/证据 |
| --- | --- |
| `python3 scripts/engineering.py integration --postgres-bin /opt/homebrew/opt/postgresql@17/bin` | [integration.log](../docs/workorders/evidence/task015_b02_2026-10-25/integration.log)：PG17.11，初次17通过；唯一库rpb_test_fddddd362eb54f8e9eb7479422fdc70b，server_stopped/root_removed=true。 |
| `python3 scripts/engineering.py check` | [check.log](../docs/workorders/evidence/task015_b02_2026-10-25/check.log)：ruff/format、mypy、82后端、66契约、3前端全部通过。 |
| `python3 scripts/engineering.py build` | [build.log](../docs/workorders/evidence/task015_b02_2026-10-25/build.log)：后端wheel/sdist与前端构建通过。 |
| `python3 scripts/engineering.py migration-history` | 输出单head：base → 0001_account。 |

Node命令使用既有临时Node24工具PATH；后端使用uv --locked及Python3.14。首次ruff发现长行已格式化/修复；最终门禁已通过，修复后的最终复验及流程映射见第9节。

本机原只有PG16且Docker daemon不可用；为符合已定PG17基线执行`brew install postgresql@17`，得到17.11；Homebrew同时更新依赖、初始化默认`/opt/homebrew/var/postgresql@17`但未启动服务，本轮不使用它，也未切换已链接PG16。集成夹具只使用`/tmp/rpb-db-*`新实例；真实测试凭据均为临时生成，无邮件/LLM/Provider请求。安装会留下二进制和Homebrew默认空集群，不将它们误称为测试残留或自行删除。

## 6. 人工审核

无新增业务政策待决；请求接受仅本单AC01–11限定存储交付。审核方式：运行README显式integration命令，观察唯一键/故障断言及最后`server_stopped/root_removed`；检查迁移env与夹具边界，确认范围没有被写成账户业务验收。

设计：已限定；代码：已实现；自动验证：初次与修复复验通过；独立审查：R01/R02已修复并复审通过；人工接受：未收到。原流程阶段已按第9节新流程映射，S1–S7工程已收口，提交用户明确要求的M-B02-01限定验收。

## 7. 单一交付报告

本单为单一审核包。本轮14文件增改包含Account元数据、迁移与安全入口、真实存储测试及任务/状态/命令文档；准确[变更补丁](../docs/workorders/evidence/task015_b02_2026-10-25/changes.patch)、[最终快照](../docs/workorders/evidence/task015_b02_2026-10-25/delivery/source-manifest.json)及第9节复审证据可重定位。已知限制见第1/4/5节；设计、代码和自动验证已完成限定范围，工程已收口，人工接受未收到。

## 8. 入场流程v1.6历史检查点（保留记录，现状见第9节）

| 阶段 | 状态 | 依据 |
| --- | --- | --- |
| S1 | 已完成 | 用户授权B02首片；入场200文件快照；选择Account基础持久事实 |
| S2 | 进行中 | 实现/真实PG初次15用例通过，待最终回归和证据 |
| S3 | 待开始 | 必须独立subagent只读审查 |
| S4 | 待开始 | 等待具体审核包，不代填人工接受 |
| S5–S7 | 待开始 | 依赖S4接受 |

恢复时核对快照和任务记录，不将当前大量未提交内容视为本轮全部变更；只授权本任务，未授权后续backlog。


## 9. 流程v1.7恢复、独立审查与最终记录

2026-10-25比对s3-input与before时发现并行流程修改：AGENTS v1.2、skill v1.1、实施入口v1.7、任务模板及workflow_autonomy记录。已重新读取；这些并行修改不计本轮B02成果且完整保留。第8节保留初始v1.6阶段记录；旧S1/S2按证据复用，旧S3继续独立审查；旧S4人工节点改记M-B02-01；旧S5覆盖→新S4，旧S6简化→新S5，旧S7复验拆新S6/S7，均不得倒填完成。

M-B02-01：用户明确要求本轮“再提交我审核”，据此保留限定验收点，范围AC01–11；触发为本轮工程收口。它不是完整注册/Project业务里程碑，不授权下一片；人工接受尚未收到，无业务政策D待决。完整账户注册及Project创建业务验收仍留后续另行授权。

独立审查者`/root/b02_review`只读检查固定[s3-input](../docs/workorders/evidence/task015_b02_2026-10-25/s3-input/source-manifest.json)，manifest SHA256 `071ea5f13fa7dc72c7339c2146020b3ba9b042d8b10f77210c7540695a98ee91`。自行以真实PG17复现两项P2：

| 问题/依据 | 复现证据 | 修复及回归 |
| --- | --- | --- |
| R01 降级检查/删除竞态；AC06不删已提交账号 | 检查空后另一连接INSERT commit，原DROP删除表；审查run_id rpb_test_82d1813e052b46b2a020490893efe9c1清理true | 迁移先ACCESS EXCLUSIVE锁表，再在同事务检查及DROP；新增AC06真实writer/downgrade阻塞交错回归。 |
| R02 管理员初始化凭据可被子测试读；00-01 §5测试仅获本次角色 | 子测试读root/admin-password并成功只读查询superuser；审查run_id rpb_test_394dfd1815a140f79a01335eb99cb215清理true，未输出密码 | initdb后立即unlink；子测试启动前复查；新增AC11文件不可见/descriptor边界/测试密码不能登录管理员。 |

初次integration 17通过未发现以上缺陷，不覆盖最终结论。修复后[integration-final.log](../docs/workorders/evidence/task015_b02_2026-10-25/integration-final.log)记录27项真实存储检查及清理。另用[反例脚本](../docs/workorders/evidence/task015_b02_2026-10-25/verify_regressions.py)在临时源码副本恢复两个缺陷，[mutation日志](../docs/workorders/evidence/task015_b02_2026-10-25/regression-mutations.log)必须识别两项回归失败，工作树不变、临时实例仍清理；证明新增断言能发现原缺陷。

[干净安装日志](../docs/workorders/evidence/task015_b02_2026-10-25/clean-install.log)通过临时副本安装/构建、锁拒绝、默认integration拒绝、已安装wheel的API/Worker启停与清理。此入口没有数据库测试，不冒充存储证据；真实存储另见上项。

| 新阶段 | 当前状态/证据 |
| --- | --- |
| S1–S2 | 完成；入场、实现、自验及修复证据如上 |
| S3 | 完成；复审固定s3-fix，R01/R02闭合，见下方独立结论 |
| S4 覆盖复核 | 完成；逐AC01–11对照测试断言和最终27项结果；成功、拒绝、故障、重复、锁交错、必需字段、内部commit及清理均有证据。原82项骨架保护保留；权限/版本绑定/人工正文对本片无应用入口，范围外需求明确列存，没有以排除项替代范围内验证。 |
| S5 简化 | 完成，无需修改。冻结迁移和可变元数据的字段重复保留以保证历史DDL稳定；未引入未使用Repository/UoW，不合并关键并发/故障断言。 |
| S6 最终复验 | 完成；最终check、27项集成及独立重跑通过；源码与s3-fix一致，构建/干净安装证据对应未变化的包源码可复用；只追加记录，文档引用/版本/差异检查通过。 |
| S7 工程收口 | 完成；保存delivery快照与receipt、同步项目状态。M-B02-01待人工验收；本轮授权队列耗尽，不启动其他B02片或B03。 |


独立复审结论（2026-10-25，`/root/b02_review`）：复审通过，R01/R02闭合，本轮限定范围无剩余阻断问题。审查者核对两项反例日志，自行运行27项集成测试通过；run_id `rpb_test_9752ca3652eb4e42a9531104453ebf29`，server_stopped/root_removed=true。复审manifest SHA256 `bee6a8d5d3d88917387509631463e85bc7d351431386b94ef781d4a1a8f6ab01`；执行前后工作树匹配该基线。审查限制：只验证夹具默认事务隔离级别，未验证其他部署环境/隔离级别；不代表注册、规范化、哈希服务、治理、CAS、Project隔离或生产迁移完成。

[最终check](../docs/workorders/evidence/task015_b02_2026-10-25/check-final.log)再次通过ruff/format、mypy、82后端、66契约、3前端；最终存储27项通过且清理成功。反例日志的2失败/1 teardown错误为故意恢复数据丢失/凭据暴露缺陷的预期结果，不是最终产物失败；整实例仍成功清理。未重跑无关浏览器端到端，未将骨架浏览器结果作为Account业务验收。

[限定文档检查](../docs/workorders/evidence/task015_b02_2026-10-25/document-checks.json)及[复现脚本](../docs/workorders/evidence/task015_b02_2026-10-25/check_delivery.py)核验14个本轮文件、链接、版本日期及受审源码无漂移；并行流程修改单列保留，不计B02成果。最终快照含所有未提交/未跟踪源码，manifest摘要和复验信息保存在[receipt](../docs/workorders/evidence/task015_b02_2026-10-25/receipt.json)，避免自引用摘要。

## 10. 2026-10-25 真实用户限定接受（后续记录）

用户在 local 聊天 `01a16eab-7cfa-7542-9bb5-b35cf70b45fb` 的消息 `01a1710b-4928-7a31-b70b-68ca1b2a2922` 明确表示：“接受 M-B02-01 的限定交付，自动新建任务继续推进项目，按照 project-delivery 流程自由迭代，直到遇到需要我决策或下一个里程碑再停下。”本轮已通过 read_thread 核实原文。

M-B02-01 已限定接受本单 AC01–11 的 Account基础物理模型、首条迁移及隔离PG17测试，绑定第9节 delivery/receipt，manifest SHA256 `e6ce09609b86c046b5bee32a6f0dc26e6888ff610ba9013e25f91e9b6037205e`。不扩大为注册登录、完整Account业务、Project持久化、生产迁移或整个B02。前文待接受/授权耗尽为当时历史记录，由本节更新当前状态。

入场核对：Account代码、迁移、测试和执行入口无漂移；四份后续整理文档（项目状态、设计索引、任务地图、task013规划）变化保留，详见[差异](../docs/workorders/evidence/task016_project_storage_2026-10-25/acceptance-drift.patch)。这些变化不修改AC01–11的规则或实现，不迁移旧接受到其他业务。后续批次及检查点见[task016](016-project-storage.md)。
