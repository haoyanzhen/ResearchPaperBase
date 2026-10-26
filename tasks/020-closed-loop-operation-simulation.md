# Task020：当前闭环全流程操作模拟

文档版本：v1.0
更新日期：2026-10-25

## 1. 目标、授权与边界

用户要求“根据当前闭环内容，设计全流程的各类操作模拟测试，看看结果是否正常”。本次测试与必要缺陷修复限定M-P0-01：注册、两种标识登录、退出、本人Project创建/读取、拒绝与恢复。不得将本次自动结果记为里程碑人工接受，不启动后续配置/构建业务。

## 2. 依据与基线

已读AGENTS、PROJECT_STATUS、设计索引、实施入口、task017–019及相关实现。规则依据01 FR-001认证子条目、FR-008本人创建/访问子条目、04-01 §1文本约束/§2认证/§3 Project及task019 UI01–06。所有原有工作区修改保留。入场236文件快照在[证据目录](../docs/workorders/evidence/closure_simulation_2026-10-25/before/source-manifest.json)，与task019交付基线相符。

## 3. 修改落点

- `backend/tests/integration/test_browser_business.py`：补真实浏览器操作与错误纠正、故障恢复、存储拒绝、多个项目及不可信文本显示。
- `backend/tests/integration/test_project_commands.py`：补规范要求的首尾空白、长度及同键规范化重放。
- `backend/src/rpb/api/projects.py`：三个Project文本字段在长度校验前strip；非字符串继续交由strict类型验证拒绝，不改账号字段。

## 4. 操作矩阵与需求追踪

每轮使用独立PG17、非管理员角色、真实HTTP及Chromium；DB内部commit不触及业务库。下表已有用例亦全部重跑，不用历史通过替代本轮运行。

| 操作类型/依据 | 模拟动作及预期 | 可执行场景 |
| --- | --- | --- |
| 正常闭环/UI01/02/04 | 注册→邮箱登录→创建三字段项目→刷新→退出→用户名登录→原链接；1项目/1回执 | `test_ui01_ui02_ui04_register_login_create_reload_logout` |
| 认证拒绝/FR001 | 错密码、无此用户均不登录；重复注册不增账号，纠正后可注册并登录 | `test_sim01_auth_rejections_then_correction` |
| 表单/窄屏/UI05 | 确认密码不匹配无写入；显示隐藏密码、390px布局和无虚假入口 | `test_ui05_confirmation_visibility_and_mobile_layout` |
| 权限/UI04 | B读A项目不可见；禁用后拒绝；私有读取途中失效清空 | `test_ui04_cross_account_and_disabled_safe_empty`、`test_ui04_private_boot_read_loses_session_clears_visible_context` |
| 多标签/UI04 | cookie在三个时序切换，A草稿不得写入B；旧标签退出不撤销B会话 | `test_ui04_actor_bound_submission_across_cookie_change`、`test_ui04_stale_logout_does_not_revoke_other_user` |
| 提交前断网/UI03 | 未送达创建无DB写，刷新后用原键恢复 | `test_sim02_network_failure_recovery[before_post]` |
| 提交后断网/UI03 | POST已提交但响应或随后GET断线；原键重放只保留1项目/1回执 | `test_ui03_lost_response_retries_same_command`、`test_sim02_network_failure_recovery[after_post_read]` |
| 恢复再受拒/UI03 | 未知结果遇会话过期或CSRF拒绝，同账号重登后原请求仍可恢复 | `test_ui03_unknown_result_survives_expiry_and_same_user_login`、`test_ui03_unknown_retry_csrf_rejection_preserves_original` |
| 浏览器存储/UI03 | setItem抛异常时阻止POST/无DB写；恢复存储后可提交 | `test_sim03_storage_unavailable_has_no_write` |
| 输入纠正/项目隔离/FR008 | 全空白名422后可编辑；创建两项目，独立URL往返；不存在ID无私有信息；HTML文本不执行 | `test_sim04_project_validation_multiple_links_and_literal_text` |
| 文本边界/04-01 §1 | 三字段剥除外空白后在上限应成功；等价同键重放不重复 | `test_sim05_text_length_after_trimming_and_replay` |
| 内部空白/04-01 §1 | 剥除首尾空白但保留正文内部空格与换行，重新读取一致 | `test_sim06_internal_whitespace_preserved` |
| 提交中/UI03 | 在真实POST发送的路由屏障处观察提交/退出按钮和字段禁用，最终仅一次写入 | `test_sim07_inflight_form_blocks_duplicate_submission` |
| 并发/事务/版本拒绝 | 并发注册仅首位管理员；同键竞争；各写点失败回滚；回执期限及载荷版本拒绝 | `test_account_auth.py` AU、`test_project_commands.py` PC全套 |
| 迁移/清理/UI06 | 首迁移及各升级/失败回滚；演示SIGINT、失败/超时清理 | `test_account_storage.py`、`test_project_storage.py`、`test_fixture_cleanup.py` |

真实故障注入包括网络route.abort、临时库会话失效/禁用及受控事务故障；成功响应来自真实应用，不伪造成功数据。完整FR001/008、生产容量、其他浏览器引擎、真实外部LLM/邮件/论文来源不在范围内。

## 5. 执行证据

证据根：`docs/workorders/evidence/closure_simulation_2026-10-25/`。先build确保浏览器使用当前产物，然后运行`python3 scripts/engineering.py integration --postgres-bin /opt/homebrew/opt/postgresql@17/bin`。首轮190项：186通过、4失败，详见`integration-before-fix.log`。其中3项为同一产品缺陷：三个文本字段未在长度检查前剥除首尾空白，合法边界值返回422；已用before validator修正。另一项为sim03恢复Storage方法的测试脚本错误（evaluate返回原生函数导致自动调用），改为无返回的函数体；产品拒绝写入的断言此前已通过。未弱化断言或跳过失败测试。补内部空白及提交中防重复操作后，最终192项全部通过（117.85s），见`integration-final.log`；其中17个真实浏览器参数场景，4个新增HTTP参数场景，其他为原有HTTP/持久化/清理场景。新增合计10项。

- 最终全套run_id：`rpb_test_c4be1512b6214a3583c0980807d41f4d`；API/PG停止、临时根删除均成功。
- `check-final.log`：ruff格式/静态、mypy 43源文件、87后端、66契约、3前端与TypeScript全部通过；`build-final.log`：最终后端wheel及前端构建通过。
- 独立审查发现R1文本规范化缺陷，经修复复审闭合；独立执行全部新增10项通过、182项未选择，18.58s，见`independent-sim.log`。run_id `rpb_test_7f090db9d2074dc1bcb2cb623f0ac561`清理成功，三份代码/测试前后摘要一致。没有声称独立重跑192项。
- 桌面与390px窄屏截图已目视检查，分别复制为本证据目录`desktop.png`和`mobile.png`。无异常布局，密码保持掩码。
- S4补入内部空白保持、提交期间禁用；S5审查无需额外抽象。sim07是确定请求屏障上的控件禁用观察，不冒充连续双击压力测试。
- 全局`git diff --check`报告6份既有设计文件尾部空行；与入场快照一致，未修改。限定本轮改动检查另见`documentation-check.json`。
- 一项既有Starlette TestClient弃用警告保留，不影响本轮通过。未重新做干净安装或跨浏览器验证，未声称生产可用。

## 6. 决策与验收

无新增业务决定。既有M-P0-01继续待人工验收；本次用户请求是操作测试，不是验收通过。账号标识保留原文的专属规则不受Project文本修正影响。

## 7. 交付报告

本次设计操作矩阵并新增10个可执行场景；发现1个产品缺陷并修复，另修正1处测试脚本错误。最终192项集成、常规check及构建通过，独立10项复验通过。代码改动仅Project输入归一，未修改业务分期、权限、数据库结构或账号规则。最终基线保存在证据目录`delivery/`。

## 8. 检查点

S1限定授权/快照、S2实现与自验、S3独立审查修复、S4覆盖补测、S5保持最小实现、S6最终复验/独立复审、S7文档与快照交接均完成。M-P0-01保持待人工验收；用户未授权越过里程碑推进后续业务。
