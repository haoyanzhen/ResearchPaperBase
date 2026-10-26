# 工程骨架R01–R04修复与复核收口

文档版本：v1.0
更新日期：2026-10-22

## 1. 交付结论

[原独立审核](skeleton_independent_review_2026-10-22.md)的R01–R04已修复并补回归。代码复核与证据复核subagent均未发现修复引入的阻断问题；人工接受仍待记录。[任务007](../../tasks/007-skeleton-review-fixes.md)列出授权、修改及需求追踪。本轮不改变业务规则、不实现业务数据库或持久Worker、不启动任务006。

本轮工作区存在并行变更，因此最终验收基线是**起始工作区加R01–R04修复的隔离源码快照**，不是未经区分的整个实时工作区。所有外部修改原样保留；独立基线与实时工作区的差异逐文件登记，不通过回退来制造一致性。

## 2. 问题闭合

| 问题 | 修改与回归证据 | 独立复核 |
| --- | --- | --- |
| R01 / P2 | 按包名相等或点分子成员匹配；禁止包根/成员正确拒绝，公开ports正确允许，近似私有名称仍拒绝；新增回归在原检查器12失败，新版本通过 | fix_code_review确认边界和三种导入形式；无新增阻断 |
| R02 / P2 | 统一monotonic截止时间，非阻塞字节读取完整启动行；无输出/半行超时、提前退出、正常退出及清理均验证；真实Worker移除启动日志后10秒明确失败 | subagent独立变异复现，确认失败并回收Worker |
| R03 / P3 | 应用测试和wheel HTTP探针精确断言200，日志来自实际响应；201变异拒绝，本机真实200/201正负检查 | subagent复跑201变异，确认在状态码断言处失败 |
| R04 / P3 | 完整源码tar和文件集合/SHA清单；含空文件、二进制与无换行文本；拒绝覆盖旧基线，拒绝缺失/篡改/额外清单 | candidate安全还原163/163及空.gitkeep验证通过；最终baseline再次核验，结果见final-review.txt |

旧文本patch不覆盖、不修写，作为历史缺陷证据保留。新交付以完整源码快照为准，修复差异仅帮助阅读，不再声称仅用文本diff即可还原文件集合。

## 3. 验证结果与基线对应

证据目录：[skeleton_fixes_2026-10-22](evidence/skeleton_fixes_2026-10-22)。原始check.txt记录早期56后端/15契约/2前端通过；随后发现并行改动，旧日志不宣称对应后续整个实时工作区。

最终隔离范围使用initial-files.tar.gz的非证据文件，加候选中本轮所属源码/测试（具体overlay见isolated-input.json），再同步本轮审核文档。重新安装运行，结果如下：

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 干净安装 | 通过，锁文件未改 | isolated-install.txt |
| 统一检查 | Ruff/格式/Mypy通过；58后端、15契约、2前端通过 | isolated-check.txt |
| 构建 | 后端sdist/wheel及前端静态产物通过 | isolated-build.txt |
| 浏览器预览 | 2项通过 | isolated-e2e.txt |
| 干净副本/安装wheel网络验证 | 安装构建、锁缺失/漂移拒绝、live实际200/ready实际503和进程关闭通过 | isolated-clean-delivery.txt |
| 缺陷变异 | 原R01回归12失败；201和静默Worker变异被修复测试拒绝 | r01-before.txt、regression-mutations.txt |
| 完整源码还原 | 文件集合及SHA逐项一致，空.gitkeep存在 | baseline/source-manifest.json、final-review.txt |

隔离目录中较早期56项多出的两项位于R03相关测试，已包含在候选快照和最终58项结果；不将不同时点计数混用。全部新证据保存在新目录，未覆盖原交付和原审核证据。

并行工作区的check也曾重跑成功（73后端、23契约、3前端，workspace-check-after-external.txt），仅说明该时点结果；契约公共错误及其他新增覆盖不属于本轮需求验收或业务审核。后续实时修改不由本轮自动背书。

## 4. 原工作保护与并行变更

initial.json与initial-files.tar.gz捕获起始191个文件；任务006及用户已有内容保留。旧交付16份、旧审核10份证据经subagent核验逐字不变。旧6份构建产物在original-artifacts备份并与原final摘要核对，最终新产物保存在validated-artifacts。

复核中发现并行写入contracts两个JSON、契约检查器、部分架构/前端测试和格式内容；未由本轮回退、删除或归入R01–R04修改。最终快照与实时工作区的明确差异见workspace-drift.json。快照是可复现且有范围的接受对象；如需接受并行新增功能，须看对应任务的证据和审核。

新基线[source.tar.gz](evidence/skeleton_fixes_2026-10-22/baseline/source.tar.gz)与[source-manifest.json](evidence/skeleton_fixes_2026-10-22/baseline/source-manifest.json)包含完整源码；[final.json](evidence/skeleton_fixes_2026-10-22/final.json)关联源码、产物和本轮证据摘要。原final.json保持历史原义，不刷新它来覆盖本轮修改。

## 5. 复现与人工审核

将最终source.tar.gz解压到新的空目录，在该目录使用README指定的Python3.14/Node24运行install、check、build及e2e；不连接旧数据。快照校验可运行：

```sh
python3 scripts/delivery_snapshot.py verify --directory docs/workorders/evidence/skeleton_fixes_2026-10-22/baseline
```

这是在当前仓库检验本轮归档的命令；归档内不递归包含证据目录。需要重新生成源码快照时，在有Git索引的仓库调用create并指定全新目录。

人工重点核对四项原反例的拒绝结果、子进程清理、空文件还原以及基线范围。上游Starlette/httpx弃用警告保留；真实PostgreSQL、业务权限/版本绑定、外部Provider、业务端到端和生产部署仍未验收。工程修复、自动验证与subagent复核完成不等同人工批准。
