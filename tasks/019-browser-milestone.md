# Task019：注册登录与Project创建浏览器闭环

文档版本：v1.1
更新日期：2026-10-25

## 1. 授权与里程碑

继续task016批次，依赖task017/018工程收口。原始授权、task015限定接受与队列见[task016](016-project-storage.md)。用户要求持续推进到业务决定或下一里程碑，并已明确接受身份规则A：用户名/邮箱去首尾空格、忽略大小写、保留显示原文，禁止跨账号任一登录标识冲突，同一账号两种标识可相同。实现采用strip/casefold，不额外引入NFKC。

M-P0-01范围为首个本地业务闭环：注册、用户名/邮箱登录、当前用户、创建本人Project、按持久URL读取、退出，以及跨账号/禁用/未知提交结果的拒绝恢复。不代表完整Account/Project模块或整个P0验收。task016–019工程收口后停在该里程碑；人工接受尚未发生，不进入配置/构建业务。

## 2. 依据与边界

依据01 FR001/008与02/03-01/04认证、Project.Create既定规则。task016–018的逐需求持久化、认证与命令运行追踪分别保留在[task016](016-project-storage.md)、[task017](017-account-authentication.md)、[task018](018-project-create-runtime.md)。本单补浏览器可观察要求，不以测试数量关闭整个FR或TRACK。

使用webapp-testing技能的真实Python Playwright浏览器验证，既有Node骨架浏览器回归保留。默认首页骨架展示仍独立，业务入口为/workspace；真实业务界面只显示本片可用操作，不提供密码找回、治理、修改/删除Project或未实现任务按钮。

## 3. 实现落点与运行隔离

- `frontend/src/BusinessApp.tsx`、main入口和style：注册/登录表单、当前账号、创建/读取Project、错误与待确认重试。密码仅在输入状态中；sessionStorage只存按用户ID隔离的待确认命令key/参数。会话失效时隐藏但保留原请求，同一用户重新认证后才恢复；显式退出清除。私有POST固定csrf→me核对表单所属账号→携带原csrf提交，拒绝共享cookie在其他标签切换后错写账号。
- `scripts/run_business_demo.py`：显式隔离descriptor验证、迁移、业务应用装配、已构建静态资源服务；不回退环境业务DB。
- `scripts/run_storage_tests.py`及engineering demo：创建独立PG17实例和非管理员角色；demo通过exec替代转发wrapper，PG进程组不接受终端Ctrl-C，由监督进程负责停止。API停止后清理本轮根；无法确认PG停止时保留并报错。最长30分钟。
- Python真实浏览器、存储、演示清理回归；未调用LLM/Provider/邮件。with_server助手先读取--help；因为本片必须绑定每次临时DB descriptor并先迁移，生命周期使用现有隔离夹具与专用fixture。

## 4. UI需求追踪

以下浏览器函数均位于`backend/tests/integration/test_browser_business.py`；运行证据为本单第5节最终全套及独立补测。

| ID | 要求及禁止副作用 | 可执行场景 |
| --- | --- | --- |
| UI01 | 注册成功引导登录；用户名/邮箱登录；当前用户；密码无持久存储 | `test_ui01_ui02_ui04_register_login_create_reload_logout`、`test_ui03_unknown_result_survives_expiry_and_same_user_login`；后端AU02/03覆盖身份归一与重复/并发 |
| UI02 | 创建后读持久资源、URL重载；展示真实字段及尚无知识版本，不伪造Run | `test_ui01_ui02_ui04_register_login_create_reload_logout`；后端PC01验证Project/CW/receipt事务事实 |
| UI03 | 获取CSRF、执行中禁用；未知结果使用同键/参数，禁止自动重发/重复项目 | `test_ui03_lost_response_retries_same_command`（含刷新）、`test_ui03_unknown_result_survives_expiry_and_same_user_login`、`test_ui03_unknown_retry_csrf_rejection_preserves_original`；分别覆盖断响应、401、真实API403后恢复 |
| UI04 | 退出/禁用/身份变更安全清空；禁止错账号写入、撤销别人会话或展示私有上下文 | `test_ui04_cross_account_and_disabled_safe_empty`、`test_ui04_actor_bound_submission_across_cookie_change`（csrf前、csrf与me间、me后3时序）、`test_ui04_private_boot_read_loses_session_clears_visible_context`、`test_ui04_stale_logout_does_not_revoke_other_user` |
| UI05 | 标签可访问、错误/加载状态、确认密码与显示切换；390px无横向溢出；无虚假功能入口 | `test_ui05_confirmation_visibility_and_mobile_layout`及桌面/移动截图目视检查；表单使用原生标签和按钮 |
| UI06 | 空库迁移、显式隔离；API/PG/浏览器清理；缺目标拒绝；骨架保持 | `test_fixture_cleanup.py` AC10失败/超时、`test_ui06_demo_terminal_interrupt_removes_real_cluster`真实完整命令+HTTP200+SIGINT；`test_business_demo.py`5项拒绝；browser fixture退出断言及旧骨架2项e2e |

## 5. 验证与独立审查

证据根：[task019_browser_2026-10-25](../docs/workorders/evidence/task019_browser_2026-10-25/)。所有结果绑定含未提交/未跟踪文件的快照，不只HEAD。

- 初始172项PG/HTTP/browser通过；恢复补测后174项通过。独立真实反例发现R1跨标签私有草稿错归新账号、R2会话过期丢失未知请求，均返回S2修复，另补boot项目读取401清空。修复后179项根自验和独立全套通过。独立run `rpb_test_41e1d845a61746db82b6b73a7e6898d4`，90.70s，API/浏览器/PG/根清理成功，见`independent-179.log`。该轮期间3个Python文件仅格式变化，经独立AST比较相同，不冒充完全无漂移。
- S4补2项：旧标签退出不撤销B会话、未知请求重试403后仍可用原键恢复。真实demo Ctrl-C发现残留根；第一次只改pid判断未修复，不计通过。最终调整监督进程与信号链，手动PTY run `rpb_test_859138158fdc4e6f93c42ecc643a7c78`退出130且清理成功，并新增完整命令SIGINT回归。历史两份根在无pid且pg_ctl status=3后清理，见`demo-failure-cleanup.json`及对应shutdown日志。
- 最终全套：182项通过，97.86s，run `rpb_test_57f96379bdcb42dc9362e67be63429f8`，API/浏览器/PG及根清理成功。`integration-final.log`。其中11个真实浏览器参数化场景，独立PostgreSQL与HTTP，不以mock/健康检查替代闭环。
- 最终check：87后端单元/无库回归、66契约、3前端通过；ruff格式/静态检查、mypy43源文件、TypeScript通过，见`check-delivery.log`。
- 构建通过`build-review-fix.log`；干净锁定安装、锁漂移拒绝、wheel启停与前端构建通过`clean-final.log`；旧骨架2项浏览器通过`skeleton-e2e.log`。后续只变演示监督脚本和新增测试，未改变构建源、依赖锁或骨架行为，复用这些未受影响证据；新脚本由最终check和真实SIGINT集成覆盖。
- 最终独立审查：179项独立全套加最终7项新增/影响路径通过；后者run `rpb_test_25efff39342741a1aeeb29ea11b91d39`，清理成功，s6-fixed执行前后无漂移，R1/R2/boot401、S4与演示中断缺陷全部闭合。未声称独立重跑全部182项。见`independent-review-fix.txt`。S5检查无需新抽象或重构，保留简短的身份绑定提交函数和专用演示装配。
- 文档引用、版本、最终快照一致性检查见`documentation-check.json`及`receipt.json`。有一项FastAPI/Starlette测试客户端弃用警告，未影响通过；不声称未来依赖升级兼容已验证。

## 6. M-P0-01单一验收包

代码、自动验证和独立审查已完成；工程S1–S7已收口，里程碑等待人工验收。最终内容基线为证据目录`delivery/source-manifest.json`与`source.tar.gz`，摘要在`receipt.json`；该包包含所有当前工作区源文件，历史已接受内容不会据此被扩大接受。

先按[README](../README.md)安装锁定依赖并build；当前机器已验证的演示命令：

```bash
python3 scripts/engineering.py demo --postgres-bin /opt/homebrew/opt/postgresql@17/bin
```

打开 `http://127.0.0.1:8765/workspace`，注册→用户名或邮箱登录→创建Project→刷新项目链接→退出。第二账号访问第一账号的项目链接应见“资源不可用”。关闭后数据删除，不能作为持久工作库。当前未留下后台演示进程。

桌面与390px截图为证据目录`project-rpb_test_57f96379bdcb42dc9362e67be63429f8.png`、`mobile-rpb_test_57f96379bdcb42dc9362e67be63429f8.png`；自动故障注入覆盖手工不便重现的断响应、并发和身份切换时序。可接受本限定闭环、要求范围内修复，或另行提出新增需求。自动通过不代表用户接受。

## 7. 风险与未交付范围

仅隔离本地演示，退出丢弃数据；生产部署/持久配置/备份恢复、完整账号治理、Project列表与生命周期、LLM/资料来源配置、知识构建及Graph-RAG未交付。本片不能关闭整个FR001/008或TRACK业务总项。账号治理锁覆盖短Project事务，是当前串行化工程选择；未声称生产并发容量经过压测。演示端口8765被占用时拒绝，不终止其他服务。

## 8. 检查点

流程v1.7：S1范围授权、S2实现与自验、S3独立审查及缺陷修复、S4逐UI覆盖补测、S5保持行为无需重构、S6最终复验/复审、S7基线与证据交接完成。用户身份规则A已决，无悬而未决的同项业务问题。M-P0-01状态为等待人工；批次按原始“下一里程碑停下”指令停止推进后续业务。恢复时先核验delivery基线、人工答复及后续授权，不把本里程碑工程通过当成接受。
