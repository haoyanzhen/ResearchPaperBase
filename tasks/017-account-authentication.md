# Task017：账号注册登录与服务端会话

文档版本：v1.0
更新日期：2026-10-25

## 1. 授权、目标和依赖

沿task016第8节批次授权。2026-10-25用户在本聊天明确选择身份规则A，现行01 v1.55/08 v1.10已记录；本片按strip+Unicode casefold生成登录键，保留显示原文，不做NFKC兼容折叠。使用已实现Account存储，不接入旧业务数据库。目标：真实持久化注册、两种标识登录、轮换Cookie/CSRF、读取自己与退出；禁用立即拒绝。所属M-P0-01，需继续Project创建闭环后提交验收。

## 2. 规格与实现边界

依据01 FR-001/005首位注册、02 Account、04 §4/7及04-01 §2、07 Session事实、08认证。注册不自动登录；返回UserView，用户显式登录。首位管理员与跨标识唯一在同一账号治理事务锁裁决；未来邮箱/管理员治理必须共用该边界。API阻塞存储调用使用同步路由线程。密码采用随机盐scrypt；会话及CSRF仅存摘要，登录撤销旧会话并生成新随机凭据。Cookie固定rpb_session、HttpOnly、SameSite=Lax、Path=/，仅显式loopback HTTP允许非Secure。

会话有效期属于本片技术默认参数，测试使用24小时、预会话30分钟；不是数据清理政策，不自动删除历史记录。已过期/撤销不能恢复。所有写请求校验精确Origin与会话CSRF，认证重新检查enabled。公开错误不返回请求体、密码、SQL或路径；no-store。无生产迁移或部署、不开放密码找回/PATCH me/管理员治理。

## 3. 文件落点

应用ports/service；adapter AccountStore及冻结0003会话迁移；API认证路由与显式装配；真实隔离PG测试。默认骨架入口继续无库，不从环境偷偷接入业务配置。API演示装配与后续临时闭环运行器显式绑定同一隔离目标。

## 4. 需求追踪（AU）

| ID | 可观察场景及禁止副作用 |
| --- | --- |
| AU01 | 注册成功，仅哈希；返回不含hash/key；同账号两个标识相同允许；首位管理员 |
| AU02 | 去空格大小写、用户名/邮箱各自及交叉重复409，失败无多余账户；独立并发注册只有一位首位管理员 |
| AU03 | 两种标识登录；错密码/不存在拒绝且不新建已认证会话；盐随机、验证失败安全 |
| AU04 | Cookie安全标志、登录轮换旧token失效、CSRF刷新；错误Origin/缺失或错CSRF拒绝无写入 |
| AU05 | me本人、匿名拒绝；禁用后当前会话与登录均拒绝；退出撤销，仅当前会话；过期拒绝 |
| AU06 | 字段/额外字段/内容类型拒绝；错误与成功no-store；密码不出错误日志/响应；body限制 |
| AU07 | 0003升级、重复升级、metadata一致、故障回滚、非空降级拒绝；既有Account/Project回归不弱化 |
| AU08 | 事务失败无部分注册/轮换；明确隔离清理，不使用外部服务 |

## 5. 验证与证据

待执行；证据根 `docs/workorders/evidence/task017_auth_2026-10-25/`。真实PG隔离入口与task016相同。协议schema、实际HTTP响应和持久事实联合断言，不以mock替代业务链。

## 6. 人工节点

D-016-01已决定，不重问。没有新的业务决策；M-P0-01未到。工程通过不等于人工接受。仅技术参数可配置，无清理/保留承诺。

## 7. 报告

待工程收口，当前不声称账号完整业务（治理/资料修改仍未实现）。

## 8. 检查点

流程v1.7；S1完成、S2进行中，S3–S7待执行。批次及里程碑见task016。上一片正在独立修复复审；本片不覆盖其历史基线。下一步实现AU01–08并绑定新快照审查。

密码参数采用scrypt N=32768/r=8/p=3、16字节随机盐、32字节输出，参考[OWASP官方密码存储指南](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)。首轮集成93通过/1失败：并发测试观察连接复用PG统计快照导致看不到新连接；补pg_stat_clear_snapshot后仍保留双请求真实等待断言，不以sleep替代屏障。

### S2/S3修复记录

初审 `/root/project_storage_review` 三项P2：R1禁用拒绝未持久撤销会话，R2注册201缺Location，R3HTTP时间非Z。现已修复：失败事务退出后另事务撤销当前token（不反转治理/session锁序）；Location=/api/v1/me，须以新账号登录后读取；公共投影输出UTC Z。新增禁用后重新启用、头与实际时间/schema断言。jsonschema仅为dev依赖，所有本片已知HTTP操作成功及具名错误变体逐响应验证。补重复logout旧Cookie安全401、跨session CSRF、缺Origin且正确CSRF、Session全部非空/expiry/FK及writer/down真实阻塞交错。

最终候选integration-contract.log：106项通过、实例停止/根清理true。此前103项证据不冒充最新测试。check初次strict metadata显式导出错误已修复，check-fixed通过；新增最后测试后重新执行final检查及构建。S4逐AU复核无已知必需缺项，S5保留冻结迁移/独立事务回归，暂不做无收益重构。S6待固定修复快照独立复审及最终检查。


S6复审追加R1b：登录禁用B时不应撤销当前有效A会话。错误内部携带被禁用account_id，拒绝后撤销同时匹配token及该account_id；不对外输出该内部事实。新增A/B回归保留原禁用复活负例。目录自审发现新建account与工程基线account_config不一致，已把本轮两个应用文件放入既有account_config/application，删除本轮空package源码；业务行为不变，纳入最终复审。


### S7最终交接

S1–S7工程收口。107项真实PG通过，独立 `/root/project_storage_review` 复审R1/R1b/R2/R3全部闭合，无剩余阻断。独立run_id `rpb_test_14435076d2f94b6693556b9f28216a17`，实例停止/目录清理true；s3-fix2摘要 `549a7b2db5e7c4d45bb3bd518d97f5a68397b36bfb342a9d8a3b235b57eeb46d`，前后无漂移。check-final2通过ruff/format/mypy、82后端/66契约/3前端；build-final通过；document-checks无失效链接。S4逐AU复核及补测完成，S5无需额外抽象；S6修复、归位后独立107重跑及全门禁完成。

当前设计/代码/自动验证/工程收口均限定完成；M-P0-01未触发。最终delivery/receipt只追加任务/项目状态和下一片规范记录，源码与独立受审一致。保留失败及反例证据，不把早先通过计数冒充最终覆盖。接续[task018](018-project-create-runtime.md)和浏览器闭环；无需逐片人工接受。HTTP测试由显式工厂启动，目前默认命令仍为无库骨架；业务演示入口将在闭环切片交付。
