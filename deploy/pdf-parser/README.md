# PDF提取运行器

版本：v1.0
日期：2026-10-29

本目录只构建PDF解析环境，应用/API/Worker无需整体容器化。Windows使用Docker Desktop的Linux容器模式；Linux使用Docker Engine；macOS默认使用原有Seatbelt，也可显式选容器。Windows原生ACL运行器与Linux原生bwrap运行器尚未实现。容器模式不是无依赖的Windows原生解析。

从仓库根构建（需要访问官方Python镜像仓库和PyPI；不发送业务文件）：

```sh
docker build --tag rpb-pdf-parser:1 deploy/pdf-parser
```

运行时不会自动拉镜像。缺少CLI、镜像、daemon或启动能力时返回`parser_unavailable`，沿原规则尝试真实摘要；不会退回应用进程解析。解析容器没有主机挂载，不继承应用环境变量；只通过标准输入接收一份PDF，以非root身份在私有tmpfs处理，禁用外部网络，根文件系统只读，限制内存/CPU/进程数/输出及总时长。超时后终止并回收CLI，再按唯一名称强制移除容器。清理退出非零或超时则返回parser_unavailable并记录容器名，不能继续报告成功。daemon失联或创建请求迟到时不能保证立即删除；运维恢复连接后应按日志中的具体容器名复查并执行`docker rm --force <该名称>`，不要按前缀批量删除其他活动任务。容器带有`org.researchpaperbase.pdf-parser=1`标签以便定位。Docker控制端属于受信部署环境，不得交给不受信用户。

当前接口：`PDFProvider(engine="pypdf", runner="auto")`。`available_engines()`只返回已实现的引擎，目前为`pypdf`；每次指定一个引擎，不轮询其他引擎、不合并多引擎结果。未知引擎/运行器拒绝配置。`runner`支持`auto`、`seatbelt`、`docker`；未显式传入时，Worker启动读取`RPB_PDF_RUNNER`，默认`auto`（macOS→Seatbelt，Windows/Linux→容器）。配置在Provider创建时固定，不热更新。环境变量只选择运行器，不开放用户指定任意命令或镜像。

这是后端可扩展选择接口，当前只有一个实际引擎，未新增终端用户切换UI。LLM解析仅为下一阶段设计目标，尚未注册；新增引擎及用户选择入口时，必须同时设计Run冻结选择、凭据/文件外发、结果溯源、预算及内容确认，不能只把联网模型塞入禁网静态解析脚本。

真实容器检查入口（使用项目Python 3.14环境，在仓库根执行；Windows将解释器路径换为`backend\.venv\Scripts\python.exe`）：

```sh
backend/.venv/bin/python -m pytest backend/tests/runtime/test_pdf_container.py -q
```

测试会创建/删除本次随机命名的`rpb-pdf-*`容器及临时测试PDF，并短暂监听本机随机TCP端口，使用默认网络控制容器建立可连正对照，再验证禁网解析器无法连接；不访问业务数据库、模型或邮件。该测试不属于默认单元测试集，缺少运行环境时失败而不跳过。平台支持证据须分别保留Linux运行时和Windows宿主实际执行结果；配置分派的模拟测试不能证明宿主支持。

当前验证状态以[task046](../../tasks/046-paper-processing-gate.md)为准。运行器参数依据[Docker官方运行文档](https://docs.docker.com/engine/containers/run/)。
