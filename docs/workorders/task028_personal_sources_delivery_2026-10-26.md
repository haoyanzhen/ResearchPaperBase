# M-P0-06：个人论文数据源配置验收包

文档版本：v1.0
更新日期：2026-10-26

## 范围与状态

用户授权推进至 M-P0-06 或新的未明确设计。本包实现 arXiv、OpenAlex、Semantic Scholar、ADS 四个基础论文源的个人配置闭环：创建、读取、更新、软删除、独立启停、加密凭据和持久连接测试。数据源设置地址是检索服务/API入口；具体论文、网页及文件地址属于结果或手动补充资料，不写入配置作为搜索入口。设计、代码、自动验证及 S1–S7 工程收口已完成；M-P0-06 待人工验收。

任务及授权见 [task028](../../tasks/028-personal-source-runtime.md)。完整入场快照及最终内容基线位于 [证据目录](evidence/task028_sources_2026-10-26/)，包含已有未提交与未跟踪文件，未重置原工作区。M-P0-05 的历史接受仍绑定其原基线。

## 实际变更

独立 source 配置、命令、任务、审计和速率表由 0008 迁移建立，复用授权事务、凭据加密和受限 HTTP 传输。配置写入不触发外呼；测试须明确提交，发送固定 electron 查询且最多请求一条。任务读取经统一入口按所有者授权；失败、过期租约、修订变更、撤权和重复提交不得重复请求或将旧结果标为新配置可用。

页面保留草稿，支持切换前保存/放弃/留在当前页、修订冲突提示、未知提交结果核查及切号清理。列表最新创建优先。启用状态独立于连接测试结果；匿名模式不发送已保存密钥。arXiv 全局单连接及三秒间隔与个人预算独立，其余服务按本人同服务目标计速。节流状态持久化，重启及重建配置不能绕过预算。

S5 简化保留共享网络/授权/事件工具，隔离 source 存储及协议差异；未进行无关重构。共享错误分类修复覆盖 LLM 与 source 回归，不改变错误码和业务语义。

## 需求追踪与反例

以下均绑定当前执行证据，而不是以测试数量替代需求覆盖。SC/SP/SU 是可执行测试函数前缀；涉及真实持久化的场景在隔离 PostgreSQL 中执行。

| 需求及禁止副作用 | 场景 / 可执行位置 |
| --- | --- |
| 个人配置 CRUD、默认值、空值、启停、修订；无效输入不能写入或外呼 | `test_source_configuration.py` SC01/03/17；`test_source_provider.py` SP 输入校验 |
| 四种已注册协议、认证模式、缺钥失败、匿名不传保存的密钥；响应必须验证协议 | SC02/04/05；SP01–05；`test_source_http.py` 受控真实 HTTP 六场景 |
| 凭据加密、保留/轮换/清除、无加密器安全失败；响应/审计不泄密 | SC01/02/09/19；SU02 |
| 所有者隔离、CSRF、预期账号、失权；旧请求不能清除新登录 | SC08/15；SU08；现有账号回归 |
| 幂等与确定性并发：同命令一次配置/审计、一次外呼 | SC04/10/18（PG 锁确认双方等待后释放）；SU03/05 |
| 持久任务、SSE、重启、修订/删除撤销、租约过期及迟到结果 | SC02/06/07/08/14/15；两个 `test_llm_demo.py` 子进程场景 |
| 用户/服务速率、arXiv 全局约束；异常及重启不得绕过，私人低速不得阻塞其他账号 | SC11/16；Worker 出站租约检查 |
| 分页新建优先、审计失败回滚、已有数据拒绝危险降级 | SC12/13；迁移和原表集回归 |
| 202/结果/失败任务/PublicError 与契约一致 | SC13/19；SP06；公共错误及契约回归 |
| 浏览器保存/测试/刷新/编辑失效/删除 | `test_browser_sources.py` SU01 |
| 草稿切换、两页冲突、丢失写响应后核查、跨修订轮询不污染旧表单 | SU02/03/04/05/06/07 |

测试文件位于 `backend/tests/integration/` 与 `backend/tests/unit/`。本片不写 Project 知识资产、Session、Review 或人工内容；知识版本绑定/跨 Project 文件处理不是本配置切片新增行为，保留后续对应需求，未宣称覆盖。

## 验证与审查

最终验证全部通过：

| 检查 | 当前结果 / 原始证据 |
| --- | --- |
| 隔离 PostgreSQL 全量集成（含真实浏览器和子进程） | **398 passed**，388.37秒；[integration-final.log](evidence/task028_sources_2026-10-26/integration-final.log)，服务停止、临时根目录移除均为true |
| 静态、格式、类型、架构及后端单元 | 58源码文件类型通过、**187 passed**；[check-final.log](evidence/task028_sources_2026-10-26/check-final.log) |
| 机器契约及契约回归 | 契约检查通过、**68 tests OK**；同一check日志 |
| 前端类型/单元 | **4 passed**；同一check日志 |
| 当前前端构建 | [build-final.log](evidence/task028_sources_2026-10-26/build-final.log)，产物与集成运行所用bundle名称一致 |
| Node24干净安装、锁文件拒绝与wheel运行检查 | [clean-install-final.log](evidence/task028_sources_2026-10-26/clean-install-final.log)，临时环境清理完成，无数据库/Provider访问 |
| 文档、差异和完整快照 | 本轮链接存在、契约规范指纹通过；原有05-01尾部空行未改且与before哈希一致，未伪称全工作区diff-check无告警；最终[delivery](evidence/task028_sources_2026-10-26/delivery/)逐文件及归档校验 |

复现全量：`backend/.venv/bin/python scripts/run_storage_tests.py --postgres-bin /opt/homebrew/opt/postgresql@17/bin`；静态/契约/单元：`python3 scripts/engineering.py check`。集成与单元各有一条现有Starlette/httpx弃用提示，不影响当前通过，未擅自升级依赖。

中间失败日志保留，最终日志不代表从未出现失败。已修复迁移父标识、可访问控件名称、初始化页面请求影响禁用会话、迁移表集期望、错误分类与默认排序等问题；未删除或弱化要求来换取通过。

独立只读后端审查发现并复核关闭协议假成功、认证/速率、任务契约及 demo 消费等问题；独立 45 项 source/共享 HTTP 单元通过，随后 SP06 三项 schema 回归通过，契约检查通过。独立前端审查关闭旧测试状态/跨修订混用/延迟登录响应问题，类型和四项前端测试通过；最终延迟挂载修复亦复核。两位审查者均未独立执行 PG/浏览器，不能将主代理证据写成独立执行。当前无剩余阻断发现。

## 可复现验收

在仓库根目录使用已安装依赖执行：

```sh
npm --prefix frontend run build
python3 scripts/engineering.py demo --postgres-bin /opt/homebrew/opt/postgresql@17/bin
```

打开终端显示的本机 `/workspace`，注册/登录后进入“数据源设置”。演示数据库独立、最长 30 分钟，退出清理，不能当持久库。

1. 新建 arXiv 配置，确认字段为检索服务/API入口；保存后刷新仍存在。编辑名称及启停，确认独立保存。
2. 创建 ADS 且不填密钥，保存成功；明确同意测试后，应出现可恢复的缺钥失败，配置保持存在。
3. 打开两页，分别编辑同配置；后一页保存冲突应保留草稿。切换配置时检查保存/放弃/留在当前页。
4. 使用下面自动浏览器场景复现成功测试与响应丢失恢复，它们使用 FakeProvider，避免真实云端额度。若自行点击已具备有效服务配置的测试，会真实发送一次固定查询；本次交付未执行真实云服务验收。

```sh
PYTEST_ADDOPTS='-k test_browser_sources' backend/.venv/bin/python scripts/run_storage_tests.py --postgres-bin /opt/homebrew/opt/postgresql@17/bin
```

## 边界与后续

真实云服务可达性、当前配额和私有代理兼容性未验证。系统数据源管理、非论文类型适配器、Construction 消费及资料下载属于后续未交付范围，登记于现有任务地图/契约覆盖缺项，不自动启动。未知适配类型明确拒绝；不能以枚举存在宣称支持。未新增业务决定；到达本里程碑后等待人工验收，不推断为已接受。
