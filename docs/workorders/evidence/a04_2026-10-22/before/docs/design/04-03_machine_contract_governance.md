# API 附录：机器契约、覆盖与变更规则

文档版本：v1.1
更新日期：2026-10-21
适用项目大版本：v1

## 1. 权威与覆盖边界

01/02 决定业务含义、权限和分期；04/04-01/04-02 维护跨字段、执行与传输语义。[OpenAPI 3.1 JSON](../../contracts/p0.openapi.json)只对其实际包含的具名 schema、请求和成功响应字段提供机器维护来源；没有 schema 的操作继续由 Markdown 维护，不能据此生成宽松 `object` 代用品。结构与业务规则冲突时停止依赖该冲突的代码生成并修正规范，不修改业务去迎合 schema。

本次机器覆盖为 **42 个操作的请求/成功响应结构、另40个操作的仅请求结构、80 个 schema、4 类 SSE payload**，全部为局部覆盖，**没有任何操作被宣称为完整 HTTP 契约或运行验收通过**。公共错误 details/recovery 尚未闭合；SSE 的 payload 验证不等于完整 event/流验证。SDK、服务端模型和路由代码尚未生成。

[覆盖清单](../../contracts/p0.coverage.json)保留 04-01 所有操作表行及 04-01/04-02 正文具名 HTTP 路由的源签名。一个表行可含多个方法和路径，因此源行数不是端点数。校验器重新抽取源签名并逐项比较，新增、删除或变更操作行后必须显式更新覆盖，不能悄悄遗漏。三份04规范文件另保留完整SHA-256审核摘要（保守地包含历史及元信息）；任意正文变更会要求重新审查并同步摘要。它检测漂移，不证明Markdown和schema语义等价；不得自动刷新摘要后跳过审查。`typed_operations` 列出请求/成功响应局部覆盖，`request_only_operations` 列出只校验请求的操作；后者没有成功响应schema，不能从缺失推断无正文。`row_coverage` 为每条源行分别列出操作覆盖与剩余项。两类清单列出可消费的机器操作；其余源行不等于已经实现或完成转写。

| 缺项类别 | 已识别范围 | 后续动作 |
| --- | --- | --- |
| 已定但尚未转写 | 其余配置测试、Construction/Research/Review、知识资产、文件、完整 SSE/累计输出等结构 | 按领域规则机械转写，不能视为新的业务待决或分期变更 |
| 设计字段尚未闭合 | Error.details/recovery 安全字段词表；Task 目标类型完整枚举、waiting_items 引用；ConfirmationPreview.affected_items/retained_items | 定义具名字段及允许变体，关联对应用例后再转写；不要猜业务默认 |
| 实现验证 | 权限、跨 Project 防枚举、Origin/CSRF、状态、修订、确认、去重、原子快照、模型能力范围、SMTP认证类型字段组合、Workspace草稿object/part唯一性等 | 后续实际服务、隔离存储和端到端验收；schema 不能替代 |

可重定位的本轮Agent限定核对基线见[A01–A03记录](../workorders/a01_a03_design_closure_2026-10-21.md)。它记录Git对象与内容摘要，不提升机器覆盖、不代表人类批准；后续兼容检查从指定Git对象提取旧JSON，不能拿本次修改后的JSON自比。

## 2. 单一维护与操作身份

- 已覆盖 schema 的字段、必填、可空、枚举及长度只修改 JSON；Markdown 对相应结构保留 schema 名、语义及链接，不再人工维护另一份完整字段副本。新增未覆盖结构暂留 Markdown，迁入时同批移除重复字段定义。
- `operationId` 沿用既有具名用例 ID；既有 `Admin.ManageSystemLLM` / `Admin.ManageSystemSources` 为多端点用例组，机器 ID 添加 `.List/.Create/.Read/.Update/.Delete` 后缀，`x-use-case` 仍引用原用例组。这是协议身份细分，不新增业务操作；已发布身份不得因重命名代码函数而改变。
- JSON 中请求拒绝未知字段；响应 schema 用于检查服务端是否输出约定字段。客户端仍须按04忽略未知只读响应字段，不把服务端验证器当作拒收兼容新增字段的客户端策略。
- OpenAPI 的 defaults 仅为创建约定；PATCH 不应用创建默认值。模型温度的允许区间取决于能力，schema 的 number 不能证明参数可执行。
- 对象权限、修订来源和版本绑定继续引用业务规则；普通配置/Project操作标记 `not-applicable`；Research/Review既有对象操作标记 `bound-object`，Review创建标记 `explicit-or-default-at-creation`。这只是语义标注，schema不证明绑定正确。
- 本批确定同源 Cookie 的 wire 名为 `rpb_session`，只是认证传输字段的工程细化；安全属性及会话轮换仍由04规定，不允许通过名字改变权限范围。

## 3. 兼容性和审查

每次 PR 对比上一份已审查 JSON，而不是和本次生成结果自比。新增独立操作/schema 可以通过结构兼容门禁；任何已有操作、组件、schema、状态码、安全规则、SSE 映射发生变化，保守检查都返回非零，要求定向审查。该门禁不声称判定了所有破坏性变化，也不自动批准可选字段增加。

审查至少区分请求与响应方向：请求新增必填/收窄取值、响应删除字段/扩大枚举、语义默认值变化、错误码变化、operationId变化、权限/版本绑定变化、幂等和事件恢复变化均须评估。可选只读字段增加在确认客户端兼容后可接受；改变业务语义、权限、人工保护、版本绑定或分期仍按 AGENTS 请求人工裁决。批准后更新受审基线并记录理由，不能通过忽略检查项或抹去基线绕过。

结构检查只覆盖显式编码的内容。对 Markdown 中默认版本、允许状态、错误安全性等语义的变更，即便机器 diff 没有变化，仍必须评估相关测试和兼容性。

## 4. 可运行入口与证据边界

仅需独立 Python 环境，不加载业务数据库、应用依赖或外部 Provider：

```sh
python3 -m venv /tmp/rpb-contract-check
/tmp/rpb-contract-check/bin/python -m pip install -r contracts/requirements.txt
/tmp/rpb-contract-check/bin/python scripts/check_api_contracts.py
/tmp/rpb-contract-check/bin/python -m unittest discover -s scripts/tests -p 'test_api_contracts.py' -v
/tmp/rpb-contract-check/bin/python scripts/check_api_contracts.py --baseline /absolute/path/to/reviewed-p0.openapi.json
```

验证器执行 OpenAPI 3.1 结构校验、JSON Schema 2020-12 定义校验、本地 `$ref`、操作唯一身份、覆盖漂移、P0/权限声明、CSRF/幂等头和路径参数检查。单元测试包含未知写字段、null、修订缺失、密钥clear/set、格式、终态事件、响应缺项、权限/枚举/字段/操作删除和覆盖漂移负例。

2026-10-19 已执行前三类校验及15项测试；compatibility 的正负例由测试执行。没有既有机器基线，不能声称完成历史版本兼容验收。未执行应用、数据库、真实Provider、SSE回放或端到端验收。依赖固定于独立 requirements，不属于新应用安装入口。

本次修订 v1.1（2026-10-21）：登记精确基线与审查层级，现有JSON和覆盖指纹未修改。
