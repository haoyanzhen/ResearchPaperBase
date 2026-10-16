# 核心重写与外围复用计划

文档版本：v1.2  
日期：2026-10-16  
适用项目大版本：v1  
状态：旧实现提取与清理已执行，新核心未开始；数据库未操作

实际进展见[清理执行记录](../workorders/legacy_cleanup_execution_2026-10-16.md)：候选片段存入 `archive/maybe_useful/`，旧应用代码及依赖环境已删除。下文原文件路径及“原文件不动/暂时存档”等描述保留为计划历史，已执行范围以该记录及分类清单为准；后续新核心工作包仍未实施。

后续独立审查：[外围代码独立审查与逻辑拆分结果](reuse_independent_review_2026-10-16.md)。三名 subagent 对候选复用项审查后，没有整模块通过；下文“审查后复用”“拆分复用”为原候选范围，最终去留以该报告的 X 片段白名单、R 规则重写和 D 历史存档裁决为准。无需维持旧项目完整性或接口兼容，只保留有用逻辑；代码尚未物理拆分。

## 1 目标与范围

按最新需求与领域设计重建业务核心，保留可独立验证的外围能力。旧代码作为历史行为和适配器实现参考，不作为新领域模型或验收规则的依据。本轮只新增本计划。

直接在旧架构上持续加功能的总体风险为高：项目级模式与状态、全局论文分析、阶段直接写正式数据、进程内任务和事件等假设贯穿多层。计划通过重建核心边界降低风险，不承诺复用比例或未经任务拆分的工期。

依据：[需求](../design/01_functional_requirements.md)、[分层](../design/00_layers.md)、[领域](../design/02_domain_core.md)、[版本附录](../design/02-02_construction_versioning_appendix.md)、[资产附录](../design/02-03_construction_assets_appendix.md)、[恢复附录](../design/02-04_run_recovery_appendix.md)、[工作台](../design/03_ui_workspace.md)。04 及以后仍为待细化草案；本计划不将其定稿，不恢复此前延期事项，也不提前实施 P1/P2 功能。

## 2 分类与风险标准

| 分类 | 后续处理 | 当前处理 |
| --- | --- | --- |
| 重写 | 按新契约实现替代模块；旧版本进入历史存档 | 原文件不动 |
| 拆分复用 | 只提取不依赖旧 ORM、状态机和事务的函数；业务编排重写 | 原文件不动，不整文件复制 |
| 审查后复用 | 经权限、契约及测试核验后适配保留 | 仅列为候选，不视为已通过 |
| 暂时存档 | 从新产品运行与测试路径退出，保留来源；对应能力到实施期再处理 | 不移动、不删除、不停用 |

风险等级用于评估继承旧实现的后果：严重表示可能破坏隔离、版本或写入正确性；高表示可能造成恢复失败、错误验收或大范围返工；中表示范围较局部但需契约适配；低表示主要为可独立验证的展示和工具逻辑。并非已复现全部风险或完成安全审计。

## 3 后端逐模块处置

下列路径均相对仓库根目录；目录项覆盖其子模块。更具体的文件或函数条目优先。

### 3.1 数据模型与迁移

| 现有文件 | 处置 | 新实现职责与理由 | 继承风险 |
| --- | --- | --- | --- |
| `backend/app/models/project.py` | 重写 | 分开 Project 生命周期、检索词修订、运行状态与 Workspace 上下文；不能延续项目单一 mode/status 作为执行中心 | 严重 |
| `backend/app/models/stage.py` | 重写 | Stage/Attempt 归属明确的 Run；加入输入引用、合法状态、诊断与写资格校验所需信息 | 严重 |
| `backend/app/models/paper.py` | 重写 | 分开共享论文身份、ProjectPaper、ProjectMaterial、DocumentAsset 与项目内解析/分析修订；保留人工来源与确认记录 | 严重 |
| `backend/app/models/dialogue.py` | 重写 | ResearchSession 固定知识版本；Turn 与 ResponseAttempt 分离，失败和部分回复可追踪 | 严重 |
| `backend/app/models/review.py` | 重写 | ReviewRun 固定知识版本，明确大纲、章节、人工编辑、终稿接受/拒绝与导出资产身份 | 严重 |
| `backend/app/models/recommendation.py` | 暂时存档 | 到相应推荐/观点能力实施时依据当前 FR 重评；不得由旧表反推新范围 | 中 |
| `backend/app/models/user.py` | 审查后复用 | 核验用户、系统/个人配置、停用与管理员边界；运行配置快照和 Project 权限需新实现 | 高 |
| `backend/app/models/base.py` | 审查后复用 | ORM 声明基础可保留，避免注册旧业务表 | 低 |
| `backend/alembic/versions/0001_initial_schema.py`、`0002_admin_columns.py` | 暂时存档旧迁移历史 | 不改写已应用迁移；是否建立独立新库或增量迁移由第 7 节决定 | 严重 |
| `backend/alembic/env.py`、`script.py.mako`、`backend/alembic.ini`、`backend/scripts/init_db.py` | 审查后复用 | 重接新模型和迁移入口；测试/开发/生产目标必须显式隔离 | 高 |

需新增的核心持久化对象包括 ConstructionRun、KnowledgeVersion/候选与快照、运行配置快照、写资格记录、Project 资产及其修订、Workspace 上下文、Research/Review 运行对象。具体字段和约束须由后续 05/07 设计确定，不把本清单当作 SQL 定稿。

### 3.2 应用服务与 API

| 现有文件 | 处置 | 新实现职责与复用边界 | 继承风险 |
| --- | --- | --- | --- |
| `backend/app/services/construction_service.py` | 重写 | Run 创建、原子占槽、输入冻结、候选写入、人工决定冲突检查、发布与退出；邮件发送拆到独立适配器 | 严重 |
| `backend/app/services/project_service.py` | 重写 | 拆分项目生命周期、权限、资产查询/修订、调度命令；旧 switch_mode、评分覆盖和推荐逻辑不迁入新核心 | 严重 |
| `backend/app/services/dialogue_service.py`、`review_service.py` | 重写 | 按固定版本操作独立 Session/Run；明确人工修改和新版本采用；导出格式化函数可单独评估 | 严重 |
| `backend/app/services/auth_service.py`、`admin_service.py` | 审查后复用 | 核验首次管理员初始化并发、停用账户、删除副作用、管理员不能自动获得 Project 私有访问权 | 高 |
| `backend/app/services/config_service.py` | 拆分复用 | 个人/系统配置回退思路可保留；运行时解析、快照、凭据引用与事务边界重写 | 高 |
| `backend/app/api/v1/projects.py`、`construction.py`、`dialogues.py`、`review.py`、`tasks.py`、`inspect.py` | 重写 | 按新资源和命令组织 API，统一权限、错误、幂等及诊断范围；不以旧响应格式限制新模型 | 高 |
| `backend/app/schemas/project.py`、`construction.py`、`dialogue.py`、`review.py` | 重写 | 与新契约一致，显式携带对象与版本身份，区分候选和已发布数据 | 高 |
| `backend/app/api/v1/auth.py`、`admin.py`、`config.py`、`health.py` 及对应 schemas | 审查后复用 | 核验字段、秘密脱敏、权限、健康探针语义；健康接口不替代业务验收 | 中至高 |
| `backend/app/api/v1/router.py`、各包 `__init__.py` | 重写装配 | 新入口只注册新实现及已通过复用检查的组件，避免导入副作用带回旧代码 | 高 |
| `backend/app/main.py` | 拆分复用 | FastAPI 装配思路可保留；生命周期、调度、任务启动及运行恢复重新实现 | 高 |

### 3.3 Agent 与基础设施

| 现有文件 | 处置 | 可保留部分与必须重写部分 | 继承风险 |
| --- | --- | --- | --- |
| `backend/app/agents/construction/pipeline.py` | 重写 | 旧状态回写缺少写资格校验；新流程由应用用例推进，Agent 不直接决定知识发布 | 严重 |
| `construction/stage1_keyword_gen.py`、`stage2_retrieval.py`、`stage3_scoring.py` | 拆分复用 | 提取 Provider HTTP 请求、结果规范化和提示词参考；检索输入、去重、评分确认、ORM 写入和事务全部重写 | 高 |
| `construction/stage4_download.py`、`stage5_analysis.py` | 拆分复用 | 提取下载/解析及模型调用工具；文件归属、分析修订、确认保护、缓存身份与持久化重写 | 严重 |
| `construction/stage6_storage.py` | 重写，旧实现存档参考 | JSON 缓存不是向量索引；新流程需候选版本隔离、向量/图谱可用性检查及发布门槛，不能覆盖 Project 唯一路径冒充版本发布 | 严重 |
| `backend/app/agents/deep_research/pipeline.py`、`dialogue_agent.py`、`graph_builder.py` | 重写，算法片段仅供参考 | 检索必须绑定知识版本和项目权限，引用可追溯；图谱方案待选型，旧关键词/图谱实现不作为新 Graph-RAG 完成证据 | 高 |
| `backend/app/agents/review/pipeline.py` 及 `stage1_topic_expansion.py` 至 `stage5_compile.py` | 重写编排，拆分复用格式化工具 | 新 Run/版本绑定、章节确认、人工保护、默认接受与拒绝清理；提示词、DOCX/Markdown 格式化片段另行验证 | 严重 |
| `backend/app/agents/base.py` | 拆分复用 | `parse_json_response`、YAML 读取和 LLM HTTP 封装可评估；`get_llm_client` 改用运行配置快照；项目级内存队列、事件发送和错误绑定重写 | 高 |
| `backend/app/agents/config/*.yaml` | 暂时存档为候选素材 | 逐阶段复核输入、输出 Schema、版本和人工确认语义后采用；不直接作为新流程默认提示词 | 中 |
| `backend/app/core/deps.py` | 重写授权装配，复用认证提取逻辑需审查 | 区分登录身份、Project 权限、资产权限和任务处置权 | 高 |
| `backend/app/core/security.py`、`config.py`、`database.py`、`logging.py`、`errors.py`、`schemas/common.py` | 审查后复用 | 核验密钥、事务归属、日志脱敏和错误信封；保留技术框架不等于保留旧默认值 | 中至高 |
| `backend/app/utils/ids.py` | 审查后复用 | ID 生成工具独立验证，按新对象补充前缀约定 | 低 |

该表中 `construction/` 简写为 `backend/app/agents/construction/`。任务持久化、调度与事件机制须通过故障测试后接入；本计划不预选队列、向量库或 Memory 框架。

## 4 前端逐模块处置

| 现有文件 | 处置 | 实施要求 |
| --- | --- | --- |
| `frontend/src/pages/ProjectWorkspacePage.tsx`、`DialoguePage.tsx`、`ReviewPage.tsx` | 重写 | 按独立 Run/Session 与 KnowledgeVersion 展示；恢复工作上下文不改变业务状态；人工编辑与生成内容分开 |
| `frontend/src/components/AppShell.tsx`、`frontend/src/App.tsx` | 重写业务导航与路由装配 | 路由、面板和对象选择遵循 03；基础布局与认证路由包装可提取复用 |
| `frontend/src/hooks/useProjectEventStream.ts` | 重写 | 使用新认证和事件身份契约；对象级过滤、去重与断线后状态核对；回放增强按既定分期实施 |
| `frontend/components/InspectorPanel/*` | 重写数据契约与装配，展示片段择优复用 | 诊断绑定明确对象；不扩大管理员权限，不混淆候选和发布统计 |
| `frontend/types/index.ts` | 重写业务类型 | 旧 Project mode/status 与阶段 JSON 不能继续作为新接口约束 |
| `frontend/api/projects.ts`、`construction.ts`、`dialogues.ts`、`review.ts`、`tasks.ts`、`inspect.ts` | 重写 | 跟随新 API 契约；不通过兼容旧接口保留错误业务语义 |
| `frontend/src/pages/ProjectsPage.tsx`、`frontend/src/components/ProjectModal.tsx` | 拆分复用 | 表单和列表外观可用；Project 生命周期、权限、统计和导航重接 |
| `frontend/src/pages/LoginPage.tsx`、`SettingsPage.tsx`、`HealthPage.tsx` | 审查后复用 | 验证新配置范围、管理员边界及错误反馈；设置页不直接持有运行配置快照 |
| `frontend/src/contexts/AuthContext.tsx`、`frontend/api/client.ts`、`auth.ts`、`admin.ts`、`config.ts` | 审查后复用 | 核验凭据、登出/失效、错误处理和响应格式 |
| `frontend/src/components/Modal.tsx`、`Alert.tsx`、`src/utils/format.ts`、`src/styles.css` | 审查后复用 | 主要保留独立 UI/格式化；剔除与旧页面状态绑定的样式约定 |
| `frontend/src/main.tsx`、`frontend/api/index.ts` | 适配装配 | 只引用新路由、客户端与通过复用检查的组件 |
| `frontend/vite.config.ts`、`tsconfig.json`、`index.html`、`src/vite-env.d.ts`、`package.json`、`package-lock.json` | 保留工程骨架并核验 | 核验构建代理、依赖和版本标识；同步项目 v1 约定，不借此进行无关升级 |

## 5 测试与运行配置处置

| 范围 | 处置 |
| --- | --- |
| `backend/tests/unit/test_ids.py`、`test_errors.py` | 工具/错误契约确认后复用适用断言 |
| `backend/tests/unit/test_base.py` | 拆分：JSON/HTTP 工具测试可复用；旧事件与配置工厂测试按新实现重写 |
| `backend/tests/unit/test_schemas.py` | 按新业务契约重写，旧断言存档 |
| `backend/tests/conftest.py` | 保留 mock 思路，按新适配器入口重写 patch 目标 |
| `backend/tests/integration/conftest.py` | 重写；显式独立测试库，禁止回退业务 `DATABASE_URL`；隔离服务内部 commit，验证测试数据可清理 |
| `backend/tests/integration/test_construction_pipeline.py`、`test_dialogue.py`、`test_mode_switch.py` | 暂时存档旧业务断言；新增基于 Run/版本的集成测试，旧模式切换测试不直接迁移 |
| `backend/tests/integration/test_email_permissions.py` | 作为权限场景参考，按新配置和发送链路改写 |
| `backend/tests/contract/*` | 工具壳可复用，目标 OpenAPI、认证、错误预期和数据隔离重新配置 |
| 前端重写模块对应的 `*.test.tsx` 与 `useProjectEventStream.test.tsx` | 旧测试存档，新测试验证当前需求；不能仅为保留旧测试而保持旧模型 |
| 前端登录、设置、健康页及通用组件测试，`frontend/src/test/*` | 复核契约后保留适用场景与测试工具 |
| `e2e/specs/*`、`e2e/global-setup.ts`、`global-teardown.ts`、`playwright.config.ts` | 旧流程暂时存档；浏览器工具壳可复用，按新对象链路重建场景和隔离环境 |
| `backend/requirements.txt`、`backend/pytest.ini`、运行环境模板 | 核验后复用；新依赖随对应工作包引入，不进行全量技术栈更换 |

2026-10-16 已有验证：后端单元测试 66 项通过，前端 25 项通过，前端构建通过。此结果仅作为旧实现快照信息；未验证新设计符合性、真实外部服务或迁移安全性。

## 6 暂时存档策略

### 6.1 存档范围

1. 保存整个旧应用的可追溯快照：`backend/`、`frontend/`、`e2e/`，以及当时的运行说明和依赖锁定文件。重写模块的旧版本也属于此快照。
2. 单独登记旧迁移、旧状态机/接口/类型、旧业务测试、推荐模块和提示词素材；保留原路径、来源提交或快照标识、用途及复用状态。
3. 当前 `docs/design/00–03` 及领域附录是新设计依据，不随旧代码归档。历史设计与执行记录继续保留其历史身份。

### 6.2 后续执行方式

- 实施启动时先记录工作区与未提交差异，建立经过核对的历史快照；不能只记录当前 HEAD，因为最新设计仍有未提交内容。避免将凭据、`.env`、用户文件和数据库内容纳入代码存档。
- 优先用独立 Git 历史引用保留旧应用；如需要目录存档，使用独立、明确排除在运行/构建/测试之外的位置。具体方式在启动工作包确定，本轮不创建分支、标签或存档目录。
- 新运行入口只导入新核心与经过核验的外围模块；不让新旧服务同时写同一业务数据或共享可覆盖的知识缓存。
- 旧迁移文件保留可追溯性。任何移动须先确认现有部署是否仍依赖该迁移链。
- 存档完成的验收：能定位旧源文件和依赖；新入口与测试收集不加载存档代码；所提取模块记录新旧路径和验证结果。

“暂时存档”不等于立即删除，也不表示能力永久取消。能力按当前 FR 分期重新进入实施，不为旧代码完整性提前扩大范围。

## 7 数据迁移与切换条件

目前尚未确认是否存在必须保留的真实业务数据，因此保留两条实施分支：

| 条件 | 后续方案 | 验收 |
| --- | --- | --- |
| 仅有可丢弃开发数据，且已确认 | 新建隔离数据库与存储命名空间，建立新迁移基线；旧库先保留 | 新库可重复初始化；未删除或覆盖旧数据 |
| 有需保留的数据或情况未明 | 保留旧迁移链和只读导出，设计到新模型的显式迁移；先在副本演练 | 计数、归属、文件引用与权限核对，迁移可重复执行且有回退步骤 |

旧共享分析无法证明属于哪个 Project 时，不自动复制成各 Project 的私有确认结果；旧会话没有版本绑定时，不伪造历史 KnowledgeVersion。此类记录应保留来源并列入人工归属/历史兼容处理清单。

切换前停止旧写入，验证新旧数据边界、文件备份与恢复。新系统已产生数据后，不得直接将旧代码连回新库作为回滚；回滚必须说明新写入的保留或补偿方式。

## 8 分阶段工作包

阶段只表示依赖顺序，不代表已开始。04+、SQL、技术选型等延期范围在恢复处理前维持原状态。

| 工作包 | 具体产出及涉及范围 | 开始条件 | 关闭条件 |
| --- | --- | --- | --- |
| W0 基线与存档准备 | 核对本计划清单、当前设计版本、数据保留需求、历史快照和新旧入口策略；更新进度入口 | 开始实施整理 | 文件处置可追踪、未提交改动有明确归属、数据分支确定 |
| W1 P0 验收与最小契约 | 需求→用例→数据→API→测试映射；围绕首次构建发布补齐 04/05/07/08/09 必要契约 | 对相应延期范围恢复处理 | 状态、写资格、发布、资产隔离、失败路径有明确验收；不要求全部下游文档一次定稿 |
| W2 基础与领域骨架 | 新模型/迁移、身份配置外围复用、Project 权限、运行配置快照、事务/错误接口 | W0、W1 相关条目闭合 | 独立测试库可初始化，越权访问被拒绝，运行快照不随个人配置修改漂移 |
| W3 Workspace 最小壳 | 新路由、对象选择、上下文恢复、状态与只读资产入口；未完成能力明确禁用 | W2 与 UI/API 契约可用 | 切换/恢复 Workspace 不改写 Run、Session 或知识状态 |
| W4 手动构建与版本发布 | 单条论文/资料 P0 主路径、检索筛选解析分析、人工确认、候选隔离、知识同步及发布 | W2；所需知识服务方案已明确 | 首个可用 KnowledgeVersion 端到端发布；并发、失败、迟到结果、人工冲突测试通过 |
| W5 Research 闭环 | 固定版本会话、单 active 回复尝试、检索引用、流式展示、失败保留、关联新版本会话 | W4 | 新构建不影响旧会话证据；引用可定位；新版采用创建新对象 |
| W6 Review 闭环 | 固定版本 Run、大纲与必需章节确认、人工编辑保护、终稿默认接受/显式拒绝、导出、新版综述 | W4；按顺序交付于 W5 后 | 生成/确认/导出链路可验收，拒绝清理不误删其他资产，采用新版保留原成果 |
| W7 自动化与切换验收 | 自动构建授权、调度/邮件、所需审计与诊断、真实服务验收、迁移演练和切换 | 手动闭环稳定，数据方案通过 | 不重复发布/推送，不静默迁移旧研究；恢复与回退验证通过 |
| W8 后续增强 | P1 批量操作/通用重跑等；P2 能力依 FR 单列 | 相应分期启动 | 独立验收，不将未做的增强冒充 P0 阻断 |

每个工作包再拆成模型/用例/API/UI/验收的小增量；每次修改更新进度、版本和证据。通用 P1 重跑的完整实现不前置到 W4，但唯一写者及迟到结果保护必须随 P0 写入路径成立。Research/Review 的 P0 新版本采用不等待 W8。

## 9 必须建立的验收场景

| 编号 | 场景 | 必须结果 |
| --- | --- | --- |
| G01 | 同 Project 同时发起两个构建 | 最多一个获得写资格，另一个明确拒绝或按已定契约处理 |
| G02 | 暂停后进程重启、超时或租约失效 | 不隐式释放暂停构建槽；恢复遵循原实例和基线 |
| G03 | 旧 Worker 在写资格失效后返回 | 不修改新状态、不写入正式资产、不发布版本 |
| G04 | 发布前数据库/文件/向量/图谱关键步骤失败 | 默认已发布版本不变；候选不可冒充正式结果 |
| G05 | 候选基线落后于最新已发布版本 | 拒绝发布，不静默改绑或覆盖较新成果 |
| G06 | 两个 Project 引用同一论文 | 文件、人工分析和权限独立；一方修改不影响另一方 |
| G07 | 构建期间新增人工修改或排除 | 旧候选不能覆盖该决定；冲突可诊断 |
| G08 | 发布新版本后继续旧 Research/Review | 原绑定和证据不变；显式采用新版创建新对象/独立结果 |
| G09 | 恢复 Workspace 或重连前端 | 只恢复上下文和查询状态，不重新提交业务命令 |
| G10 | Agent 再生成已人工确认/编辑内容 | 不静默覆盖；新结果有独立修订和来源 |
| G11 | 同一 Session 并发回复、流中断或失败 | 最多一个 active attempt；用户输入、失败原因和未采纳片段按规则保留 |
| G12 | 管理员诊断、跨 Project ID/文件访问 | 不绕过资产权限，诊断不泄露秘密 |
| G13 | 服务内部 commit 后结束测试 | 测试不污染其他测试或业务数据库 |

G01–G13 按对应能力落地逐步加入集成/故障测试。单元测试数量、HTTP 200、生成文件或页面可打开均不能替代这些验收。

## 10 待明确事项与首个任务

待明确：真实数据保留范围；04+ 最小契约的恢复范围；知识服务选型；任务执行/事件持久化机制；paused 显式重跑旧实例终态及创建失败处理。后者在对应执行契约中收口，不自行规定新业务语义。

推荐首个独立任务为 W0 与 W1 的映射准备：形成 P0 需求到新模块和测试的清单、确认数据分支、记录可复用函数边界。该任务不需要先批量修改代码，也不需要一次完成所有下游设计。实际核心重写从契约已闭合的 W2 开始。

## 11 变更记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.2 | 2026-10-16 | 关联实际提取、候选存档和旧实现删除记录；新核心未开始 |
| v1.1 | 2026-10-16 | 关联独立审查与最终拆分裁决；原候选复用范围下调为限定片段/规则留存，无整模块通过 |
| v1.0 | 2026-10-16 | 建立核心重写、外围复用、旧代码存档、迁移条件、实施工作包与验收计划；未执行代码修改 |
