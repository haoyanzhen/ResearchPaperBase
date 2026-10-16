# API Contracts 设计

文档版本：v1.9
更新日期：2026-10-16
依据文档：[00](00_layers.md)、[01](01_functional_requirements.md)、[02](02_domain_core.md)及其领域附录

## 1. 范围与维护边界

本文与两份附录构成 P0 API 设计基线，供后续实现、契约测试和联调使用；不表示已实现或通过运行验收。API 把 HTTP 命令/查询映射到 [05 应用用例](05_application_use_cases.md)，不直接操作数据库、Agent 或图谱，不定义新的业务状态、权限或产品分期。

| 文档 | 唯一维护内容 |
| --- | --- |
| 本文 | 公共认证、信封、分页、修订、确认、幂等、错误与分期 |
| [04-01 P0 操作契约](04-01_p0_operation_contracts.md) | 操作到 FR/用例映射、请求响应字段、业务前置条件、关键示例及验收入口 |
| [04-02 任务、事件与文件](04-02_transport_task_file_contracts.md) | TaskHandle/TaskView、SSE 回放与恢复、文件传输及技术限制 |
| [设计审查工作单](../workorders/api_p0_design_review_2026-10-16.md) | 独立预案、主代理评审取舍、待人工决策、实际文档检查证据 |

业务含义服从 01/02，页面职责服从 03。附录不得通过新增字段改变业务规则。R1-A–R4-A 及用户补充已于2026-10-16采纳，见[决策记录](../proposals/api_boundary_redesign_2026-10-16.md)；替换D03严格覆盖与D06独立导出快照，本轮E01–E04已关闭。06–10、SQL 和历史备份不因本次修改整体升格为已定规范。

本轮使用可检查的 Markdown 操作表和具名字段结构；未生成 OpenAPI，也没有生成 SDK、服务端代码或数据库迁移。实现阶段应把已定字段机械转写为 OpenAPI/校验模型，逐项校验方法、路径、必填、枚举、响应、错误和分期一致性；不得把未决分支补成猜测默认值。

## 2. P0 范围及后续入口

P0：FR-001/002/003/005/006/007/008，FR-011–018 的 P0 子集，FR-020–026 的 P0 子集，FR-028，FR-032–035。基础引用展示和跳转由 FR-012/028/033 承接，不因 FR-031 整体 P1 而删除。

- FR-034 的当前终稿形成、轻量编辑、单篇已保存稿 Markdown 下载、默认接受、显式拒绝与显式完成是 P0；不要求独立导出快照。FR-019 的通用导出中心、批量与PDF/Word转换 ExportJob 仍为 P1。
- 检索词的 `auto_update_enabled=true` 默认值及开关由 FR-020 定义；实际自动调度及邮件仍为 P1。未实现时只报告能力不可用，不伪造下次运行或推送结果。
- 重新评分、当前分析/大纲/章节重新生成、重新审查是相应 P0 阶段动作；不等于整个历史 Run 的 P1 通用 retry/reconnect/rerun。
- P0 SSE 断线重新订阅只恢复显示，不启动 P1 业务恢复。

以下仅保留后续设计落点，不计入已定 P0 字段契约，不得返回伪成功或开放不可用入口：

| 分期 | FR / 后续接口族 | 未来验收重点 |
| --- | --- | --- |
| P1 | FR-001 密码找回；FR-004 `/me/notification-config`、`/test-email` | 安全验证、多收件人、失败不改偏好 |
| P1 | FR-009 调度内部命令；FR-027 `/projects/{project_id}/email-push-jobs` | 无人值守、固定发布范围、逐项防重复、无空邮件 |
| P1 | FR-014/015 `/retry`、`/reconnect`、`/rerun`、暂停/恢复、通用复制/归档/删除实例 | 原实例保留、断点可信、paused 占槽显式交接 |
| P1 | FR-019 `/exports`、`/exports/{export_job_id}`、`/file-access` | 范围快照、部分成功、授权读取、生命周期 |
| P1 | FR-023 批量上传/数据表；FR-029 输出倾向；FR-030 总结/搜索增强；FR-031 引用增强 | 不改变 P0 单文件和基础引用；不改绑版本 |
| P1 | FR-006 系统白名单/速率/并发上限 | 仅已启用限制参与检查，不作为 P0 前置 |
| P2 | FR-008 协作授权，FR-010 `/viewpoints` 及管理隐藏，FR-006 管理员诊断/调度控制，FR-036 Review 历史/差异/回退 | 独立授权与分期；管理员无 Project 隐式权限 |

## 3. HTTP、字段与分页

- 前缀 `/api/v1`；附录表格路径省略此前缀。JSON 使用 UTF-8，字段名 snake_case。文件/SSE 响应例外见 04-02。
- ID 使用 UUID 字符串，客户端视为不透明值；`revision`、游标、确认 token 为不透明字符串，不按数值或时间推断权限/顺序。时间为带时区 RFC3339，输出统一 UTC `Z`；日期区间显式说明边界，不能依赖服务器本地时区。
- 请求仅接受操作列出的可写字段。未知写字段返回 422；`owner_id`、状态、确认人、任务结果、版本绑定等服务端字段不可任意 PATCH。新对象创建允许的目标版本字段不表示已有对象可改绑。
- 字段省略与 `null` 区分：PATCH 省略保持原值，只有显式标记可空的字段允许 `null` 清空；数组提交为空表示清空该数组，不能默认为“保持”。其余字段不接受 `null`。只读未知响应字段客户端可忽略。
- 创建默认值仅在创建时应用，不在 PATCH 时补齐覆盖。空字符串不等于缺失；非空文本去除首尾空白后必须非空，正文保留内部空白。数值必须有限，不能传 NaN/Infinity。
- 同步读取/更新/确认为 200；已完成创建为 201，附 `Location`；可靠受理的异步命令为 202，附任务 `Location`；无内容删除为 204（无 JSON）。异步失败后的任务 GET 正常为 200，通过任务错误表示执行失败。
- GET 不能启动生成、发布、重新下载或修复。能力与动作建议仅改善 UI，不是授权凭据。
- 列表采用 `page_size`（默认 20，1–100）、`cursor`（可省略），默认 `created_at DESC,id DESC`；消息/步骤等自然顺序列表在附录指定。`sort` 仅接受该接口明确列出的值，不能传任意数据库字段。
- 游标绑定调用者、Project、筛选、排序和已解析读取版本；后续页不能漂移至新默认版本。条件不同返回 `VALIDATION_CURSOR_MISMATCH`，过期返回 `VALIDATION_CURSOR_EXPIRED` 并从第一页重新读取；客户端必须保留原版本意图。
- 列表 `data.items` 是数组，空列表成功返回 `[]`；`meta.next_cursor=null` 表示结束，`has_more=false`。不强制提供昂贵全量 total；已有业务统计单独返回且注明候选或正式版本范围。

### 3.1 知识读取版本与接口演进边界

知识资产接口沿用 [04-01 知识资产契约](04-01_p0_operation_contracts.md)，内部服务契约见 [06](06_agent_knowledge_services.md#31-版本读取与存储适配契约)。接口灵活性限于存储适配和兼容扩展，不能放宽版本、权限或引用边界。

- 普通浏览入口可省略版本，服务端一次解析并返回实际版本；由 Session/Run/引用打开时使用其绑定版本。后续详情、分页、文件与图谱读取继续显式传递已解析版本；游标过期重开第一页也保留原版本意图。
- 客户端传入版本/资产/证据 ID 均须校验 Project、成员关系和来源对象绑定；冲突拒绝，不能选其中一个静默继续。公开接口不接受任意存储路径、namespace、清单替换或已发布修订覆盖。
- EvidenceRef 的 id 是不可变证据记录身份，服务端记录须解析到具体资产/文本/分块或图谱修订及定位校验信息；不要求客户端提交或复制整份清单。现有版本+证据 ID 不能被重新赋予其他内容。AssetView.asset_revision 指该版本的资产修订，不是当前可编辑对象 revision。
- 公开返回 DTO 与物理存储结构分离；新增可选只读诊断字段可兼容扩展，改变必需字段、修订含义、查询可见范围或默认绑定语义必须进行契约修订及兼容性验证。适配器更换不得改变证据身份或扩大访问范围。
- 失败沿用公共错误与防枚举规则；内部可诊断版本失配/依赖缺失/不可用，对外不得通过细分错误泄露无权访问的对象。不可用时不能返回拼接其他版本的成功响应。

## 4. 认证、授权和当前状态

P0 Web 使用同源部署或开发代理，服务端会话 Cookie：生产 `HttpOnly; Secure; SameSite=Lax; Path=/`，不设置宽泛 Domain。登录成功轮换会话，登出撤销当前会话。开发 HTTP 仅限 loopback，可不启用 Secure；不能将例外用于共享部署。第三方 Bearer API、跨站凭证和 SSO 不在本轮范围。

`GET /auth/csrf` 返回与预会话/当前会话绑定的 `csrf_token`。所有不安全方法（包括登录、注册）必须携带 `X-CSRF-Token`，并验证 Origin 为配置的同源来源；会话轮换后重新取得 token。登录/注册/CSRF 引导和最小公开健康检查无需已登录身份，其余均认证。P1 密码找回未实现时不开放该路由。SSE 使用同源 Cookie，不在 URL 放长期凭证。

账号状态在每次请求、异步关键提交及流式推送鉴权点重新检查；缓存会话不能绕过禁用。认证、账号、密钥配置、私人业务响应、确认预览及任务响应均 `Cache-Control: no-store`，不得进入共享缓存。

| 边界 | P0 判定 |
| --- | --- |
| 个人配置、当前模型、个人上下文 | 当前有效用户本人；不可由请求自报 user_id 替代认证主体 |
| Project 及子对象 | Owner 且对象属于路径中的 Project；同时校验 Run/Session/版本/候选/文件之间的归属，不只检查单个 ID 可读 |
| 管理员路由 | 当前启用管理员；只允许账号治理及系统配置；不因此读取他人 Project、个人配置或原始任务诊断 |
| active Project | 按对象/动作许可读写；使用/删除权限语义服从 02，P0 不提供共享权限编辑 |
| archived Project | 只读；业务生成、上传、修改、继续等拒绝；P1 历史导出按既定允许范围单独校验 |
| deleted Project | 不进入 Workspace、不读业务资产、不调度；返回安全不可访问结果 |
| 任务/文件/证据 | 当前权限与生命周期优先于启动时授权；历史版本不是绕过删除或撤权的通道 |

Workspace 显示上下文与业务写入分开：P0 服务端上下文保存仅用于 active Project；archived 阅读过程可在本地按用户/Project 保存显示位置，不能通过上下文端点修改业务对象或自动提交草稿。跨账号登录不得恢复另一用户的本地草稿。

未认证 401；非管理员访问管理功能 403；不存在、跨 Project 或不允许披露的资源统一 404，不透露对象归属。只有已确认可访问的对象才返回具体状态、修订冲突和诊断。权限判断必须先于幂等结果重放及对象差异响应。

## 5. 响应与错误

成功与列表示例：

```json
{"data":{"id":"00000000-0000-4000-8000-000000000001","revision":"r1"},"meta":{"request_id":"00000000-0000-4000-8000-000000000002"}}
```

```json
{"data":{"items":[]},"meta":{"request_id":"00000000-0000-4000-8000-000000000002","next_cursor":null,"has_more":false,"resolved_knowledge_version_id":null}}
```

失败结构固定：

```json
{
  "error": {
    "code": "STATE_REVISION_CONFLICT",
    "category": "state",
    "message": "内容已变化，请重新读取后提交",
    "retryable": false,
    "details": {"current_revision": "r2", "resource_url": "/api/v1/projects/00000000-0000-4000-8000-000000000001"},
    "recovery": {"action": "reload_resource", "label": "重新读取"}
  },
  "meta": {"request_id": "00000000-0000-4000-8000-000000000002"}
}
```

`details` 只允许安全字段名、原因枚举和当前主体可访问的资源引用；不得传 Provider 原始响应、SQL、堆栈、密钥、私有路径或其他 Project 资料。`recovery` 可为 null；只是建议，不会自动执行，也不替代确认。`retryable=true` 仅表示可以按既定条件重试传输/请求，不表示自动重跑业务或更换幂等键。

| HTTP | code（规范示例） | category | 客户端行为 |
| --- | --- | --- | --- |
| 400 | `VALIDATION_BAD_REQUEST`、`VALIDATION_CURSOR_MISMATCH`、`VALIDATION_CURSOR_EXPIRED` | validation | 修正请求/重新取页 |
| 401 | `AUTH_REQUIRED`、`AUTH_SESSION_INVALID`、`AUTH_ACCOUNT_DISABLED`、`AUTH_INVALID_CREDENTIALS` | auth | 重新认证；不自动重发写命令 |
| 403 | `PERMISSION_ADMIN_REQUIRED`、`PERMISSION_CSRF_REJECTED` | permission | 修复身份/CSRF，禁止越权回落 |
| 404 | `PERMISSION_RESOURCE_UNAVAILABLE` | permission | 不存在或不可披露；安全空态 |
| 409 | `STATE_OPERATION_NOT_ALLOWED`、`STATE_PROJECT_READ_ONLY`、`STATE_NOT_CANCELLABLE`、`STATE_LAST_ADMIN_REQUIRED` | state | 展示原因，不改变对象状态 |
| 409 | `STATE_IDEMPOTENCY_CONFLICT`、`STATE_CONFIRMATION_STALE`、`STATE_CONFIRMATION_REQUIRED` | state | 不换键自动执行；刷新确认依据 |
| 409 | `LOCK_CONSTRUCTION_OCCUPIED`、`LOCK_RESPONSE_ACTIVE`、`LOCK_CONTENT_BUSY` | lock_conflict | 读取已有任务；不得强制覆盖 |
| 409 | `VERSION_REQUIRED`、`VERSION_BINDING_MISMATCH`、`VERSION_BASELINE_STALE` | version | 缺版本/范围不匹配；非最新本身不是错误 |
| 409 | `CONFIG_MODEL_SELECTION_REQUIRED`、`CONFIG_MISSING`、`CONFIG_SECRET_UNAVAILABLE`、`CONFIG_SOURCE_DISABLED`、`CONFIG_CONNECTION_FAILED` | configuration | 修复配置后显式重新提交 |
| 409 | `STATE_EVENT_REPLAY_UNAVAILABLE` | state | 按 04-02 读取快照重新订阅，不重跑 |
| 410 | `STORAGE_FILE_UNAVAILABLE` | storage | 已授权对象的文件已清理/失效；不替换其他版本文件 |
| 412 / 428 | `STATE_REVISION_CONFLICT` / `STATE_REVISION_REQUIRED` | state | 刷新后提交 / 补前置修订 |
| 413 / 415 | `VALIDATION_PAYLOAD_TOO_LARGE` / `VALIDATION_UNSUPPORTED_FORMAT` | validation | 调整文件/请求；不进入流水线 |
| 422 | `VALIDATION_FIELD_INVALID`、`VALIDATION_UNKNOWN_FIELD`、`VALIDATION_FILE_UNREADABLE` | validation | `details.fields[]` 标识字段与原因；不泄露原值 |
| 429 | `STATE_RESOURCE_LIMIT` | state | 技术资源保护，带 Retry-After；不等于 P1 配额产品 |
| 502 / 503 / 504 | `PROVIDER_FAILED` / `PROVIDER_UNAVAILABLE` / `PROVIDER_TIMEOUT` | provider | 仅同步依赖失败；异步失败见 TaskView |
| 500 | `STORAGE_INTERNAL_FAILURE` | storage | 通用安全错误与 request_id；内部分类留日志 |

附录的专用错误须落在上述 HTTP/category 规则下，使用已有类别前缀；未决业务不得伪装成已生效的新错误语义。Project 删除等异步操作若失去资源可见性，只提供账号治理授权范围内的执行结果，不复原原内容。

## 6. 修订、确认与内容保护

所有可变资源返回 `revision`（不透明字符串，1–128 字符）。影响该操作语义的变更推进修订；仅下载次数等无关统计不得让人工确认无故失效。读取详情给出 `available_actions`，条目至少含 `action`、`enabled`、`reason_code`（可空）；由应用层计算，调用时仍重验。

- PATCH/PUT 和针对已存在对象的有条件命令携带 `expected_revision`；DELETE 用同名 query 参数，避免请求体兼容问题。新建资源和纯测试/查询不要求不存在的修订。附录说明复合目标的各修订字段。全项目粗粒度 revision 不能替代章节/候选级保护。
- 缺必需修订 428；不匹配 412，并只返回可授权读取的当前修订。客户端不能拿新 revision 自动重发旧修改。
- P0 采用请求体协议，不同时要求 ETag/If-Match。revision 是当前内容并发标记，不提供 P2 历史版本列表/回退。
- `content_state` 表达 `agent_draft`、`manual_confirm`、`manual_edit`；与 `acceptance_status`（如终稿 accepted/rejected）分开。默认接受不伪造人工确认。必要修改追溯返回修改人、时间、来源动作、修订。
- 人工保存不自动完成筛选确认、入库确认或章节确认。重新生成获准后，生成内容也不自动继承旧内容的人工确认身份。

确认对象的共同字段：`confirmation_id`、`action`、`target{type,id}`、`subject_revision`、`impact_revision`、`knowledge_version_id`（适用时）、`candidate_revision`（适用时）、`risks[{id,message}]`、`expires_at`、`confirmation_token`。token 为服务端随机引用/可验证不透明值，绑定当前用户、目标、动作、修订、影响范围及有效期；不能用于授权其他动作。

提交确认携带 `confirmation_token`、目标 `expected_revision`、`acknowledged_risk_ids[]`（无风险时为空数组）；DELETE 使用同名重复 query 参数传风险 ID，省略代表空数组，不省略其他前置字段，并按端点提交具体决定。服务端重新校验当前权限、状态、依据、范围和风险；实质变更返回 `STATE_CONFIRMATION_STALE`。token 过期需重取预览；技术 TTL 只限制新命令受理，不限制已受理任务的执行时长。受理时原子保存确认记录及其操作者、动作、目标修订、影响范围和风险依据；Worker 校验该持久确认记录是否仍适用于当前内容/权限/依据，不再以原 token 的墙钟过期时间拒绝长任务。同一幂等请求的已执行确认重放只返回执行记录，不再次消费。覆盖人工内容必须有明确替换范围的预览/token，不接受 `force=true` 或全局覆盖开关。

修订校验保护并发写入，确认凭据保护已展示的具体影响范围；不能因对象可变就额外要求用户确认。确认适用场景及凭据读取入口由 04-01 明列，现有阶段确认、人工覆盖、治理与删除清理、版本采用等要求不减少。

阶段等待项可在详情中直接提供上述确认对象；不要求额外多走一个通用预览端点。明示后果的操作及已显示的风险确认可以完成确认，不强制重复弹窗。token 是并发与依据证明，不能证明前端实际看过页面，更不能替代服务端业务校验。

任务启动固定有效输入修订、覆盖授权及执行资格；Construction 显式返回检索按 D01 A 追加修订，不改初始快照、基线或配置，旧执行不得跨修订写入。提交结果再次检查。期间人工内容/候选/依赖变化，旧结果不能覆盖当前内容，保留未采纳结果与诊断。失败/取消不删除原成功或人工内容。构建预览变化只能使相关确认失效，无关配置留到下轮。

## 7. 幂等与可靠受理

幂等按操作副作用划分。创建、生成、外部连接测试、模型刷新、确认执行、取消和单文件接收等 POST 命令要求 `Idempotency-Key`（客户端随机 UUID 或 16–128 个可打印 ASCII 字符）；认证 register/login/logout 仍为例外。纯 GET 不使用此头；PATCH/PUT/DELETE 仍以修订条件保护，响应丢失先查询核实，不自动覆写新状态。

纯预览 POST（操作附录的 action-preview、cleanup-preview、association-clear-preview、adoption-preview）只计算当前影响范围并签发确认凭据，不调用 Provider、不创建 Task、不修改业务修订或消费确认，因此不要求幂等键、不保存业务命令去重记录、不返回 idempotency_expires_at；若携带该头则忽略，不能据此重放旧预览。每次重新鉴权并校验 expected_revision，返回当前依据的预览及有效 token，响应为 200/no-store。技术凭据存储和访问审计不算业务变更。token 过期重新读取预览，旧依据变化仍返回修订/确认冲突；预览不代表用户已同意，真正执行命令仍须提交确认并按幂等规则受理。新增预览必须满足这些条件，否则按有副作用命令单列契约。

1. 去重作用域是认证主体 + 固定 operation_id + Project/目标资源 + key；服务端计算规范化参数摘要，包含影响语义的 query、body、expected_revision、确认 token、上传内容摘要。CSRF token、request_id、multipart boundary 不进入摘要。
2. 校验身份和资源可见性后检查幂等记录。已受理同键同参数返回同一对象/任务与原结果语义；已受理同键异参数返回 409。重放不重新执行当前修订校验导致假冲突，但必须检查当前权限、可见性及结果有效性，不能重放已删除/拒绝文件的可用下载结果。
3. 201/202 表示已可靠受理：并发同键同参只产生一次业务效果，返回的对象/任务必须可查询，受理后不能因派发故障丢失任务。受理存储不可用返回安全失败，不调用 Provider；事务、去重竞争与可靠派发的执行顺序统一由 05 第 3 节维护。
4. 已受理但最终失败仍返回原失败任务；同键不自动重试 Provider。明确重新生成是新操作、新键，并再次校验当前权限与内容保护。
5. 记录至少保存受理后 24 小时，非终态不得仅因超时淘汰；响应 `meta.idempotency_expires_at` 给出当前最早去重失效时间（非终态可为 null）。这不是永久 exactly-once 承诺。客户端保留对象/任务 ID，超期或结果不明先查询，不自动换键重发。
6. 重放的 `request_id` 是当前请求追踪 ID，可附 `original_request_id`；不得把另一个主体的命令记录作为返回值。取消与完成的竞争按 04-02，不靠幂等决定业务顺序。

管理员重置密码是敏感例外：仅首次成功响应返回 `{operation_id,reset_completed:true,password_disclosed:true,new_password}` 中本次新生成密码（FR-005），`no-store`、不日志、不存通用幂等响应明文；同键重放返回 `reset_completed=true,password_disclosed=false` 及操作 ID，不再次重置。首次响应丢失时管理员显式新建一次重置命令取得新密码，不能恢复原明文。普通密码、API key、SMTP 密码在其他任何 GET/重放中均不返回明文。

## 8. 契约验收与未决限制

每个写操作必须具备：FR、具名 use case、字段结构、当前权限/状态前置、修订/确认要求、同步或异步返回、幂等范围、失败语义和测试入口。具体覆盖见 04-01/04-02；执行、事务与结果提交见 05。验收至少覆盖：

- 禁用会话与跨 Project ID 混用；管理员不能借诊断查看用户内容。
- 同键重复、异参冲突、响应丢失；修订冲突后不自动重发。
- 同一 Project 写槽互斥、迟到 Worker 拒写、候选隔离和完整发布。
- 旧对象固定证据、资产分页版本稳定、新版采用只创建新对象。
- 人工编辑与后台生成竞争、确认依据变化、终稿默认接受与显式拒绝。
- SSE 重复/乱序/回放过期、无 done 的断线恢复、取消与完成竞争。
- P0 单文件与支持格式、无执行代码能力、下载重验权限。
- P1/P2 未实现不阻塞已定 P0 路径。

业务待决及被阻塞分支统一登记在[工作单](../workorders/api_p0_design_review_2026-10-16.md)，不在各层重复给出不同答案。当前文档检查只能证明引用、版本、协议一致性；不能证明数据库隔离、真实多源检索、模型/解析能力或端到端接受。相关实现必须使用隔离测试环境和默认 mock 外部服务，真实外部验收另有明确目标及副作用声明。

已采纳的构建状态机以 [02-02 第 10 章](02-02_construction_versioning_appendix.md)为准：成功结果区分 published/no_change，不扩展 Run 状态；P1 恢复与分期仍遵循 [02-04](02-04_run_recovery_appendix.md)。这不关闭工作单中其他 API-D 待决分支。

## 9. 变更记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.6 | 2026-10-16 | 收敛纯预览幂等与确认适用范围；执行顺序引用应用层，保留可观察可靠性保证 |
| v1.5 | 2026-10-16 | 对接已采纳构建状态机及两种成功结果，保留其他 API 待决与分期 |
| v1.4 | 2026-10-16 | 经独立预案与审计补齐 P0 通用协议，拆分操作与传输附录，明确分期、未决分支及实现限制；未实现代码 |

本次修订 v1.8（2026-10-16）：更新七项方向已决状态与显式输入修订边界。

本次修订 v1.9（2026-10-16）：同步 R1-A–R4-A 及人工补充裁决；本轮细则已关闭，实现与运行验收另行跟踪。
