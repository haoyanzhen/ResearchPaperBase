# M-P0-05：个人LLM配置与模型选择验收包

文档版本：v1.0
更新日期：2026-10-26

设计、代码、自动验证与S1–S7工程收口已完成。M-P0-05待用户验收；本报告不是用户接受记录。授权与逐项追踪见[task026](../../tasks/026-llm-parameter-runtime.md)。

## 1. 可使用成果

登录后可维护本人LLM配置、写入/轮换/清除加密凭据；常用参数与受控custom_params保留类型，拒绝重复/冲突/越界字段。四协议适配与未知能力显式测试遵循[04-04](../design/04-04_llm_parameter_contracts.md)，不引入启停开关或自动替换模型。

保存不调用Provider。发现模型只产生待测候选；显式测试固定文本，当前配置及凭据修订下逐模型成功后才可选择。选择跨刷新和登录恢复；配置变化后保留失效身份提示。测试、幂等回执、事件和安全结果持久化；未知调用结果不自动重发。删除后私有配置和任务不可读。

草稿切换提供保存/放弃/留下；响应丢失核查原请求或读取当前配置，明确拒绝后可继续编辑；测试状态刷新不升级旧草稿修订。账号切换清除私有界面。任务详情展示实际参数、仅测试覆盖和安全失败原因。

## 2. 可复现验收

先按[README](../../README.md)使用Python3.14、Node24/npm11安装锁定依赖并build，运行：

```sh
python3 scripts/engineering.py demo --postgres-bin /opt/homebrew/opt/postgresql@17/bin
```

浏览器打开 `http://127.0.0.1:8765/workspace`，注册/登录后：

1. 新增LLM配置，填写支持的协议与Base URL、密钥、temperature=0及适用扩展；保存后密钥框为空且标明已保存，不发生外部测试。
2. 刷新发现模型或手填ID，确认可能费用后显式测试；读取测试状态及详情。只有该模型成功才加入顶部可选项；发现本身不能选择。
3. 选择模型，刷新页面验证恢复；修改配置后原选择提示失效。
4. 两标签编辑同一配置，旧页保存应冲突且草稿保留；切换配置可明确保存/放弃/留下。删除前确认，删除后选择失效。
5. 无密钥配置测试被拒后可原页补密钥保存；失败原因可见。自动测试另覆盖响应丢失、租约和派发竞争，见第3节。

演示使用可清理隔离数据库和0600临时密钥文件，退出删除数据；不是持久开发/生产环境。只有手动点击已确认的测试才向填写的外部Provider发起推理，可能收费。自动验证全程用FakeProvider或受控本地服务，没有真实云调用或邮件发送。

## 3. 验证证据

证据根目录：[task026 evidence](evidence/task026_llm_parameters_2026-10-26)。完整内容快照：[delivery/source-manifest.json](evidence/task026_llm_parameters_2026-10-26/delivery/source-manifest.json)，对应source.tar.gz包含未提交/未跟踪源码。

| 检查 | 实际结果 | 日志 |
| --- | --- | --- |
| 完整隔离PG/HTTP/浏览器 | 350通过，318.53秒；包含LU01–09 | [integration-final](evidence/task026_llm_parameters_2026-10-26/integration-final.log) |
| S4事务/迁移补强 | LC20–22：3通过；降级前后密文/解密、两个等待请求竞争、审计失败回滚 | [coverage-verified](evidence/task026_llm_parameters_2026-10-26/coverage-verified.log) |
| 实际demo Worker进程 | LD01：1通过；持久队列消费与网络拒绝路径 | [demo-worker](evidence/task026_llm_parameters_2026-10-26/demo-worker.log) |
| 静态/类型/架构/后端单元 | 155通过 | [check-final](evidence/task026_llm_parameters_2026-10-26/check-final.log) |
| 机器契约 | 68通过，结构/引用/规范摘要一致 | 同上 |
| 前端 | 4通过；包含重复JSON键测试 | 同上 |
| 构建 | wheel与Vite成功 | [build-accessibility](evidence/task026_llm_parameters_2026-10-26/build-accessibility.log) |
| 干净安装/锁拒绝/wheel启停 | Node24环境成功，临时副本清理；进程smoke仍限定工程骨架，真实业务Worker另由LD01证明 | [clean-install-node24](evidence/task026_llm_parameters_2026-10-26/clean-install-node24.log) |

当前集成场景合计354项（350全量+4补验），不把筛选专项重复计入数量。命令入口为`engineering.py check/build/integration`与`verify_skeleton_delivery.py`；数据库始终显式`--postgres-bin`，无业务库回退。日志记录非管理员测试角色和最终server_stopped/root_removed。首次干净安装因系统Node25不符合约定被正确拒绝，后用Node24复验；首次完整运行超过旧300秒上限，后按增长后的用例集将上限设为600秒，未跳过测试。其他中间失败与修复证据保留，不冒称首次全绿。

## 4. 独立审查与覆盖收口

后端reviewer独立执行68项相关单元；前端reviewer独立执行4项。已关闭：参数解析异常、派发前授权/租约、错误响应假成功、DNS/TLS总期限、SSE取消释放、旧草稿修订被刷新提升、结果详情缺失、测试入口漏收、切号读取混合、明确拒绝后pending阻塞编辑。补验LC20密文断言及LC21确定性等待窗口再次只读复核通过。两位reviewer均未声称独立运行PG或浏览器；这些以主代理真实执行日志为准。

S4逐LP/LN/LC/LU/LD追踪补足适用成功、拒绝、失败、并发、凭据、版本和恢复边界；S5保留清晰分层、复用现有授权/错误/分页，未做无收益重构；S6复验和受影响复审闭合。入场254文件内容基线保留，未提交原工作区没有重置或擅自提交。`git diff --check`中3处既有文档EOF空行与入场摘要完全相同，未为消除提示修改无关设计。

## 5. 边界与后续

本片是个人配置的本地业务成果。未知模型仍须显式测试，不保证全部云版本或流式/工具能力；系统LLM管理、生产密钥/Worker运维、知识构建及新Run启动消费模型配置仍待后续授权与实施。一般TaskView/事件信封及逐端点错误机器绑定仍由coverage保留缺项，不能把个人LLM投影当整个任务平台交付。

无新增业务设计待决。到达M-P0-05，暂停依赖此验收的下一阶段，等待用户验收。
