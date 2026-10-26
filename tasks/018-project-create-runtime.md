# Task018：Project创建与本人读取的真实事务

文档版本：v1.0
更新日期：2026-10-25

## 1. 授权与目标

按task016第8节用户批次授权，在task017账号认证工程收口后接入Project.Create/Read。task004是设计示例，授权来源仍是本次真实用户指令。目标：有效用户创建自己的Project，Project/唯一CW/去重记录原子提交；同键重复只返回原结果，非Owner安全404，管理员不例外。

## 2. 依据及依赖

01 FR008、02 §2.3、04 §3/4/7、04-01 §3、05/05-01跨模块写入所有权、07 §6.1；task014机器契约已接受，task016物理前置与task017认证可用。采用task004 T01–T10、R01–R13完整场景，不以其历史“未授权”否定本批次指令，也不把样例当代码完成。

## 3. 实现边界

Project应用协调UoW和Construction公开初始化端口，PostgreSQL adapter分别写自己事实；不造Task/outbox。去重键显式含actor/operation/scope/key，scope固定本人Project创建集合；JSON摘要仅包含规范化后的三个业务输入，默认空串归一，排除CSRF/请求ID。应用事务统一账号治理→会话→Project，短事务提交后才返回。当前版本为空，只返回显式null，不创建假KnowledgeVersion。

去重最早失效E默认t0+48h（>=24h）；无自动回收，超过E仍可保留原记录。测试时钟只替换受理时间来源，独立连接持久查询期限与重放，epsilon=1微秒。不增加生产保留政策。读取当前Owner与生命周期，deleted/非Owner返回404，archived可读且重放仅返回历史创建事实、不再次写入；deleted拒绝重放。无Project修改/归档/删除/列表端点；它们后续独立切片，不在UI暗示可用。

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

流程v1.7；S1规范与测试规格准备完成；task017已独立复审通过并S7，S2已实现且156项PG通过；S3独立审查中，S4–S7待最终执行。保留既有所有工作区修改。


### 自验与工程选择

初轮集成两项失败：资源安全404文案须严格“资源不可用”，公共错误映射已修复，实际schema回归识别原问题。当前integration-fixed为156项通过、实例停止/清理true；增加命令全部必需字段、operation/scope/key/hash/result身份、24h下界、同Owner复合FK/唯一键、故障升级及writer/down并发。所有旧AC/PS/AU回归保留，仅head/table集合适应新增迁移；原迁移0001–0003不改。

当前选择账号治理事务锁覆盖受理，确保禁用与创建有同一排序边界；粒度较粗，会串行不同账号的短创建事务，不宣称吞吐验收。Construction写入由bootstrap注入其初始化端口，Project应用只协调，不直接写其私有表。S5自审移除未使用的writing分支，保留当前可见性检查；未改权限或断言。最终源码复验/独立审查后收口。


### 独立审查修复与覆盖复核

S3 `/root/project_storage_review` 发现R1：JSON null的result.id使CHECK得到SQL NULL而被接受，已增加jsonb_typeof(id)=string及JSON null回归；R2：持久重放载荷缺独立版本，现保存schema_version=1，未知版本在当前授权检查后安全拒绝且不改写/删除，测试v2拒绝及原记录保持。初审混合态重跑与修复DDL重载重叠的3失败不计固定基线结论，完整保留说明；修复快照后重跑。S4补实际字段NULL/研究范围上限/未知status及16/128键边界，沿用task004全部T01–T10。版本不是文档/OpenAPI版本，无旧业务库回填。


### S7最终工程收口

S1–S7完成。S3/S6独立 `/root/project_storage_review` 固定s3-fix2复验168项真实PG全部通过，run_id `rpb_test_8f25a755524a4ab5ba8708799bc21349`，实例停止/目录清理true；manifest SHA256 `a9d712b6cb9e6a802584bfca6c695f95ca969f1d7f7c22e1ced5faf5f2707d2e`，前后无漂移。R1/R2和覆盖缺口全部闭合。S4按PC01–08/task004 T01–T10及R01–13核对完整；S5无需额外简化，已移除未消费分支。check-final2：82后端/66契约/3前端、ruff/format/mypy通过；build-final通过；最新测试仅新增合法name1组合，独立168项实际执行覆盖该最终内容。详见receipt及独立记录。

设计、代码、自动验证与工程收口限定完成；M-P0-01未到触发点，继续[task019](019-browser-milestone.md)真实浏览器闭环。未实现的Project列表/修改/归档/删除等不算本片完成，也不恢复逐任务人工门禁。最终delivery相对受审仅追加交接记录。
