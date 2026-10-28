# Research Paper Base

文档版本：v1.19
更新日期：2026-10-26

面向深度检索与学术研究的工作空间项目，目标包含论文库构建、基于知识版本的研究对话和文献综述。

当前交付范围与验证结果见[项目状态](docs/PROJECT_STATUS.md)和[第一批骨架审核单](tasks/005-engineering-skeleton.md)。默认api/ui命令保留无库工程预览；注册登录和Project创建/本人读取已有独立本地演示入口，见下方M-P0-01。个人LLM和数据源连接测试已接入持久任务；知识构建尚未接入。

## 当前入口

- [项目进度](docs/PROJECT_STATUS.md)
- [每日项目整理规则](docs/NIGHTLY_MAINTENANCE.md)
- [现行设计索引](docs/design/README.md)
- [新核心设计与审核入口](docs/IMPLEMENTATION_ENTRY.md)
- [最小工程基线](docs/design/00-01_engineering_baseline.md)
- [A01–A03交付与基线记录](docs/workorders/a01_a03_design_closure_2026-10-21.md)
- [API 机器契约范围与验证命令](docs/design/04-03_machine_contract_governance.md)
- [内部模块与执行契约](docs/design/05-01_internal_module_contracts.md)
- [安全与交付设计细化记录](docs/workorders/security_delivery_refinement_2026-10-19.md)
- [数据、测试与文档清理记录](docs/workorders/data_test_design_cleanup_2026-10-19.md)
- [历史设计归档](docs/archive/design_retirement_2026-10-19/README.md)
- [历史核心重写计划（不作为现行执行单）](docs/proposals/core_rewrite_plan_2026-10-16.md)
- [独立审查与拆分结果](docs/proposals/reuse_independent_review_2026-10-16.md)
- [或许有用的逻辑存档](archive/maybe_useful/README.md)
- [实际清理记录](docs/workorders/legacy_cleanup_execution_2026-10-16.md)
- [逐文件处置清单](docs/workorders/legacy_cleanup_manifest_2026-10-16.json)
- [文件职责索引](docs/file_map.md)

## 重建边界

`archive/maybe_useful/` 仅为独立候选片段与规则材料，不是新应用。新实现采用其中内容前应按新契约核验，不恢复旧接口、旧状态机或旧依赖全集。

`docs/design/` 保留现行设计；旧07 SQL草案已删除，可执行数据结构由后续迁移维护。07为持久化协议，08为安全契约，09为架构/模块及SEC/OPS测试用例，10为运行与交付约束；未决政策在08/10单列。历史报告及工作单用于追溯，不是当前功能验收证据。既有 Git 历史未改写。

工程安装与验证入口如下；业务实现按独立切片推进。

2026-10-19：新增独立 API 契约产物及检查工具。其依赖、运行命令和覆盖缺项见上述机器契约入口；这些检查不启动应用，不替代数据库或端到端验收。

本次修订 v1.2（2026-10-19）：同步07/09/10及退役归档入口，未启动应用实现。

本次修订 v1.3（2026-10-19）：同步安全与交付设计入口，未启动应用实现。

本次修订 v1.4（2026-10-21）：建立当前实施/审核入口；历史重写计划仅用于追溯，未开始编码或环境安装。


## 本地工程入口

已验证环境：Python 3.14.4、uv 0.11.7、Node 24.22.1、npm 11.21.1。
先用自己的运行时管理器选择 `backend/.python-version` 和 `frontend/.node-version` 对应版本；不使用系统 Node 25。命令在仓库根执行。

```sh
python3 scripts/engineering.py install
python3 scripts/engineering.py check
python3 scripts/engineering.py build
python3 scripts/verify_skeleton_delivery.py
```

安装使用 `backend/uv.lock` 的 locked 模式与前端 `npm ci`。契约检查保持独立环境及原 `contracts/requirements.txt`，其间接依赖尚未单独锁定；本次环境版本见审核证据。安装需要依赖仓库网络，测试与启动不调用真实 LLM、论文源或邮件。

分别在三个终端运行，按 Ctrl+C 停止：

```sh
python3 scripts/engineering.py api     # http://127.0.0.1:8000
python3 scripts/engineering.py worker  # 显式 --idle，无任务领取能力
python3 scripts/engineering.py ui      # http://127.0.0.1:5173
```

API `/health/live` 返回200；`/health/ready` 固定503，表示骨架尚无业务就绪能力。没有业务API、会话或管理员账号，不连接数据库或文件存储。类型化进程配置唯一来源是 `backend/src/rpb/bootstrap/config.py`：仅进程环境变量 `RPB_ENVIRONMENT`（development/test）、`RPB_HOST`（仅127.0.0.1）、`RPB_PORT`（1024–65535）受支持，默认值见源码；变更需重启，不读取.env。未知RPB变量或生产模式拒绝启动，错误不回显值。

浏览器验证（先完成build）：

```sh
cd frontend
npm exec playwright install chromium
cd ..
python3 scripts/engineering.py e2e
```

浏览器测试针对构建产物，覆盖390/1280宽度、本地导航、键盘入口、无横向溢出和无写请求；不代表业务端到端验收。截图在 `frontend/test-results/`。

`python3 scripts/engineering.py migration-history` 可查看 `0001_account → 0002_project → 0003_auth_sessions → 0004_project_commands → 0005_project_lifecycle → 0006_account_profile → 0007_llm_configuration → 0008_source_configuration → 0009_account_governance → 0010_system_llm → 0011_system_sources` 单链。执行真实存储测试：

```bash
python3 scripts/engineering.py integration --postgres-bin /opt/homebrew/opt/postgresql@17/bin
```

`--postgres-bin` 必须显式指向 PostgreSQL 17 的二进制目录（其他机器替换路径）。命令创建仅 Unix socket 可达的临时实例、独立测试库和非管理员角色；测试内部提交保留到本轮结束，随后停止进程并删除该实例。未传目标的 `integration` 和直接 `alembic upgrade head` 仍拒绝，忽略业务 DATABASE_URL；没有生产迁移入口。默认 `check` 执行无数据库测试，真实存储测试须另行运行且缺目标为失败，不是跳过。[task015](tasks/015-account-storage-migration.md)记录最初Account存储范围；后续[task017](tasks/017-account-authentication.md)/[task018](tasks/018-project-create-runtime.md)提供显式装配的注册登录、当前会话及Project创建/本人读取；完整Project生命周期与生产迁移未交付；当前账号治理见下节。构建产物在 `backend/dist/` 和 `frontend/dist/`，不隐式迁移。

本次修订（2026-10-22）：增加首批工程安装、启停、检查和构建入口；审核结论由人工记录。


## 工程交付快照

审核R01–R04修复见[任务007](tasks/007-skeleton-review-fixes.md)。完整源码快照包含空文件、二进制和当前未提交源码；不依赖文本diff恢复文件集合，不包含证据目录以避免递归。只接受新输出目录，不覆盖历史基线：

```sh
python3 scripts/delivery_snapshot.py create --directory docs/workorders/evidence/new-delivery-baseline
python3 scripts/delivery_snapshot.py verify --directory docs/workorders/evidence/new-delivery-baseline
```

验证检查归档文件集合和每份内容摘要；修改源码后须生成新基线，旧交付记录保留。创建命令中的路径是新基线示例；本次实际基线位置见任务007。


## 本地业务闭环与 Project Hub

需先按以上命令安装锁定依赖、构建前端。真实浏览器验证使用Python Playwright（dev依赖）：

```bash
uv run --project backend playwright install chromium
python3 scripts/engineering.py integration --postgres-bin /opt/homebrew/opt/postgresql@17/bin
python3 scripts/engineering.py demo --postgres-bin /opt/homebrew/opt/postgresql@17/bin
```

最后一条在 `http://127.0.0.1:8765/workspace` 提供独立临时演示，最长30分钟；Ctrl-C退出，API停止后清理本轮数据库。不是持久开发库，不会保存演示输入；不读取DATABASE_URL，不连接Homebrew默认业务集群。端口被占用时启动失败并清理，不终止其他进程。`demo`需要现有frontend/dist；修改前端后先build，不自动使用旧源码冒充新产物。集成测试同样消费构建产物，执行前应先build。

演示步骤：注册（含确认密码）→用用户名或邮箱登录→创建Project→按项目链接刷新读取→退出。第二账号打开第一账号的项目链接应显示“资源不可用”。创建响应丢失时，刷新可恢复按用户隔离的待确认请求，只在点击“用原请求重试”后重放原键，不自动提交。显式退出清除本地待确认输入；会话失效时隐藏但保留原请求，同一账号重新登录后可用原键核查结果，不自动改键重发。密码不进入浏览器存储。

登录后可在“我的项目”查看本人项目（默认每页20项），点击名称进入，返回列表或退出重登后重新找回；归档项目标为只读，已删除项目不显示，管理员也不列出他人项目。列表失败可重试，游标失效可回第一页。

当前active项目可编辑名称/描述/研究范围，或经预览、勾选风险确认后归档/软删除。归档后只读且不提供解除归档或删除入口；软删除保留存储记录但不再允许进入。编辑冲突保留草稿，不自动以新修订覆盖；结果未知先核查，归档可核查同一原请求。个人LLM配置见下节；账号治理和现有私人资产清理见下节；知识构建尚未提供。默认根路径工程预览不等于业务入口；以/workspace和显式demo为验收对象。原认证/创建闭环已获限定接受，见[task019](tasks/019-browser-milestone.md)；Project Hub已获M-P0-02限定接受，见[task021](tasks/021-project-hub.md)。本批维护新增范围、验证与M-P0-03验收包见[task022](tasks/022-project-maintenance.md)。

个人资料维护入口见[task023](tasks/023-account-profile.md)：登录后点击“个人资料”，修改邮箱或显示名并保存，刷新后仍可读取。邮箱登录键遵守既有去空格/忽略大小写规则，展示保留原文；显示名可清空。用户名、权限和密码不通过此入口更改。遇到并发修改或提交结果未知，先显式核查当前资料；不会自动重发旧草稿。自动验证与M-P0-04验收状态以任务单为准。

## 个人LLM配置与模型选择

登录后点击“LLM设置”：新增配置，选择协议、填写Base URL与密钥；常用参数留空省略，高级参数或扩展键值编辑保留JSON类型，调用超时单独设置。保存只做校验与加密存储，不调用Provider。刷新模型只发现候选；手工填模型ID或选择候选，勾选费用提示后显式测试。测试成功才可作为顶部当前模型，刷新/重登恢复选择；修改配置后原选择显示失效，须重新测试/选择。可点击刷新测试状态查看实际参数、测试覆盖与安全诊断。

演示命令沿用上节。演示进程包含配置Worker，密钥文件写入本次隔离目录且权限0600，退出清理数据库时一并删除；保存的凭据不回显明文。HTTP Provider默认拒绝私网/回环地址及重定向，内部部署白名单为显式适配器配置，页面不能绕过。实际点击测试可能产生Provider费用；自动验收仅使用FakeProvider或受控本地服务，不代表所有云模型均兼容。生产密钥管理/生产Worker部署不在本片交付范围。系统LLM后续交付见下节。

任务与验收材料见[task026](tasks/026-llm-parameter-runtime.md)。完整集成运行上限为600秒，超时仍失败并清理测试环境。开发与干净安装均需Node24/npm11，不能用系统Node25代替约定版本。


## 个人数据源配置（M-P0-06）

同一临时demo中登录后打开“数据源设置”。支持arXiv、OpenAlex、Semantic Scholar、ADS的配置、启停、加密凭据及显式测试；“检索服务/API入口”填写对应服务入口，具体论文/文件地址属于检索结果或手动补充。保存不外呼，显式测试发送固定非业务查询，可能消耗供应商额度；默认自动验证只使用FakeProvider或受控本地HTTP服务。

匿名模式不发送已存密钥，ADS使用密钥模式；缺key可保存但不能测试成功。实际测试结果、访问模式、时间与失败原因可查看，修改配置后旧结果不恢复新修订可用性。未知请求结果沿页面“核查”恢复，不另建重复命令。非论文检索适配和Construction运行消费保持后续范围，系统数据源管理见下节；最新验证与里程碑状态见[task028](tasks/028-personal-source-runtime.md)。


## 管理员账号管理（M-P0-07）

首位注册用户为管理员，登录后使用“管理员用户”入口。支持基础账号列表、邮箱修改、密码重置、普通用户启停/删除和其他用户管理员授权/撤销；任何修改先预览并确认风险。账号治理不提供私人Project或配置读取能力。

重置密码只在新执行响应显示一次，不保存明文；若响应丢失，同键核查只返回已重置事实。自重置后保留密码展示，复制后刷新并用新密码登录。删除先撤销访问及旧任务资格，再清理私人资产；失败后保持失效，可重新选择账号预览删除以继续清理。返回的新预览会说明未完成清理，不能通过启用绕过。未知邮箱/角色/启停提交使用GET核查当前账号，不自动覆盖新修订。演示命令同上，测试使用隔离数据库且不调用真实论文/邮件服务。当前验证及人工验收状态见[task029](tasks/029-admin-accounts.md)。

## 系统LLM管理（M-P0-08）

管理员登录后打开“系统LLM”，维护平台配置、模型发现与逐模型测试。保存不调用Provider；测试费用提示与个人配置一致。普通用户在当前模型下拉框看到标注“系统”的已验证模型，须显式选择；失效时保留原选择并提示修复，不自动回落。普通用户不能读取系统配置、测试任务或密钥。

系统配置、已完成测试和审计不随创建管理员删除；撤销管理员资格终结其未完成系统测试，重新授权不复活旧任务。演示入口同时运行个人与系统配置Worker；仅配置闭环，不包含Construction/Research/Review任务；系统数据源和SMTP见后续小节。交付状态及证据见[task031](tasks/031-system-llm-runtime.md)，工程验证不代替M-P0-08人工验收。


## 系统数据源与个人多源API（M-P0-09）

管理员打开“系统数据源”维护四种论文源的平台配置、启停、API入口和凭据，并显式测试连接；普通用户仍从“数据源设置”分别维护arXiv、OpenAlex、Semantic Scholar、ADS的个人API配置。arXiv使用匿名API；其他源按其访问模式保存个人凭据。个人配置与系统配置使用独立编辑状态，切换页面保留草稿；未知提交结果通过原请求或只读核查恢复，不自动重复创建/更新。

来源解析按Provider逐类个人优先：个人arXiv可与系统OpenAlex共存；同Provider有个人配置但禁用/失败时不静默回落，多个实例保留各自身份。显式来源引用失效时要求修复，不换成同名来源。系统源测试共享平台限流预算，不因更换管理员绕过；撤权终止旧任务但不把权限终结冒充连接失败。平台资产不随管理员账号删除。

解析目前是经过隔离PG验证的内部读取接缝，尚未接入真实Construction启动或持久快照；配置页面与Provider测试可用，不代表知识构建已完成。验收状态及完整证据见[task033](tasks/033-system-source-runtime.md)。自动测试使用FakeSource，未调用真实论文服务。


## 系统SMTP、OAuth与基础安全配置

管理员打开“系统SMTP”维护一套平台发件配置。QQ/163填写客户端授权码，Gmail可使用符合账号条件的应用密码或OAuth，Microsoft 365使用OAuth，SendGrid填写API Key；界面按服务展示对应字段。保存不外发，“测试SMTP连接”只建立连接与认证，不发送邮件。系统配置不随创建管理员账号删除，普通用户不能读取其凭据或任务。

Gmail/Microsoft 365先由部署方在供应商注册OAuth应用并配置页面显示的精确回调地址，再填写client ID、client secret及Microsoft租户，保存后点击“连接账号”。授权成功后应用加密保管并按需刷新Token；撤销或无法刷新时提示重新授权。授权成功与SMTP测试成功分别显示，不能证明发信权限、收件投递或业务邮件已交付。生产部署必须对OAuth回调的查询串禁用访问日志或做明确脱敏；本地demo已禁用访问日志，不能把授权code/state记录到代理日志。

“基础安全”维护测试超时、未提交连接失败重试次数、诊断保留天数及诊断级别。超时仅用于配置测试，并与LLM配置取较严格预算；结果未知不自动重发，诊断清理不删除任务输入、审计或知识资产。页面遇未知保存结果先读取核查，测试命令按原键恢复。

复现沿现有隔离demo入口，构建后启动会运行SMTP测试Worker。自动验证使用模拟OAuth及本地SMTP/TLS服务，没有真实邮箱授权或发信；供应商账号策略与生产部署仍需目标环境验证。工程与M-P0-10状态见[task035](tasks/035-smtp-security-runtime.md)。本片验证补充使用Node 24.19.0，依赖锁不变。
