# API 附录：P0 操作与数据契约

文档版本：v1.28
更新日期：2026-10-30
依据：[需求基线](01_functional_requirements.md)、[领域核心](02_domain_core.md)、[API 主文](04_api_contracts.md)
适用范围：P0 设计契约；不是实现或验收通过声明。

## 1. 阅读与字段约定

本附录定义应用命令和读取投影，不允许绕过领域规则直接 CRUD 数据表。路径均省略 `/api/v1`，`P` 代表 `/projects/{project_id}`，`CW` 代表 `P/construction-workspace`，`CR` 代表 `P/construction-runs/{run_id}`，`RS` 代表 `P/research-sessions/{session_id}`，`RV` 代表 `P/review-runs/{run_id}`。这些缩写须完整展开为真实路径，不是客户端传值。

通用信封、认证、错误码、分页、幂等和权限以 [04](04_api_contracts.md) 为准；任务、SSE、文件传输以 [04-02](04-02_transport_task_file_contracts.md) 为准。下文响应类型指成功信封的 `data`；`List<T>` 的 data 为 `{items:T[]}`，分页位于 `meta.next_cursor` 和 `meta.has_more`。列表按 `created_at DESC,id DESC` 稳定排序，特定业务顺序另注明。未知写字段拒绝；所有只读字段不得回传为更新指令。

字段记法：`!` 必填且非 null，`?` 可省略，`|null` 明确允许 null；未写 null 的字段不接受 null。PATCH 省略保持原值，null 仅用于明确允许清空的字段；POST 省略使用明列默认值，不从无关历史对象推断。UUID 标识、UTC RFC3339 时间、非空不透明修订字符串分别记为 `ID`、`Time`、`Revision`。文本去除首尾空白后校验长度，正文保留内部空白。默认约束：短名称 1–200 字符、资产/文章标题1–500字符、说明 0–10000 字符、正文 1–200000 字符、查询 1–2000 字符、URL 最大 2048 字符。文件和模型参数的能力限制由服务端返回，不允许无界请求。

`RevCommand`（字段见机器schema）。更新已有对象、取消具体尝试、确认及有冲突风险的命令要求该字段；DELETE 放在同名 query 参数。缺失返回 428，失配返回 412。首次创建无既有目标时不要求 revision；涉及父对象快照的创建须提供对应输入修订。有副作用的业务 POST 按主文使用 `Idempotency-Key`；纯预览和认证例外见主文。`Confirmation={confirmation_token:string!,acknowledged_risk_ids:string[]!}` 为提交结构，token由服务端生成，绑定操作者、对象、动作、目标修订、影响范围和有效期；它不能替代 expected_revision、权限、锁或状态检查。

公共返回字段：

| 类型 | 字段与含义 |
| --- | --- |
| `Resource` | 字段见机器schema，全部只读 |
| `ActionAvailability` | 字段见机器schema；仅展示已实现分期，后端每次重新判定 |
| `Content` | `content:string,revision:Revision,content_state:agent_draft\|manual_confirm\|manual_edit,last_modified_by:ID\|null,last_modified_at:Time,source_action:string`；Agent 作者可空，不冒充人工 |
| `TaskRef` | 04-02 `TaskHandle` 的完整别名，字段及 `execution_status` 不在此重复定义；不得缩减必需字段 |
| `CommandResult` | `resource_id:ID,revision:Revision,task:TaskRef\|null`；有异步执行返回 202，否则 200；创建已持久化对象可为 201 |
| `ConfirmationPreview` | §1.1定义完整具名影响/保留结构；使用subject_revision，预览不执行业务动作 |
| `Trace` | `actor_id:ID\|null,at:Time,source_action:string,content_revision:Revision`；只保存必要追溯，不代表 P2 历史版本功能 |

仅承担确认凭据读取的详情返回 `confirmations:ConfirmationPreview[]`：检索词、补充请求、候选（含分析）、大纲、章节、Research attempt 和终稿详情；当前无合法确认动作时为空数组。WaitingItem、IngestionPreview 与 FinalizationPreview 保留各自已定义确认字段。PendingRevisionView 的 confirmations 沿用其显式结构，无适用动作时为空。其他普通详情、列表和 Workspace 显示上下文不要求附带 confirmations，也不为读取计算全部动作的影响范围。阶段确认、无证据继续、人工内容覆盖、治理、删除清理和版本采用的既有确认要求不变；普通保存只按所属操作表要求，不增加确认步骤。

可由当前详情确定范围的确认从上述详情获取；替换参数或影响范围需用户指定时，使用下列限定纯预览路由，均为 POST、不要求 Idempotency-Key，请求 `{expected_revision!,action:string!,proposed_changes?:对应目标写结构}`，响应 ConfirmationPreview。纯预览只计算影响并签发凭据，不改变业务状态；具体行为遵循 04 第 7 节。

| 预览路由 | 用例 ID / FR | 允许 action |
| --- | --- | --- |
| `CW/search-terms/action-preview` | `Construction.PreviewTermGeneration` / 017,020 | generate |
| `CR/screening/action-preview` | `Construction.PreviewScoring` / 017,022 | score |
| `CR/candidates/{candidate_id}/analysis/action-preview` | `Construction.PreviewAnalysisGeneration` / 017,025 | generate |
| `RV/outline/action-preview` | `Review.PreviewOutlineAction` / 017,032 | generate、edit、confirm |
| `RV/chapters/{chapter_id}/action-preview` | `Review.PreviewChapterAction` / 017,033 | generate、edit、confirm、apply_suggestion |
| `RV/finals/{final_id}/action-preview` | `Review.PreviewFinalAction` / 017,034 | edit、generate_components、reject |

proposed_changes 仅允许该 action 对应操作表已有可写字段，不是任意命令分发入口。DELETE 确认同时传 confirmation_token、expected_revision，风险 ID 以重复 query 参数 `acknowledged_risk_ids=x&acknowledged_risk_ids=y` 编码；仅 DELETE 可省略风险参数代表空数组，存在风险必须逐项提交。

所有 Project 资源及嵌套 ID 均校验所属 Project。P0 只有有效 Owner 可使用自己的 Project；管理员身份不提供 Project 内容访问权。可读须非 deleted，可写须 active。返回旧版本不等于错误；候选与正式已发布版本禁止互相补齐。

### 1.1 ConfirmationPreview具名影响与保留项（A07设计）

以下新增字段仍由本文维护，尚未机器转写；公共确认字段语义服从04 §6。ConfirmationPreview完整必填：confirmation_id:ID、action:string、target:{type,id}、subject_revision:Revision、impact_revision:Revision、knowledge_version_id:ID|null、candidate_revision:Revision|null、risks:{id:string,message:string}[]、expires_at:Time、confirmation_token:string、affected_items:PreviewAffectedItem[]、retained_items:PreviewRetainedItem[]、blocked_reasons:string[]。无适用版本/候选时显式null，其余不能省略；无风险/影响/保留/阻断分别[]。风险id在本预览内唯一，token非空且不透明，不记录到普通日志/SSE。

subject_revision标识该动作直接依据，expected_revision按第7节取目标/等待项修订，两者不强求相同；impact_revision绑定全部影响对象修订、选定范围及动作参数的服务端摘要身份。列表按语义身份去重、必须完整，不能静默截断后照常签发覆盖“大概范围”的token；无法形成完整预览则安全失败。blocked_reasons非空的预览仅解释不可执行原因，所含token不得用于执行；条件改变后重新预览，不能把旧阻断token自动解锁。风险提示不创建新同意制度。

`PreviewObjectRef={type,id,project_id,revision,read_url}`：全部必填；type取下表实际对象类别，id为ID，project_id为ID|null，revision为Revision|null，read_url为同源既有读取入口|null。可变被影响对象必须有准确revision，不可变knowledge_version/shared_identity依其不可变id定位可为null；按当前权限决定能否展示对象及链接。父Run/Session等定位由既有读取入口包含，不能只核验孤立id。管理员无权的私人对象不得用这个结构列出，使用治理摘要变体。

| PreviewAffectedItem.kind | 该变体其他必需字段（不接受其他变体字段） | 所属语义与边界 |
| --- | --- | --- |
| content_change | object:PreviewObjectRef、operation:replace\|edit\|reject、content_state:agent_draft\|manual_confirm\|manual_edit、content_scope:string[]、reason:string | object.type为search_term/construction_workspace/construction_candidate/review_brief/review_outline/review_chapter/review_final；只表示已授权具体内容范围，不作为PATCH载荷 |
| confirmation_invalidation | object:PreviewObjectRef、confirmation_revision:Revision、reason:string | 已确认内容或候选的依据失效；标明受影响旧确认，保留原稿，不等于删除历史 |
| execution_revocation | object:PreviewObjectRef、attempt_id:ID\|null、reason:string | object.type为construction_run/research_response_attempt/review_run/task；未分配attempt时可null；只有原治理/关联移除用例允许的执行才可列为本次终止范围 |
| association_removal | object:PreviewObjectRef、asset_kind:paper\|material、asset_revision:Revision、base_knowledge_version_id:ID | object.type与asset_kind一致，移除Project关联，不删旧版本/共享身份；与AssociationRemovalPreview.targets逐项相等 |
| private_cleanup | object:PreviewObjectRef、artifact_kind:document\|text\|vector\|graph\|private_record、reason:string | object.type为document_asset/project_record/vector_view/graph_view；由当前Project治理授权枚举实际私有对象，不暴露物理路径/桶key；共享依赖校验后才清理 |
| account_governance | account_id:ID、account_revision:Revision、operation:change_email\|enable\|disable\|grant_admin\|revoke_admin\|reset_password\|delete、summary:string | 仅已授权账号治理事实；具体邮箱参数绑定token而非从summary反解析；不得附私人Project/文件/标题/URL；摘要不是可扩大执行范围的选择器 |
| version_adoption | source:PreviewObjectRef、target_knowledge_version_id:ID、source_content_revisions:PreviewContentRevision[]、regeneration_scope:string[] | source.type为research_session/review_run；仅复制已选稳定背景或明确人工参考，绑定目标版，不能原地迁移 |

content_change.content_scope为非空、去重的封闭语义范围，按原动作裁剪：检索词生成用search_terms（列明每个受保护词对象，尚无词时用workspace）；评分用screening；候选分析用analysis；大纲用outline；章节用chapter；简报用brief；终稿允许body、abstract、references。generate_components严格等于原请求components选集（abstract/references）；终稿人工编辑只列实际改动字段，重汇总及reject列实际完整终稿范围。不得将选定摘要扩大成body或把候选分析扩大为processing；不支持的操作/范围组合拒绝。每项object.revision绑定该范围所依附的当前内容修订，服务端token同时绑定请求参数及全部范围；UI按此回显，不从reason解析。范围列表不是新增可写字段或任意JSON路径。

`PreviewContentRevision={type:research_message|review_brief|review_outline|review_chapter|review_final,id:ID,revision:Revision}`，全部必填；review_brief/outline单例id为Run ID，必须以type区分；禁止流式未采纳片段，跨Project/Run/Session引用拒绝。AdoptionPreview的source_content_revisions原object[]具体改为此数组，与version_adoption项同一集合；Research只使用稳定message，Review只使用选定参考及主题/简报，不继承确认。regeneration_scope仅既有Research背景继承/Review从头生成的安全说明，不是可执行指令。

PreviewRetainedItem为以下封闭联合：

- `kind=object`：必填object:PreviewObjectRef、reason:string。type为knowledge_version、research_session、research_message、review_run、review_outline、review_chapter、review_final、shared_identity、export_file；表示本次保持的具体对象，不获得新读取权，也不提前实现P1导出。
- `kind=protected_scope`：必填scope:shared_identity|other_projects|historical_evidence|completed_exports|existing_content、reason:string。只描述既有保留规则，不附无权ID、数量、路径或正文；用于账号治理及无法安全逐项公开的保留范围，不替代服务端真实依赖核验。不能用此摘要代替必须明示授权的覆盖/终止对象清单。

### 1.2 预览变体与既有操作、等待实体对应

| 既有入口/动作族 | 允许影响变体 | 保留与精确依据 |
| --- | --- | --- |
| 检索词生成、评分、候选分析及Review内容覆盖预览 | content_change、confirmation_invalidation | 原内容修订/内容状态、具体替换参数与下游确认；保留独立原成果；不豁免执行锁 |
| 阶段等待确认、检索词/补充/大纲/章节确认 | 仅实际发生的confirmation_invalidation；通常affected_items=[] | 确认对象/步骤与候选/KV依据，未确认不虚构旧确认；不能为了显示影响创造覆盖动作 |
| Admin.PreviewAccountAction | account_governance | 所属治理范围和安全protected_scope保留说明；管理员无权读私人Project内容，不枚举私人ID来“证明完整” |
| Project.PreviewLifecycle / PreviewCleanup | execution_revocation；cleanup另用private_cleanup | 现有Project状态/治理修订与固定影响范围；保留共享身份/他人数据/受保护旧依赖与默认保留导出；archive不物理删除 |
| Construction.PreviewClearAssociations | association_removal、execution_revocation | targets/asset_revision/基线/conflicting_runs固定；retained_items解释旧版引用与共享身份保留；新冲突须刷新，不扩大取消 |
| Research/Review.PreviewAdoption | version_adoption | 原绑定、目标KV、稳定继承内容修订；retained_items列原对象/原稿；出现新版不换目标 |
| Review.PreviewFinalization | 重新覆盖时content_change及实际失效项；首次无受保护稿confirmations=[] | source_revisions完整绑定大纲与必需章节，不给首次汇总增加token；可选缺失不阻断 |
| Review.RejectFinal | content_change(operation=reject)，只指目标final | 既有拒绝与文件清理范围；保留其他accepted成果、历史诊断；不承诺撤回下载副本 |

本表不取代每条操作的权限/确认条件，也不把所有动作都改成异步。`WaitingItem`保留id/kind/revision/confirmation/allowed_actions；confirmation为公共确认对象，subject_revision指该步骤确认快照，candidate_revision在该阶段没有候选时null，已有候选则必须匹配。ConfirmStep请求的candidate_revision按已存在机器schema允许值执行；无候选的检索词确认走原检索词入口，不伪造候选修订让请求过关。六种kind仅标识原业务等待阶段，不能由客户端新建；当前操作仅按原路由开放。

TaskWaitingRef的subject_revision是被引用实体的revision，确认对象的subject_revision是被审快照依据，两者通过具名字段区分。Research空证据确认从attempt详情confirmations读取，不能把retrieval_status=failed转为empty；补充缺标题/多候选先沿详情edit/confirm合法流程，深度结果形状留A08。A05风险同意与来源分类写入仍使用自身字段，不套通用ConfirmationPreview，也不新增“分类waiting_item”。

合法实例：关联移除预览固定paper A/r3、基线V12和冲突Run R/r5；affected_items列A的association_removal与R的execution_revocation，retained_items列V12旧引用保留；执行前出现R2则旧token不授权终止R2。非法实例：以protected_scope=existing_content替代具体人工覆盖对象、把未知revision写null、预览V13后执行偷偷改V14、管理员预览列他人文件URL，均拒绝而非补默认。

## 2. 账号、配置与模型选择

### 2.1 数据结构

下列标明机器schema的结构以[OpenAPI components.schemas](../../contracts/p0.openapi.json)为唯一字段维护位置；剩余结构继续由本文维护。范围及兼容门禁见[04-03](04-03_machine_contract_governance.md)。

- `UserView`（字段见机器schema）；用户名 1–64，邮箱最大 254，校验邮箱格式。`UserPatch`（字段见机器schema）；display_name 上限 200，账号状态和管理员身份不可在 `/me` 修改。
- `Register`（字段见机器schema）；密码 12–128 字符，只在请求接收；`Login`（字段见机器schema），identifier 为用户名或邮箱。密码策略为协议初始工程约束，不增加找回密码 P0 功能。
- `SecretWrite`（字段见机器schema）；set 必须有非空 value，clear 禁止 value；省略整个字段保持现有密钥。`SecretView`（字段见机器schema），不得返回已保存值。
- `LLMWrite`（字段见机器schema）；temperature 默认由模型能力决定，显式值须在能力范围；token 数为正整数；自定义 provider 仍须满足受支持适配协议。PATCH 使用上述可选字段加 expected_revision。
- `LLMView`（字段见机器schema）。
- `ModelSelection`（字段见机器schema）；模型名 1–200。`ModelOption`（字段见机器schema）。
- `SourceWrite`（字段见机器schema）；enabled 默认 true；速率为正数或 null 表示按 Provider 适配默认，不能越过平台限制。新增其他 provider 须先有实现的能力注册，不以任意字符串宣称支持。
`base_url`仅表示该适配器的检索服务/API入口；不是某份文件地址，也不因填入搜索网页URL就获得API能力。具体资源地址沿候选/SourceRef及手动补充协议承载，不在SourceWrite中新增文件地址字段。
- `SourceView`（字段见机器schema）。匿名源允许无密钥，api_key 模式缺密钥不能测试成功或被解析为可用。
- `ConnectionTest`（字段见机器schema）；非 LLM 的 models 为空；数据源测试返回access_mode及所测配置/凭据修订，连接成功与enabled分别展示。任务型测试先返回 TaskRef，再由结果链接读取此结构；个人数据源限定投影由SourceTaskView承载，不代表通用TaskView已全部转写。
- `SMTPWrite`（字段见机器schema）；端口 1–65535，认证字段按 auth_type 校验，GET 只返回 SecretView。
- `SecurityWrite`（字段见机器schema）；正超时/保留天数，重试次数 0–5；不得携带 P1 白名单/平台并发等字段。

参数扩展方案已接受，具体工程规则见[04-04](04-04_llm_parameter_contracts.md)，机器字段与本片覆盖随task026同步；此前“待调研”描述为历史。

### 2.2 操作表

2026-10-26已决语义：个人/系统LLM无enabled字段；发现或手填只产生待测候选，当前配置/凭据修订下逐模型显式最小测试成功才可选择。测试请求为`{model_id!}`，刷新请求为`{}`；测试结果绑定模型、配置修订及凭据修订，使用持久TaskRef/结果协议。个人投影LLMTaskView与系统投影SystemLLMTaskView分别约束Config.*和Admin.*身份；系统任务仅当前管理员可读，普通用户只读取安全ModelOption。参数规则见04-04；旧选择失效提示修复，不自动替换。已有任务凭据更新仍按08 §12.3。机器覆盖范围以覆盖清单为准，不以局部投影宣称完整Task/SSE契约已覆盖。


| 方法/路径 | 用例 ID / FR | 请求 → 响应 | 前置与失败 |
| --- | --- | --- | --- |
| GET `/auth/csrf` | `Account.GetCSRF` / 001 | 无 → `{csrf_token:string}` | 预会话或当前会话绑定；见04 |
| GET `/capabilities` | `System.ReadCapabilities` / 002,023 | 无 → 04-02 CapabilityView | 已认证只读能力，不是配置后台 |
| POST `/auth/register` | `Account.Register` / 001,005 | Register → UserView（201） | 用户名/邮箱重复 409；首位管理员资格事务互斥 |
| POST `/auth/login` | `Account.Login` / 001 | Login → `{user:UserView}` | 建立主文定义会话；凭证错误/禁用拒绝，不返回密码 |
| POST `/auth/logout` | `Account.Logout` / 001 | `{}` → `{logged_out:true}` | 仅结束当前会话；重复登出安全 |
| GET/PATCH `/me` | `Account.ReadSelf/UpdateSelf` / 001 | 无/UserPatch → UserView | 只读写本人基础信息 |
| GET/POST `/me/llm-configs` | `Config.ListLLM/CreateLLM` / 002 | 无/LLMWrite → List<LLMView>/LLMView | 私有配置；密钥只写 |
| GET/PATCH/DELETE `/me/llm-configs/{config_id}` | `Config.ReadLLM/UpdateLLM/DeleteLLM` / 002 | 无/部分LLMWrite+RevCommand/修订query → LLMView/LLMView/204无正文 | 删除不改变历史任务快照；后续选择失效须显式修复 |
| POST `/me/llm-configs/{config_id}/test` | `Config.TestLLM` / 002 | `LLMTestRequest{model_id}` → TaskRef | 使用已保存配置；冻结修订并逐模型测试，失败保留配置 |
| POST `/me/llm-configs/{config_id}/models/refresh` | `Config.RefreshModels` / 002 | `{}` → TaskRef | 不自动替换当前模型 |
| GET `/me/model-options` | `Config.ListUsableModels` / 002,007 | 无 → `{items:ModelOption[]}` | 合并个人/系统可选模型；只暴露可选信息，不泄漏系统密钥 |
| GET/PUT `/me/model-selection` | `Config.ReadSelection/SelectModel` / 002,007 | 无/`{expected_revision!,selection:ModelSelection\|null}` → `{selection:ModelSelection\|null,revision,valid,reason_code}` | null 明确清除；失效已保存选择可展示但不能启动 |
| GET/POST `/me/data-source-configs` | `Config.ListSources/CreateSource` / 003 | 无/SourceWrite → List<SourceView>/SourceView | 私有范围 |
| GET/PATCH/DELETE `/me/data-source-configs/{config_id}` | `Config.ReadSource/UpdateSource/DeleteSource` / 003 | 无/部分SourceWrite+RevCommand/修订query → SourceView/SourceView/204无正文 | 不改既有 Run 快照 |
| POST `/me/data-source-configs/{config_id}/test` | `Config.TestSource` / 003 | `{}` → TaskRef | 返回匿名/密钥失效/限流等可诊断结果 |
| GET `/admin/users` | `Admin.ListUsers` / 005 | 分页 → List<UserView> | 管理员，不附 Project 内容或私人配置 |
| POST `/admin/users/{user_id}/action-preview` | `Admin.PreviewAccountAction` / 005 | `{action:change_email\|enable\|disable\|grant_admin\|revoke_admin\|reset_password\|delete!,expected_revision!,email?:string}` → ConfirmationPreview | change_email 必填待修改 email，其余禁止 email；token绑定具体邮箱及治理影响 |
| PATCH `/admin/users/{user_id}` | `Admin.UpdateAccount` / 005 | `{expected_revision!,confirmation_token!,acknowledged_risk_ids:string[]!,action:change_email\|enable\|disable\|grant_admin\|revoke_admin!,email?}` → UserView | change_email 必填 email；其余禁止 email；最后管理员保护 |
| POST `/admin/users/{user_id}/reset-password` | `Admin.ResetPassword` / 005 | RevCommand+Confirmation → `{reset_completed:true,password_disclosed:boolean,operation_id:ID,new_password?:string}` | 新执行仅本次返回新密码、no-store；同键重放只返回 reset_completed=true、password_disclosed=false、operation_id，不再次重置、不重放密码 |
| DELETE `/admin/users/{user_id}` | `Admin.DeleteUser` / 005 | expected_revision、confirmation_token query → CommandResult | P0 普通用户；删除相关私人数据，保留共享身份及他人数据；运行中禁止后续写入或安全终止；终结按 D04 A，原终态保持，清理失败独立呈现 |
| GET/POST `/admin/llm-configs`；GET/PATCH/DELETE `/admin/llm-configs/{config_id}` | `Admin.ManageSystemLLM` / 006 | 对应 LLM 类型 → 对应 LLMView/列表/删除结果 | 与个人结构相同，scope 固定 system，限管理员 |
| POST `/admin/llm-configs/{config_id}/test`、`/models/refresh` | `Admin.TestSystemLLM/RefreshSystemModels` / 006 | 测试`{model_id!}`、刷新`{}` → TaskRef | 当前管理员读系统任务；不暴露系统密钥 |
| GET/POST `/admin/data-source-configs`；GET/PATCH/DELETE `/admin/data-source-configs/{config_id}` | `Admin.ManageSystemSources` / 006 | 对应 Source 类型 → 对应 SourceView/列表/删除结果 | 仅系统配置 |
| POST `/admin/data-source-configs/{config_id}/test` | `Admin.TestSystemSource` / 006 | `{}` → TaskRef | 连接验证，不启动构建 |
| GET/PUT `/admin/smtp-config` | `Admin.ReadSMTP/SaveSMTP` / 006 | 无/SMTPWrite+RevCommand → 脱敏SMTP配置+revision | 只保存平台发送能力，不提前实现用户通知 P1 |
| POST `/admin/smtp-config/test` | `Admin.TestSMTPConnection` / 006 | `{}` → TaskRef | P0 测试连接/认证，不隐式发送真实邮件 |
| POST `/admin/smtp-config/oauth/start` | `Admin.StartSMTPOAuth` / 006 | `{expected_revision}`+幂等键 → `{authorization_url,expires_at}` | 显式管理员会话绑定授权，不将授权链接写日志 |
| GET `/admin/smtp-config/oauth/callback` | `Admin.CompleteSMTPOAuth` / 006 | `state,code或error` → 303本地安全状态页 | 校验会话/权限/修订/一次性state；不回显code/token，不发送邮件 |
| GET/PUT `/admin/security-config` | `Admin.ReadSecurity/SaveSecurity` / 006 | 无/SecurityWrite+RevCommand → SecurityWrite+revision | 不接受 P1/P2 管理字段 |


Security执行规格：连接测试超时仅控制LLM模型发现/逐模型显式测试、Source和SMTP连接测试，不改写个人配置或扩展到业务Run。LLM实际预算取配置timeout_seconds和系统测试上限的较小值；测试内OAuth刷新共用该次预算，授权回调采用独立有限技术超时。每次测试执行固定已解析的安全设置修订/预算，后续测试重新解析；不追溯改写已完成结果。

connection_retry_count只允许重试能证明尚未提交任何应用请求的连接建立失败，最多该次数；无证据则不重试。不重试认证拒绝、权限/配置失效、已提交结果未知、可能收费的模型请求或Worker租约过期；OAuth授权码交换/刷新提交结果未知同样不能盲目重放。每次外发重新检查当前权限/配置资格，退避仍受总预算和租约约束。该限制不新增P0业务重试入口。

诊断采用固定字段白名单：minimal为关联ID、阶段、状态和安全错误分类；standard可增加耗时、内部尝试次数及脱敏协议类别。两级均不得含密钥、OAuth code/token、业务正文、物理路径或Provider原始错误，不扩大管理员读取私人配置/任务的权限。配置快照保留期只清理独立可清理诊断，不删任务输入/结果引用、冻结配置、人工确认或审计；清理须有资格判断和测试证据，不能仅按创建时间级联删除Task。

SMTP OAuth补充（2026-10-26，D-SMTP-03 A已批准）：Gmail/Microsoft 365的Token模式由应用处理管理员显式授权及自动刷新；部署方注册OAuth应用，管理员维护client ID/必要client secret/Microsoft租户配置。不得把单个secret输入的现有机器结构解释为完整OAuth契约。实施时须增补应用配置、授权开始/回调和连接状态的机器结构及用例，沿用系统SMTP单例，不新增Profile集合。凭据使用独立加密存储和脱敏视图，access/refresh token不进入Task输入、业务快照、日志或前端响应。

授权开始须绑定当前管理员会话、SMTP配置身份/修订、Provider和预登记回调；回调校验一次性state、期限、PKCE及当前管理员资格，拒绝切号、重复/过期、配置已修改及Provider不匹配的回调，不覆盖其他管理员的新配置。授权/令牌URL由明确Provider适配提供，不接受任意回调跳转或任意Token端点。授权码与token交换的敏感响应不写入普通日志；回调完成后跳转到不含code/state的本地状态页。保存配置不隐式触发授权或连接测试。

按需刷新绑定原Provider、OAuth应用与SMTP账号；并发刷新需串行或等价提交保护，轮换后的refresh token与修订原子保存，旧响应不能覆盖新凭据。同绑定下自动刷新属于凭据更新，不改冻结业务配置；更换Provider、应用、租户、SMTP账号或认证模式后旧授权不可作为新绑定凭据。refresh失败分为暂时不可用和需重新授权，返回安全原因；不能换用其他邮箱/模式，不能因授权成功直接标记SMTP测试成功。执行与结果提交仍检查当前权限及任务资格；撤销管理员资格不得被回调或迟到刷新恢复。P0只执行配置授权与SMTP连接/认证测试，不发送邮件。

上述为已批准能力的执行约束；机器schema、运行端点、存储及验收测试尚未实现，不以本文新增文字声明其已交付。授权/刷新外部服务默认mock；真实OAuth应用注册、账号授权或发信不由本次本地实现授权自动执行。

单例初始化：`GET /me/model-selection` 必须返回已初始化的 revision，首次 selection=null、valid=false。`GET /admin/smtp-config` 返回 `{revision,configured:false,config:null}` 直到首次保存，配置后 `{revision,configured:true,config:脱敏SMTPView}`；`GET /admin/security-config` 返回 `{revision,configured:boolean,effective:SecurityWrite}`，首次使用部署默认值（连接超时30秒、自动连接重试0次、诊断快照保留30天、diagnostic_scope=minimal）且 configured=false。保留天数仅用于可清理诊断快照；历史Run复现必需的冻结配置、人工确认和引用依赖不得据此删除，具体清理仍受领域保留规则约束。相应 PUT 返回同一读取结构，使首次保存无需猜测 revision；初始化不创建任何密钥，SecretView.configured=false、hint=null。

配置连接测试真实执行时存在外部网络调用；自动化验证默认 Mock，真实测试另行指定目标。保存配置不等于连接测试成功，也不等于可启动任务。

## 3. Project 与 Workspace

`ProjectWrite`、`ProjectPatch`、`ProjectView` 字段以机器schema为准。创建描述/范围默认空串，PATCH不补默认值；Owner与status不可由通用写请求修改。

`ObjectRef`、`WorkspaceContextWrite`、`WorkspaceDraft` 的字段以机器schema为准；drafts 每个对象/part 唯一，上限 50，单草稿正文上限 200000；不包含运行状态、KV 或资产编辑字段。`WorkspaceView` 字段以机器schema为准。

| 方法/路径 | 用例 ID / FR | 请求 → 响应 | 前置/失败及影响 |
| --- | --- | --- | --- |
| GET/POST `/projects` | `Project.List/Create` / 008 | 分页/ProjectWrite → List<ProjectView>/ProjectView | 创建 Owner=当前用户，默认 active；列表默认排除 deleted |
| GET/PATCH `P` | `Project.Read/Update` / 008 | 无/部分ProjectWrite+RevCommand → ProjectView | 更新限 active；禁止状态和 Owner 通用修改 |
| POST `P/action-preview` | `Project.PreviewLifecycle` / 008 | `{action:archive\|delete!,expected_revision!}` → ConfirmationPreview | 展示范围和活跃任务，不以存在活跃任务新增拒绝卡口；执行资格立即撤销、异步安全终止，见 D04 A |
| POST `P/archive` | `Project.Archive` / 008 | RevCommand+Confirmation → ProjectView | 不新增解除归档能力；生效即撤销写资格，受影响非终态执行安全终止为 cancelled，已终态不改 |
| DELETE `P` | `Project.SoftDelete` / 008 | expected_revision、confirmation_token query → 204无正文 | 软删除不破坏共享身份和他人数据；不允许继续 Workspace |
| POST `P/cleanup-preview` | `Project.PreviewCleanup` / 008 | RevCommand → ConfirmationPreview | 私有资产清理影响清单；完成导出默认保留 |
| POST `P/cleanup-confirm` | `Project.Cleanup` / 008 | RevCommand+Confirmation → CommandResult | 重新检查影响范围及当前写资格，撤销后续写入或安全终止；不可清理不假装成功 |
| GET `P/workspace` | `Workspace.Open` / 011,013 | 无 → WorkspaceView | 无效记录安全回退并给原因；不恢复为写权限 |
| PUT `P/workspace/context` | `Workspace.SaveContext` / 013 | WorkspaceContextWrite → `{revision,saved_at}` | 用户+Project 隔离；active 可保存，archived 只读取服务端上下文，未提交输入可本地保留 |

Project.List可携带可选`X-Expected-Actor` UUID请求头，作为浏览器当前显示账号的一致性断言；与已认证主体不符返回401 `AUTH_SESSION_INVALID`，不能凭该头选择Owner或获得权限。列表当前仅支持page_size/cursor；固定非deleted范围与created_at/id降序，不接受未声明筛选或排序。

Workspace 草稿保存不是章节/检索词内容保存；业务写入必须调用所属对象命令。恢复旧草稿时保留 base_revision，保存时重新做并发校验。

## 4. Construction 配置、补充请求与候选处理

### 4.1 结构

- `SourcePolicy={mode:all_resolvable|selected!,source_refs?:{source:user|system,config_id:ID}[]}`；all_resolvable 禁止 source_refs，selected 必须非空。
- `SearchTermWrite={query:string!,keywords?:string[],synonyms?:string[],exclusions?:string[],rationale?:string,coverage?:string,source_policy?:SourcePolicy,auto_update_enabled?:boolean}`；字符串数组每项1–200、最多100项；缺省数组空，理由/覆盖空串，source_policy 默认 all_resolvable，auto_update_enabled 默认 true。
- `SearchTermView=Resource+SearchTermWrite+{status:candidate|accepted,content_state:agent_draft|manual_edit|manual_confirm,confirmed_revision:Revision|null,confirmed_at:Time|null,modified_by:ID|null,modified_at:Time,confirmations:ConfirmationPreview[],source_dependencies?:TermSourceDependencies}`；不存在独立 enabled 字段。
- `ConstructionWorkspaceView=Resource+{auto_update_enabled:boolean,scheduler_available:boolean,occupying_run_id:ID|null,pending_supplement_count:integer,pending_revision_count:integer}`；P0 scheduler_available=false。
- `SupplementCreate={kind:paper|material!,source:{type:doi|arxiv_id|url!,value:string!},title?:string}`；paper 可 DOI/arXiv/URL，material 只 URL；单文件使用下表 upload。`SupplementView=Resource+{kind,source,title:string|null,content_format:string|null,metadata_candidates:MetadataCandidate[],resolution_status:pending|resolved|ambiguous|failed,confirmation_status:unconfirmed|confirmed,inclusion_status:pending|processing|published,assigned_run_id:ID|null,published_version_id:ID|null,error:TaskError|null}`；未解析不伪造 title/format，ambiguous 必须用户选择。
- `SupplementPatch={expected_revision!,title?:string,selected_candidate_id?:ID,source_note?:string,metadata?:{doi?:string|null,arxiv_id?:string|null,title?:string,authors?:string[],year?:integer|null}}`；metadata 仅 paper；source_note为1–10000字符的人工来源说明，供关键元数据不足时确认依据；资料不强制作者/年份/语言/provider。
- `PendingRevisionCreate` 不再是公开写 DTO。已发布 paper/material 只读；移除必须走 association-clear-preview/confirm，由服务端生成仅 operation=exclude、changes={} 的 PendingRevisionView 并直接关联移除构建；不得借 pending revision 修改已发布内容。
- `RetrievalConstructionStart={mode?:retrieval,selected_terms:{term_id:ID,confirmed_revision:Revision}[]!,supplement_ids?:ID[],retrieval_range:{published_from:Time|null,published_until:Time|null}!,result_limit_per_source:integer!,model_selection:ModelSelection!,graph_mode?:incremental|rebuild}`；默认空补充范围、incremental；检索时间为左闭右开，null 表示该端无界，两端同时非空时from<until；result_limit_per_source为1–1000，每个解析后数据源按全部选中检索词累计返回上限，服务端能力上限更低时明确拒绝而不静默截断；去重后数量可更少。首次构建实际创建图谱。selected_terms 必须非空，表示常规检索构建；ConstructionStart 的另一分支见下文。
- `ConstructionStart` 为按 `mode` 判别的联合：`mode=retrieval`（省略时默认）使用 RetrievalConstructionStart；`mode=revision_only` 使用 `RevisionOnlyConstructionStart={mode:revision_only!,supplement_ids?:ID[],model_selection?:ModelSelection}`。公开启动的 supplement_ids 必须非空且不重复，补充须已确认；移除型 revision_only 仅由风险确认命令内部创建并填充 pending_revision_ids，公开启动不得指定该字段。不接受 selected_terms、retrieval_range、result_limit_per_source 或 graph_mode，不伪造检索配置。只有实际处理需要 LLM 时 model_selection 必填；纯关联移除不要求模型或检索来源。
- `InputRevisionView={revision:Revision,source_revision:Revision|null,created_at:Time,reason:string,input_snapshot:ConstructionInputSnapshot}`。Run 详情另返回 `effective_input_revision:Revision|null`，首次冻结前为 null，冻结后指向有效输入修订。初始 input_snapshot 保持不可变，后续修订只追加；追加词命令见4.2；不能通过通用 PATCH 改值。
- `ConstructionRunView=Resource+{status:string,phase:string,base_knowledge_version_id:ID|null,published_knowledge_version_id:ID|null,completion:ConstructionCompletion|null,input_snapshot:ConstructionInputSnapshot|null,config_snapshot:RuntimeConfigSnapshot|null,candidate_revision:Revision|null,candidate_version:CandidateVersionView|null,steps:StepView[],waiting_items:WaitingItem[],task:TaskRef|null,available_actions:ActionAvailability[]}`；status 仅使用领域允许状态，未取得槽并冻结输入前快照为 null，快照不包含密钥；completion 仅 succeeded 非空，不是新状态。
- `CandidateVersionView={state:preparing|ready_to_publish|published|discarded,revision:Revision,closing_reason:{code:published|cancelled|abandoned|cleanup|no_change,message:string}|null}`；依次映射 [02-02 第 10.3 节](02-02_construction_versioning_appendix.md#103-候选版本状态机)的准备中、待发布、已发布、已废弃，不新增领域状态。尚未产生候选时 candidate_version 与 candidate_revision 均为 null；存在时 candidate_revision 必须等于 candidate_version.revision，不混用 Run 修订或单条 CandidateView 修订。准备中/待发布的 closing_reason 为 null，已发布为 published，已废弃按实际裁决记录取消、明确放弃、清理或 no_change；no_change 的 message 明示“核验无变化”，不能将候选标为已发布。该投影只反映持久状态，不授权客户端修改状态或通过 CandidateView 推导整体就绪。
- `ConstructionCompletion={outcome:published|no_change,verified_knowledge_version_id:ID|null,checked_at:Time,checked_scope:ConstructionInputSnapshot}`；published 时 published_knowledge_version_id 必有值并属于本 Run，verified_knowledge_version_id 为基线（首次可空）；no_change 时 published_knowledge_version_id 必为空，verified_knowledge_version_id 必为核验的既有基线。checked_scope/checked_at 记录本轮实际完成核验的范围及时间，不修改既有 KnowledgeVersion 的截止时间。failed/cancelled 不填成功结果。no_change 需完成内容一致性核验，首次无版本、检索失败或仅零新增均不成立；候选收尾为已废弃并记录“核验无变化”。
- `StepView={id:ID,kind:string,state:string,result_summary:object,error:object|null}`；`WaitingItem={id:ID,kind:search_terms|retrieval|screening|processing|analysis|ingestion_preview,revision:Revision,confirmation:主文完整确认对象,allowed_actions:string[]}`。
- `CandidateView=Resource+{kind:paper|material,title:string|null,source_refs:SourceRef[],deduplication:{decision:string,reason:string,matched_project_asset_id:ID|null},screening:ScreeningView,processing:ProcessingView,analysis:PaperAnalysis|MaterialAnalysis|null,content_state:string,confirmed_revision:Revision|null}`。论文 analysis 包含 `one_sentence_summary,highlights[],relevance_points[],methods,innovations[]`；资料 analysis 为 `important_summary,relevance_points[]`。
- `CandidatePatch={expected_revision!,metadata?:部分PaperMetadata或MaterialMetadata,screening?:{score?:number,valid?:boolean,reason:string!},analysis?:PaperAnalysis或MaterialAnalysis}`；metadata 限 SupplementPatch 已允许字段，资料仅标题/格式识别修正；修改使依赖下游结果失效，不改变启动配置。
- `IngestionPreview={revision:Revision,base_knowledge_version_id:ID|null,valid_papers:ID[],valid_materials:ID[],skipped:object[],failed:object[],degraded:object[],non_knowledge_items:object[],risks:object[],waiting_item:WaitingItem}`。


M-P0-11工程细化：生成只追加候选，不提供覆盖已有词的分支；确认候选即接受进入长期列表，批量动作按逐词命令执行，遇到冲突停止并保留已完成项。`query`为1–10000字符，rationale/coverage最多10000字符；来源引用最多100项且去重。确认快照另冻结修改来源、修改人/时间，确认token绑定主体、Project、词及修订，有效期10分钟，跨应用实例可验证。弃用后幂等重放只返回最小DiscardedTermView，不再返回候选正文。

本片WorkspaceView增加 `topic_source:MaterialSourceIdentity` 与最近20项 `generation_tasks:TermGenerationTaskView[]`。已保存的Project名称/描述/研究范围按其内容修订注册historical_input来源，默认private/unconfirmed；用户显式分类后再按本人Project政策决定Agent资格。本次追加文字绑定actor、Project和生成任务ID的current_submission；派生词记录完整主题来源修订和本次提交scope。任务的受理、派发、提交记录当前政策/分类修订及判定（不含正文/凭据），业务输入另外冻结。权限放宽不自动重做已失败任务，未知外呼结果不得自动重发。任务只经通用Task/SSE读取，成功返回词引用，不生成KnowledgeVersion。

### 4.1.1 候选、修订与输入快照的最小结构

- D-CW-02 A：P0初始评分尺度固定0–10、系统默认阈值7、score≥7初判有效；阈值和来源、理论/技术/Project相关性理由及模型依据应可读可追溯。失败保持未判定，不伪造0分；人工调整和覆盖保护沿原命令。具体新增机器字段随评分实现转写，不把本次设计同步称为运行交付。
- `ScreeningView={score:number|null,score_scale:{min:number,max:number}|null,valid:boolean|null,threshold_source:string|null,reason:string|null}`；未评分时score/scale为null，已有评分须在公开scale范围内；确认前valid可空。候选与正式资产复用此投影，正式资产只展示其版本固化值。
- `PaperMetadata={doi:string|null,arxiv_id:string|null,title:string,authors:string[],year:integer|null,abstract:string|null,url:string|null}`；年份1–9999，title必需，authors可空。`MaterialMetadata={title:string,content_format:string,primary_source:SourceRef}`，格式必须为04-02支持列表。
- `DraftPaperMetadata` 具有 PaperMetadata 的同名字段，但 title/其他未知标量允许null、authors默认[]；`DraftMaterialMetadata={title:string|null,content_format:string|null,primary_source:SourceRef|null}`。仅元数据草稿使用宽松结构，确认与正式资产按所需字段校验。
- `MetadataCandidate={id:ID,metadata:DraftPaperMetadata|DraftMaterialMetadata,extraction_source:file|identifier|provider|agent,conflicts:{field:string,reason:string}[],requires_confirmation:boolean}`；kind由补充请求决定联合分支。
- `SourceRef={source_kind:provider|url|upload,provider_config_ref:{source:user|system,config_id:ID}|null,url:string|null,supplement_id:ID|null,search_term_id:ID|null,retrieved_at:Time|null}`；不能包含本地路径，upload以supplement_id关联授权范围。
- `PendingRevisionView=Resource+{target_kind:paper|material,target_id:ID,base_asset_revision:Revision,operation:string,changes:RevisionChanges,reason:string,submitted_by:ID,inclusion_status:pending|processing|published,assigned_run_id:ID|null,published_version_id:ID|null,confirmations:ConfirmationPreview[]}`。
- `RevisionChanges={}`；仅内部 exclude 记录使用。已发布目标不接受 metadata_correction、text_supplement、analysis_revision；未入库候选使用 CandidatePatch 及候选来源替换命令。
- `PaperAnalysis={one_sentence_summary:string,highlights:string[],relevance_points:string[],methods:string,innovations:string[]}`；`MaterialAnalysis={important_summary:string,relevance_points:string[]}`；文字字段1–10000，数组最多100项、单项1–2000。CandidatePatch.analysis以候选kind选择此结构；metadata以相应Metadata结构选择。
- `RetrievalInputSnapshot={mode:retrieval,selected_terms:{term_id:ID,confirmed_revision:Revision,content:SearchTermWrite}[],supplement_ids:ID[],pending_revision_ids:ID[],retrieval_range:{published_from:Time|null,published_until:Time|null},result_limit_per_source:integer,resolved_sources:SourceRef[],graph_mode:incremental|rebuild,base_knowledge_version_id:ID|null,frozen_at:Time}`。
- `ConstructionInputSnapshot` 为 `mode` 联合：retrieval 使用 RetrievalInputSnapshot；revision_only 为 `{mode:revision_only,supplement_ids:ID[],pending_revision_ids:ID[],base_knowledge_version_id:ID|null,frozen_at:Time}`。初始快照、后续有效修订及 completion.checked_scope 都使用此联合；revision_only 不伪造检索时间或数据源。RuntimeConfigSnapshot 的 model_selection 在不需要 LLM 时为 null，parameters 两项也为 null，resolved_source_config_revisions=[]；其他任务仍按原所需配置校验。
- `RuntimeConfigSnapshot={model_selection:ModelSelection|null,parameters:{temperature:number|null,max_output_tokens:integer|null},config_revision:Revision,resolved_source_config_revisions:{config_id:ID,revision:Revision}[],captured_at:Time}`；服务端冻结结果，无密钥或认证参数。

SupplementView 与 CandidateView 另返回只读 `document_refs:ID[]`，列出该请求/候选实际关联且当前允许读取的 DocumentAsset 身份；无可读文件为 []。它们不表示文件已发布、可检索或可作正式证据；文件访问仍逐次复核。

### 4.2 操作

| 方法/路径 | 用例 ID / FR | 请求 → 响应 | 前置/拒绝 |
| --- | --- | --- | --- |
| GET/PATCH `CW` | `Construction.ReadWorkspace/SaveConfig` / 020 | 无/`{expected_revision!,auto_update_enabled?:boolean}` → ConstructionWorkspaceView | 可保存策略，P0 不触发自动任务 |
| GET/POST `CW/search-terms` | `Construction.ListTerms/AddTerm` / 020 | 分页/SearchTermWrite → List<SearchTermView>/SearchTermView | 新建为未确认；手工输入与生成同等可追溯 |
| GET/PATCH/DELETE `CW/search-terms/{term_id}` | `Construction.ReadTerm/EditTerm/DeleteTerm` / 020 | 无/部分SearchTermWrite+RevCommand/修订query → SearchTermView/SearchTermView/204无正文 | 不修改历史 Run 快照；实质编辑清除当前确认有效性 |
| POST `CW/search-terms/generate` | `Construction.GenerateTerms` / 020 | `{expected_revision!,model_selection!,additional_requirements?:string,confirmation_token?:string,acknowledged_risk_ids:string[]!}` → TaskRef | 已有人工内容的覆盖需具体授权，否则保留原内容 |
| GET `CW/source-options` | `Construction.SourceOptions` / 020 | 无 → `{sources:TermSourceOption[],rejected:TermSourceOption[],valid:boolean,reason_code:string|null}` | 仅当前主体可见配置的安全投影，无凭据；拒绝项保留原因，不替换显式选择 |
| POST `CW/search-terms/{term_id}/discard` | `Construction.DiscardTerm` / 020 | RevCommand → `{id,revision,status:discarded,discarded_at:Time}` | 仅候选；删除候选正文，仅保留归一化查询摘要及必要幂等回执 |
| POST `CW/search-terms/{term_id}/confirm` | `Construction.ConfirmTerm` / 020 | RevCommand+Confirmation → SearchTermView | 详情confirmations提供当前确认token；保存确认快照，不自动启动 Run |
| GET/POST `CW/supplements` | `Construction.ListSupplements/SubmitSupplement` / 023 | 分页/SupplementCreate → List<SupplementView>/`{supplement:SupplementView,task:TaskRef}` | 返回202；接收不等于入库 |
| POST `CW/supplements/upload` | `Construction.UploadSupplement` / 023,024 | multipart `file!,kind:paper\|material!,title?` → `{supplement:SupplementView,task:TaskRef}` | 单文件；格式/大小按04-02；paper仅PDF |
| GET/PATCH `CW/supplements/{supplement_id}` | `Construction.ReadSupplement/CorrectSupplement` / 023 | 无/SupplementPatch → SupplementView | 仅未入库确认的请求可修改；已冻结范围走候选修正，已发布同身份须先完成移除再显式新导入 |
| GET `CW/supplements/{supplement_id}/file-access` | `Construction.AccessSupplementFile` / 023,024 | `document_asset_id!` query → 04-02 UnpublishedFileAccess | 只读该请求实际关联且可安全读取的文件；不解析、不确认、不纳入 |
| GET `CR/candidates/{candidate_id}/processing-text` | `Construction.ReadProcessingText` / 024 | 无 → 原始提取全文、整理全文、处理修订、页段及行映射 | 当前Project/Run/候选完整归属鉴权；no-store；不接受知识版本或任意对象ID，不写状态 |
| GET `CR/candidates/{candidate_id}/file-access` | `Construction.AccessCandidateFile` / 024 | `document_asset_id!` query → 04-02 UnpublishedFileAccess | 校验 Project/Run/候选/文件完整归属，不作为正式研究证据入口 |
| GET `CW/supplements/{supplement_id}/files/{document_asset_id}/download`、`CR/candidates/{candidate_id}/files/{document_asset_id}/download` | `Construction.DownloadUnpublishedFile` / 023,024 | 无 → 鉴权文件流 | 与 file-access 同等当前权限、生命周期和安全接收检查；不接受 knowledge_version_id |
| POST `CW/supplements/{supplement_id}/confirm` | `Construction.ConfirmSupplement` / 023 | RevCommand+Confirmation → SupplementView | 详情confirmations提供当前确认token；关键元数据冲突、资料标题缺失禁止确认；仅进入待纳入 |
| GET `CW/pending-revisions` | `Construction.ListPendingRevisions` / 023,026 | 分页 → List<PendingRevisionView> | 只读已受理关联移除记录，无独立 POST；不能重复绑定其他构建 |
| POST `CW/association-clear-preview` | `Construction.PreviewClearAssociations` / 023,026 | RevCommand+AssociationSelection → AssociationRemovalPreview | 单条/多条/全部统一预览；绑定实际成员及修订、基线、冲突构建，不物理清理 |
| POST `CW/association-clear-confirm` | `Construction.ClearAssociations` / 023,026 | RevCommand+Confirmation → `{run:ConstructionRunView,task:TaskRef,pending_revisions:PendingRevisionView[]}`（202） | 一次确认授权已列明冲突构建安全终止及自动创建 revision_only 移除构建；无需再启动或再确认入库；发布后生效 |
| GET/POST `P/construction-runs` | `Construction.ListRuns/Start` / 014,020–026 | 分页/ConstructionStart → List<ConstructionRunView>/`{run:ConstructionRunView,task:TaskRef}` | 按 mode 校验已确认输入及实际需要的模型/来源；retrieval来源采用D-CW-01 A逐词部分继续，selected失效整词拒绝，全部不可执行不受理，失败项随输入保存且可诊断；排队不占槽，取得槽后冻结最新基线；revision_only 不检索；有意全移除可发布空版本 |
| GET `CR` | `Construction.ReadRun` / 014–016 | 无 → ConstructionRunView | 历史读取与当前配置分离 |
| GET `CR/input-revisions` | `Construction.ReadInputRevisions` / 022 | 分页 → List<InputRevisionView> | 同 Run 初始及显式修订记录，按 created_at ASC；只读，不创建输入修订 |
| POST `CR/append-search-terms` | `Construction.AppendSearchTerms` / 022 | `{expected_revision!,selected_terms:{term_id:ID,confirmed_revision:Revision}[]!,reason:string!}` → `{run:ConstructionRunView,task:TaskRef}`（202） | 非空且仅追加新已确认词；筛选等待阶段、剩余预算及冻结来源检查；建立输入修订，保留原人工选择 |
| POST `CR/candidates/{candidate_id}/replace-source` | `Construction.ReplaceCandidateSource` / 023–025 | `{expected_revision!,supplement_id:ID!,supplement_confirmed_revision:Revision!}` → CandidateView | 仅入库确认前；同Project同kind已确认补充及其不可变来源；原子核验确认修订，拒绝已发布或被其他Run占用的补充，互斥处理；替换重新核验身份/元数据/去重并使依赖处理及确认失效，不直接接收路径或已发布资产修改 |
| GET `CR/candidates`、`CR/candidates/{candidate_id}` | `Construction.ReadCandidates` / 022–025 | 分页/无 → List<CandidateView>/CandidateView | 只读本 Run 候选；禁止传给正式研究 |
| PATCH `CR/candidates/{candidate_id}` | `Construction.EditCandidate` / 017,022,025 | CandidatePatch → CandidateView | expected_revision 校验；计算中冲突拒绝；改变范围使相关确认失效 |
| POST `CR/candidates/{candidate_id}/deduplication-decision` | `Construction.CorrectDeduplication` / 022 | `{expected_revision!,decision:distinct\|match!,matched_project_asset_id?:ID,matched_candidate_id?:ID,matched_candidate_revision?:Revision,reason:string!}` → CandidateView | match目标二选一：同Run候选（同时必须提交matched_candidate_revision，原子校验目标当前修订）或同Project资产；distinct不带匹配目标，可撤销误合并，保留原决定追溯。当前运行切片仅支持同Run候选；资产目标待发布能力实现 |
| POST `CR/screening/score` | `Construction.ScoreCandidates` / 022 | `{expected_revision!,candidate_ids:ID[]!,confirmation_token?:string,acknowledged_risk_ids:string[]!}` → TaskRef | 使用本Run冻结模型配置对当前有效候选重新评分，不允许换model_selection；人工覆盖须先生成确认预览，不自动改确认结果 |
| POST `CR/candidates/{candidate_id}/analysis/generate` | `Construction.GenerateAnalysis` / 025 | `{expected_revision!,confirmation_token?:string,acknowledged_risk_ids:string[]!}` → TaskRef | 使用本Run冻结模型配置和已确认处理文本，禁止变更model_selection；P0阶段重生成，不是P1通用重跑 |
| GET `CR/ingestion-preview` | `Construction.PreviewIngestion` / 026 | 无 → IngestionPreview | 明列失败/降级等；失败或零结果不得伪造可发布，有意移除全部按统一确认及空版本发布规则 |
| POST `CR/waiting-items/{waiting_item_id}/confirm` | `Construction.ConfirmStep` / 016,022,024–026 | `{expected_revision!,subject_revision!,candidate_revision!,confirmation_token!,acknowledged_risk_ids:string[]!}` → CommandResult | token绑定具体等待项、步骤及快照；风险未确认/候选已改拒绝 |
| POST `CR/cancel` | `Construction.Cancel` / 015 | `{expected_revision!,attempt_id:ID\|null!}` → CommandResult | 无已分配执行身份时 attempt_id 才可为空，按 Run ID 和修订取消；与 published/no_change 完成排他裁决；旧 Worker 写资格先失效再释放槽；请求接收不等于清理完成；failed 放弃恢复不改 cancelled |

输入冻结后新上传默认待下一轮；同 Run 返回检索只允许手动 retrieval Run 的筛选等待点追加已确认词，不允许其他阶段或 revision_only。保留原词、原解析来源集合、时间范围、每源总预算、模型、配置和知识基线；新词来源策略不得引入新来源，按剩余额度执行，额度已耗尽拒绝。只合并新增候选并重新去重/筛选，原人工决定及无关结果保留；受影响确认失效，旧执行资格撤销，迟到结果不得写入新输入修订。发布只由 Construction 内部执行。

`AssociationSelection` 为封闭联合：`{scope:selected,targets:{kind:paper|material,id:ID}[]}` 或 `{scope:all,kind:paper|material|all}`；selected 非空去重，all 在预览时解析为准确集合，不能随排队扩大。`AssociationRemovalPreview=ConfirmationPreview+{targets:{kind,id,asset_revision:Revision}[],base_knowledge_version_id:ID,conflicting_runs:{run_id:ID,revision:Revision,reason:string}[],will_be_empty:boolean}`。基线无版本或无目标拒绝空操作；预览展示旧引用保留、未来范围减少及空库后果。确认 token 绑定全部字段；确认时/取得写槽时重新检查，基线、目标修订或冲突范围变化要求刷新预览，不能静默扩大取消范围。撤销列明冲突构建写资格后才能让槽；无关任务不终止。幂等重放返回同一移除 Run；自动发布只使用已持久化的风险确认，不再要求第二次手动入库确认。失败/取消默认版本不变；有意全移除产生 published 空版及一致空索引/图谱，不记为 no_change。

入库确认受理后锁定本批所有 paper/material 候选内容，PATCH、去重修正、重新评分、分析生成及来源替换均拒绝；发布后资产只读。入库前编辑需无冲突处理任务、修订匹配并失效受影响处理/确认。若当前版本已含目标，显式重新导入提示先移除；移除发布后才允许新导入，重新确认内容，不复用旧人工确认。自动检索命中不得复活人工排除；旧版本/证据引用不变。

## 5. 知识读取与采用新版本

`KnowledgeVersionView={id:ID,project_id:ID,construction_run_id:ID,published_at:Time,retrieval_cutoff_at:Time|null,counts:{papers:integer,materials:integer},is_latest:boolean}`。仅返回已发布版本。`AssetView={id:ID,project_id:ID,knowledge_version_id:ID,asset_revision:Revision,title:string,metadata:PaperMetadata|MaterialMetadata,processing:ProcessingView,analysis:PaperAnalysis|MaterialAnalysis|null,screening:ScreeningView,document_refs:ID[],graph_refs:ID[],unavailable_reason:string|null}`；材料额外 `content_format,primary_source`；candidate_sources 为独立候选来源线索投影，不修改已发布元数据，也不是正式证据。

`EvidenceRef={id:ID,project_id:ID,knowledge_version_id:ID,asset_kind:paper|material,asset_id:ID,document_asset_id:ID|null,locator:EvidenceLocator|null,graph_node_ids:ID[],text_source_kind:string}`。`EvidenceLocator={kind:page|paragraph|text_range,page_number?:integer,paragraph_id?:string,start_offset?:integer,end_offset?:integer}`；page要求页码≥1，paragraph要求段落ID，text_range要求0≤start<end；禁止不属kind的字段和内部路径。`ProcessingView={status:pending|processing|available|degraded|failed|unsupported,text_source_kind:full_text|abstract_fallback|user_text|material_text|null,failure_reason:string|null,participates_in_knowledge:boolean}`；具体读取只呈现该版本保存的最终来源，不拼接候选。`GraphView={project_id,knowledge_version_id,nodes:{id,label,kind,evidence_ids[]}[],edges:{id,source,target,label,evidence_ids[]}[]}`；分页使用公共 meta。

| 方法/路径 | 用例 ID / FR | 请求 → 响应 | 约束 |
| --- | --- | --- | --- |
| GET `P/knowledge-versions`、`/{version_id}` | `Knowledge.ListVersions/ReadVersion` / 012,018 | 分页/无 → 列表/KnowledgeVersionView | 本 Project 已发布范围 |
| GET `P/knowledge-version-changes` | `Knowledge.CompareVersions` / 018 | `from_version_id?,to_version_id!` query → `{from_version_id,to_version_id,changes:{kind:added\|corrected\|excluded\|source_changed\|degraded\|failed,asset_kind:paper\|material,asset_id:ID\|null,summary:string,risk_kind:none\|scope_exclusion\|retraction\|correction\|parse_error\|source_unavailable,source_url:string\|null,observed_at:Time}[]}`，分页为公共meta | 事实变化清单；省略from仅允许to为首次发布版本，表示空基线；其他比较须显式指定同Project已发布from。to晚于from；不冒充章节级影响分析 |
| GET `P/papers`、`P/materials` | `Knowledge.ListPapers/ListMaterials` / 012 | knowledge_version_id?、cursor?、page_size?、q?、合法过滤条件 → List<AssetView>+实际knowledge_version_id | 缺省固定当前默认版本；后续游标绑定该版本 |
| GET `P/papers/{asset_id}`、`P/materials/{asset_id}` | `Knowledge.ReadAsset` / 012,028,033 | knowledge_version_id? → AssetView | 引用入口必须显式版本；不得跨版本补齐文件/分析 |
| GET `P/graph` | `Knowledge.ReadGraph` / 012,028,033 | knowledge_version_id?、focus_node_id?、cursor? → GraphView | 只读；无任意图查询语句或写指令 |
| GET `P/evidence/{evidence_id}` | `Knowledge.ResolveEvidence` / 028,033 | knowledge_version_id! → EvidenceRef | 版本不匹配/缺失返回安全失败，不改写引用 |
| GET `P/papers/{asset_id}/file-access`、`P/materials/{asset_id}/file-access` | `Knowledge.AccessFile` / 012,028,033 | knowledge_version_id!、document_asset_id! → 04-02 FileAccess | 每次校验文件归属和当前权限 |

文件代理下载 `GET P/files/{asset_id}/download?knowledge_version_id=...`（`Knowledge.DownloadFile` / FR-012,028,033）使用04-02定义的授权二进制响应；file-access的asset_id为DocumentAsset身份，与论文/资料ID区分。

论文过滤query：title/abstract/author/source为可选1–200字符字符串，score_min/score_max为可选有限数且min≤max、按资产返回的score_scale解释；valid/cited为可选boolean，push_status可选not_enabled|not_sent|sent|failed。资料过滤query：title/source为可选1–200字符，content_format为04-02已支持格式枚举，processing_status可选pending|processing|available|degraded|failed|unsupported，participates_in_knowledge为可选boolean。q为可选1–200字符全文匹配词；未列字段拒绝，不接受任意排序表达式。P0 push_status 只能展示未启用或已有事实，不能隐式触发推送。空过滤结果为成功空列表，缺失版本为明确错误。

`AdoptionPreviewRequest={expected_revision!,target_knowledge_version_id:ID!,inheritance:{stable_message_ids?:ID[],reference_content_ids?:ID[]}}`。预览返回 ConfirmationPreview 加 `{source_object_id,source_bound_version_id,target_knowledge_version_id,source_content_revisions:PreviewContentRevision[],regeneration_scope:string[],cost_notice:string}`。cost_notice 可说明无法估算，不伪造精确费用。Research 继承只取已保存稳定内容，标为待复核背景；Review 保留原主题，人工内容仅为明确参考，不继承确认状态。

### 5.1 版本摘要与引用解析补充

本节补充上列 DTO，字段为只读；内部存储引用不透传。既有 ID/分页/安全错误规则不变。KnowledgeVersionView 增加 observed_at:Time，标识 is_latest 等动态投影的观测时间，不作为创建绑定凭据。

- `KnowledgeVersionView` 增加 `scope_summary:VersionScopeSummary`、`paper_text_counts:{full_text:integer,abstract_fallback:integer,user_text:integer,other:integer}|null`、`availability:{state:available|unavailable|unknown,checked_at:Time,reason:string|null}`、`risk_summary:{recorded_count:integer|null,checked_at:Time|null}`。文本计数按该版每篇论文最终主文本来源互斥归类，总和等于 counts.papers；不含资料、候选、未纳入或失败项。null 表示未统计，other 不得计作全文；counts.materials 独立呈现。availability 是当前主体下版本知识依赖的读取可用性，不等于 Project 可写/可启动，启动仍逐次检查权限、状态与资源。
- `VersionScopeSummary={construction_run_id:ID,search_execution:executed|not_executed|unknown,search_scopes:SearchScope[],includes_manual_inputs:boolean|null,summary:string}`；`SearchScope={source:string,query_summary:string,executed_at:Time|null,date_basis:string|null,date_from:Time|null,date_to:Time|null,result:completed|partial|failed|unknown}`。范围来自本次冻结输入/执行事实，日期端点是否包含及日期含义写入 date_basis；未知 date_basis 时不得推断截止满足情况。该摘要不能表示累计版本的完整检索覆盖，详细事实仍追溯 construction_run_id。revision_only 标 not_executed，空 search_scopes 不等于“全部来源”。既有 retrieval_cutoff_at 为有依据的文献截止说明，无单一可证明截止时为 null，不以 published_at 或最近检查时间填充。
- `EvidenceRef` 增加 `asset_revision:Revision`、`target:EvidenceTarget`、`origin_evidence_id:ID|null`。`EvidenceTarget={kind:asset|text|graph,text_revision_id:ID|null,fragment_id:ID|null,graph_view_id:ID|null,graph_edge_ids:ID[]}`。text 必有 text_revision_id，fragment_id 可空但片段引用必须有 fragment_id 或 locator；graph 必有 graph_view_id 且 graph_node_ids 或 graph_edge_ids 非空；asset 为资产级引用，不冒充精确文段支持。text 不携带 graph_node_ids；graph 不携带正文 locator；asset 不携带 fragment_id、locator 或图谱节点/边。非本 kind 字段为 null/空数组。document_asset_id 若非空须解析为清单内不可变文件修订；无 PDF 的摘要证据允许为空。内部保存内容校验依据，不公开对象 key。来源关联仅用于同 Project 可授权追溯，不赋予访问权，不表示自动继承支持性。
- GET `P/evidence/{evidence_id}` 成功仍返回 EvidenceRef，附只读 `resolution:{checked_at:Time,integrity:verified|not_checked,risk_notices:RiskNotice[]}`；带定位的成功解析要求 verified，asset 级可为 not_checked 且不得称已验证片段。`RiskNotice={kind:retraction|correction|parse_error|source_unavailable,summary:string,source_url:string|null,observed_at:Time}`；风险来自已有可追溯记录，空数组不保证全面核查。权限、缺失或校验失败沿用既有非成功错误信封，不返回伪成功 EvidenceRef；只有有权获知时才提供具体不可用原因。动态 resolution 不写回历史引用，不代表论断已获支持。
- 用户显式选择/预览目标后，ResearchCreate/ReviewCreate 必须带 knowledge_version_id；AdoptionPreviewRequest 继续必填 target_knowledge_version_id。预览/创建期间出现新版不改目标，仍可创建已选可用旧版；省略只代表创建事务时默认选择，响应必须展示实际绑定。列表 is_latest 是查询时投影，不作为创建时必须最新的约束。

本节不增加迁移引用或自动截止筛选端点；无已发布版本引导用户进入 Construction，不隐式启动构建；已发布空版本可浏览及新建 Research/Review，明确无证据，不以成员数为创建门槛，不自动回退其他版本。无权限的版本摘要与来源引用同样按公共防枚举规则隐藏；动态状态不改变版本内容，风险统计 unknown/null 与 0 区分。

## 6. Research

`ResearchCreate={title?:string,knowledge_version_id?:ID}`；title 默认由服务端使用项目主题形成；省略版本在创建事务绑定当前默认版本。`ResearchSessionView=Resource+{title,knowledge_version_id:ID,latest_knowledge_version_id:ID,range_fixed:boolean,retrieval_cutoff_at:Time|null,current_attempt_id:ID|null,available_actions:ActionAvailability[]}`；不创建 paused Session 状态。

`ResearchMessageSend`（字段见机器schema）。`ResearchTurnView={id:ID,session_id:ID,knowledge_version_id:ID,user_message:{id,text,created_at},attempts:ResearchAttemptView[]}`。`ResearchAttemptView={id,revision,status:string,partial_result_ref:string|null,accepted_text:string|null,evidence:EvidenceRef[],retrieval_status:pending|found|empty|failed,no_evidence:boolean,error:object|null,task:TaskRef|null}`；partial_result_ref 指向04-02 `/tasks/{task_id}/output`，其未完成文本不作为成功回复，empty 不等于 failed。

| 方法/路径 | 用例 ID / FR | 请求 → 响应 | 约束 |
| --- | --- | --- | --- |
| GET/POST `P/research-sessions` | `Research.List/Create` / 014,018,028 | 分页/ResearchCreate → List<ResearchSessionView>/ResearchSessionView | 无可读已发布版本拒绝创建 |
| GET `RS` | `Research.Read` / 011,014,028 | 无 → ResearchSessionView | 返回实际绑定和新版本提示，不强制采用 |
| GET `RS/turns` | `Research.ReadTurns` / 028 | 分页 → List<ResearchTurnView> | 按 created_at ASC,id ASC；失败用户输入和诊断保留 |
| POST `RS/messages` | `Research.SendMessage` / 028 | ResearchMessageSend → `{turn:ResearchTurnView,attempt_id:ID,task:TaskRef}` | 同 Session 只有一个活跃回复；重复命令不重复追加输入 |
| GET `RS/attempts/{attempt_id}` | `Research.ReadAttempt` / 015,028 | 无 → ResearchAttemptView | 核验 Session 归属 |
| POST `RS/attempts/{attempt_id}/cancel` | `Research.CancelResponse` / 015,028 | RevCommand → CommandResult | 只取消指定 attempt，不取消未来回复，不把部分回复标成功 |
| POST `RS/attempts/{attempt_id}/continue-without-evidence` | `Research.ContinueWithoutEvidence` / 028 | `{expected_revision!,confirmation_token!,acknowledged_risk_ids:string[]!}` → TaskRef | 仅当前 empty 等待项，显式选择无证据普通回复；仍标 no_evidence |
| POST `RS/fix-evidence-range` | `Research.FixRange` / 018 | RevCommand → ResearchSessionView | 固定现有绑定，停止重复升级催促，保留重要证据风险提示 |
| POST `RS/adoption-preview` | `Research.PreviewAdoption` / 018 | AdoptionPreviewRequest → 采用预览 | 不读取流式半成品 |
| POST `RS/adoptions` | `Research.AdoptVersion` / 018 | AdoptionPreviewRequest+Confirmation → `{source_session_id,new_session:ResearchSessionView}` | 创建独立新会话，旧绑定/历史不变；目标版本不自动替换成新出现的 latest |

调整空检索问题可取消当前等待尝试后发送新问题；不得把“继续无证据”自动当用户同意。API-D02 B 已将消息编辑/删除、失败片段编辑/采纳划入 P1，P0 不开放其写端点；已保存成功消息读取、失败输入/片段及诊断保留继续属于 P0。

## 7. Review

### 7.1 数据结构

- `ReviewCreate`（字段见机器schema）；scope/requirements 默认空串；省略知识版本绑定创建事务的当前默认版本。创建并启动大纲生成返回202。
- `ReviewRunView=Resource+{topic,scope,requirements,knowledge_version_id:ID,latest_knowledge_version_id:ID,range_fixed:boolean,lifecycle_status:string,phase:string,outline:OutlineView|null,chapter_summaries:object[],current_final_id:ID|null,tasks:TaskRef[],available_actions:ActionAvailability[]}`；lifecycle_status 只映射02既有合法状态，不添加 active 枚举，不由子任务完成擅自决定 Run succeeded。
- `OutlineView={revision,content_state,title:string,abstract_prompt:string,chapters:{id:ID,title:string,type:string,order:integer,required:boolean,key_points:string[],support_summary:string,risk_codes:string[]}[],review_issues:ReviewIssue[],confirmed_revision:Revision|null,trace:Trace}`。章节 type 是用户描述标签，1–64；order 从0起唯一；required 必须显式提供，不能根据类型猜测。
- `OutlinePatch={expected_revision!,confirmation_token?:string,acknowledged_risk_ids:string[]!,title?:string,abstract_prompt?:string,chapters?:{id?:ID,title:string,type:string,order:integer,required:boolean,key_points:string[]}[]}`；整组章节替换中已有条目必须包含本Run的已存在ID，保留其身份；新条目省略id，由服务端分配；禁止客户端伪造/借用其他Run章节ID。移除/改变既有章节时预览下游失效范围，不删除已接受成果。
- `ChapterView={id,revision,content:Content,required:boolean,confirmed_revision:Revision|null,evidence:EvidenceRef[],review_history:{id:ID,content_revision:Revision,created_at:Time,issues:ReviewIssue[]}[],trace:Trace}`。引用链接问题和学术审查建议复用 ReviewIssue，绑定内容修订；不提供覆盖率、严格模式、阈值或豁免。
- `ReviewIssue={id:ID,revision:Revision,source_revision:Revision,kind:string,description:string,suggestion:string|null,resolution:open|applied|handled|ignored,actor_id:ID|null,resolved_at:Time|null}`。
- `GenerateRequest`（字段见机器schema）；重新生成受到已确认/人工修改内容保护，确认令牌范围必须包括具体章节/大纲/终稿片段。
- `FinalView={id,revision,content:Content,abstract:string,keywords:string[],references:EvidenceRef[],source_outline_revision:Revision,source_chapter_revisions:{chapter_id,revision}[],knowledge_version_id:ID,acceptance:accepted|rejected,acceptance_source:default|explicit_rejection,issues:ReviewIssue[],trace:Trace}`。content 是唯一可写的完整 Markdown 文章，摘要/关键词/参考文献为同修订只读投影，不独立保存冲突正文。

ReviewRun 的 accepted 不自动推进 succeeded；无活动任务且可继续时为 waiting_user。终稿保存后当前修订即可读取和下载，无独立导出快照、过期状态或重新生成快照命令。完成检查当前 accepted 终稿、无活动任务及来源大纲/必需章节仍有效；成功后整个 Run 只读，P0 不提供 reopen 或复制 Run 编辑。完成不是下载前置。新生成结果独立完成后按输入修订及人工覆盖授权提交，失败/迟到不覆盖旧稿。人工终稿编辑不反向使章节确认失效。

引用遵循 FR-033 学术规范：借用内容注明来源、直接引文准确定位、摘要证据明确标示、事实与自己的推论区分。只做标记—参考条目—EvidenceRef 的机械对应检查和已有章节/全文建议式审查，不以数量或 Agent 分数判定学术充分性。人工正文坏标记允许保存并显示问题，不注册伪有效 EvidenceRef；越权/跨 Project/跨绑定版本的证据读取和关联仍拒绝。旧审查不能冒充当前修订审查。

`FinalizationSources={outline_revision:Revision,chapters:{chapter_id:ID,revision:Revision}[]}`。`FinalizationPreview={revision:Revision,confirmations:ConfirmationPreview[],required_chapters:{chapter_id:ID,confirmed_revision:Revision|null}[],optional_chapters:{chapter_id:ID,confirmed_revision:Revision|null}[],source_revisions:FinalizationSources,blocked_reasons:string[]}`；finalize必须携带该完整来源，校验确认修订仍有效。首次汇总无受保护终稿时 confirmations=[]，不新增确认门槛；重新汇总会覆盖受保护内容时返回绑定完整来源及替换范围的确认对象，提交其 token。输入简报为`ReviewBrief={revision:Revision,topic:string,scope:string,requirements:string,knowledge_version_id:ID,trace:Trace}`，知识版本只读。

### 7.2 操作

| 方法/路径 | 用例 ID / FR | 请求 → 响应 | 前置/拒绝 |
| --- | --- | --- | --- |
| GET/POST `P/review-runs` | `Review.List/Create` / 014,018,032 | 分页/ReviewCreate → List<ReviewRunView>/`{run:ReviewRunView,task:TaskRef}` | 无正式知识版本拒绝；冻结简报及模型 |
| GET `RV` | `Review.Read` / 011,014,032–035 | 无 → ReviewRunView | 历史只读；不因默认版本变化改绑 |
| GET/PATCH `RV/brief` | `Review.ReadBrief/EditBrief` / 017,032,035 | 无/`{expected_revision!,topic?:string,scope?:string,requirements?:string,confirmation_token?:string,acknowledged_risk_ids:string[]!}` → ReviewBrief | 更新已保存输入简报；影响已生成内容须预览失效范围与人工覆盖保护；成功Run分支受第9节约束 |
| POST `RV/brief/action-preview` | `Review.PreviewBriefEdit` / 017,032 | `{expected_revision!,action:edit!,proposed_changes:部分ReviewBrief!}` → ConfirmationPreview | 仅topic/scope/requirements可写；绑定下游影响 |
| POST `RV/outline/review` | `Review.ReviewOutline` / 032 | GenerateRequest → TaskRef | 自审绑定当前大纲修订与知识版本；只追加审查，不覆盖当前文本 |
| GET/PATCH `RV/outline` | `Review.ReadOutline/EditOutline` / 017,032,035 | 无/OutlinePatch → OutlineView | 可继续Run中的正常修改按内容保护及影响预览使相关确认/下游结果失效，保留旧成果；Run 完成后只读，不提供平台内再编辑 |
| POST `RV/outline/generate` | `Review.GenerateOutline` / 032 | GenerateRequest → TaskRef | 合法可继续 Run，保护已确认/人工修改内容；阶段再生成不是通用重跑 |
| POST `RV/outline/confirm` | `Review.ConfirmOutline` / 032 | `{expected_revision!,confirmation_token!,acknowledged_risk_ids:string[]!}` → OutlineView | 确认绑定大纲及KV；允许确认低支撑风险，不冒充无风险 |
| GET/PATCH `RV/chapters/{chapter_id}` | `Review.ReadChapter/EditChapter` / 017,033,035 | 无/`{expected_revision!,markdown:string!}` → ChapterView | 同章生成/审查/保存互斥；编辑记录人工来源并使旧确认失效 |
| POST `RV/chapters/{chapter_id}/generate` | `Review.GenerateChapter` / 033 | GenerateRequest → TaskRef | 当前大纲已确认；同章锁；所有证据为绑定版本 |
| POST `RV/chapters/{chapter_id}/review` | `Review.ReviewChapter` / 033,035 | GenerateRequest → TaskRef | 审查结果绑定提交时章节修订；迟到审查不覆盖其他修订 |
| POST `RV/chapters/{chapter_id}/confirm` | `Review.ConfirmChapter` / 033 | `{expected_revision!,confirmation_token!,acknowledged_risk_ids:string[]!}` → ChapterView | 引用问题/学术建议提示，不以覆盖率或未处理建议拒绝确认；证据关联权限仍强制校验 |
| POST `RV/chapters/{chapter_id}/issues/{issue_id}/resolve` | `Review.ResolveChapterIssue` / 033,035 | `{expected_revision!,issue_revision:Revision!,action:apply\|ignore!,replacement_markdown?:string}` → ChapterView | apply 必填已查看的替换正文，按当前修订保存；ignore 禁止正文；不使用过期建议静默覆盖 |
| GET `RV/finalization-preview` | `Review.PreviewFinalization` / 034 | 无 → `FinalizationPreview` | 必需章节缺失/未确认阻断，可选缺失不阻断 |
| POST `RV/finalize` | `Review.Finalize` / 034 | GenerateRequest+`{source_revisions:FinalizationSources!}` → TaskRef | 重新校验大纲、必需章节与版本；完成默认接受，无额外接受按钮 |
| POST `RV/finals/{final_id}/review` | `Review.ReviewFinal` / 034,035 | GenerateRequest → TaskRef | 全文终审绑定该稿件修订并保留历史问题；不把审查当重新接受，不改变原知识版本 |
| GET `RV/finals/{final_id}` | `Review.ReadFinal` / 034,035 | 无 → FinalView | 返回当前已保存稿及问题/下载资格，default 不等于人工确认 |
| PATCH `RV/finals/{final_id}` | `Review.EditFinal` / 017,034,035 | `{expected_revision!,markdown:string!}` → FinalView | 仅可继续 Run 且 accepted：保存新内容修订、标记 manual_edit，立即可下载；rejected 不因保存复活；完成后只读 |
| POST `RV/finals/{final_id}/generate-components` | `Review.RegenerateFinalComponents` / 034 | GenerateRequest+`{components:(abstract\|references)[]!}` → TaskRef | 非空去重；可继续 Run 且 accepted，基于当前完整正文按人工保护生成并提交同一正文修订；失败不破坏已保存稿；完成后拒绝 |
| POST `RV/finals/{final_id}/issues/{issue_id}/resolve` | `Review.ResolveFinalIssue` / 034,035 | `{expected_revision!,issue_revision!,action:handled\|ignore!,note?:string}` → FinalView | handled映射resolution=handled，ignore映射ignored；章节apply映射applied，不将处理状态冒充已应用正文。记录处理/忽略，不隐式修改文章；需改正文走显式编辑 |
| POST `RV/finals/{final_id}/reject` | `Review.RejectFinal` / 034,035 | RevCommand+Confirmation → CommandResult | 拒绝对应终稿，撤销正文读取/下载并清理其本地文件，保留状态与诊断及其他 accepted 成果；已下载副本不可撤回 |
| POST `RV/complete` | `Review.Complete` / 034 | `{expected_revision!,final_id:ID!,final_revision:Revision!}` → ReviewRunView | 幂等；原子检查Run/终稿/来源修订、accepted及无活动任务；未处理审查建议不阻断；不另要确认token |
| GET `RV/finals/{final_id}/download` | `Review.DownloadFinalMarkdown` / 034,035 | `expected_revision!` query → Markdown附件流 | 仅当前已保存accepted修订；缺修订428、失配412；无模型调用，流固定读取内容；完成前后均可用，见04-02 |
| POST `RV/tasks/{task_id}/cancel` | `Review.CancelGeneration` / 015 | `{expected_revision!,attempt_id:ID!}` → CommandResult | 只取消指定生成任务；不能取消下一次任务或删除人工稿 |
| POST `RV/fix-evidence-range` | `Review.FixRange` / 018 | RevCommand → ReviewRunView | 保持原绑定，不反复催促 |
| POST `RV/adoption-preview` | `Review.PreviewAdoption` / 018 | AdoptionPreviewRequest → 采用预览 | 展示从头生成范围、继承主题、人工参考处理和成本提示 |
| POST `RV/adoptions` | `Review.AdoptVersion` / 018 | AdoptionPreviewRequest+Confirmation+`{model_selection!}` → `{source_run_id,new_run:ReviewRunView,task:TaskRef}` | 新独立Run，不改旧绑定，不继承原确认状态 |

审查历史可随 ChapterView 分页读取 `GET RV/chapters/{chapter_id}/review-history`（`Review.ReadChapterReviews` / FR-033,035，响应 List<审查记录>）；这不提供任意内容版本恢复。大纲和必需章节确认、Review 终稿默认接受属于不同规则，不可合并为通用“全部确认”。

### 7.3 前置修订的精确目标

未列特殊项时 expected_revision 为路径末端目标详情的 revision；不能用 Project 的总修订替代章节/候选修订。

| 命令族 | expected_revision 读取来源 |
| --- | --- |
| 当前模型、SMTP、安全配置首次及后续保存 | 对应单例 GET 的 revision；无配置也返回初始化修订 |
| Workspace 上下文保存 | WorkspaceView.context_revision |
| 检索词生成、CW 配置、清空关联预览/确认 | ConstructionWorkspaceView.revision；清空 token 另绑定目标关联集合 |
| 检索词/补充确认及修改 | 对应 SearchTermView/SupplementView.revision |
| 候选修改、去重修正、分析生成 | CandidateView.revision |
| 候选重评分 | ConstructionRunView.candidate_revision；预览同时绑定目标候选修订集合 |
| 阶段等待项确认 | WaitingItem.revision；subject_revision/candidate_revision是附加确认依据 |
| Construction 取消 | ConstructionRunView.revision；已有执行身份时 attempt_id 必须匹配，无已分配执行身份时显式传 null，按路径 Run ID 和修订取消 |
| Research 发送、固定范围和采用预览/执行 | ResearchSessionView.revision；采用 token 另绑定稳定继承内容修订 |
| Research 取消/无证据继续 | ResearchAttemptView.revision |
| 大纲生成/审查/编辑/确认 | 已存在 OutlineView.revision；尚无大纲的首次补生成使用 ReviewRunView.revision，服务端同时检查 outline 仍为空 |
| 章节、章节问题处理 | ChapterView.revision；问题另校验 issue_revision |
| 汇总 finalize | FinalizationPreview.revision（依赖集合修订），同时提交 source_revisions |
| 终稿操作、问题处理 | FinalView.revision；问题另校验 issue_revision |
| 返回检索追加词、Review 完成 | 对应 RunView.revision；完成另校验 final_revision 与当前来源集合 |
| Review 指定任务取消 | TaskView.revision，attempt_id 必须匹配该 task |
| Review 简报/固定范围/采用 | 简报用 ReviewBrief.revision；固定范围及采用用 ReviewRunView.revision |

同键已受理命令按主文先重放，不让上述已推进的修订造成假冲突。确认 token 的技术有效期只限制新命令受理，执行中使用持久确认记录。

## 8. 交互示例与契约验收

### 8.1 固定输入启动构建

```json
{
  "selected_terms": [{"term_id": "00000000-0000-4000-8000-000000000001", "confirmed_revision": "term-r3"}],
  "supplement_ids": [],
  "retrieval_range": {"published_from": null, "published_until": null},
  "result_limit_per_source": 100,
  "model_selection": {"source": "user", "config_id": "00000000-0000-4000-8000-000000000002", "model_id": "selected-model"},
  "graph_mode": "incremental"
}
```

以新 Idempotency-Key 提交，返回202含 run 和 task。第一次构建 base_knowledge_version_id 为 null；已有版本时由取得构建资格的事务确定，不能要求客户端写一个任意基线。同键重复返回同 run/task；另一个键遇占槽返回409。

### 8.2 具体入库预览确认

```json
{
  "expected_revision": "wait-r4",
  "subject_revision": "preview-r9",
  "candidate_revision": "candidate-r9",
  "confirmation_token": "opaque-preview-token",
  "acknowledged_risk_ids": ["ABSTRACT_ONLY"]
}
```

若提交前候选已变为 candidate-r10，返回412或主文明确的确认失效冲突，不可用相同 token 发布 r10。用户重新查看预览，再取得与新内容绑定的确认。

### 8.3 新知识采用

```json
{
  "expected_revision": "session-r8",
  "target_knowledge_version_id": "00000000-0000-4000-8000-000000000003",
  "inheritance": {"stable_message_ids": ["00000000-0000-4000-8000-000000000004"]},
  "confirmation_token": "opaque-adoption-token",
  "acknowledged_risk_ids": []
}
```

返回 source_session_id 和 new_session，new_session 绑定确认目标版本。源会话继续其原版本；即使确认期间发布另一版本，也不替换请求中的目标。

### 8.4 必须覆盖的文档/后续实现验收

公共错误投影及恢复建议统一见04 §5.1和机器契约PublicError；本表的真实授权、并发和副作用验收不能由A04的结构测试代替。

| 场景 | 对应契约可判定结果 |
| --- | --- |
| 并发首位注册/最后管理员治理 | 只一位首位管理员、至少保留一位启用管理员 |
| 无模型/失效模型/匿名数据源 | 不静默回落；匿名支持源可无密钥；必须密钥源拒绝 |
| 配置编辑与运行输入冻结交错 | 运行保持其快照；新配置明确下轮生效 |
| 已采纳 API 方向 | 覆盖 R1–R4：无覆盖率阻断；保存即下载/完成后只读；一次确认终止列明冲突且自动移除；空版可浏览/新研究；入库确认后paper/material锁定；筛选追加词保持范围及预算 |
| 双启动/重复消息/重复确认 | 同键同结果；异键按锁/修订拒绝，不重复副作用 |
| 跨 Project 资产/版本/任务ID | 拒绝且不泄漏私有文件、分析、任务日志 |
| 上传PDF元数据不足/资料标题缺失 | 待确认，不成为正式证据；支持格式可进入处理 |
| 筛选、解析、分析、预览确认 | 未满足前一确认不推进；候选变更使相关确认失效 |
| 解析降级、部分源失败、全源失败 | 来源可辨；部分成功继续，全源失败阻断后续 |
| 已发布KV与候选同时存在 | 研究/知识面板只读指定已发布版本 |
| 研究空检索与流式失败 | 显式选择普通回复；半成品不保存为成功回复 |
| 新版本发布与旧回复并行 | 原绑定稳定；关联新对象独立绑定用户确认版本 |
| 章节并发、过期审查建议、人工覆盖 | 同章互斥；修订冲突拒绝；不得静默覆盖 |
| 终稿必需/可选章节、默认接受与拒绝 | 必需缺失阻断；可选不阻断；成功默认接受；拒绝只清理目标产物 |
| archived/deleted/context恢复 | 不能恢复写权限；context不改变业务对象 |
| SSE 重放和断线 | 重放不重执行；状态查询确定最终结果，见04-02 |

本轮只进行文档结构、引用、版本和协议一致性检查；上述是后续实现必须执行的自动化与端到端验收，不是已通过测试。局部机器契约及其实际检查范围见04-03，不能将结构校验当作上述业务场景已通过。

## 9. 已采纳边界与剩余分期

R1-A、R2-A、R3-A、R4-A 及用户补充已于2026-10-16批准，记录见[决策记录](../proposals/api_boundary_redesign_2026-10-16.md)。本轮 E01–E04 已关闭，不再阻塞这些协议分支。R1替代D03严格覆盖；R2替代D06独立导出快照，保留D05显式完成。D01追加词、D07无检索构建按本附录窄范围执行。不得用通用 PATCH、force 或 retry 绕过。

D02 B 的消息编辑/删除及失败片段编辑/采纳仍为P1；D04 A 管理生效即撤销写资格并安全终止，清理失败不复权。P0仅新增单篇当前已保存终稿 Markdown 下载；通用导出中心、批量与PDF/Word转换、通用运行恢复、邮件、输出倾向仍为P1；P2协作/完整历史差异回退不提前实现。账号删除对已完成通用导出文件生命周期在P1实现前明确，不阻塞本轮P0下载。真实接口仅展示已实现能力；设计决策关闭不代表OpenAPI、代码或验收完成。

## 变更记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.2 | 2026-10-16 | 限定确认载体与纯预览协议，移除待决占位路由，补未发布文件读取并登记 API-D07 |
| v1.1 | 2026-10-16 | 同步 published/no_change 完成投影、排队空快照与取消裁决；不扩展 P1 恢复入口 |
| v1.0 | 2026-10-16 | 独立预案经主代理评审后建立P0操作、字段、确认与版本绑定契约，明确局部待决分支及P1/P2边界；未实现代码 |

本次修订 v1.3（2026-10-16）：承接七项已采纳方向；定义 revision_only 和当前稿快照投影/重生成，收束待决至 E01–E04。

本次修订 v1.4（2026-10-16）：补充版本范围摘要、证据修订与动态解析投影及显式选择契约。

本次修订 v1.5（2026-10-16）：同步 R1-A–R4-A 及人工补充裁决；本轮细则已关闭，实现与运行验收另行跟踪。

本次修订 v1.6（2026-10-19）：迁移本批具名字段到局部OpenAPI，保留操作/业务规则，明确未迁移范围及机器校验非业务验收。

## 10. A05 资料设置与来源分类

本节只细化[08-01](08-01_agent_data_access_policy.md)已决策略；字段唯一来源为机器schema `MaterialPolicyWrite/View`、`MaterialSourceIdentity`、`MaterialClassificationWrite/View/Fact`、`MaterialProvenance`、`MaterialUseNotice`。所有操作同步返回200及标准data/meta；不创建Task，不调用模型。路径仍按本文P缩写。

| 方法/路径 | 用例 ID / FR | 请求 → 响应 | 前置与失败 |
| --- | --- | --- | --- |
| GET `P/material-policy` | `MaterialPolicy.Read` / 008,017 | 无 → MaterialPolicyView | 本人×Project；active/archived可读，缺记录返回public_only及稳定初始修订、空风险时间；不恢复Workspace授权 |
| PUT `P/material-policy` | `MaterialPolicy.Update` / 008,017 | MaterialPolicyWrite → MaterialPolicyView | active Owner；expected_revision指政策记录；allow_private需已展示风险并明确同意，public_only不要求确认；成功返回新修订 |
| GET `P/material-sources/{source_id}/classification` | `MaterialSource.ReadClassification` / 008,017 | 无 → MaterialClassificationView | 当前Project具体来源；active/archived可读；不得以DOI或物理哈希跨Project定位授权 |
| POST `P/material-sources/{source_id}/classification/confirm` | `MaterialSource.ConfirmClassification` / 008,017 | MaterialClassificationWrite → MaterialClassificationConfirmedView | active Owner；仅unconfirmed；明确选择和依据，在首次模型使用前完成 |
| POST `P/material-sources/{source_id}/classification/correct` | `MaterialSource.CorrectClassification` / 008,017 | MaterialClassificationWrite → MaterialClassificationConfirmedView | active Owner；仅confirmed；public放宽必须Owner明确确认及具体公开依据；不更新正文或引用 |

### 10.1 修订、确认及可信来源

政策revision独立于Project/Workspace修订，分类revision独立于内容修订。每次受理的新写命令（即使选项相同）获得不可复用新修订；打开→关闭→打开不得复用。GET在尚无记录时返回稳定默认投影而非修改Project业务状态；首次PUT可使用该修订。`risk_acknowledged`记录此次界面风险同意，不是通用ConfirmationPreview/token；public_only写入false，开启写入true，服务端记录操作者、时间、当时所展示的当前Provider及风险说明。未选模型时明确显示“未选择”，设置不自动选模型；真正外呼仍需合法模型选择。关闭后保留最近一次风险同意时间供审计，初始为null。服务端不从客户端接收user_id、审计时间或Provider授权。

确认/更正请求的expected_revision针对当前分类；content_revision必须匹配该source_id的不可变具体内容。任一失配为412，缺必需修订为428；其他缺字段/非法组合为422。confirm作用于已确认记录、correct作用于未确认记录均409 STATE_OPERATION_NOT_ALLOWED，不以更换入口覆盖人工事实。同键同参按04重放原执行事实，不再执行、不重新检查旧修订制造冲突；同键异参409。PUT响应丢失先GET核查，不自动换修订提交。可见性及归档写保护优先于重放；来源不存在、其他Project、deleted、管理员但非Owner均安全404。

上传初始private/unconfirmed；检索可建议public但仍unconfirmed，建议不构成授权。无分类历史按private/unconfirmed保守投影，保留原事实，禁止批量public。分类确认不等于分析/处理/入库确认，不自动启动后续流水线。文件及检索/历史来源的安全接收、隔离暂存与必要静态提取先于分类，分类确认先于这些来源的模型/嵌入外发；私人模式也不能跳过未确认。可信本次主动文字按下文例外处理，不增加分类确认步骤。用户原有合法查看与静态接收不受该开关阻止。

basis是针对具体实际内容的非空依据说明，不收凭据或正文；公网URL/DOI/公开摘要不足以证明机构全文公开。服务端必须核验依据及Owner身份，字符串合法不等于证据充分；不充分返回422 VALIDATION_FIELD_INVALID（basis）。confirmed_by/time由服务端写入，LLM不可代填。更新只写当前分类及审计，已发布正文、入库时事实、引用和版本成员不改；普通Project/资产metadata PATCH不得接收这些字段。

`MaterialProvenance`为只读可信投影。current_submission仅由接收当前明确提交的应用入口签发submission_scope_id并绑定操作者、Project及本次命令；客户端不能选择该标记，复制ID不构成授权。后续自动取用同一文字必须投影historical_input且scope为null；上传文件不因主动上传而取得文字例外。derived_content的dependency_status由服务端追踪全部实际输入，complete不代表public；混合私人、缺依赖或unknown不能推定公开。unknown的dependency_status必须unknown；current_submission必须complete。其余类型按实际证据标记，不由引用列表或LLM自评。可信current_submission对应的本次明确提交文字，可在绑定的当前主体、Project及本次命令范围内直接使用，无需额外分类确认；这不把文字标为public，不改原分类事实，不授权自动读取历史、草稿或其他文件。该例外不适用于上传文件；后续历史/自动取用、派生产物仍按08-01检查分类及全部来源依赖。该投影不是可转移的授权凭据；除上述本次文字例外外不能代替分类确认。不提供任意来源注册或授权端点；source_id由既有接收/内容生产链创建并通过详情提供，相关完整详情转写留A08。

两个分类POST成功data使用 `MaterialClassificationConfirmedView`，meta使用 `MaterialClassificationMutationMeta`；字段约束只在机器schema维护。GET保持 `MaterialClassificationView`，允许显示未确认来源；设置GET/PUT仍使用通用Meta。同步分类写入及同键重放均须返回已确认事实和明确的最早去重失效时间；真实至少24小时保留按04 §7落实，schema不证明保留时长。

### 10.2 错误、UI和异步对应

每条操作的精确HTTP/code子集以机器`x-error-codes`及响应schema为准，复用A04而不新增错误码。所有操作：400格式错误、401认证、404安全不可用、422字段问题、429资源保护、500存储失败。写操作另含403 CSRF、409只读/操作不允许、412冲突、428缺修订、413请求过大、415媒体类型不支持；分类POST另含409幂等冲突。不向这些同步路由绑定Provider失败或Task恢复。

| 结果/原因 | UI动作与不可发生事项 |
| --- | --- |
| 200 | 展示服务端当前值及新修订；分类重放展示原执行事实后可重新读取当前状态，不回写旧状态 |
| 401 / 403 CSRF | 重新认证/刷新凭据；不自动重发修改 |
| 404 | 安全不可用空态；不显示他人Project、存在性、修订或链接 |
| 409只读/不允许 | 保留当前内容，显示只读/不适用；无强制覆盖或解除归档入口 |
| 409幂等冲突 | 核查原操作结果；不换键自动执行 |
| 412 / 428 | 重新读取当前依据并保留用户未提交选择；不拿新revision自动覆盖 |
| 400 / 422 | 修正字段；不回显任意字段名/原值；依据不足不改变分类 |
| 429 / 500 / 断网 | 按A04结果未知规则先核查；只有有未受理证据才允许原条件技术重试，不创建业务attempt |

既有异步任务在当前政策下不再能使用必需输入时，仍沿A04 `TaskError`投影STATE_OPERATION_NOT_ALLOWED（安全原因、details/recovery均null、retryable=false），Task GET成功读取仍200；资源可见性丧失先走安全404，不披露诊断。具体attempt终止与提交裁决留A06，不新增业务状态。`MaterialUseNotice`为受控读取/上下文构造的只读提示词汇：private_source、classification_unconfirmed、provenance_unknown、dependencies_incomplete、required_history_restricted、available_subset；没有在本任务绑定新的TaskView字段，完整消费接口尚待A06/A07。

### 10.3 执行交接与验证边界

下一正常受控读取、实际派发和提交均用当前政策/分类修订；受理快照只作审计。扩权不重跑结束任务、恢复终止attempt、追加冻结输入、扩大确认范围或改绑KnowledgeVersion；收紧不删除合法旧成果、不承诺撤回在途字节。缓存与派生数据重验全部依赖，受限必需历史明确阻断，不静默删消息继续；合法检索子集显示范围受限，不能说完整知识库无结果。

A06负责可信scope签发/消费、分类与内容修订核验、全输入依赖、read/dispatch/commit原子裁决和缓存；07的逻辑记录不在本次转成数据库。A07/A08负责完整任务/详情承载。测试见 `scripts/tests/test_material_policy_contracts.py` 和[任务007审核包](../workorders/task007_a05_review_2026-10-22.md)：schema/操作矩阵可测，真实身份、事务、并发、模型发送、版本保护和UI运行效果均未验证。

## A08 补充详情与处理依据投影

新增具名字段仍待机器转写；既有PaperAnalysis/MaterialAnalysis、MetadataCandidate、ProcessingView以本文原定义为唯一来源。SupplementView.error由object收紧为`TaskError|null`（A04机器schema），仅反映对应准备任务的安全失败；元数据缺项/歧义使用下述诊断，不伪造终态TaskError。

SupplementView增加必填`input_revision:Revision,selected_candidate_id:ID|null,processing:ProcessingView,processing_basis:ProcessingBasis|null,preparation_notices:PreparationNotice[],duplicate:SupplementDuplicateView`。

`PreparationNotice={reason:PreparationReason,message:string}`，reason复用06 A08.1词汇，message仅安全摘要，不返回内部诊断ID/来源依赖；权限错误仍防枚举。`SupplementDuplicateView={decision:not_checked|distinct|duplicate|suspected,matched_project_asset:{kind:paper|material,id:ID}|null,reason:string|null}`；匹配只限当前Project可见成员，未检查不得返回distinct；它是已有去重决策投影，不自动合并、覆盖或确认。

`ProcessingBasis={processing_revision:Revision,input_revision:Revision,text_revision_id:ID|null,document_asset_id:ID|null,file_revision:Revision|null,confirmed_revision:Revision|null}`。所有字段必填；file_revision与document_asset_id同空/同有，text_revision_id仅实际可用文本非空。confirmed_revision指当前有效处理确认；独立补充无Run处理确认故为null，元数据确认不填这里。processing_revision为已持久处理结果身份，pending且无结果时整个basis=null。内部文件摘要、依赖闭包不公开。

CandidateView和AssetView增加必填`processing_basis:ProcessingBasis|null,analysis_basis:AnalysisBasis|null`，AnalysisBasis字段唯一见06 A08.3。无分析/无有效结果时null；失效旧结果不作为当前有效analysis/basis，人工旧稿按现有保护保留而不混入有效投影。正式AssetView只取指定版本固化依据，不能用当前候选修订补齐；引用字段存在不授权其他Project或未发布数据读取。

ProcessingView原status/text_source_kind/failure_reason/participates_in_knowledge按06 A08.2映射。pending/processing无最终文本，failed/unsupported无文本且参与=false；available/degraded仅表示文本能力，不自动参与知识构建，仍须有效性、确认、纳入和发布规则，排除项参与=false。paper degraded仅abstract_fallback，material没有摘要降级。成功读取含失败状态仍HTTP200，不重放生成命令；Task等待和文件读取保持A07/04-02规则。

选择MetadataCandidate必须属于当前补充input_revision；CorrectSupplement的expected_revision绑定当前详情，旧候选选择返回既有修订/状态错误。选择/修正后重新核验关键元数据与冲突，确认时再次检查；不能以选过一个ID绕过缺标题。确认仅使其待纳入，不表示已有全文、处理确认或分析确认。


MetadataCandidate增加必填`assessment:MetadataDraftAssessment`：`{confidence:number|null,missing_fields:string[],evidence:MetadataDraftEvidence[]}`。LLM草稿confidence必为0–1的估计值（不是已校准质量或自动确认门槛），其他提取无估计可null；missing_fields是该kind允许元数据字段名的去重集合，必须与实际缺项一致，不要求资料具备作者/年份。LLM字段缺省拒绝结构化结果，不能以默认1或空数组掩盖缺项。

`MetadataDraftEvidence={field:string,source:SourceRef,document_asset_id:ID|null,file_revision:Revision|null,text_revision_id:ID|null,locator:EvidenceLocator|null}`；field只能是该kind元数据字段，文档身份与file_revision同空/同有；text/locator若存在须对应已保存输入文本和同一文件修订，可通过原授权文件入口定位，未具定位不能伪造。证据为当前补充实际使用的输入来源，不是正式EvidenceRef；provider元数据可无文件/文本定位，但必须指实际解析的SourceRef。无依据字段不编造证据，明确列入缺项或冲突供人工修正；所有引用限当前Project授权，不输出内部路径/依赖闭包。公开投影不能安全提供必要证据时不称已核验，保留安全缺项说明。


本次修订（2026-10-26）：落实task025用户决定，P0个人/系统LLM无启停开关；发现/手填只提供待测项，当前配置/凭据修订下逐模型显式测试成功才可选择。扩展参数方向B另行调研，不将方案或机器缺项视为已实现。

本次修订（2026-10-26）：按用户决定分离数据源检索服务入口与具体资源地址；本次决定不涉及通用抓站支持及范围，具体文件地址不作为配置入口。

本次修订（2026-10-28，D-CW-03）：用户明确“只以去标点符号、全小写的标题来判断是否是同一论文身份”。自动标题键删除Unicode P类标点后调用lower，不增加模糊匹配、空白合并或字符兼容转换；保留数学符号，空/纯空白结果不自动匹配。人工修正优先、原始元数据和全部来源保留；身份合并不修改已发布内容或跨Project私有资产。该规则替代旧强标识优先自动去重要求。


Task044（2026-10-29）论文评分限定增量：同Run身份组按逐来源原始标题/摘要结构化输入评分，不拼接成权威摘要；空摘要如实保留。PaperScreeningView返回0–10分、有效性、系统默认阈值来源和理由；screening_basis记录三类理由、阈值7、冻结模型配置修订、实际来源/主题输入及任务。人工修改、过期依据、错误和历史独立投影；身份变化保留旧判断并标记待复核，不按显示代表自动解决冲突。候选详情提供MaterialClassificationView，来源分类与当前资料政策在读取/派发/提交重验；主题使用评分命令受理时已分类的具体内容修订，不改变Run初始输入/模型快照。

POST screening/action-preview与score按A07绑定当前候选集及所选组，人工覆盖须完整预览；PATCH候选本切片只开放screening评分/有效性/理由，metadata/analysis仍未实现。运行中的评分拒绝候选编辑/去重变更；失败或取消保留人工内容。ScoringTaskView为该限定Task投影，原Run仍处于screening等待，评分任务完成不等于Run发布；不能从此推定筛选确认/下载解析已开放。Run/candidate新增字段机器契约见PaperScreeningView、ScoringPreview、ScoringTaskView、PaperScreeningPatch及RetrievalCandidate/RunView；不扩全量CandidateView或一般Task覆盖声明。


### M-P0-15工程细化：论文处理切片

D-CW-04 B（2026-10-29用户选择）：沿冻结候选来源顺序选首个可用全文；全部全文不可用才选第一份真实非空摘要，不拼接。确认展示最终来源、其他来源及逐次失败诊断，不声称所选版本最新/权威。筛选阶段确认仅放行当前有效且依据未失效的独立论文组，失败/无效/待判定项仍可诊断，不增加整Run全成功门槛。

沿既有ConfirmStep路由支持confirm_screening/confirm_processing，沿修订和主体绑定token。处理完成等待用户；无可用文本不进入分析。确认后phase=analysis只表示已完成处理确认，本切片没有分析生成/入库能力。活动处理与编辑互斥；处理完成后评分/有效性/去重编辑保留旧处理历史和文件，失效受影响确认，重新筛选确认。Run源、配置和知识基线不变。

本片RetrievalCandidate增加可选processing（机器schema RunPaperProcessing）、processing_history与document_refs；processing展示状态、来源类型、最终source ID、按序source IDs及必返source_attempts（所选全文/所选摘要/全文失败/未尝试）、脱敏diagnostics、前2000字符节选及总字符数、文本digest、页/文本范围和ProcessingBasis。全文分类单独返回material_classification，不继承摘要分类。对象字节与完整文本存于Run所属未发布对象，列表不内联正文或物理路径；file-access及download沿原授权路由。处理/确认不设置参与正式知识标志，旧结果不能冒充新确认。

PDF下载每跳独立校验公开HTTP/HTTPS目标，最多4次请求、每次30秒，最多50MiB，无应用凭据；静态解析子进程20秒、CPU15秒、最多2000页/200000字符且不截断，限额失败可用真实摘要降级。macOS保留sandbox-exec；Windows/Linux采用独立Linux解析容器方案，Windows宿主需要Docker Desktop的Linux容器模式，不宣称Windows原生无依赖运行。应用不必整体容器化；未提供隔离运行时的平台必须报告parser_unavailable，不退回应用进程解析。技术获取重试预算为0，不新增P1通用恢复。非论文格式、独立补充上传/替换、全局成员、AI分析和发布仍不属于本切片，不宣称完整FR024验收。

2026-10-29用户确认提取引擎选择语义：提供多个引擎选项，每次选择一个执行，不同时运行多个引擎或混合结果。本阶段建立统一后端选择/结果接口，仅pypdf已实现；未实现引擎不列为可用，也不新增终端用户选择UI。LLM PDF解析引擎列为下一阶段设计目标，未授权本阶段模型调用；后续需明确Run冻结选择、外发权限、模型配置、证据定位、预算与失败规则。平台方案、部署依赖及真实执行证据参见[运行器说明](../../deploy/pdf-parser/README.md)与[task046](../../tasks/046-paper-processing-gate.md)，实现方案不代表平台验证通过。

### M-P0-16工程细化：LLM文字整理（2026-10-30）

依据task047及D-PDF-01–04：RetrievalRunStart可选pdf_extraction_engine=pypdf|llm_text_cleanup，省略及旧Run为pypdf；单次选一个引擎，换引擎新建Run。LLM引擎内部pypdf静态准备，仅读文字层，不视觉/OCR；保留原行原序，只建议同页换行。冻结同一Run模型/参数；不改变评分等其他调用的参数。个人每模型上下文容量默认262144；仅整理引擎未指定输出上限时默认4096，原显式同义输出参数保留。实际容量与隐藏推理消耗不能由连通测试证明，按UTF-8字节保守估计并预留协议/输出，单行不容纳明确失败，Provider截断/超限拒绝且不截断原文。

实际PDF保存为Project/Run/候选所属不可变对象，独立private/unconfirmed分类；cleanup_pending给出文件、来源及分类。D-PDF-02特定例外：分类保存自动继续已明确请求的原整理作业，不另启动流水线，不复活终态任务；派发与提交仍重验当前权限、分类修订和资料政策。活动分类等待也禁止候选编辑和处理确认。原文件/原文本与整理后文本分开保存，cleanup给出来源定位/模型/输出默认标志和映射，processing-text按需读取完整比较文本；列表仅节选，旧人工确认和处理历史保留。

每调用30秒、每来源120秒/32次、每论文组240秒/64次，限额冻结；外呼前原子预留并提交预算，结果未知不重发，重启不重置。失败按冻结来源顺序继续，整源所有批次验证才可用；组预算耗尽不把未尝试来源写成失败，也不能将真实摘要标作成功降级，只有全部全文实际不可用才选真实摘要。权限/政策失效或取消停止并拒绝提交。此设计细化不代表S6或M-P0-16验收已完成；平台实测限制继续沿task046记录。
