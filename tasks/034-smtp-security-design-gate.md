# Task034：SMTP与基础安全配置设计核查

文档版本：v1.2
更新日期：2026-10-26

## 1. 目标与授权

用户2026-10-26明确接受M-P0-09并授权“继续实现下一阶段，直到里程碑进度或遇到未明确设计”。承接[task030](030-next-system-configuration-plan.md) N4：管理员SMTP保存/连接认证测试、基础安全配置。拟M-P0-10为该可用闭环：管理员保存后刷新恢复、测试成功/失败与修复、普通用户拒绝、密钥脱敏和安全设置实际生效。未到里程碑，不启用P1通知或业务邮件，不执行真实外部测试。

## 2. 依据与实际基线

已读AGENTS、项目状态、设计索引、实施入口、project-delivery技能及01 FR006/007、03-01 P10d/e、04-01配置操作、04-02任务对象、05配置解析、07密钥、08凭据/诊断、09 MOD02、10 P0分期。机器结构见contracts/p0.openapi.json的SMTPWrite/SMTPSave/SMTPConfigView/SecurityWrite。

原task033 delivery320文件逐SHA-256核对0漂移；用户接受绑定该原产物。保留全部既有修改。入场完整快照和核对见[证据目录](../docs/workorders/evidence/task034_smtp_design_gate_2026-10-26/)。实际代码尚无SMTP或Security业务路由/页面；机器定义不等于运行实现。原474项测试不作为本轮重跑证据。

## 3. 修改落点

本轮仅更新task033接受记录、PROJECT_STATUS及本核查单/证据，不改业务规则、代码、机器契约或测试。决定后预计涉及平台配置单例存储/迁移、SMTP适配器和持久任务、管理员页面、Security消费者、API/机器契约及PG/HTTP/浏览器测试；具体实现单按决定展开。

## 4. 核查与覆盖

| ID | 规范与反例 | 本轮观察 / 实现状态 |
| --- | --- | --- |
| DG01 | 03-01 P10d列Primary/Backup、添加、删除；04-01 §2 GET/PUT单例；04-02任务对象表明确system_smtp_config稳定单例，不新增按ID路由 | 多Profile没有选择默认/启停/删除语义及对应API；真实设计冲突待决定 |
| DG02 | 03-01 P10d承诺None/Password/Token/API Key；SMTPWrite只有server/auth_type/username/secret，无服务或认证机制字段 | 同一Token/API Key配置应采用什么认证交换没有规范；不能把所有secret自动当密码或猜用户名 |
| DG03 | 04-01 §2单例默认30秒/0重试/30天/minimal；08 §5保护冻结输入/人工确认/引用依赖 | 默认及保留资格已明确，无需重开；minimal/standard输出差异和超时/重试对现有测试消费者的作用范围待后续细化，不自行扩张日志权限 |
| DG04 | 04-01测试连接/认证不发信；03-01按钮“测试发送” | P0不发送邮件已有API/09/10一致规则，后续把按钮校准为“测试连接”，不当成新的发信授权问题 |
| DG05 | 接受与授权基线、文档链接/版本、已有文件保护 | 本轮静态核对；不冒充SMTP运行覆盖 |

SMTP/Security业务成功、拒绝、失败、并发、审计回滚、撤权、修订迟到、凭据隔离及浏览器恢复测试尚未建立或执行。实施时须逐条建立需求追踪，不能用本核查替代。

## 5. 验证与审查

本轮为S1设计核查与接受记录，只做快照哈希、引用/版本、范围一致性和只读独立核查，不运行无关应用测试。使用scripts/delivery_snapshot.py保存完整未提交/未跟踪内容；无数据库或外部邮件副作用。独立审查由/root/review_smtp_gate自行阅读实际规范，最终结果及文档检查保存于证据目录；不得据此标记业务S3完成。独立核查确认DG01/02为真实缺口；文档复核发现DG03章节引用误写，已改为08 §5。引用、版本及原业务文件保留检查通过，详见checks.json。

## 6. 待人工决定

**D-SMTP-01：一套系统SMTP还是多套可切换配置？**

- A（建议）：P0一套系统SMTP，按04-01/04-02单例维护；修正P10d多实例线框，仅编辑/保存/测试。保留初始未配置状态，不新增未定义的删除语义。
- B：多套SMTP Profile；需同时决定主配置选择、启停、删除后行为及在途任务绑定，再扩充API/领域/UI。
- 影响：阻塞SMTP聚合身份、迁移/API和页面；不能擅自用单例丢弃UI承诺或凭空增加多实例产品规则。

**D-SMTP-02：首版支持哪些认证方式与服务？**

- A（建议）：首版None和Username+Password（含按密码使用的授权码）；Token/API Key暂缓，明确记录分期变更并同步规范。连接加密仍按None/SSL-TLS/STARTTLS。
- B：保留四类认证；先指定需要支持的邮件服务及其认证方式，再定义Provider/机制映射和字段约束，不能承诺任意server通用Token/API Key。
- 影响：阻塞认证校验、适配器、成功判定和验收；A改变已列功能范围，必须由用户决定，不以工程选择默认为A。

Security默认值不重开；诊断级别和消费者作用范围在恢复N4时给出具体字段/行为方案并核对现行边界。当前不擅自用诊断清理删除任务冻结快照。根据用户“遇到未明确设计”停止条件，本轮保存核查点；无独立并行业务队列需要继续，未启动Security或Construction实现。

## 7. 当前报告

M-P0-09已接受；下一阶段进入S1后遇到真实设计缺口。设计未定，代码未开始，业务自动验证未执行，业务工程未收口，M-P0-10未到。完成的是入场核查和可审阅决定材料，不能标记N4完成。保留历史验证证据和工作区。

## 8. 恢复检查点

流程v1.7。授权范围为N4下一阶段，止于里程碑或未明确设计；当前S1等待D-SMTP-01/02，S2–S7未开始。最近完成动作：M-P0-09原产物核对与接受记录、规范差异核查。当前内容快照见证据目录handoff；before保留原320文件。下一动作：收到决定后核对handoff漂移，同步批准规则，完成剩余Security可执行规格核查，再进入业务实现与需求测试。不得自动启动P1通知/真实邮件或把延期事项视为授权。


## 9. 2026-10-26人工决定与恢复

用户原话：“D-SMTP-01采用建议A，02采用B，因为大多数邮箱不支持Username+Password的模式，采用该模式将导致邮箱不可用”。D-SMTP-01已决：系统SMTP单例；D-SMTP-02方向已决：保留None/Password/Token/API Key，不能将Token/API Key延期。用户理由作为决定背景保留，不据此断言所有邮箱禁用密码类SMTP认证。

入场原handoff321文件逐SHA-256核对无漂移，before快照见[本轮证据](../docs/workorders/evidence/task034_smtp_decisions_2026-10-26/)。已同步03-01 P10d为单例，移除多配置/删除线框，测试按钮改为既定“测试连接”。API原有单例及四类枚举无需因本次决定改变；未改业务代码。

服务范围尚未指定，已询问首批需要支持的邮件服务，不重新询问A/B。可选建议组合为QQ/163/Gmail/Microsoft 365/SendGrid，或用户实际使用的服务；此组合是建议，不是批准范围。待答复后确定服务与认证机制映射、所需字段及Token生命周期方案，不自动增加OAuth注册/授权回调/刷新流程。不能仅保存Token文本就宣称完整OAuth接入可用。

官方资料核查（2026-10-26，仅文档读取，无实际邮箱连接/发信）：
- [Gmail应用专用密码](https://support.google.com/mail/answer/185833?hl=en)：符合条件时支持应用专用密码，不能把邮箱登录密码与应用凭据混为一谈。
- [Microsoft SMTP OAuth](https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth/)：SMTP OAuth认证有应用注册、令牌权限和协议要求，不能将“Token”当作通用密码别名。
- [SendGrid认证故障排查](https://help.twilio.com/articles/47401340345243)：SMTP使用固定用户名apikey与API key作为密码值；这说明API Key的协议映射依服务而异，不是排除API Key模式的理由。

当前S1：D-SMTP-01关闭，D-SMTP-02四类认证方向已确认、具体服务范围待补齐；Security执行规格仍待后续核查。S2–S7业务阶段未开始，M-P0-10未到。本轮仅决定同步及资料核查，文档验证/独立复核证据见本轮目录，不声称业务验证通过。上文等待两项A/B决定的记录为历史；恢复先核对本轮handoff，再按服务答复继续，不重复请求已批准事项。


## 10. 首批服务确认与OAuth生命周期方案

用户已答复首批支持“QQ邮箱、163邮箱、Gmail、Microsoft 365、SendGrid”。该名单已确认，不再要求重新选择服务。第9节“服务待指定”为本轮较早检查点；协议适配与本节Token生命周期尚不等于已实现。

| 服务 | 认证映射 / 预期表单 | 依据与限制 |
| --- | --- | --- |
| QQ邮箱 | Password类，字段显示“邮箱账号＋授权码”，避免引导输入登录密码 | [QQ官方帮助](https://help.mail.qq.com/)列出授权码用于第三方POP/IMAP/SMTP；具体连接参数在适配测试前核对 |
| 163邮箱 | 拟Password类，字段显示“邮箱账号＋客户端授权码” | 网易帮助站本轮无法读取，服务方细节仍待核验，不把搜索摘要当已验证适配；不影响用户已选支持范围 |
| Gmail | Token映射SASL XOAUTH2；符合账号条件时也可用Password类应用专用密码 | [Google XOAUTH2](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol)及第9节官方应用密码资料 |
| Microsoft 365 | Token映射SASL XOAUTH2，须满足租户SMTP AUTH及授权权限 | 第9节Microsoft官方文档；不承诺绕过租户禁用策略 |
| SendGrid | API Key映射SMTP AUTH，固定用户名apikey，密钥为API key | [SendGrid SMTP集成](https://www.twilio.com/docs/sendgrid/for-developers/sending-email/integrating-with-the-smtp-api)，smtp.sendgrid.net；不新增HTTP发信实现 |

None保留为现有无认证SMTP模式，不声称上述五种公共服务均支持无认证。产品认证类型和SMTP线上认证机制分开：授权码可能在密码位置发送，API Key也可能通过固定用户名＋密码位置发送；“四类认证”不表示每个服务都支持任意四类组合。

**D-SMTP-03：Gmail/Microsoft 365的Token由管理员手动维护，还是由应用完成授权及刷新？**

证据：现有SMTPWrite只有一个secret，P10d仅Token输入；未定义OAuth应用注册配置、回调、refresh token和过期处理。Google的[Web Server OAuth流程](https://developers.google.com/identity/protocols/oauth2/web-server)及Microsoft文档明确授权与刷新步骤。直接支持XOAUTH2协议不能自动解决令牌获取/续期，默默把此能力记作完整OAuth支持不准确。

- A（建议，面向长期可用）：应用管理OAuth授权及刷新。部署方准备Google/Microsoft OAuth应用；管理员配置client ID及必要client secret/tenant，然后显式连接发件账号。应用处理授权回调、加密保存刷新凭据、测试连接前按需刷新；撤销/过期不可刷新时明确要求重新授权，不切换账号或认证方式。需要增加管理配置字段、授权/回调接口和连接/重新授权交互。此建议包含授权交互及凭据生命周期的产品扩展，尚未批准；不自动注册外部应用、不索取真实密钥、不触发真实授权或发信。Google SMTP权限范围由服务方规定，授权页应明确展示实际请求范围；应用自身仅执行SMTP连接/认证测试。
- B：仅支持管理员提供现成access token，使用XOAUTH2；过期后失败并要求手动更新。不实现OAuth登录、获取或自动刷新，可完成当前输入字段所表达的能力，但需要管理员持续维护短期令牌，不能称为免维护连接。

仅阻塞Gmail/Microsoft 365的完整凭据生命周期、相应字段/UI及验收，SMTP单例、QQ/163授权码、SendGrid映射和密钥隔离不因该问题技术性阻塞。按用户“遇到未明确设计”边界，本轮保存已完成的决定同步与具体方案，不另行启动平行业务实现。Security执行规格仍须在后续S1明确；已有默认及保留保护继续有效。M-P0-10未到。

本轮文档及第10节增量已由/root/review_smtp_decisions独立只读核查通过，无阻断意见；引用/版本与321文件原产物保护检查通过。证据见本轮checks.json及independent-review.json，最终handoff保留321文件完整快照。本结论仅覆盖决定记录与方案，不是业务S3或M-P0-10通过。


## 11. D-SMTP-03接受与OAuth执行边界

2026-10-26用户在D-SMTP-03选择题后明确回复“采用A”。自动授权/刷新方向已批准；D-SMTP-01/02/03及五服务名单均不再请求选择。入场上一轮handoff321文件逐SHA-256无漂移；[本轮证据](../docs/workorders/evidence/task034_oauth_accepted_2026-10-26/)保存before及后续handoff，保留全部原工作区。

已同步P10d及04-01：OAuth应用配置、管理员连接/重新授权、回调绑定与重放拒绝、加密Token保管、并发刷新/轮换提交、权限和配置变更后迟到响应拒绝、失败恢复。授权成功不替代连接测试成功，不启动P1发信；真实外部注册/授权未执行。Google/Microsoft官方授权和刷新文档本轮重新核查，来源沿第9/10节。

实现需补的验收场景：授权成功/拒绝/响应丢失、错误/重复/过期state、PKCE失败、回调切号/撤权/配置变更、缺刷新凭据、刷新轮换和确定性交错、刷新失败需重授权、无明文进入API/日志/快照、保存不外发、授权不自动标记测试成功、SMTP不发送MAIL/RCPT/DATA。测试须使用隔离PG和mock OAuth/SMTP；本轮尚未建立或执行，不将设计条目记为通过。

接续核查已在task034 DG03登记的Security执行语义，不重新讨论已批准OAuth方向。现行04-04允许个人LLM timeout_seconds为1–120秒且部署只能收紧，04-01的系统默认为30秒/0次重试，但尚未规定系统连接测试参数覆盖哪些动作、如何与个人超时组合。现有LLM/Source Worker均将未知结果终结，不自动重发；任何扩大自动重试的实现须核对是否改变显式调用及计费语义。当前仍在S1；代码、机器契约与业务测试未改，M-P0-10未到。


第11节核查结论：独立审查/root/review_security_scope确认DG03可在04-04超时收紧、P0未知结果禁止重发及08隐私边界内工程细化，无新增人工决定。已写入04-01：配置测试预算取较小值、只对可证明未提交的连接失败重试、固定诊断白名单和保护性诊断清理。SMTP决定同步及S1核查完成，承接[task035](035-smtp-security-runtime.md)实施，不再以Security技术细节设置审批门禁。原S1等待状态为历史；业务S2–S7由task035记录。
