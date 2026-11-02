# Domain 附录：Construction 资产入库

文档版本：v1.10
更新日期：2026-10-30
依据文档：[功能需求](01_functional_requirements.md)、[Domain Core](02_domain_core.md)  
用途：定义 Construction 的检索词、候选论文与资料、去重筛选、手动补充、文本处理和分析确认的业务对象与不变量。本文不定义 UI 布局、API 路径、数据库字段、Provider SDK、队列实现或文件存储实现。

## 1. 设计边界

本附录是 Domain Core 的领域规则组成部分，与主文共同受 FR 约束，沿用主文的对象分类、权限、生命周期和内容保护规则。

知识库版本、构建输入冻结、待纳入修订、入库预览确认、完整发布和图谱维护由 [02-02 知识库版本附录](02-02_construction_versioning_appendix.md) 定义；本文承接其输入与发布接口，不另设版本规则。断点续连与临时产物清理由 [02-04 运行恢复附录](02-04_run_recovery_appendix.md) 定义。命令校验和流程编排由后续 `05_application_use_cases.md` 细化，不得反向改变领域规则。

## 2. 领域主链路

论文进入 Project 知识库的领域主链路：

```text
CandidatePaper
 -> DeduplicationDecision
 -> PaperIdentity
 -> ProjectPaper
 -> DocumentAsset / DocumentProcessingState
 -> PaperAnalysis
 -> KnowledgeSyncState
 -> KnowledgeVersion
 -> CitationEvidence
```

非论文 Project 资料进入 Project 知识库的领域主链路：

```text
CandidateMaterial
 -> MaterialDeduplicationDecision
 -> MaterialScreeningDecision
 -> ProjectMaterial
 -> DocumentAsset / MaterialProcessingState
 -> MaterialAnalysis
 -> KnowledgeSyncState
 -> KnowledgeVersion
 -> CitationEvidence
```

KnowledgeSyncState、KnowledgeVersion 和 CitationEvidence 为 [02-02](02-02_construction_versioning_appendix.md) 提供的同步、发布与证据接口。

## 3. 核心对象

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `SearchTermSet` | Project 检索词集合 | 属于 ConstructionWorkspace；用于手动 selected 构建和自动更新；每条检索词应能够单独管理，包括编辑、删除、是否参与自动更新等 | FR-020 |
| `SearchTermVersion` | ConstructionWorkspace 内的检索词内容快照 | 保存自然语言关键词、布尔表达式、同义词/缩写、排除词、生成理由、预期覆盖方向、确认时间、修改来源、自动更新开关和数据源策略；新生成或新增检索词默认 `auto_update_enabled=true` | FR-020 |
| `SelectedSearchTerms` | 单次手动 ConstructionRun 本次选择的检索词集合 | 不改变检索词自身的自动更新开关 | FR-014, FR-021 |
| `AutoUpdateSearchTerms` | 自动 Run 使用的检索词集合 | 只包含 `auto_update_enabled=true` 的检索词 | FR-009, FR-021 |
| `DataSourcePolicy` | 检索词级数据源策略 | 按FR-007逐Provider个人优先解析，未显式选择时使用解析后的全部可用数据源 | FR-020, FR-021 |
| `ConstructionRunConfigSnapshot` | ConstructionRun 启动配置快照 | 固化本次检索词内容、检索词来源、数据源策略、解析后数据源、配置来源、检索时间范围、返回数量上限和触发方式 | FR-009, FR-014, FR-021 |
| `CandidatePaper` | 检索得到的候选论文 | 必须记录来源检索词、来源数据源和基础元数据；论文元数据保持严格结构 | FR-021, FR-022 |
| `CandidateMaterial` | 检索得到的候选非论文 Project 资料 | 必须记录来源检索词、来源数据源或资料来源、标题或待补充标题状态、`content_format`、URL/文件线索和最小可追溯信息 | FR-021, FR-022 |
| `DeduplicationDecision` | 候选论文身份归一化决策 | 记录候选论文与 PaperIdentity 或既有 ProjectPaper 的匹配依据、冲突、操作者/Agent 来源、误合并撤销状态 | FR-022 |
| `MaterialDeduplicationDecision` | 候选资料 Project 内去重决策 | 记录候选资料与既有 ProjectMaterial 的标题、`content_format_group`、相似度、重复/疑似重复判断、`candidate_sources` 写入结果、操作者/Agent 来源和误合并撤销状态 | FR-022 |
| `PaperScreeningDecision` | 论文评分与筛选决策 | 记录评分、有效性、评分阈值来源、人工调整、确认状态和可追溯理由；确认前不得进入下载解析 | FR-022 |
| `MaterialScreeningDecision` | 资料评分与筛选决策 | 记录评分、有效性、评分阈值来源、人工调整、确认状态和可追溯理由；确认前不得进入文件获取解析 | FR-022 |
| `ManualPaperSupplementRequest` | 用户手动补充论文请求 | 记录补充方式、提交人、来源值、解析结果、确认状态和失败原因；不得在用户确认前写入 ProjectPaper | FR-023 |
| `ManualMaterialSupplementRequest` | 用户手动补充 Project 资料请求 | 记录补充方式、提交人、来源值、`content_format`、解析结果、标题草稿/确认状态和失败原因；不得在用户确认前写入 ProjectMaterial | FR-023 |
| `PaperIdentity` | 全局论文身份 | 按D-CW-03以去标点、小写的非空标题自动归一化，外部标识保留为来源依据；跨 Project 共享身份，不共享私有资产 | FR-022, FR-023 |
| `ExternalPaperIdentifier` | DOI、arXiv ID、URL 等外部标识 | 必须归一化类型和值，并记录解析来源；解析到多个候选或关键元数据冲突时必须要求用户确认 | FR-023 |
| `ProjectPaper` | Project 私有论文关联 | 同一 Project 当前版本不得有同一论文的重复活动关联；移除后新导入保留历史成员；保存有效性、评分、推送状态和分析结果 | FR-012, FR-022, FR-026 |
| `ProjectMaterial` | Project 私有非论文资料条目 | 同一 Project 内按 `normalized_title + content_format_group` 去重；保存项目资料库编号、标题、`content_format`、主来源、`candidate_sources`、有效性、推送状态和重要摘要 | FR-012, FR-022, FR-026 |
| `ContentFormat` | Project 资料文件或内容格式 | 表达资料文件类型和相似格式组；P0 支持文档、演示、HTML、Markdown/纯文本、类字典、Notebook 和代码文件；P1 数据表和 P2 多媒体的版本纳入资格承接 [02-02](02-02_construction_versioning_appendix.md) | FR-021, FR-023, FR-024 |
| `DocumentAsset` | PDF、远程文件、Project 资料文件或解析文本资产 | 记录访问引用、资产来源、解析状态、失败原因、摘要降级或不参与知识构建标记；用户上传资产必须绑定提交人和 Project 授权边界 | FR-012, FR-023, FR-024 |
| `DocumentProcessingState` | 论文全文获取和可用文本来源状态 | 记录下载、解析、用户上传替代、重试后的最终可用文本来源；全文解析与摘要降级必须可区分 | FR-024 |
| `MaterialProcessingState` | Project 资料文件获取和文本可用状态 | 记录下载/上传、解析、格式支持、可用文本来源、不参与 KnowledgeVersion、失败原因和重试结果 | FR-024 |
| `PaperAnalysis` | Project 私有论文结构化 AI 分析 | 绑定 ProjectPaper、TextSourceKind 和 DocumentProcessingState；至少包含一句话总结、亮点、相关性要点、方法与创新；仅未入库锁定的候选可被人工编辑和确认，发布后只读 | FR-025 |
| `MaterialAnalysis` | Project 私有资料轻量 AI 分析 | 绑定 ProjectMaterial、TextSourceKind 和 MaterialProcessingState；至少包含重要信息摘要和 Project 相关性要点；Agent 生成标题、来源或摘要必须可区分草稿/确认状态；与论文分析同样在入库确认受理后锁定 | FR-025 |

## 4. 检索与候选处理

常规检索与纯补充/纯修订模式、同 Run 返回检索的显式输入修订，统一遵循 [02-02 第 3.2 节](02-02_construction_versioning_appendix.md#32-同-run-返回检索与纯修订构建)。无检索模式不伪造检索/评分结果；各项按实际依赖处理，相关人工确认仍保留。关联移除、空版本消费、入库确认后锁定与删除后新导入统一按 02-02 第 3.3 节执行；论文与 ProjectMaterial 均适用。

Construction 不变量：

- 手动 ConstructionRun 使用用户本次 selected 检索词集合；自动 ConstructionRun 使用 AutoUpdateSearchTerms，即当前由用户维护配置后仍满足 `auto_update_enabled=true` 的检索词集合。
- 历史 ConstructionRun 必须能基于 ConstructionRunConfigSnapshot 复现当时的检索词内容、数据源策略和启动参数，即使当前检索词已被修改或删除。
- 检索词未确认时，手动构建不得进入多源检索阶段。
- 检索词生成失败时，用户手动输入并确认的检索词应形成同等可追溯的 SearchTermVersion。
- 新生成或新增的 SearchTermVersion 默认参与系统自动更新；用户编辑检索词、调整数据源策略或关闭自动更新，均是在 `auto_update_enabled=true` 默认态基础上修改。
- 不存在独立的检索词 `enabled` 领域状态；手动构建是否使用某个检索词只由本次 SelectedSearchTerms 决定，自动构建是否使用只由 `auto_update_enabled` 决定。
- 删除检索词只影响之后按检索词检索时的可选集合和自动更新集合；不得删除历史 Run、候选论文、候选资料、ProjectPaper、ProjectMaterial、KnowledgeVersion、图谱、向量或其他已生成内容；历史回溯只能读取当时的 ConstructionRunConfigSnapshot。
- 所有实际数据源均失败或不可解析时，不得进入去重、评分与筛选阶段。
- 单个数据源失败不得破坏其他成功数据源结果；失败数据源、失败原因和受影响检索词必须可诊断。
- D-CW-01 A（2026-10-27）：Construction检索构建的身份、Project资格及所需LLM等全局必需配置失败时拒绝整个Run；数据源按检索词解析。all_resolvable使用可用来源并记录拒绝项；selected中任一显式来源失效则整条词失败，不执行该词的其他来源，但不阻断其他可执行词。至少一条词有可执行来源才受理，全部不可执行则拒绝启动。显式失效来源不替换，个人禁用不回落。取得独占构建资格后、冻结并派发前重新校验；此时全部不可执行则终止且不外发。失败项与原因必须可见并随本轮输入依据保存，不以部分执行冒充完整范围。
- 普通检索命中当前 Project 已有关联论文的重复候选项不得进入下载、解析、AI 分析、入库、图谱更新或推送流程；已发布论文不再接受补全文本、元数据或分析修订，更改须移除成功后重新导入；人工排除承接 [02-02](02-02_construction_versioning_appendix.md) 的待纳入修订与人工决定接口。
- 2026-10-30用户澄清：其他Project对同标题论文的人工区分不改变当前Project的新候选展示或入库流程，不显示特殊提示；当前Project无关联时正常建立关联。全局身份无法唯一确定时内部保持未确定，不合并或改写其他Project身份、人工决定和私有资产；当前Project已有关联和历史重导仍按自身规则去重与沿用身份。
- 命中当前 Project 已有 ProjectMaterial 的候选资料不得创建新资料条目；重复来源仅记录为独立候选来源线索，不改变已发布资料元数据或版本内 `candidate_sources`；`candidate_sources` 的知识构建资格承接 [02-02](02-02_construction_versioning_appendix.md)。
- 论文去重、评分、筛选和人工修正必须形成 DeduplicationDecision 或 PaperScreeningDecision；评分阈值来源、去重依据、人工调整和误合并撤销必须可追溯到 ConstructionRun、候选论文和操作者。
- Project 资料去重、评分、筛选和人工修正必须形成 MaterialDeduplicationDecision 或 MaterialScreeningDecision；标题归一化、`content_format_group`、人工调整和误合并撤销必须可追溯到 ConstructionRun、候选资料和操作者。
- 用户确认筛选结果后，候选论文和候选资料才能进入下载解析流程。
- 自动评分按FR-022 D-CW-02 A：0–10综合分、系统默认阈值7、score≥7初判有效；记录三方面理由、尺度、阈值来源和模型依据。评分失败保持未判定，不写伪0分；人工修改/确认不能被重新评分静默覆盖。

## 5. 手动补充与资产边界

具体网页/文件地址与数据源配置的检索服务入口分离；接收资源地址不自动创建数据源配置，下载及后续资产仍遵循Project隔离与原确认流程。检索候选中的具体资源地址由Provider结果提供，不以配置base_url代替。


Construction 不变量：

- 手动补充论文必须形成 ManualPaperSupplementRequest；补充方式至少区分 PDF 上传、DOI、arXiv ID 和 URL，且必须绑定提交用户、目标 Project 和提交时间。
- DOI、arXiv ID 或 URL 补充必须先归一化为 ExternalPaperIdentifier，再解析为 CandidatePaper 或 PaperIdentity；解析失败、解析到多个候选或关键元数据冲突时，不得自动入库，必须等待用户确认或修正。
- PDF-only 上传必须先从 PDF 本身提取候选元数据；关键元数据不足时必须要求用户补充或确认 LLM 元数据草稿，LLM 草稿不得直接成为用户已确认元数据。
- 非论文资料只要求轻量元数据，包括项目资料库编号、标题、`normalized_title`、`content_format`、主来源、`candidate_sources`、重要摘要、处理状态和来源 ConstructionRun；不得要求作者、时间、语言或 provider 必填。
- 非论文资料不维护业务类型字段；文件类型只由 `content_format` 表达。
- ProjectMaterial 的 `normalized_title` 至少执行去首尾空格、大小写归一、连续空白合并和常见文件扩展名移除。
- 同一 Project 内，当非论文资料标题相同或相似，且 `content_format` 相同或属于相似格式组时，必须视为重复或疑似重复，不得静默创建重复 ProjectMaterial。
- 非论文资料标题缺失时不得自动确认入库；用户可补充标题，或由 Agent 生成待确认标题草稿。
- P0 Project 资料支持 `pdf`、`doc/docx`、`ppt/pptx`、`html/htm`、`md/txt/rst`、`yaml/yml/json/toml`、`ipynb` 和 `py` 等代码文件参与后续解析和分析；版本纳入资格承接 [02-02](02-02_construction_versioning_appendix.md)。
- P1 数据表资料可入库和使用；P2 多媒体资料可作为文件资产管理，解析能力后续扩展；两者的知识构建资格承接 [02-02](02-02_construction_versioning_appendix.md)。
- 用户上传 PDF、Project 资料文件或远程文件形成的 DocumentAsset 只能服务于其有 `use` 权限的 Project；不得因为同一 PaperIdentity 或相似资料跨 Project 出现而自动暴露上传文件给其他 Project 或用户。
- 手动补充命中当前 Project 已有关联论文时，提示先移除关联后重新导入，不得作为补充资产或内容修订绕过只读边界，不得创建重复活动 ProjectPaper。
- 手动补充命中当前 Project 已有 ProjectMaterial 时，提示先移除关联后重新导入，不得作为元数据修订或文件替换绕过只读边界；独立备选来源线索不写入已发布内容，不得创建重复活动 ProjectMaterial。

## 6. 文本处理与分析确认

候选在入库确认受理前允许修改元数据、文件/文本、分析和评分/有效性，须失效并重做受影响处理与确认；活动处理与编辑不得竞争。确认受理后至隔离写入、发布期间锁定内容；已发布资产修改须移除成功后新导入。独立运行投影不在内容锁定范围。手工重新导入可复用身份和不可变字节，但不得沿用旧人工确认或把旧分析冒充新内容分析。

Construction 不变量：

- PDF 下载、文本解析、用户上传替代和重试结果必须收敛为一个可追溯的 DocumentProcessingState；后续 AI 分析、向量化、RAG 和综述引用只能读取其标记的最终可用文本来源。
- Project 资料文件获取、文本解析、格式支持、不参与 KnowledgeVersion 和重试结果必须收敛为一个可追溯的 MaterialProcessingState；后续 AI 分析、向量化、RAG 和综述引用只能读取其标记的最终可用文本来源。
- 摘要降级文本可进入后续分析、向量化或 RAG，但必须标记为摘要降级来源，不能冒充全文解析。
- D-CW-04 B（2026-10-29用户决定）：同论文组按固定且可追溯的来源顺序选择首个可用全文；全部全文不可用时选择一份真实摘要降级，不融合不同原文。处理确认展示实际所用来源及其他来源，用户确认后才能进入分析；不将首成功来源称为权威或最新版本。
- 下载解析阶段完成后，手动 ConstructionRun 必须由用户确认 DocumentProcessingState/MaterialProcessingState 摘要、失败项、摘要降级项和不参与知识构建项，才能进入 AI 分析阶段；自动 ConstructionRun 可由 AutoConfirmationPolicy 处理低风险确认，或对单项执行跳过、摘要降级和局部失败。
- 手动 ConstructionRun 中，用户确认后的 PaperAnalysis 才能进入候选入库流程；自动 ConstructionRun 中，AutoConfirmationPolicy 确认后的 PaperAnalysis 可进入后续流程；正式研究读取承接 [02-02](02-02_construction_versioning_appendix.md) 的发布接口。
- 手动 ConstructionRun 中，用户确认后的 MaterialAnalysis 才能进入候选入库流程；自动 ConstructionRun 中，AutoConfirmationPolicy 确认后的 MaterialAnalysis 可进入后续流程；正式研究读取承接 [02-02](02-02_construction_versioning_appendix.md) 的发布接口。

入库预览的展示范围、确认门槛、自动低风险处理和高风险失败裁决，统一承接 [02-02](02-02_construction_versioning_appendix.md) 的确认与发布接口。

## 7. FR 覆盖检查

| FR 范围 | Domain 覆盖点 |
| --- | --- |
| FR-009, FR-014, FR-020~021 | 检索词集合、自动更新集合、数据源策略、启动配置快照和候选来源追溯 |
| FR-022~023 | 论文与资料去重筛选、手动补充、身份归一化、轻量元数据和 Project 私有资产边界 |
| FR-012, FR-024~026 | 文件处理状态、最终文本来源、摘要降级、分析确认和版本发布接口 |

## 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
| --- | --- | --- | --- |
| v1.0 | 2026-10-16 | 从 Domain Core 迁移 Construction 资产入库对象与不变量；版本规则和恢复规则分别承接 02-02、02-04 | Codex |

本次修订 v1.1（2026-10-16）：关联已批准的构建模式和输入修订边界，避免另设发布规则。

本次修订 v1.2（2026-10-16）：落实人工采纳 R1–R4 及补充决定：学术引用与简化终稿、关联移除发布、空版本消费、确认后锁定及论文/资料重新导入边界；仅设计同步。

## A08 类型映射索引

本附录的业务状态及不变量不变。[06 A08](06_agent_knowledge_services.md#a08-补充处理与分析具名服务载荷)具名化补充准备、论文/资料处理和分析提案；[04-01 A08](04-01_p0_operation_contracts.md#a08-补充详情与处理依据投影)定义读取依据。元数据解析、内容处理、人工确认、候选纳入和成功发布是独立事实；补充可无Run，静态结果可复用但确认不继承。输入/文件/最终文本/处理/分析修订必须可追溯，解析器不决定业务确认。工程映射不改变人工保护、P0格式、两个写范围或既有恢复分期。


本次修订（2026-10-26）：按用户决定分离数据源检索服务入口与具体资源地址；本次决定不涉及通用抓站支持及范围，具体文件地址不作为配置入口。

本次修订（2026-10-26）：按task032 D-SOURCE-02用户选择B同步逐Provider优先/回落及显式身份保护；个人可分别配置四个论文源API。

本次修订（2026-10-28，D-CW-03）：用户明确“只以去标点符号、全小写的标题来判断是否是同一论文身份”。自动标题键删除Unicode P类标点后调用lower，不增加模糊匹配、空白合并或字符兼容转换；保留数学符号，空/纯空白结果不自动匹配。人工修正优先、原始元数据和全部来源保留；身份合并不修改已发布内容或跨Project私有资产。该规则替代旧强标识优先自动去重要求。
