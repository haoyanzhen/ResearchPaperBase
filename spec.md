# 需求规格说明书

## 文档信息

| 项目 | 内容 |
|------|------|
| 项目名称 | Paper Push Agent |
| 文档版本 | v1.0 |
| 编写日期 | 2026-04-03 |
| 编写人 | 系统设计师 |
| 审核人 | 郝彦臻 |
| 批准人 | - |

---

## 1. 引言

### 1.1 编写目的

本文档旨在详细描述Paper Push Agent系统的功能需求、非功能需求和约束条件，为系统设计、开发、测试和验收提供依据。

### 1.2 项目背景

学术研究人员需要定期跟踪相关领域的最新论文，但手动检索、筛选、下载和分析论文的过程耗时耗力。本系统旨在通过AI Agent自动化这一流程，帮助研究人员高效获取相关论文并生成分析报告。

### 1.3 定义与缩写

| 术语/缩写 | 定义 |
|-----------|------|
| LLM | Large Language Model，大语言模型 |
| RAG | Retrieval Augmented Generation，检索增强生成 |
| DOI | Digital Object Identifier，数字对象标识符 |
| API | Application Programming Interface，应用程序编程接口 |
| SOTA | State of the Art，最先进的技术 |

### 1.4 参考资料

- design.md - 系统设计文档
- LangGraph官方文档
- FastAPI官方文档
- React官方文档

---

## 2. 项目概述

### 2.1 产品目标

构建一个基于AI Agent的学术论文推送系统，能够：
- 根据研究课题自动生成检索词
- 从多个学术数据库检索论文
- 智能评分和筛选相关论文
- 自动下载和解析论文
- 生成AI分析报告
- 通过邮件推送结果

### 2.2 用户特征

| 用户类型 | 特征 | 主要需求 |
|---------|------|---------|
| 学术研究人员 | 需要跟踪最新研究进展，时间宝贵 | 自动化、准确性、可定制 |
| 研究生 | 需要收集相关文献，学习新技术 | 易用性、全面性 |
| 科研团队 | 需要共享检索结果，协作研究 | 多用户支持、数据共享 |

### 2.3 应用场景

1. **定期文献跟踪**：每周/每月自动检索和推送新论文
2. **课题研究启动**：快速收集相关领域的研究现状
3. **技术调研**：深入了解某一技术方向的研究进展
4. **论文写作辅助**：收集相关文献作为参考文献

### 2.4 运行环境

**客户端环境：**
- 操作系统：Windows 10/11, macOS, Linux
- 浏览器：Chrome 90+, Firefox 88+, Safari 14+, Edge 90+
- 网络要求：稳定的互联网连接

**服务端环境：**
- 操作系统：Linux (Ubuntu 20.04+)
- Python版本：3.10+
- 内存：最低4GB，推荐8GB+
- 存储：最低20GB，推荐50GB+
- 网络：稳定的互联网连接，用于访问外部API

---

## 3. 功能需求

### 3.1 功能需求清单

| 需求编号 | 需求名称 | 优先级 | 状态 |
|---------|---------|--------|------|
| FR-001 | 用户注册与登录 | 高 | 待开发 |
| FR-002 | 模型配置管理 | 高 | 待开发 |
| FR-003 | 论文数据库API配置 | 高 | 待开发 |
| FR-004 | 邮件配置管理 | 高 | 待开发 |
| FR-005 | 多源检索词生成 | 高 | 待开发 |
| FR-006 | 多源论文检索 | 高 | 待开发 |
| FR-007 | 智能评分与筛选 | 高 | 待开发 |
| FR-008 | PDF下载与解析 | 高 | 待开发 |
| FR-009 | AI分析生成 | 高 | 待开发 |
| FR-010 | 数据库存储 | 高 | 待开发 |
| FR-011 | 邮件发送 | 高 | 待开发 |
| FR-012 | 分步骤用户交互 | 高 | 待开发 |
| FR-013 | 检索历史查看 | 中 | 待开发 |
| FR-014 | 数据库查看与管理 | 中 | 待开发 |
| FR-015 | 任务管理 | 中 | 待开发 |
| FR-016 | 数据导出 | 低 | 待开发 |
| FR-017 | 定时任务 | 低 | 待开发 |

### 3.2 功能需求详细说明

#### FR-001 用户注册与登录

**需求描述：**
系统应提供用户注册和登录功能，支持多用户使用。

**功能要求：**
- 支持用户注册（用户名、邮箱、密码）
- 支持用户登录（用户名/邮箱 + 密码）
- 支持密码找回功能
- 支持用户信息修改
- 支持用户注销功能

**输入：**
- 用户名/邮箱
- 密码

**输出：**
- 登录成功/失败提示
- 用户信息

**验收标准：**
- 能够成功注册新用户
- 能够使用正确的凭证登录
- 错误的凭证应提示错误信息
- 密码应加密存储

#### FR-002 模型配置管理

**需求描述：**
用户应能够在设置界面配置和管理LLM模型，包括选择提供商、模型和API密钥。

**功能要求：**
- 支持多个LLM源（OpenAI、Anthropic、Gemini、deepseek、自定义url来源、本地模型ollama等）
- 支持动态获取可用模型列表
- 支持API密钥加密存储
- 支持连接测试功能
- 支持模型参数配置（温度、最大输出Token等）

**输入：**
- LLM提供商
- 模型名称
- API密钥
- API端点
- 模型参数（温度、最大Token等）

**输出：**
- 配置保存成功/失败提示
- 连接测试结果

**验收标准：**
- 能够成功配置多个LLM提供商
- API密钥应安全存储
- 连接测试应准确反映连接状态
- 配置应持久化保存

#### FR-003 论文数据库API配置

**需求描述：**
用户应能够配置各个学术数据库的API，包括端点、密钥等。

**功能要求：**
- 支持配置arXiv、OpenAlex、Semantic Scholar、Astrophysics Data System的API
- 支持自定义API端点
- 支持API密钥管理
- 支持连接状态实时监控
- 支持速率限制配置

**输入：**
- 数据库类型
- API端点
- API密钥（如需要）
- 速率限制参数

**输出：**
- 配置保存成功/失败提示
- 连接测试结果

**验收标准：**
- 能够成功配置所有支持的论文数据库
- 连接状态应实时更新
- 配置应持久化保存

#### FR-004 邮件配置管理

**需求描述：**
用户应能够配置邮件发送相关参数。

**功能要求：**
- 支持SMTP配置（服务器、端口、认证信息）
- 支持发件邮箱配置
- 支持多个接收邮箱配置
- 支持测试邮件发送
- 支持邮件模板自定义

**输入：**
- SMTP服务器地址
- SMTP端口
- 发件邮箱
- 发件邮箱密码
- 接收邮箱列表
- 邮件模板

**输出：**
- 配置保存成功/失败提示
- 测试邮件发送结果

**验收标准：**
- 能够成功配置SMTP
- 测试邮件应能够成功发送
- 配置应持久化保存

#### FR-005 多源检索词生成

**需求描述：**
系统应根据用户输入的研究课题，自动生成高覆盖率的检索词列表。

**功能要求：**
- 使用LLM生成检索词
- 按维度分类（核心概念、技术方法、评价指标等）
- 针对不同数据库生成优化的布尔表达式候选
- 每个论文数据库保留三套布尔表达式，应从候选中选择能查到大多数相关领域论文、无大量不相干论文的表达式
- 支持用户编辑和修改检索词
- 支持重新生成检索词

**输入：**
- 研究课题描述

**输出：**
- 关键词列表（按维度分类）
- 布尔表达式（针对不同数据库）

**验收标准：**
- 生成的检索词应覆盖课题的多个维度
- 布尔表达式应符合各数据库的语法
- 用户应能够编辑检索词
- 重新生成应产生不同的结果

#### FR-006 多源论文检索

**需求描述：**
系统应能够从多个学术数据库检索论文，并汇总结果。

**功能要求：**
- 支持调用多个数据库API，遵守每个API的访问用量限制
- 解析检索结果（标题、作者、出版时间、期刊、摘要等）
- 去重处理（基于DOI/ArXiv ID/小写字母的标题）
- 汇总到统一的列表中
- 支持用户手动选择访问的论文数据库

**输入：**
- 检索词/查询表达式
- 数据库列表

**输出：**
- 论文信息列表（包含元数据）

**验收标准：**
- 能够成功从所有配置的数据库检索
- 结果应正确解析
- 去重应准确

#### FR-007 智能评分与筛选

**需求描述：**
系统应对检索到的论文进行评分，筛选出高价值的论文。

**功能要求：**
- 使用LLM对论文进行评分（理论价值、技术价值）
- 评分规则：总分≥7分为有效
- 支持用户查看评分理由
- 支持用户手动调整评分
- 支持调整评分阈值
- 支持重新评分

**输入：**
- 论文元数据（标题、摘要、期刊、作者）

**输出：**
- 评分结果（总分、理论分、技术分）
- 评分理由
- 筛选结果（有效/无效）

**验收标准：**
- 评分应基于明确的规则
- 评分理由应清晰
- 用户应能够调整评分
- 筛选结果应符合阈值设定

#### FR-008 PDF下载与解析

**需求描述：**
系统应能够下载论文PDF并解析为文本信息。

**功能要求：**
- 从多个来源尝试下载PDF
- 解析PDF为文本信息
- 裁剪PDF中的图像表格
- 处理下载失败情况（记录原因，使用摘要替代）
- 支持用户手动上传PDF
- 支持重新下载
- 存储PDF和文本文件

**输入：**
- 论文元数据

**输出：**
- PDF文件路径
- 文本文件路径
- 下载状态（成功/失败）

**验收标准：**
- 能够成功下载可获取的PDF
- 解析应准确提取文本，并在合适处截断
- 失败处理应合理
- 文件应正确存储

#### FR-009 AI分析生成

**需求描述：**
系统应使用LLM对论文进行深度分析，生成总结和要点。

**功能要求：**
- 生成一句话总结
- 提取亮点解析
- 识别相关性要点
- 提取技术方法与创新
- 支持用户编辑分析内容
- 支持重新生成分析
- 支持使用不同模型

**输入：**
- 论文文本信息（全文或摘要）
- 论文图像表格等解析信息

**输出：**
- 一句话总结
- 亮点解析
- 相关性要点
- 技术方法与创新

**验收标准：**
- 分析应准确反映论文内容
- 亮点应突出
- 相关性判断应合理
- 用户应能够编辑分析

#### FR-010 数据库存储

**需求描述：**
系统应将论文数据存储到数据库中，支持增量更新。

**功能要求：**
- 存储到SQLite（关系型数据库）
- 存储到ChromaDB（向量数据库）
- 支持增量更新（基于DOI去重）
- 存储论文元数据、AI分析、文件路径等
- 支持推送状态标记

**输入：**
- 论文完整信息

**输出：**
- 存储成功/失败提示
- 数据库统计信息

**验收标准：**
- 数据应正确存储
- 去重应准确
- 推送状态应正确标记
- 数据库操作应高效

#### FR-011 邮件发送

**需求描述：**
系统应将未推送的论文通过邮件发送给用户。

**功能要求：**
- 提取未推送的论文数据
- 将元信息数据及PDF原件链接（如有）转换为HTML邮件格式
- 发送到指定接收邮箱
- 标记推送状态
- 支持定时发送
- 支持选择性发送（如仅高评分论文）

**输入：**
- 接收邮箱列表
- 邮件模板
- 发送选项

**输出：**
- 邮件发送成功/失败提示
- 发送统计信息

**验收标准：**
- 邮件应成功发送
- 格式应美观易读
- 推送状态应正确更新
- 支持定时发送

#### FR-012 分步骤用户交互

**需求描述：**
系统应在每个关键步骤暂停，让用户参与互动和修改。

**功能要求：**
- 在7个关键步骤暂停：
  1. 检索词生成后
  2. 检索与汇总后
  3. 评分与筛选后
  4. 下载与解析后
  5. 总结生成后
  6. 格式化与储存后
- 显示当前步骤的结果
- 提供编辑、修改、重新执行等操作
- 支持跳过当前步骤
- 支持继续执行后续步骤
- 实时显示执行进度

**输入：**
- 用户操作（接受、编辑、跳过、重新执行等）

**输出：**
- 当前步骤结果
- 修改后的结果
- 进度更新

**验收标准：**
- 每个关键步骤都应暂停
- 用户应能够查看和修改结果
- 操作应准确反映用户意图
- 进度应实时更新

#### FR-013 检索历史查看

**需求描述：**
用户应能够查看所有已执行的检索任务。

**功能要求：**
- 显示检索历史列表
- 显示任务基本信息（课题名称、时间、状态等）
- 显示检索统计信息（论文数量、有效数量等）
- 支持搜索和筛选
- 支持查看任务详情
- 支持重新执行任务
- 支持导出报告

**输入：**
- 搜索关键词
- 筛选条件

**输出：**
- 检索历史列表
- 任务详情信息

**验收标准：**
- 历史记录应完整
- 搜索和筛选应准确
- 详情信息应完整
- 重新执行应正常工作

#### FR-014 数据库查看与管理

**需求描述：**
用户应能够查看和管理数据库中的所有论文。

**功能要求：**
- 显示数据库统计信息
- 显示论文列表
- 支持搜索和筛选
- 支持查看论文详情
- 支持编辑论文信息
- 支持删除论文
- 支持导出数据（CSV、JSON等）
- 支持清空数据库

**输入：**
- 搜索关键词
- 筛选条件

**输出：**
- 数据库统计信息
- 论文列表
- 论文详情

**验收标准：**
- 统计信息应准确
- 搜索和筛选应准确
- 编辑和删除应正常工作
- 导出应包含所有必要信息

#### FR-015 任务管理

**需求描述：**
用户应能够创建、暂停、继续、取消任务。

**功能要求：**
- 创建新任务
- 暂停正在执行的任务
- 继续暂停的任务
- 取消任务
- 查看任务状态
- 查看任务日志

**输入：**
- 任务操作（创建、暂停、继续、取消）

**输出：**
- 任务状态更新
- 任务日志

**验收标准：**
- 任务操作应准确执行
- 状态应正确更新
- 日志应完整记录

#### FR-016 数据导出

**需求描述：**
用户应能够导出检索结果和分析报告。

**功能要求：**
- 支持导出为CSV格式
- 支持导出为JSON格式
- 支持导出为Markdown格式
- 支持导出为PDF格式
- 支持选择导出内容（全部、部分）

**输入：**
- 导出格式
- 导出内容选择

**输出：**
- 导出文件

**验收标准：**
- 导出应包含所有必要信息
- 格式应正确
- 文件应能正常打开

#### FR-017 定时任务

**需求描述：**
系统应支持定时执行检索任务。

**功能要求：**
- 支持设置定时任务（每天、每周、每月）
- 支持自定义执行时间
- 支持启用/禁用定时任务
- 支持查看定时任务列表
- 支持编辑定时任务
- 支持删除定时任务

**输入：**
- 定时规则
- 任务参数

**输出：**
- 定时任务状态

**验收标准：**
- 定时任务应准时执行
- 规则应正确解析
- 状态应正确更新

---

## 4. 非功能需求

### 4.1 性能需求

| 需求项 | 指标 | 说明 |
|--------|------|------|
| 响应时间 | < 2秒 | 页面加载时间 |
| 响应时间 | < 1秒 | API响应时间 |
| 检索速度 | < 5分钟 | 完成一次完整检索（10篇论文） |
| 并发用户 | < 20 | 支持同时在线用户数 |
| 数据处理 | ≥ 100篇 | 单次任务处理论文数量 |

### 4.2 可靠性需求

| 需求项 | 指标 | 说明 |
|--------|------|------|
| 系统可用性 | ≥ 99% | 系统正常运行时间比例 |
| 数据完整性 | 100% | 数据存储和读取无丢失 |
| 错误恢复 | 自动 | 网络错误自动重试 |
| 备份频率 | 每天 | 数据库自动备份 |

### 4.3 安全性需求

| 需求项 | 要求 | 说明 |
|--------|------|------|
| 身份认证 | 必需 | 用户登录认证 |
| 数据加密 | 必需 | API密钥加密存储 |
| 传输加密 | 必需 | HTTPS加密传输 |
| 访问控制 | 必需 | 用户只能访问自己的数据 |
| 审计日志 | 可选 | 记录关键操作 |

### 4.4 可维护性需求

| 需求项 | 要求 | 说明 |
|--------|------|------|
| 代码规范 | 必需 | 遵循编码规范 |
| 注释完整 | 必需 | 关键代码有注释 |
| 模块化 | 必需 | 功能模块独立 |
| 文档完整 | 必需 | 提供用户文档和开发文档 |

### 4.5 可扩展性需求

| 需求项 | 要求 | 说明 |
|--------|------|------|
| 数据库扩展 | 支持 | 支持切换到PostgreSQL |
| 模型扩展 | 支持 | 支持添加新的LLM提供商 |
| 数据源扩展 | 支持 | 支持添加新的学术数据库 |
| 功能扩展 | 支持 | 支持添加新功能模块 |

### 4.6 易用性需求

| 需求项 | 要求 | 说明 |
|--------|------|------|
| 界面友好 | 必需 | 直观易用的界面 |
| 操作简单 | 必需 | 核心功能操作步骤≤3步 |
| 帮助文档 | 必需 | 提供在线帮助 |
| 错误提示 | 必需 | 清晰的错误提示信息 |

---

## 5. 系统约束

### 5.1 技术约束

- 前端必须使用React + TypeScript
- 后端必须使用FastAPI
- Agent框架必须使用LangGraph
- LLM集成必须使用LiteLLM
- 数据库必须使用SQLite和ChromaDB
- 必须支持Python 3.10+

### 5.2 业务约束

- 必须支持7个关键步骤的分步交互
- 必须支持4个学术数据库（arXiv、OpenAlex、Semantic Scholar、ADS）
- 必须实现智能评分功能
- 必须实现AI分析生成
- 必须实现邮件推送功能

### 5.3 法律约束

- 遵守各学术数据库的API使用条款
- 遵守数据隐私保护法规
- 遵守版权法（论文下载和使用）

### 5.4 时间约束

- 项目开发周期：3个月
- 里程碑：
  - 第1个月：基础架构和核心Agent功能
  - 第2个月：用户界面和交互功能
  - 第3个月：测试、优化和部署

### 5.5 资源约束

- 开发团队：2-3人
- 服务器资源：单机部署，8GB内存，50GB存储
- LLM API预算：每月≤$100

---

## 6. 数据需求

### 6.1 数据字典

#### 用户表 (users)

**说明**：存储系统用户基本信息，每个用户唯一。

| 字段名 | 类型 | 长度 | 必填 | 约束 | 说明 |
|--------|------|------|------|------|------|
| id | VARCHAR | 50 | 是 | PRIMARY KEY | 用户唯一标识符 |
| username | VARCHAR | 50 | 是 | UNIQUE | 用户名，全局唯一 |
| email | VARCHAR | 100 | 是 | UNIQUE | 邮箱，全局唯一 |
| password_hash | VARCHAR | 255 | 是 | - | 密码哈希值 |
| created_at | DATETIME | - | 是 | - | 创建时间 |
| updated_at | DATETIME | - | 是 | - | 最后更新时间 |
| last_login_at | DATETIME | - | 否 | - | 最后登录时间 |

**索引**：
- PRIMARY KEY (id)
- UNIQUE INDEX idx_username (username)
- UNIQUE INDEX idx_email (email)
- INDEX idx_created_at (created_at)

---

#### 用户配置表 (user_configs)

**说明**：存储用户相关的配置信息，包括系统默认配置和用户自定义配置。每一行保存一个配置项，每个配置项唯一。

| 字段名 | 类型 | 长度 | 必填 | 约束 | 说明 |
|--------|------|------|------|------|------|
| id | VARCHAR | 50 | 是 | PRIMARY KEY | 配置唯一标识符 |
| user_id | VARCHAR | 50 | 是 | FOREIGN KEY | 用户ID，关联users表 |
| config_name | VARCHAR | 100 | 是 | - | 配置名称（如：llm.model、database.arxiv.endpoint等） |
| config_value | TEXT | 是 | - | 配置值（JSON格式存储复杂配置） |
| is_system_default | BOOLEAN | - | DEFAULT FALSE | 是否为系统默认配置 |
| created_at | DATETIME | - | 是 | - | 创建时间 |
| updated_at | DATETIME | - | 是 | - | 最后更新时间 |

**约束**：
- PRIMARY KEY (id)
- FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
- UNIQUE INDEX idx_user_config (user_id, config_name)

**配置示例**：
```
config_name: llm.provider.deepseek.url
config_value: {"url":"https://api.deepseek.com/v1", "api_key": "***"}

config_name: email.smtp.host
config_value: "smtp.gmail.com"

config_name: email.recipients
config_value: ["user1@example.com", "user2@example.com"]
```

---

#### 课题任务表 (research_topics)

**说明**：存储用户创建的各个研究课题及其执行进展，每个课题唯一。

| 字段名 | 类型 | 长度 | 必填 | 约束 | 说明 |
|--------|------|------|------|------|------|
| id | VARCHAR | 50 | 是 | PRIMARY KEY | 课题唯一标识符 |
| user_id | VARCHAR | 50 | 是 | FOREIGN KEY | 用户ID，关联users表 |
| name | VARCHAR | 200 | 是 | - | 课题名称 |
| description | TEXT | 否 | - | 课题描述 |
| status | VARCHAR | 20 | 是 | - | 状态（draft/pending/running/paused/completed/failed） |
| current_stage | INTEGER | - | DEFAULT 1 | 当前执行阶段（1-7） |
| total_papers | INTEGER | - | DEFAULT 0 | 总论文数 |
| valid_papers | INTEGER | - | DEFAULT 0 | 有效论文数 |
| push_status | VARCHAR | 20 | - | DEFAULT "not_pushed" | 推送状态（not_pushed/pushed/failed） |
| created_at | DATETIME | - | 是 | - | 创建时间 |
| updated_at | DATETIME | - | 是 | - | 最后更新时间 |
| completed_at | DATETIME | - | 否 | - | 完成时间 |

**约束**：
- PRIMARY KEY (id)
- FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
- INDEX idx_user_id (user_id)
- INDEX idx_status (status)
- INDEX idx_created_at (created_at)

**执行阶段说明**：
- 1: 检索词生成
- 2: 检索与汇总
- 3: 评分与筛选
- 4: 下载与解析
- 5: 总结生成
- 6: 格式化与储存
- 7: 邮件发送

---

#### 检索词表 (keywords)

**说明**：存储每个课题的检索词，每一行为一个检索词，支持多个数据库的布尔表达式。

| 字段名 | 类型 | 长度 | 必填 | 约束 | 说明 |
|--------|------|------|------|------|------|
| id | VARCHAR | 50 | 是 | PRIMARY KEY | 检索词唯一标识符 |
| topic_id | VARCHAR | 50 | 是 | FOREIGN KEY | 课题ID，关联research_topics表 |
| dimension | VARCHAR | 50 | 是 | - | 维度（core_concept/technical_method/metric/upper_term/lower_term） |
| keyword | VARCHAR | 500 | 是 | - | 关键词 |
| boolean_expressions | JSON | - | - | 各数据库的布尔表达式 |
| is_selected | BOOLEAN | - | DEFAULT TRUE | 是否被选中使用 |
| created_at | DATETIME | - | 是 | - | 创建时间 |
| updated_at | DATETIME | - | 是 | - | 最后更新时间 |

**约束**：
- PRIMARY KEY (id)
- FOREIGN KEY (topic_id) REFERENCES research_topics(id) ON DELETE CASCADE
- INDEX idx_topic_id (topic_id)
- INDEX idx_dimension (dimension)

**boolean_expressions示例**：
```json
{
  "arxiv": "deep learning AND medical imaging",
  "openalex": "(deep learning OR CNN) AND medical imaging",
  "semantic_scholar": "deep learning AND medical imaging",
  "ads": "deep learning AND medical AND imaging"
}
```

---

#### 论文表 (papers)

**说明**：存储所有论文的元数据，每篇论文唯一，支持多课题关联。

| 字段名 | 类型 | 长度 | 必填 | 约束 | 说明 |
|--------|------|------|------|------|------|
| id | VARCHAR | 50 | 是 | PRIMARY KEY | 论文唯一标识符 |
| doi | VARCHAR | 100 | 否 | UNIQUE | DOI，数字对象标识符 |
| arxiv_id | VARCHAR | 50 | 否 | UNIQUE | ArXiv ID |
| title | TEXT | 是 | - | 论文标题 |
| authors | TEXT | 否 | - | 作者列表（JSON格式） |
| pub_date | DATE | 否 | - | 发布日期 |
| venue | VARCHAR | 200 | 否 | - | 期刊/会议名称 |
| abstract | TEXT | 否 | - | 摘要 |
| source | VARCHAR | 50 | 否 | - | 检索来源（arxiv/openalex/semantic_scholar/ads） |
| retrieved_at | DATETIME | - | 是 | - | 检索时间 |
| pdf_path | VARCHAR | 500 | 否 | - | PDF文件本地路径 |
| text_path | VARCHAR | 500 | 否 | - | 文本文件本地路径 |
| download_status | VARCHAR | 20 | - | DEFAULT "not_downloaded" | 下载状态（not_downloaded/downloading/success/failed） |
| download_error | TEXT | 否 | - | 下载错误信息 |
| ai_analysis | JSON | 否 | - | AI分析结果 |
| ai_analysis_status | VARCHAR | 20 | - | DEFAULT "not_analyzed" | AI分析状态（not_analyzed/analyzing/success/failed） |
| created_at | DATETIME | - | 是 | - | 创建时间 |
| updated_at | DATETIME | - | 是 | - | 最后更新时间 |

**约束**：
- PRIMARY KEY (id)
- UNIQUE INDEX idx_doi (doi)
- UNIQUE INDEX idx_arxiv_id (arxiv_id)
- INDEX idx_title (title)
- INDEX idx_pub_date (pub_date)
- INDEX idx_source (source)

**ai_analysis示例**：
```json
{
  "summary": "提出了一种新的多尺度CNN框架用于医学影像分割",
  "highlights": ["多尺度特征融合", "注意力机制", "SOTA性能"],
  "relevance_points": ["高度相关，技术可直接借鉴"],
  "technical_methods": ["MS-CNN架构", "自适应注意力机制", "混合损失函数"],
  "generated_at": "2026-02-18T15:30:00Z",
  "model_used": "gpt-4-turbo"
}
```

---

#### 课题-论文关联表 (topic_paper_relations)

**说明**：保存课题与论文的关联关系以及论文在该课题中的评分和状态。

| 字段名 | 类型 | 长度 | 必填 | 约束 | 说明 |
|--------|------|------|------|------|------|
| id | VARCHAR | 50 | 是 | PRIMARY KEY | 关联唯一标识符 |
| topic_id | VARCHAR | 50 | 是 | FOREIGN KEY | 课题ID，关联research_topics表 |
| paper_id | VARCHAR | 50 | 是 | FOREIGN KEY | 论文ID，关联papers表 |
| reference_score | INTEGER | - | - | 参考价值评分（0-5） |
| technical_score | INTEGER | - | - | 技术价值评分（0-5） |
| total_score | INTEGER | - | - | 总分（0-10） |
| scoring_reason | TEXT | 否 | - | 评分理由 |
| is_valid | BOOLEAN | - | DEFAULT TRUE | 是否有效（总分≥7） |
| push_status | BOOLEAN | - | DEFAULT FALSE | 是否已推送给该课题 |
| pushed_at | DATETIME | - | 否 | - | 推送时间 |
| created_at | DATETIME | - | 是 | - | 创建时间 |
| updated_at | DATETIME | - | 是 | - | 最后更新时间 |

**约束**：
- PRIMARY KEY (id)
- FOREIGN KEY (topic_id) REFERENCES research_topics(id) ON DELETE CASCADE
- FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
- UNIQUE INDEX idx_topic_paper (topic_id, paper_id)
- INDEX idx_topic_id (topic_id)
- INDEX idx_paper_id (paper_id)
- INDEX idx_is_valid (is_valid)
- INDEX idx_push_status (push_status)

---

#### 阶段记录表 (stage_records)

**说明**：记录课题各执行阶段的详细信息。

| 字段名 | 类型 | 长度 | 必填 | 约束 | 说明 |
|--------|------|------|------|------|------|
| id | VARCHAR | 50 | 是 | PRIMARY KEY | 记录唯一标识符 |
| topic_id | VARCHAR | 50 | 是 | FOREIGN KEY | 课题ID，关联research_topics表 |
| stage | INTEGER | 是 | - | 执行阶段（1-7） |
| status | VARCHAR | 20 | 是 | - | 状态（running/paused/completed/failed） |
| started_at | DATETIME | - | 是 | - | 开始时间 |
| completed_at | DATETIME | - | 否 | - | 完成时间 |
| paused_at | DATETIME | - | 否 | - | 暂停时间 |
| resumed_at | DATETIME | - | 否 | - | 恢复时间 |
| failed_at | DATETIME | - | 否 | - | 失败时间 |
| result | JSON | - | 否 | - | 阶段结果数据 |
| error | TEXT | 否 | - | 错误信息 |
| user_actions | JSON | - | 否 | - | 用户操作记录 |
| created_at | DATETIME | - | 是 | - | 创建时间 |

**约束**：
- PRIMARY KEY (id)
- FOREIGN KEY (topic_id) REFERENCES research_topics(id) ON DELETE CASCADE
- INDEX idx_topic_id (topic_id)
- INDEX idx_stage (stage)
- INDEX idx_status (status)

---

#### 定时任务表 (scheduled_tasks)

**说明**：存储用户的定时任务配置。

| 字段名 | 类型 | 长度 | 必填 | 约束 | 说明 |
|--------|------|------|------|------|------|
| id | VARCHAR | 50 | 是 | PRIMARY KEY | 定时任务唯一标识符 |
| user_id | VARCHAR | 50 | 是 | FOREIGN KEY | 用户ID，关联users表 |
| name | VARCHAR | 200 | 是 | - | 任务名称 |
| topic_description | TEXT | 是 | - | 研究课题描述 |
| schedule_type | VARCHAR | 20 | 是 | - | 调度类型（daily/weekly/monthly） |
| schedule_time | TIME | 是 | - | 调度时间 |
| enabled | BOOLEAN | - | DEFAULT TRUE | 是否启用 |
| last_run_at | DATETIME | - | 否 | - | 上次运行时间 |
| next_run_at | DATETIME | - | 否 | - | 下次运行时间 |
| created_at | DATETIME | - | 是 | - | 创建时间 |
| updated_at | DATETIME | - | 是 | - | 最后更新时间 |

**约束**：
- PRIMARY KEY (id)
- FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
- INDEX idx_user_id (user_id)
- INDEX idx_enabled (enabled)
- INDEX idx_next_run_at (next_run_at)

---

### 6.2 数据库关系图

```
users (用户表)
    ↓ 1:N
user_configs (用户配置表)

users (用户表)
    ↓ 1:N
research_topics (课题任务表)
    ↓ 1:N
keywords (检索词表)

research_topics (课题任务表)
    ↓ 1:N
stage_records (阶段记录表)

research_topics (课题任务表)
    ↓ 1:N
scheduled_tasks (定时任务表)

papers (论文表)
    ↓ 1:N
topic_paper_relations (课题-论文关联表)
    ↑ N:1
research_topics (课题任务表)
```

---

### 6.3 数据字典说明

#### 6.3.1 设计原则

1. **用户隔离**：所有用户数据通过user_id关联，确保多用户数据隔离
2. **配置灵活**：user_configs表采用键值对方式存储配置，支持动态扩展
3. **论文复用**：papers表独立存储论文元数据，通过关联表实现多课题共享
4. **状态追踪**：每个课题都有完整的阶段记录，支持执行过程追踪
5. **评分独立**：论文评分存储在关联表中，同一论文在不同课题中可有不同评分

#### 6.3.2 数据一致性保证

1. **外键约束**：所有关联表都使用外键约束确保数据完整性
2. **级联删除**：用户删除时，级联删除其所有相关数据
3. **唯一约束**：关键字段（如DOI、ArXiv ID）设置唯一约束避免重复
4. **索引优化**：为常用查询字段创建索引，提高查询性能

#### 6.3.3 配置管理策略

1. **系统默认配置**：is_system_default=TRUE的配置为系统默认值
2. **用户自定义配置**：用户可覆盖默认配置，优先使用用户配置
3. **配置加载顺序**：用户配置 > 系统默认配置
4. **配置分类**：通过config_name的命名约定实现配置分类（如llm.xxx、database.xxx、email.xxx）

### 6.2 数据流图

```
用户输入课题
    ↓
生成检索词
    ↓
检索论文（4个数据库）
    ↓
汇总论文列表
    ↓
评分筛选
    ↓
下载PDF
    ↓
解析文本
    ↓
AI分析
    ↓
存储到数据库
    ↓
发送邮件
    ↓
完成
```

---

## 7. 接口需求

### 7.1 用户接口

| 接口名称 | 功能描述 |
|---------|---------|
| 登录页面 | 用户登录 |
| 注册页面 | 用户注册 |
| 配置页面 | 模型、API、邮件配置 |
| 任务创建页面 | 创建新检索任务 |
| 任务执行页面 | 执行任务，显示进度 |
| 检索历史页面 | 查看历史任务 |
| 数据库查看页面 | 查看和管理数据库 |
| 任务详情页面 | 查看任务详情 |

### 7.2 外部接口

#### arXiv API

| 接口 | 功能 |
|------|------|
| GET /api/query | 检索论文 |

#### OpenAlex API

| 接口 | 功能 |
|------|------|
| GET /works | 检索论文 |

#### Semantic Scholar API

| 接口 | 功能 |
|------|------|
| GET /graph/v1/paper/search | 检索论文 |

#### Astrophysics Data System API

| 接口 | 功能 |
|------|------|
| GET /search/query | 检索论文 |

#### LLM API（通过LiteLLM）

| 接口 | 功能 |
|------|------|
| POST /v1/chat/completions | 聊天完成 |

### 7.3 内部接口

| 接口 | 功能 |
|------|------|
| POST /api/auth/register | 用户注册 |
| POST /api/auth/login | 用户登录 |
| POST /api/config/llm | 保存LLM配置 |
| POST /api/config/database | 保存数据库配置 |
| POST /api/config/email | 保存邮件配置 |
| POST /api/tasks/create | 创建任务 |
| POST /api/tasks/{id}/pause | 暂停任务 |
| POST /api/tasks/{id}/resume | 继续任务 |
| POST /api/tasks/{id}/cancel | 取消任务 |
| GET /api/tasks | 获取任务列表 |
| GET /api/tasks/{id} | 获取任务详情 |
| POST /api/tasks/{id}/step/confirm | 确认当前步骤 |
| POST /api/tasks/{id}/step/edit | 编辑当前步骤 |
| GET /api/papers | 获取论文列表 |
| GET /api/papers/{id} | 获取论文详情 |
| DELETE /api/papers/{id} | 删除论文 |
| POST /api/export | 导出数据 |
| POST /api/scheduled-tasks | 创建定时任务 |
| GET /api/scheduled-tasks | 获取定时任务列表 |

---

## 8. 底层设计

### 8.1 设计原则

本系统以**科学研究主题（Research Topic）**为核心单元进行底层设计，所有状态管理、生命周期管理和接口协议均围绕科学研究主题展开，确保系统的一致性和可维护性。

### 8.2 核心数据模型

#### 8.2.1 科学研究主题（Research Topic）

科学研究主题是系统的核心实体，包含一个完整的研究任务从创建到完成的全生命周期信息。

```python
class ResearchTopic:
    """
    科学研究主题核心数据模型
    """
    # 基础信息
    id: str                          # 唯一标识符
    user_id: str                     # 所属用户ID
    name: str                        # 主题名称
    description: str                 # 主题描述

    # 生命周期管理
    status: TopicStatus              # 当前状态
    created_at: datetime             # 创建时间
    updated_at: datetime             # 最后更新时间
    completed_at: Optional[datetime] # 完成时间

    # 执行流程状态
    current_stage: ExecutionStage    # 当前执行阶段
    stage_history: List[StageRecord] # 阶段历史记录

    # 检索配置
    retrieval_config: RetrievalConfig  # 检索配置

    # 结果数据
    keywords: List[Keyword]          # 生成的检索词
    papers: List[Paper]              # 检索到的论文
    analysis_results: List[AnalysisResult]  # AI分析结果

    # 推送信息
    push_config: PushConfig          # 推送配置
    push_status: PushStatus          # 推送状态

class TopicStatus(Enum):
    """主题状态"""
    DRAFT = "draft"              # 草稿
    PENDING = "pending"          # 等待执行
    RUNNING = "running"          # 执行中
    PAUSED = "paused"            # 已暂停
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 失败

class ExecutionStage(Enum):
    """执行阶段"""
    STAGE_1_KEYWORD_GENERATION = 1      # 检索词生成
    STAGE_2_RETRIEVAL = 2               # 检索与汇总
    STAGE_3_SCORING = 3                 # 评分与筛选
    STAGE_4_DOWNLOAD = 4                # 下载与解析
    STAGE_5_ANALYSIS = 5                # 总结生成
    STAGE_6_STORAGE = 6                 # 格式化与储存
    STAGE_7_EMAIL = 7                   # 邮件发送

class StageRecord:
    """阶段记录"""
    stage: ExecutionStage               # 阶段
    status: str                         # 状态
    started_at: datetime                # 开始时间
    completed_at: Optional[datetime]    # 完成时间
    result: Optional[dict]              # 结果数据
    error: Optional[str]                # 错误信息
    user_actions: List[UserAction]      # 用户操作记录
```

#### 8.2.2 检索配置（RetrievalConfig）

针对科学研究主题的检索配置，包含所有检索相关的参数和设置。

```python
class RetrievalConfig:
    """检索配置"""
    # 检索词配置
    keywords: List[Keyword]             # 检索词列表
    keyword_generation_config: KeywordGenerationConfig  # 检索词生成配置

    # 数据库配置
    database_configs: Dict[str, DatabaseConfig]  # 数据库配置
    enabled_databases: List[str]       # 启用的数据库列表

    # 评分配置
    scoring_config: ScoringConfig      # 评分配置

    # 下载配置
    download_config: DownloadConfig    # 下载配置

class Keyword:
    """检索词"""
    id: str                            # 唯一标识符
    topic_id: str                      # 所属主题ID
    dimension: str                     # 维度（核心概念/技术方法/评价指标等）
    keyword: str                       # 关键词
    boolean_expressions: Dict[str, str]  # 布尔表达式（按数据库）

class DatabaseConfig:
    """数据库配置"""
    database_type: str                 # 数据库类型
    api_endpoint: str                  # API端点
    api_key: Optional[str]             # API密钥
    rate_limit: int                    # 速率限制
    timeout: int                       # 超时时间
    retry_config: RetryConfig          # 重试配置
```

#### 8.2.3 论文数据（Paper）

论文数据与科学研究主题关联，所有论文都归属于特定的研究主题。

```python
class Paper:
    """论文数据"""
    # 唯一标识
    id: str                            # 唯一标识符
    topic_id: str                      # 所属主题ID

    # 元数据
    doi: Optional[str]                 # DOI
    arxiv_id: Optional[str]            # ArXiv ID
    title: str                         # 标题
    authors: List[str]                 # 作者
    pub_date: Optional[date]           # 发布日期
    venue: Optional[str]               # 期刊/会议
    abstract: Optional[str]            # 摘要

    # 检索来源
    source: str                        # 检索来源
    retrieved_at: datetime             # 检索时间

    # 评分信息
    reference_score: Optional[int]     # 参考价值评分
    technical_score: Optional[int]     # 技术价值评分
    total_score: Optional[int]         # 总分
    scoring_reason: Optional[str]      # 评分理由
    is_valid: Optional[bool]           # 是否有效

    # 下载信息
    pdf_path: Optional[str]            # PDF路径
    text_path: Optional[str]           # 文本路径
    download_status: str               # 下载状态
    download_error: Optional[str]      # 下载错误

    # 分析信息
    ai_analysis: Optional[AIAnalysis]  # AI分析结果

    # 推送信息
    push_status: bool                  # 推送状态
    pushed_at: Optional[datetime]      # 推送时间

class AIAnalysis:
    """AI分析结果"""
    paper_id: str                      # 论文ID
    summary: str                       # 一句话总结
    highlights: List[str]              # 亮点解析
    relevance_points: List[str]        # 相关性要点
    technical_methods: List[str]       # 技术方法与创新
    generated_at: datetime             # 生成时间
    model_used: str                    # 使用的模型
```

### 8.3 状态管理设计

#### 8.3.1 状态管理架构

采用集中式状态管理，以ResearchTopic为核心，通过状态机管理主题的生命周期。

```
┌─────────────────────────────────────────────────────────────┐
│                    状态管理层                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ResearchTopicStateManager                           │  │
│  │  - 管理ResearchTopic的状态转换                        │  │
│  │  - 维护主题的生命周期                                  │  │
│  │  - 协调各阶段的状态同步                                │  │
│  └──────────────────────────────────────────────────────┘  │
│                    ↓                                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  StageStateManager                                   │  │
│  │  - 管理执行阶段的状态                                  │  │
│  │  - 处理阶段间的转换                                    │  │
│  │  - 维护阶段历史记录                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                    ↓                                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  DataStateManager                                    │  │
│  │  - 管理论文数据的状态                                  │  │
│  │  - 维护检索词、分析结果等数据                          │  │
│  │  - 处理数据的增量更新                                  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

#### 8.3.2 主题状态机

```
                    ┌─────────┐
                    │  DRAFT  │
                    └────┬────┘
                         │ create
                         ↓
                    ┌─────────┐
                    │ PENDING │
                    └────┬────┘
                         │ start
                         ↓
                    ┌─────────┐
                    │ RUNNING │◄──────┐
                    └────┬────┘       │
              pause /  │   \  resume  │
                 ↓     │    ↓        │
            ┌────────┐ │  ┌────────┐ │
            │ PAUSED │ │  │ RUNNING│ │
            └───┬────┘ │  └────────┘ │
                │     │              │
                │     │ complete/fail│
                │     ↓              │
                │  ┌─────────┐       │
                │  │COMPLETED│       │
                │  └─────────┘       │
                │  ┌─────────┐       │
                └─►│ FAILED  │───────┘
                   └─────────┘
```

#### 8.3.3 阶段状态管理

每个执行阶段都有独立的状态管理，支持暂停、继续、重试等操作。

```python
class StageStateManager:
    """阶段状态管理器"""

    def __init__(self, topic_id: str):
        self.topic_id = topic_id
        self.current_stage = None
        self.stage_states = {}

    def start_stage(self, stage: ExecutionStage) -> StageState:
        """开始执行阶段"""
        stage_state = StageState(
            stage=stage,
            status="running",
            started_at=datetime.now()
        )
        self.stage_states[stage] = stage_state
        self.current_stage = stage
        return stage_state

    def pause_stage(self, stage: ExecutionStage) -> StageState:
        """暂停阶段"""
        stage_state = self.stage_states[stage]
        stage_state.status = "paused"
        stage_state.paused_at = datetime.now()
        return stage_state

    def resume_stage(self, stage: ExecutionStage) -> StageState:
        """继续阶段"""
        stage_state = self.stage_states[stage]
        stage_state.status = "running"
        stage_state.resumed_at = datetime.now()
        return stage_state

    def complete_stage(self, stage: ExecutionStage, result: dict) -> StageState:
        """完成阶段"""
        stage_state = self.stage_states[stage]
        stage_state.status = "completed"
        stage_state.completed_at = datetime.now()
        stage_state.result = result
        return stage_state

    def fail_stage(self, stage: ExecutionStage, error: str) -> StageState:
        """阶段失败"""
        stage_state = self.stage_states[stage]
        stage_state.status = "failed"
        stage_state.failed_at = datetime.now()
        stage_state.error = error
        return stage_state

class StageState:
    """阶段状态"""
    stage: ExecutionStage               # 阶段
    status: str                         # 状态（running/paused/completed/failed）
    started_at: datetime                # 开始时间
    paused_at: Optional[datetime]       # 暂停时间
    resumed_at: Optional[datetime]      # 恢复时间
    completed_at: Optional[datetime]    # 完成时间
    failed_at: Optional[datetime]       # 失败时间
    result: Optional[dict]              # 结果
    error: Optional[str]                # 错误信息
    user_actions: List[UserAction]      # 用户操作
```

### 8.4 生命周期管理

#### 8.4.1 主题生命周期

```python
class ResearchTopicLifecycle:
    """科学研究主题生命周期管理"""

    def __init__(self, topic: ResearchTopic):
        self.topic = topic
        self.state_manager = ResearchTopicStateManager(topic.id)
        self.stage_manager = StageStateManager(topic.id)

    def create(self) -> ResearchTopic:
        """创建主题"""
        self.topic.status = TopicStatus.DRAFT
        self.topic.created_at = datetime.now()
        self.topic.updated_at = datetime.now()
        return self.topic

    def start(self) -> ResearchTopic:
        """开始执行"""
        self._validate_config()
        self.topic.status = TopicStatus.RUNNING
        self.topic.current_stage = ExecutionStage.STAGE_1_KEYWORD_GENERATION
        self.topic.updated_at = datetime.now()
        return self.topic

    def pause(self) -> ResearchTopic:
        """暂停执行"""
        self.topic.status = TopicStatus.PAUSED
        self.stage_manager.pause_stage(self.topic.current_stage)
        self.topic.updated_at = datetime.now()
        return self.topic

    def resume(self) -> ResearchTopic:
        """继续执行"""
        self.topic.status = TopicStatus.RUNNING
        self.stage_manager.resume_stage(self.topic.current_stage)
        self.topic.updated_at = datetime.now()
        return self.topic

    def complete(self) -> ResearchTopic:
        """完成执行"""
        self.topic.status = TopicStatus.COMPLETED
        self.topic.completed_at = datetime.now()
        self.topic.updated_at = datetime.now()
        return self.topic

    def fail(self, error: str) -> ResearchTopic:
        """执行失败"""
        self.topic.status = TopicStatus.FAILED
        self.stage_manager.fail_stage(self.topic.current_stage, error)
        self.topic.updated_at = datetime.now()
        return self.topic

    def advance_stage(self) -> ExecutionStage:
        """推进到下一阶段"""
        current_stage_value = self.topic.current_stage.value
        if current_stage_value < 7:
            next_stage = ExecutionStage(current_stage_value + 1)
            self.topic.current_stage = next_stage
            self.topic.updated_at = datetime.now()
            return next_stage
        raise ValueError("Already at final stage")
```

#### 8.4.2 数据生命周期

```python
class PaperDataLifecycle:
    """论文数据生命周期管理"""

    def __init__(self, paper: Paper):
        self.paper = paper

    def retrieve(self, source: str) -> Paper:
        """检索论文"""
        self.paper.source = source
        self.paper.retrieved_at = datetime.now()
        return self.paper

    def score(self, ref_score: int, tech_score: int, reason: str) -> Paper:
        """评分"""
        self.paper.reference_score = ref_score
        self.paper.technical_score = tech_score
        self.paper.total_score = ref_score + tech_score
        self.paper.scoring_reason = reason
        self.paper.is_valid = self.paper.total_score >= 7
        return self.paper

    def download(self, pdf_path: str, text_path: str) -> Paper:
        """下载和解析"""
        self.paper.pdf_path = pdf_path
        self.paper.text_path = text_path
        self.paper.download_status = "success"
        return self.paper

    def analyze(self, analysis: AIAnalysis) -> Paper:
        """AI分析"""
        self.paper.ai_analysis = analysis
        return self.paper

    def push(self) -> Paper:
        """推送"""
        self.paper.push_status = True
        self.paper.pushed_at = datetime.now()
        return self.paper
```

### 8.5 接口协议设计

#### 8.5.1 主题管理接口

所有主题管理接口都围绕ResearchTopic展开。

```python
# 创建主题
POST /api/topics
Request:
{
    "name": "深度学习在医学影像分析中的应用研究",
    "description": "研究深度学习技术在医学影像分析中的应用..."
}
Response:
{
    "topic_id": "topic_123",
    "status": "draft",
    "created_at": "2026-02-18T14:30:00Z"
}

# 获取主题
GET /api/topics/{topic_id}
Response:
{
    "id": "topic_123",
    "name": "深度学习在医学影像分析中的应用研究",
    "description": "研究深度学习技术在医学影像分析中的应用...",
    "status": "running",
    "current_stage": 3,
    "stage_history": [...],
    "keywords": [...],
    "papers": [...],
    "created_at": "2026-02-18T14:30:00Z",
    "updated_at": "2026-02-18T15:00:00Z"
}

# 更新主题配置
PUT /api/topics/{topic_id}/config
Request:
{
    "retrieval_config": {...},
    "push_config": {...}
}
Response:
{
    "topic_id": "topic_123",
    "updated_at": "2026-02-18T15:30:00Z"
}

# 开始执行主题
POST /api/topics/{topic_id}/start
Response:
{
    "topic_id": "topic_123",
    "status": "running",
    "current_stage": 1,
    "started_at": "2026-02-18T15:00:00Z"
}

# 暂停主题执行
POST /api/topics/{topic_id}/pause
Response:
{
    "topic_id": "topic_123",
    "status": "paused",
    "current_stage": 3,
    "paused_at": "2026-02-18T15:30:00Z"
}

# 继续主题执行
POST /api/topics/{topic_id}/resume
Response:
{
    "topic_id": "topic_123",
    "status": "running",
    "current_stage": 3,
    "resumed_at": "2026-02-18T16:00:00Z"
}

# 取消主题执行
POST /api/topics/{topic_id}/cancel
Response:
{
    "topic_id": "topic_123",
    "status": "cancelled",
    "cancelled_at": "2026-02-18T16:30:00Z"
}

# 删除主题
DELETE /api/topics/{topic_id}
Response:
{
    "topic_id": "topic_123",
    "deleted_at": "2026-02-18T17:00:00Z"
}
```

#### 8.5.2 阶段交互接口

每个阶段的交互接口都包含主题ID作为核心参数。

```python
# 确认当前阶段
POST /api/topics/{topic_id}/stages/{stage}/confirm
Request:
{
    "action": "confirm"
}
Response:
{
    "topic_id": "topic_123",
    "stage": 3,
    "status": "completed",
    "next_stage": 4
}

# 编辑当前阶段数据
POST /api/topics/{topic_id}/stages/{stage}/edit
Request:
{
    "data": {
        "keywords": [...],
        "papers": [...]
    }
}
Response:
{
    "topic_id": "topic_123",
    "stage": 3,
    "updated_data": {...}
}

# 重新执行当前阶段
POST /api/topics/{topic_id}/stages/{stage}/retry
Response:
{
    "topic_id": "topic_123",
    "stage": 3,
    "status": "running",
    "retried_at": "2026-02-18T16:00:00Z"
}

# 跳过当前阶段
POST /api/topics/{topic_id}/stages/{stage}/skip
Response:
{
    "topic_id": "topic_123",
    "stage": 3,
    "status": "skipped",
    "next_stage": 4
}

# 获取阶段详情
GET /api/topics/{topic_id}/stages/{stage}
Response:
{
    "topic_id": "topic_123",
    "stage": 3,
    "status": "completed",
    "started_at": "2026-02-18T14:00:00Z",
    "completed_at": "2026-02-18T14:30:00Z",
    "result": {...},
    "user_actions": [...]
}
```

#### 8.5.3 数据查询接口

所有数据查询接口都支持按主题ID过滤。

```python
# 获取主题的论文列表
GET /api/topics/{topic_id}/papers?status=valid&sort_by=score
Response:
{
    "topic_id": "topic_123",
    "papers": [...],
    "total": 12,
    "valid": 12,
    "invalid": 3
}

# 获取主题的检索词
GET /api/topics/{topic_id}/keywords
Response:
{
    "topic_id": "topic_123",
    "keywords": [
        {
            "dimension": "核心概念",
            "keywords": ["deep learning", "medical imaging"],
            "boolean_expressions": {
                "arxiv": "deep learning AND medical imaging",
                "openalex": "(deep learning OR CNN) AND medical imaging"
            }
        }
    ]
}

# 获取主题的分析结果
GET /api/topics/{topic_id}/analysis
Response:
{
    "topic_id": "topic_123",
    "analysis_results": [...],
    "total_analyzed": 12,
    "avg_score": 8.5
}
```

### 8.6 数据库设计优化

基于科学研究主题核心单元，优化数据库表结构。

#### 8.6.1 主题表（research_topics）

```sql
CREATE TABLE research_topics (
    id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL,
    current_stage INTEGER,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    completed_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
);
```

#### 8.6.2 阶段记录表（stage_records）

```sql
CREATE TABLE stage_records (
    id VARCHAR(50) PRIMARY KEY,
    topic_id VARCHAR(50) NOT NULL,
    stage INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    started_at DATETIME NOT NULL,
    completed_at DATETIME,
    paused_at DATETIME,
    resumed_at DATETIME,
    failed_at DATETIME,
    result JSON,
    error TEXT,
    FOREIGN KEY (topic_id) REFERENCES research_topics(id),
    INDEX idx_topic_id (topic_id),
    INDEX idx_stage (stage)
);
```

#### 8.6.3 论文表（papers）

```sql
CREATE TABLE papers (
    id VARCHAR(50) PRIMARY KEY,
    topic_id VARCHAR(50) NOT NULL,
    doi VARCHAR(100) UNIQUE,
    arxiv_id VARCHAR(50),
    title TEXT NOT NULL,
    authors TEXT,
    pub_date DATE,
    venue VARCHAR(200),
    abstract TEXT,
    source VARCHAR(50),
    retrieved_at DATETIME,
    reference_score INTEGER,
    technical_score INTEGER,
    total_score INTEGER,
    scoring_reason TEXT,
    is_valid BOOLEAN,
    pdf_path VARCHAR(500),
    text_path VARCHAR(500),
    download_status VARCHAR(20),
    download_error TEXT,
    ai_analysis JSON,
    push_status BOOLEAN DEFAULT FALSE,
    pushed_at DATETIME,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (topic_id) REFERENCES research_topics(id),
    INDEX idx_topic_id (topic_id),
    INDEX idx_doi (doi),
    INDEX idx_is_valid (is_valid),
    INDEX idx_push_status (push_status)
);
```

#### 8.6.4 检索词表（keywords）

```sql
CREATE TABLE keywords (
    id VARCHAR(50) PRIMARY KEY,
    topic_id VARCHAR(50) NOT NULL,
    dimension VARCHAR(50) NOT NULL,
    keyword VARCHAR(200) NOT NULL,
    boolean_expressions JSON,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (topic_id) REFERENCES research_topics(id),
    INDEX idx_topic_id (topic_id),
    INDEX idx_dimension (dimension)
);
```

### 8.7 数据一致性保证

#### 8.7.1 事务管理

所有涉及ResearchTopic的操作都使用事务保证数据一致性。

```python
class ResearchTopicTransaction:
    """主题事务管理器"""

    def __init__(self, db_session):
        self.db_session = db_session

    def create_topic_with_config(self, topic_data: dict, config_data: dict) -> ResearchTopic:
        """创建主题并保存配置"""
        try:
            # 开始事务
            self.db_session.begin()

            # 创建主题
            topic = ResearchTopic(**topic_data)
            self.db_session.add(topic)

            # 保存配置
            config = RetrievalConfig(
                topic_id=topic.id,
                **config_data
            )
            self.db_session.add(config)

            # 提交事务
            self.db_session.commit()
            return topic

        except Exception as e:
            # 回滚事务
            self.db_session.rollback()
            raise TransactionError(f"Failed to create topic: {str(e)}")

    def update_stage_and_data(self, topic_id: str, stage: ExecutionStage, data: dict):
        """更新阶段和数据"""
        try:
            # 开始事务
            self.db_session.begin()

            # 更新主题当前阶段
            topic = self.db_session.query(ResearchTopic).get(topic_id)
            topic.current_stage = stage.value
            topic.updated_at = datetime.now()

            # 更新阶段记录
            stage_record = StageRecord(
                topic_id=topic_id,
                stage=stage.value,
                status="completed",
                result=data
            )
            self.db_session.add(stage_record)

            # 提交事务
            self.db_session.commit()

        except Exception as e:
            # 回滚事务
            self.db_session.rollback()
            raise TransactionError(f"Failed to update stage: {str(e)}")
```

#### 8.7.2 并发控制

使用乐观锁和版本控制处理并发访问。

```python
class ResearchTopicWithVersion:
    """带版本控制的主题"""

    __version__ = 0

    def update_with_optimistic_lock(self, updates: dict):
        """使用乐观锁更新"""
        current_version = self.__version__

        try:
            # 尝试更新
            self.__dict__.update(updates)
            self.__version__ += 1
            self.updated_at = datetime.now()

        except ConcurrentModificationError:
            # 版本冲突，重试或报错
            raise ConcurrentModificationError(
                f"Topic was modified by another process. "
                f"Current version: {current_version}"
            )
```

---

## 9. 错误处理设计

### 9.1 错误分类体系

系统采用分层错误分类体系，确保错误能够被准确识别和处理。

#### 9.1.1 错误类型定义

```python
class ErrorType(Enum):
    """错误类型"""
    # 业务错误
    BUSINESS_ERROR = "business_error"           # 业务逻辑错误
    VALIDATION_ERROR = "validation_error"       # 数据验证错误
    CONFIGURATION_ERROR = "configuration_error" # 配置错误

    # 系统错误
    SYSTEM_ERROR = "system_error"               # 系统错误
    DATABASE_ERROR = "database_error"           # 数据库错误
    FILESYSTEM_ERROR = "filesystem_error"       # 文件系统错误

    # 网络错误
    NETWORK_ERROR = "network_error"             # 网络错误
    API_ERROR = "api_error"                     # 外部API错误
    TIMEOUT_ERROR = "timeout_error"             # 超时错误

    # Agent错误
    AGENT_ERROR = "agent_error"                 # Agent执行错误
    LLM_ERROR = "llm_error"                     # LLM调用错误
    RETRIEVAL_ERROR = "retrieval_error"         # 检索错误

    # 用户错误
    USER_ERROR = "user_error"                   # 用户操作错误
    PERMISSION_ERROR = "permission_error"       # 权限错误
    AUTHENTICATION_ERROR = "authentication_error" # 认证错误

class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"           # 低：不影响主流程
    MEDIUM = "medium"     # 中：影响部分功能
    HIGH = "high"         # 高：影响核心功能
    CRITICAL = "critical" # 严重：系统无法继续运行
```

#### 9.1.2 错误码设计

采用分层错误码，便于识别和追踪。

```
错误码格式: [系统码-模块码-错误码]

系统码:
- 1: 用户系统
- 2: 主题管理系统
- 3: Agent系统
- 4: 数据库系统
- 5: 外部API系统

模块码:
- 01: 认证模块
- 02: 配置模块
- 03: 执行模块
- 04: 数据模块
- 05: 通知模块

示例:
- 2-03-001: 主题管理系统 - 执行模块 - 主题创建失败
- 3-04-002: Agent系统 - 数据模块 - LLM调用失败
- 5-02-003: 外部API系统 - 配置模块 - API配置无效
```

### 9.2 错误处理机制

#### 9.2.1 全局异常处理器

```python
class GlobalExceptionHandler:
    """全局异常处理器"""

    def __init__(self):
        self.error_logger = ErrorLogger()
        self.error_notifier = ErrorNotifier()
        self.error_recovery = ErrorRecovery()

    def handle_exception(self, exception: Exception, context: dict) -> ErrorResponse:
        """处理异常"""
        # 1. 识别错误类型
        error_info = self._classify_error(exception)

        # 2. 记录错误日志
        self.error_logger.log(error_info, context)

        # 3. 通知相关人员
        if error_info.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            self.error_notifier.notify(error_info, context)

        # 4. 尝试恢复
        recovery_result = self.error_recovery.attempt_recovery(error_info, context)

        # 5. 返回错误响应
        return self._build_error_response(error_info, recovery_result)

    def _classify_error(self, exception: Exception) -> ErrorInfo:
        """分类错误"""
        if isinstance(exception, BusinessException):
            return ErrorInfo(
                type=ErrorType.BUSINESS_ERROR,
                severity=ErrorSeverity.MEDIUM,
                code=exception.code,
                message=str(exception)
            )
        elif isinstance(exception, ValidationException):
            return ErrorInfo(
                type=ErrorType.VALIDATION_ERROR,
                severity=ErrorSeverity.LOW,
                code="VAL-001",
                message=str(exception)
            )
        elif isinstance(exception, APIException):
            return ErrorInfo(
                type=ErrorType.API_ERROR,
                severity=ErrorSeverity.HIGH,
                code=f"API-{exception.status_code}",
                message=str(exception)
            )
        elif isinstance(exception, DatabaseException):
            return ErrorInfo(
                type=ErrorType.DATABASE_ERROR,
                severity=ErrorSeverity.HIGH,
                code="DB-001",
                message=str(exception)
            )
        else:
            return ErrorInfo(
                type=ErrorType.SYSTEM_ERROR,
                severity=ErrorSeverity.CRITICAL,
                code="SYS-001",
                message=f"Unexpected error: {str(exception)}"
            )

class ErrorInfo:
    """错误信息"""
    type: ErrorType
    severity: ErrorSeverity
    code: str
    message: str
    details: Optional[dict] = None
    timestamp: datetime = field(default_factory=datetime.now)
    stack_trace: Optional[str] = None
```

#### 9.2.2 错误恢复策略

```python
class ErrorRecovery:
    """错误恢复管理器"""

    def __init__(self):
        self.recovery_strategies = {
            ErrorType.NETWORK_ERROR: self._recover_network,
            ErrorType.API_ERROR: self._recover_api,
            ErrorType.DATABASE_ERROR: self._recover_database,
            ErrorType.TIMEOUT_ERROR: self._recover_timeout
        }

    def attempt_recovery(self, error_info: ErrorInfo, context: dict) -> RecoveryResult:
        """尝试恢复"""
        strategy = self.recovery_strategies.get(error_info.type)

        if strategy:
            try:
                result = strategy(error_info, context)
                return result
            except Exception as e:
                return RecoveryResult(
                    success=False,
                    message=f"Recovery failed: {str(e)}"
                )
        else:
            return RecoveryResult(
                success=False,
                message="No recovery strategy available"
            )

    def _recover_network(self, error_info: ErrorInfo, context: dict) -> RecoveryResult:
        """网络错误恢复"""
        max_retries = 3
        retry_delay = 5  # 秒

        for attempt in range(max_retries):
            try:
                # 等待后重试
                time.sleep(retry_delay * (attempt + 1))

                # 重新执行操作
                result = self._retry_operation(context)
                return RecoveryResult(
                    success=True,
                    message=f"Recovered after {attempt + 1} attempts"
                )
            except Exception as e:
                if attempt == max_retries - 1:
                    return RecoveryResult(
                        success=False,
                        message=f"Failed after {max_retries} retries: {str(e)}"
                    )

    def _recover_api(self, error_info: ErrorInfo, context: dict) -> RecoveryResult:
        """API错误恢复"""
        # 检查是否是速率限制错误
        if "rate limit" in error_info.message.lower():
            # 等待后重试
            wait_time = 60  # 1分钟
            time.sleep(wait_time)
            return self._retry_operation(context)

        # 检查是否是认证错误
        elif "authentication" in error_info.message.lower():
            # 刷新认证信息
            self._refresh_authentication(context)
            return self._retry_operation(context)

        # 其他错误，尝试备用API
        else:
            return self._try_backup_api(context)

    def _recover_database(self, error_info: ErrorInfo, context: dict) -> RecoveryResult:
        """数据库错误恢复"""
        # 检查连接是否有效
        if not self._check_database_connection():
            # 重新连接数据库
            self._reconnect_database()

        # 重试操作
        return self._retry_operation(context)

    def _recover_timeout(self, error_info: ErrorInfo, context: dict) -> RecoveryResult:
        """超时错误恢复"""
        # 增加超时时间
        new_timeout = context.get('timeout', 30) * 2
        context['timeout'] = new_timeout

        # 重试操作
        return self._retry_operation(context)

class RecoveryResult:
    """恢复结果"""
    success: bool
    message: str
    recovered_data: Optional[dict] = None
```

### 9.3 特定错误场景处理

#### 9.3.1 Agent执行错误

```python
class AgentErrorHandler:
    """Agent错误处理器"""

    def handle_stage_error(self, topic_id: str, stage: ExecutionStage, error: Exception):
        """处理阶段执行错误"""
        # 1. 记录错误
        error_info = self._create_error_info(topic_id, stage, error)
        self._log_error(error_info)

        # 2. 更新主题状态
        self._update_topic_status(topic_id, stage, error)

        # 3. 保存阶段记录
        self._save_stage_record(topic_id, stage, error)

        # 4. 通知用户
        self._notify_user(topic_id, stage, error)

        # 5. 尝试恢复
        if self._can_recover(stage, error):
            return self._attempt_recovery(topic_id, stage, error)
        else:
            # 标记主题为失败状态
            self._mark_topic_as_failed(topic_id, error)

    def _can_recover(self, stage: ExecutionStage, error: Exception) -> bool:
        """判断是否可以恢复"""
        # 某些阶段可以重试
        recoverable_stages = [
            ExecutionStage.STAGE_2_RETRIEVAL,      # 检索可以重试
            ExecutionStage.STAGE_4_DOWNLOAD,       # 下载可以重试
            ExecutionStage.STAGE_5_ANALYSIS        # 分析可以重试
        ]

        if stage in recoverable_stages:
            # 检查错误类型
            if isinstance(error, (NetworkError, TimeoutError, APIError)):
                return True

        return False

    def _attempt_recovery(self, topic_id: str, stage: ExecutionStage, error: Exception):
        """尝试恢复"""
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # 等待后重试
                wait_time = 10 * (attempt + 1)
                time.sleep(wait_time)

                # 重新执行阶段
                result = self._execute_stage(topic_id, stage)

                # 恢复成功
                self._log_recovery_success(topic_id, stage, attempt + 1)
                return result

            except Exception as e:
                if attempt == max_retries - 1:
                    # 恢复失败
                    self._log_recovery_failure(topic_id, stage, max_retries)
                    self._mark_topic_as_failed(topic_id, error)
                    raise
```

#### 9.3.2 LLM调用错误

```python
class LLMErrorHandler:
    """LLM错误处理器"""

    def handle_llm_error(self, operation: str, error: Exception, context: dict) -> dict:
        """处理LLM调用错误"""
        # 1. 识别错误类型
        if isinstance(error, RateLimitError):
            return self._handle_rate_limit(operation, error, context)
        elif isinstance(error, AuthenticationError):
            return self._handle_authentication(operation, error, context)
        elif isinstance(error, TimeoutError):
            return self._handle_timeout(operation, error, context)
        elif isinstance(error, ContentFilterError):
            return self._handle_content_filter(operation, error, context)
        else:
            return self._handle_generic_error(operation, error, context)

    def _handle_rate_limit(self, operation: str, error: RateLimitError, context: dict) -> dict:
        """处理速率限制错误"""
        # 1. 记录错误
        self._log_error(f"Rate limit hit for {operation}: {error}")

        # 2. 获取等待时间
        wait_time = error.retry_after or 60

        # 3. 等待
        time.sleep(wait_time)

        # 4. 重试
        return self._retry_operation(operation, context)

    def _handle_authentication(self, operation: str, error: AuthenticationError, context: dict) -> dict:
        """处理认证错误"""
        # 1. 记录错误
        self._log_error(f"Authentication failed for {operation}: {error}")

        # 2. 刷新API密钥
        self._refresh_api_key(context['llm_provider'])

        # 3. 重试
        return self._retry_operation(operation, context)

    def _handle_timeout(self, operation: str, error: TimeoutError, context: dict) -> dict:
        """处理超时错误"""
        # 1. 记录错误
        self._log_error(f"Timeout for {operation}: {error}")

        # 2. 增加超时时间
        new_timeout = context.get('timeout', 60) * 2
        context['timeout'] = new_timeout

        # 3. 重试
        return self._retry_operation(operation, context)

    def _handle_content_filter(self, operation: str, error: ContentFilterError, context: dict) -> dict:
        """处理内容过滤错误"""
        # 1. 记录错误
        self._log_error(f"Content filter triggered for {operation}: {error}")

        # 2. 尝试修改输入内容
        modified_input = self._sanitize_input(context.get('input', ''))

        # 3. 重试
        context['input'] = modified_input
        return self._retry_operation(operation, context)

    def _handle_generic_error(self, operation: str, error: Exception, context: dict) -> dict:
        """处理通用错误"""
        # 1. 记录错误
        self._log_error(f"Generic error for {operation}: {error}")

        # 2. 尝试使用备用模型
        backup_model = self._get_backup_model(context.get('model'))

        # 3. 重试
        context['model'] = backup_model
        return self._retry_operation(operation, context)
```

#### 9.3.3 数据库操作错误

```python
class DatabaseErrorHandler:
    """数据库错误处理器"""

    def handle_database_error(self, operation: str, error: Exception, context: dict):
        """处理数据库操作错误"""
        if isinstance(error, ConnectionError):
            return self._handle_connection_error(operation, error, context)
        elif isinstance(error, TimeoutError):
            return self._handle_timeout_error(operation, error, context)
        elif isinstance(error, IntegrityError):
            return self._handle_integrity_error(operation, error, context)
        elif isinstance(error, OperationalError):
            return self._handle_operational_error(operation, error, context)
        else:
            return self._handle_generic_error(operation, error, context)

    def _handle_connection_error(self, operation: str, error: ConnectionError, context: dict):
        """处理连接错误"""
        # 1. 记录错误
        self._log_error(f"Database connection error for {operation}: {error}")

        # 2. 尝试重新连接
        self._reconnect_database()

        # 3. 重试操作
        return self._retry_operation(operation, context)

    def _handle_integrity_error(self, operation: str, error: IntegrityError, context: dict):
        """处理完整性错误"""
        # 1. 记录错误
        self._log_error(f"Database integrity error for {operation}: {error}")

        # 2. 分析错误类型
        if "duplicate key" in str(error):
            # 重复键错误，可能是并发插入
            return self._handle_duplicate_key(operation, error, context)
        elif "foreign key" in str(error):
            # 外键错误
            return self._handle_foreign_key(operation, error, context)
        else:
            # 其他完整性错误
            raise error

    def _handle_duplicate_key(self, operation: str, error: IntegrityError, context: dict):
        """处理重复键错误"""
        # 1. 提取键值
        key_value = self._extract_key_value(error)

        # 2. 检查是否已存在
        existing_record = self._get_existing_record(key_value)

        if existing_record:
            # 记录已存在，更新而不是插入
            return self._update_existing_record(existing_record, context)
        else:
            # 并发插入，重试
            return self._retry_operation(operation, context)
```

### 9.4 错误日志与监控

#### 9.4.1 错误日志系统

```python
class ErrorLogger:
    """错误日志系统"""

    def __init__(self):
        self.log_file = "logs/errors.log"
        self.error_database = ErrorDatabase()

    def log(self, error_info: ErrorInfo, context: dict):
        """记录错误日志"""
        # 1. 记录到文件
        self._log_to_file(error_info, context)

        # 2. 记录到数据库
        self._log_to_database(error_info, context)

        # 3. 记录到监控系统
        self._log_to_monitoring(error_info, context)

    def _log_to_file(self, error_info: ErrorInfo, context: dict):
        """记录到文件"""
        log_entry = {
            "timestamp": error_info.timestamp.isoformat(),
            "type": error_info.type.value,
            "severity": error_info.severity.value,
            "code": error_info.code,
            "message": error_info.message,
            "details": error_info.details,
            "context": context,
            "stack_trace": error_info.stack_trace
        }

        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

    def _log_to_database(self, error_info: ErrorInfo, context: dict):
        """记录到数据库"""
        error_record = ErrorRecord(
            type=error_info.type.value,
            severity=error_info.severity.value,
            code=error_info.code,
            message=error_info.message,
            details=json.dumps(error_info.details),
            context=json.dumps(context),
            stack_trace=error_info.stack_trace,
            created_at=error_info.timestamp
        )
        self.error_database.insert(error_record)

    def _log_to_monitoring(self, error_info: ErrorInfo, context: dict):
        """记录到监控系统"""
        if error_info.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            # 发送到监控系统
            MonitoringSystem.send_alert(
                error_type=error_info.type.value,
                severity=error_info.severity.value,
                message=error_info.message,
                context=context
            )
```

#### 9.4.2 错误统计与分析

```python
class ErrorAnalyzer:
    """错误分析器"""

    def __init__(self):
        self.error_database = ErrorDatabase()

    def analyze_errors(self, time_range: tuple) -> ErrorAnalysis:
        """分析错误"""
        # 1. 获取时间范围内的错误
        errors = self.error_database.get_errors_by_time_range(time_range)

        # 2. 统计错误类型
        error_types = self._count_by_type(errors)

        # 3. 统计错误严重程度
        error_severities = self._count_by_severity(errors)

        # 4. 识别高频错误
        frequent_errors = self._identify_frequent_errors(errors)

        # 5. 识别趋势
        trends = self._analyze_trends(errors)

        # 6. 生成报告
        return ErrorAnalysis(
            total_errors=len(errors),
            error_types=error_types,
            error_severities=error_severities,
            frequent_errors=frequent_errors,
            trends=trends,
            time_range=time_range
        )

    def _count_by_type(self, errors: List[ErrorRecord]) -> Dict[str, int]:
        """按类型统计"""
        type_counts = {}
        for error in errors:
            type_counts[error.type] = type_counts.get(error.type, 0) + 1
        return type_counts

    def _count_by_severity(self, errors: List[ErrorRecord]) -> Dict[str, int]:
        """按严重程度统计"""
        severity_counts = {}
        for error in errors:
            severity_counts[error.severity] = severity_counts.get(error.severity, 0) + 1
        return severity_counts

    def _identify_frequent_errors(self, errors: List[ErrorRecord]) -> List[ErrorPattern]:
        """识别高频错误"""
        # 按错误码分组
        error_groups = {}
        for error in errors:
            if error.code not in error_groups:
                error_groups[error.code] = []
            error_groups[error.code].append(error)

        # 统计频率
        frequent_errors = []
        for code, error_list in error_groups.items():
            if len(error_list) >= 5:  # 至少出现5次
                frequent_errors.append(ErrorPattern(
                    code=code,
                    count=len(error_list),
                    first_occurrence=min(e.created_at for e in error_list),
                    last_occurrence=max(e.created_at for e in error_list),
                    sample_message=error_list[0].message
                ))

        # 按频率排序
        frequent_errors.sort(key=lambda x: x.count, reverse=True)
        return frequent_errors[:10]  # 返回前10个

    def _analyze_trends(self, errors: List[ErrorRecord]) -> List[ErrorTrend]:
        """分析趋势"""
        # 按天分组
        daily_counts = {}
        for error in errors:
            date = error.created_at.date()
            daily_counts[date] = daily_counts.get(date, 0) + 1

        # 计算趋势
        dates = sorted(daily_counts.keys())
        if len(dates) < 2:
            return []

        trends = []
        for i in range(1, len(dates)):
            prev_date = dates[i - 1]
            curr_date = dates[i]
            prev_count = daily_counts[prev_date]
            curr_count = daily_counts[curr_date]

            if curr_count > prev_count:
                trend = "increasing"
            elif curr_count < prev_count:
                trend = "decreasing"
            else:
                trend = "stable"

            trends.append(ErrorTrend(
                date=curr_date,
                count=curr_count,
                trend=trend,
                change=curr_count - prev_count
            ))

        return trends
```

### 9.5 用户友好的错误提示

```python
class ErrorMessageFormatter:
    """错误消息格式化器"""

    def format_error_message(self, error_info: ErrorInfo, user_language: str = "zh") -> str:
        """格式化错误消息"""
        # 1. 获取错误模板
        template = self._get_error_template(error_info.type, user_language)

        # 2. 填充模板
        message = template.format(
            code=error_info.code,
            message=error_info.message,
            suggestions=self._get_suggestions(error_info, user_language)
        )

        return message

    def _get_error_template(self, error_type: ErrorType, language: str) -> str:
        """获取错误模板"""
        templates = {
            "zh": {
                ErrorType.NETWORK_ERROR: "网络错误 [{code}]: {message}\n建议：{suggestions}",
                ErrorType.API_ERROR: "API调用失败 [{code}]: {message}\n建议：{suggestions}",
                ErrorType.VALIDATION_ERROR: "数据验证失败 [{code}]: {message}\n建议：{suggestions}",
                ErrorType.TIMEOUT_ERROR: "操作超时 [{code}]: {message}\n建议：{suggestions}",
            },
            "en": {
                ErrorType.NETWORK_ERROR: "Network error [{code}]: {message}\nSuggestion: {suggestions}",
                ErrorType.API_ERROR: "API call failed [{code}]: {message}\nSuggestion: {suggestions}",
                ErrorType.VALIDATION_ERROR: "Validation error [{code}]: {message}\nSuggestion: {suggestions}",
                ErrorType.TIMEOUT_ERROR: "Timeout error [{code}]: {message}\nSuggestion: {suggestions}",
            }
        }

        return templates[language].get(error_type, "Error: {message}")

    def _get_suggestions(self, error_info: ErrorInfo, language: str) -> str:
        """获取建议"""
        suggestions = {
            "zh": {
                ErrorType.NETWORK_ERROR: "请检查网络连接，稍后重试",
                ErrorType.API_ERROR: "请检查API配置，或联系管理员",
                ErrorType.VALIDATION_ERROR: "请检查输入数据格式是否正确",
                ErrorType.TIMEOUT_ERROR: "请稍后重试，或增加超时时间",
            },
            "en": {
                ErrorType.NETWORK_ERROR: "Please check your network connection and try again later",
                ErrorType.API_ERROR: "Please check your API configuration or contact administrator",
                ErrorType.VALIDATION_ERROR: "Please check if the input data format is correct",
                ErrorType.TIMEOUT_ERROR: "Please try again later or increase timeout",
            }
        }

        return suggestions[language].get(error_info.type, "Please contact support")
```

---

## 10. 状态监控设计

### 10.1 监控架构设计

采用分层监控架构，从系统、应用、业务三个层面进行全方位监控。

```
┌─────────────────────────────────────────────────────────────┐
│                      监控展示层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  仪表板      │  │  告警中心    │  │  日志查看    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      监控处理层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  数据聚合    │  │  告警规则    │  │  通知分发    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      监控采集层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  系统监控    │  │  应用监控    │  │  业务监控    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      监控存储层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  时序数据库  │  │  日志存储    │  │  状态存储    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### 10.2 系统监控

#### 10.2.1 系统资源监控

```python
class SystemMonitor:
    """系统资源监控器"""

    def __init__(self):
        self.metrics_collector = MetricsCollector()
        self.alert_manager = AlertManager()

    def collect_system_metrics(self) -> SystemMetrics:
        """收集系统指标"""
        metrics = SystemMetrics(
            cpu_usage=self._get_cpu_usage(),
            memory_usage=self._get_memory_usage(),
            disk_usage=self._get_disk_usage(),
            network_io=self._get_network_io(),
            process_count=self._get_process_count(),
            load_average=self._get_load_average()
        )

        # 检查告警阈值
        self._check_alerts(metrics)

        return metrics

    def _get_cpu_usage(self) -> CPUMetrics:
        """获取CPU使用率"""
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()

        return CPUMetrics(
            usage_percent=cpu_percent,
            core_count=cpu_count,
            load_avg=psutil.getloadavg()
        )

    def _get_memory_usage(self) -> MemoryMetrics:
        """获取内存使用率"""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        return MemoryMetrics(
            total=mem.total,
            used=mem.used,
            free=mem.free,
            usage_percent=mem.percent,
            swap_total=swap.total,
            swap_used=swap.used,
            swap_percent=swap.percent
        )

    def _get_disk_usage(self) -> DiskMetrics:
        """获取磁盘使用率"""
        disk = psutil.disk_usage('/')
        io_counters = psutil.disk_io_counters()

        return DiskMetrics(
            total=disk.total,
            used=disk.used,
            free=disk.free,
            usage_percent=disk.percent,
            read_bytes=io_counters.read_bytes,
            write_bytes=io_counters.write_bytes,
            read_count=io_counters.read_count,
            write_count=io_counters.write_count
        )

    def _check_alerts(self, metrics: SystemMetrics):
        """检查告警"""
        # CPU使用率告警
        if metrics.cpu_usage.usage_percent > 80:
            self.alert_manager.send_alert(
                alert_type="high_cpu_usage",
                severity="warning",
                message=f"CPU usage is {metrics.cpu_usage.usage_percent}%"
            )

        # 内存使用率告警
        if metrics.memory_usage.usage_percent > 85:
            self.alert_manager.send_alert(
                alert_type="high_memory_usage",
                severity="warning",
                message=f"Memory usage is {metrics.memory_usage.usage_percent}%"
            )

        # 磁盘使用率告警
        if metrics.disk_usage.usage_percent > 90:
            self.alert_manager.send_alert(
                alert_type="high_disk_usage",
                severity="critical",
                message=f"Disk usage is {metrics.disk_usage.usage_percent}%"
            )
```

#### 10.2.2 服务健康检查

```python
class HealthCheckMonitor:
    """服务健康检查监控器"""

    def __init__(self):
        self.services = {
            "api_server": {"url": "http://localhost:8000/health", "timeout": 5},
            "database": {"check_func": self._check_database, "timeout": 5},
            "llm_service": {"check_func": self._check_llm_service, "timeout": 10},
            "email_service": {"check_func": self._check_email_service, "timeout": 5}
        }

    def check_all_services(self) -> Dict[str, HealthStatus]:
        """检查所有服务健康状态"""
        results = {}

        for service_name, config in self.services.items():
            try:
                if "url" in config:
                    status = self._check_http_service(config["url"], config["timeout"])
                elif "check_func" in config:
                    status = config["check_func"](config["timeout"])
                else:
                    status = HealthStatus(healthy=False, message="No check method defined")

                results[service_name] = status

            except Exception as e:
                results[service_name] = HealthStatus(
                    healthy=False,
                    message=f"Check failed: {str(e)}"
                )

        return results

    def _check_http_service(self, url: str, timeout: int) -> HealthStatus:
        """检查HTTP服务"""
        try:
            response = requests.get(url, timeout=timeout)

            if response.status_code == 200:
                return HealthStatus(
                    healthy=True,
                    message="Service is healthy",
                    details=response.json()
                )
            else:
                return HealthStatus(
                    healthy=False,
                    message=f"Service returned status {response.status_code}"
                )

        except requests.exceptions.Timeout:
            return HealthStatus(
                healthy=False,
                message="Service timeout"
            )
        except Exception as e:
            return HealthStatus(
                healthy=False,
                message=f"Check failed: {str(e)}"
            )

    def _check_database(self, timeout: int) -> HealthStatus:
        """检查数据库"""
        try:
            # 执行简单查询
            start_time = time.time()
            result = self.db_session.execute("SELECT 1").fetchone()
            elapsed_time = time.time() - start_time

            if elapsed_time < timeout:
                return HealthStatus(
                    healthy=True,
                    message=f"Database is healthy (response time: {elapsed_time:.2f}s)"
                )
            else:
                return HealthStatus(
                    healthy=False,
                    message=f"Database response too slow: {elapsed_time:.2f}s"
                )

        except Exception as e:
            return HealthStatus(
                healthy=False,
                message=f"Database check failed: {str(e)}"
            )

    def _check_llm_service(self, timeout: int) -> HealthStatus:
        """检查LLM服务"""
        try:
            # 发送测试请求
            start_time = time.time()
            response = self.llm_client.chat_completion(
                messages=[{"role": "user", "content": "test"}],
                max_tokens=10
            )
            elapsed_time = time.time() - start_time

            if response and elapsed_time < timeout:
                return HealthStatus(
                    healthy=True,
                    message=f"LLM service is healthy (response time: {elapsed_time:.2f}s)"
                )
            else:
                return HealthStatus(
                    healthy=False,
                    message=f"LLM service response too slow: {elapsed_time:.2f}s"
                )

        except Exception as e:
            return HealthStatus(
                healthy=False,
                message=f"LLM service check failed: {str(e)}"
            )
```

### 10.3 应用监控

#### 10.3.1 应用性能监控

```python
class ApplicationMonitor:
    """应用性能监控器"""

    def __init__(self):
        self.metrics_collector = MetricsCollector()
        self.performance_tracker = PerformanceTracker()

    def track_request(self, endpoint: str, method: str, response_time: float, status_code: int):
        """跟踪请求"""
        # 记录请求指标
        self.metrics_collector.record_metric(
            name="http_request_duration",
            value=response_time,
            tags={
                "endpoint": endpoint,
                "method": method,
                "status_code": str(status_code)
            }
        )

        # 记录请求计数
        self.metrics_collector.record_metric(
            name="http_request_count",
            value=1,
            tags={
                "endpoint": endpoint,
                "method": method,
                "status_code": str(status_code)
            }
        )

        # 检查性能告警
        if response_time > 5.0:  # 5秒阈值
            self.alert_manager.send_alert(
                alert_type="slow_request",
                severity="warning",
                message=f"Slow request to {endpoint}: {response_time:.2f}s"
            )

    def track_database_query(self, query_type: str, table: str, execution_time: float):
        """跟踪数据库查询"""
        # 记录查询指标
        self.metrics_collector.record_metric(
            name="database_query_duration",
            value=execution_time,
            tags={
                "query_type": query_type,
                "table": table
            }
        )

        # 检查慢查询
        if execution_time > 1.0:  # 1秒阈值
            self.alert_manager.send_alert(
                alert_type="slow_query",
                severity="warning",
                message=f"Slow {query_type} query on {table}: {execution_time:.2f}s"
            )

    def track_llm_call(self, model: str, operation: str, duration: float, token_count: int):
        """跟踪LLM调用"""
        # 记录LLM调用指标
        self.metrics_collector.record_metric(
            name="llm_call_duration",
            value=duration,
            tags={
                "model": model,
                "operation": operation
            }
        )

        self.metrics_collector.record_metric(
            name="llm_token_count",
            value=token_count,
            tags={
                "model": model,
                "operation": operation
            }
        )

        # 记录成本
        cost = self._calculate_cost(model, token_count)
        self.metrics_collector.record_metric(
            name="llm_cost",
            value=cost,
            tags={
                "model": model,
                "operation": operation
            }
        )

    def _calculate_cost(self, model: str, token_count: int) -> float:
        """计算LLM调用成本"""
        # 这里可以根据不同模型的定价计算成本
        pricing = {
            "gpt-4": 0.03 / 1000,  # 每1000 tokens $0.03
            "gpt-3.5-turbo": 0.002 / 1000,
            "claude-3": 0.015 / 1000
        }

        price_per_1k = pricing.get(model, 0.01 / 1000)
        return token_count * price_per_1k
```

#### 10.3.2 应用状态监控

```python
class ApplicationStateMonitor:
    """应用状态监控器"""

    def __init__(self):
        self.state_tracker = StateTracker()
        self.alert_manager = AlertManager()

    def monitor_topic_states(self):
        """监控主题状态"""
        # 获取所有主题
        topics = self.db_session.query(ResearchTopic).all()

        # 统计各状态主题数量
        state_counts = {}
        for topic in topics:
            state_counts[topic.status] = state_counts.get(topic.status, 0) + 1

        # 记录指标
        for status, count in state_counts.items():
            self.metrics_collector.record_metric(
                name="topic_count",
                value=count,
                tags={
                    "status": status
                }
            )

        # 检查长时间运行的主题
        running_topics = [t for t in topics if t.status == "running"]
        for topic in running_topics:
            running_time = (datetime.now() - topic.updated_at).total_seconds()

            # 如果运行时间超过1小时，发送告警
            if running_time > 3600:
                self.alert_manager.send_alert(
                    alert_type="long_running_topic",
                    severity="warning",
                    message=f"Topic {topic.id} has been running for {running_time/60:.0f} minutes"
                )

        # 检查失败的主题
        failed_topics = [t for t in topics if t.status == "failed"]
        if failed_topics:
            self.alert_manager.send_alert(
                alert_type="failed_topics",
                severity="error",
                message=f"{len(failed_topics)} topics have failed"
            )

    def monitor_stage_progress(self, topic_id: str):
        """监控阶段进度"""
        # 获取主题的阶段历史
        stage_records = self.db_session.query(StageRecord).filter(
            StageRecord.topic_id == topic_id
        ).order_by(StageRecord.started_at).all()

        # 分析阶段执行时间
        for record in stage_records:
            if record.started_at and record.completed_at:
                duration = (record.completed_at - record.started_at).total_seconds()

                # 记录阶段执行时间
                self.metrics_collector.record_metric(
                    name="stage_execution_duration",
                    value=duration,
                    tags={
                        "stage": str(record.stage),
                        "topic_id": topic_id
                    }
                )

                # 检查阶段执行时间是否过长
                expected_duration = self._get_expected_duration(record.stage)
                if duration > expected_duration * 2:
                    self.alert_manager.send_alert(
                        alert_type="slow_stage_execution",
                        severity="warning",
                        message=f"Stage {record.stage} took {duration:.0f}s (expected: {expected_duration:.0f}s)"
                    )

    def _get_expected_duration(self, stage: int) -> float:
        """获取预期执行时间"""
        durations = {
            1: 60,   # 检索词生成：1分钟
            2: 300,  # 检索与汇总：5分钟
            3: 600,  # 评分与筛选：10分钟
            4: 900,  # 下载与解析：15分钟
            5: 1200, # 总结生成：20分钟
            6: 60,   # 格式化与储存：1分钟
            7: 120   # 邮件发送：2分钟
        }
        return durations.get(stage, 300)
```

### 10.4 业务监控

#### 10.4.1 业务指标监控

```python
class BusinessMonitor:
    """业务指标监控器"""

    def __init__(self):
        self.metrics_collector = MetricsCollector()
        self.alert_manager = AlertManager()

    def monitor_topic_metrics(self):
        """监控主题指标"""
        # 获取统计数据
        total_topics = self.db_session.query(ResearchTopic).count()
        completed_topics = self.db_session.query(ResearchTopic).filter(
            ResearchTopic.status == "completed"
        ).count()
        failed_topics = self.db_session.query(ResearchTopic).filter(
            ResearchTopic.status == "failed"
        ).count()

        # 记录指标
        self.metrics_collector.record_metric(
            name="total_topics",
            value=total_topics
        )

        self.metrics_collector.record_metric(
            name="completed_topics",
            value=completed_topics
        )

        self.metrics_collector.record_metric(
            name="failed_topics",
            value=failed_topics
        )

        # 计算成功率
        if total_topics > 0:
            success_rate = (completed_topics / total_topics) * 100
            self.metrics_collector.record_metric(
                name="topic_success_rate",
                value=success_rate
            )

            # 检查成功率告警
            if success_rate < 80:
                self.alert_manager.send_alert(
                    alert_type="low_success_rate",
                    severity="warning",
                    message=f"Topic success rate is {success_rate:.1f}%"
                )

    def monitor_paper_metrics(self):
        """监控论文指标"""
        # 获取统计数据
        total_papers = self.db_session.query(Paper).count()
        valid_papers = self.db_session.query(Paper).filter(
            Paper.is_valid == True
        ).count()
        pushed_papers = self.db_session.query(Paper).filter(
            Paper.push_status == True
        ).count()

        # 记录指标
        self.metrics_collector.record_metric(
            name="total_papers",
            value=total_papers
        )

        self.metrics_collector.record_metric(
            name="valid_papers",
            value=valid_papers
        )

        self.metrics_collector.record_metric(
            name="pushed_papers",
            value=pushed_papers
        )

        # 计算有效率
        if total_papers > 0:
            valid_rate = (valid_papers / total_papers) * 100
            self.metrics_collector.record_metric(
                name="paper_valid_rate",
                value=valid_rate
            )

    def monitor_retrieval_metrics(self):
        """监控检索指标"""
        # 获取最近的检索记录
        recent_retrievals = self.db_session.query(StageRecord).filter(
            StageRecord.stage == 2,
            StageRecord.started_at >= datetime.now() - timedelta(days=7)
        ).all()

        if not recent_retrievals:
            return

        # 统计检索论文数量
        total_retrieved = 0
        for record in recent_retrievals:
            if record.result and "total_papers" in record.result:
                total_retrieved += record.result["total_papers"]

        avg_papers_per_topic = total_retrieved / len(recent_retrievals)

        # 记录指标
        self.metrics_collector.record_metric(
            name="avg_papers_per_topic",
            value=avg_papers_per_topic
        )

        # 检查检索量是否异常
        if avg_papers_per_topic < 5:
            self.alert_manager.send_alert(
                alert_type="low_retrieval_count",
                severity="warning",
                message=f"Average papers per topic is low: {avg_papers_per_topic:.1f}"
            )

    def monitor_llm_usage(self):
        """监控LLM使用情况"""
        # 获取最近一周的LLM调用记录
        recent_calls = self.db_session.query(LLMCall).filter(
            LLMCall.created_at >= datetime.now() - timedelta(days=7)
        ).all()

        if not recent_calls:
            return

        # 统计token使用量
        total_tokens = sum(call.token_count for call in recent_calls)
        total_cost = sum(call.cost for call in recent_calls)

        # 记录指标
        self.metrics_collector.record_metric(
            name="weekly_token_usage",
            value=total_tokens
        )

        self.metrics_collector.record_metric(
            name="weekly_llm_cost",
            value=total_cost
        )

        # 检查成本告警
        weekly_budget = 100  # $100
        if total_cost > weekly_budget:
            self.alert_manager.send_alert(
                alert_type="high_llm_cost",
                severity="warning",
                message=f"Weekly LLM cost is ${total_cost:.2f} (budget: ${weekly_budget})"
            )
```

#### 10.4.2 用户行为监控

```python
class UserBehaviorMonitor:
    """用户行为监控器"""

    def __init__(self):
        self.metrics_collector = MetricsCollector()

    def monitor_user_activity(self):
        """监控用户活动"""
        # 获取活跃用户数
        active_users = self.db_session.query(User).filter(
            User.last_login_at >= datetime.now() - timedelta(days=7)
        ).count()

        # 记录指标
        self.metrics_collector.record_metric(
            name="active_users",
            value=active_users
        )

        # 获取用户操作统计
        user_actions = self.db_session.query(UserAction).filter(
            UserAction.created_at >= datetime.now() - timedelta(days=1)
        ).all()

        # 按操作类型统计
        action_counts = {}
        for action in user_actions:
            action_counts[action.action_type] = action_counts.get(action.action_type, 0) + 1

        # 记录指标
        for action_type, count in action_counts.items():
            self.metrics_collector.record_metric(
                name="user_action_count",
                value=count,
                tags={
                    "action_type": action_type
                }
            )

    def monitor_feature_usage(self):
        """监控功能使用情况"""
        # 获取各功能的使用次数
        feature_usage = {
            "create_topic": self.db_session.query(ResearchTopic).count(),
            "retrieve_papers": self.db_session.query(Paper).count(),
            "export_data": self.db_session.query(ExportRecord).count(),
            "send_email": self.db_session.query(EmailRecord).count()
        }

        # 记录指标
        for feature, count in feature_usage.items():
            self.metrics_collector.record_metric(
                name="feature_usage",
                value=count,
                tags={
                    "feature": feature
                }
            )
```

### 10.5 告警系统

#### 10.5.1 告警规则配置

```python
class AlertRuleManager:
    """告警规则管理器"""

    def __init__(self):
        self.rules = self._load_rules()

    def _load_rules(self) -> List[AlertRule]:
        """加载告警规则"""
        return [
            AlertRule(
                name="high_cpu_usage",
                condition=lambda metrics: metrics.cpu_usage.usage_percent > 80,
                severity="warning",
                message="CPU usage is {cpu_usage}%"
            ),
            AlertRule(
                name="high_memory_usage",
                condition=lambda metrics: metrics.memory_usage.usage_percent > 85,
                severity="warning",
                message="Memory usage is {memory_usage}%"
            ),
            AlertRule(
                name="high_disk_usage",
                condition=lambda metrics: metrics.disk_usage.usage_percent > 90,
                severity="critical",
                message="Disk usage is {disk_usage}%"
            ),
            AlertRule(
                name="slow_request",
                condition=lambda data: data.get("response_time", 0) > 5.0,
                severity="warning",
                message="Slow request: {response_time:.2f}s"
            ),
            AlertRule(
                name="failed_topics",
                condition=lambda data: data.get("failed_count", 0) > 5,
                severity="error",
                message="{failed_count} topics have failed"
            ),
            AlertRule(
                name="low_success_rate",
                condition=lambda data: data.get("success_rate", 100) < 80,
                severity="warning",
                message="Success rate is {success_rate:.1f}%"
            ),
            AlertRule(
                name="high_llm_cost",
                condition=lambda data: data.get("weekly_cost", 0) > 100,
                severity="warning",
                message="Weekly LLM cost is ${weekly_cost:.2f}"
            )
        ]

    def evaluate_rules(self, metrics_data: dict) -> List[Alert]:
        """评估告警规则"""
        alerts = []

        for rule in self.rules:
            try:
                if rule.condition(metrics_data):
                    alert = Alert(
                        name=rule.name,
                        severity=rule.severity,
                        message=rule.message.format(**metrics_data),
                        timestamp=datetime.now()
                    )
                    alerts.append(alert)
            except Exception as e:
                logger.error(f"Error evaluating rule {rule.name}: {str(e)}")

        return alerts

class AlertRule:
    """告警规则"""
    name: str
    condition: Callable
    severity: str
    message: str
```

#### 10.5.2 告警通知

```python
class AlertNotifier:
    """告警通知器"""

    def __init__(self):
        self.notifiers = {
            "email": EmailNotifier(),
            "slack": SlackNotifier(),
            "webhook": WebhookNotifier()
        }

    def send_alert(self, alert: Alert, channels: List[str] = None):
        """发送告警"""
        if channels is None:
            channels = ["email"]  # 默认使用邮件

        for channel in channels:
            if channel in self.notifiers:
                try:
                    self.notifiers[channel].send(alert)
                except Exception as e:
                    logger.error(f"Failed to send alert via {channel}: {str(e)}")

class EmailNotifier:
    """邮件通知器"""

    def send(self, alert: Alert):
        """发送邮件告警"""
        subject = f"[{alert.severity.upper()}] {alert.name}"
        body = self._format_alert_body(alert)

        self.email_client.send(
            to=self.alert_recipients,
            subject=subject,
            body=body
        )

    def _format_alert_body(self, alert: Alert) -> str:
        """格式化告警内容"""
        return f"""
Alert: {alert.name}
Severity: {alert.severity}
Time: {alert.timestamp}
Message: {alert.message}

Please check the system for more details.
        """

class SlackNotifier:
    """Slack通知器"""

    def send(self, alert: Alert):
        """发送Slack告警"""
        color = {
            "info": "good",
            "warning": "warning",
            "error": "danger",
            "critical": "danger"
        }.get(alert.severity, "warning")

        attachment = {
            "color": color,
            "title": f"[{alert.severity.upper()}] {alert.name}",
            "text": alert.message,
            "ts": alert.timestamp.timestamp()
        }

        self.slack_client.send_message(
            channel=self.alert_channel,
            attachments=[attachment]
        )
```

### 10.6 监控仪表板

#### 10.6.1 仪表板数据聚合

```python
class DashboardAggregator:
    """仪表板数据聚合器"""

    def __init__(self):
        self.metrics_store = MetricsStore()
        self.alert_store = AlertStore()

    def get_dashboard_data(self, time_range: str = "24h") -> DashboardData:
        """获取仪表板数据"""
        return DashboardData(
            # 系统指标
            system_metrics=self._get_system_metrics(),

            # 应用指标
            application_metrics=self._get_application_metrics(),

            # 业务指标
            business_metrics=self._get_business_metrics(),

            # 告警信息
            alerts=self._get_recent_alerts(),

            # 趋势数据
            trends=self._get_trend_data(time_range)
        )

    def _get_system_metrics(self) -> SystemMetrics:
        """获取系统指标"""
        latest_metrics = self.metrics_store.get_latest_metrics("system")

        return SystemMetrics(
            cpu_usage=latest_metrics.get("cpu_usage", 0),
            memory_usage=latest_metrics.get("memory_usage", 0),
            disk_usage=latest_metrics.get("disk_usage", 0),
            network_in=latest_metrics.get("network_in", 0),
            network_out=latest_metrics.get("network_out", 0)
        )

    def _get_application_metrics(self) -> ApplicationMetrics:
        """获取应用指标"""
        # 获取请求数据
        request_metrics = self.metrics_store.get_metrics(
            name="http_request_count",
            time_range="1h"
        )

        total_requests = sum(m.value for m in request_metrics)

        # 获取错误率
        error_requests = [m for m in request_metrics if m.tags.get("status_code", "200") != "200"]
        error_rate = (len(error_requests) / total_requests * 100) if total_requests > 0 else 0

        # 获取平均响应时间
        response_time_metrics = self.metrics_store.get_metrics(
            name="http_request_duration",
            time_range="1h"
        )

        avg_response_time = sum(m.value for m in response_time_metrics) / len(response_time_metrics) if response_time_metrics else 0

        return ApplicationMetrics(
            total_requests=total_requests,
            error_rate=error_rate,
            avg_response_time=avg_response_time
        )

    def _get_business_metrics(self) -> BusinessMetrics:
        """获取业务指标"""
        # 获取主题统计
        topic_metrics = self.metrics_store.get_latest_metrics("topic")

        # 获取论文统计
        paper_metrics = self.metrics_store.get_latest_metrics("paper")

        # 获取LLM成本
        llm_cost_metrics = self.metrics_store.get_metrics(
            name="weekly_llm_cost",
            time_range="7d"
        )

        weekly_cost = sum(m.value for m in llm_cost_metrics)

        return BusinessMetrics(
            total_topics=topic_metrics.get("total", 0),
            completed_topics=topic_metrics.get("completed", 0),
            success_rate=topic_metrics.get("success_rate", 0),
            total_papers=paper_metrics.get("total", 0),
            valid_papers=paper_metrics.get("valid", 0),
            weekly_llm_cost=weekly_cost
        )

    def _get_recent_alerts(self) -> List[Alert]:
        """获取最近的告警"""
        return self.alert_store.get_recent_alerts(limit=10)

    def _get_trend_data(self, time_range: str) -> Dict[str, List[DataPoint]]:
        """获取趋势数据"""
        # CPU使用率趋势
        cpu_trend = self.metrics_store.get_trend(
            name="cpu_usage",
            time_range=time_range,
            interval="1h"
        )

        # 请求量趋势
        request_trend = self.metrics_store.get_trend(
            name="http_request_count",
            time_range=time_range,
            interval="1h"
        )

        return {
            "cpu_usage": cpu_trend,
            "request_count": request_trend
        }
```

---

## 11. 质量属性

### 11.1 可测试性

- 提供单元测试框架
- 提供集成测试环境
- 提供测试数据
- 关键功能测试覆盖率≥80%

### 11.2 可移植性

- 支持Windows、macOS、Linux操作系统
- 支持主流浏览器
- 支持容器化部署（Docker）

### 11.3 兼容性

- 向后兼容旧版本数据
- 支持多种LLM模型
- 支持多种数据库

---

## 12. 验收标准

### 12.1 功能验收

- 所有功能需求（FR-001至FR-017）均已实现
- 功能测试通过率100%
- 用户验收测试通过

### 12.2 性能验收

- 页面加载时间< 2秒
- API响应时间< 1秒
- 完成一次完整检索（10篇论文）< 5分钟

### 12.3 安全验收

- 通过安全测试
- 无高危漏洞
- API密钥加密存储
- 数据传输加密

### 12.4 文档验收

- 用户手册完整
- 开发文档完整
- API文档完整
- 部署文档完整

### 12.5 监控验收

- 系统监控功能正常运行
- 告警规则准确触发
- 监控仪表板数据准确
- 错误日志完整记录

---

## 13. 附录

### 13.1 术语表

| 术语 | 定义 |
|------|------|
| Agent | 智能代理，能够自主执行任务的软件实体 |
| Retrieval | 检索，从数据源获取信息的过程 |
| Scoring | 评分，对论文进行价值评估 |
| Vector Database | 向量数据库，存储和检索向量数据的数据库 |
| Knowledge Graph | 知识图谱，结构化的知识表示 |
| Research Topic | 科学研究主题，系统的核心业务单元 |
| Execution Stage | 执行阶段，Agent执行的7个关键步骤 |

### 13.2 参考文档

- design.md - 系统设计文档
- LangGraph官方文档
- FastAPI官方文档
- React官方文档
- SQLite文档
- ChromaDB文档
- Prometheus监控文档
- Grafana仪表板文档

### 13.3 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|---------|--------|
| v1.0 | 2026-02-18 | 初始版本 | 系统设计师 |
| v1.1 | 2026-04-03 | 新增底层设计、错误处理设计、状态监控设计章节 | 系统设计师 |

---

## 14. 签字确认

| 角色 | 姓名 | 签字 | 日期 |
|------|------|------|------|
| 需求分析人员 | - | - | - |
| 系统设计师 | - | - | - |
| 项目经理 | - | - | - |
| 用户代表 | - | - | - |
