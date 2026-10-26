# Task022：Project基础维护闭环

文档版本：v1.2
更新日期：2026-10-26

## 1. 目标与授权

用户接受task021并授权“继续推进项目实现，直到里程碑或出现未决策的设计时再交给我审核”。本批连续实现Project元信息编辑→归档/软删除影响预览与确认→浏览器闭环；以M-P0-03统一验收，不逐操作要求人工审核。排除私人资产物理清理、生产迁移、P1/P2及尚未实现的Run/Task终止运行验证；当前真实模型没有Run/资产，不伪造活跃任务。后续接入Run必须补齐治理终止接缝。

## 2. 依据与基线

01 FR008基础字段、Owner、active/archived/deleted；02 §2.3；03-01 P02a/b；04 §5–7修订、确认与幂等；04-01 §1/3；05原子提交；07锁顺序；08状态限制/审计。归档和删除仅active；归档无解除入口，归档项目不允许删除。PATCH省略保持、null拒绝、Owner/status禁止通用更新，缺修订428/冲突412；未知结果先读取，不自动换修订提交。

入场task021 delivery240文件核对无漂移；快照在`docs/workorders/evidence/task022_project_maintenance_2026-10-25/before/`，全部既有修改保留。当前账号治理锁→Project行锁串行化短事务；不声称生产吞吐已验证。

## 3. 修改落点

Project服务/端口/PG适配器、API路由、独立生命周期审计/归档幂等记录迁移、BusinessApp、真实PG/HTTP/浏览器测试；按实际增量同步契约、README、状态。预览只签名不写业务记录；执行时原子保存确认事实、治理epoch/修订和结果，不生成伪Task。归档回执保存48小时最低承诺，已受理重放不重新校验旧token过期；删除失去可见性后返回统一404，不重放私人对象。

## 4. 需求追踪

- PM01 编辑：三字段部分更新、strip后长度/内部空白；省略保持、空说明清空、未知/只读/null拒绝；无字段修改不推进修订。
- PM02 并发保护：当前Owner/账号/CSRF、active限制；缺修订428、旧修订412；并发仅一份成功，失败无部分写；不改CW/知识/其他项目。
- PM03 预览：固定archive/delete动作、当前修订/Owner、有限有效期、影响/保留项/风险；不写业务状态或命令、无外部调用。
- PM04 确认执行：绑定账号/目标/动作/修订/影响/风险，缺失/篡改/过期/变化拒绝；状态/epoch/新revision/审计同事务，失败回滚；归档只读不可逆、删除不可读取不物理删共享/其他对象。
- PM05 幂等：归档同键同参只执行一次，同键异参409；先鉴权/可见性、重放保留原结果/到期元信息，不因旧revision/token过期失败；不同键重复受状态拒绝。
- PM06 存储：升级保留既有数据、metadata一致、约束/回滚/有数据降级拒绝、真实隔离与清理。
- PM07 UI：编辑/取消/保存、冲突保留草稿并显式重新加载、未知提交先核查、确认预览/取消/执行、归档只读/删除回列表、跨账号及失败恢复，桌面/窄屏；新功能不自动改写已接受内容。

当前实现的场景追踪（测试位于`backend/tests/integration/`）：

| 要求 | 可执行场景与证据边界 |
| --- | --- |
| PM01 | `test_pm01_partial_normalized_edit_noop_and_preserved_container`、10项`test_pm01_reject_invalid_without_write`、3项`test_pm01_each_field_trimmed_before_length_check`；保留省略字段、内部空白、清空说明、空PATCH/相同内容不推进修订、只读/未知/null拒绝 |
| PM02 | `test_pm02_permissions_revision_and_states`、`test_pm02_concurrent_updates_have_one_winner`、`test_pm02_metadata_write_failure_rolls_back`；真实PG阻塞观察，不只比较最终值；Owner/禁用/CSRF、缺旧修订、active状态及事务失败 |
| PM03 | 2项`test_pm03_preview_has_exact_effects_and_no_business_writes`、`test_pm03_preview_and_delete_reject_foreign_disabled_body_and_unknown_action`；完整具名字段/实际无Run的空影响集合、保留项、SQL无写入、重复预览不去重、权限/版本/动作拒绝 |
| PM04 | 2项`test_pm04_transition_audit_and_visibility`、`test_pm04_confirmation_binding_risks_and_revisions`、`test_pm04_expiry_and_pm05_replay_after_expiry`、4项`test_pm04_transaction_failure_has_no_partial_state`；两种动作/两处写点故障均回滚、token/风险/目标/动作/修订/过期、数据保留/epoch/审计 |
| PM05 | `test_pm05_archive_duplicate_conflict_visibility`、`test_pm05_key_scope_and_pm06_existing_foreign_owner`及4项`test_pm04_pm05_pm06_archive_commit_serializes_competitors`；归档同键重放/异参、不同Project同键独立、归档先提交后编辑/删除拒绝、并发降级不得删除已提交审计 |
| PM06 | `test_pm06_migration_data_preserved_and_downgrade_guard`、18项`test_pm06_record_constraints_preserve_audit`、`test_pm06_upgrade_ddl_failure_rolls_back_and_retry`及上行并发降级/已存在其他Owner的复合FK拒绝；新迁移与metadata一致、旧数据保持、失败DDL回滚和禁止有数据降级 |
| PM07 | `test_pm07_edit_cancel_archive_readonly_and_delete`、`test_pm07_conflict_retains_draft_and_requires_explicit_reload`、`test_pm07_lost_patch_and_archive_responses`、`test_pm07_shared_cookie_change_cannot_submit_old_draft`、`test_pm07_invalid_edit_can_be_corrected_without_losing_draft`、`test_pm07_lost_delete_then_404_clears_unavailable_project`；真实API响应先提交再断开，不伪造成功响应，含跨标签、明确字段拒绝可纠正、404安全空态 |

默认权限仍由当前有效Owner获得，状态限制不篡改权限授予。PATCH不需确认；预览不带幂等要求；DELETE不使用幂等键，其重复或未知结果必须按当前可见性处理。三份既有存储/认证用例只更新最高迁移名与精确表集合，原回滚/数据保持断言保留。

## 5. 验证计划与证据

证据根`docs/workorders/evidence/task022_project_maintenance_2026-10-25/`。真实临时PG17/非管理员、HTTP/Chromium；外部LLM/Provider/邮件不调用。计划build、集成、check，独立subagent审查与复验；历史失败与修复记录保留；最终全套与独立复审均已通过，准确范围如下。

- `integration-s2.log`：21通过/2失败，两项DELETE错误来自路由读取middleware私有`_body`属性；修复为统一请求边界检查，成功删除/错误确认拒绝原断言不变。
- `integration-s2-retry.log`：26通过/1失败，为新共享cookie测试前置错误（已登录的新标签没有注册按钮）；改为另一标签明确退出再注册B，保留A旧标签草稿，不改变被测拒绝条件。
- `integration-s3.log`：52通过/1失败，textarea可访问树和值已正确，但Playwright精确label选择器包含textarea内容而不匹配；改为可访问角色textbox/名称定位，同值断言保持。
- 首轮全套`integration-final.log`：255通过/10失败，包括8个旧head期望、旧精确表集和上条选择器；后续`integration-delivery.log`为迭代中的全套记录。旧轮执行时源码逐步修复，不能把这些结果移交为最终基线通过；最终输入固定在`final-input/`并运行`integration-verified.log`。
- 独立初审`/root/maintenance_review`发现R1：明确422误归为未知结果锁住可纠正草稿；R2：DELETE响应丢失后核查404仍保留旧详情。已修复并各补真实浏览器回归；不据404声称删除成功。初始独立反例和失败测试前置均保留，最终复审另记。
- `check-final.log`：87后端/66契约/3前端，以及ruff格式/静态、mypy43源文件、TypeScript通过。`build-final.log`：wheel及前端构建通过；之后源码未再修改，仅需求测试及最高迁移/表清单期望同步。
- 集成监督上限由180秒调整为300秒，以容纳扩展后的回归；保留超时/失败finally清理与30分钟demo限制，相关隔离清理回归仍执行。无依赖锁变化，未重新执行干净安装。
- 当前机器契约仍是局部覆盖：PATCH沿用已有ProjectPatch，归档请求沿用ConfirmationCommand；完整预览响应和SoftDelete机器转写缺项仍开放。本片按现行04/04-01逐字段、行为与副作用验证运行，不宣称OpenAPI已完整覆盖生命周期。
- 390px确认页面截图已目视核验，无横向溢出；其余浏览器操作使用默认桌面视口。已有Starlette测试客户端弃用警告保留。
- `integration-verified.log`：最终271项通过（原211项回归＋本批60项新增），201.15秒，run `rpb_test_cb2bcea4d92d4d52b6ae702aaa9c3155`；API/PG停止与临时根删除成功。代码/测试绑定`final-input/`，之后只有文档交接更新。上一迭代`integration-delivery.log`仍含旧表清单失败，不冒充最终通过。
- `independent-review-final.json`：R1/R2关闭，最终61项独立通过（本批60项及旧精确表集1项），210项未选择，59.82秒，run `rpb_test_8611470703e04ba291cfdc3e380ce5f8`，清理成功；受审源码、测试和迁移执行前后无漂移。未声称独立重跑全部271项。
- 最后旧表清单期望同步后的限定ruff/格式检查见`lint-final.log`。文档路径/版本/差异与受审摘要核对见`documentation-check.json`；最终`delivery/`保存完整内容基线，摘要见`receipt.json`。

## 6. 决策与里程碑

暂无新增业务决定。M-P0-02已限定接受；M-P0-03为本批Project维护可操作闭环，S1–S7已工程收口，现提交一次人工验收。后续Run接入必须落实活跃执行的立即撤权/安全终止，不用本片无Run场景替代。

## 7. 交付报告

本批实现Project基础维护的API、持久事务和浏览器入口；新建独立生命周期确认/审计与归档回执表，未重写已接受的创建回执或历史迁移。普通字段编辑不会改状态、Owner、CW或知识资产，失败不部分提交。状态治理与审计同事务，软删除不物理删除Project/CW/他人记录。

演示命令沿用已验证入口：先build，执行`python3 scripts/engineering.py demo --postgres-bin /opt/homebrew/opt/postgresql@17/bin`；打开`http://127.0.0.1:8765/workspace`。注册登录→创建项目→编辑信息/取消或保存→刷新查看；归档先预览、勾选风险后确认，项目变为只读；另建项目测试软删除，确认后回列表且旧链接资源不可用。第二账号无法维护第一账号项目。数据仅存本轮临时库，结束清理，不是持久开发环境。

本里程碑只涵盖当前尚无Run/资产的Project基础维护；运行中撤权/安全终止、私人资产清理、配置、知识构建、完整FR008和生产部署均未交付。预览签名为当前应用实例内存密钥，重启后重新预览，不声称多进程部署已验证。旧人工接受只绑定原基线，新维护行为由M-P0-03验收。

## 8. 检查点

流程v1.7；S1基线/范围、S2实现与自验、S3独立审查及R1/R2修复、S4逐PM覆盖补齐、S5保持现有UoW与独立维护组件无需额外抽象、S6最终271项/独立61项及构建/检查、S7基线和状态交接均已完成。所有操作使用本轮明确持续授权，不恢复延期或私人资产物理删除。

M-P0-03工程已收口、人工验收待接受；按用户“直到里程碑或出现未决策的设计时再交给我审核”在此交接，不继续后续依赖业务。无新增未决业务设计。交付状态分别为：本片设计/代码/自动验证/工程收口完成；里程碑接受尚未发生。原M-P0-01/02接受保持各自历史基线。

最终快照与`final-input/`相比仅README、文件索引、任务/状态记录追加，不改变受审行为。所有原工作区修改保留，未提交和未跟踪文件纳入快照。


## 9. FR-008剩余接缝规划（2026-10-26）

每日整理只登记交接，不改变第1–8节PM01–07交付范围、M-P0-03验收状态或原授权。依据01 FR-008功能范围/验收、02状态规则、04/04-01/04-02、08授权及10生命周期规则；不把无Run/无资产用例算作完整FR-008。以下编号为本任务的规划缺口，落地前须实例化验收任务并核对授权；不是本片已知缺陷已修复的声明。

| 缺口与可观察结果 | 包含/排除及写入所有者 | 输入→输出、硬前置 | 必需验收草案与完成条件 |
| --- | --- | --- | --- |
| PM-G01 生命周期机器协议 | B01负责contracts/p0.openapi.json、p0.coverage.json及契约测试；包含预览成功与SoftDelete完整结构；排除改变已定治理语义或重复实现HTTP | 消费04/04-01及PM03/04既有结构→具名机器载荷及覆盖映射；不依赖Run实现 | 成功/拒绝/未知字段/必填与修订、确认绑定负例；结构与运行响应一致、差异兼容有解释后闭合。缺逐字段矩阵及可执行测试映射；TRACK-004 |
| PM-G02 有执行对象时的治理 | Project应用服务拥有状态/epoch，Run/Task各自所有者负责停止和提交资格；包含归档/删除/私人资产清理生效时撤销影响范围内的执行写资格、安全终止与迟到结果拒绝；排除新业务状态、P1暂停恢复或通用重跑 | 当前Project/账号/执行资格→治理结果与终止交接；依赖真实Run/Task及对应B02/B03契约 | 真正提交与治理竞争屏障、重复治理、撤权、失效Worker、终止失败恢复，断言旧Worker不得发布KV或改人工内容；沿02 §2.3/08 §4保留既有终态，Research只取消attempt、不终结Session，Construction先撤销写资格再释放槽；补实际持久模型/端口/测试与执行证据后闭合。不得用空影响数组代替；TRACK-012d |
| PM-G03 私人资产清理 | Project发起授权/预览/确认，各资产所有者删除或排队清理Project独占数据；保留共享论文身份、他人数据及默认保留的已完成导出；排除自动按期限清理与旧库迁移 | 当前资产依赖/影响/保留清单→受控清理结果；复用PM-G02执行治理，依赖真实资产模型、文件/向量/图端口及A06/A07，不将H03当所有手动清理的前置 | 越权/陈旧确认拒绝、共享引用保留、执行中失败/重复/恢复、清理失败不恢复旧执行资格、跨Project隔离及导出保留；缺物理清单、故障点、可执行用例，逐项证据齐备才闭合。时间保留政策仅阻塞自动清理；TRACK-011b/012c |
| PM-G04 系统入口与可用性摘要 | UI系统导航拥有入口，Project列表只读投影；配置、Knowledge、Construction各提供者拥有源事实；包含用户/管理员配置入口、按分期的观点入口及真实知识/最近构建/活动/自动更新摘要；排除Workspace内部切换和提前实现P2观点业务 | 当前身份、权限、Project状态及源投影→可用入口/摘要；每个提供者具备契约后独立接入，不一次吞并所有模块 | 非管理员不可访问管理员入口；删除不可进入、归档只读；自动更新关闭仍可进入及手动交互；未知/失败不得伪造构建或KV；陈旧响应/跨账号不能泄露。缺提供者端口及逐入口浏览器用例；TRACK-012a/012e |

上述规划不解除M-P0-03验收点。PM-G02–04须再拆到具名操作、具体文件和逐需求用例，尤其PM-G03按关系/文件/向量/图资产分别建立验证，PM-G04按功能提供者拆分；不可将整行作为一个大实现任务。当前任务单仅承担缺口规划主责，后续实例保留这些ID作为交接引用。FR-011/012/013的内部对象/资产面板/上下文恢复继续沿原规划归属，不由本单吞并。

## 10. 人工接受与后续授权（2026-10-26）

用户明确表示“M-P0-03通过验收，可以进行下一阶段工作，直到完成项目里程碑或遇到未明确设计的内容”。接受范围为第4–7节PM01–07及原delivery基线，不包括第9节规划缺口。核对原244文件，代码/测试/机器契约无漂移；仅PROJECT_STATUS、设计索引、任务拆解和本单因10月26日每日整理发生文档追加。原271项和独立61项为历史有效证据，本次未重跑。M-P0-03已限定人工接受，第6/8节待验收为历史状态。下一阶段首先实现task023个人账户资料维护，不恢复延期项。
