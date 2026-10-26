# Research Paper Base

文档版本：v1.7
更新日期：2026-10-23

面向深度检索与学术研究的工作空间项目，目标包含论文库构建、基于知识版本的研究对话和文献综述。

当前交付范围与验证结果见[项目状态](docs/PROJECT_STATUS.md)和[第一批骨架审核单](tasks/005-engineering-skeleton.md)。以下命令用于本地工程骨架；业务功能、持久任务和知识库尚未接入。

## 当前入口

- [项目进度](docs/PROJECT_STATUS.md)
- [每日项目整理规则](docs/NIGHTLY_MAINTENANCE.md)
- [现行设计索引](docs/design/README.md)
- [新核心设计与审核入口](docs/IMPLEMENTATION_ENTRY.md)
- [最小工程基线](docs/design/00-01_engineering_baseline.md)
- [A01–A03交付与基线记录](docs/workorders/a01_a03_design_closure_2026-10-21.md)
- [API 机器契约范围与验证命令](docs/design/04-03_machine_contract_governance.md)
- [内部模块与执行契约](docs/design/05-01_internal_module_contracts.md)
- [安全与交付设计细化记录](docs/workorders/security_delivery_refinement_2026-10-19.md)
- [数据、测试与文档清理记录](docs/workorders/data_test_design_cleanup_2026-10-19.md)
- [历史设计归档](docs/archive/design_retirement_2026-10-19/README.md)
- [历史核心重写计划（不作为现行执行单）](docs/proposals/core_rewrite_plan_2026-10-16.md)
- [独立审查与拆分结果](docs/proposals/reuse_independent_review_2026-10-16.md)
- [或许有用的逻辑存档](archive/maybe_useful/README.md)
- [实际清理记录](docs/workorders/legacy_cleanup_execution_2026-10-16.md)
- [逐文件处置清单](docs/workorders/legacy_cleanup_manifest_2026-10-16.json)
- [文件职责索引](docs/file_map.md)

## 重建边界

`archive/maybe_useful/` 仅为独立候选片段与规则材料，不是新应用。新实现采用其中内容前应按新契约核验，不恢复旧接口、旧状态机或旧依赖全集。

`docs/design/` 保留现行设计；旧07 SQL草案已删除，可执行数据结构由后续迁移维护。07为持久化协议，08为安全契约，09为架构/模块及SEC/OPS测试用例，10为运行与交付约束；未决政策在08/10单列。历史报告及工作单用于追溯，不是当前功能验收证据。既有 Git 历史未改写。

工程安装与验证入口如下；业务实现按独立切片推进。

2026-10-19：新增独立 API 契约产物及检查工具。其依赖、运行命令和覆盖缺项见上述机器契约入口；这些检查不启动应用，不替代数据库或端到端验收。

本次修订 v1.2（2026-10-19）：同步07/09/10及退役归档入口，未启动应用实现。

本次修订 v1.3（2026-10-19）：同步安全与交付设计入口，未启动应用实现。

本次修订 v1.4（2026-10-21）：建立当前实施/审核入口；历史重写计划仅用于追溯，未开始编码或环境安装。


## 本地工程入口

已验证环境：Python 3.14.4、uv 0.11.7、Node 24.22.1、npm 11.21.1。
先用自己的运行时管理器选择 `backend/.python-version` 和 `frontend/.node-version` 对应版本；不使用系统 Node 25。命令在仓库根执行。

```sh
python3 scripts/engineering.py install
python3 scripts/engineering.py check
python3 scripts/engineering.py build
python3 scripts/verify_skeleton_delivery.py
```

安装使用 `backend/uv.lock` 的 locked 模式与前端 `npm ci`。契约检查保持独立环境及原 `contracts/requirements.txt`，其间接依赖尚未单独锁定；本次环境版本见审核证据。安装需要依赖仓库网络，测试与启动不调用真实 LLM、论文源或邮件。

分别在三个终端运行，按 Ctrl+C 停止：

```sh
python3 scripts/engineering.py api     # http://127.0.0.1:8000
python3 scripts/engineering.py worker  # 显式 --idle，无任务领取能力
python3 scripts/engineering.py ui      # http://127.0.0.1:5173
```

API `/health/live` 返回200；`/health/ready` 固定503，表示骨架尚无业务就绪能力。没有业务API、会话或管理员账号，不连接数据库或文件存储。类型化进程配置唯一来源是 `backend/src/rpb/bootstrap/config.py`：仅进程环境变量 `RPB_ENVIRONMENT`（development/test）、`RPB_HOST`（仅127.0.0.1）、`RPB_PORT`（1024–65535）受支持，默认值见源码；变更需重启，不读取.env。未知RPB变量或生产模式拒绝启动，错误不回显值。

浏览器验证（先完成build）：

```sh
cd frontend
npm exec playwright install chromium
cd ..
python3 scripts/engineering.py e2e
```

浏览器测试针对构建产物，覆盖390/1280宽度、本地导航、键盘入口、无横向溢出和无写请求；不代表业务端到端验收。截图在 `frontend/test-results/`。

`python3 scripts/engineering.py migration-history` 可查看空迁移链。`integration` 和 `alembic upgrade head` 当前明确失败，不连接任何数据库；真实PostgreSQL 17、隔离夹具及第一份业务迁移须随后续存储切片交付。构建产物在 `backend/dist/` 和 `frontend/dist/`，不隐式迁移。

本次修订（2026-10-22）：增加首批工程安装、启停、检查和构建入口；审核结论由人工记录。


## 工程交付快照

审核R01–R04修复见[任务007](tasks/007-skeleton-review-fixes.md)。完整源码快照包含空文件、二进制和当前未提交源码；不依赖文本diff恢复文件集合，不包含证据目录以避免递归。只接受新输出目录，不覆盖历史基线：

```sh
python3 scripts/delivery_snapshot.py create --directory docs/workorders/evidence/new-delivery-baseline
python3 scripts/delivery_snapshot.py verify --directory docs/workorders/evidence/new-delivery-baseline
```

验证检查归档文件集合和每份内容摘要；修改源码后须生成新基线，旧交付记录保留。创建命令中的路径是新基线示例；本次实际基线位置见任务007。
