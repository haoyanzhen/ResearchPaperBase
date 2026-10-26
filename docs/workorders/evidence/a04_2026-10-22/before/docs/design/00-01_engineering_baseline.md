# 新核心最小工程基线

文档版本：v1.1
更新日期：2026-10-22
依据：[00](00_layers.md)、[05-01](05-01_internal_module_contracts.md)、[07](07_data_persistence.md)、[08](08_security_permissions.md)、[10](10_operations_deployment.md)

## 1. 决策范围

A02采用同仓库模块化应用、同一后端包的API与Worker两个进程、关系库持久任务及本地受控文件存储。本文件是具体工程选择的唯一维护位置，各层通过引用承接；落实已确认的单部署/计划停机方向，不要求零停机、独立消息中间件或微服务。

本文件维护目标工程选择；各部分实际落地与验证范围统一见[项目状态](../PROJECT_STATUS.md)及[任务005](../../tasks/005-engineering-skeleton.md)。目录存在不代表业务能力实现。A04–A10缺项仍按模块阻塞，工程选型不关闭资料政策或Graph-RAG设计。

## 2. 技术选择与版本管理

| 领域 | 首版选择 | 理由与交付约束 |
| --- | --- | --- |
| 后端 | CPython 3.14标准构建；FastAPI、Pydantic 2、Uvicorn | Python承载应用与知识服务；领域为普通Python值对象，不导入HTTP/ORM类型；选稳定维护线，具体补丁/兼容组合由首次安装锁定 |
| Python依赖 | uv项目，backend/pyproject.toml及backend/uv.lock | 锁文件唯一解析来源，安装/CI采用locked模式；contracts/requirements.txt保留独立检查环境，不改写其固定版本 |
| UI | React 19、TypeScript、Vite单页应用；Node.js 24、npm | 同源浏览器工作台，无新增SSR服务；frontend/package-lock.json为唯一前端依赖锁；npm版本与Node补丁随首次工程验证固定 |
| 关系库 | PostgreSQL 17；SQLAlchemy 2.0、Psycopg 3、Alembic | 真实PostgreSQL验证事务/锁；不用SQLite替代并发验收；API/Worker共用迁移链 |
| 数据访问 | 应用UoW封装同步SQLAlchemy事务；API阻塞数据库调用在受控线程执行 | 单事务独立Session，不跨线程/请求共享；SSE等待不占数据库事务/连接，外部调用不在事务内 |
| 文件与凭据 | FileStore使用本地持久目录、不可变对象key和独立临时目录；SecretStore使用关系库密文记录、部署外置本地加密主密钥 | 下载经应用鉴权；主密钥不入源码/数据库/日志；不维护历史Provider key；成熟加密库及恢复验证随适配器任务落实，不新增用户密钥管理功能 |
| 执行与流 | PostgreSQL命令/Task/outbox及持久事件，Worker轮询领取；SSE读取持久投影 | 进程内队列不是唯一任务记录；P0不依赖Scheduler/邮件推送；轮询/租约参数随实现验证 |
| 向量与图谱 | Knowledge拥有VectorStore/GraphStore端口，具体产品/索引算法留A09 | 不采纳pgvector、独立图数据库或013候选；未配置能力时相关操作安全拒绝，不用空结果/JSON占位伪装可用 |
| 验证 | pytest、Ruff及Python类型检查；TypeScript、Vitest/Testing Library；Playwright浏览器链路 | 工具补丁及插件随锁文件验证；单元、真实存储集成、端到端分开报告，不按数量替代验收 |

本表固定技术方向与运行时版本线，不把尚未安装的依赖组合称为可运行基线。首次交付记录Python/Node/npm/uv/PostgreSQL和直接依赖准确版本、锁文件摘要及干净安装结果。安全补丁和常规兼容修复可在授权工程任务内处理；更换框架/数据库更新本决策及验证，不默认升级为产品决策。

查证依据（2026-10-21）：[Python支持版本](https://devguide.python.org/versions/)的3.14维护线、[Node发布表](https://nodejs.org/en/about/previous-releases)的24 LTS、[PostgreSQL支持表](https://www.postgresql.org/support/versioning/)的17支持线；只支持版本选择，不证明项目兼容。[FastAPI版本建议](https://fastapi.tiangolo.com/deployment/versions/)支持锁定和测试依赖；[uv locked](https://docs.astral.sh/uv/concepts/projects/sync/)与[npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/)用于阻止安装时隐式改锁。UI参考[React版本](https://react.dev/versions)和[Vite指南](https://vite.dev/guide/)。

## 3. 规划目录与写入归属

目标目录如下；首批只建立所需边界，未实现端口不提供伪可用结果：

```text
backend/
  src/rpb/
    bootstrap/                  # 唯一装配具体适配器处；API/Worker入口
    api/                        # HTTP/SSE/DTO转换，只调公开用例
    modules/
      account_config/ project/ workspace/ construction/ research/ review/
        domain/ application/    # 各模块规则、用例及其端口
    execution/                  # 去重、任务、资格与交接技术契约
    knowledge/                  # 读取/证据/候选准备及其端口
    agents/                     # 类型化提案及Provider端口
    adapters/                   # PostgreSQL/文件/密钥/Provider/解析器
  migrations/                   # 唯一Alembic迁移链
  tests/                        # unit/architecture/contract/integration
frontend/src/                   # Shell、按业务划分features、api客户端
frontend/e2e/                   # 浏览器链路；业务隔离夹具随对应切片建立
contracts/                      # 已有机器契约，仅消费实际覆盖结构
scripts/                        # 已有契约工具，工程入口随实现建立
```

| 所有者 | 可提交事实 | 边界 |
| --- | --- | --- |
| Account / Config | 身份、会话、配置及凭据引用 | 管理员不隐含Project内容权限 |
| Project | Project生命周期与归属 | 经应用协作初始化Construction容器和治理撤权，不私改Run/版本 |
| Workspace | 用户显示现场、未提交草稿 | 恢复不提交业务内容 |
| Construction | 补充、候选、Run和知识资产发布 | 唯一组织知识库业务提交，Knowledge/Agent只返回受控准备结果 |
| Research / Review | 各自绑定、回复/稿件、确认及证据关联 | 不修改知识资产或旧绑定，遵循人工保护 |
| Execution / Knowledge / Agent | 所属技术事实或具名能力 | 不拥有跨业务状态机；身份登记经应用端口，候选写受scope限制 |

Domain不导入外层；Application依赖Domain、服务契约和自身端口；Agent可依赖Knowledge契约，Knowledge不反向依赖具体Agent/应用。跨模块只用公开端口，不传可写ORM对象；adapters实现所属端口，只有bootstrap选择具体实现。事务由应用协调，repository/Provider不擅自commit。

迁移装配可登记各模块表，不授予运行时跨模块写权。禁止导入archive；未启用P1/P2不因目录设计而要求建表/开放入口。导入图与架构负例由B08随源码落实。

## 4. 进程与持久交接

API与Worker分进程、同版本后端包、同一关系库及显式文件命名空间。API受理/查询/流投影，Worker执行持久任务。解析器使用受限子进程或容器，仅挂载本次输入/输出和临时目录，默认无网络/密钥；具体隔离工具由B05验证，普通子进程本身不证明隔离。

异步受理按07 §6.1短事务提交去重、Task、冻结输入/适用确认和outbox后返回。Worker轮询并短事务条件领取/租约，重验资格后调用所属应用入口；可用行锁跳过锁定的队列项，但队列锁不是业务槽或权限校验。[PostgreSQL锁定语义](https://www.postgresql.org/docs/17/sql-select.html)是机制依据，正确性须故障测试证明。

领取、外部执行、提交分离；重复投递查持久事实；响应丢失先核验同一提交身份；Provider结果未知不盲目重试。领取不把任务永久视为完成；崩溃后按租约/资格和持久结果裁决，不能恢复旧Worker资格。取消与提交沿05/07互斥；同步操作不造Task/outbox；SSE断线不重做业务。缺模型配置不关闭无模型依赖的管理入口。

计划停机先停止接入/领取，再排空或按授权撤资格；API/Worker同版本成组切换，不要求并存升级。迁移不随服务启动隐式执行。具体轮询/重试/租约参数是B03技术细化，不能改变P1恢复分期或paused占槽规则。

## 5. 数据与测试隔离

| 环境 | 隔离目标 | 缺项行为 |
| --- | --- | --- |
| 开发 | 新实例/库、新文件根和密钥材料；不从旧业务配置推导目标 | 必需目标缺失拒绝相应服务就绪 |
| 集成/端到端 | 专用测试PostgreSQL实例；每次运行独立库/角色、文件根、索引命名空间及测试密钥；API/Worker共享本次运行标识 | 缺显式测试配置或标识不匹配立即失败，不回退开发/业务目标 |
| 业务部署 | 独立业务目标与保管材料，部署前按10验证恢复 | 未有运行目标/恢复证据不宣称部署验收通过 |

测试代码只取得本次角色，建库/删库权限留给测试夹具。连接前检查显式测试地址/允许目标，连接后核验库名、角色和运行标识；不只凭名字含test认定隔离。业务凭据/旧目录不提供给测试进程。文件及清理目标校验运行标识和根归属，不做宽泛递归清理。

涉及并发、Worker或服务内部commit时使用可销毁独立库并真实提交断言，不只依赖外层rollback。结束后先停止本次API/Worker/解析器，再按登记清理本次库及存储；失败记录残留，不误清其他运行。Savepoint可用于局部测试，但不替代真实提交/竞争验证；参考[SQLAlchemy事务](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)。

测试实例可使用本机专用容器，具体运行时和镜像摘要随首次环境交付登记。LLM/论文源/邮件默认mock，真实检查另明确目标、副作用和授权。恢复演练不连接旧Worker。H02未定时只设计独立新环境，不触碰旧数据。

## 6. 工程入口责任

入口由B08建立并实测后写入README。下表是职责设计；当前可执行命令及限制见README，不得拷贝旧工程命令冒充验证。

| 类别 | 负责位置 | 交付证据 |
| --- | --- | --- |
| 安装/锁检查 | backend/frontend依赖定义，根级入口调用 | 固定版本、锁、干净安装；缺锁/漂移非零退出 |
| 静态/类型/架构 | 语言配置、backend架构测试 | 类型/依赖负例拒绝，不让ORM/SDK类型进入Domain |
| 契约 | 已有检查器/测试 | 对真实基线比较、报告缺项；框架生成不能覆盖已定协议 |
| 测试 | backend/tests、frontend测试、e2e夹具 | 09用例到真实命令/环境/结果/清理；缺隔离不执行 |
| 构建 | 后端包/前端静态产物 | 绑定源码/锁摘要，不隐式迁移或访问Provider |
| 迁移 | backend/migrations、受控入口 | 明确目标、版本、前置、失败核验与恢复 |
| 启停/就绪 | bootstrap、部署runbook | API/Worker准确版本；依赖就绪与业务验收分开 |

A01阶段仅复跑契约检查；后续工程证据统一见任务005及PROJECT_STATUS。业务迁移、并发和首条业务链路仍须闭合自身前置并实际验证。

## 7. 备选与未决边界

- 暂不引入独立队列/Redis：先验证现有关系库原子受理；以后替换适配器保持相同契约。
- 不引入SSR或按层拆服务：现行同源工作台无此新增运行需求。
- 不用SQLite、内存任务或可变Project索引代替真实持久/隔离验收。
- Graph/向量产品留A09/H01；若影响本基线，记录工程差异，不静默替换。
- 旧数据保留留H02：未知时不接触旧环境，新隔离设计可继续；不决定删除/迁移。
- 保留期限、备份周期、RPO/RTO和容量留H03/10 §9，不设默认数字；它们阻塞相关自动清理和生产承诺，不阻塞本地设计。

没有需重新裁决的业务语义。未来确需付费资源、真实外部测试或政策变更时列具体问题；常规兼容修复和参数细化按已授权任务自主处理。
