# 当前实现审计与精简

文档版本：v1.0
更新日期：2026-10-23

## 授权与基线

用户要求“审计当前实现的代码，对其进行重整，删除不必要的冗余和分支，并保证其能够通过已有的全量测试”。范围为已有工程骨架和校验工具的等价简化，不启动业务 backlog、不改变业务语义或权限边界。

入场 HEAD 为 `7ba2a2c638500eaa43f2137d16a6a0686b663630`。工作区原有大量修改和未跟踪源码；[入场完整快照](evidence/code_cleanup_2026-10-23/before/source-manifest.json)包含184文件及可恢复归档，不以HEAD代替实际产物。本次运行期间出现task009及项目状态并行更新，原样保留，不归为本次成果。当前实现与状态一致：只有工程骨架，业务核心尚未实现。

## 审计及修改

检查后端启动/配置/探针/迁移、前端Shell、工程安装检查构建、架构门禁、契约检查与交付快照工具，并核对相关测试。依据为AGENTS、实施入口、设计索引及工程基线的启动、模块边界、无业务能力与隔离约束。

- `backend/src/rpb/bootstrap/config.py`、`api.py`、`worker.py`：集中CLI配置失败处理，保持退出码2、固定脱敏错误及校验先后顺序。API工厂仍独立校验配置，不改变直接调用时抛出ValidationError的约定。
- `scripts/engineering.py`：Ruff检查与格式校验共用文件清单，命令顺序和检查范围不变。
- `frontend/src/App.tsx`：标题直接显示当前页面状态，删除返回同一状态值的三元分支。
- `backend/tests/unit/test_startup.py`：扩展API/Worker对端口、环境、监听地址、未知配置的拒绝和脱敏用例，补工厂拒绝非法配置场景；已有断言不减弱。

本次只改5个实现文件和1个测试文件，逐文件准确差异见[补丁](evidence/code_cleanup_2026-10-23/changes.patch)。保留架构占位包、健康/就绪区别、idle显式开关、存储/迁移拒绝、快照路径/摘要检查和契约兼容门禁：这些均有已定职责，不能因当前业务未实现当作冗余删除。其余受审代码未发现本轮需要删除的确定冗余，不做大规模重排或新增抽象。

## 需求追踪与执行证据

| 受影响规则 | 可执行场景 | 本轮证据 |
| --- | --- | --- |
| 配置边界、失败退出及不泄露值 | test_startup.py 的配置默认/边界、test_process_rejects_configuration_without_leaking_values（2入口×4配置）、test_app_factory_rejects_invalid_configuration | check.log，82项后端通过 |
| API只有探针、ready固定503，无存储副作用 | test_probes_and_no_business_routes、test_skeleton_requirements.py 的禁止连接场景、wheel实际HTTP探针 | check.log、delivery.log |
| Worker显式idle、信号退出、等待有界 | test_worker_refuses_task_execution、test_worker_idle_lifecycle及超时/早退场景 | check.log |
| 工程检查范围、架构边界不减弱 | engineering.py check完整执行，架构正负例、类型/格式检查 | check.log |
| 两个页面的标题、本地导航、不可写、键盘和响应式布局 | App.test.tsx全部3项、shell.spec.ts的1280/390屏宽2项 | check.log、e2e.log |
| 安装锁拒绝、独立构建及无隐式迁移 | verify_skeleton_delivery.py干净副本安装、锁漂移/缺失拒绝、wheel启停；空迁移历史 | delivery.log、build.log、migration-history.log |
| 既有机器契约保持不变 | 全部58项契约测试，结构检查，与本轮入场OpenAPI比较 | check.log、compatibility.log |

证据目录：[code_cleanup_2026-10-23](evidence/code_cleanup_2026-10-23)。执行环境为Python 3.14.4、Node 24.22.1、npm 11.21.1；命令在仓库根执行，前端运行时通过以下PATH选择，未改系统运行时：

```sh
export PATH=/tmp/rpb-skeleton-tools/node_modules/node/bin:/tmp/rpb-skeleton-tools/node_modules/.bin:$PATH
python3 scripts/engineering.py check
python3 scripts/engineering.py build
python3 scripts/engineering.py e2e
python3 scripts/verify_skeleton_delivery.py
python3 scripts/engineering.py migration-history
contracts/.venv/bin/python scripts/check_api_contracts.py --baseline docs/workorders/evidence/code_cleanup_2026-10-23/before.openapi.json
```

最终结果：82后端、58契约、3前端、2浏览器全部通过；Ruff、mypy、TypeScript、结构与相对入场兼容检查、构建、干净安装/wheel验证、空迁移历史通过。初次复验因根目录调用formatter采用不同格式配置失败，按backend配置修正后全量重跑通过；失败日志保留在check-format-failure.log。before-check.log为开始阶段运行记录，最终结果以check.log为准。

测试无真实LLM、论文源、邮件或数据库连接。干净安装下载依赖，仅在临时目录写入，脚本确认清理；浏览器仅访问本地预览。已有Starlette/httpx弃用警告未导致失败，依赖升级不纳入本轮。数据库集成和业务端到端尚未实现，拒绝测试不等于这些能力通过；与早期历史契约基线的人工审查差异不被本次“相对入场无变化”覆盖。

## 交付状态

实现与自审、全量自动验证已完成；无新增业务决定。未记录本次独立subagent审查或人工接受，不把自动检查当作人工验收。最终可恢复源码快照及摘要保存在`evidence/code_cleanup_2026-10-23/after/`。全项目剩余实现与验收仍由[项目状态](../PROJECT_STATUS.md)管理。
