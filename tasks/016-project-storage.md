# Task016：Project与唯一Construction容器持久化

文档版本：v1.0
更新日期：2026-10-25

## 1. 目标与授权

2026-10-25用户批次授权与真实消息已核实，见[task015第10节](015-account-storage-migration.md)。沿已定P0自主迭代，不恢复延期项。本片建立Project及唯一ConstructionWorkspace的存储前置，数据库提交后恰好一对、Owner存在、非法状态或跨Project配对被拒绝；不冒充HTTP权限、完整Project或知识版本业务。

## 2. 依据与基线

已读AGENTS、实施入口v1.7、设计索引、01 FR-008/011/014、02 §2.3、04-01 §3、05应用边界、07 §3/4/9、08 §2/3。task015 Account已获限定接受。入场[完整快照](../docs/workorders/evidence/task016_project_storage_2026-10-25/before/source-manifest.json)保留所有既有修改。

## 3. 修改落点与工程选择

新增Project/CW存储元数据及0002迁移；保留0001不变。Project保存owner/name/description/research_scope/status/治理epoch、revision和UTC时间。CW独立UUID、project_id唯一、revision和时间。Project通过延迟复合外键指向属于自己的唯一CW，CW反向引用Project；允许同事务创建，禁止半对提交或跨Project配对，不采用级联删除。将来知识版本迁移再加default指针及同Project外键，本片不引入悬空UUID列，也不建空壳KnowledgeVersion。检索词/来源策略/运行记录另片落实，不把基础CW表称为完整配置容器。

## 4. 需求追踪

测试：`backend/tests/integration/test_project_storage.py`，PS编号对应函数前缀。

| ID/依据 | 输入与观察 | 禁止副作用 |
| --- | --- | --- |
| PS01 07迁移 | 空库及0001升级，Account数据保持，metadata一致、单head；重入无损 | 不改写0001、不删账号 |
| PS02 02唯一CW | 同事务创建Project/CW，独立连接读完整对、UUID/UTC/默认active/空描述 | 不产生Run/Task/KV |
| PS03 07归属 | 缺Owner、孤立Project/CW、跨Project配对、第二CW、删唯一CW/Owner均拒绝 | commit后无半对，无跨项目绑定 |
| PS04 04字段 | 名称1–200；描述/范围≤10000；状态active/archived/deleted；epoch非负；必需字段非空 | 失败事务全部回滚 |
| PS05 07回滚 | 有Project拒绝降级；空Project允许回0001，原Account保持；故障后版本及DDL回滚再重试 | 不删已提交业务数据 |
| PS06 并发 | writer未提交时down等待，writer提交后down拒绝，持久行保持 | 不先检查后删导致数据丢失 |
| PS07 影响范围 | AC01–11全量回归及隔离清理；原API/Worker无库行为保持 | 不把数据库外键当鉴权 |

## 5. 执行证据

已执行隔离PG17：59项通过，清理成功；完整检查进行中。命令：`python3 scripts/engineering.py integration --postgres-bin /opt/homebrew/opt/postgresql@17/bin`、check、build。证据根 `docs/workorders/evidence/task016_project_storage_2026-10-25/`。测试仅独立临时PG17，无外部服务调用。

## 6. 决策与里程碑

D-016-01身份标识规则：用户在本聊天明确选择A，用户名/邮箱去首尾空格并忽略大小写，保留显示原文；禁止跨账号任一标识冲突，允许同账号二者相同。该决定解除注册/登录规范化阻塞；后续账号任务写入规范与并发回归。

M-P0-01拟定为首个可用闭环：注册、两种标识登录、退出/禁用拒绝、创建并读取本人Project；重放不重复创建、非Owner（含管理员）不可读。触发为该闭环工程收口后，提交单一验收包；之后依赖该业务基线的配置/构建接入等验收后继续。本片只是前置，不单设人工验收。

## 7. 交付报告

S1–S7已完成工程收口，非独立人工验收。排除真实生产迁移、知识版本/发布、Run/Slot、检索词配置、账号治理、HTTP/UI端到端。数据库字段约束不代替应用权限和状态裁决。

## 8. 顺序交付检查点

批次来源见第1节；队列：task016 Project/CW存储（依赖Account已接受）→账号注册登录及会话（依赖D-016-01已决定）→Project.Create幂等及本人读取→UI闭环/里程碑验证。后续逐片建单，业务前置不满足时不假定完成；延期项不进入队列。

流程v1.7；S1–S7已完成。当前基线before；无待决业务事项。最近核对task015只有4份整理文档变化，无代码漂移，接受绑定旧delivery。下一动作实现PS01–07、自验、只读独立审查。


### 最终工程记录

S2：初次59项PG17通过，check通过（82后端、66契约、3前端及ruff/mypy/格式），build通过。S3独立审查 `/root/project_storage_review` 发现P2：PS04漏Project id及CW五个必需字段NULL负例；已补6例，明确23502、两表回滚且Owner保留，最终65项通过。S4按PS01–07逐场景复核无本片必需缺项；S5无需简化，冻结迁移和可变元数据保持各自所有权。S6独立复审重跑65项通过，run_id `rpb_test_6bdbc5a9f88a4d71891656758fdb36a9`，停止/清理true；s3-fix SHA256 `260b3834991aa0f7ac0faf0602866df1ef1139617d5265dff6a17ce1cffde196`，无漂移。S3后仅增测试及用户已决定账号规范记录，包源码未变，复用本轮构建。独立复审确认P2闭合、无剩余阻断问题。

S7保存delivery及receipt，状态同步。设计/代码/自动验证/工程收口：本片完成；M-P0-01未触发。继续[task017](017-account-authentication.md)，不设逐任务人工审批。当前快照相对受审仅任务/状态交接和下一任务记录追加，不改变本片规则。最终证据见同目录integration-final.log、check.log、build.log及receipt.json。
