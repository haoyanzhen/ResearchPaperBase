# Research Paper Base

**！It's not finished!**

Research Paper Base 是一个面向研究场景的 Web 应用，围绕一个研究项目提供三类能力：

- 构建模式：检索论文、筛选评分、下载解析、总结分析、定时推送
- 深度研究模式：基于项目论文库进行对话式研究
- 综述模式：生成综述架构、章节与汇总内容

当前仓库已经包含：

- FastAPI 后端
- PostgreSQL + Alembic 数据迁移
- Vite + React 前端
- 前端单元测试与后端单元测试

本文档基于当前仓库现状整理，重点说明如何安装、配置、启动和使用这套应用。

## 1. 运行环境

建议环境：

- Python `3.11+`
- Node.js `18+`
- npm `9+`
- PostgreSQL `14+`

本地开发时默认端口：

- 后端 API: `http://127.0.0.1:8000`
- 前端 Dev Server: `http://127.0.0.1:5173`
- Swagger UI: `http://127.0.0.1:8000/docs`

## 2. 项目结构

关键目录如下：

```text
backend/   FastAPI 后端、数据库迁移、业务逻辑
frontend/  Vite + React 前端
docs/      API、页面设计、文件映射等文档
e2e/       Playwright E2E 测试草稿
```

更详细的文件职责见 [docs/file_map.md](docs/file_map.md)。

## 3. 安装

### 3.1 克隆并进入项目

```bash
git clone <your-repo-url>
cd ResearchPaperBase_codex
```

### 3.2 安装后端依赖

推荐使用虚拟环境：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 3.3 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

## 4. 配置

### 4.1 配置后端 `.env`

复制模板：

```bash
cd backend
cp .env.example .env
```

编辑 `backend/.env`，至少配置以下字段：

```env
DATABASE_URL=postgresql+asyncpg://<db_user>:<db_password>@localhost:5432/<db_name>
SECRET_KEY=replace-with-a-random-secret
ACCESS_TOKEN_EXPIRE_MINUTES=1440
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
STORAGE_DIR=./storage
```

说明：

- `DATABASE_URL` 必须改成真实可连接的 PostgreSQL 地址。仓库默认值只是占位符，不能直接使用。
- `SECRET_KEY` 必须自行替换。
- `STORAGE_DIR` 用于保存 PDF、解析文本和图缓存。

### 4.2 关于工作目录

后端配置使用 `env_file=".env"`。这意味着：

- 推荐从 `backend/` 目录启动后端
- 否则需要手动导出环境变量

如果你从仓库根目录启动，`backend/.env` 不会被自动读取。

### 4.3 初始化数据库

初始化顺序是：

1. 先填写 `backend/.env`
2. 运行初始化脚本
3. 由脚本负责“检查数据库是否存在 -> 必要时创建数据库 -> 执行 Alembic 迁移”

执行方式：

```bash
cd backend
../.venv/bin/python scripts/init_db.py
```

如果你已经激活了虚拟环境，也可以直接执行：

```bash
cd backend
python scripts/init_db.py
```

## 6. 启动

需要两个终端。

### 6.1 启动后端

```bash
cd backend
PYTHONPATH=. ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动成功后可访问：

- API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 健康检查：[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 6.2 启动前端

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

启动成功后访问：

- 前端首页：[http://127.0.0.1:5173](http://127.0.0.1:5173)

## 7. 用户如何使用该 App

### 7.1 第一次进入

1. 打开前端首页，会进入 `/login`
2. 注册一个用户
3. **首个注册用户会自动成为管理员**

这一点由后端 `auth_service` 实现，用于初始化系统级配置。

### 7.2 管理员首次配置

首次进入后，建议先打开设置页 `/settings`，完成最小可用配置：

1. 配置系统 LLM
2. 配置系统论文库接口
3. 可选：配置系统邮件

原因：

- 普通用户的个人配置未填写时，会回落到管理员的系统配置
- 发件 SMTP、发件邮箱和发件密码只允许管理员维护
- 构建模式、深度研究模式、综述模式都依赖 LLM 和论文库配置

当前设置页已经包含：

- 个人资料
- 个人 LLM 配置
- 个人论文库配置
- 个人邮件设置
- 用户管理（管理员）
- 系统 LLM（管理员）
- 系统数据库（管理员）
- 系统邮件（管理员）

### 7.3 创建项目

进入 `/projects` 后：

1. 点击“新建项目”
2. 填写项目名称和描述
3. 创建完成后会进入项目工作台

### 7.4 使用构建模式

项目工作台默认为构建模式入口，主要可完成：

1. 点击“开始构建”
2. 查看当前阶段、阶段历史、论文摘要
3. 打开 Inspector 查看诊断信息
4. 配置项目级定时推送

当前工作台已经接入真实服务层，可看到：

- 当前阶段
- 有效论文 / 总论文
- 阶段历史
- 定时推送开关与间隔
- InspectorPanel 诊断信息

### 7.5 使用深度研究模式

当项目已经有有效论文后，可切到深度研究模式：

1. 在工作台顶部切换到“深度研究”
2. 进入 `/projects/{projectId}/dialogue`
3. 新建对话
4. 输入问题并发送
5. 前端会通过 SSE 实时展示模型回复

适合用来做：

- 问题追问
- 论文对比
- 技术路线梳理
- 基于现有论文库的问答研究

### 7.6 使用综述模式

当项目已经有有效论文后，可切到综述模式：

1. 在工作台顶部切换到“综述”
2. 进入 `/projects/{projectId}/review`
3. 点击“启动综述”
4. 查看架构预览、章节列表和章节内容

当前前端已经实现综述模式基础工作台，但导出和更完整的编辑交互仍在继续完善。

### 7.7 健康检查

设置页中可进入 `/settings/health`，检查：

- 基础探针
- 数据库探针
- 深度依赖探针

这页用于快速确认当前环境是否满足联调条件。

## 8. 当前已实现与未实现范围

当前已经具备可用入口的页面：

- `/login`
- `/projects`
- `/projects/:projectId`
- `/projects/:projectId/dialogue`
- `/projects/:projectId/review`
- `/settings`
- `/settings/health`

当前仍属于“部分实现 / 未完成”的前端能力：

- 模式切换确认弹窗
- 独立论文库页面
- 论文评分详情弹窗
- 独立知识图谱页面
- 推荐模块页面
- 更完整的综述导出 UI

详细状态可参考 [docs/ui_design.md](docs/ui_design.md)。

## 9. 测试

### 9.1 前端单元测试

```bash
cd frontend
npm run test:run
```

当前前端测试覆盖：

- 登录/注册
- 项目列表
- 构建工作台
- 深度研究对话
- 综述页
- 设置页
- 健康检查页
- InspectorPanel
- SSE hook

### 9.2 前端构建检查

```bash
cd frontend
npm run build
```

### 9.3 后端单元测试

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/unit -q
```

## 10. 常见问题

### Q1. `alembic upgrade head` 报错 `database "... " does not exist`

这是因为你直接运行了迁移，但目标数据库还没有创建。

优先改用：

```bash
cd backend
python scripts/init_db.py
```

该脚本会自动检查并创建目标数据库，然后执行迁移。

如果仍失败，继续检查：

- PostgreSQL 服务是否已启动
- `DATABASE_URL` 中的用户是否有 `CREATE DATABASE` 权限
- 是否需要设置 `INIT_DB_ADMIN_DATABASE=template1`

### Q2. 启动后登录/注册失败

优先检查：

- `DATABASE_URL` 是否可连接
- Alembic 是否已执行到最新版本
- 后端是否确实从 `backend/` 目录启动，从而读取到了 `backend/.env`

### Q3. 前端打开但请求全部失败

检查：

- 后端是否运行在 `127.0.0.1:8000`
- 前端是否通过 `npm run dev` 启动
- Vite 代理是否指向 `/api/v1`

### Q4. 深度研究 / 综述模式无法使用

这是预期行为之一。两个模式都依赖已有的有效论文库。请先完成构建模式，至少让项目具备可用论文数据。

### Q5. 邮件相关功能不可用

当前项目的邮件功能依赖 SMTP 配置。如果未配置 SMTP，相关发送动作会失败或降级。

- 普通用户只能维护自己的收件人列表。
- SMTP Host、SMTP Port、发件邮箱和发件密码需要管理员在 `/settings` 的“系统邮件”中配置。

## 11. 参考文档

- API 设计：[docs/api.md](docs/api.md)
- 页面设计：[docs/ui_design.md](docs/ui_design.md)
- 文件映射：[docs/file_map.md](docs/file_map.md)
