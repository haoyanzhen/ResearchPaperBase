# Task 017: Add UploadedDocument model

你是本项目的开发助手。请严格遵守以下约束。

## Goal
添加 UploadedDocument 数据模型，用于记录用户上传的文档元数据。

## In Scope
- 新增 SQLAlchemy model
- 新增 Alembic migration
- 新增基础 repository 方法
- 新增测试

## Out of Scope
- 不实现文件上传 API
- 不实现前端页面
- 不接入向量数据库
- 不做文档解析
- 不改认证逻辑

## Acceptance Criteria
- migration 可以正常执行
- UploadedDocument 与 User 正确关联
- 测试覆盖创建和查询
- 不新增第三方依赖

## Must read
- docs/architecture.md
- docs/tech_constraints.md
- docs/api_contracts.md
- docs/database_schema.md
- docs/coding_rules.md

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
