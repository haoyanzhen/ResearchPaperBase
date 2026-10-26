# 第一批工程骨架独立审核

文档版本：v1.0
更新日期：2026-10-22

## 1. 结论与审核范围

用户授权安排subagent独立审核工程基线符合性、本批需求测试覆盖及交付证据一致性。本轮由三位独立subagent审核，主代理复核发现并汇总；只新增审核材料和同步项目状态，不修复实现，不替代人工接受。

结论：技术栈、目录、进程与未实现能力的边界总体符合任务005；原交付摘要与审核入场时的代码/产物一致。发现 **2项P2、2项P3**，建议先修复R01/R02，并随同补齐R03/R04后再确认本批完整接受。检查通过不等于本批全部测试要求已充分覆盖。

| 审核者 | 独立关注范围 | 结果 |
| --- | --- | --- |
| baseline_review | 00-01工程基线、实际源码与范围 | R01；未发现业务边界越权 |
| coverage_review | SK-01–09的输入、断言、失败与测试可靠性 | R02/R03；架构门禁问题与R01合并 |
| evidence_review | initial/final、补丁重构、产物与依赖版本、日志声明 | R04；其余摘要与产物核验通过 |
| 主代理 | 统一check重跑、入场摘要验证、架构与HTTP状态反例复核、去重与分级 | 接纳四项发现，未修改实现 |

评审依据：[任务005](../../tasks/005-engineering-skeleton.md)、[工程基线](../design/00-01_engineering_baseline.md)、[AGENTS](../../AGENTS.md)、[实施入口](../IMPLEMENTATION_ENTRY.md)及相关00/03/05-01/09/10。依赖锁、启动入口、脚本、全部本批测试与原交付材料均在范围内。数据库、业务迁移、持久任务、权限业务、版本绑定及Graph-RAG明确不在本批交付范围，未将其列为本轮缺陷。

## 2. 发现与建议

### R01 — P2：架构门禁漏拦包根导入，并误拒公开端口包

位置：[check_architecture.py](../../scripts/check_architecture.py:36) 第36–48行；对应任务005 SK-02及00-01 §3。

禁止前缀仅判断带尾点的字符串，导致Application中的 `import rpb.adapters`、`from rpb import adapters`，以及Knowledge中的 `import rpb.agents`、`from rpb import agents` 均返回空违规列表。合法的 `from rpb.modules.review.application import ports` 又因缺少ports后面的点被拒绝。这些是普通静态导入，不能归为动态分析的能力限制。

当前源码尚无上述违规依赖，但未来实现可绕过本批交付的门禁，现有负例未覆盖这类写法。建议统一按“目标等于包名或以包名加点开头”匹配，公开端口也采用相同边界规则，补三种导入形式的正负回归。

复现：[architecture-reproduction.txt](evidence/skeleton_review_2026-10-22/architecture-reproduction.txt)。主代理直接调用当前violations函数复核，无文件变更。

### R02 — P2：Worker启动测试没有等待截止时间

位置：[test_startup.py](../../backend/tests/unit/test_startup.py:96) 第94–98行；对应SK-05与工程检查失败可观测要求。

`stdout.readline()` 在进入 `communicate(timeout=10)` 前可能无限阻塞。临时副本移除Worker启动日志后，测试在外部4秒截止时间到达时仍未退出，只能由复现工具终止整个测试/Worker进程组。因此启动卡住时统一check不能及时给出失败结果。

建议使用有期限的启动握手或非阻塞读取，超时进入清理逻辑；添加“不输出启动信号/启动卡住”的回归并核验子进程退出。不是要求实现持久Worker。

复现命令和输出：[coverage-reproduction.py](evidence/skeleton_review_2026-10-22/coverage-reproduction.py)、[coverage-reproduction.txt](evidence/skeleton_review_2026-10-22/coverage-reproduction.txt)。变异仅在临时目录，已清理进程组。

### R03 — P3：live=200缺少精确状态码断言，日志固定宣称200

位置：[test_startup.py](../../backend/tests/unit/test_startup.py:54) 第54行、[verify_skeleton_delivery.py](../../scripts/verify_skeleton_delivery.py:114) 第114–129行；对应SK-04。

单元用例只断言响应JSON；wheel网络检查也只检查JSON，然后固定打印 `live=200`。将临时路由改为201仍能通过原单元用例（1 passed），urllib也会将201作为成功响应。当前实现实际返回200，问题是测试未保护明确要求且日志没有根据实际响应记录状态。

建议两处显式断言HTTP200，证据输出取实际响应值，并补状态码变异回归。复现见上述coverage输出及主代理的[live-status-reproduction.txt](evidence/skeleton_review_2026-10-22/live-status-reproduction.txt)。

### R04 — P3：交付补丁漏记新增空文件

位置：[原final.json](evidence/skeleton_2026-10-22/final.json) 第11/111行与[任务005](../../tasks/005-engineering-skeleton.md:20)的精确重定位说明。

初始tar解压后应用delivery.patch成功，但对照清单只能重构63/64文件，缺少新增空文件 `backend/migrations/versions/.gitkeep`。当前文件存在且摘要正确，重构目录的Alembic空history也返回0，因此无当前运行影响；但补丁不能完整重建声明的文件集合。

建议证据生成支持空文件新增，或增加完整交付源码快照，并执行“重构后的所有文件及摘要相等”验证。复现：[evidence-reproduction.py](evidence/skeleton_review_2026-10-22/evidence-reproduction.py)、[evidence-reproduction.json](evidence/skeleton_review_2026-10-22/evidence-reproduction.json)。

## 3. 实际验证与可信范围

| 验证 | 结果与证据 |
| --- | --- |
| 当前统一check重跑 | Ruff/格式/Mypy通过；26后端、15契约、2前端通过，保留原上游弃用警告；[check.txt](evidence/skeleton_review_2026-10-22/check.txt) |
| 入场摘要 | 64源码/文档、6构建产物、15证据全匹配；[entry-verification.json](evidence/skeleton_review_2026-10-22/entry-verification.json) |
| 初始内容快照与既有工作保留 | 106/106初始文件匹配；99个原文件逐字未变，7个为登记文档修改 |
| wheel与sdist | 各30份源码逐字匹配当前源码 |
| 版本记录与锁 | 后端34项记录、前端15项直接依赖一致 |
| 补丁重构 | 63/64，遗漏空文件，见R04 |
| 测试反例 | R01错误放行/误拒、R02等待无截止时间、R03错误状态码仍通过均已复现 |

本轮未重新安装依赖、构建产物或运行浏览器测试，以免覆盖原交付材料。原浏览器2项及安装/构建成功记录的摘要与内容已核对；不能把核对历史结果描述为本轮重新执行。真实数据库、外部Provider和业务端到端未执行，也不在本轮验收声明内。

## 4. 基线与本轮文档变更

审核入场以原final.json及其摘要为基线，检查时全部一致。本轮仅新增本报告、review证据目录，并将PROJECT_STATUS更新到v1.32登记待修问题。该状态文档变化会使原final.json中PROJECT_STATUS一项不再匹配，属于已解释的审核后文档变化；**没有重写原final.json或原证据来掩盖差异**。本轮清单见[review-manifest.json](evidence/skeleton_review_2026-10-22/review-manifest.json)，实现、锁文件与构建产物保持原摘要。

实现修复后应重新执行受影响检查和反例，再形成新的交付基线；原记录保留用于追溯。当前状态为独立审核完成、四项问题待修复、人工接受待记录。修复均属于工程质量问题，不需要新的业务语义裁决；本轮按用户要求先整理问题，没有自行进入修复。
