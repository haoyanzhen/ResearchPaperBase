# 或许有用：辅助逻辑与外围业务规则

版本：v1.0 · 日期：2026-10-16 · 项目大版本：1

这是隔离候选存档，不是新核心或新认证方案。没有应用入口、ORM、数据库连接、配置加载、JWT、撤销列表、全局日志初始化或外部服务请求；不会维持旧接口。候选仅供重建时重新评估，不承诺直接上线，也不把既有散列迁移能力作为目标。

## 实际拆分

| 审查项 | 存档文件 | 提取与局部修正 | 依赖与局限 |
| --- | --- | --- | --- |
| B-X01 | `password_candidate.py` | 仅保留 bcrypt 散列/匹配意图，去掉 passlib 兼容层，直接调用 bcrypt；输入不做归一化，超过 72 UTF-8 字节显式拒绝，避免截断；损坏散列不匹配 | 可选第三方 `bcrypt`；仅接受本候选生成的 `$2b$12$` 格式/成本，不通吃历史散列；新系统的算法、密码长度政策、迁移和会话另行设计 |
| B-X02 | `helpers.py` 的 context 函数 | 复制快照、ContextVar token 恢复；收窄到 trace/operation/project/user ID，限制字符与长度；修正旧示例误用 async with | 标准库；字段白名单不能识别伪装成 ID 的秘密，调用方仍须只传不含秘密的标识；子任务按 ContextVar 规则继承创建时上下文 |
| B-X03 | `helpers.py` 的 `random_identifier` | 保留内部前缀＋随机 ID，改标准库 128 位随机值，限制前缀；不保留旧前缀或长度契约 | 标准库；不是唯一性证明，未来存储仍需唯一约束及碰撞处理 |
| B-X04 | `helpers.py` 的 `quote_identifier` | 仅留双引号转义，拒绝空值/NUL/超过 63 UTF-8 字节的输入 | 标准库；63 字节为本候选显式边界；仅单个 PostgreSQL 标识符，`a.b` 被当作一个名字；不是 SQL 值转义，不支持自动建库 |

源码来源（相对仓库根，记录的是删除前来源定位，不是当前可运行入口）：

| 来源 | SHA-256 |
| --- | --- |
| `backend/app/core/security.py` | `17586c51621292d8f122546da8b3159b1bc3c26f45eb3efb76bedc8afbe7239e` |
| `backend/app/core/logging.py` | `eb79e911d5a2ff3b0ce6448a43ad04b45d5c11b53866949fadde0a0c4381caa8` |
| `backend/app/utils/ids.py` | `c6ed3fa2d162374261f5150dca13cde98ac1117ffb7bc4f2e54b5a283bb70527` |
| `backend/scripts/init_db.py` | `731ba60113bbfa7edaac39a4c064cbdea9dfda499e54ea93c2f3856a33c6a238` |

全部为限定片段提取并局部修正，没有整文件复制。具体留存理由来自 `docs/proposals/reuse_independent_review_2026-10-16.md` 的 B-X01～04。

## 只留规则，不留实现：B-R01～10

以下规则整理自独立审查，不新增接口或架构，不代表规则已实现。

| 编号/旧来源 | 留存业务意图 | 重建时应验证 |
| --- | --- | --- |
| B-R01 `auth_service.py`、`core/deps.py`、`schemas/auth.py` | 认证需要核对凭据与账号状态；停用账号不能继续使用 | 用户名与他人 email 交叉冲突、并发注册、旧会话停用、资料修改验证 |
| B-R02 `auth_service.py`、`admin_service.py` | 首个管理员建立、授权管理、至少一个启用管理员 | 并发首次注册/撤权/禁用，停用者不计可用管理员；不能沿用先计数再写入 |
| B-R03 `admin_service.py`、`models/user.py` | 删除账号前计算应删/应留引用和资产范围 | 保留其他 Project 的引用及全局论文身份；任务/文件清理和失败恢复；不能沿用 ORM 级联 |
| B-R04 `admin_service.py` | 经授权重置密码，新密码一次展示和审计 | 安全随机生成、散列保存、会话策略与邮件分离；新密码展示遵循现行 FR-005，不能继承非密码学 shuffle |
| B-R05 `config_service.py` | 显式选择模型，解析个人/系统来源，组合个人收件人与系统 SMTP，并形成运行快照 | 缺失/禁用/失效分开；凭据引用及快照冻结；不能以首个模型回退替代显式选择 |
| B-R06 `config_service.py`、`models/user.py` | 配置、凭据、无秘密展示投影分离 | 保存失败原子性、并发变更、特殊名称、脱敏；不得继承明文 KV、逐字段提交、LIKE 模糊删除 |
| B-R07 `api/v1/config.py`、`admin.py` | 明确 endpoint/协议/凭据后进行连接与模型枚举，产生分类结果 | 401/403/429、坏 JSON/空列表；可读模型列表不等于能调用模型 |
| B-R08 `api/v1/health.py` | 受限探针分清连通、就绪、认证和业务调用 | 部分失败/未配置/读取失败可见；默认诊断不得静默付费生成或发邮件 |
| B-R09 `core/errors.py`、`logging.py` | 类型化错误，分离用户安全信息与内部诊断，可重试性由用例决定 | 秘密与嵌套 detail 脱敏；不继承字符串猜测分类、任意 traceback/extra 透传 |
| B-R10 `core/database.py`、`config.py`、`alembic/*`、`scripts/init_db.py` | 显式环境、事务所有权、迁移目标；新库初始化与真实数据迁移分开 | 不自动加载旧 metadata/业务库；测试不能回退业务环境；两条迁移分支独立验收 |

## 离线验证

2026-10-16 使用已有 `.venv/bin/python`、bcrypt 4.3.0，未安装任何依赖。运行：

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s archive/maybe_useful/support_logic/tests -v
```

结果：8 项通过，0 跳过。覆盖中文密码、72 字节边界、超长/错误/损坏散列、随机盐、上下文副本与嵌套异常恢复、协程隔离、字段限制、随机 ID 契约、标识符特殊字符及 UTF-8 长度。

旧虚拟环境清理后，在具备 Python 的环境可运行：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s archive/maybe_useful/support_logic/tests -v
```

缺少可选 bcrypt 时，密码候选的 3 项测试会明确跳过，辅助标准库的 5 项测试仍可运行；跳过不等于密码测试通过。没有复制旧 requirements 或依赖环境。本次未读凭据文件、未联网、未连接数据库；测试均使用合成字符串，不涉及真实密码。验证不覆盖数据库唯一性、服务端授权、旧散列迁移或生产认证安全。
