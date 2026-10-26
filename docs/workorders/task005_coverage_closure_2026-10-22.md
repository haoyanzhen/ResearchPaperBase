# Task005 面向需求的测试覆盖修复与审核包

文档版本：v1.0
更新日期：2026-10-22

## 1. 结论与范围

按用户授权完成task005已识别的覆盖缺口补齐、实现问题复核与必要修复、执行验证及审核证据整理。当前SK-01–09限定工程场景已具备需求、可执行断言和执行证据；提交人工审核，尚不代表人工接受或完整业务验收。详细逐项追踪以[任务005 §4](../../tasks/005-engineering-skeleton.md#4-验收规格与需求追踪)为准。

本轮入场时，工作区已经包含[独立审核](skeleton_independent_review_2026-10-22.md)R01–R04的部分修复及新增测试（相关任务007正在同一工作区推进）。保留这些实现并统一复验；不将其冒称本轮从零编写。契约文件、契约检查器及新增公共错误测试也有并行改动，本轮不编辑这些文件、不据此关闭task006。其他任务的新增/修改在最终快照内如实保留，其完成状态由对应任务负责。

## 2. 问题闭合与自审

| 发现 | 当前实现和需求断言 | 结果 |
| --- | --- | --- |
| SK-01 缺前端锁反例及锁不变断言 | 分别删除uv.lock/package-lock.json；断言没有安装调用、未生成缺锁、另一锁字节不变；真实locked/npm ci漂移反例后两个锁均不变 | 已通过 |
| R01 / SK-02 包根漏拦、公开ports误拒 | in_package按完整包边界匹配；3种导入形式、合法公开端口和相似私有包反例；补Application HTTP/ORM矩阵 | 已通过 |
| SK-03 端口下界与Worker脱敏遗漏 | 加1023拒绝；API/Worker错误码2及stdout+stderr无标记；保留上下界和其余非法配置 | 已通过 |
| R03 / SK-04 live未精确断言200 | 应用和wheel网络检查精确断言状态；实际HTTP200允许、201拒绝；证据输出真实状态；应用201变异被拒绝 | 已通过 |
| R02 / SK-05 无限等待 | 单一monotonic期限，selectors字节读取；无输出、半行和提前退出均可诊断并回收；真实Worker SIGTERM/SIGINT正常退出 | 已通过 |
| SK-04/05/06 缺连接副作用断言 | socket连接、psycopg.connect、SQLAlchemy create_engine均用记录调用的拒绝桩；API探针、idle Worker、migration/integration断言零调用；后两者覆盖缺配置和合成业务配置 | 已通过；只验证工程入口，不代表真实存储隔离 |
| SK-07 无伪造业务状态断言过弱 | 两页分别检查未接入说明、禁用操作、无fetch；无业务记录控件/链接/账号管理员入口、唯一main、导航往返 | 已通过；UI结构与源码同时自审 |
| SK-08 设置页未检查溢出 | 两种宽度逐页检查，截图四张；Tab+Enter聚焦main；无pageerror/写请求/fetch/xhr | 已通过 |
| R04 / SK-09 空文件无法重构 | 完整tar+SHA清单替代只靠文本diff；空/二进制/无末尾换行及缺失/篡改/额外清单回归；新快照只写新目录；实际全量解包核验 | 已通过 |

自审确认：业务源码仍只有进程配置、探针和显式空闲Worker，没有新增持久任务、业务状态写入或伪业务路由；前端产品源码未改。无数据库连接目标、LLM、论文源或邮件服务启用。新增测试期望来自task005和工程基线的可观察结果，并覆盖已发现回归；未降低原断言或删除必要反例。

## 3. 当前执行证据

目录：[task005_coverage_2026-10-22](evidence/task005_coverage_2026-10-22)。Node24/npm11沿用本机独立工具目录，跨机器按README选择运行时。

| 命令 | 实际结果 | 证据 |
| --- | --- | --- |
| `python3 scripts/engineering.py check` | 75后端、23契约、3前端通过；Ruff/格式/Mypy/TypeScript/契约结构通过 | check.txt、verification-inputs.json |
| `python3 scripts/engineering.py build` | 后端sdist/wheel、前端静态产物成功 | build.txt |
| `python3 scripts/engineering.py e2e` | 2项Chromium真实浏览器测试通过，每项覆盖Projects/设置 | e2e.txt及四张shell截图 |
| `python3 scripts/engineering.py migration-history` | 空链，退出0 | migration-history.txt |
| `python3 scripts/verify_skeleton_delivery.py` | 新临时副本按锁安装构建成功；两种缺锁及漂移拒绝、锁不变；安装wheel实际live=200/ready=503与SIGTERM；临时目录清理 | clean-delivery.txt |
| `python3 scripts/delivery_snapshot.py verify --directory docs/workorders/evidence/task005_coverage_2026-10-22/baseline` | 完整文件集合与SHA一致，包含空.gitkeep；另实际解包逐文件核对 | snapshot-verification.txt |

开发过程仅遇到一次格式检查失败：从仓库根运行格式化未显式选择backend配置。已使用`--config backend/pyproject.toml`修正，统一检查重跑通过；无测试失败被跳过。保留Starlette/httpx上游弃用警告。契约工具不提供旧审查baseline，因此不宣称历史兼容；其传递依赖未单独锁定仍为既有边界。

## 4. 审核基线与重定位

- `initial/source.tar.gz`及清单：本次入场完整源码，包含当时已有未提交和未跟踪内容，证据目录排除以避免递归。
- `baseline/source.tar.gz`及清单：交付完整源码；只使用diff不能代替该快照的文件集合核验。
- `delivery.patch`：相对本轮入场的差异，辅助审核；`scope.json`区分本轮文件与并行修改，不把其他任务改动列为本轮成果。
- `review-manifest.json`：审核材料、构建产物和实际验证输入摘要；`verification-inputs.json`记录执行时工程源码/锁/测试/契约输入，区分验证期间的并行变化。
- 原`skeleton_2026-10-22`、`skeleton_review_2026-10-22`证据保留，旧补丁的空文件缺陷仍如实留存。

人工复核建议：先读task005追踪表，运行check和clean-delivery；重点抽查包根导入拒绝、1023边界、201拒绝、无启动信号时的有限等待/回收、缺锁无副作用及快照完整重构，再查看两页两种宽度截图。源码和测试修改须生成新基线，不能将本记录用于其他产物。

## 5. 未验证范围与审核结论

真实PostgreSQL事务/并发、权限、知识版本绑定、人工内容保护、持久任务、业务端到端及生产恢复不在本任务范围，仍由PROJECT_STATUS相关TRACK跟踪。连接拒绝桩测试不替代将来的真实数据库隔离验收。干净安装访问公开软件依赖仓库；无真实业务外部调用。

设计依据：已核对；代码与测试：已实现并自审；自动验证：以上工程范围通过；人工审核：**待审核**。审核者、接受日期、接受基线/范围与问题处置留待人类记录。本轮提交审核不创建业务部署、不提交或推送Git、不自动启动其他任务。
