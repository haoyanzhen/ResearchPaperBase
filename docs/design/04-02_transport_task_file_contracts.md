# API 附录：异步任务、事件传输与文件

文档版本：v1.4
更新日期：2026-10-16  
适用项目大版本：v1  
依据文档：[API 主文](04_api_contracts.md)、[P0 操作契约](04-01_p0_operation_contracts.md)、[应用用例](05_application_use_cases.md)、[运行恢复领域附录](02-04_run_recovery_appendix.md)

## 1. 范围与分期

本文定义 P0 操作所需的技术执行投影、状态读取、SSE 传输和单文件上传/授权读取。路径均省略 `/api/v1`。认证、响应信封、错误分类、`expected_revision`、幂等键及当前权限复核遵循 API 主文，不提供另一套规则。

- Task 是应用执行的技术投影，不替代 ConstructionRun、ResearchSession、ResearchResponseAttempt、ReviewRun、内容确认或 KnowledgeVersion 的业务状态。任务成功不必然表示知识发布或内容被人工采纳。
- P0 事件断线后重新订阅只读取已产生事件；不得恢复 Worker、重新调用模型、重建执行上下文或创建新的 attempt。业务 retry/reconnect/rerun、暂停/恢复仍为 P1。
- FR-034 的当前终稿保存及单篇 Markdown 下载属于 P0，无独立导出快照；FR-019 通用导出中心、批量与PDF/Word转换 ExportJob 仍为 P1。
- 当前权限及对象状态始终优先于历史任务、文件和配置快照。Project 任务只允许当前有权访问该 Project 的用户读取；配置测试任务按配置所有权或系统管理员权限读取。知道 task_id 不构成授权。

## 2. TaskHandle 与 TaskView

### 2.1 公共结构

创建命令需要异步执行时，HTTP 为 `202 Accepted`，`Location` 指向 TaskHandle.status_url。data 的具体形状由 04-01 操作表决定：纯测试/生成操作可直接返回 TaskHandle，带业务对象的操作返回 `{业务对象字段,task:TaskHandle}`；客户端不得假定所有异步响应都有 data.task。同步完成的操作不必伪造 Task。

| 字段 | 类型与含义 |
| --- | --- |
| `task_id` | UUID；一次受理执行的稳定标识 |
| `project_id` | UUID 或 null；Project 操作必须有值，个人/系统配置测试可为空 |
| `target` | `{type:string,id:UUID}`；业务目标，例如 construction_run、research_response_attempt、review_chapter、review_final、supplement、user_llm_config；枚举由操作契约限定，客户端不得自行新增 |
| `attempt_id` | UUID；本次执行尝试身份，不因网络重订阅改变 |
| `execution_status` | `queued / running / waiting_user / succeeded / failed / cancelled`；仅为技术执行投影 |
| `status_url` | `/api/v1/tasks/{task_id}` |
| `events_url` | `/api/v1/tasks/{task_id}/events` |
| `cancel_url` | 已定义业务取消命令的地址或 null；不是任意 Task 均可取消 |
| `result_refs` | 授权业务结果引用数组；受理时可为空；每项为 `{type,id,url}`，不含文件真实路径 |

TaskView 在上述字段上增加：

| 字段 | 类型与含义 |
| --- | --- |
| `revision` | 字符串；任务视图修订标识 |
| `created_at / updated_at` | RFC3339 时间 |
| `started_at / finished_at` | RFC3339 时间或 null |
| `stage` | 当前业务阶段代码或 null，仅用于展示 |
| `business_state` | `{target_type,target_id,state,revision}` 或 null；明确归属对象，不把 Task 状态传播为 Session 或整个 Review 状态 |
| `waiting_items` | 等待项引用数组，沿用业务契约的确认身份、依据修订与允许动作；无等待项时为空 |
| `cancel_requested_at` | RFC3339 时间或 null；技术取消请求事实，不新增领域 cancelling 状态 |
| `error` | 主文定义的安全错误对象或 null；不得返回密钥、内部路径、完整日志 |
| `warnings` | 可展示风险/降级信息数组，元素 `{code,message}` |
| `event_cursor` | 不透明游标；对应本次快照已包含的最后一个事件位置 |
| `partial_result_ref` | `{type,id,url}` 或 null；本 Task 已保存的累计输出读取引用，可在任务运行或失败/取消后恢复显示；不代表已采纳或成功内容 |

`GET /tasks/{task_id}` 返回 `200 {data:TaskView,meta:{request_id}}`。任务本身后来失败时，该 GET 仍返回 200，失败记录在 `execution_status/error`，不将成功读取诊断误报为 HTTP 502。无权或不存在按主文返回安全 404。

`result_refs` 仅引用已经存在的结果；引用不保证目标仍可读取，跟随链接时重新鉴权。`succeeded` 的具体意义由创建操作定义，例如文件校验成功、章节生成完成或终稿生成完成；ConstructionRun 的 succeeded 结果通过业务对象读取并区分 published / no_change：仅前者返回本 Run 发布的版本，后者关联核验的既有版本与范围、时间，不伪造新版本。attempt/Task 失败不直接推导整个 Run failed，后续通知 Task 失败不逆转已经成功的 Run。

配置连接测试及模型刷新任务的 `result_refs` 指向 `GET /tasks/{task_id}/result`（`Task.ReadConnectionResult`）：200 的 data 为 `{result_type:"connection_test",payload:ConnectionTest}`，ConnectionTest 结构见04-01。未完成返回409 `STATE_OPERATION_NOT_ALLOWED`，无此结果类型返回安全404；执行失败优先读取TaskView.error。此路由只承接配置测试结果，不作为可写通用业务结果入口。其他任务通过其业务结果URL读取具名投影。

### 2.2 累计文本恢复

对于产生 delta 的文本任务，`partial_result_ref.url` 指向 `GET /tasks/{task_id}/output`；相同当前任务权限适用。不存在已保存输出时 partial_result_ref 为 null，直接调用返回安全 404。输出对象为：

`{task_id,attempt_id,output_revision,text,text_length_chars,execution_status,event_cursor,citations,warnings,result_refs,business_state}`。

`citations` 为截至该游标的完整证据引用快照，元素固定使用04-01 EvidenceRef；当前权限不可读取的证据不能泄漏内容，也不能用其他版本证据补齐。`warnings` 为截至该游标仍需展示的 `{code,message}` 数组；`result_refs`、`business_state` 与 TaskView 的结构和语义一致。空集合返回 []，无业务状态时返回 null。这些字段与累计文本、执行状态、event_cursor 必须属于同一个原子快照，不能仅恢复文本而跳过此前 citation/warning/status 事件。

`text` 是该 attempt 截至 event_cursor 已持久化的完整累计文本，`text_length_chars` 为 Unicode 字符数，`output_revision` 为不透明修订；输出及全部附属快照字段、执行状态和游标必须原子一致。不使用字节 offset 拼接不同快照，也不从其他 attempt 补齐。`execution_status=succeeded` 仅表示本任务成功，是否采纳仍读取业务内容状态。对无文本的任务以 result_refs 恢复，不伪造文本输出。

首次读取或回放过期时，客户端先 GET TaskView；若有 partial_result_ref，读取累计输出并用返回文本替换该 attempt 的临时展示缓冲区，同时恢复 citations、warnings、result_refs、business_state 和 execution_status。若输出快照已为 succeeded/failed/cancelled，停止订阅并按该状态展示；否则以输出响应 event_cursor 订阅，不再使用较早 TaskView 的游标。新 delta 仅应用于该缓冲区，不替换人工编辑内容。该只读查询不调用模型、不新建 attempt，失败/取消任务的累计文本仍明确为未成功/未采纳输出。

### 2.3 受理、派发和并发

- 202 保证句柄可查询、受理可恢复且不会因派发故障丢失任务；事务、去重和派发实现统一见 [05 第 3 节](05_application_use_cases.md#3-标准用例管线)，不在传输协议重复规定内部执行步骤。
- 权限、写资格或来源依据失效后，迟到结果不得写入当前人工内容或已发布资产；执行检查点由 05 第 3、6 节维护。
- 状态和事件按同一提交顺序可观察；TaskView 的业务快照与 `event_cursor` 必须原子一致，不能返回“新游标配旧内容”。
- 同幂等键重复提交返回同一业务对象/Task；不同命令争用同一业务锁返回明确冲突，不隐式排队多个相互覆盖的写操作。已按领域规则登记的 Construction 排队请求不占槽，实际取得槽后才进入执行；接口受理不得提前宣称占槽。独立章节是否可并发仍服从领域锁范围。
- 整体 Run 等待人工时可以投影 waiting_user；不能把单个等待项包装成新业务状态。确认通过后继续原允许流程，不视为 P1 故障重连。
- 非终态的幂等记录不得按固定窗口淘汰；保留规则见主文。任务诊断、业务结果和临时产物各按其生命周期保留，事件窗口不代替业务保留规则。

### 2.4 取消

API-D04 A：Project 归档/删除/清理生效即撤销影响范围内的执行资格，异步安全终止；该系统终止不要求先调用用户取消路由。TaskView.error 可为空，以 warnings 的管理原因和 business_state 区分；安全终止确认后 execution_status=cancelled，finished_at 记录终结时间。已终态的 Task/Run 不因管理操作重写成功/失败结果，清理失败是独立结果，不恢复旧资格。Project 删除后不能凭任务链接读取原内容；账号治理清理结果仅显示该治理授权范围的安全摘要。


客户端调用业务契约给出的取消入口，必须明确被取消的 `task_id` 或 `attempt_id`，并提交该入口要求的目标 `expected_revision`；不得只传“当前任务”而误取消后来开始的任务。尚未分配执行身份的 ConstructionRun 按 04-01 传 attempt_id=null，以路径 Run ID 和 expected_revision 限定目标。请求成功受理但后台尚未结束时返回 202 和最新句柄，TaskView 记录 `cancel_requested_at`。

- 同键重复按主文重放，不用旧 expected_revision 产生假冲突。不同键请求先校验其 expected_revision；通过后，已 cancelled 的同目标取消返回 200 和当前状态，succeeded/failed 等其他终态返回 `409 STATE_NOT_CANCELLABLE`。不同键且修订过时仍返回 412，不能用取消绕过并发保护。
- 取消完成必须确保执行不能再提交成功内容；Construction 的取消与 published/no_change 两种完成结果在同一业务裁决边界排他：完成先提交则保留 succeeded，取消先撤销写资格则拒绝后续完成；响应丢失先查持久结果，不重复发布。撤销旧写资格后才释放占槽。
- 技术租约、心跳超时或进程重启不得释放 paused ConstructionRun 的业务槽。失败后放弃恢复保持 Run failed，关闭恢复资格并记录清理结果，不调用取消命令把 failed 改为 cancelled；P1 恢复入口继续由 02-04 约束。
- Review 章节任务取消不取消其他章节；Research 回复取消不把 Session 变为 cancelled 或 paused。
- 浏览器关闭连接不等于取消任务。客户端仅在用户明确取消后调用取消命令。

## 3. SSE 事件契约

### 3.1 订阅和事件结构

`GET /tasks/{task_id}/events` 返回 `text/event-stream`，采用主文同源会话认证。订阅是只读操作，不创建 Task 或触发模型生成。认证失败在流建立前按 HTTP 错误处理；连接存续期间持续核验当前授权，身份失效或权限撤销后停止推送和关闭连接。

```text
id: <opaque-event-cursor>
event: delta
data: {"event_id":"<uuid>","sequence":12,"task_id":"<uuid>","project_id":"<uuid>","target":{"type":"research_response_attempt","id":"<uuid>"},"attempt_id":"<uuid>","knowledge_version_id":"<uuid>","task_revision":"t12","target_revision":"r5","occurred_at":"2026-10-16T09:00:00Z","payload":{"text":"增量文本"}}

```

- `event_id` 是去重身份；`sequence` 是该 Task/attempt 内单调递增整数，不承诺全 Project 的全局顺序。
- `project_id` 仅配置类任务可为空；`knowledge_version_id` 对无知识版本任务可为空，Research/Review 必须等于其实际绑定版本；Construction 的基线/候选/发布版本通过明确命名的 payload 字段表达，不能以一个含糊版本字段互相替代。
- `task_revision` 必填，对应该事件提交时 TaskView.revision；`target_revision` 可为空，非空时对应 target 业务对象修订，不能混用。`business_state.revision` 仅对应 business_state.target_id 的业务对象，若与事件 target 相同则应与 target_revision 一致。两类修订均不比较大小，事件顺序由 sequence 决定。
- delta 必须可重放或包含在可恢复快照中后才能发送。客户端按 event_id 去重；不得重复追加文本。

| event | payload 最小结构 | 语义 |
| --- | --- | --- |
| `status` | `{execution_status,stage,business_state}` | 已提交的状态变化，不授权客户端推进业务状态 |
| `delta` | `{text}` | 本 attempt 的增量文本；仅应用到对应生成缓冲区，不覆盖编辑器人工草稿 |
| `citation` | `{citation_ref}` | 授权且带绑定版本的证据引用；按业务契约解释 |
| `warning` | `{code,message}` | 风险、局部失败或降级，不能被误当作整体成功 |
| `error` | `{error}` | 安全错误对象；业务执行失败须同时可由快照查询 |
| `done` | `{execution_status,result_refs}` | 该 Task 进入 succeeded/failed/cancelled；不结束 Session 或其他 Task |

`done` 只在技术任务终态产生；waiting_user 发送 status，不发送 done。失败可先 error 后 done，客户端也必须仅凭失败快照停止 loading，不依赖始终收到两条事件。

### 3.2 回放和快照恢复

客户端传 `Last-Event-ID`；需要用 fetch 重建连接时可使用 `after_event_id` 查询参数。两者同时存在必须相同，否则 `400 VALIDATION_CURSOR_MISMATCH`。事件游标必须校验属于当前 Task、attempt 和授权范围。

首次订阅及任何需要重建显示的重新连接均先 GET TaskView；文本任务若已有 partial_result_ref，按 2.2 读取累计输出并使用其 event_cursor，其他任务使用 TaskView.event_cursor，随后订阅该游标之后的事件。服务端按提交顺序回放，再连续推送，不能在回放/实时切换之间漏事件。

- 游标过期或回放窗口不足：在开始流之前返回 `409 STATE_EVENT_REPLAY_UNAVAILABLE`，安全 details 包含 `status_url`。客户端重取快照及其 event_cursor，再订阅，绝不重发生成命令。
- 快照若为终态，客户端停止重连；快照必须包含完整结果引用或可读取的已保存部分回复引用，不能要求客户端依靠已过期 delta 才能恢复内容。
- 无法解析或属于其他流的游标返回 400；无权对象先按主文安全 404，不用错误透露另一 Task 是否存在。
- 流建立后的传输断开可能没有 error/done。客户端使用指数退避并查询状态；若服务端能发送关闭提示，可发送安全 warning，但它不能代替 HTTP/快照恢复。
- 重复、乱序或迟到事件不得覆盖按已处理 sequence 更新过的视图（revision 为不透明值，不能比较大小），不得改变知识版本绑定，不能把旧 attempt 内容接入新 attempt。
- 发布新 KnowledgeVersion 的通知仅提示新版本；不得通过 SSE 改绑 Research/Review。

### 3.3 错误示例

以下仅展示主文统一信封中的 error 部分：

```json
{"code":"STATE_EVENT_REPLAY_UNAVAILABLE","message":"事件回放窗口已过，请重新读取任务状态。","category":"state","retryable":false,"details":{"status_url":"/api/v1/tasks/<task_id>"},"recovery":{"action":"reload_task","label":"重新读取状态"}}
```

任务失败后的 GET 响应仍可为 200，`data.execution_status="failed"`，`data.error.code="PROVIDER_UNAVAILABLE"`；这不授权客户端自动创建新 attempt。API 主文的错误前缀和恢复动作限制适用于所有事件错误。

## 4. 单文件上传与补充处理

### 4.1 接收契约

`POST /projects/{project_id}/construction-workspace/supplements/upload` 使用 `multipart/form-data`，要求主文的认证、CSRF 和 `Idempotency-Key`。字段：

| 字段 | 约束 |
| --- | --- |
| `file` | 必填且恰好一个文件；paper 仅 PDF，material 按 P0 格式白名单 |
| `kind` | 必填，`paper / material` |
| `title` | 可选字符串；仅作为用户提供元数据，不冒充提取确认结果 |

成功完成基础接收校验后，异步解析返回 `202 {data:{supplement,task},meta}`，supplement 使用业务附录的 SupplementView 结构。`task.target.type=supplement`，其 ID 等于 supplement_id。Location 指向 Task 查询地址。

上传幂等请求指纹涵盖 kind、title 及服务端计算的文件内容摘要；同 key 不同内容返回幂等冲突，不要求客户端自报摘要可信。为重放计算摘要可以接收临时字节，但不得生成重复业务补充记录或触发重复解析；被拒字节按临时接收文件处理。

- 接收成功、解析完成、元数据确认、候选纳入与 KnowledgeVersion 发布是不同结果。
- 新补充默认进入待纳入范围。不得因为有 active Run 就自动改写其冻结输入；当前 Run 内显式候选修订使用业务附录的受控入口。
- `GET/PATCH /projects/{project_id}/construction-workspace/supplements/{supplement_id}` 和对应 `/confirm` 由业务附录定义；上传入口本身不跳过人工确认或授予入库资格。
- DOI/arXiv/URL 单条补充通过 JSON `/supplements`，不混入 multipart 文件字段。
- URL 获取是受控服务端 Provider/下载操作，必须限制协议、重定向和内网目标；不是任意 URL 代理。处理失败记录在补充任务，不能伪造已确认论文。

### 4.2 基础校验与解析边界

在进入待确认、去重、分析及入库流程前验证大小、扩展名与内容识别、基础可读性。基础接收失败返回 413/415/422 并保留脱敏诊断，不创建已确认资产。接收通过后发现深度解析失败，保留补充请求及可诊断失败状态，不能将其标记为可检索知识。

- paper：PDF。
- material P0 基础白名单：pdf、doc、docx、ppt、pptx、html、htm、md、txt、rst、yaml、yml、json、toml、ipynb、py。代码文件的基础可验收格式明确为 py；其他已实现静态解析的代码扩展名必须逐项出现在 capabilities 白名单，不以“等”或任意扩展名替代支持声明，也不缩减 FR 的后续扩展范围。
- csv/tsv/xlsx/xls 属于 P1；图像、音频、视频属于 P2。P0 返回 `415 VALIDATION_UNSUPPORTED_FORMAT`，不得靠更改文件名绕过。
- `.doc/.ppt` 属于既有 P0 要求，不能悄悄降为 P1；实现时若缺转换器须记录未满足能力和验证缺口。
- HTML 不执行脚本；notebook/code 不执行代码；Office 不运行宏。只提取静态文本，不提供通用文件执行服务。
- 压缩容器检查解压大小、条目数、路径穿越和递归压缩；拒绝口令保护或无法安全读取的输入，保留明确诊断。
- PDF-only 按既有规则先本地提取，再用查询锚点补元数据；关键元数据不足时等待用户确认，不直接生成正式资产。

## 5. 授权文件读取

P0 使用鉴权代理下载流。业务资源的 `file-access` 入口返回：

`FileAccess={asset_id:ID,knowledge_version_id:ID,filename:string,media_type:string,size_bytes:integer,download_url:string}`。

`download_url` 指向同源 `/api/v1/projects/{project_id}/files/{asset_id}/download?knowledge_version_id=...`；该路由仅在资产确实属于当前 Project、指定版本包含该资产且当前账号有权限时返回文件流。尚未发布的补充/候选文件使用下述专用读取路径，不能伪造已发布 knowledge_version_id 或用正式资产路径绕过候选隔离。

- file-access 和实际下载均鉴权；元数据读取许可不能代替下载许可。
- 文件响应设置准确的 Content-Type、`Content-Disposition: attachment`、`X-Content-Type-Options: nosniff`，私有文件不进入共享缓存。
- 不返回本地路径、对象存储内部 key、其他 Project 引用或无限期公开 URL。
- 资源不存在/越权、安全不可披露时按主文返回 404；有权资源的明确版本错配返回 `409 VERSION_BINDING_MISMATCH`；文件丢失返回 `410 STORAGE_FILE_UNAVAILABLE`，进入安全空态，不从其他版本补齐。
- Project archived 仍按现有只读规则读取授权历史文件；deleted 不得通过 Workspace 文件路径访问。
- P1 ExportJob 下载继续使用同样鉴权原则，但其保留及 deleted Project 导出文件的访问边界由 FR-019/对应操作契约细化，本文不新增下载授权。

### 5.1 未发布文件读取

04-01 定义的补充/候选 file-access 返回 `UnpublishedFileAccess={document_asset_id:ID,scope:{type:supplement|candidate,id:ID,run_id:ID|null},filename:string,media_type:string,size_bytes:integer,download_url:string}`。supplement 的 run_id 为 null，candidate 必须为所属 Run ID；不包含 knowledge_version_id，不复用正式 FileAccess 的版本字段。

- download_url 只能指向同 Project、同补充请求或同 Run/候选的专用 files/{document_asset_id}/download 路由。document_asset_id 从对应详情 document_refs 取得，不向客户端暴露临时路径。
- P0 当前有效 Owner 按既有 Project 读取权限访问；archived 仅可读仍保留且允许访问的文件，deleted 不可读。file-access 与下载均检查全部归属、当前授权和生命周期；读取候选不授予研究检索或正式引用资格。
- 仅返回已经通过基础安全接收且可安全提供的实际文件；隔离、拒绝或尚不能安全读取的字节不可下载。深度解析失败不自动等于原文件不可读，但仍须通过前述安全检查。读取不重新下载远程来源、不解析或触发模型。
- 越权、不存在、跨 Project/Run/候选或关联错误统一安全 404；已授权且确认关联但文件已清理/丢失返回 410；已授权且确认关联但尚未通过安全接收返回 409 STATE_OPERATION_NOT_ALLOWED，不披露字节。不以其他候选或正式版本的文件替代。
- 文件流沿用第 5 节 attachment、准确 Content-Type、nosniff 和 no-store 要求；不增加预览执行脚本、代码或宏的能力，不延长原文件保留期限。

### 5.1 当前终稿 Markdown 下载

`GET /projects/{project_id}/review-runs/{run_id}/finals/{final_id}/download?expected_revision=...` 使用04-01定义的当前终稿修订。缺失修订428、失配412；一次一致读取固定字节，后续保存不混入已开始的流，不提供任意历史修订下载。不调用模型、不创建ExportJob。终稿accepted且当前有权读取时，完成前后及归档只读场景均可下载；rejected、deleted或越权不可下载。返回 `text/markdown; charset=utf-8`、安全文件名的 attachment、no-store、nosniff；预览不执行脚本，不暴露或写入用户本地路径。已下载副本不能撤回，外部修改不自动回传。以当前已保存完整正文生成附件，摘要/引用投影不得与其使用不同修订。

## 6. 技术默认限制

下列是实现初始部署默认值，不改变业务分期，不代表已实现限额管理后台。部署可以覆盖，但前后端必须使用同一有效配置；降低限制不得将已有成功内容删除或改成失败。

`GET /capabilities` 是认证只读入口，返回 `CapabilityView={contract_version:"v1",capabilities_revision:Revision,limits,supported_upload_formats,features}`。capabilities_revision 是不透明配置修订，用于识别客户端缓存是否失效；响应使用主文 no-store。

- `limits` 必须返回当前实际生效值：`json_body_bytes`、`upload_file_bytes`、`multipart_body_bytes`、`title_chars`、`text_field_chars`、`archive_expanded_bytes`、`archive_entries`、`sse_frame_bytes`、`sse_heartbeat_seconds`、`sse_replay_seconds`、`sse_replay_events_per_task`、`sse_connections_per_user`、`poll_interval_seconds`、`confirmation_ttl_seconds`，以及主文 `page_size_default/page_size_max`。数值单位由字段名固定，不将秘密或基础设施路径作为能力返回。
- `supported_upload_formats` 为 `{paper:["pdf"],material:[...]}`，扩展名小写且不带点；material 基础项见 4.2，额外代码格式仅能列真实实现且经过验证的静态解析格式。此表只报告当前运行能力；缺失需求规定的 P0 格式须记录为实现缺口，不能靠隐藏条目声称验收通过。
- `features` 为具名布尔值：`task_events`、`single_file_supplements`、`general_exports`、`business_recovery`、`batch_upload`。P0 已实现能力才可为 true；本期后面三项为 false。该结果不授予 Project 权限，不代替每次写请求校验，不提供管理员编辑或配额管理入口。

| 项目 | 默认值 | 超限/恢复 |
| --- | --- | --- |
| JSON 请求体 | 1 MiB | 413 VALIDATION_PAYLOAD_TOO_LARGE |
| 单文件 | 50 MiB（52,428,800 bytes） | 413；上传前可提示，服务端流式计数必须强制校验 |
| multipart 总体积 | 文件上限 + 1 MiB | 413；防止额外字段绕过文件上限 |
| 确认 token 技术有效期 | 15 分钟；内容实质变化可提前失效 | 过期重取预览，不延长业务授权或回收用户成果 |
| 标题 | 1–500 Unicode 字符（提供时） | 422；不截断 |
| 普通文本单字段 | 200,000 Unicode 字符，且受总体积约束；业务更小上限优先 | 422；不静默截断论文/草稿 |
| 解压后总大小/条目数 | 200 MiB / 10,000 项；不递归展开嵌套归档 | 422 VALIDATION_FILE_UNREADABLE，说明安全解析限额 |
| SSE 单帧 | 64 KiB；超长文本拆为连续 delta | 不截断正文；元数据过大改为授权结果引用 |
| SSE 心跳 | 每 15 秒注释帧；无业务事件也保持连接 | 心跳不增加业务事件 sequence |
| 客户端传输重连退避 | 1 秒起，指数增长至 30 秒，加随机抖动 | 401/403/404 停止；409 先取快照；429 遵循 Retry-After |
| SSE 回放 | 每 Task 保留最近 24 小时且至多 10,000 条，任一界限触发可淘汰 | 过期用快照恢复，不删除业务回复/诊断 |
| 同账号 SSE 活跃连接 | 6 条 | 429，Retry-After: 5；客户端合并同 Task 订阅或轮询 |
| 状态轮询 | 正常每 3 秒；后台页面可放慢 | 不把超时或临时网络失败变为业务 failed |

这些限制不是吞吐保证。论文检索数量、模型 token、运行并发业务上限、资料保留期等由既定需求/配置定义；本文不擅自给出会改变研究范围或删除用户成果的默认值。失败可恢复临时产物的等待/清理窗口仍需应用设计单列，不与 24 小时 SSE/幂等窗口混用。

## 7. 契约验收设计

以下是后续自动化验证入口，尚未执行，也不替代端到端验收：

| 编号 | 必须验证的结果 |
| --- | --- |
| TTF-01 | 202 前受理与派发可恢复；提交/派发间崩溃不丢任务，同键并发仅一任务 |
| TTF-02 | 跨 Project task_id、文件 ID、事件游标均不能读取；配置任务按所有权/管理员范围隔离 |
| TTF-03 | Task 成功不改绑版本；章节完成不结束整个 Review；回复取消不暂停 Session |
| TTF-04 | 重复取消已取消目标为 200，其他终态 409；迟到 Worker 不写回，Construction 槽交接安全 |
| TTF-05 | SSE 重复 delta 不重复追加，快照与游标无竞态，回放/实时交界不丢事件 |
| TTF-06 | 游标过期取快照；网络断线不重发生成、不触发 P1 reconnect；终态可通过 GET 收敛 |
| TTF-07 | 禁用用户或撤销权限后停止事件/文件披露；任务缓存或幂等重放不能绕过权限 |
| TTF-08 | 多文件、超大、伪装格式、不可读、压缩炸弹拒绝且不入确认/解析业务链；HTML/代码不执行 |
| TTF-09 | 同键不同文件冲突；同键同文件不重复补充；接收和解析成功不代表发布 |
| TTF-10 | 运行期间上传归属待纳入；当前候选修订必须显式且使相关确认失效 |
| TTF-11 | 文件当前权限和版本严格匹配，丢失时安全空态，响应不泄漏内部路径 |
| TTF-12 | P0 终稿形成不依赖 P1 导出中心；SSE 窗口到期不清理已采纳内容或业务恢复资产 |
| TTF-13 | 累计输出、引用/风险/业务状态及游标原子一致，首次/过期恢复不遗漏或重复事件效果；终态输出不继续订阅，文本只进入原 attempt 缓冲区，不覆盖人工草稿 |
| TTF-15 | 未发布文件须由详情定位，元数据与下载均复核归属；跨 Run/Project 拒绝，未通过安全接收无字节，已清理返回安全失败；读取不触发处理且不进入正式证据 |
| TTF-14 | capabilities 返回生效限制及真实格式，超过限制由服务端强制拒绝；缺 P0 格式为验收缺口，P1/P2 false 不授权调用 |

## 变更记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.2 | 2026-10-16 | 聚焦可观察任务保证；定义未发布文件受控读取及后续验收入口 |
| v1.1 | 2026-10-16 | 区分任务与运行结果，同步无变化成功、取消竞争、失败放弃恢复及占槽规则 |
| v1.0 | 2026-10-16 | 建立任务技术投影、P0 SSE 传输恢复、单文件补充、鉴权下载及技术限制契约；明确 P1 业务恢复/通用导出边界 |

本次修订 v1.3（2026-10-16）：承接 D04 管理生效后的任务取消及安全诊断边界。

本次修订 v1.4（2026-10-16）：同步 R1-A–R4-A 及人工补充裁决；本轮细则已关闭，实现与运行验收另行跟踪。
