# Task021：Project Hub 本人项目找回闭环

文档版本：v1.1
更新日期：2026-10-25

## 1. 目标与授权

用户于2026-10-25接受最新task019并要求“继续推进下一阶段的任务”。先完成本人已有项目找回：登录后列表、分页、进入持久链接、空/失败恢复。按既定P0切片，沿用Owner权限，不实现编辑/归档/删除、配置、构建或延期项。M-P0-02在该可操作闭环工程收口后提交验收，不将局部Hub称为完整FR008。

## 2. 依据与基线

01 FR008、02 Project Owner/状态、03-01 P02a、04 §3分页、04-01 §1/3及机器Project.List、05应用边界、07存储、08授权。task020最终237文件基线逐文件无漂移；原工作区全部保留，入场快照见`docs/workorders/evidence/task021_project_hub_2026-10-25/before/`。M-P0-01接受记录见task019第9节。

## 3. 修改落点

Project application端口/服务、project_commands适配器、projects路由、BusinessApp及样式、PG/HTTP/浏览器测试。分页按created_at DESC,id DESC执行keyset查询，默认20、1–100；游标绑定Owner、固定筛选/排序/资源范围，无知识版本范围，HMAC防篡改并限时30分钟。进程重启后游标失效，用户回第一页；不为临时游标引入持久化迁移。只读不增加Task/Run/回执或改写Project/CW。

## 4. 需求与验证追踪

- PH01：本人列表；管理员无他人项目特权；active/archived可见，deleted不可见；空列表成功。
- PH02：默认/边界页大小，稳定复合排序，同时间不漏不重，插入新项目不扰动后续页；终页标记。
- PH03：游标篡改、跨账号、过期拒绝；每次请求重新鉴权；不接受未声明筛选/排序。
- PH04：列表与详情投影一致，no-store；读取不写Project/CW/命令或创建运行对象；故障返回安全错误且可重试。
- PH05：浏览器登录后找回项目、进入/返回、分页/刷新、空/加载/失败；退出或身份切换不展示另一账号列表，迟到响应不得覆盖新页面；窄屏可用。

可执行用例：`backend/tests/integration/test_project_list.py`含15项参数化HTTP/真实PG场景；`test_project_hub_browser.py`含4项真实浏览器场景。逐项对应如下：

| 要求 | 用例与观察 |
| --- | --- |
| PH01 | `test_ph01_empty_owned_status_projection_and_no_writes`：空、他人/管理员、归档/删除、详情一致 |
| PH02 | `test_ph02_default_bounds_ties_insert_and_terminal`、`test_ph02_invalid_page_inputs`：默认20、1/100边界、非法类型/范围、同时间id排序、插入后翻页、终页 |
| PH03 | `test_ph03_unknown_query_and_malformed_cursor`、`test_ph03_tamper_actor_and_current_authorization`、`test_ph03_expiry_and_process_restart`：固定筛选/排序、篡改/跨Owner/过期/重启、未认证/禁用、页面账号断言 |
| PH04 | PH01记录SQL无写入且三表计数保持；`test_ph04_failure_safe_retry`注入真实查询故障并验证脱敏及恢复；ContractClient逐响应校验OpenAPI与no-store |
| PH05 | `test_ph05_hub_empty_paging_enter_return_mobile`：空/分页/归档进入/返回/退出重登/390px；`test_ph05_hub_network_failure_retry_and_expired_cursor`：网络失败恢复与真实游标拒绝；`test_ph05_hub_actor_switch_before_read_and_disabled`：请求前共享cookie切换及禁用；`test_ph05_delayed_list_cannot_restore_previous_account`：真实响应保留在Promise屏障，观察加载/禁用，退出重登后释放不显示旧账号项目 |

最后一个用例仅在测试中忽略AbortSignal，以独立验证已排队响应的alive防护，不伪造API成功数据。游标过期时间由应用服务注入时钟确定；浏览器游标用例改请求参数触发真实拒绝，不冒充等待30分钟。数据库全部使用隔离临时PG17，真实HTTP/Chromium；无LLM、邮件、Provider调用。

## 5. 执行证据

证据根：[task021_project_hub_2026-10-25](../docs/workorders/evidence/task021_project_hub_2026-10-25/)。

- 首轮`integration.log`：210项通过，143.59秒，run `rpb_test_7aba576960014cd9b03c5e7940c48f00`，API/PG/临时根清理成功。期间适配器类型标注和SQL literal写法按mypy修正，不能用首轮代替最终复验。
- `check-s4.log`：87后端/66契约/3前端、ruff格式/静态、mypy43源文件、TypeScript通过。先前失败日志保留：首次类型检查失败、随后规范指纹未同步、旧A04完整操作比较检测到新头/长度约束；已分别修正。旧断言现在先精确验证这两个增量，再对其余历史操作全等检查，不删除或降低原保证。
- `build-final.log`：后端wheel及前端构建通过。依赖锁、安装和数据库迁移未改变；未重新做干净安装，未声称本轮执行。
- 独立审查`/root/hub_review`发现C01必需迟到响应/加载用例缺失与C02机器游标边界缺失，均已补齐。`independent-review-final.json`：20项独立集成通过（19项本片新增＋1项既有认证），191项未选择，26.58秒；run `rpb_test_e04ae16326e34a7cab6d25892b0b2603`清理成功。受影响8项契约测试独立通过，执行前后受审文件无漂移。未声称独立重跑全套。
- `compatibility.log`：对入场机器契约的兼容门禁退出1，仅`GET /projects`变化；已逐项审查为可选账号一致性头和游标长度约束，未绕过门禁或声称零变化。新接口尚无此前运行消费者；其他操作/响应/权限绑定保持。
- 桌面与390px完整截图已目视核验，无横向溢出；不可信HTML显示为文字。截图包含20个测试项目，属于真实列表与滚动页面。
- `integration-final.log`：最终211项通过，144.10秒；run `rpb_test_3b619a77ab7e42158de1e1122cec6b0d`，API/PG停止及临时根删除成功。包括19项本片新增与原192项回归。既有Starlette TestClient弃用警告保留；无真实外部服务调用。

## 6. 决策与里程碑

无新增业务决定。M-P0-01已接受；M-P0-02为本片Hub找回闭环，工程已收口，现提交人工验收。后续配置/构建不由本片自动宣称完成。

## 7. 交付报告

当前完成本人项目发现接口与浏览器入口，完整Project编辑/生命周期、搜索/筛选、设置与构建仍未交付，FR008整体不关闭。无数据库结构变化，复用已有owner/created_at/id索引。列表游标仅适合本地单进程演示，重启使旧游标拒绝并可回第一页，多进程共享签名密钥/生产部署未验证。演示仍为临时库，关闭后删除数据。

M-P0-02验收路径：按README安装并build后，运行`python3 scripts/engineering.py demo --postgres-bin /opt/homebrew/opt/postgresql@17/bin`，打开`http://127.0.0.1:8765/workspace`；注册登录→创建多个项目→“我的项目”返回列表→从名称进入→退出重登仍能从列表找回；第二账号不见前账号项目。超过20项出现下一页。自动场景覆盖手工不便复现的故障、禁用、共享cookie和迟到响应。测试使用独立临时PG17，无生产写入。

本片补充了已接受M-P0-01的首页展示，原认证/创建/读取及恢复全套回归随最终验证运行；旧人工接受只绑定原基线。本次Hub行为由M-P0-02单独验收。

## 8. 检查点

流程v1.7。S1范围/基线、S2实现自验、S3独立审查、S4逐PH复核与补测已完成。S5抽取列表/详情共用投影、沿用现有UoW/索引、独立列表组件生命周期，无必要额外抽象。S6最终211项、check/build及独立复审通过；S7最终基线和状态已收口。授权来自本轮消息，依赖task019/020最新基线接受。无待决业务事项，M-P0-02已到并等待人工验收，暂停后续依赖本闭环的业务推进。


最终内容基线：证据根`delivery/source-manifest.json`及`source.tar.gz`；完整性和摘要见`receipt.json`。受审代码/测试/机器契约与独立执行摘要一致；S6后仅追加README、文件导航、任务和状态交接，未改变运行规则。文档引用/版本/差异核验见`documentation-check.json`。未提交、未跟踪文件均包含，保留全部既有工作区修改。

交付状态：本片设计/代码/自动验证/工程收口完成；M-P0-01原范围已接受，M-P0-02待接受；完整FR008、配置/构建、生产部署仍未完成。


## 9. 人工接受与后续授权（2026-10-25）

用户回复“可以，继续推进项目实现，直到里程碑或出现未决策的设计时再交给我审核”，接受上一轮M-P0-02限定交付并授权继续既定P0。接受基线为task021证据根delivery，manifest SHA-256 `57fcb21b5d7642603368b7a3d2f05b524093a447c7beb198b13f6ca0b2a8edd6`；本轮逐文件核对无漂移。原等待描述保留为历史状态，当前M-P0-02已接受。后续批次见[task022](022-project-maintenance.md)。
