# Task035：SMTP、OAuth授权刷新与基础安全配置

文档版本：v1.1
更新日期：2026-10-27

## 1. 授权与目标

承接M-P0-09接受后持续实现至下一里程碑或未明确设计的用户授权，以及task034 D-SMTP-01 A、02 B（QQ/163/Gmail/Microsoft 365/SendGrid）、03 A。交付管理员系统SMTP单例、四类认证及OAuth授权/刷新、显式连接测试与Security设置实际生效，目标M-P0-10。P0不发邮件、不启用通知，不执行真实外部注册/授权或邮件请求。

## 2. 依据及基线

task034原handoff321文件无漂移；本轮before保存在docs/workorders/evidence/task034_oauth_accepted_2026-10-26。已批准规则同步至03-01/04-01；Security补规格经独立核查可按已有保护规则工程细化，不设置新审批门禁。保留所有未提交/未跟踪工作。依据01 FR006/007、03-01 P10d/e、04-01/04-02、04-04、05/07/08/09及实施入口v1.7。

## 3. 修改落点

平台SMTP/Security迁移及存储、SMTP/OAuth适配器与持久Worker、管理员API/UI、系统任务治理/读取路由、LLM/Source测试预算接入、本地演示、机器契约、需求测试和文档。OAuth凭据不进入快照或响应；系统资产生命周期独立于操作者，撤权后迟到结果不可恢复执行资格。

## 4. S1需求追踪（历史计划；最终映射见第9节）

| ID | 场景与禁止副作用 | 可执行测试与证据 |
| --- | --- | --- |
| MS01 | 单例首次读取、保存/刷新、合法和无效组合、普通用户/CSRF/切号拒绝、凭据加密不回显 | 待建立SMTP PG/HTTP测试 |
| MS02 | 幂等/修订冲突/并发管理员/审计回滚、平台资产保留及撤权三阶段 | 待建立持久故障及确定性交错测试 |
| MS03 | 五服务认证映射、TLS/STARTTLS失败、认证拒绝、无认证、绝不发送邮件 | 待建立受控协议测试 |
| MS04 | 持久测试、刷新/重启恢复、租约/修订迟到拒绝、未知结果不重发 | 待建立Worker测试 |
| MS05 | OAuth state/PKCE/会话/Provider/修订绑定、重复/过期/拒绝回调、授权不等于测试成功 | 待建立OAuth测试 |
| MS06 | Token过期自动刷新、轮换原子并发、失败重授权、权限/配置变化拒绝、code/token不泄露 | 待建立凭据生命周期测试 |
| MS07 | Security默认/更新/冲突/未知字段拒绝/审计、超时取小、只重试未提交连接失败、最小与标准诊断及清理保护 | 待建立Security与受影响LLM/Source回归 |
| MS08 | 浏览器保存/测试/失败修复、未知响应原键恢复、切号及移动端、OAuth安全跳转 | 待建立真实浏览器测试 |
| MS09 | 机器wire、空链迁移、持久事实降级拒绝、构建/安装 | 待运行契约/迁移/工程检查 |

所有测试从已批准规则推导，不能以数量替代覆盖；未建立/未执行保持明确。完成后追加具名映射和结果。

## 5. 验证

隔离PG17由scripts/run_storage_tests.py显式创建并清理，禁止回落业务DB；Fake OAuth/SMTP/LLM/Source及本地浏览器。scripts/engineering.py check/build和verify_skeleton_delivery.py验证静态、单元、契约、类型、构建与离线安装。真实供应商兼容性未验证，不以mock代替真实服务声明。记录失败、修复、最终输入快照和清理证据。

## 6. 人工节点

SMTP三项已决，无新业务决定；Security按task034独立结论工程细化。M-P0-10在本片S1–S7完成后提交单一验收包并停止，不将工程检查当成人工接受。

## 7. S1历史报告

S1完成；S2实现中。代码、自动验证与工程收口均未完成，M-P0-10未到。实现分工不替代后续独立只读审查。

## 8. S1历史检查点

流程v1.7。已授权N4，S1基线/需求/决定核对完成，S2实现与首次测试进行中，S3–S7未执行。后续：完成需求测试与自验，独立只读审查、覆盖修复、行为保持简化、最终复验及快照交接。现有工作区全部保留；不自动推进Construction或P1通知。


## 9. S2–S5实现、覆盖与独立审查

已实现平台SMTP/Security表及0012迁移，原账号生命周期与Task读路由接入SMTP；管理员表单、五服务认证、持久测试及OAuth授权/自动刷新完整本地闭环。更新README操作入口和机器契约，旧PublicError守卫精确核对批准的SMTP增量，保留原字段断言。

| 需求 | 当前具名覆盖（backend/tests内） |
| --- | --- |
| MS01 | integration/test_smtp_configuration.py SM01、SM03；test_mail_integration.py MI01；SMB01/03/04 |
| MS02 | test_mail_integration.py MI02（三阶段）、MI03、MI04、MI05（真实PG advisory屏障）；SM01 |
| MS03 | test_smtp_configuration.py SM02五服务；unit/test_smtp_transport.py 真实回环SMTP/SSL-TLS/STARTTLS、证书/TLS拒绝零AUTH、无MAIL/RCPT/DATA、总deadline和固定DNS/SNI |
| MS04 | SM02、SM07、MI02、SMB05/06；原任务读取/事件共用回归 |
| MS05 | SM04/05/08/11/13（含PKCE材料损坏先消费）、SMB05/07；MI03撤权再授予握手失效 |
| MS06 | SM04/06/09/10/12（并发刷新意图所属task/attempt）；SM13无外发 |
| MS07 | integration/test_security.py SC01–07；unit/test_security_policy.py及test_llm_http.py未提交/已提交HTTP反例；SC06六种private/system测试的冻结策略 |
| MS08 | test_browser_smtp.py SMB01–07；test_browser_security.py SCB01–04；真实浏览器/HTTP/隔离PG，外部协议mock |
| MS09 | MI01真实wire、MI04降级保护及既有account/project空链迁移；scripts/tests/test_smtp_contracts.py及原契约守卫；工程检查见第10节 |

S3独立后端review_mail_backend发现P2刷新意图归属缺陷：竞争任务可清除其他活跃刷新意图，已增加持久task/attempt归属并由SM12真实提交屏障回归验证；P2 TLS覆盖缺口已补本地可信/不可信证书及STARTTLS拒绝、0AUTH验证。独立协议16项与增量契约11项通过，复审关闭。

独立review_security_ui确认未扩大诊断访问权/未重放已提交请求，发现P3超时轮间诊断尝试计数重置。先新增反例复现旧代码2失败/1通过，再修复计数，57项受影响单元与SC07持久诊断通过；日志security-p3-*。S4补SMB07 OAuth start未知响应恢复、SCB04 Security切号草稿，11项浏览器复验通过；首次SMB07等待边界不充分已修，保留所有业务断言及首轮日志。受影响独立复审见证据目录。

S5保留Store公共任务投影/授权锁、统一Security预算/诊断函数及现有UI请求封装；未作无关重构。重试只触发可证明未提交的连接失败，未知refresh持久意图不会重放。无新增业务决定，S6最终复验进行中，尚不宣称工程收口。

## 10. S6复验过程（历史检查点）

证据目录docs/workorders/evidence/task035_smtp_security_2026-10-26。首轮smoke为493通过/5失败：4项旧迁移头0011断言、1项新增select可访问标签，已修并保留日志。初轮静态失败为格式/分层引用和历史SMTP schema守卫，已按架构修复/精确登记批准增量，未放宽错误断言。

verification-input342文件后执行全量integration-full；期间仅追加经审查的PKCE损坏处理与Security尝试计数修复、S4浏览器/诊断测试及README。最终范围复验必须绑定这些差异：smtp-final-integration25项、smtp-final-unit-architecture57项、security-p3受影响单元/18SC、browser-s4-coverage-recheck11项；不能将旧输入的全量日志直接称为最新代码全量。最终release-input及漂移核对待本节追加。

Node25执行的check-full/build-full为初轮辅助结果；项目要求Node24，最终check/build/干净安装须使用明确Node24 PATH并分别记录。clean-install-node24已通过离线安装、构建、锁拒绝和安装wheel启停。上述测试均无真实供应商访问；本轮不会将mock视为供应商兼容性或生产验收。

## 11. S6–S7最终工程收口

最终Node24检查通过：221后端单元/架构、77契约、4前端测试；Ruff、Mypy、TypeScript及契约覆盖检查通过。Node24构建、离线干净安装、锁拒绝、wheel启停通过。日志为check-node24-final、build-node24-final、clean-install-node24-final。

verification-input全量隔离集成531通过（608.53秒），临时PostgreSQL停止且目录清理。该基线之后9文件差异记录于verification-delta.json；代码差异仅SMTP损坏PKCE处理与Security尝试次数，分别经25 SMTP集成/57单元架构及57受影响单元/18 Security集成覆盖，新增浏览器11项通过。最终静态/单元/构建/安装绑定release-input，未宣称旧531案例在最终源码重新全跑。release-input校验无代码漂移；之后仅收口文档更新，最终delivery快照包含文档。

两位独立审查者S6通过，无未关闭发现；详见independent-review.json。S4需求MS01–09均已具名映射，S5无需额外重构。S1–S7工程收口完成；设计、代码和自动验证完成，M-P0-10等待人工验收，真实邮箱授权/投递及生产部署未验证。现有未提交修改全部保留。

验收材料：[M-P0-10交付报告](../docs/workorders/task035_smtp_security_delivery_2026-10-26.md)。授权队列在此里程碑暂停；未自动执行Construction、通知推送或其他backlog，无新业务待决项。

## 12. M-P0-10人工接受（2026-10-27）

用户明确“通过M-P0-10”，接受第11节及交付报告限定范围，绑定原delivery343文件基线。恢复核对仅四份每日整理文档变化，业务代码/测试/契约无漂移，详见[task036](036-construction-design-gate.md)。历史验证复用，不声称本轮重新执行；真实邮箱与生产仍不在接受范围。用户同时授权下一阶段至里程碑或未明确设计，已进入N5核查；历史待验收记录保留原义。
