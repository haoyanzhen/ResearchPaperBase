/**
 * Research Paper Base — 跨模块共享数据结构定义
 *
 * 对齐文档：spec.md v1.7 / schema.sql v1.0 + migration 0002
 * 维护规则：本文件是前后端类型的唯一权威来源。
 *           任何业务模块不得在本地重复定义这些结构；
 *           表结构变更须同步更新 schema.sql 和本文件。
 */

// =============================================================================
// 通用基础类型
// =============================================================================

/** ISO 8601 格式的 UTC 时间字符串，对应数据库 TIMESTAMPTZ */
export type ISODateString = string;

/** YYYY-MM-DD 格式的日期字符串，对应数据库 DATE */
export type DateString = string;

// =============================================================================
// 枚举 / 字面量联合类型
// =============================================================================

/** 研究模式（projects.mode） */
export type ProjectMode = 'construction' | 'deep_research' | 'review';

/**
 * 项目任务状态（projects.status）
 *
 * - idle:     无活动任务，项目可正常操作（初始值；任务完成/失败处理后回归）
 * - running:  构建/综述模式某阶段正在执行；定时调度器触发时写入
 * - paused:   到达阶段交互暂停点，等待用户操作
 * - error:    LLM 调用重试后仍失败，需用户介入；用户处理后恢复为 idle
 * - archived: 用户主动归档；归档后禁止启动新任务
 *
 * 注意：深度研究对话期间 status 保持 idle，对话无"运行中任务"概念。
 */
export type ProjectStatus = 'idle' | 'running' | 'paused' | 'error' | 'archived';

/** 论文下载状态（papers.download_status） */
export type DownloadStatus = 'not_downloaded' | 'success' | 'failed';

/** AI 分析状态（papers.ai_analysis_status） */
export type AiAnalysisStatus = 'not_analyzed' | 'success' | 'failed';

/** 阶段记录所属模式（stage_records.mode） */
export type StageMode = 'construction' | 'review';

/** 阶段执行状态（stage_records.status） */
export type StageStatus = 'running' | 'paused' | 'completed' | 'failed';

/**
 * 构建模式阶段编号（1-7）
 * 1-检索词生成 2-检索与汇总 3-评分与筛选 4-下载与解析
 * 5-总结生成   6-格式化与储存  7-邮件发送（全自动，无用户交互暂停）
 */
export type ConstructionStage = 1 | 2 | 3 | 4 | 5 | 6 | 7;

/**
 * 综述模式阶段编号（1-5）
 * 1-扩写课题内容 2-生成综述架构 3-撰写章节内容 4-自动审查迭代 5-汇总成综述文章
 */
export type ReviewStage = 1 | 2 | 3 | 4 | 5;

/** 对话子模式（dialogue_turns.sub_mode） */
export type SubMode = 'theory' | 'technical' | 'experiment';

/** 对话会话状态（research_dialogues.status） */
export type DialogueStatus = 'active' | 'archived';

/** 综述架构状态（review_outlines.status） */
export type OutlineStatus = 'draft' | 'confirmed' | 'archived';

/** 综述章节状态（review_chapters.status） */
export type ChapterStatus = 'pending' | 'writing' | 'reviewing' | 'completed';

/** 数据导出类型（FR-009） */
export type ExportType = 'excel' | 'pdf_zip';

/** 论文检索来源 */
export type PaperSource = 'arxiv' | 'openalex' | 'semantic_scholar' | 'ads';

/** 推荐内容类型（FR-011） */
export type RecommendationContentType = 'insight' | 'conclusion' | 'experiment_design' | string;

// =============================================================================
// 关系型数据库实体类型（对应 schema.sql 各表）
// =============================================================================

/** users 表 */
export interface User {
  id: string;
  username: string;
  email: string;
  password_hash: string;
  /** 是否为管理员；首位注册用户自动为 true（FR-029） */
  is_admin: boolean;
  /** 账号是否启用；管理员禁用后为 false，禁用账号无法登录 */
  is_active: boolean;
  created_at: ISODateString;
  updated_at: ISODateString;
  last_login_at: ISODateString | null;
}

/**
 * system_configs 表（管理员全局配置，FR-029）
 *
 * 命名规范与 user_configs 一致；普通用户无个人配置时系统回落读取此表。
 */
export interface SystemConfig {
  id: string;
  config_name: string;
  config_value: string;
  description: string | null;
  updated_by: string | null;
  created_at: ISODateString;
  updated_at: ISODateString;
}

/** user_configs 表（Key-Value 配置项） */
export interface UserConfig {
  id: string;
  user_id: string;
  config_name: string;
  config_value: string;        // 复杂配置以 JSON 字符串格式存储
  is_system_default: boolean;
  created_at: ISODateString;
  updated_at: ISODateString;
}

/** projects 表 */
export interface Project {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  mode: ProjectMode;
  status: ProjectStatus;
  total_papers: number;
  valid_papers: number;
  auto_push: boolean;
  push_interval: number | null;  // 单位：天，auto_push=true 时有效
  last_push_at: ISODateString | null;
  next_push_at: ISODateString | null;  // 由调度器写入
  created_at: ISODateString;
  updated_at: ISODateString;
}

/** keywords 表 */
export interface Keyword {
  id: string;
  project_id: string;
  search_word: string;
  boolean_expressions: KeywordBooleanExpressions | null;
  searched_papers_arxiv: number;
  searched_papers_openalex: number;
  searched_papers_semanticscholar: number;
  searched_papers_ads: number;
  searched_papers_total: number;
  is_searched: boolean;   // DEFAULT FALSE，执行过搜索后置为 true
  is_selected: boolean;   // DEFAULT TRUE，FR-010 定时任务仅使用 is_selected=true 的记录
  created_at: ISODateString;
  last_search_at: ISODateString;
}

/** keywords.boolean_expressions JSONB 结构 */
export interface KeywordBooleanExpressions {
  arxiv?: string;
  openalex?: string;
  semantic_scholar?: string;
  ads?: string;
}

/** papers 表（全局共享，每篇论文只存一份） */
export interface Paper {
  id: string;
  doi: string | null;
  arxiv_id: string | null;
  title: string;             // 小写格式，用于去重
  authors: string[] | null;  // JSON 数组
  pub_date: DateString | null;
  venue: string | null;
  abstract: string | null;
  source: PaperSource | null;
  retrieved_at: ISODateString;
  download_status: DownloadStatus;
  pdf_path: string | null;
  text_path: string | null;
  download_error: string | null;
  ai_analysis_status: AiAnalysisStatus;
  ai_analysis: AiAnalysis | null;
  created_at: ISODateString;
  updated_at: ISODateString;
}

/** papers.ai_analysis JSONB 结构（构建模式阶段5产出） */
export interface AiAnalysis {
  summary: string;            // 一句话总结
  highlights: string[];       // 亮点解析
  relevance_points: string[]; // 相关性要点
  technical_methods: string[];// 技术方法与创新
}

/**
 * project_paper_relations 表
 * 评分和推送状态按课题独立存储。
 * is_valid DEFAULT FALSE，评分完成后显式置为 true（总分≥7）。
 */
export interface ProjectPaperRelation {
  id: string;
  project_id: string;
  paper_id: string;
  reference_score: number | null;  // 参考价值评分（0-5）
  technical_score: number | null;  // 技术价值评分（0-5）
  total_score: number | null;      // 总分（0-10）
  scoring_reason: string | null;
  is_valid: boolean;               // DEFAULT FALSE；评分完成后显式置为 true
  push_status: boolean;            // DEFAULT FALSE；FR-018 发送后置为 true
  pushed_at: ISODateString | null;
  created_at: ISODateString;
  updated_at: ISODateString;
}

/** stage_records 表基础字段（不含 mode/stage） */
interface StageRecordBase {
  id: string;
  project_id: string;
  status: StageStatus;
  started_at: ISODateString;
  completed_at: ISODateString | null;
  paused_at: ISODateString | null;
  resumed_at: ISODateString | null;
  failed_at: ISODateString | null;
  error: string | null;
  user_actions: UserAction[] | null;
  created_at: ISODateString;
}

/** stage_records 表 — 构建模式行（mode='construction'，stage 1-7） */
export interface ConstructionStageRecord extends StageRecordBase {
  mode: 'construction';
  stage: ConstructionStage;
  result: StageResult | null;
}

/** stage_records 表 — 综述模式行（mode='review'，stage 1-5） */
export interface ReviewStageRecord extends StageRecordBase {
  mode: 'review';
  stage: ReviewStage;
  result: null;  // 综述模式阶段结果暂无结构化定义，存储在 review_outlines/review_chapters
}

/**
 * stage_records 表（判别联合）
 * TypeScript 可通过 record.mode 自动收窄 stage 类型范围，
 * 防止 mode='review', stage=7 等非法组合通过编译。
 */
export type StageRecord = ConstructionStageRecord | ReviewStageRecord;

/** stage_records.result JSONB 各阶段产出物的联合类型 */
export type StageResult =
  | Stage1Result   // 检索词生成
  | Stage2Result   // 检索与汇总
  | Stage3Result   // 评分与筛选
  | Stage4Result   // 下载与解析
  | Stage5Result   // 总结生成
  | Stage6Result   // 格式化与储存
  | Stage7Result;  // 邮件发送

export interface Stage1Result {
  stage: 1;
  keywords_generated: number;
  keyword_ids: string[];
}

export interface Stage2Result {
  stage: 2;
  total_retrieved: number;
  after_dedup: number;
  by_source: Partial<Record<PaperSource, number>>;  // 用户可能只配置部分数据源（FR-003）
}

export interface Stage3Result {
  stage: 3;
  total_scored: number;
  valid_count: number;
  new_papers_count: number;
}

export interface Stage4Result {
  stage: 4;
  download_success: number;
  download_failed: number;
  used_abstract_fallback: number;
}

export interface Stage5Result {
  stage: 5;
  analyzed_count: number;
  failed_count: number;
}

export interface Stage6Result {
  stage: 6;
  pg_written: number;
  chroma_written: number;
  graph_updated: number;
}

export interface Stage7Result {
  stage: 7;
  emails_sent: number;
  papers_pushed: number;
  skipped: boolean;  // true 表示无未推送论文，跳过发送
}

/** stage_records.user_actions JSONB 元素 */
export interface UserAction {
  /** accept=接受结果 | edit=编辑结果 | retry=重新执行 | continue=继续下一阶段（FR-019） */
  action: 'accept' | 'edit' | 'retry' | 'continue';
  timestamp: ISODateString;
  detail?: Record<string, unknown>;
}

/**
 * FR-028 Agent总结模块输出结构
 * 对应 research_dialogues.summary 字段的 JSON 内容（DB 层存储为 TEXT/JSON 字符串）
 *
 * 四类输出来自 FR-028 规格：
 *   - progress:      研究进展总结
 *   - key_findings:  关键发现列表
 *   - pending_issues:待解决问题清单
 *   - next_steps:    下一步研究建议
 */
export interface AgentSummary {
  progress: string;
  key_findings: string[];
  pending_issues: string[];
  next_steps: string[];
  generated_at: ISODateString;
}

/** research_dialogues 表 */
export interface ResearchDialogue {
  id: string;
  project_id: string;
  title: string | null;
  status: DialogueStatus;
  turn_count: number;
  /** FR-028 Agent 总结内容；DB 存为 TEXT（JSON 字符串），API 层解析为 AgentSummary */
  summary: AgentSummary | null;
  tags: string[] | null;
  created_at: ISODateString;
  updated_at: ISODateString;
  last_active_at: ISODateString;
}

/** dialogue_turns 表 */
export interface DialogueTurn {
  id: string;
  dialogue_id: string;
  project_id: string;
  turn_index: number;       // 会话内从 1 开始自增
  sub_mode: SubMode;
  user_content: string;
  assistant_content: string;
  referenced_papers: string[] | null;   // paper_id 列表
  graph_nodes_used: string[] | null;    // 知识图谱节点 ID 列表
  input_tokens: number | null;
  output_tokens: number | null;
  created_at: ISODateString;
}

/** review_outlines 表 */
export interface ReviewOutline {
  id: string;
  project_id: string;
  version: number;
  topic_expansion: string | null;  // 阶段1产出：用户确认的课题扩写描述
  outline: ReviewOutlineContent | null;
  status: OutlineStatus;
  confirmed_at: ISODateString | null;
  created_at: ISODateString;
  updated_at: ISODateString;
}

/** review_outlines.outline JSONB 结构 */
export interface ReviewOutlineContent {
  title: string;
  abstract_hint: string;
  sections: ReviewSection[];
}

export interface ReviewSection {
  index: number;
  title: string;
  type: 'introduction' | 'related_work' | 'methodology' | 'experiment' | 'conclusion' | string;
  key_points: string[];
}

/** review_chapters 表 */
export interface ReviewChapter {
  id: string;
  outline_id: string;
  project_id: string;
  chapter_index: number;   // 与 ReviewSection.index 对应
  title: string;
  content: string | null;  // Markdown 格式
  citations: ChapterCitation[] | null;
  iteration_count: number;
  review_history: ReviewIteration[] | null;
  status: ChapterStatus;
  completed_at: ISODateString | null;
  created_at: ISODateString;
  updated_at: ISODateString;
}

/** review_chapters.citations JSONB 元素 */
export interface ChapterCitation {
  paper_id: string;
  citation_key: string;     // 如 "doe2024novel"
  format_apa: string;
  context: string;          // 引用上下文说明
}

/** review_chapters.review_history JSONB 元素 */
export interface ReviewIteration {
  iteration: number;
  reviewed_at: ISODateString;
  issues: string[];
  suggestions: string[];
  accepted: boolean;
  revised_at: ISODateString | null;
}

/** recommendations 表（基础层，只与用户相关，无课题归属） */
export interface Recommendation {
  id: string;
  user_id: string;
  dialogue_id: string | null;
  content_type: RecommendationContentType;
  title: string;
  content: string;
  tags: string[] | null;
  contact_info: string | null;  // 仅用户名或邮箱
  view_count: number;
  like_count: number;
  is_visible: boolean;
  created_at: ISODateString;
  updated_at: ISODateString;
}

// =============================================================================
// 向量数据库（ChromaDB）类型
// =============================================================================

/** ChromaDB Collection 命名规范：project_{project_id}_vectors */
export type ChromaCollectionName = `project_${string}_vectors`;

/** ChromaDB 向量文档 ID 格式：paper_{paper_id}_chunk_{chunk_id} */
export type ChromaDocumentId = `paper_${string}_chunk_${number}`;

/** ChromaDB 向量文档元数据（metadata 字段） */
export interface VectorDocumentMetadata {
  paper_id: string;
  project_id: string;
  chunk_id: number;
  chunk_type: 'abstract' | 'content' | 'conclusion';
  section: string;
  start_char: number;
  end_char: number;
  authors: string[];
  pub_date: DateString;
  venue: string;
  title: string;
  doi: string | null;
  keywords: string[];
  is_valid: boolean;
  total_score: number;
  reference_score: number;
  technical_score: number;
}

/** ChromaDB 向量文档（完整结构） */
export interface VectorDocument {
  id: ChromaDocumentId;
  embedding: number[];           // 1536维，text-embedding-ada-002
  metadata: VectorDocumentMetadata;
  document: string;              // 原始文本内容
}

// =============================================================================
// 图数据库（NetworkX）类型
// =============================================================================

/** 知识图谱节点类型 */
export type GraphNodeType = 'paper' | 'author' | 'keyword' | 'venue' | 'concept' | 'method';

/** 知识图谱边类型 */
export type GraphEdgeType =
  | 'authored_by'
  | 'has_keyword'
  | 'in_venue'
  | 'mentions_concept'
  | 'uses_method'
  | 'cites'
  | 'collaborates_with'
  | 'related_to'
  | 'similar_to';

/** 论文节点属性 */
export interface PaperGraphNode {
  node_type: 'paper';
  paper_id: string;
  project_id: string;
  title: string;
  authors: string[];            // author_{normalized_name} 格式
  pub_date: DateString;
  venue: string;
  doi: string | null;
  abstract: string;
  total_score: number;
  is_valid: boolean;
  keywords: string[];           // keyword_{normalized} 格式
  chunk_count: number;
  citations: string[];          // paper_{id} 格式
}

/** 作者节点属性 */
export interface AuthorGraphNode {
  node_type: 'author';
  author_name: string;
  normalized_name: string;
  paper_count: number;
  affiliation: string | null;
  h_index: number | null;
  papers: string[];             // paper_{id} 格式
}

/** 关键词节点属性 */
export interface KeywordGraphNode {
  node_type: 'keyword';
  keyword: string;
  normalized_keyword: string;
  paper_count: number;
  related_keywords: string[];
  growth_trend: number | null;
}

/** 概念节点属性 */
export interface ConceptGraphNode {
  node_type: 'concept';
  concept_name: string;
  normalized_name: string;
  definition: string | null;
  paper_count: number;
  related_concepts: string[];
}

/** 方法节点属性 */
export interface MethodGraphNode {
  node_type: 'method';
  method_name: string;
  normalized_name: string;
  description: string | null;
  paper_count: number;
  related_methods: string[];
}

/** 知识图谱节点（联合类型） */
export type GraphNode =
  | PaperGraphNode
  | AuthorGraphNode
  | KeywordGraphNode
  | ConceptGraphNode
  | MethodGraphNode;

/** 引用边属性 */
export interface CitesEdge {
  edge_type: 'cites';
  source_paper: string;
  target_paper: string;
  citation_count: number;
  citation_context: string | null;
  strength: number;
}

/** 合作边属性 */
export interface CollaboratesWithEdge {
  edge_type: 'collaborates_with';
  source_author: string;
  target_author: string;
  collaboration_count: number;
  papers_together: string[];
}

/** 通用边属性（其他边类型） */
export interface GenericEdge {
  edge_type: Exclude<GraphEdgeType, 'cites' | 'collaborates_with'>;
  source: string;
  target: string;
  weight: number;
}

/** 知识图谱边（联合类型） */
export type GraphEdge = CitesEdge | CollaboratesWithEdge | GenericEdge;

// =============================================================================
// 业务流程类型（非数据库实体，用于 API 层和 Agent 层交互）
// =============================================================================

/** Graph-RAG 检索参数（FR-026 内部实现参数） */
export interface GraphRAGParams {
  project_id: string;             // 确定查询的 ChromaDB Collection: project_{project_id}_vectors
  query: string;
  sub_mode: SubMode;
  top_k?: number;                   // DEFAULT 10
  similarity_threshold?: number;    // DEFAULT 0.7
  graph_expansion_depth?: number;   // DEFAULT 2
  max_context_length?: number;      // DEFAULT 28000 tokens
}

/** Graph-RAG 检索结果 */
export interface GraphRAGResult {
  chunks: VectorDocument[];
  graph_nodes: GraphNode[];
  context: string;                  // 构建好的 LLM 上下文字符串
  referenced_paper_ids: string[];
  graph_node_ids: string[];
}

/** 模式切换请求（FR-005） */
export interface ModeSwitchRequest {
  target_mode: ProjectMode;
  reason?: string;
  running_task_action?: 'stay' | 'leave_and_cancel';
}

/** 数据导出请求（FR-009） */
export interface ExportRequest {
  project_id: string;
  export_type: ExportType;
  filters?: ExportFilters;
}

export interface ExportFilters {
  is_valid?: boolean;
  push_status?: boolean;
  source?: PaperSource;
}

/** 数据导出结果 */
export interface ExportResult {
  download_url: string;
  total_count: number;
  exported_count: number;
  skipped_count: number;
  skipped_reasons?: string[];
}

/** 论文在课题内的完整视图（papers + project_paper_relations 连接查询） */
export interface PaperWithRelation extends Paper {
  relation: ProjectPaperRelation;
}
