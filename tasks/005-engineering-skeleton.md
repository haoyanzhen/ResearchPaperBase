# Task 005：第一批可验证工程骨架

文档版本：v1.3
更新日期：2026-10-24

## 1. 目标与授权

用户于2026-10-22授权：按现有工程基线搭建第一批骨架，完成安装、启动、检查和构建验证，保留已有未提交修改并提交审核。

可观察结果：审核者能按README安装，在本机启动API、显式空闲Worker与前端预览，运行统一检查和构建；未接入的业务能力明确不可用。

范围：B08工程入口、A10本任务限定验收、模块包边界、进程配置、健康探针、空迁移链与失败保护、前端基础导航及预览。关联ARC-01/08/09/10、OPS-01/03的工程子集；不关闭这些用例的完整业务范围。

不含账号/Project业务实现、持久任务、业务迁移与UoW、文件/密钥适配器、真实PostgreSQL测试夹具、Graph-RAG、模型接入、生产部署。A04–A09、H01–H03维持原边界；本批不消费尚缺公共错误模型的业务接口，不需要先关闭它们。

2026-10-24恢复授权原文：“继续按 project-delivery 流程推进 A10，核对已有任务单和交付范围，完成本轮交付、自验及独立审查，再提交我审核。”A10按切片实例化；本轮复用本单SK-01–09已有工程行为，不新建重复任务、不把它扩成全量P0验收设计。核对当前代码（含10月23日精简修改），补当前验收规格/执行证据与S3审查后提交S4。既有历史结果原样保留；本轮结果以第7–8节及新审核包为准。

## 2. 当前依据与精确基线

依据：AGENTS v1.1；00-01 v1.0 §2/3/5/6；00分层与05-01模块所有权；03 v1.25 §2/3的基础导航和单一主体原则；09工程隔离、证据与OPS要求；10 v1.7 §2.1/7。设计中完整Project Workspace需真实对象，本批只提供未连接业务数据的全局预览，不模拟Project绑定。

[初始清单](../docs/workorders/evidence/skeleton_2026-10-22/initial.json)保存HEAD、初始状态和文件摘要；[初始diff](../docs/workorders/evidence/skeleton_2026-10-22/initial.patch)与[初始内容快照](../docs/workorders/evidence/skeleton_2026-10-22/initial-files.tar.gz)包含已有未提交/未跟踪文件。修改前校验快照逐文件摘要。首轮交付与构建摘要见[最终清单](../docs/workorders/evidence/skeleton_2026-10-22/final.json)，本次相对初始工作区的差异见[交付diff](../docs/workorders/evidence/skeleton_2026-10-22/delivery.patch)。它们不是人工批准记录。

初始仅有设计与契约工具，Python3.14.4已安装，系统Node25不符合基线，Docker daemon不可用。通过独立临时工具目录安装Node24/npm11，未改全局Node、Docker服务、业务配置或旧数据。

## 3. 修改落点与工程取舍

| 落点 | 职责和限制 |
| --- | --- |
| backend/src/rpb | 六个业务模块的domain/application包边界，bootstrap/API/Execution/Knowledge/Agent/Adapters包；业务包仅明确保留位置，无通用假实现 |
| backend/src/rpb/bootstrap | 类型化进程配置、API和Worker装配；仅本机development/test；无数据库/模型隐式回退 |
| backend/src/rpb/api/health.py | 无对象信息的live=200、ready=503；无业务路由、API文档或伪造P0 OpenAPI |
| backend/migrations | 单一Alembic链入口，无业务revision；执行迁移立即拒绝，不读业务连接配置 |
| frontend/src | 单一全局导航与main，Projects/设置预览；未实现写操作disabled，不显示虚构账号或管理员入口 |
| frontend/e2e | 对构建后的预览进行真实浏览器检查；不是业务端到端验收 |
| scripts/engineering.py | install/check/build/api/worker/ui/e2e/integration/migration-history统一入口 |
| scripts/verify_skeleton_delivery.py | 临时干净副本安装构建、锁缺失/漂移反例、隔离入口拒绝、安装wheel的网络探针和停机 |
| scripts/check_architecture.py | 静态导入图及违规负例；约束Domain纯Python、Application不依赖ORM/HTTP、具体适配器仅装配处选择、禁止archive |
| README与现行入口 | 仅同步工程命令、实际范围和证据，不变更业务规则或产品分期 |

Worker采用显式 `--idle`，默认执行模式拒绝，避免把空循环宣称持久队列。API不因存活而宣称业务就绪；真实依赖启用后须替换ready逻辑并增加对应成功/失败测试。迁移入口采用硬拒绝，真实隔离目标/迁移协议未交付前不能误运行。没有为了骨架提前定义泛化Repository或任意JSON业务端口。

前端浏览器用例放在frontend/e2e，复用同一Node锁文件，工程基线同步路径。依赖补丁锁定于uv.lock/package-lock.json；构建后端使用精确Hatchling版本，wheel验证从uv.lock导出运行依赖后安装，不采用可编辑源码代替产物验证。

本轮覆盖补齐依据当前00-01 v1.1及本任务工程范围；完整审核包、当前源码快照与执行证据见[覆盖修复记录](../docs/workorders/task005_coverage_closure_2026-10-22.md)。入场已有部分R01–R04修复，保留并复验；并行任务的契约改动不归入本任务修改。

## 4. 验收规格与需求追踪

以下编号仅为本任务的工程子场景，不宣称覆盖对应ARC/OPS的全量业务规则。

原覆盖修复证据目录为 `docs/workorders/evidence/task005_coverage_2026-10-22/`；下表保留历史追踪，2026-10-24当前运行证据及完整测试路径见第4.1节和本轮审核包。

| 需求与场景 | 输入、预期和禁止副作用 | 可执行测试 / 当前证据 |
| --- | --- | --- |
| SK-01 / OPS-01 | 干净安装构建成功；前后端锁漂移拒绝且锁字节不变；分别缺任一锁时，在启动安装工具前拒绝，不生成锁、不修改另一锁 | verify_skeleton_delivery.py；test_missing_lock_refuses_before_install_and_preserves_files；check.txt、clean-delivery.txt、build.txt |
| SK-02 / ARC-01 | 禁止Domain外层、Application HTTP/ORM/具体适配器/跨模块私有领域、Knowledge反向依赖、API绕过应用、archive和动态导入；包根/父包from/成员导入均校验；公开ports合法，ports_private拒绝 | test_boundaries.py全部测试（含包根回归和HTTP/ORM矩阵）；check.txt |
| SK-03 / ARC-08、OPS-01 | 默认配置无隐式存储；1024/65535接受，0/1023/65536/非数字拒绝；外部绑定、production、未知RPB拒绝；API和Worker错误退出且stdout/stderr均不泄漏 | test_config_*、test_invalid_or_unimplemented_configuration_refused、test_process_rejects_configuration_without_leaking_values；check.txt |
| SK-04 / ARC-09/10 | live精确200及alive；ready精确503及not_ready；业务GET/POST、文档路由404；安装wheel网络探针与SIGTERM；无数据库连接 | test_probes_and_no_business_routes、test_live_201_mutation_fails_application_contract、test_wheel_network_probe_requires_exact_200、test_api_probes_do_not_connect_with_ambient_business_configuration；check.txt、clean-delivery.txt |
| SK-05 / ARC-09 | 默认拒绝；显式idle不就绪、不连接存储；SIGTERM/SIGINT正常退出；无启动输出或半行输出在期限内失败并回收；提前退出可诊断 | test_worker_refuses_task_execution、test_worker_idle_lifecycle、test_worker_missing_startup_signal_times_out_and_is_reaped、test_worker_exit_before_handshake_is_reaped、test_idle_worker_has_no_storage_activity；check.txt |
| SK-06 / OPS-01 | 缺配置及合成业务DATABASE_URL两种情形，migration/integration均拒绝且连接调用次数为0，不泄漏值；迁移history为空 | test_unavailable_storage_refuses_without_connection、test_migration_refuses_even_with_business_configuration；check.txt、clean-delivery.txt、migration-history.txt |
| SK-07 / 03基础导航 | 两页均明确未连接、未实现；创建/保存禁用且点击无fetch；无账号/项目记录控件、业务链接或管理员入口；唯一main；可返回Projects | App.test.tsx三项；浏览器同时检查fetch/xhr及非GET请求为空；check.txt、e2e.txt |
| SK-08 / 03窄屏与键盘子集 | 1280/390分别检查Projects和设置无横向溢出；Tab到跳转入口且Enter聚焦main；导航往返；无浏览器异常/业务请求，四张截图 | shell.spec.ts两项，每项覆盖两页；e2e.txt、shell-{1280,390}-{projects,settings}.png |
| SK-09 / OPS-03 | 保留既有变更；新完整快照包括空文件和二进制，文件集合及SHA一致；缺失/篡改/额外文件拒绝；历史基线不覆盖 | test_delivery_snapshot.py；initial/source-manifest.json、baseline/source-manifest.json、delivery.patch、review-manifest.json、snapshot-verification.txt |
| 受影响既有契约工具 | 对当前共享工作区执行结构检查与全部契约回归；并行契约修改保留，不归为task005实现；未提供旧基线，不宣称兼容或运行授权验证 | scripts/tests、check_api_contracts.py；check.txt及verification-inputs.json |

无业务写路径，业务并发、去重、权限、版本绑定和人工内容保护没有执行入口，本批不以空断言冒充覆盖；仍由TRACK-004/007/008/012/018/019/021跟踪。真实PostgreSQL commit/race验证需后续切片，当前integration明确非零退出。架构检查只分析静态Python导入，不证明未来运行时写入所有权。

### 4.1 A10 当前切片的执行条件与观察（2026-10-24）

当前依据为00-01 v1.2 §3/5/6、09 v1.22 ARC-01/08/09/10及工程隔离、10 v1.8 §2.1/7、03基础Shell规范。本轮仅取“可安装、启动、验证且未实现能力明确不可用”的工程子集；不声称任何完整FR业务已验收。配置所有者为bootstrap；API只有health读端口；Worker无持久写权；UI只改本地页面状态。ARC-02身份与Project隔离及业务存储、账号授权、版本绑定、人工内容与业务竞争无入口，明确不适用本工程切片，相关TRACK继续开放。

| 场景 | 前置/动作与故障点 | 可执行定位（仓库相对路径） | 观察、禁止副作用与清理 |
| --- | --- | --- | --- |
| SK-01 | 临时干净副本；安装构建，分别改后端版本/前端依赖制造锁漂移；分别移去一个锁 | scripts/verify_skeleton_delivery.py::main；backend/tests/unit/test_skeleton_requirements.py::test_missing_lock_refuses_before_install_and_preserves_files | 成功产出wheel/静态文件；反例非零且锁字节不变、缺锁不启动安装。TemporaryDirectory只清本次副本；依赖缓存允许保留。 |
| SK-02 | 参数化非法/合法导入源码，包括包根、父包、私有近似名与动态导入 | backend/tests/architecture/test_boundaries.py 全部用例；scripts/check_architecture.py | 实际源码导入图通过；负例报违规、公开ports正例通过。只AST静态分析，不等于运行写入所有权或任意Python动态行为防护。 |
| SK-03 | 清除测试子进程RPB配置，按第4节边界设置合成值；API/Worker分别启动 | backend/tests/unit/test_startup.py::test_config_has_no_storage_or_provider_fallback、test_config_valid_boundaries、test_invalid_or_unimplemented_configuration_refused、test_process_rejects_configuration_without_leaking_values、test_app_factory_rejects_invalid_configuration | 配置合法或精确拒绝；CLI退出2、固定脱敏消息，无值泄漏；10秒子进程期限。无持久写入。 |
| SK-04 | TestClient及已安装wheel实际本地HTTP；注入live=201负例；合成DATABASE_URL+连接拒绝spy | backend/tests/unit/test_startup.py::test_probes_and_no_business_routes；test_review_regressions.py两项探针回归；test_skeleton_requirements.py::test_api_probes_do_not_connect_with_ambient_business_configuration；scripts/verify_skeleton_delivery.py | live=200/alive、ready=503/not_ready；业务/文档404；201必须被测试识别。真实wheel SIGTERM后shutdown complete且回收进程；连接spy为0。 |
| SK-05 | 默认执行拒绝；idle进程先收到启动握手再发SIGTERM/SIGINT；独立子进程模拟无输出/半行/提前退出 | backend/tests/unit/test_startup.py 的worker五组场景；test_skeleton_requirements.py::test_idle_worker_has_no_storage_activity；process_support.py | 默认退出2，idle明确not ready并正常停；故障等待有界，最终poll非None。握手控制进程先后，不虚构业务锁竞争。连接spy测试不替代真实数据库测试。 |
| SK-06 | 缺连接与合成DATABASE_URL；迁移/integration入口执行，连接函数全部拒绝；查询迁移history | backend/tests/unit/test_skeleton_requirements.py::test_unavailable_storage_refuses_without_connection；test_startup.py::test_migration_refuses_even_with_business_configuration；scripts/engineering.py migration-history | 明确非零且不回显秘密，连接调用0，history空。拒绝是预期成功断言，不代表迁移能力已验收；无需建/清业务库。 |
| SK-07 | 渲染Projects/设置，点击禁用动作及本地导航 | frontend/src/App.test.tsx三项 | 唯一main、不可写、无fetch/伪业务记录或管理员入口；测试卸载及恢复spy。无业务账号/数据夹具。 |
| SK-08 | 已构建前端预览，1280/390；Tab/Enter后两页往返 | frontend/e2e/shell.spec.ts两项 | main聚焦、无溢出/异常、无fetch/xhr/websocket及非GET；四张截图仅工程Shell。Playwright管理本次预览进程；不停止用户其他服务。 |
| SK-09 | 临时源码含空/二进制/文本；独立篡改manifest为missing/tampered/extra | backend/tests/unit/test_delivery_snapshot.py；scripts/delivery_snapshot.py | 重构文件集合/字节一致，三反例拒绝；旧输出目录拒绝覆盖，仅写pytest管理的tmp_path，按pytest保留策略回收，不宣称退出即时删除。本轮完整快照另核对实际工作树摘要。 |

表内省略目录的test_*.py均位于backend/tests/unit/。对应第4节所有SK需求及受影响机器契约回归；本轮完整命令/结果集中在第7节报告。业务数据并发、授权、版本绑定、内容保护及真实隔离PostgreSQL尚无测试执行入口，不能按“骨架不写入”关闭它们。A04–A09本轮不新增消费；A05未记录接受不会阻塞只含health和预览的本切片，也不能借本切片接受A05。

## 5. 执行证据与复现

### 5.1 首轮历史执行记录

以下为首轮结果，当前修复后结果以5.2为准。

证据目录：[skeleton_2026-10-22](../docs/workorders/evidence/skeleton_2026-10-22)。命令在仓库根执行，Node24在PATH；本机临时工具位于 `/tmp/rpb-skeleton-tools/node_modules/.bin`，不是跨机器前置路径。跨机器按README选择运行时。

| 命令 | 实际结果与范围 |
| --- | --- |
| python3 scripts/engineering.py install | 通过；本机环境按锁安装，契约独立环境按原requirements安装 |
| python3 scripts/engineering.py check | 通过；Ruff/格式/Mypy，26项后端、15项契约、2项前端测试；静态契约通过，未传旧审查基线，因此不宣称历史兼容检查 |
| python3 scripts/engineering.py build | 通过；后端sdist/wheel、前端静态产物 |
| python3 scripts/verify_skeleton_delivery.py | 通过；新临时环境安装构建、锁缺失/漂移拒绝、integration拒绝、锁定依赖的wheel安装及实际API启停；临时目录已清理 |
| python3 scripts/engineering.py migration-history | 通过；空链，无业务迁移执行 |
| python3 scripts/engineering.py e2e | 通过；2项真实Chromium浏览器用例及桌面/窄屏截图，人工式视觉检查未见布局问题；仅工程预览范围 |

开发中发现并修复：Testing Library类型不接受Playwright式exact选项；独立契约安装须解析requirements依赖；脚本格式配置统一；锁负例须实际触发锁不一致而非离线缓存失败。Uvicorn SIGTERM完成清理后可返回信号码，测试同时断言shutdown complete及允许的信号退出，不把正常信号当业务故障。修复后重跑当前检查；无删除必要反例或修改业务要求。

剩余非阻断警告：上游Starlette提示httpx TestClient适配器未来弃用；本次锁定组合仍通过真实进程测试，未屏蔽警告。契约工具原requirements的传递依赖未锁定，其本次准确版本见versions.txt；后续契约工具维护另行处理。浏览器下载由Playwright管理用户缓存，不属于业务服务访问。

### 5.2 本轮覆盖补齐与复验（2026-10-22）

用户明确授权修复全部已识别缺口并提交审核。当前统一check通过：75项后端、23项契约、3项前端；Ruff/格式/Mypy/TypeScript及契约结构检查通过。构建、干净副本安装构建与锁负例、安装wheel网络探针、空迁移链、2项真实浏览器用例均通过。契约测试数量包含并行任务新增用例，不代表本任务新增业务范围。

详细命令、输入摘要、产物、四张截图、反例和完整源码重构证据见[覆盖修复记录](../docs/workorders/task005_coverage_closure_2026-10-22.md)。原记录不改写；本轮无数据库或真实外部Provider访问。对实际交付自审后提交人工审核，未代填接受结论。

## 6. 决策、限制与人工审核

本批无待裁决业务变更。数据库、迁移、配置管理、账号、Project、持久Worker、解析、知识版本、Graph-RAG及生产恢复未实现；ready=503是预期限制，不能作为可部署业务系统。依赖下载访问公开软件仓库；无真实LLM、论文源、邮件、旧数据库或旧文件操作。

人工审核建议：先查看本轮覆盖修复记录，复现README命令并查看四张截图；抽查config拒绝路径、health就绪状态、worker默认拒绝、迁移保护、架构反例及锁漂移证据，再确认本批范围是否接受。后续业务切片另行授权，不由通过检查推定。

设计依据：已核对；骨架代码：已实现；自动验证：按第5节逐项记录；人工接受：**2026-10-24已获本轮SK-01–09限定接受**，基线及收口见第9节；此前各轮历史证据不倒填批准。

## 7. 本轮单一交付报告（2026-10-24）

[A10恢复审核包](../docs/workorders/task005_a10_review_2026-10-24.md)记录已有任务归属、精简修改承接、实际测试、独立审查和精确基线。本轮补验收交接，不把10月23日既有实现修改归为新增代码。旧报告与人工接受状态保留；当前审核以本次明确基线为准。

## 8. 顺序交付检查点

唯一队列为task005的A10工程子集，授权原文见第1/9节。S1–S7已完成（限定工程交付收口）：S1核对实际基线，S2验证通过，S3独立复审通过且C01/C02闭合，S4于2026-10-24获用户接受，S5逐SK复核无新增缺口，S6无需修改，S7文档/差异/快照复验通过。源码、测试、锁文件和机器契约与接受基线一致。原197文件入场及受审快照保留；本次仅更新任务单、审核包和项目状态的接受/执行记录，最终证据见审核包末节。

当前授权队列已完成；没有待决工程缺陷。其他业务切片、全项目A10、真实存储/权限/并发/版本/人工保护及Graph-RAG不在本次接受范围，仍由原任务和TRACK跟踪；下一任务须有明确授权。

## 9. 人工接受与S5–S7收口（2026-10-24）

用户原文：“接受 task005 本轮 A10 工程骨架限定交付，继续按 project-delivery 流程完成 S5–S7，更新任务单和项目状态。”接受范围为本轮SK-01–09工程骨架及A10验收交接，绑定delivery清单SHA256 `18d7332dc7ffe53faeb5de39e1898795bcd5ca2b8b5e0dbea735c5ae0d319075`（197文件）。恢复逐文件核验无漂移，原独立复审和82后端/58契约/3前端/2浏览器、构建/干净安装/wheel/空迁移链证据仍对应当前代码。

[S5–S7收口记录](../docs/workorders/task005_a10_review_2026-10-24.md#人工接受后的s5s7执行记录)逐项记录覆盖与简化结论，以及本轮文档/快照实际检查。没有代码、测试或规范语义变更，不重复全量工程测试和独立审查，也不因登记接受本身再次要求接受。设计规格、现有工程代码、限定自动验证及人工接受均已完成；业务核心实现与验收未完成。
