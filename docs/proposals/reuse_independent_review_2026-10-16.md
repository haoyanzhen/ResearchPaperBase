# 外围代码独立审查与逻辑拆分结果

文档版本：v1.1  
日期：2026-10-16  
适用项目大版本：v1  
状态：独立审查已完成；后续物理提取与旧代码清理已执行

本报告正文保留审查时事实与来源行号。后续经用户授权完成实际操作，见[清理执行记录](../workorders/legacy_cleanup_execution_2026-10-16.md)和[候选存档](../../archive/maybe_useful/README.md)；旧代码已删除，未实现新核心。

## 1 任务目标与独立分工

依据[重构计划](core_rewrite_plan_2026-10-16.md)，对“审查后复用”和“拆分复用”候选进行独立审查。用户明确要求：不考虑旧项目完整性，无需保留接口，仅留存有用的业务逻辑。因此不以旧项目能启动、旧测试通过、API 兼容或保留文件数量作为成功标准。

| 审查者 | 独立范围 | 方法 |
| --- | --- | --- |
| subagent `review_backend_reuse` | 认证、管理员、配置、通用模型与 schemas、core、外围 API、迁移工具和工程基础 | 只读实现及 FR 核对；AST 隔离验证健康聚合函数 |
| subagent `review_agent_reuse` | Agent、Provider 解析、下载解析、评分、引用、导出、邮件、提示词 | 只读实现；AST 隔离复现解析和去重边界样例 |
| subagent `review_frontend_tests` | 前端全部候选、后端/前端测试及 E2E | 只读代码、测试断言与实际调用链核对 |

三者均收到相同边界：不改文件，不连接业务数据库，不调用真实外部服务，不读取凭据，不维护旧接口。主代理负责汇总、抽查证据和处理结论分歧；不将三者审查误称为同一模块的三重复核。

## 2 总结与裁决口径

**没有整模块通过复用审查。** 原计划中的认证、配置、设置页、健康页等“审查后复用”应下调为“重写实现，仅保留规则或交互语义”。Agent 也不保留整文件。复用单元是下面明确限定的函数片段、字段映射、业务规则及测试场景。

| 裁决 | 含义 | 后续动作 |
| --- | --- | --- |
| X 片段留存 | 已识别独立价值；可能仍需局部修正 | 只提取表中限定片段并通过测试，不能复制整个来源文件 |
| R 规则留存 | 业务意图有价值，旧实现缺陷或耦合较多 | 用新契约重新实现，不将修补旧代码称为复用 |
| D 历史存档 | 无值得迁移的业务实现，或规则已经过期 | 仅保留历史快照，不进入新运行/测试路径 |

“X”不是安全认证或可直接上线。“严重/高/中/低”表示继承旧实现的风险，不是对缺陷发生频率的测量。未列入 X 的实现默认不迁入新核心；需要新增白名单时提供用途、来源、隔离边界和验证证据。

## 3 最小代码与素材留存白名单

以下路径相对仓库根目录，行号基于本轮只读代码。技术辅助与展示素材不属于稀缺业务资产，可重建，无需为了它们保留框架胶水。

| 编号 | 来源 | 精确留存边界和输入输出 | 提取前修正及验证 |
| --- | --- | --- | --- |
| B-X01 | `backend/app/core/security.py:16,20` | 密码散列/校验片段：明文及散列 → 散列或匹配结果 | 不带 JWT、settings、黑名单；验证长密码、中文、错误/损坏散列，确认算法与依赖兼容；中风险 |
| B-X02 | `backend/app/core/logging.py:26,32` | 日志上下文复制和作用域绑定，退出恢复旧值 | 仅接收受控非敏感字段；不带 Formatter/全局 logger；验证嵌套、异常退出、协程隔离；低风险 |
| B-X03 | `backend/app/utils/ids.py:7` | 受控内部前缀 → 随机 ID | 旧前缀不保留；数据库仍需唯一约束/碰撞处理；低风险 |
| B-X04 | `backend/scripts/init_db.py:39` | 数据库标识符双引号转义 | 可选开发工具，不带自动建库入口；验证引号及输入限制；不是 SQL 值参数转义；低风险 |
| AG-X01 | `backend/app/agents/base.py:120` | JSON 文本外围 fence 处理与 JSON 解码 | 仅匹配完整外围 fence，不沿用 MULTILINE 全文剥离；调用方另验 Schema；普通/非法 JSON、正文 fence、数组测试 |
| AG-X02 | `backend/app/agents/construction/stage2_retrieval.py:148` | Semantic Scholar 的 DOI/arXiv/title/authors/abstract/venue 字段提取片段 | 不复制整个 parser；新候选保留 Provider ID、来源、原始响应、检索批次、日期精度；null/错误类型必须处理 |
| AG-X03 | `backend/app/agents/deep_research/pipeline.py:154` | 解析引用标记并与允许 ID 集合求交 | 允许集合来自绑定知识版本；按出现顺序去重并报告未知 ID；不把 ID 合法当成证据充分 |
| AG-X04 | `backend/app/services/construction_service.py:504` | 邮件论文表格布局与字段选择 | 只留布局，插值统一 HTML 转义；无查询、发送、状态回写；测试特殊字符/空列表/超长文本 |
| F-X01 | `frontend/src/utils/format.ts:1,13` | 日期显示与 classNames 小函数 | 日期明确时区/年份；空值、非法日期、跨年测试；纯技术辅助 |
| F-X02 | `frontend/src/components/Alert.tsx` | 受控严重性、图标、消息展示 | 补读屏语义/长文本；不得自行决定业务错误等级 |
| F-X03 | `frontend/src/pages/SettingsPage.tsx:523` | ConfigListSection 标题、空态、操作槽外观 | 不带配置加载/保存；仅可选展示素材 |
| F-X04 | `frontend/components/InspectorPanel/InspectorPanel.tsx:78,92,134` | 耗时、结构化建议、依赖卡片的展示片段 | 去掉字符串前缀协议和固定七依赖键，输入为脱敏 DTO；测试缺项/非有限耗时/长文本 |
| F-X05 | `frontend/src/styles.css` | 颜色变量、基础表单/按钮等视觉素材 | 按实际采用组件提取，旧工作台状态类不迁移；可选素材 |
| T-X01 | `frontend/src/test/render.tsx` | 内存路由渲染辅助 | 接新路由，不导入旧 Provider；仅测试工具 |

严格按“只保留业务逻辑”的最小实施包，优先关注 AG-X02 的字段映射和 AG-X03 的引用过滤，以及第 4～6 节的业务规则。其余技术辅助和外观可以用新工程的标准工具替换，不构成必须迁移资产。

## 4 后端外围拆分结果

| 编号 | 旧来源 | 保留规则与新独立单元语义 | 不留的实现与验收重点 |
| --- | --- | --- | --- |
| B-R01 | `services/auth_service.py`、`core/deps.py`、`schemas/auth.py` | 身份认证、账号状态核对：凭据 → 身份或明确错误；停用账号不能继续使用 | 重写会话、查询、事务和验证；测用户名与他人 email 交叉冲突、并发注册、停用旧会话、资料修改验证 |
| B-R02 | `auth_service.py:24`、`admin_service.py:57` 起 | 首个管理员建立、至少一个启用管理员、授权管理 | 重写原子治理命令，不留 count-then-insert；测并发首次注册、并发撤权/禁用、停用管理员不计可用人数 |
| B-R03 | `admin_service.py:121`、`models/user.py` | 账号删除影响范围计算：目标及引用 → 应删/应留清单 | 不继承 ORM 级联；新资产/任务/文件清理与失败恢复，保留其他 Project 引用及全局论文身份 |
| B-R04 | `admin_service.py:158` 起 | 授权密码重置、新密码一次展示和审计 | 安全随机生成、散列保存、会话策略、邮件分离；不留同步 SMTP 编排和非密码学 shuffle |
| B-R05 | `config_service.py:313` 起 | 显式模型选择、个人/系统配置来源解析、个人收件人加系统 SMTP → 运行配置快照 | 重写缺失/禁用/失效区别、凭据引用和冻结；不留“取首个模型”或隐藏系统模型的 fallback |
| B-R06 | `config_service.py`、`models/user.py` | 配置仓储、凭据仓储、无秘密展示投影分离 | 弃用明文 KV、逐字段 commit、LIKE 模糊删除；测试失败原子性、并发变更、特殊名称及脱敏 |
| B-R07 | `api/v1/config.py:79`、`admin.py:194` | Provider 连接与模型枚举：明确 endpoint/协议/凭据 → 目录或分类错误 | 重写 transport/响应验证；模型列表可读不等于模型调用成功；测试 401/403/429/坏 JSON/空列表 |
| B-R08 | `api/v1/health.py` | 受限依赖探针：检查层次与结果分开；连通、就绪、认证、业务调用分开 | 不留旧聚合器和全依赖调用；探针不得静默花费模型额度或发邮件；测试部分失败/未配置/读取失败 |
| B-R09 | `core/errors.py`、`logging.py` | 类型化错误、用户安全信息与内部诊断分离 | 不留字符串猜测分类、任意 traceback/extra 透传；用例决定可重试性；测试秘密与嵌套 detail 脱敏 |
| B-R10 | `core/database.py`、`config.py`、`alembic/*`、`scripts/init_db.py` | 显式环境、事务所有权和迁移目标 | 重建入口，不能自动载入旧 metadata/业务库；新库初始化与既有数据迁移分支独立验收 |

这些单元可以合并到新分层中的适当模块，不要求一行表对应一个文件。`User` 基础字段、DeclarativeBase、API 路由、DTO/信封和 Alembic 模板只作需求或框架参考，不值得专门迁移实现。旧 `main.py` 调度及启动胶水为 D。

### 已确认的关键隐患

- **严重，配置秘密保护缺失：**`config_service.py:43–54,169–190` 写入明文 Text；加密只存在于注释。数据源配置的 `api_key` 经 `api/v1/config.py:108` 和 `admin.py:226` 一带返回前端。不是跨用户泄漏的实测结论，但不得声称已有完整脱敏/凭据隔离。
- **高，治理与会话边界不可靠：**首次管理员先 count 再 insert；管理员计数未统一排除停用者，且缺并发保护。`core/security.py` 撤销列表仅在内存，重启/多进程不共享。
- **高，配置保存与选择错误：**一份 LLM 配置逐字段 commit，可留下半配置；provider 名直接参与 LIKE 删除，`%/_` 会扩大匹配范围；自动 fallback 不满足显式模型选择。
- **高，健康结论可误导：**HTTP `<500` 在上层被当依赖正常，401/403/429 均可能进入正常分支；聚合器忽略 degraded 状态。此问题在于上层可用性解释，不能仅把“4xx 证明网络连通”判为错误。
- **高，诊断可能携带秘密：**错误信封和 JSON 日志直接接收 traceback/detail/extra，未形成受控脱敏边界。

## 5 Agent 与外部适配逻辑拆分结果

| 编号 | 旧来源 | 留存意图与重新实现的单元 | 淘汰部分及验收重点 |
| --- | --- | --- | --- |
| AG-R01 | `agents/base.py:83–113,138,247` | 模板加载、配置解析、模型 transport 分开；快照＋消息＋预算 → 文本/用量/分类错误 | 不留全异常重试、每次读活配置、首 provider 回退；校验参数优先级、401、429、截断、超时预算 |
| AG-R02 | `construction/stage2_retrieval.py:46,91,103` | arXiv/OpenAlex 字段映射知识；原响应 → 带来源/精度/警告的候选 | 解析实现重写；旧式 arXiv ID、null source、倒排空位置/巨大位置、源 ID/OA URL 保留 |
| AG-R03 | 同文件 `:183,202,230` | 各源请求构造、分页、配额与 transport 分离 | 弃用吞异常返回空列表、静默截断；区分零结果/失败/部分结果。API 细节在实施时核验官方规范 |
| AG-R04 | 同文件 `:258,289` | DOI/arXiv/title 作为匹配线索；候选集 → 身份分组、冲突、来源合并 | 不复制 `_dedup` 或 `_save_papers`；测传递合并、同标题不同 DOI、DOI URL/版本规范化、字段及来源合并 |
| AG-R05 | `construction/stage4_download.py:40,62,78,102` | 下载候选定位、受控字节流、PDF 逐页解析分离 | 不留任意重定向、完整下载后限额、全局路径、吞异常；测目标网络限制、超限提前停止、坏 PDF/空文本/截断标志和页引用 |
| AG-R06 | `construction/stage1_keyword_gen.py`、`stage3_scoring.py`、`stage5_analysis.py` | 检索建议、分维评分、结构化分析候选生成 | 全部输入用快照/证据 DTO，输出严格 Schema；缺字段不能当 0 分或成功，错误数组类型不能被隐式转换，不能直接写人工内容 |
| AG-R07 | `review/stage1_topic_expansion.py` 至 `stage4_auto_review.py` | 扩写、大纲、章节、审查建议四种能力 | 不留阶段链/写库/自动覆盖；章节按证据检索，审查包含实际证据；缺失或不等长问题/建议不能静默丢弃 |
| AG-R08 | `review/stage3_chapter_writing.py:98`、`stage5_compile.py:64` | 正文＋固定版本目录 → 引用定位/诊断 → 一致参考表 | 不留 set 顺序、伪 APA 拼接、过时引用列表；测修订后同步、首次出现顺序、未知引用、正文与参考编号一致 |
| AG-R09 | `review/stage5_compile.py:79`、`services/review_service.py:375,448` | 已接受文档快照 → 中立文档树 → Markdown/DOCX | 不留动态查库导出和逐行简陋转换；测摘要不重复、参考表一致、列表/表格/代码支持及产物完整性 |
| AG-R10 | `services/construction_service.py:546` | 不发空邮件；发布版本内容＋收件人快照 → 单次发送结果；模板/transport/去重存储分开 | 不留同步 SMTP、忽略部分拒收、发送与 commit 无补偿；测并发、部分失败、发送成功落库失败后的重试 |
| AG-R11 | `deep_research/pipeline.py`、`graph_builder.py` | 引用上下文和元数据展示图的概念 | 不留子串排名、零命中仍返论文、碰撞图 ID、手写 GraphML、假重建成功；这些不是合格 Graph-RAG 实现 |
| AG-R12 | `agents/config/*.yaml` | 检索角度、评分维度、分析字段、综述结构/审查维度、理论/技术/实验视角 | 提示词作为候选素材重新编写；加入版本、输出 Schema、缺证据语义。`llm_defaults.yaml` 只留参数清单，不留旧 stage key/默认配置 |

主要继承风险：下载目标及重定向未经网络范围约束、先读完整响应后限大小；分析/评分空对象被当作成功；综述自动修改可能覆盖人工内容；SMTP 成功后落库失败可重复发送。这些为静态代码风险，不声称已执行真实攻击或故障注入。

配置优先级静态核验：`get_stage_llm_params` 已合并 YAML defaults，LLMClient 再读取 provider 值，实际形成 stage > YAML defaults > provider，和构造器注释不一致。新配置解析需明确单一规则并冻结，不能照抄任一旧注释。

### 明确只作历史存档的 Agent 实现

- 所有 construction/review 的 `run`、pipeline 状态推进、直接 commit、全局 Paper 文件/分析覆盖逻辑。
- `base.py` 项目内存队列和 SSE 绑定，`stage6_storage.py` 项目唯一缓存路径及 JSON 向量替代。
- `dialogue_agent.py` 伪流式切片、输出后再写入、按历史长度算轮号、活项目数据读取；摘要只留任务意图。
- `graph_builder.py` rebuild 存根、手写 GraphML、旧图缓存机制。
- 旧阶段编号、sub_mode 名、函数签名和错误事件协议，不作为新契约约束。

## 6 前端拆分结果

前端没有需要保留的完整业务页面。除第 3 节展示片段，其余保留交互需求后重写。

| 编号 | 旧来源 | 应留下的交互或业务规则 | 重写内容和关键验证 |
| --- | --- | --- | --- |
| F-R01 | `src/contexts/AuthContext.tsx` | 恢复身份、登录后获取用户、登出清理本地身份 | 新认证状态机；临时网络失败不混同失效；测迟到 `/me` 在登出后不能恢复用户、切账号/停用/401 |
| F-R02 | `api/client.ts`、`auth.ts`、`admin.ts`、`config.ts` | 分类错误、认证联动、取消请求需求 | 旧协议包装为 D；新客户端处理 204、非法 JSON、错误正文、特殊路径参数，不保留 `as T` 当验证 |
| F-R03 | `src/pages/LoginPage.tsx` | 字段输入、提交禁用、错误反馈、返回内部目标 | 重写页面/Provider；验证重复提交、注册后认证失败、query/hash 恢复 |
| F-R04 | `src/pages/SettingsPage.tsx` | 资料/个人模型/来源/收件人/管理员用户/系统模型/系统邮件分开管理 | 拆独立加载保存状态；不丢未保存编辑；秘密使用已配置及更新/清除语义；收件人解析后校验去重 |
| F-R05 | `src/pages/HealthPage.tsx` | 各探针独立展示、部分失败可见 | 按权限独立请求；loading/error/unknown 区分；一项失败不隐藏其他结果 |
| F-R06 | `src/pages/ProjectsPage.tsx`、`components/ProjectModal.tsx` | 列表/空态、项目字段编辑、错误保留、删除确认 | 不留 mode/status/旧统计/级联说明；测表单关闭重开后的迟到结果、空白名称和重复提交 |
| F-R07 | `components/AppShell.tsx`、`src/App.tsx` | 身份徽标、初始化状态、认证导航意图 | 旧业务导航为 D；路由鉴权不替代 Project 授权，导航不提交模式切换 |
| F-R08 | `components/InspectorPanel/*` | 脱敏建议/依赖/耗时展示 | 请求编排重写；Project/Run 切换清理或分区旧数据；权限降级后不残留私有诊断 |
| F-R09 | `src/utils/format.ts:17` | Blob 下载及资源释放操作思路 | 实现重写：先验状态、正确解析 filename/filename*、避免下载错误响应 |
| F-R10 | `src/utils/format.ts:32`、`src/hooks/useProjectEventStream.ts` | 流解析与业务消费分离、取消及终态需求 | 旧 SSE 实现为 D；测 CRLF/跨块/中文字节/多行 data、显式终态/异常断流、对象绑定及适用分期的去重/恢复 |
| F-R11 | `src/components/Modal.tsx` | 对话框外观及未保存修改提示需求 | 不留不完整交互实现；焦点捕获恢复、Esc、背景隔离和读屏语义重建 |

前端高风险证据：SettingsPage `:162,177` 创建硬编码 `sk-demo` 示例配置，不迁入；AuthContext 无迟到身份响应防护；Inspector 整组 Promise.all 与旧数据留存可能展示前一 Project 诊断；SSE 仅按 LF 分帧且 EOF 无条件回调完成，不能表示业务成功。

`vite.config.ts`、`tsconfig.json`、`package*.json`、`main.tsx`、API 导出索引属于工程装配，不是业务资产，按新工程实际需要重建。旧依赖锁仅作为历史环境证据；不要求旧别名、旧目录结构和入口继续可用。

## 7 测试留存与淘汰结果

| 编号 | 旧来源 | 留存场景 | 淘汰与新增断言 |
| --- | --- | --- | --- |
| T-R01 | `backend/tests/unit/test_base.py` | JSON/外围 fence/数组/非法输入 | 不保留内存队列满静默丢弃断言；增加 Schema/超大输入；当前没有可直接继承的 HTTP transport 测试 |
| T-R02 | `test_ids.py`、`test_errors.py`、`test_schemas.py` | ID 形状、错误分类/安全展示、序列化、降级场景 | 旧长度/前缀/阶段字段不约束新契约；500 次无碰撞不证明唯一；补秘密脱敏 |
| T-R03 | `integration/test_email_permissions.py:25,36,46` | 普通用户不能改系统发件配置/读管理员设置，普通响应不含系统秘密 | 用新接口重写并补管理员跨 Project 私有资产拒绝 |
| T-R04 | `integration/test_construction_pipeline.py` | 故障归属正确 attempt、此前成功成果不被污染 | 丢旧 StageRecord 与文本兼容断言；追加写资格、版本发布、人工保护 |
| T-R05 | `integration/test_dialogue.py:83` | LLM 故障注入 | 淘汰“失败后 Turn 数不变”；应保留用户输入、失败 attempt 和诊断 |
| T-R06 | `integration/test_mode_switch.py:80` | 未授权访问拒绝 | 淘汰允许 `(200,403,404)` 的断言；明确身份、拒绝成功、检查正文/文件/诊断泄漏 |
| T-R07 | `backend/tests/*conftest.py`、contract 工具 | mock 故障注入、独立测试库、OpenAPI 检查 | fixture/执行壳重写；禁止回退业务库；内部 commit 与后台写入可清理；不对业务环境 fuzz |
| T-R08 | 前端 Login/Settings/Health/ProjectModal 测试 | 认证反馈、失败保留、部分失败、收件人与系统邮件权限交互 | 重写 mock/契约；隐藏按钮不证明服务端授权 |
| T-R09 | `frontend/src/pages/DialoguePage.test.tsx:149` | 迟到查询不覆盖已收回复片段 | 按 ResponseAttempt 身份合并；不留自动创建旧会话/旧事件字段 |
| T-R10 | 前端 Shell/Workspace/Review/Inspector/hook 测试 | 导航、人工编辑、错误可见、对象切换 | 旧模式/阶段断言存档；补切换竞态、取消/关闭可观察性 |
| T-R11 | `e2e/specs/*` | 登录、手动构建、研究、综述、诊断和失败展示场景 | 重建确定性端到端数据/假 Provider；只断言 body 可见和条件跳过断言的用例全部淘汰 |

测试方面的严重/高风险证据：

1. `backend/tests/integration/conftest.py:35` 回退 `DATABASE_URL`，末尾 rollback 无法撤销服务内部 commit，旧 fixture 不复用。
2. 权限测试允许 HTTP 200，不能作为隔离证据；失败对话“不写入”与新设计相反。
3. `e2e-002/004/007` 用浏览器 `page.route` 拦截实际由后端 httpx 发出的模型调用，拦截范围不匹配。
4. `e2e/global-setup.ts:16,38` 发 username，但登录 Schema 要 credential；失败允许空 JWT；teardown 无实质清理。
5. `e2e-003/004/006` 有 body 可见或缺元素时不执行断言的路径；`e2e-007` 额外创建测试 EventSource，与产品订阅不同，不能证明产品处理错误流。

原测试代码默认归档，只移植有效场景；工具层可采用 T-X01。pytest/Playwright 工具选择不等于旧 fixture 复用。

## 8 隔离复现与证据限制

以下由对应 subagent 用 AST 单独加载纯函数运行，未导入完整应用，未执行网络或写库。主代理静态抽查了认证、配置、HTTP/SSE、健康探针及权限测试等关键位置；没有独立重跑全部 AST 样例。

| 审查者 | 输入或状态 | 实际结果 |
| --- | --- | --- |
| Agent 审查 | OpenAlex `primary_location.source=null` | `AttributeError` |
| Agent 审查 | 摘要倒排索引 `{"word":[]}` | `ValueError`，空序列无法求 max |
| Agent 审查 | arXiv `https://arxiv.org/abs/hep-th/9901001v2` | 输出 `9901001`，丢失 `hep-th/` |
| Agent 审查 | `(doi=d,title=A)`、`(doi=d,arxiv=x,title=B)`、`(arxiv=x,title=C)` | 留下首条和第三条，桥接标识被丢弃，传递去重失败 |
| 后端审查 | 健康聚合仅 arXiv 为 error | 返回 ok / 所有依赖正常 |
| 后端审查 | 主 LLM degraded；另测全 not_configured | 均返回 ok |

其余发现是静态行为或风险判断，未声称真实漏洞利用、外部 API 兼容或全链路复现。前一轮后端 66 / 前端 25 项通过及构建成功，不影响本轮对旧验收失真的判断。

## 9 主代理综合裁决

- **管理员重置密码分歧：**前端审查建议不要默认继承一次展示临时密码，后端审查对照当前 FR-005 确认允许管理员取得新生成密码转交。采用现行 FR：保留该业务规则，重写授权、生成、审计和显示生命周期；不将“一次展示”本身列为缺陷。
- **LLM fallback：**现行 FR-002/007 要求明确模型选择，不能套用数据源缺省回退或系统 SMTP 规则。分别保留各类配置的正确规则，不整套迁移旧 fallback。
- **健康探针：**连通不等于可用。保留分层探测意图，重写上层判断；默认诊断不隐式触发付费生成。
- **提取与重写区分：**AG-X01/02/03/04 和部分展示片段都附局部修正条件，不能称为原样复用；R 项只保留规则，不复制实现。任何整文件复制均不在本次白名单内。

## 10 后续拆分交付与验收

本轮只交付逻辑拆分。实际提取开始时，对每个入选 X 项建立记录：来源路径/快照、保留片段、舍弃依赖、新语义输入输出、修正点、离线测试结果。**不要求旧应用、旧接口或旧测试仍可运行。**

建议按以下顺序：

1. 将 B-R/T-R 中的权限、账号治理、配置来源、失败留存规则转成新验收场景，先建立不会误写业务库的测试基础。
2. 用中立 DTO 提取实际需要的 AG-X02/03，补来源精度、引用诊断测试；AG-X01 随模型适配器需求引入。
3. 重写身份/配置/Provider transport/下载/邮件/导出规则单元，逐项满足第 4～7 节验收；不接旧 ORM、pipeline、事件队列。
4. 新产品用到哪项 UI 或技术素材再提取哪项，不先迁入整套外围工程。
5. 旧实现全部留在历史快照，不为其接口兼容增加新核心复杂度；知识服务选型、真实数据迁移和延期契约仍按原计划处理。

关闭条件：所有迁入代码可追溯到白名单或新增独立审查；无旧接口/状态机隐藏依赖；新业务规则、错误路径与隔离场景通过。文档中未记录为已完成的物理提取、修复和测试不得提前标完成。

## 11 变更记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.1 | 2026-10-16 | 链接实际提取与删除结果，保留审查时来源及结论 |
| v1.0 | 2026-10-16 | 汇总三名独立 subagent 审查，形成片段白名单、规则拆分、存档项、缺陷证据与验收要求 |
