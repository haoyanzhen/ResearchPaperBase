# 状态机与业务流程设计

> 分层定位：状态机与业务流程层。
> 本文件承载 Run/Session 生命周期、流程式步骤、调度、取消、暂停、恢复、重试、知识库刷新和并发互斥设计。
> 用户可见能力由 `01_functional_requirements.md` 定义；字段、索引和约束以 `06_data_model.sql` 为最终数据契约。

## 1. 设计边界

本文件只定义业务状态、状态转换和横切流程规则，不定义页面布局、按钮文案、API 响应字段或数据库字段。

相关 FR：

- `FR-WORKSPACE-003`：Run/Session 间切换与上下文恢复。
- `FR-WORKSPACE-004`：Run/Session 实例操作。
- `FR-WORKSPACE-005`：Run/Session 状态展示与运行控制。
- `FR-WORKSPACE-006`：流程式 Agent 步骤容器。
- `FR-WORKSPACE-007`：内容修改与版本保护。
- `FR-WORKSPACE-008`：知识库版本刷新提示与不打断规则。

## 2. Project 状态

Project 是长期研究容器，不保存唯一当前 Agent 模式，也不保存全局运行状态。

| 状态 | 含义 | 允许行为 |
| --- | --- | --- |
| `active` | Project 处于活跃研究状态 | 可进入 Workspace、可手动构建、可被系统级 scheduler 扫描 |
| `paused` | Project 暂停自动追踪 | 可进入 Workspace、可查看历史、可手动构建，不参与自动构建调度 |
| `archived` | Project 归档保留 | 默认只读查看历史，不参与自动构建调度 |
| `deleted` | Project 删除态 | 不可进入 Workspace，不参与任何调度 |

Project 状态只表达研究主题是否活跃，不表达某个 Agent 是否正在运行。Agent 运行状态由 Construction Run、Research Session、Review Run 自己维护。

## 3. Agent 实例类型

| 类型 | 生命周期定位 | 写入边界 |
| --- | --- | --- |
| `Construction Workspace` | 每个 Project 唯一的长期构建工作台和配置容器 | 写检索词、检索词级数据源策略、自动更新开关；不写 Knowledge Version |
| `Construction Run` | 构建 Agent 的一次执行记录 | 写论文库、向量库、Graph 和 Knowledge Version |
| `Research Session` | 深度研究 Agent 的开放式对话会话 | 读 Knowledge Version，写对话历史、引用和总结 |
| `Review Run` | 主题综述 Agent 的流程式写作运行 | 读 Knowledge Version，写大纲、章节、审查、导出版本 |

## 4. Run/Session 通用状态

| 状态 | 含义 | 可见控制 |
| --- | --- | --- |
| `draft` | 已创建但未启动，或等待用户补充启动参数 | 编辑、启动、删除 |
| `running` | 正在执行任务 | 暂停、取消；是否允许重试取决于当前步骤 |
| `waiting_user` | 等待用户确认、选择或修改 | 继续、取消、编辑相关输入 |
| `completed` | 已成功完成 | 查看、复制、重跑、导出、归档 |
| `failed` | 失败且需要用户处理 | 查看错误、重试、复制新建、取消 |
| `cancelled` | 用户取消或系统安全中止 | 查看、复制新建、删除 |
| `archived` | 已归档，不再继续执行 | 查看、恢复归档、删除 |

允许的通用转换：

| From | To | 触发 |
| --- | --- | --- |
| `draft` | `running` | 用户启动或系统调度启动 |
| `running` | `waiting_user` | 流程到达人工确认点 |
| `waiting_user` | `running` | 用户确认继续 |
| `running` | `completed` | 当前任务成功完成 |
| `running` | `failed` | 自动重试后仍失败 |
| `running` | `cancelled` | 用户取消或系统安全中止 |
| `failed` | `running` | 用户确认重试 |
| `completed` | `archived` | 用户归档 |
| `cancelled` | `archived` | 用户归档 |
| `archived` | `completed` | 用户恢复归档，仅适用于原 completed 实例 |

删除不是运行状态转换，而是数据保留策略下的资源操作。删除必须由权限、二次确认和保留策略共同约束。

## 5. Construction Workspace 与 Construction Run

每个 Project 有且仅有一个 Construction Workspace。Construction Workspace 保存长期构建配置，不是执行记录，不参与 Run 状态机。

Construction Run 创建来源：

| 来源 | 创建方式 | 检索词来源 |
| --- | --- | --- |
| 手动 | 用户在 Construction Workspace 中选择本次 selected 检索词后启动 | 本次 selected 检索词集合 |
| 自动 | 系统级 scheduler 根据 `FR-013` 创建 | `auto_update_enabled=true` 的检索词集合 |

Construction Run 并发规则：

- 同一 Project 同时只允许一个 active Construction Run 写入知识库。
- 如果已有 active Construction Run，新的手动 Run 应阻止启动并提示当前运行状态。
- 如果已有 active Construction Run，自动调度应跳过或延后，不得创建第二个 active 写入者。
- 不同 Project 的 Construction Run 可以并行，受系统级并发上限控制。

Construction Run 快照规则：

- Run 启动时必须保存检索词内容、检索词来源、检索词级数据源策略、解析后的数据源、用户/系统配置来源和启动方式。
- 历史 Construction Run 可作为日志、结果、失败诊断和复制配置来源。
- 历史 Construction Run 不得作为长期构建配置容器。

## 6. Research Session 状态规则

Research Session 是开放式对话会话，不使用固定步骤容器。

规则：

- 新建 Research Session 默认绑定当前 Project 默认 Knowledge Version。
- 同一 Research Session 内一次只允许一个 active reply stream 追加，避免同一对话轮次顺序冲突。
- 不同 Research Session 可并行运行。
- Construction Run 发布新 Knowledge Version 不会中断 active Research Session。
- 已完成回复不会因 Knowledge Version 刷新而自动改写。

## 7. Review Run 状态规则

Review Run 是流程式写作运行，使用步骤容器展示当前步骤和历史步骤。

典型步骤：

1. 综述主题扩写。
2. 综述大纲生成与确认。
3. 章节撰写。
4. 章节审查与修订。
5. 汇总、终审和导出。

规则：

- 新建 Review Run 默认绑定当前 Project 默认 Knowledge Version。
- 同一 Review Run 内，同一章节或同一最终稿不能被多个任务同时写入。
- 用户手动编辑章节后，后续 Agent 覆盖必须先获得用户确认。
- Review Run 可以中途刷新 Knowledge Version；刷新只影响后续生成，不自动改写既有章节。
- 已完成章节、终审稿和导出产物不会因 Knowledge Version 刷新而自动改写。

## 8. 流程式步骤状态

适用对象：Construction Run 和 Review Run。

| 状态 | 含义 |
| --- | --- |
| `not_started` | 步骤尚未开始 |
| `running` | 步骤正在执行 |
| `waiting_user` | 步骤已产生结果，等待用户确认或修改 |
| `completed` | 步骤已完成 |
| `failed` | 步骤失败 |
| `cancelled` | 步骤被取消 |
| `skipped` | 步骤被规则允许跳过 |

步骤规则：

- 步骤动作必须来自对应 Agent FR。
- 用户确认门槛未满足时，不得进入下一业务步骤。
- 查看历史步骤不得自动重跑或覆盖当前结果。
- 失败步骤是否可重试由对应 Agent FR、当前状态和失败类型共同决定。

## 9. 知识库版本刷新流程

Construction Run 成功后生成新的 Knowledge Version，并更新 Project 默认 Knowledge Version。

刷新规则：

1. active Research Session / Review Run 不被强制切换 Knowledge Version。
2. 新建 Research Session / Review Run 默认绑定最新 Project 默认 Knowledge Version。
3. 依赖旧版本的 active Research Session / Review Run 结束后，系统提示用户知识库依赖可刷新。
4. 用户确认后，系统将非 active Research Session / Review Run 的知识库依赖刷新到最新版本。
5. 已完成的 Research 回复、Review 章节和导出产物不自动改写。

旧版本清理规则：

- 旧 Knowledge Version 只有在没有 active Research Session / Review Run 依赖时才可清理。
- 清理不得破坏已完成文本中的稳定论文引用。
- 具体数据保留和稳定 ID 规则见 `06_data_requirements.md`。

## 10. 内容覆盖保护

内容可分为：

| 类型 | 说明 |
| --- | --- |
| Agent 草稿 | Agent 自动生成但用户尚未确认 |
| 人工确认 | 用户确认接受的 Agent 结果 |
| 人工修改 | 用户主动编辑过的内容 |

覆盖规则：

- Agent 可覆盖自己的未确认草稿。
- Agent 覆盖人工确认或人工修改内容前，必须提示用户确认。
- 失败或取消的重新生成不得破坏原内容。
- 冲突时优先保护人工修改内容。

## 11. 待同步事项

- `06_data_model.sql` 仍需与本文件统一 Project 状态、Run/Session 表和 Knowledge Version 表。
- `07_api_contract.md` 仍需补齐对应的状态转换接口、幂等键和错误码。
- `04_information_architecture_ui.md` 仍需按 `FR-WORKSPACE-001~009` 新顺序更新页面示意图。
