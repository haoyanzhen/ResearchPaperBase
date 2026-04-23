-- =============================================================================
-- Research Paper Base — PostgreSQL Schema
-- =============================================================================
-- Author:  haoyanzhen
-- Version: v1.1 (aligned with spec.md v1.7 — FR-029 admin columns + system_configs)
-- Date:    2026-04-23
--
-- 契约说明：
--   本文件是所有模块间数据层的唯一权威契约。
--   任何业务实现任务均不得修改本文件；表结构变更须独立评审后更新版本号。
--
-- 数据库：PostgreSQL 15+
-- 字符集：UTF-8
-- 时区：所有 TIMESTAMPTZ 字段均使用 UTC 存储
--
-- 一致性策略（重要，禁止在实现中绕过）：
--   - papers + project_paper_relations 写入：与 ChromaDB 向量写入在同一事务上下文中
--     执行，任意一方失败立即整体回滚，不允许部分成功状态
--   - NetworkX 图数据库：最终一致，新论文入库后做局部增量更新，每日深夜全量重建
--   - projects.status 只由构建模式和综述模式的 Agent 链写入；
--     深度研究模式的对话不改变 status，对话期间 status 保持 idle
-- =============================================================================

-- 扩展
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- 用于 gen_random_uuid()

-- =============================================================================
-- 1. 用户表 (users)
-- 说明：存储系统用户基本信息，每个用户唯一。
-- =============================================================================
CREATE TABLE users (
    id            VARCHAR(50)  NOT NULL,
    username      VARCHAR(50)  NOT NULL,
    email         VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_admin      BOOLEAN      NOT NULL DEFAULT FALSE,  -- 首位注册用户自动置为 TRUE（FR-029）
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,   -- FALSE 时用户无法登录
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,

    CONSTRAINT pk_users PRIMARY KEY (id),
    CONSTRAINT uq_users_username UNIQUE (username),
    CONSTRAINT uq_users_email    UNIQUE (email)
);

CREATE INDEX idx_users_created_at ON users (created_at);
CREATE INDEX idx_users_is_admin   ON users (is_admin);

COMMENT ON TABLE  users               IS '系统用户基本信息，每个用户唯一';
COMMENT ON COLUMN users.id            IS '用户唯一标识符';
COMMENT ON COLUMN users.username      IS '用户名，全局唯一';
COMMENT ON COLUMN users.email         IS '邮箱，全局唯一';
COMMENT ON COLUMN users.password_hash IS '密码哈希值（bcrypt）';
COMMENT ON COLUMN users.is_admin      IS '是否为管理员；首位注册用户自动置为 TRUE（FR-029）';
COMMENT ON COLUMN users.is_active     IS '账号是否启用；FALSE 时用户无法登录，由管理员禁用';
COMMENT ON COLUMN users.last_login_at IS '最后登录时间';

-- =============================================================================
-- 2. 用户配置表 (user_configs)
-- 说明：Key-Value 结构，每行一个配置项（含系统默认配置和用户自定义配置）。
--       config_value 使用 TEXT 存储，复杂配置以 JSON 字符串格式写入。
-- 示例 config_name：llm.provider.deepseek.url / email.smtp.host / email.recipients
-- =============================================================================
CREATE TABLE user_configs (
    id                VARCHAR(50)  NOT NULL,
    user_id           VARCHAR(50)  NOT NULL,
    config_name       VARCHAR(100) NOT NULL,
    config_value      TEXT         NOT NULL,
    is_system_default BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_user_configs     PRIMARY KEY (id),
    CONSTRAINT fk_user_configs_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT uq_user_configs_user_config UNIQUE (user_id, config_name)  -- 同一用户下配置名唯一
);

CREATE INDEX idx_user_configs_user_id ON user_configs (user_id);

COMMENT ON TABLE  user_configs                   IS '用户配置，Key-Value 结构，每行一个配置项';
COMMENT ON COLUMN user_configs.config_name       IS '配置名称，如 llm.model / email.smtp.host';
COMMENT ON COLUMN user_configs.config_value      IS '配置值，复杂配置以 JSON 字符串格式存储';
COMMENT ON COLUMN user_configs.is_system_default IS '是否为系统默认配置';

-- =============================================================================
-- 3. 研究主题表 (projects)
-- 说明：系统核心实体，所有功能都以 project_id 为轴心。
--
-- status 状态机（只有构建模式/综述模式 Agent 链负责写入）：
--   idle     → 项目创建初始值；任务完成/失败处理后回归；用户手动取消后
--   running  → 用户启动构建/综述阶段任务时；定时调度器触发时
--   paused   → 构建/综述模式完成某阶段，进入用户交互等待时
--   error    → LLM 调用重试后仍失败；用户确认处理后恢复为 idle
--   archived → 用户主动归档项目；归档后禁止启动新任务
--
-- 注意：深度研究对话期间 status 保持 idle，对话无"运行中任务"概念。
-- 当前执行阶段不存本表，通过查询 stage_records 取最新记录获取。
-- =============================================================================
CREATE TABLE projects (
    id            VARCHAR(50)  NOT NULL,
    user_id       VARCHAR(50)  NOT NULL,
    name          VARCHAR(255) NOT NULL,
    description   TEXT,
    mode          VARCHAR(20)  NOT NULL DEFAULT 'construction',
    status        VARCHAR(20)  NOT NULL DEFAULT 'idle',
    total_papers  INTEGER      NOT NULL DEFAULT 0,
    valid_papers  INTEGER      NOT NULL DEFAULT 0,
    auto_push     BOOLEAN      NOT NULL DEFAULT FALSE,
    push_interval SMALLINT,                        -- 单位：天，auto_push=TRUE 时有效
    last_push_at  TIMESTAMPTZ,
    next_push_at  TIMESTAMPTZ,                     -- 由调度器写入
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_projects PRIMARY KEY (id),
    CONSTRAINT fk_projects_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT chk_projects_mode
        CHECK (mode   IN ('construction', 'deep_research', 'review')),
    CONSTRAINT chk_projects_status
        CHECK (status IN ('idle', 'running', 'paused', 'error', 'archived'))
);

CREATE INDEX idx_projects_user_id     ON projects (user_id);
CREATE INDEX idx_projects_status      ON projects (status);
CREATE INDEX idx_projects_mode        ON projects (mode);
CREATE INDEX idx_projects_next_push   ON projects (next_push_at);
CREATE INDEX idx_projects_created_at  ON projects (created_at);

COMMENT ON TABLE  projects               IS '研究主题（Project），系统核心实体';
COMMENT ON COLUMN projects.mode          IS '当前模式：construction / deep_research / review';
COMMENT ON COLUMN projects.status        IS '当前任务状态：idle/running/paused/error/archived；深度研究对话期间保持 idle';
COMMENT ON COLUMN projects.valid_papers  IS '有效论文数（total_score≥7）；为 0 时前端拦截切换到深研/综述模式';
COMMENT ON COLUMN projects.auto_push     IS '是否启用定时自动检索推送（FR-010）';
COMMENT ON COLUMN projects.push_interval IS '自动推送间隔（天），auto_push=TRUE 时有效';
COMMENT ON COLUMN projects.next_push_at  IS '下次计划推送时间，由调度器写入';

-- =============================================================================
-- 4. 检索词表 (keywords)
-- 说明：每行一个检索词，支持各学术数据库的布尔表达式。
--       is_selected=TRUE 的记录用于 FR-010 定时自动任务。
-- =============================================================================
CREATE TABLE keywords (
    id                               VARCHAR(50)  NOT NULL,
    project_id                       VARCHAR(50)  NOT NULL,
    search_word                      VARCHAR(500) NOT NULL,
    boolean_expressions              JSONB,          -- 各数据库布尔表达式，见 spec 6.1 示例
    searched_papers_arxiv            SMALLINT     NOT NULL DEFAULT 0,
    searched_papers_openalex         SMALLINT     NOT NULL DEFAULT 0,
    searched_papers_semanticscholar  SMALLINT     NOT NULL DEFAULT 0,
    searched_papers_ads              SMALLINT     NOT NULL DEFAULT 0,
    searched_papers_total            SMALLINT     NOT NULL DEFAULT 0,
    is_searched                      BOOLEAN      NOT NULL DEFAULT FALSE,  -- 新词创建时尚未执行过搜索
    is_selected                      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at                       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_search_at                   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_keywords PRIMARY KEY (id),
    CONSTRAINT fk_keywords_project
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX idx_keywords_project_id  ON keywords (project_id);
CREATE INDEX idx_keywords_is_selected ON keywords (project_id, is_selected);

COMMENT ON TABLE  keywords                       IS '课题检索词，每行一个词，支持多数据库布尔表达式';
COMMENT ON COLUMN keywords.boolean_expressions   IS 'JSONB，格式：{"arxiv":"...","openalex":"...","semantic_scholar":"...","ads":"..."}';
COMMENT ON COLUMN keywords.is_selected           IS '是否被选中；FR-010 定时任务仅使用 is_selected=TRUE 的记录';

-- =============================================================================
-- 5. 论文表 (papers)
-- 说明：全局共享，每篇论文只存一份（DOI / ArXiv ID / 小写标题三路去重）。
--       与课题的关联及评分状态在 project_paper_relations 中。
--
-- 一致性约束（重要）：
--   papers 的写入必须与 ChromaDB 向量写入在同一事务上下文中执行，
--   任意一方失败立即整体回滚。
-- =============================================================================
CREATE TABLE papers (
    id                 VARCHAR(50)  NOT NULL,
    doi                VARCHAR(100),                -- 全局唯一，可为空
    arxiv_id           VARCHAR(50),                 -- 全局唯一，可为空
    title              TEXT         NOT NULL,       -- 小写格式，用于去重
    authors            JSONB,                       -- JSON 数组，如 ["John Doe", "Jane Smith"]
    pub_date           DATE,
    venue              VARCHAR(200),                -- 期刊/会议名称
    abstract           TEXT,
    source             VARCHAR(50),                 -- arxiv / openalex / semantic_scholar / ads
    retrieved_at       TIMESTAMPTZ  NOT NULL,
    download_status    VARCHAR(20)  NOT NULL DEFAULT 'not_downloaded',
    pdf_path           VARCHAR(500),
    text_path          VARCHAR(500),
    download_error     TEXT,
    ai_analysis_status VARCHAR(20)  NOT NULL DEFAULT 'not_analyzed',
    ai_analysis        JSONB,                       -- AI 分析结果（总结/亮点/相关性/技术方法）
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_papers PRIMARY KEY (id),
    CONSTRAINT uq_papers_doi      UNIQUE (doi),
    CONSTRAINT uq_papers_arxiv_id UNIQUE (arxiv_id),
    CONSTRAINT uq_papers_title    UNIQUE (title),
    CONSTRAINT chk_papers_download_status
        CHECK (download_status    IN ('not_downloaded', 'success', 'failed')),
    CONSTRAINT chk_papers_ai_analysis_status
        CHECK (ai_analysis_status IN ('not_analyzed', 'success', 'failed'))
);

CREATE INDEX idx_papers_pub_date ON papers (pub_date);
CREATE INDEX idx_papers_source   ON papers (source);

COMMENT ON TABLE  papers                    IS '全局论文表，每篇论文只存一份（三路去重）；写入须与 ChromaDB 同事务';
COMMENT ON COLUMN papers.title              IS '小写格式，用于去重（UNIQUE 约束）';
COMMENT ON COLUMN papers.doi               IS 'DOI 标识符，全局唯一，可为空';
COMMENT ON COLUMN papers.arxiv_id          IS 'ArXiv ID，全局唯一，可为空';
COMMENT ON COLUMN papers.download_status   IS 'not_downloaded / success / failed';
COMMENT ON COLUMN papers.ai_analysis_status IS 'not_analyzed / success / failed';
COMMENT ON COLUMN papers.ai_analysis       IS 'AI 分析结果：一句话总结、亮点解析、相关性要点、技术方法与创新';

-- =============================================================================
-- 6. 研究主题-论文关联表 (project_paper_relations)
-- 说明：课题与论文的多对多关联，评分和推送状态按课题独立存储。
--       FR-007 删除论文 = 删除本表记录，全局 papers 表不受影响。
--
-- 一致性约束（同 papers 表）：
--   本表写入须与 ChromaDB 向量写入在同一事务上下文中执行。
-- =============================================================================
CREATE TABLE project_paper_relations (
    id               VARCHAR(50)  NOT NULL,
    project_id       VARCHAR(50)  NOT NULL,
    paper_id         VARCHAR(50)  NOT NULL,
    reference_score  SMALLINT,                      -- 参考价值评分（0-5）
    technical_score  SMALLINT,                      -- 技术价值评分（0-5）
    total_score      SMALLINT,                      -- 总分（0-10），reference_score + technical_score
    scoring_reason   TEXT,
    is_valid         BOOLEAN      NOT NULL DEFAULT FALSE,  -- 评分完成后显式置为 TRUE（总分≥7），避免未评分记录误入推送和检索
    push_status      BOOLEAN      NOT NULL DEFAULT FALSE,  -- 是否已推送邮件
    pushed_at        TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_project_paper_relations PRIMARY KEY (id),
    CONSTRAINT fk_ppr_project
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CONSTRAINT fk_ppr_paper
        FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE RESTRICT,  -- 全局论文不允许被级联删除
    CONSTRAINT uq_ppr_project_paper UNIQUE (project_id, paper_id),
    CONSTRAINT chk_ppr_reference_score
        CHECK (reference_score IS NULL OR (reference_score >= 0 AND reference_score <= 5)),
    CONSTRAINT chk_ppr_technical_score
        CHECK (technical_score IS NULL OR (technical_score >= 0 AND technical_score <= 5)),
    CONSTRAINT chk_ppr_total_score
        CHECK (total_score IS NULL OR (total_score >= 0 AND total_score <= 10))
);

CREATE UNIQUE INDEX idx_ppr_project_paper ON project_paper_relations (project_id, paper_id);
CREATE        INDEX idx_ppr_project_id    ON project_paper_relations (project_id);
CREATE        INDEX idx_ppr_paper_id      ON project_paper_relations (paper_id);
CREATE        INDEX idx_ppr_is_valid      ON project_paper_relations (project_id, is_valid);
CREATE        INDEX idx_ppr_push_status   ON project_paper_relations (project_id, push_status);

COMMENT ON TABLE  project_paper_relations             IS '课题-论文关联；删除论文=删除本表记录，全局 papers 不受影响';
COMMENT ON COLUMN project_paper_relations.is_valid    IS '总分≥7 为有效；FR-018 邮件只发送 is_valid=TRUE AND push_status=FALSE 的记录';
COMMENT ON COLUMN project_paper_relations.push_status IS '是否已推送邮件；FR-018 发送成功后更新为 TRUE 并写入 pushed_at';

-- =============================================================================
-- 7. 阶段记录表 (stage_records)
-- 说明：记录构建模式（7阶段）和综述模式（5阶段）各阶段执行详情。
--       深度研究模式无固定阶段，不使用本表。
--       当前阶段通过查询本表 (project_id + mode, 取最新 started_at) 获取，
--       不在 projects 表冗余存储。
--
-- 构建模式阶段（mode='construction'）：
--   1-检索词生成  2-检索与汇总  3-评分与筛选  4-下载与解析
--   5-总结生成    6-格式化与储存  7-邮件发送（全自动，无用户交互暂停）
--
-- 综述模式阶段（mode='review'）：
--   1-扩写课题内容  2-生成综述架构  3-撰写章节内容  4-自动审查迭代  5-汇总成综述文章
-- =============================================================================
CREATE TABLE stage_records (
    id           VARCHAR(50)  NOT NULL,
    project_id   VARCHAR(50)  NOT NULL,
    mode         VARCHAR(20)  NOT NULL,             -- construction / review
    stage        SMALLINT     NOT NULL,             -- 构建模式 1-7；综述模式 1-5
    status       VARCHAR(20)  NOT NULL,             -- running / paused / completed / failed
    started_at   TIMESTAMPTZ  NOT NULL,
    completed_at TIMESTAMPTZ,
    paused_at    TIMESTAMPTZ,
    resumed_at   TIMESTAMPTZ,
    failed_at    TIMESTAMPTZ,
    result       JSONB,                             -- 阶段结果数据
    error        TEXT,
    user_actions JSONB,                             -- 用户操作记录（编辑/重新执行等）
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_stage_records PRIMARY KEY (id),
    CONSTRAINT fk_stage_records_project
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CONSTRAINT chk_stage_records_mode
        CHECK (mode   IN ('construction', 'review')),
    CONSTRAINT chk_stage_records_status
        CHECK (status IN ('running', 'paused', 'completed', 'failed')),
    CONSTRAINT chk_stage_records_stage_construction
        CHECK (NOT (mode = 'construction' AND (stage < 1 OR stage > 7))),
    CONSTRAINT chk_stage_records_stage_review
        CHECK (NOT (mode = 'review'        AND (stage < 1 OR stage > 5)))
);

CREATE INDEX idx_stage_records_project_id ON stage_records (project_id);
CREATE INDEX idx_stage_records_mode       ON stage_records (project_id, mode);
CREATE INDEX idx_stage_records_stage      ON stage_records (project_id, mode, stage);
CREATE INDEX idx_stage_records_status     ON stage_records (status);

COMMENT ON TABLE  stage_records             IS '构建/综述模式阶段执行记录；当前阶段查此表，不在 projects 冗余';
COMMENT ON COLUMN stage_records.mode        IS 'construction（7阶段）或 review（5阶段）';
COMMENT ON COLUMN stage_records.stage       IS '阶段编号；构建 1-7，综述 1-5';
COMMENT ON COLUMN stage_records.user_actions IS '用户在交互暂停点的操作记录（接受/编辑/重新执行等）';

-- =============================================================================
-- 8. 深度研究对话表 (research_dialogues)
-- 说明：每次用户开启一次主题性探讨即创建一条记录。
--       一个课题可包含多个对话会话，具体轮次在 dialogue_turns 中存储。
--       对话不改变 projects.status（无"运行中任务"概念）。
-- =============================================================================
CREATE TABLE research_dialogues (
    id             VARCHAR(50)  NOT NULL,
    project_id     VARCHAR(50)  NOT NULL,
    title          VARCHAR(255),                   -- 用户自定义或由首轮输入自动生成
    status         VARCHAR(20)  NOT NULL DEFAULT 'active',
    turn_count     INTEGER      NOT NULL DEFAULT 0,
    summary        TEXT,                           -- Agent 自动生成的对话摘要
    tags           JSONB,                          -- 用户标签列表（JSON 数组）
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_research_dialogues PRIMARY KEY (id),
    CONSTRAINT fk_research_dialogues_project
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CONSTRAINT chk_research_dialogues_status
        CHECK (status IN ('active', 'archived'))
);

CREATE INDEX idx_research_dialogues_project_id    ON research_dialogues (project_id);
CREATE INDEX idx_research_dialogues_status        ON research_dialogues (project_id, status);
CREATE INDEX idx_research_dialogues_last_active   ON research_dialogues (last_active_at);

COMMENT ON TABLE  research_dialogues              IS '深度研究模式对话会话列表；对话期间 projects.status 保持 idle';
COMMENT ON COLUMN research_dialogues.turn_count   IS '已完成的对话轮次数，与 dialogue_turns 行数保持一致';
COMMENT ON COLUMN research_dialogues.summary      IS 'Agent 自动生成的对话摘要（FR-028）';

-- =============================================================================
-- 9. 对话轮次表 (dialogue_turns)
-- 说明：每行 = 用户发言一次 + Agent 回复一次（一轮）。
--       turn_index 从 1 开始自增，保证会话内轮次顺序可还原。
--       sub_mode 决定注入不同的 system prompt 引导 LLM 风格。
-- =============================================================================
CREATE TABLE dialogue_turns (
    id                 VARCHAR(50)  NOT NULL,
    dialogue_id        VARCHAR(50)  NOT NULL,
    project_id         VARCHAR(50)  NOT NULL,  -- 冗余存储，便于直接查询
    turn_index         INTEGER      NOT NULL,  -- 会话内从 1 开始自增
    sub_mode           VARCHAR(20)  NOT NULL,  -- theory / technical / experiment
    user_content       TEXT         NOT NULL,
    assistant_content  TEXT         NOT NULL,
    referenced_papers  JSONB,                  -- Agent 引用的论文 ID 列表（JSON 数组）
    graph_nodes_used   JSONB,                  -- Graph-RAG 命中的知识图谱节点 ID 列表
    input_tokens       INTEGER,                -- 用于成本追踪
    output_tokens      INTEGER,                -- 用于成本追踪
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_dialogue_turns PRIMARY KEY (id),
    CONSTRAINT fk_dialogue_turns_dialogue
        FOREIGN KEY (dialogue_id) REFERENCES research_dialogues(id) ON DELETE CASCADE,
    CONSTRAINT fk_dialogue_turns_project
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CONSTRAINT uq_dialogue_turns_index UNIQUE (dialogue_id, turn_index),
    CONSTRAINT chk_dialogue_turns_sub_mode
        CHECK (sub_mode IN ('theory', 'technical', 'experiment'))
);

CREATE UNIQUE INDEX idx_dialogue_turns_index      ON dialogue_turns (dialogue_id, turn_index);
CREATE        INDEX idx_dialogue_turns_dialogue   ON dialogue_turns (dialogue_id);
CREATE        INDEX idx_dialogue_turns_project    ON dialogue_turns (project_id);
CREATE        INDEX idx_dialogue_turns_created_at ON dialogue_turns (created_at);

COMMENT ON TABLE  dialogue_turns                    IS '对话轮次，每行=用户输入+Agent回复，turn_index 保证顺序';
COMMENT ON COLUMN dialogue_turns.sub_mode           IS 'theory/technical/experiment，决定注入的 system prompt';
COMMENT ON COLUMN dialogue_turns.referenced_papers  IS 'Agent 回复引用的论文 ID 列表（JSON 数组）';
COMMENT ON COLUMN dialogue_turns.graph_nodes_used   IS 'Graph-RAG 图扩展命中的知识图谱节点 ID 列表';
COMMENT ON COLUMN dialogue_turns.input_tokens       IS '用户输入 token 数，用于 LLM 成本追踪';
COMMENT ON COLUMN dialogue_turns.output_tokens      IS 'Agent 回复 token 数，用于 LLM 成本追踪';

-- =============================================================================
-- 10. 综述架构表 (review_outlines)
-- 说明：每次发起新综述流程或手动创建版本时生成一条记录。
--       status='confirmed' 时，对应章节撰写（stage_records stage=3）才可开始。
--       version 在同一课题内自增。
-- =============================================================================
CREATE TABLE review_outlines (
    id              VARCHAR(50)  NOT NULL,
    project_id      VARCHAR(50)  NOT NULL,
    version         INTEGER      NOT NULL DEFAULT 1,  -- 同一课题内自增
    topic_expansion TEXT,                             -- 阶段1：用户确认后的课题扩写描述
    outline         JSONB,                            -- 阶段2：章节架构，见 spec 6.1 outline 字段示例
    status          VARCHAR(20)  NOT NULL DEFAULT 'draft',
    confirmed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_review_outlines PRIMARY KEY (id),
    CONSTRAINT fk_review_outlines_project
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CONSTRAINT uq_review_outlines_version UNIQUE (project_id, version),
    CONSTRAINT chk_review_outlines_status
        CHECK (status IN ('draft', 'confirmed', 'archived'))
);

CREATE UNIQUE INDEX idx_review_outlines_version    ON review_outlines (project_id, version);
CREATE        INDEX idx_review_outlines_project_id ON review_outlines (project_id);
CREATE        INDEX idx_review_outlines_status     ON review_outlines (project_id, status);

COMMENT ON TABLE  review_outlines                 IS '综述架构版本表；status=confirmed 后章节撰写才可开始';
COMMENT ON COLUMN review_outlines.version         IS '同一课题内自增版本号';
COMMENT ON COLUMN review_outlines.topic_expansion IS '阶段1产出：LLM 扩写后、用户确认的课题描述';
COMMENT ON COLUMN review_outlines.outline         IS '阶段2产出：章节架构 JSONB，含 title/abstract_hint/sections 数组';

-- =============================================================================
-- 11. 综述章节表 (review_chapters)
-- 说明：每章独立追踪撰写状态和审查迭代历史。
--       chapter_index 与 review_outlines.outline.sections[].index 对应。
-- =============================================================================
CREATE TABLE review_chapters (
    id              VARCHAR(50)  NOT NULL,
    outline_id      VARCHAR(50)  NOT NULL,
    project_id      VARCHAR(50)  NOT NULL,  -- 冗余存储，便于直接查询
    chapter_index   SMALLINT     NOT NULL,  -- 与 outline sections[].index 对应
    title           VARCHAR(255) NOT NULL,
    content         TEXT,                   -- 章节正文，Markdown 格式
    citations       JSONB,                  -- 引用论文列表，见 spec 6.1 citations 字段示例
    iteration_count SMALLINT     NOT NULL DEFAULT 0,
    review_history  JSONB,                  -- 每次审查的建议与结果，见 spec 6.1 review_history 示例
    status          VARCHAR(20)  NOT NULL DEFAULT 'pending',
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_review_chapters PRIMARY KEY (id),
    CONSTRAINT fk_review_chapters_outline
        FOREIGN KEY (outline_id) REFERENCES review_outlines(id) ON DELETE CASCADE,
    CONSTRAINT fk_review_chapters_project
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CONSTRAINT uq_review_chapters_index UNIQUE (outline_id, chapter_index),
    CONSTRAINT chk_review_chapters_status
        CHECK (status IN ('pending', 'writing', 'reviewing', 'completed'))
);

CREATE UNIQUE INDEX idx_review_chapters_index      ON review_chapters (outline_id, chapter_index);
CREATE        INDEX idx_review_chapters_outline_id ON review_chapters (outline_id);
CREATE        INDEX idx_review_chapters_project_id ON review_chapters (project_id);
CREATE        INDEX idx_review_chapters_status     ON review_chapters (project_id, status);

COMMENT ON TABLE  review_chapters                   IS '综述章节，每章独立追踪撰写状态和迭代历史';
COMMENT ON COLUMN review_chapters.chapter_index     IS '章节序号，与 review_outlines.outline.sections[].index 对应';
COMMENT ON COLUMN review_chapters.content           IS '章节正文，Markdown 格式';
COMMENT ON COLUMN review_chapters.citations         IS 'JSONB 数组，含 paper_id / citation_key / format_apa / context';
COMMENT ON COLUMN review_chapters.review_history    IS 'JSONB 数组，每次审查含 iteration/issues/suggestions/accepted/revised_at';

-- =============================================================================
-- 12. 推荐模块表 (recommendations)
-- 说明：用户发表研究观点和洞察，单向展示，禁止评论/回复/讨论功能（FR-011）。
--       可关联某条对话会话（dialogue_id 可为空，支持独立发布）。
-- =============================================================================
CREATE TABLE recommendations (
    id               VARCHAR(50)  NOT NULL,
    user_id          VARCHAR(50)  NOT NULL,
    dialogue_id      VARCHAR(50),                   -- 可为空，支持独立发布（不绑定特定对话）
    content_type     VARCHAR(50)  NOT NULL,          -- insight / conclusion / experiment_design 等
    title            VARCHAR(255) NOT NULL,
    content          TEXT         NOT NULL,
    tags             JSONB,                          -- 标签列表（JSON 数组）
    contact_info     VARCHAR(255),                   -- 仅展示用户名或邮箱，用于私下交流
    view_count       INTEGER      NOT NULL DEFAULT 0,
    like_count       INTEGER      NOT NULL DEFAULT 0,
    is_visible       BOOLEAN      NOT NULL DEFAULT TRUE,  -- 内容审核开关
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_recommendations PRIMARY KEY (id),
    CONSTRAINT fk_recommendations_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_recommendations_dialogue
        FOREIGN KEY (dialogue_id) REFERENCES research_dialogues(id) ON DELETE SET NULL
);

CREATE INDEX idx_recommendations_user_id    ON recommendations (user_id);
CREATE INDEX idx_recommendations_dialogue   ON recommendations (dialogue_id);
CREATE INDEX idx_recommendations_type       ON recommendations (content_type);
CREATE INDEX idx_recommendations_created_at ON recommendations (created_at DESC);
CREATE INDEX idx_recommendations_like_count ON recommendations (like_count DESC);

COMMENT ON TABLE  recommendations                IS '用户研究观点推荐，基础层功能，只与用户相关，单向展示，禁止评论/回复（FR-011）';
COMMENT ON COLUMN recommendations.content_type   IS 'insight / conclusion / experiment_design 等';
COMMENT ON COLUMN recommendations.contact_info   IS '仅展示用户名或邮箱，禁止存储其他联系方式';
COMMENT ON COLUMN recommendations.is_visible     IS '内容审核开关，FALSE 时前端不展示';

-- =============================================================================
-- 13. 系统配置表 (system_configs)
-- 说明：管理员设置的系统级全局配置（FR-029）。
--       命名规范与 user_configs 一致；普通用户无个人配置时系统回落读取此表。
--       updated_by 记录最后修改的管理员 ID（管理员删除时 SET NULL）。
-- =============================================================================
CREATE TABLE system_configs (
    id           VARCHAR(50)  NOT NULL,
    config_name  VARCHAR(100) NOT NULL,
    config_value TEXT         NOT NULL,
    description  VARCHAR(255),                        -- 配置项说明，供管理员界面展示
    updated_by   VARCHAR(50),                         -- 最后修改的管理员 user_id
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_system_configs         PRIMARY KEY (id),
    CONSTRAINT uq_system_configs_name    UNIQUE (config_name),
    CONSTRAINT fk_system_configs_updater
        FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX idx_system_configs_config_name ON system_configs (config_name);

COMMENT ON TABLE  system_configs             IS '管理员全局配置，命名规范与 user_configs 一致；普通用户无配置时回落读取（FR-029）';
COMMENT ON COLUMN system_configs.config_name IS '配置名称，UNIQUE，如 llm.provider.openai.url / database.arxiv.api_key';
COMMENT ON COLUMN system_configs.updated_by  IS '最后修改该配置的管理员 user_id；管理员删除时 SET NULL';

-- =============================================================================
-- END OF SCHEMA
-- =============================================================================
