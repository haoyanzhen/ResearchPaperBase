from pathlib import Path
import json,hashlib,difflib,tarfile
r=Path('docs/workorders/evidence/nightly_2026-10-23_0954'); old=json.loads((r/'before/source-manifest.json').read_text())
files=['docs/PROJECT_STATUS.md','docs/workorders/preimplementation_design_tasks_2026-10-21.md']
for n in files:
 assert hashlib.sha256(Path(n).read_bytes()).hexdigest()==old[n], 'parallel drift '+n
n='tasks/009-workspace-context-plan.md'; assert not Path(n).exists()
Path(n).write_text('''# Task009 Workspace恢复子条目规划

文档版本：v1.0
更新日期：2026-10-23

## 1. 目标、授权与边界

本单由每日整理授权建立规划，不授权设计改写、编码或测试执行。主规划归属为FR-013；关联TRACK-012a/012b/012c/012e，B01/B02/B06/B07按下述行为提供工程能力，不另建同义所有者。设计含义沿用现行规范，实际实现、自动验证和人工接受均未开始。

依据：[FR-013](../docs/design/01_functional_requirements.md#fr-013-workspace-上下文管理与恢复)、[05-01模块所有权](../docs/design/05-01_internal_module_contracts.md)、[07逻辑事实](../docs/design/07_data_persistence.md)、[08权限](../docs/design/08_security_permissions.md)。Workspace只写用户/Project显示上下文与未提交草稿，业务模块保留Run/Session/KV及正文写权。

包含P0最近对象、基础面板、三类对象草稿恢复和全部安全降级；P1精细位置单列。排除FR-011对象创建/切换业务、FR-014运行操作、FR-016步骤内容、FR-018版本采用及任何自动生成/检索/导出。复用这些模块的只读投影，不代替它们实现。

## 2. 子条目、所有者与输入输出

下列WC编号为本任务局部规划标识，不新增FR。每个切片执行前单独获授权并补实际文件和测试定位，不将整个任务当作一次大交付。

| 切片/分期 | FR-013功能范围与验收子项 | 输入→可观察输出 | 所有者/拟修改落点 | 真正前置及交接 |
| --- | --- | --- | --- | --- |
| WC-01 / P0 | 按用户、Project、对象类型/ID记录；最近对象与无记录默认；基础面板 | 当前主体与Project、保存的对象和panels→允许查看的对象及展开/折叠状态 | Workspace应用/持久适配器及前端Shell（具体路径待执行前确定）；唯一上下文写者 | 认证/Project可用性与对象可访问投影；07唯一归属及API对应契约待实例化；交WC-02 |
| WC-02 / P0 | Construction检索词草稿、Research未发送输入、Review当前章节或大纲及编辑草稿 | 对象/part、draft及base_revision→相应未提交编辑器现场 | Workspace保存草稿，前端恢复编辑器；Construction/Research/Review正文仍由原模块写入 | WC-01及对象/part只读投影；不要求对应Agent已可运行；交WC-03的统一降级验收 |
| WC-03 / P0及P1复用 | 不自动写入/重跑/生成/检索/导出/覆盖；失效对象或落点降级并说明；状态/权限/人工保护/版本规则 | 删除、撤权、归档只读、不可继续、失效落点或不可写草稿→安全空态/对象安全位置及原因，不恢复可写状态 | Workspace读取编排与前端保护；权限/业务状态由各自权威模块提供 | WC-01/02实现时必须同时满足本约束，WC-03是共用验收归属而非可后补安全功能；无反向硬依赖 |
| WC-04 / P1 | Construction区域/自动设置/最近Run位置；Run步骤/结果/错误/日志/右面板；Research轮次/滚动/引用/详情；Review大纲/章节/审查/导出步骤、引用/滚动 | 细粒度位置→仍合法的原位置或安全默认位置 | Workspace上下文与对应前端面板 | WC-01/02/03和对应页面只读定位；P1未实现不阻塞P0，不触发自动调度或导出 |

共同写入落点：07的WorkspaceContext逻辑记录、Workspace应用端口和前端上下文消费；这些是职责范围，实际源码路径、HTTP操作与物理迁移仍待建实。不会因此授权修改机器契约。输出交接为前端恢复结果与需求测试证据，业务对象/版本绑定必须保持原值。

## 3. 验收规格与缺口

| 场景/归属 | 输入与动作 | 预期及禁止副作用 | 必须观察的证据 |
| --- | --- | --- | --- |
| WC-T01 / WC-01 | 同一用户重开Project，有有效最近对象/无记录各一次；另一用户及Project有不同记录 | 恢复本作用域对象/安全默认与基础面板；不读取其他主体或Project草稿 | 隔离真实存储的上下文归属、API响应及浏览器对象/面板 |
| WC-T02 / WC-02 | 分别保存三类对象草稿后关闭重开；Review分别选章节与大纲 | 恢复准确未提交草稿与目标；Research不发送，Construction不改正式检索词，Review不覆盖正文 | 草稿与业务正文/修订前后比较；Provider调用计数为零 |
| WC-T03 / WC-03 | 保存后删除对象、撤权、归档Project、对象不可继续；另测草稿存在但目标不可写 | 安全空态及原因，不暴露无权内容，不恢复可写编辑状态；不自动提交草稿 | 读取授权结果、页面提示和所有业务记录前后不变；各分支分别运行 |
| WC-T04 / WC-03 | 目标仍合法但所存落点失效 | 对象默认安全位置/概览并说明；不通过创建新对象修复位置 | 当前对象与无新增Run/Session/Task/KV记录 |
| WC-T05 / WC-01/02/03 | 重复打开；恢复期间权限或业务正文/修订已改变；已有人工编辑与旧绑定版本 | 重复恢复不增加业务写入；不绕过当前权限、覆盖人工内容、刷新绑定或自动重跑 | 确定交错屏障置于上下文读取与投影授权边界；实际正文、绑定、任务数与外呼均检查 |
| WC-T06 / WC-01/02 | 上下文保存或读取失败，随后重新打开 | 不将保存失败报成功，不推进任何业务状态；恢复可用性及提示按现行API/UI错误规则落实 | 故障注入与事务回滚证据；具体错误展示和多端草稿冲突预期待契约核对，不自行制定胜出政策 |
| WC-T07 / WC-04 | 逐一恢复上表全部P1位置；失效/撤权/只读反例重复 | 合法位置可恢复，失效降级；查看导出步骤不能触发导出，查看自动设置不能触发调度 | 各页面浏览器验证及WC-T03/04/05复用；P1独立验收 |

所有场景的可执行测试路径、用例名和运行证据均未建立。前置缺口归本单对应WC切片：WC-01缺具体端口/迁移/权限夹具；WC-02缺各编辑器接入及草稿base_revision冲突规则核对；WC-03缺真实授权/状态投影及确定交错测试；WC-04缺P1逐页面定位协议。错误行为或多端冲突若现行规范不足，列证据/选项/建议，只暂停对应分支，不假定新产品规则。

完成条件：每个获授权切片逐条映射上述需求、真实文件和测试；隔离数据库覆盖服务内commit并清理，Provider默认mock；通过适用持久化/浏览器/失败及权限验证后再提交人工审核。静态文档检查不算业务测试，WC-03不能成为无执行观察点的安全兜底声明。

## 4. 交付及当前检查点

本轮仅完成上述任务规划，代码/自动业务验证/人工接受均未开始；不进入project-delivery执行队列。规划检查见[本轮每日整理](../docs/workorders/nightly_maintenance_2026-10-23_0954.md)。其余35个FR及非功能要求的细拆仍由任务清单第10节登记，不能以本单宣布全量逐需求覆盖完成。
''')
p=Path(files[1]); s=p.read_text().replace('文档版本：v1.2','文档版本：v1.3',1)
s=s.replace('Project可用性、对象切换、资产查看、上下文恢复分别成单；缺实际任务/权限与恢复反例','Project可用性、对象切换、资产查看仍待建单；FR-013由[task009](../../tasks/009-workspace-context-plan.md)细拆WC-01–04及WC-T01–07，具体端口/源码/测试仍缺')
s+='''\n### 10.4 本轮细拆交接\n\nFR-013唯一主规划责任由“Project与工作区”索引下的[task009](../../tasks/009-workspace-context-plan.md)承接：WC-01最近对象与基础面板、WC-02三类草稿、WC-03共用安全降级验收为P0，WC-04精细位置为P1。WC-03约束必须随WC-01/02交付，不作为可延后的安全补丁；不依赖A09/H01选型，也不授权实现。所有者、输入输出、正向/拒绝/失败及权限交错场景已列；具体文件/端口、冲突细则核对及可执行测试仍开放。其余FR的具体子条目、非功能/领域不变量/安全/运维逐条实例矩阵仍缺，主责与缺失字段沿用10.1–10.3；TRACK-012a不关闭。A/B/H和开放TRACK归属保持，A05新增覆盖证据不关闭运行验收。\n'''
p.write_text(s)
p=Path(files[0]); s=p.read_text().replace('文档版本：v1.45','文档版本：v1.46',1)
s=s.replace('首次手动试跑与覆盖缺口见[整理记录](workorders/nightly_maintenance_2026-10-23.md)；','首次手动试跑与覆盖缺口见[整理记录](workorders/nightly_maintenance_2026-10-23.md)；[后续增量整理](workorders/nightly_maintenance_2026-10-23_0954.md)已核对5份证据文档增量，并建立FR-013的[task009规划](../tasks/009-workspace-context-plan.md)，实现与测试未启动；')
p.write_text(s)
(r/'changed-files.txt').write_text('\n'.join(files+[n])+'\n')
