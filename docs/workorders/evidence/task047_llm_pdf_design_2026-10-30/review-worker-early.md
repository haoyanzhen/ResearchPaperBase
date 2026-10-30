# task047 Worker/容量边界早审

日期：2026-10-30
版本：v1.0

只读局部 S3 早审，非完整阶段通过。依据主代理转达的 D-PDF-04 用户选择（本引擎未填输出上限时默认4096），审查容量规划、四协议适配、真实持久化 Worker、prepared_document 复用及等待投影。任务顶部/状态当时仍保留 D04 待答复的旧检查点；按主代理明确本轮授权继续，不能把旧文字当成新实现已验收。

## 发现

P2：组预算在 cleanup 阶段耗尽时，已实际派发的当前来源被标为 not_attempted。基线 Worker f15336924a4585a6feccff4876a8017ec08ac5b1a8a8afa22ef96a1bc96d032a 的 run_once group_exhausted 分支直接 finish_group(blocked=True)，没有追加当前来源的 budget_exhausted 诊断；paper_processing.commit_result 从 diagnostics 推导 failed_sources，因而丢失真实尝试事实。需求依据：task047 第3节预算终态段要求区分已失败来源与未尝试/预算阻断来源，以及固定来源链的实际结果。

独立反例 review_worker_probe.py：100行文本，完成一次模型批次并持久保存reply/计数后，将持久组seconds设为已耗尽，执行下一次 Worker；当前源应 failed，实际 not_attempted，diagnostics=[]。这是受控持久预算边界注入，不声称实测耗费240秒。review-worker1 真实exit1、1条失败，日志/JUnit/run/summary齐全。隔离PG日志确认server_stopped=true、root_removed=true。未观察到预算耗尽后绕道摘要成功。建议只为实际已尝试且未完成的当前源记 budget_exhausted，保留后续未尝试源状态。已通知主代理修复，本文尚未宣称修复通过。

## 已核对边界

- effective_config 深拷贝原配置，仅缺省补4096，显式输出和已支持别名保留；容量计划同时预留输入、输出和framing，连续完整行分批，并检查响应建议体预算；不会静默截断原文。此为保守字节估算，不是Provider真实tokenizer或费用保证。
- 原始PDF与原始提取文本作为独立对象保留；整理结果另建文本对象，既有PDF对象的分类/文件修订复用，不直接覆盖原文。
- waiting_classification 属于busy，等待期间不签发处理确认；确认分类后原作业继续，后续读/派发/结果/提交分别核当前资格与分类修订。
- reservation先持久后外呼；running租约过期转未知结果失败，不重发原请求；迟到结果受状态、attempt、lease检查。PL01–04现有用例已阅读，但本轮未重复执行它们，不能以阅读替代新的全面验证。
- 当前 reconstructed 输出越200000字符已捕获 CleanupInvalid 并按来源失败处理，早期未捕获风险不再适用于本次Worker基线。

## 执行证据与限制

独立 review-worker-unit1：容量+Provider单元47/47，exit0；两次运行均实际调用scripts/delivery_summary.py，完整产物位于本报告同目录。review-worker1-artifacts.json绑定红测前基线，review-worker-current-artifacts.json记录结束快照。读取使用独立review-worker-ledger.json，恢复context为review-worker-20261030-r2；按bootstrap/entry、DELIVERY_TOOLS第5节定向读取。工具entry不支持ledger参数的失败、少数越界read失败均未被当作成功读取；改用已定位的准确范围成功重读。首次宽Git状态输出被截断，仅用于混合工作区存在性提示，不用于宣称完整产物覆盖。

Run启动/UI/契约仍在集成，不给整体绿结论。本轮未验证真实模型、业务DB、端到端浏览器或平台容器；仅mock服务及隔离PG。后续完整S3/S6仍需覆盖多组/来源失败顺序、分类/模型资格/政策变更、并发领取/事务回滚、确认失效和人工内容保护。预算纯账本已冻结每组limits；目前首次处理及新组仍从模块默认新建，若整Run跨部署要求同一参数，应在Run冻结limits并复制到各组。该点作为集成待补项，不声称纯账本重启保护失效。
