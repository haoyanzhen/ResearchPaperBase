# 项目首页的已发布知识版本

文档版本：v1.2
更新日期：2026-11-05

## 8. 最新检查点
S7，项目默认版本读视图与首次发布状态刷新已工程收口。独立审查发现的跨标签页删除问题已修复并复验。按用户“先对已实现的内容按照设计进行修改”处理 Project 列表、详情及首页的默认版本显示。

## 1. 授权与范围
落实 FR-008、FR-012、FR-018 已有生产端到 Project 读视图的衔接。研究、综述运行按下一阶段计划交付。
## 2. 基线
手动论文发布已有真实 heads 指针；Project 视图硬编码 null。首页只展示是否已有版本。
## 3. 落点
项目事务查询、首页已发布状态与已有构建回归用例。
## 4. 验收规格

列表与详情按所属项目投影当前默认值；首次发布前为空、首次及增量发布后为实际版本、无变化核验后保留原版。旧版仍能按 ID 打开。页面打开期间首次发布后，自动更新知识状态并保留用户输入。覆盖权限、隔离及既有维护返回路径。

| 需求 | 可执行场景 |
| --- | --- |
| 首次发布、已有页无感更新 | test_browser_analysis 的 PAB01：已打开项目自动由无版本变为已有版本，未保存项目名称及输入焦点保留。 |
| 不同项目与增量 | PAB01 查同用户另一空项目仍为 null；test_incremental_publication 验证 V1 详情、V2 详情/列表及原 V1 论文。test_project_list 覆盖他人/已删除项目不可见、分页及只读。 |
| no_change 和维护 | test_no_change_completion 的 success 分支验证无变化保留 V1，后续发布新版本并编辑、归档时返回真实指针。 |
| 已打开页面跨标签删除 | test_head_poll_clears_unavailable_project_and_form：另一标签页删除后，原页退出旧 URL，清空创建表单。 |
## 5. 验证
根目录执行 delivery_context.py read 状态 §2、设计索引 §1，entry 本单，再按 root 账本读取 DELIVERY_TOOLS §5、IMPLEMENTATION_ENTRY 工程阶段。入场受影响文件摘要见 baseline.sha256。每批实际命令及退出码在证据目录的 run.json；JUnit 用 delivery_summary.py 汇总，普通输出使用 --log。
- 原临时 PG17 缺少 postgres.bki，首轮环境失败后新建独立临时安装，复用本地 PG17 与 pgvector 0.8.1、临时 socket/专用库/最小权限角色。red2 在真实首次发布后复现 null；api1 的 164 项受影响集成通过，unit 的 559 项后端单元通过。
- 首轮前端类型收窄、断言定位及格式问题分别见 build、focused 和 static；修复后 build_final、focused2、types、lint_final 与 ui_final 通过。browser1 的 5 项浏览器用例与后续批次存在重叠，不能合并计数。
- S3 发现新轮询遇 404 时仍留旧项目 URL 与创建草稿。red_deleted2 在旧前端构建复现；修正为同一离开不可用项目的清理入口。前置探针 red_deleted 因浏览器测试上下文错误未触发此断言。
- S4 逐项复核第 4 节，补充了编辑/归档返回值与删除负例。S5 复用统一项目投影、既有不可用退出流程。研究/综述的 FR-018 操作与自动提示由其后续切片单独验收。
## 6. 决策与里程碑
沿用已确认发布和权限规则。本切片为已有 Project 展示修复，验收场景见第 4 节。
## 7. 交接
最终受影响专项 14 项通过，独立复验 8 项通过，隔离 PG 实例均已停止、删除。API 范围、专项及独立批次有重叠。此次是现有界面的工程修复，未声明新的研究或综述里程碑已获人工验收。详见[最终专项](../docs/workorders/evidence/task050_project_knowledge_head/final/summary.json)、[独立复验](../docs/workorders/evidence/task050_project_knowledge_head/review/final-summary.json)。研究提问及综述生成、审查的后续规格见[任务拆解 §10.10](../docs/workorders/preimplementation_design_tasks_2026-10-21.md#1010-fr-018-操作受理与历史证据交接2026-11-05)。实施证据在 [task050 目录](../docs/workorders/evidence/task050_project_knowledge_head/)。

## 9. 人工接受与 Git 交接
2026-11-05 用户明确“ok，通过审核，先提交一次git”，接受本切片并授权本地提交。6 个业务代码/测试文件逐字节匹配最终 source 快照；复用最终专项 14 项及独立复验 8 项证据，不重跑未变业务测试。本次仅提交本切片代码、测试、任务记录、状态行及文本验证证据；其他设计/协议/工具和维护改动保留。当前 HEAD 与范围清单、索引核验保存在 evidence/task050_project_knowledge_head/commit。实际读取调用：delivery_context.py entry 本单；read 状态 §2、设计索引 §1、实施入口“人工接受后的Git提交”、DELIVERY_TOOLS §5；账本 commit/ledger.json。提交前运行 git diff --cached --check 并使用 delivery_summary.py --log 记录退出码。
