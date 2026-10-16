# Task <编号>: <任务名称>

文档版本：v1.0

更新日期：2026-10-16

你是本项目的开发助手。请遵守根目录 AGENTS.md，并在使用本模板时填写以下任务范围与验收条件。占位内容不构成执行授权。

## Goal
<描述本次任务要解决的问题及预期结果。>

## In Scope
- <明确本次已授权的实现或文档范围。>

## Out of Scope
- <明确不包含和继续延期的事项。>

## Acceptance Criteria
- <可观察、可验证的验收条件。>
- <相关检查方式；代码任务填写适用的测试，文档任务填写引用、版本和一致性检查。>

## Must read
- [AGENTS.md](../AGENTS.md)
- [项目进度](../docs/PROJECT_STATUS.md)
- [设计索引](../docs/design/README.md)
- <补充本任务实际相关且存在的文件；核对其适用状态。>

## Initial State Check

- 检查 Git 工作区及任务相关文件，将文档中的完成声明与实际文件、执行证据核对。
- 分开识别计划、已执行与已验证；矛盾标记为“待核验”，不得为了符合文档而擅自删除或恢复文件。
- 只暂停依赖矛盾结论的操作，继续不受影响的工作。

## Human Decisions

- 已授权范围内的局部实现、修复、测试及必要文档同步自主完成，不重复请求确认。
- 改变业务语义、权限边界、人工内容保护、知识版本绑定或产品分期，需要明确的人工决策；已有授权不重复询问。
- 延期事项或待办登记不等于执行授权。需要决策时说明：待决问题、证据、方案及影响、推荐方案、受阻工作。

## Verification

- 新增或修改业务行为须有相应自动化验证；缺陷修复应增加能复现问题的回归测试。
- 数据库测试显式使用隔离测试环境，不回退业务数据库配置；核验服务内部提交后的数据隔离与清理。
- 默认模拟 LLM、论文源和邮件服务；真实集成验证须明确测试目标、外部副作用及适用授权。
- Mock、健康检查和存档片段测试不能替代端到端验收。
- 记录实际执行的命令及结果；无法执行时记录原因、未验证范围和后续命令，不标记验收通过。
- 纯文档修改检查引用、版本和一致性，无需运行无关应用测试。新工程入口建立后记录经验证的安装、测试与构建命令，不照搬旧命令。

## Document Versions

- 设计文档保持 `v1.x`；修改带版本声明的自有文档时递增该文档次版本并更新日期，无版本文档首次标注为 `v1.0`。
- 源码通过 Git 追踪，不要求逐文件添加版本号；依赖版本、锁文件格式和迁移编号遵循各自规则，不为匹配项目版本而改写。

## Additional Order
1. 只完成当前任务，不要扩展范围。
2. 不要新增未批准的依赖。
3. 不要修改认证、数据库连接、全局配置，除非任务明确要求。
4. 如果发现任务需要超出范围的修改，先说明并暂停依赖该决策的部分，继续已授权且不受影响的工作。
5. 按本模板 Verification 和 AGENTS.md 执行验证。
6. API 修改遵循本任务适用的契约；不得沿用失效路径或未经核对的旧接口。
7. 所有数据库修改必须有 migration。
8. 完成后输出审查报告。

## Output format
1. 当前任务要解决什么问题
2. 涉及哪些 Web 开发概念
3. 本项目采用的设计选择
4. 替代方案有哪些
5. 为什么暂时不选替代方案
6. 具体代码修改
7. 如何验证 & 测试
8. 有哪些风险或限制
9. 有哪些知识点（在 web app 方面）

## Final Response Format

Use this format after completing a task:

### Summary
- What changed

### Verification
- Commands or document checks run and actual results
- If not run: reason, unverified scope, and follow-up commands; do not claim acceptance passed

### Risks / Notes
- Remaining concerns

### Human Review Checklist
- Specific things the human should inspect
