# Domain 附录：Run / Session 恢复与清理

文档版本：v1.0  
更新日期：2026-10-16  
依据文档：[功能需求](01_functional_requirements.md)、[Domain Core](02_domain_core.md)  
用途：定义重试、重连、重跑、Construction 断点和 Research 回复恢复的业务对象、不变量及临时产物清理边界。本文不定义 UI 布局、API 路径、数据库字段、Provider SDK、队列实现或文件存储实现。

## 1. 设计边界

本附录是 Domain Core 的领域规则组成部分，与主文共同受 FR 约束，沿用主文的通用状态、权限、内容保护和非构建互斥规则。

构建槽、写资格终止与安全交接、版本发布、基线校验和版本采用统一承接 [02-02 知识库版本附录](02-02_construction_versioning_appendix.md)。本文的失败超时清理不得代替该附录要求的暂停运行显式取消或重跑决策。资产处理输入与确认承接 [02-03 Construction 资产入库附录](02-03_construction_assets_appendix.md)。具体自动重试次数、等待窗口和后台清理编排由后续 `05_application_use_cases.md` 定义，不得反向改变领域规则。

## 2. 核心对象

| 对象 | 定位 | 核心规则 | 关联 FR |
| --- | --- | --- | --- |
| `ConstructionCheckpoint` | 构建断点续连状态 | 记录 ConstructionRun 子内容写入进度、重试次数、失败原因、可续连位置、中间临时文件引用、清理状态和用户继续/停止决策；不得替代错误日志 | FR-015, FR-026 |
| `ResearchResponseAttempt` | ResearchSession 内的一次 AI 回复尝试 | 记录 running/succeeded/failed/cancelled 等结果、诊断原因、部分回复、是否被用户采纳和所属 ResearchTurn；每个 AI 回复可重跑并生成新 attempt | FR-028 |

## 3. 重试、重连与重跑

通用重试、重连和重跑为 P1 受控能力（FR-018 版本采用专用创建为 P0，见 [02-02](02-02_construction_versioning_appendix.md)）。

| 操作 | 优先级 | 领域含义 | 领域约束 |
| --- | --- | --- | --- |
| `retry` / 重试 | P1 | 对同一后端运行单元重新尝试执行一次 | 必须记录新的 attempt、失败原因、重试次数和结果；不得覆盖原失败诊断 |
| `reconnect` / 重连 | P1 | 基于断点从未完成位置继续执行 | 必须依赖完整状态记录、可续连位置、中间临时文件引用和一致性校验；断点不可信时不得继续 |
| `rerun` / 通用重跑 | P1 | 按原实例的原始输入、配置和数据版本从头开始运行 | 必须保留原实例；新运行不得复用原未完成中间写入作为成功结果 |

FR-018 的 P0 版本采用操作、与 P1 通用重跑的区别及基线失配裁决，统一承接 [02-02](02-02_construction_versioning_appendix.md) 的版本采用和发布接口。

重连不变量：

- 可重连对象必须记录运行阶段、子任务状态、已提交正式数据、未提交临时数据、临时文件引用、断点位置、失败原因、重试次数、操作者决策和清理状态。
- 重连前必须校验断点、正式数据和中间临时文件仍然一致；临时文件缺失、损坏、越权、过期或与状态记录不匹配时，不得继续重连，只能失败、重试或重跑。
- 重连只能从已成功写入且状态一致的位置之后继续；不得重复写入已成功子内容，也不得跳过未完成子内容。
- 重连完成并生成正式数据后，系统必须清理已完成链路不再需要的临时文件，并保留清理结果；清理失败不得把临时文件冒充为正式资产。
- 取消、失败超时或用户选择不继续时，未发布中间写入和可续连临时文件必须按运行类型进入清理流程；清理不得破坏已发布 KnowledgeVersion、已确认内容或其他 Run/Session 资产。

## 4. Construction 断点与清理

关联 FR：FR-015、FR-026。

Construction 恢复不变量：

- ConstructionRun 失败后的发布限制承接 [02-02](02-02_construction_versioning_appendix.md)；手动失败 Run 的未发布中间写入只能用于断点续连，用户取消或超时未处理后必须清理，并保持当前已发布 KnowledgeVersion 边界，不回滚其他成果；自动 ConstructionRun 不得进入等待用户处理状态，达到应用层失败清理条件后必须直接清理未发布中间写入和临时文件。
- 用户选择重连继续构建时，新的 ConstructionRun attempt 必须基于 ConstructionCheckpoint 从已成功写入且状态一致的位置断点续连；不得重复写入已成功子内容或跳过未完成子内容。
- ConstructionCheckpoint 必须记录正式写入进度、未发布中间写入、中间临时文件引用、可续连位置、失败原因、重试次数和清理状态；断点或临时文件不一致时不得重连。
- 手动 ConstructionRun 中，用户选择不继续构建、取消失败 Run，或超过应用层定义的等待窗口仍无操作时，系统应删除所有可续连 ConstructionCheckpoint、失败 Run 的未发布中间写入和不再需要的中间临时文件，保持当前已发布知识状态；不得回滚其他已完成成果或清除独立保存的待纳入修订；系统只保留失败记录、错误日志和历史 Run 诊断。自动 ConstructionRun 达到应用层失败清理条件时必须执行同等清理，不等待用户操作。
- ConstructionRun 重连成功并发布新的 KnowledgeVersion 后，必须将临时文件收敛为正式 DocumentAsset、ProjectMaterial、向量、Graph 或日志诊断引用，随后清理不再需要的临时文件；清理结果必须可诊断。

## 5. Research 回复恢复

关联 FR：FR-028、FR-030。

Research 恢复不变量：

- 流式回复中断、用户取消、检索失败或 LLM 失败时，ResearchTurn、用户输入、失败状态和可诊断原因必须保留；部分 AI 回复只能作为未采纳的 ResearchResponseAttempt 保存，由用户决定编辑、采纳、删除或重跑。
- 同一 ResearchSession 一次只能有一个 active ResearchResponseAttempt；同一 AI 回复重跑必须生成新的 ResearchResponseAttempt，不得覆盖原 attempt 的诊断状态。
- ResearchResponseAttempt 的重连必须基于流式回复游标、已保存部分回复、检索上下文、模型配置快照和临时输出状态；断点不可信时不得把部分回复保存为成功回复。
- ResearchResponseAttempt 完成后，未被采纳且不再需要的临时流式片段应进入清理流程；已采纳回复和诊断记录不得被清理流程破坏。

## 6. FR 覆盖检查

| FR 范围 | Domain 覆盖点 |
| --- | --- |
| FR-015 | P1 重试、重连、通用重跑语义、断点一致性、临时产物清理与原实例保护 |
| FR-018 | 版本采用和基线校验接口，规则由 02-02 定义 |
| FR-026 | ConstructionCheckpoint、断点续连、失败清理和成功后的临时文件收敛 |
| FR-028, FR-030 | ResearchResponseAttempt、失败轮次保留、回复重跑、流式断点和临时片段清理 |

## 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
| --- | --- | --- | --- |
| v1.0 | 2026-10-16 | 从 Domain Core 迁移通用重试/重连/重跑、Construction 断点清理和 Research 回复恢复规则；版本与构建写资格承接 02-02 | Codex |
