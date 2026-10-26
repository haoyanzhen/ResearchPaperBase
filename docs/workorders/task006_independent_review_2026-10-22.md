# Task006 公共错误契约独立审核

文档版本：v1.0
更新日期：2026-10-22

## 结论与范围

用户要求派subagent审核task006，重点安全边界、恢复提示及兼容差异。三位subagent分别只读检查安全、恢复和兼容，主代理复核并合并为 **3项P2待修问题**。本次未修改契约、检查器或测试，不记人工接受；原自动测试通过不代表这些遗漏已经覆盖。

受审内容为当前工作树（含未跟踪文件），不是只审HEAD。开始审核时[原交付清单](evidence/a04_2026-10-22/delivery-sha256.json)的25项摘要全部匹配；基线来自7ba2a2c638500eaa43f2137d16a6a0686b663630，与原交付保存的JSON相同。本次随后更新PROJECT_STATUS登记审核结果，因此该状态文件与历史交付摘要发生预期变化；原证据不刷新、不冒充新批准基线。

## 发现

### R01 / P2：回放恢复目标未完整转写

位置：[公共错误schema](../../contracts/p0.openapi.json) `ErrorStateEventReplayUnavailable.details`（审核时9767行）及`ErrorTaskDetails.status_url`（8380行）。[04-02 §3.2](../design/04-02_transport_task_file_contracts.md#32-回放和快照恢复)要求回放窗口过期的安全details包含status_url，§2.1定义任务状态URL为 `/api/v1/tasks/{task_id}`。

实际验证：以下错误通过PublicError；将details替换为 `{"status_url":"/api/v1/me"}` 或任务events地址也通过。

```json
{"code":"STATE_EVENT_REPLAY_UNAVAILABLE","category":"state","message":"事件回放窗口已过","retryable":false,"details":null,"recovery":{"action":"reload_task","label":"重新读取状态"}}
```

影响：缺失或错误恢复目标仍被契约接受，消费者无法依约定位状态快照。测试把全部42变体空details作为正例，掩盖具体错误的必填要求。建议该变体要求非空任务详情、任务状态URL使用具名路径约束，并增加空值/错误端点反例。URL归属与权限仍是运行义务，路径约束不代替鉴权。

### R02 / P2：已受理Task/SSE仍可声明命令未受理

位置：[TaskError](../../contracts/p0.openapi.json)（11503行）。[04 §5.1](../design/04_api_contracts.md#51-公共错误的安全投影与恢复含义a04)把not_accepted定义为命令未受理；TaskError自身说明是任务受理后的错误，却仅限制retryable和recovery，未限制该outcome。

```json
{"code":"STORAGE_INTERNAL_FAILURE","category":"storage","message":"操作未完成","retryable":false,"details":{"outcome":"not_accepted"},"recovery":null}
```

以上对象通过TaskError，包装为 `{"error":...}` 后也通过ErrorPayload。主代理另用PROVIDER_UNAVAILABLE复现相同结果。影响：同一投影同时声称存在已受理Task与原命令未受理，混淆结果核查和恢复判断。建议TaskError排除该命令级outcome；若未来表达Provider子调用未接收，须明确独立作用域，不能混用现有含义。当前没有证明它直接绕过retryable限制，问题是跨载体语义不一致。

### R03 / P2：HTTP状态元数据与响应信封可漂移而不被发现

位置：[检查器](../../scripts/check_api_contracts.py)109–112行及[测试](../../scripts/tests/test_public_errors.py)40行附近。检查器只确认PublicError{status}存在并引用同名ErrorEnvelope{status}，没有确认当前变体确实属于该信封。

内存变异：把ErrorPermissionResourceUnavailable.x-http-status由404改为500，check()仍通过。兼容专项subagent针对该内存变异执行全部23项测试，仍全部通过；主代理独立复现check()通过。建议按状态比较变体集合与信封成员，并增加错误映射变异回归。当前正式JSON映射正确；这是新增静态防漂移及测试遗漏，不是当前已发生的错误HTTP返回。

## 已核对与未列为缺陷的事项

- 原80个schema、请求/成功响应及权限/版本绑定声明均保持；新增79个schema。
- 兼容门禁83项确为82操作x-errors变更和1项SSE映射新增；新增responses是新增组件，原审核包已独立评估，不算漏审。
- 固定404消息、空details/recovery及具名字段白名单有效；未知结果禁止直接重试、禁止换键/重跑动作没有发现直接绕过。
- 自由文本脱敏、资源引用鉴权、动作资格、真实提交/并发和确认生命周期已明确排除运行验证，不将这些排除项伪报成本次实现缺陷。
- 逐端点错误响应绑定、完整Task/SSE仍明确未覆盖，没有发现误报完整HTTP或业务验收通过。

## 执行与后续

安全与恢复subagent分别复跑新增8个测试方法，全部通过；兼容subagent完成内存变异的23测试检查。主代理使用 `/tmp/rpb-a04-contract/bin/python` 导入现有valid/check，对R01/R02/R03反例逐项复现。未访问业务数据库、Provider或邮件服务；所有变异只在内存，未写入受审契约。

修复需补相应回归，重新运行原15项与新增契约测试、结构/覆盖检查及旧基线兼容审查，再记录新交付摘要。此审核仅登记问题，不自动启动其他任务；人工审核者、接受范围及结论仍待填写。

交付时并行变化说明：结束核对发现task006及PROJECT_STATUS另有覆盖补齐记录更新，状态新增31项测试声明及task006_coverage_closure链接（核对时目标尚不存在）；本审核不验证该并行声明。上述测试数量针对本审核开始时快照，3项问题的schema/检查器位置仍未变化。未覆盖或回滚并行内容，后续复审须绑定更新后的测试与证据。
