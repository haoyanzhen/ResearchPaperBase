# Task046 PDF引擎与容器运行器独立审查

版本：v1.0
日期：2026-10-29
代理：processing_design_review

## 结论

新增代码的有界S3审查及已修缺陷复审通过，未发现仍需独立修复的代码阻塞。**跨平台交付仍未通过**：真实容器PC01–03此前3项失败，Windows宿主无实际执行证据；本报告不能作为S7工程收口或M-P0-15人工接受。Linux容器运行、Windows宿主及部署依赖必须分别记录，模拟平台分派不是实机验证。

范围为pdf_processing/pdf_engines/pdf_container、两组PDF测试、镜像Dockerfile/README、task046第11节、04-01末节与coverage指纹及状态。仅pypdf实际注册，单次明确选择一个引擎，不自动切换其他引擎；LLM仍为下一阶段设计，无模型调用/UI选择新增。旧17项review-code-artifacts中仅pdf_processing改变；其他处理提交、权限与确认实现SHA未变，未重跑数据库或浏览器历史验收。

## 发现与修复核查

1. **P2 清理失败仍报告成功，已修**。初读pdf_container SHA dc0a6b58直接忽略docker rm非零/超时，finally之前已准备返回成功。独立review-runtime1两条红测均复现；现SHA a2bbf8fb先终止并回收CLI，再强制删除具唯一名称的容器。删除失败返回parser_unavailable并warning具体名称；PE08和独立probe覆盖非零及超时。没有声称daemon断联或迟到创建必然被立即清除；README已明确恢复连接后按具体名称复查处理，禁止前缀批量删除活动任务。此部署限制保留。
2. **P2 未校验引擎结果，已修**。初读parse_pdf直接返回运行器JSON，prepare依赖text/reason字段，非法形状可使Worker捕获整组异常并丢失摘要降级机会。审查中主代理已加入统一验证：诊断白名单、非空文本及20万字符界限、1–2000个页段、整数且非bool、连续偏移覆盖文本、递增页码及2000页上限。失败结果清除文本/页段，不让未知结果成为证据。PE07及独立异常形状probe通过。本项未执行旧代码红测，不虚构红绿证据。
3. **P2 运行时隔离测试缺少可判别对照，测试设计已修、执行未通过**。旧PC02连接192.0.2.1失败不能证明禁网，非root写/usr/local失败不能证明只读。现有默认网络控制容器连接受控宿主临时socket的正对照，隔离容器尝试相同IP/端口；写/tmp明确期望EROFS。测试源码已审，镜像不可用，尚无这些新断言的实际通过证据。
4. task第8节历史“之后仅文档变化”与新增实现冲突已反馈主代理修订；第11节仍列初始31项、lint1待复验及S3待执行，应在收录本报告与主新证据时更新，不得覆盖原失败记录或把此代码结论写成平台支持已交付。

## 实际验证与证据

- review-runtime1：真实exit1，45项中43通过、2失败，失败为上述清理回归probe；运行中基线已含parse_pdf校验修复。
- review-runtime2：exit0，较小深度JSON探针1/1；不是缺陷红测。
- review-runtime3：exit0，独立probe8/8；含10万层合法JSON，实际运行器拒绝非dict，没有声称曾复现RecursionError或源码已经增加该catch。
- **review-runtime4：exit0，48/48，无skip：项目PDF单元40项＋独立probe8项。** 完整日志、JUnit、run真实退出码、执行前SHA及实际delivery_summary结果均为同名前缀。执行命令为backend/.venv/bin/python -m pytest backend/tests/unit/test_pdf_engine_runtime.py backend/tests/unit/test_pdf_processing.py docs/workorders/evidence/task046_processing_gate_2026-10-29/review_runtime_probes.py -q --junitxml=docs/workorders/evidence/task046_processing_gate_2026-10-29/review-runtime4.xml。
- review-runtime-records：只读SHA/指纹比对及实际普通日志摘要；04-01原文SHA与coverage匹配。review-runtime4后业务和单元文件无漂移；runtime测试仅字符串折行、README清理限制更新，已定向重读。最终相关13文件SHA在review-runtime-artifacts.json。
- 主platform-runtime1 run和摘要独立读取：exit1，0/3通过、3失败，均parser_unavailable。本轮不重复启动必然缺镜像失败的PC测试，不调用Docker/业务数据库/LLM/email。主31项旧证据、lint/types通过均不能替代真实平台验证。

## 读取与剩余事项

按AGENTS先两条bootstrap、entry、DELIVERY_TOOLS第5节；独立context=review-runtime-20261029、ledger=review-runtime-ledger.json。对三份较小安全边界源文件完整定向读取以审查跨函数清理/验证路径；其他用outline和必要symbol/section。一次paper_processing路径定位拼错通过限定rg纠正；一次容器显式行范围超界exit2，改为有效100–140行，未使用错误输出作结论。运行证据不能替代需求审查。

尚需：获取官方基础镜像并构建实际解析镜像，执行真实PC01–03（含新正对照）并保留清理证据；在Windows宿主Docker Desktop Linux容器模式实际执行；如宣称Linux宿主支持也保留对应部署/运行证据。可观测的清理失败与运维处理限制必须保留。以上完成后再做受影响复审、最终验证和工程收口，M-P0-15仍等待用户接受。
