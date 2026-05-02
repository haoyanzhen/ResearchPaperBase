# Task 017: Add UploadedDocument model

你是本项目的开发助手。请严格遵守以下约束。

## Goal
按照以下任务，依次执行，并在执行完毕后生成执行报告：
1. 对 docs/design/02_product_requirements.md 中的结构进行审查和更新
2. 维护变更记录
3. 根据每一条FR的功能设计，重新审查其验收设计，保证验收设计能够在保持最小必要的情况下完整覆盖功能设计。
4. 以设计者的角度给出全量审计报告，包含每个模块的设计完整性，潜在/可能冲突；每一条FR的设计必要性、完整性、边界清晰性和实现复杂度。
5. 对每一条潜在冲突给出对应的解决建议。
6. 以使用者的角度给出检查报告，先根据该项目的总体设计给出一版整体需求，再对每个FR进行审查，判断是否覆盖自己的需求边界。
7. 整理使用者需求并汇总，给出新的或未被满足的需求列表并给出实现建议。
8. 总结所有审计结果，给出需要人工决策的列表。

## In Scope
- 读写 docs/design/01_functional_requirements.md

## Out of Scope
- 读其他文件

## Additional Order
1. 只完成当前任务，不要扩展范围。
2. 不要新增未批准的依赖。
3. 不要修改认证、数据库连接、全局配置，除非任务明确要求。
4. 如果发现任务需要超出范围的修改，先停止并说明。
5. 所有新增业务逻辑必须有测试。
6. 所有 API 修改必须符合 api_contracts.md。
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

### Tests(if meaningful codes are changed)
- Commands run and results

### Risks / Notes
- Remaining concerns

### Human Review Checklist
- Specific things the human should inspect
