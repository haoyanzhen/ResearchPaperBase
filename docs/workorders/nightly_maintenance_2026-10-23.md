# 每日项目整理首次手动试跑

文档版本：v1.0
更新日期：2026-10-23

## 范围与结果

用户授权将整理规则写入仓库、维护任务拆解、手动试跑通过后启用每天Asia/Shanghai 03:00定时执行。本轮只修改文档；业务实现、机器契约、数据库、外部Provider及应用测试不在范围。

- 新增[规则](../NIGHTLY_MAINTENANCE.md)，从[README](../../README.md)和[项目状态](../PROJECT_STATUS.md)进入；规定证据核对、并行修改保护、失败基线、任务覆盖与无变化处理。
- 整理[任务拆解清单](preimplementation_design_tasks_2026-10-21.md)第10节，区分历史授权、当前任务边界、FR目录归属、开放TRACK归属及仍缺的子条目规格；保留A/B/H定义与分期。
- 更新[task008](../../tasks/008-material-policy-internal-contracts.md)当前准入：A04限定接受；A05独立审核R01/R02待修、C01澄清影响分类成功响应/元信息和主动输入边界；未执行A06。
- 状态来源核对包括task006第11节、task007第6–7节及[独立审核](task007_independent_review_2026-10-23.md)。原测试通过是历史记录，本轮未重跑，不推定A05接受或缺陷关闭。

## 基线、并行变化与验证

[入场快照](evidence/nightly_2026-10-23_manual/before/source-manifest.json)包含176个源文件及未提交/未跟踪内容，归档由现有delivery_snapshot工具创建并校验。首次写入前检测到PROJECT_STATUS并行新增顺序交付skill记录及v1.40，整批写入中止、未覆盖任何文件。核对差异后保存[并行版本](evidence/nightly_2026-10-23_manual/concurrent-project-status.md)，基于其合并最小修改至v1.41；原条目保留。实施入口和任务模板的其他并行变化不归本轮交付。

检查脚本、实际输出和本轮差异存于 `docs/workorders/evidence/nightly_2026-10-23_manual/`。文档检查覆盖新增/修改文件，包括未跟踪文档；检查结果见[validation.json](evidence/nightly_2026-10-23_manual/validation.json)。只有检查通过且最终快照校验成功后才写入[success.json](evidence/nightly_2026-10-23_manual/success.json)，下次从其中after快照继续；失败不推进成功基线。

语义自审：A05/A06互相对齐没有转为循环硬前置；A04接受范围未扩大；旧记录保留；延期Graph-RAG、运行目标和未授权业务任务未启动；FR-034 P0单稿下载与FR-019通用导出分离，FR-036 P2版本增强未成为P0前置。全部36个FR目录和当前开放TRACK已分配规划归属；逐子条目与非功能完整任务实例仍有缺口，已具体列在清单第10节并由TRACK-012a继续跟踪，不宣称全项目需求/测试覆盖完成。

## 调度与限制

手动试跑的文档检查与调度配置是两项独立结果。调度将在检查通过后创建，配置结果保存在本轮证据目录；首次实际03:00触发尚未发生，不能记为运行验证通过。本地运行依赖电脑开机及Codex应用运行。

本轮不自动提交或推送；保留所有既有工作树修改。人工接受未代填。未来每轮须重新读规范、状态和实际产物，不能把本报告的A05问题状态永久固化。
