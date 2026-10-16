# UI / Workspace 设计

文档版本：v1.22
更新日期：2026-10-16
依据文档：`00_layers.md`、`01_functional_requirements.md`、`02_domain_core.md`

## 1. 设计目标

UI / Workspace 层负责用户可见的信息架构、入口、对象切换、状态展示和可操作 affordance。所有写操作最终必须通过 Application Use Cases 校验，前端禁用态只用于改善体验。

本文维护页面、入口、交互和用户可见反馈；需求/分期以 `01` 为准，状态含义和不变量以 `02` 为准。本文与第 9 章索引的四份附录具有相同 UI 规范效力；页面线框与交互说明不能改变业务规则。详细交互只在对应附录维护，主文保留跨模块约束；历史审查单独归档，不作为现行规范。`04` 及以后尚未形成规范，其待细化契约不能反向决定本轮交互。

## 2. 全局页面结构

| 页面 | 主要内容 | 写操作入口 | 关联 FR |
| --- | --- | --- | --- |
| 登录/注册 | 账号登录、注册、公开错误页 | 注册、登录、登出 | FR-001 |
| Project Hub | Project 列表、创建入口、状态、最近活动、Knowledge Version 可用性 | 创建、编辑信息、归档、软删除、私人资产清理 | FR-008 |
| 用户设置 | 账户、LLM、数据源、通知 | 保存配置、测试连接、测试邮件 | FR-002 至 FR-004 |
| 管理员设置 | 用户管理、系统默认 LLM/数据源/SMTP、基础安全配置 | 用户治理、系统配置保存、连接测试 | FR-005 至 FR-007 |
| Project Workspace | Project 内 Construction/Research/Review 工作台与知识资产 | 通过具体对象工作台触发 | FR-011 至 FR-036 |

P1/P2 页面默认不进入 P0 主线框；少量已明确边界的 P1 支撑页可作为参考线框保留，其余仍在第 10 节作为后续能力清单保留，避免第一阶段实现范围膨胀。

## 3. Project Workspace Shell

Workspace Shell 必须绑定当前 Project，并分为以下稳定区域：

| 区域 | 职责 |
| --- | --- |
| 顶层栏 | Projects 返回/选择器、系统级入口、用户菜单 |
| 对象选择栏 | 首行显示当前 Project 名称和最小状态；下列 Construction Workspace、Research Session 列表、Review Run 列表 |
| 主体流程栏 | 首次进入或点击 Project 名称时显示 Project Home；选择对象后替换为对象主工作区，不可折叠 |
| Project 信息面板 | 只读论文库、Project 资料库、Graph、Knowledge Version、构建摘要和知识更新与采用新版本入口；自动更新设置在 Construction Workspace 维护 |
| Run/Session 信息面板 | 当前对象状态、配置快照、阶段、错误、引用、结果摘要 |

Workspace 内不常驻其他 Project 列表；跨 Project 导航通过顶栏 Projects 返回 Project Hub 或打开选择器完成。

切换对象时，主体流程栏和 Run/Session 信息面板必须同步切换。面板展开/折叠、Project 跳转或系统级页面跳转不得中断后台任务或流式回复。

<a id="shell-composition"></a>

### 3.1 Shell 与模块布局组合规则

桌面默认只有一套全局顶栏、一个对象选择栏、一个 Main Workbench 和一个辅助信息区域。Project Assets 与 Object Info 是辅助区域内的两个标签/折叠区，默认显示当前任务需要的内容，不能各自扩展为常驻独立侧栏。没有选中对象时 Object Info 显示安全空态。

| 对象/视图 | 对象选择栏 | Main Workbench | 辅助信息区域 |
| --- | --- | --- | --- |
| Project Home | 当前 Project 与三类对象入口 | 项目概览及创建入口 | Project Assets 摘要，无对象信息 |
| Construction Workspace | 唯一 Construction 入口 | 当前任务/待办、配置、补充请求或历史 Run；选中 Run 后显示其步骤 | Project Assets 或选中 Run 的 Object Info |
| Research Session | 复用 Shell Session 列表 | 对话与输入区 | Object Info 中的 Evidence，或引用指向的 Project Assets |
| Review Run | 复用 Shell Review 列表 | 步骤/章节目录与编辑器 | Object Info 中的 Context/Citations/Final Check，或 Project Assets |

模块线框的 Sessions/Review Runs 映射 Shell 对象栏，Evidence/Context/Citations/Final Check 映射 Object Info，不把完整三栏图嵌入 Main Workbench。Steps/Chapters/Document、构建阶段论文列表属于局部导航，只能在主体内按需展开，不替代或复制全局对象选择。

Project Assets 的论文/PDF/Graph 详情可使用同一辅助区的展开覆盖层，关闭后回到原工作台；不另加永久侧栏、不卸载主编辑器、不切换对象绑定版本。P35 知识更新与 P36/P37 确认使用一次一个的对话框，关闭不改变业务状态。

选择对象时以 Project 与对象标识同步主体、信息面板和引用上下文，过期异步响应不得覆盖新对象。草稿按用户/Project/对象隔离；切换前对未保存人工编辑提供保存、放弃、留在当前对象的选择，不因导航覆盖人工内容或取消后台任务。只读项目和无权限限制对所有布局槽位一致生效。

### 3.2 窄屏与渐进展示

平板/窄屏优先保留 Main Workbench，对象栏变为“对象”抽屉，辅助区变为“资料/对象信息”抽屉；同一时刻最多打开一个辅助抽屉，提供明确关闭/返回入口。Review 章节目录与 Construction 步骤列表改用局部选择器，避免对象、章节、资料三套侧栏同时展开。

断点由前端根据内容可用宽度实现，不以缩小字体或整页横向滚动承载三栏；表格可在自身容器内滚动。布局变化不清空输入草稿、改变对象/版本绑定或中止流式回复。展开详情时焦点进入面板，关闭后回到触发控件，键盘可完成对象切换、编辑、打开和关闭详情。

默认显示当前任务、主要操作、等待原因和绑定版本；Construction 成功区分已发布与核验无变化，后者展示核验既有版本及范围，不触发知识升级提示，详细交互见 Construction 附录 P15/P20；配置快照、诊断、历史列表和完整资产详情按需打开。常见操作不要求用户先理解内部状态机。

### 3.3 Shell 基准线框

### P13 Project Workspace Shell

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Logo  Projects  Settings         Admin*                 [Current Model ▼]  Avatar          │
├──────────────────────┬──────────────────────────────────────────┬──────────────────────────┤
│ Workspace Objects    │ Main Workbench                           │ Info Panels              │
│                      │                                          │                          │
│ Project A            │ ┌──────────────────────────────────────┐ │ [Project Assets ▾]      │
│ active               │ │ Construction Workspace               │ │ Papers / Materials      │
│                      │ │ current object / state / KV baseline │ │ Graph                   │
│ > Construction       │ │                                      │ │ Default KV: KV-12       │
│   Workspace          │ │ object-specific workflow content     │ │ Object KV: KV-12        │
│   Auto policy: on    │ │                                      │ │ Build / 调度未启用    │
│   Terms: 6 active    │ │                                      │ │ [查看知识更新]       │
│                      │ └──────────────────────────────────────┘ │                          │
│ Research Sessions    │                                          │ [Object Info ▾]          │
│ + New                │                                          │ Status / phase           │
│ ┌──────────────────┐ │                                          │ Waiting items            │
│ │ RS-023 active   │ │                                          │ Config snapshot          │
│ │ RS-020 active   │ │                                          │ Diagnostics              │
│ └──────────────────┘ │                                          │ Citations / results      │
│                      │                                          │                          │
│ Review Runs          │                                          │                          │
│ + New                │                                          │                          │
│ ┌──────────────────┐ │                                          │                          │
│ │ RV-008 running  │ │                                          │                          │
│ │ RV-004 done     │ │                                          │                          │
│ └──────────────────┘ │                                          │                          │
└──────────────────────┴──────────────────────────────────────────┴──────────────────────────┘
```

P13 Project Home 状态：

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Logo  Projects  Settings         Admin*                 [Current Model ▼]  Avatar          │
├──────────────────────┬──────────────────────────────────────────┬──────────────────────────┤
│ Workspace Objects    │ Project Home                             │ Info Panels              │
│                      │                                          │                          │
│ > Project A          │ Project No.   PRJ-2026-001               │ [Project Assets ▾]      │
│ active               │ Description   long research topic...     │ Papers / Materials      │
│                      │ Papers 128 | Materials 24                │ Graph                   │
│ Construction         │ Last build      2026-06-08 02:10         │ Default KV: KV-12       │
│ Workspace            │ Last activity   2026-06-08 09:35         │ Build / 调度未启用    │
│ Research Sessions    │ Default KV      KV-12                    │                          │
│ Review Runs          │ Auto policy     on, 6 terms              │ [Object Info ▾]          │
│                      │ [Open Construction] [New Research]       │ No object selected       │
│                      │ [New Review]                             │                          │
└──────────────────────┴──────────────────────────────────────────┴──────────────────────────┘
```

P13 的 Auto policy 表示已保存的检索词策略；P0 摘要同时显示“调度未启用”，只有 FR-009 的 P1 启用后才显示实际调度运行状态和时间。

P13 是进入某个 Project 后的唯一 Workspace Shell，不再展示其他 Project 列表；切换 Project 应通过顶栏 `Projects` 返回 Project Hub 或打开 Project 选择器完成。左侧栏首行显示当前 Project 名称和最小状态，点击 Project 名称或首次打开 Workspace 时，Main Workbench 显示 Project Home 概览；用户选择 Construction Workspace、Research Session 或 Review Run 后，Project Home 概览退出，不持续占用工作界面。

Project Home 只用于快速查看 Project 编号、详细说明、论文数、资料数、最近构建时间、最近活动时间、默认 Knowledge Version 和自动更新摘要，并提供进入构建、深研或综述入口。左侧除 Project 名称外，只展示当前 Project 的唯一 Construction Workspace、Research Session 列表和 Review Run 列表；历史 Construction Run 不与 Session/Run 平级展示，只能在 Construction Workspace 内部查看。选择对象时，Main Workbench 和 Object Info 面板必须同步切换；Project Assets 面板保持只读，承载论文、Project 资料、Graph、默认 Knowledge Version、当前对象绑定 Knowledge Version、构建摘要和知识更新与采用新版本入口。

当 Project 为 archived 时，P13 保持可进入但进入只读模式，禁用新建、启动、继续生成、上传、删除、重跑和基于新知识创建关联会话或新版综述等写操作，并展示只读原因。没有可访问的已发布 Knowledge Version 时，Research Session 和 Review Run 的新建入口禁用；已发布空版本可浏览和新建，明确无项目证据，不隐式回退历史版本。Admin 入口仅对管理员显示；Project Workspace 内的系统级入口条件与 Project Hub 保持一致。

## 4. Workspace 对象入口

### 4.1 Construction Workspace

展示长期检索词、检索词级数据源策略、自动更新开关、构建状态摘要、历史 Construction Run 列表及其状态、配置快照入口、诊断入口、结果入口和手动启动入口。

写操作必须在 Construction Workspace 内触发，不在 Project 总列表中直接执行。

### 4.2 Research Session

展示对话历史、当前绑定 Knowledge Version、Graph-RAG 引用和跳转。同一 Session 存在流式回复时，输入区进入等待态，展示取消或查看状态入口。

### 4.3 Review Run

展示综述主题、范围、大纲、章节列表、章节状态、引用、审查记录、终稿、摘要、关键词、参考文献和当前稿接受状态与 Markdown 下载。章节写入中时，该章节的生成、覆盖操作应锁定；其他章节是否可编辑由应用用例校验。

## 5. 知识资产面板

Project 信息面板提供只读知识资产：

- 论文及 Project 资料的统计、列表、筛选和详情；资料显示标题、content_format、重要摘要、处理状态及来源 Run。
- PDF 或远程资源访问入口，必须使用鉴权或签名 URL。
- Graph 图谱节点、关系和论文详情互跳。
- Project 默认 Knowledge Version 与当前对象绑定版本。
- 缺失、过期、无权限、版本不匹配时的安全空态。

不得提供上传、删除、重新下载、重新解析、重新评分、重新分析、入库、推送或图谱重建动作。

## 6. 禁用态与提示

| 场景 | 展示行为 |
| --- | --- |
| 无可访问的已发布 Knowledge Version | Research/Review 新建入口禁用；空版本不是缺版本，可新建并显示无项目证据 |
| Project archived | Workspace 进入只读模式，写操作禁用并展示归档原因 |
| Project deleted | 禁止进入 Workspace，返回 Project Hub 并展示不可进入提示 |
| 权限不足 | 隐藏不可访问入口或展示无权限空态，后端仍必须拒绝 |
| 配置缺失/失效 | 任务启动按钮显示修复入口，指向用户设置或管理员设置 |
| 构建槽已占用（含 paused Construction Run） | 允许登记下轮请求但不占槽、不启动第二个写入者，展示占槽 Run；显式继续沿用原实例及原槽，显式取消清除占槽，显式重跑撤销旧写资格并将旧 Run cancelled 后由新实例安全接管 |
| 内容覆盖风险 | 弹出覆盖确认，说明将覆盖的内容来源和最后编辑者 |
| 对象绑定历史 Knowledge Version | 展示“有更新可查看”或“已固定文献范围”，不把历史版本视为失效，不自动改写内容 |

内容保护的权威判断由 Application Use Cases 和后台状态执行。UI 只展示用户完成当前决策所需的最小反馈，例如禁用原因、覆盖确认、冲突对象、影响范围和最后编辑者；不得依赖前端状态绕过后台保护，也不展示完整内部状态机。

## 7. 上下文恢复

P0 恢复最近打开 Project、最近打开对象、基础面板展开状态和输入草稿。P1 增强恢复滚动位置、日志和步骤落点、筛选条件、最近查看的论文或 Graph 节点。

恢复失败时应回到安全空态或 Project Hub，不得打开其他用户或其他 Project 的上下文。

## 8. UI 验收检查

- 每个 P0 FR 都能找到用户入口或明确的后台入口。
- P1/P2 默认进入后续清单；已明确边界的 P1 参考线框须标注分期。FR-018 版本刷新专用 Review 重跑与单条论文/资料补充属于 P0。
- UI 所有写操作对应一个 Application Use Case。
- archived/已删除不可进入/无权限/配置缺失/锁冲突/知识更新均有可见反馈。
- 知识资产面板只读。
- 引用跳转能处理缺失、过期和越权。
- 响应式范围至少覆盖桌面浏览器和平板/窄屏可用布局。
- Research/Review 线框复用 Shell 对象栏与 Object Info，无重复对象列表或第四个常驻信息栏。
- 窄屏一次只展开一个辅助抽屉，关闭后恢复焦点；布局变化保留输入与流式状态。
- 切换对象后旧请求结果不覆盖新对象，引用保留原绑定版本；未保存人工编辑可保存、放弃或取消切换。
- P0 导航不出现 Plaza、Backend、Notifications，构建流程不出现邮件步骤；P1 参考图不作为 P0 验收控件。



## 9. 附录与页面索引

| 附录 | 页面与交互 | 维护范围 |
| --- | --- | --- |
| [系统页面](03-01_ui_system_pages_appendix.md) | P01、P02、P06a–P06d、P10a–P10f | 登录、Project Hub、个人/管理员设置；P06d 为 P1 参考，P10f 仅 P2 范围占位 |
| [Construction](03-02_ui_construction_appendix.md) | P15–P21、P43、P44、P40 | 配置与请求队列、启动、运行步骤；P21 为 P1 参考 |
| [Research / Review](03-03_ui_research_review_appendix.md) | P23、P45、P46、P26–P28、P41、P42 | 对话、流式恢复、大纲、章节、终稿 |
| [共用交互](03-04_ui_shared_interactions_appendix.md) | P14、P30、P35–P39 | 只读资产、知识更新、保护确认、恢复和对象切换 |

P13 Shell 留在主文，作为模块组合基准。P 编号是稳定标识，不代表实现顺序；旧 P07/P08/P09 对应系统附录 P06b/P06c/P06d，不新增重复页面。迁移记录见 [历史审查](../proposals/ui_design_historical_review_2026-06-01.md)。

## 10. 后续能力清单

以下能力不进入 P0 导航与可执行控件；已保留的 P1 参考线框只用于后续设计，不授权提前实现：

| 后续范围 | 对应 FR | 处理说明 |
| --- | --- | --- |
| 系统自动构建调度 | FR-009, P1 | P0 保留 FR-020 检索词自动更新策略配置，显示调度未启用；下次运行时间及自动 Run 在 P1 启用后展示 |
| 用户通知与业务邮件推送 | FR-004、FR-027, P1 | P06d/P21 保留参考线框，P0 隐藏 Notifications 和邮件步骤；不影响 FR-006 系统 SMTP 配置 |
| 平台硬限制配置 | FR-006/FR-007, P1 | 模型白名单、数据源范围、系统速率/并发上限不进入 P0 表单 |
| 观点广场与发布页 | FR-010, P2 | 保留需求，不在 P0 顶层导航和主线框展示 |
| 系统状态与诊断页 | FR-006, P2 | 管理员系统诊断不进入 MVP 主线框 |
| Research 输出倾向、总结文件和导出 | FR-029, FR-030, P1 | 不在 P0 Research Session 顶栏展示 |
| Project/Run/Session 导出中心 | FR-019, P1 | 后续补异步任务状态、批量/格式转换和失败报告；P0 单篇终稿 Markdown 下载由 FR-034 提供 |
| Review 版本历史、差异和回退 | FR-036, P2 | 不在 P0 Review Run 入口展示 |
| Run/Session 复制、通用重跑、归档和删除 | FR-014, FR-015, P1 | 不使用旧版统一实例操作弹窗；FR-018 版本刷新专用 Review 重跑为 P0，由 P35 承载 |
| 批量补充论文/资料及数据表上传 | FR-023, P1 | P0 保留 Construction Workspace 内单条论文补充和支持格式单文件资料请求队列；多媒体为 P2 |

## 11. 更改记录

| 版本 | 日期 | 变更摘要 |
| --- | --- | --- |
| v1.19 | 2026-10-16 | 拆出四份同效力 UI 附录与历史审查；补齐 Shell 组合、窄屏和上下文规则，清理分期残留及页面引用 |
| v1.18 | 2026-10-16 | 对齐知识库并行构建附录：非阻塞更新、固定范围、关联新会话/新版综述、候选确认与待纳入；移除旧依赖构建门槛及 D01 待决提示 |
| v1.20 | 2026-10-16 | 明确 paused ConstructionRun 的继续、取消与重跑实例交接语义 |
| v1.17 | 2026-10-16 | 澄清 UI 规范边界并修失效依据，对齐 P13、资料补充/只读入口、暂停占槽、P35 单版本新结果与 P28 默认接受；不拆分附录 |
| v1.16 | 2026-06-08 | 调整 P13 Project Workspace：移除常驻 Project 详情条，将左侧栏首行改为当前 Project 名称；Project 详细信息仅在首次打开 Workspace 或点击 Project 名称时以 Project Home 展示。 |
| v1.15 | 2026-06-08 | 根据 FR-011/FR-012/FR-013/FR-018 重新设计 P13：移除 Workspace 内 Project Rail，改为当前 Project 绑定的对象切换、主体工作区、只读 Project Assets 和同步 Object Info 面板。 |
| v1.14 | 2026-06-08 | 收紧 P10e Security：删除密钥脱敏、密钥隔离、快照禁止明文密钥等固定化安全规则的 UI 展示，只保留管理员可查看或更改的安全参数和 P1 硬限制。 |
| v1.13 | 2026-06-08 | 根据 FR-006/FR-007 调整 P10e Security 为基础安全限制与 P1 硬限制配置，并新增 P10f Backend（P2）展示系统状态、调度、用量和脱敏诊断后台。 |
| v1.12 | 2026-06-08 | 调整 P10d SMTP 配置：将 TLS/SSL 改为 Encryption 选择，并新增 Auth Type 以支持 None、Password、Token 和 API Key 认证方式；将动态凭据字段改为认证凭据分组。 |
| v1.11 | 2026-06-08 | 重构管理员设置线框：去掉 Users/System 二分，改为 P10a-P10e 同级侧栏入口 Users、LLM、Sources、SMTP、Security；P10a 用户操作改为动作下拉并标注二次确认规则；P10b 与 P07 的 LLM 配置实例编辑结构对齐。 |
| v1.10 | 2026-06-08 | 增强 P07-P09 列表-详情交互表达：中间栏增加当前选中态，右侧编辑器标题显示正在编辑的配置实例、数据源或收件邮箱。 |
| v1.9 | 2026-06-08 | 调整 P07 LLM 设置：中间栏从 provider 类型改为 LLM 配置实例列表，支持多个同类型配置；右侧编辑器拆为基础连接设置、可用模型查询和详细参数配置，当前模型选择回归主界面顶栏。 |
| v1.8 | 2026-06-07 | 收敛 P06 账户页，移除最近模型；在 P07 增加当前模型选择；新增 P09 通知设置参考线框，承载收件邮箱、通知偏好和测试邮件。 |
| v1.7 | 2026-06-06 | 移除 P02 Project 级暂停/恢复入口，将编辑按钮改为编辑信息，并把自动更新状态展示为 Construction Workspace 管理的摘要；明确 deleted Project 不在 Workspace 中展示。 |
| v1.6 | 2026-06-06 | 拆分 P01 登录/注册为同一认证入口的两个状态，明确登录凭证可为用户名或邮箱，注册需分别填写用户名和邮箱；修正 P02/P13 顶栏 Admin 条件入口标记；重画 P02 Project Hub，移除左侧全局状态栏并补充 Project 编号、说明、统计和完整时间字段。 |
| v1.5 | 2026-06-01 | 清理旧版遗留 UI：P1/P2 线框移入后续能力清单；重画 Construction Workspace、知识资产面板和补充论文请求；修正空邮件保护为强制启用。 |
| v1.4 | 2026-06-01 | 最小化补齐 P0 UI 缺口：新增 P43-P46；将内容保护收敛为后台裁决、UI 最小反馈；保留 P47 为后续 P1 增强。 |
| v1.3 | 2026-06-01 | 写入 UI 设计审查结果；修正 Project Workspace 关联 FR 范围为 FR-011 至 FR-036；记录 Construction、Research、Review 和导出体验的后续补强项。 |
| v1.2 | 2026-05-22 | 建立 UI / Workspace 分层设计，迁入并适配旧页面线框。 |
| v1.21 | 2026-10-16 | 同步构建排队与占槽区分、重跑旧实例终态和无变化成功展示；详细状态交互由附录维护 |

本次修订 v1.22（2026-10-16）：落实 R1-A 至 R4-A 与人工补充裁决：学术引用建议、轻量稿件编辑及下载、风险确认移除、空版本可新建研究、论文及资料入库后只读、筛选等待点追加词。仅设计同步，未实现或运行验收。
