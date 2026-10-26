# Task025：LLM决定同步与Open WebUI参数方案调研

文档版本：v1.0
更新日期：2026-10-26

## 1. 授权与结论边界

用户决定：“前两项采用建议，同步设计。第三项原则上应当选B，可以参考已有的open-webui项目的实现，先查找一下解决方案”。D-LLM-01第1项取消P0个人/系统LLM启停开关，第2项逐模型测试成功后可选，现已作为已决规则同步01/02/03/04/05/07/08/09；数据源启停及已启动任务换key规则保留。第3项采用扩展方向B，以下具体参数方案为调研建议，尚非用户逐项批准的业务规则。此次不实施配置业务或修改机器schema，不把只含两项参数的当前schema冒充扩展完成。

入场与task025上一轮delivery253文件摘要完全一致（检查见本轮evidence）。本轮证据目录：`evidence/task025_llm_decisions_2026-10-26/`；before保存全部未提交和未跟踪内容。M-P0-04接受不变，M-P0-05未到。

## 2. 固定来源与实际观察

源码基线为Open WebUI main在本次读取时的提交[33c1978d5bad52a31df75ea55143025dfad18d16](https://github.com/open-webui/open-webui/commit/33c1978d5bad52a31df75ea55143025dfad18d16)，提交说明0.12.4，时间2026-10-25。通过GitHub连接器读取并保存相关文件，未安装、运行或复制到业务源码。在线文档读取于2026-10-26，文档会继续变化；实现结论优先绑定上述提交。

| 一手来源 | 核查到的做法 | 对本项目的参考意义 |
| --- | --- | --- |
| [AdvancedParams.svelte](https://github.com/open-webui/open-webui/blob/33c1978d5bad52a31df75ea55143025dfad18d16/src/lib/components/chat/Settings/Advanced/AdvancedParams.svelte) | 常用参数独立控件，覆盖采样、长度、推理和Ollama专属选项，另嵌CustomParams | 可以提供常用表单及高级入口；出现控件不证明任意模型支持 |
| [CustomParams.svelte](https://github.com/open-webui/open-webui/blob/33c1978d5bad52a31df75ea55143025dfad18d16/src/lib/components/chat/Settings/Advanced/CustomParams.svelte) | 动态键值行、名称/值建议、添加/删除；注释明确支持取决于Provider和模型 | 借鉴编辑体验，不照搬工具、存储、路由类参数的权限 |
| [payload.py](https://github.com/open-webui/open-webui/blob/33c1978d5bad52a31df75ea55143025dfad18d16/backend/open_webui/utils/payload.py) | 自定义值尝试JSON解析，失败保留字符串；剥离WebUI内部选项；类型转换及自定义参数合并；OpenAI/Ollama分支处理，Ollama使用options并映射token字段 | 参数编辑、规范化与Provider请求组装应分层；必须明确类型、合并及字段落点 |
| [openai.py](https://github.com/open-webui/open-webui/blob/33c1978d5bad52a31df75ea55143025dfad18d16/backend/open_webui/routers/openai.py) | 兼容不同token名称，Responses转换移除部分Chat专属参数；HTTP timeout由客户端配置处理 | 不把各协议当成一套通用参数，也不把timeout当生成请求字段 |
| [官方参数层级说明](https://docs.openwebui.com/features/chat-conversations/chat-features/chat-params/) | 模型、账号、会话存在多层参数优先级 | 本项目先沿用选定配置的参数来源，不顺带引入新的会话/账号覆盖产品规则 |

补充核对[Claude Messages参数](https://platform.claude.com/docs/en/api/typescript/messages/create)、[Claude thinking](https://platform.claude.com/docs/en/build-with-claude/thinking)、[Gemini GenerationConfig](https://ai.google.dev/api/generate-content)、[Gemini排错](https://ai.google.dev/gemini-api/docs/troubleshooting)：参数支持与模型和API版本相关，尤其采样与推理参数会有不支持/忽略/组合限制。因此不能仅按Provider名称宣称支持，也不能把Open WebUI的OpenAI/Ollama路径视为本项目Anthropic/Gemini原生适配已完成。

## 3. 建议落地方案B

以下是本项目方案推导，不是对Open WebUI行为的逐字移植。

### 3.1 三类参数与编辑方式

| 类别 | 建议内容 | 保存与发送 |
| --- | --- | --- |
| 常用生成参数 | temperature、top_p、max_output_tokens、stop、seed；frequency_penalty/presence_penalty及top_k按能力展示 | 类型化字段；未设置就省略，0/false不得被当成未设置；不为所有模型硬塞共同默认值 |
| Provider扩展 | custom_params键值编辑，允许number/boolean/string/array/object；例如不同协议的推理配置 | 明确JSON类型或文本，非法JSON明确报错；只允许适配器登记的生成参数路径，不直接展开任意请求对象 |
| 调用控制 | timeout_seconds等客户端选项 | 与生成参数分开保存、校验和快照；受部署限制约束，仅作用于HTTP客户端，不转发为模型参数，不扩展网络目标 |

建议“常用 / 高级”两个区块，显示当前协议/模型适用性、未设置及不支持原因。新增Provider参数通过版本化适配器描述登记，不要求修改前端一组硬编码控件；未知模型可保存结构合法配置，展示能力待验证，但不能承诺任意扩展受支持。

### 3.2 能力描述与协议映射

建议能力键为adapter协议＋API版本＋model_id（包含显式匹配规则和未知能力状态），描述字段类型、范围、枚举、互斥依赖、默认策略、实际发送路径及受保护字段。发现模型列表仅提供身份，不假设其返回完整参数schema；已知能力来自维护的协议描述，最终由显式测试/实际调用反馈验证。

| 协议 | 长度及扩展示例（拟映射，非已实现支持表） |
| --- | --- |
| OpenAI Chat兼容 | max_output_tokens规范名按能力转为max_completion_tokens或max_tokens；推理参数依具体协议能力发送 |
| OpenAI Responses | max_output_tokens；推理类对象按Responses能力；Chat专属字段不应被静默丢弃 |
| Anthropic Messages | max_tokens；thinking等按所选API版本/模型登记；不假定temperature/top_p在所有版本可用 |
| Gemini | 对支持generateContent的协议映射到generationConfig.maxOutputTokens及该协议定义字段；其他接口单独适配，禁止仅换字段名假称全部支持 |
| DeepSeek / custom | 按已实现且明确选择的兼容协议处理；自定义base URL不意味着接受任意schema；专属字段须登记 |

Ollama源码仅作为映射参考；本轮不因为参考工程支持它就新增本项目Provider承诺。API协议选择字段仍需在后续机器转写时明确。

### 3.3 合并、校验和业务边界

建议只解析当前显式选择的配置参数；同一目标路径若被常用字段和custom_params同时提供，拒绝并提示冲突，不用顺序悄悄覆盖。不同token别名视作同一目标冲突。嵌套对象使用明确的叶路径合并规则，数组整体替换；未设置/null清除/空对象的PATCH含义须由后续schema统一表达，不沿用隐式深合并猜测。

custom_params建议采用受支持生成字段允许列表：禁止覆盖model、messages/input/system/instructions、tools/tool_choice、stream、认证头/密钥、base URL、账户/Project标识、外部路由、回调/文件目标等应用所有字段；不能绕过当前模型绑定、工具授权和资料读取策略。模型输出格式若由具名用例拥有，也不能被用户扩展覆盖。扩展JSON本身不提供secret通道。

建议后端验证有限数值、类型、范围、组合、JSON深度/字节上限与重复键；不支持的显式参数给出字段级错误，不静默删除以获得请求成功。先结构校验保存，已知不支持字段立即拒绝；未知模型的语义能力标待验证。错误不得带密钥或原始私人请求内容。

### 3.4 与已决定的逐模型测试衔接

测试固定待测模型及当前配置/凭据修订，使用非业务测试文本；测试结果展示实际测试的参数摘要及范围。高级参数修改后需新测试，旧/迟到成功不能恢复可用性。最小测试若为了成本/时长覆盖输出上限，应显式展示覆盖，不能据此声称原始大上限或其他任务能力已验证；具体测试预算和覆盖规则在实施前收敛。新任务固定解析后的参数与适配版本以便追溯；当前配置编辑不重写既有任务快照，凭据仍按08 §12.3解析。

### 3.5 实施与验证顺序

1. 收敛扩展允许列表、协议/模型能力描述、测试参数覆盖规则，更新权威设计；转写ModelParameters/LLM测试/结果/运行快照机器结构，不并行维护第二份字段来源。
2. 以纯参数解析器完成类型、范围、零值、互斥、同义字段冲突、嵌套输入和禁止覆盖测试，逐协议断言实际出站请求；配置修订/异步迟到测试用真实隔离数据库。
3. 建立常用表单和高级键值编辑，覆盖添加/清除、类型纠正、实例切换草稿、失败不丢输入、能力提示及显式费用提示。
4. Provider默认mock，仅验证适配与应用行为；如需真实Provider可用性证据，另指定目标及费用授权。不能从静态源码阅读推断生产兼容性。

本轮建议选择“受控custom_params＋能力描述＋客户端控制分离”，在B方向提供可扩展性，同时遵守项目已有边界。参数列表、上限数值及测试覆盖细节仍是方案待收敛项，不把“原则上B”记录为全部细节已获接受。

## 4. 本轮检查与状态

仅设计/调研，无业务代码、迁移、依赖或机器契约变更；不运行无关业务测试。检查范围为与入场快照的增量、文档版本/日期/引用、已决规则的一致性及来源可追溯性。独立审查与最终证据存于本轮evidence；具体结论由最终记录追加。本轮文档交付与task025业务实现阶段分别记录。

最终结果：10份既有文档递增次版本，新增本报告；本地引用、差异范围与253文件入场基线核对通过。独立审查者`/root/llm_decision_review`发现R1：全局替换误改P06c/P10c数据源线框，已逐章节恢复并独立确认与入场完全一致，复审无剩余阻断项。文档切片完成范围核对、自验、独立审查、覆盖复核、无需额外简化及最终交接；业务阶段仍按task025第9节停在参数方案收敛，不宣称配置实现或里程碑交付。检查见documentation-check.json，源码依据见sources.json，最终内容快照为delivery。
