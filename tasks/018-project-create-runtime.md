# Task018：Project创建与本人读取的真实事务

文档版本：v1.0
更新日期：2026-10-25

## 1. 授权与目标

按task016第8节用户批次授权，在task017账号认证工程收口后接入Project.Create/Read。task004是设计示例，授权来源仍是本次真实用户指令。目标：有效用户创建自己的Project，Project/唯一CW/去重记录原子提交；同键重复只返回原结果，非Owner安全404，管理员不例外。

## 2. 依据及依赖

01 FR008、02 §2.3、04 §3/4/7、04-01 §3、05/05-01跨模块写入所有权、07 §6.1；task014机器契约已接受，task016物理前置与task017认证可用。采用task004 T01–T10、R01–R13完整场景，不以其历史“未授权”否定本批次指令，也不把样例当代码完成。

## 3. 实现边界

Project应用协调UoW和Construction公开初始化端口，PostgreSQL adapter分别写自己事实；不造Task/outbox。去重键显式含actor/operation/scope/key，scope固定本人Project创建集合；JSON摘要仅包含规范化后的三个业务输入，默认空串归一，排除CSRF/请求ID。应用事务统一账号治理→会话→Project，短事务提交后才返回。当前版本为空，只返回显式null，不创建假KnowledgeVersion。

去重最早失效E默认t0+48h（>=24h）；无自动回收，超过E仍可保留原记录。测试时钟只替换受理时间来源，独立连接持久查询期限与重放，epsilon=1微秒。不增加生产保留政策。读取当前Owner与生命周期，deleted/非Owner返回404，archived可读但创建旧结果的写重放按当前只读保护拒绝。无Project修改/归档/删除/列表端点；它们后续独立切片，不在UI暗示可用。

## 4. 追踪

`backend/tests/integration/test_project_commands.py` 对应PC运行场景，task014同名前缀仅指静态契约，证据分目录。

| ID | 规格/观察 |
| --- | --- |
| PC01/T01 | 201/Location可读；Owner/active/default字段；Project/CW/command各一，无Task/Run/KV |
| PC02/T02/T03 | 同键真实竞争等待；同参同ID、异参409，两种winner顺序，无第二效果 |
| PC03/T04/T05/T08 | Project/CW/去重写后故障分别回滚；成功响应丢失后重放；存储不可用安全500 |
| PC04/T06/T07 | 两主体同键各自创建；跨主体（含管理员）404；禁用/CSRF/非法键/未知Owner/非法字段无写 |
| PC05/T08 | 默认/字段顺序归一；更换CSRF/request_id不改语义；返回当前request_id |
| PC06/T09/T10 | 独立时点12h/24h−epsilon及24h+epsilon<E重放；异参冲突；E与持久值一致且>=24h |
| PC07 | 去重唯一键、FK/必需字段、迁移失败/重入/降级保护；此前全回归及隔离清理 |
| PC08 | 读取/重放当前生命周期、无权限不泄漏细节；实际成功/错误schema断言 |

## 5. 证据

待执行，证据根 `docs/workorders/evidence/task018_project_commands_2026-10-25/`。独立PG17，不接外部服务或旧业务库。

## 6. 里程碑

所属M-P0-01。此片工程收口后继续浏览器闭环，完成注册/登录/创建/读取/退出与拒绝演示后提交单一验收包；不在每片要求人工批准。

## 7. 报告

待工程收口。完整Project生命周期/Hub列表/运行、知识、协作、生产部署均不在本片。

## 8. 检查点

流程v1.7；S1规范与测试规格准备完成；代码S2待task017最终复审闭合后开始；S3–S7未执行。保留既有所有工作区修改。
