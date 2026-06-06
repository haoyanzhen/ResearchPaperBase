-- Research Paper Base MVP schema draft
-- Version: v1.2
-- Updated: 2026-06-06
-- Authority: docs/design/01_functional_requirements.md and docs/design/00_layers.md

create table users (
  id uuid primary key,
  username text not null unique,
  email text not null unique,
  password_hash text not null,
  is_admin boolean not null default false,
  status text not null check (status in ('active', 'disabled', 'deleted')),
  created_at timestamptz not null,
  updated_at timestamptz not null
);

create table projects (
  id uuid primary key,
  owner_user_id uuid not null references users(id),
  name text not null,
  description text,
  status text not null check (status in ('active', 'archived', 'deleted')),
  default_knowledge_version_id uuid,
  last_opened_object_type text,
  last_opened_object_id uuid,
  created_at timestamptz not null,
  updated_at timestamptz not null
);

create table construction_workspaces (
  id uuid primary key,
  project_id uuid not null unique references projects(id),
  auto_update_enabled boolean not null default false,
  settings_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null,
  updated_at timestamptz not null
);

create table search_terms (
  id uuid primary key,
  workspace_id uuid not null references construction_workspaces(id),
  term text not null,
  enabled boolean not null default true,
  auto_update_enabled boolean not null default false,
  data_source_policy_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null,
  updated_at timestamptz not null
);

create table runtime_config_snapshots (
  id uuid primary key,
  owner_user_id uuid not null references users(id),
  project_id uuid references projects(id),
  source_type text not null,
  snapshot_json jsonb not null,
  created_at timestamptz not null
);

create table construction_runs (
  id uuid primary key,
  project_id uuid not null references projects(id),
  workspace_id uuid not null references construction_workspaces(id),
  trigger_type text not null check (trigger_type in ('manual', 'automatic')),
  status text not null,
  phase text,
  runtime_config_snapshot_id uuid references runtime_config_snapshots(id),
  started_by_user_id uuid references users(id),
  started_at timestamptz,
  finished_at timestamptz,
  diagnostic_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null,
  updated_at timestamptz not null
);

create unique index ux_active_construction_run
on construction_runs(project_id)
where status in ('queued', 'running', 'waiting_user');

create table papers (
  id uuid primary key,
  doi text,
  arxiv_id text,
  source_ids_json jsonb not null default '{}'::jsonb,
  title text not null,
  abstract text,
  publication_date date,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null,
  updated_at timestamptz not null
);

create unique index ux_papers_doi on papers(lower(doi)) where doi is not null;
create unique index ux_papers_arxiv on papers(lower(arxiv_id)) where arxiv_id is not null;

create table project_papers (
  id uuid primary key,
  project_id uuid not null references projects(id),
  paper_id uuid not null references papers(id),
  construction_run_id uuid references construction_runs(id),
  relevance_score numeric,
  validity_status text not null default 'candidate',
  pushed_status text not null default 'not_pushed',
  ai_analysis_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique(project_id, paper_id)
);

create table document_assets (
  id uuid primary key,
  project_paper_id uuid not null references project_papers(id),
  asset_type text not null check (asset_type in ('pdf', 'parsed_text', 'remote_url')),
  storage_key text,
  access_metadata_json jsonb not null default '{}'::jsonb,
  parse_status text,
  degradation_reason text,
  created_at timestamptz not null,
  updated_at timestamptz not null
);

create table knowledge_versions (
  id uuid primary key,
  project_id uuid not null references projects(id),
  source_construction_run_id uuid references construction_runs(id),
  version_number integer not null,
  status text not null check (status in ('building', 'published', 'failed', 'superseded')),
  vector_index_ref text,
  graph_ref text,
  diagnostic_json jsonb not null default '{}'::jsonb,
  published_at timestamptz,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique(project_id, version_number)
);

alter table projects
  add constraint fk_projects_default_knowledge_version
  foreign key (default_knowledge_version_id) references knowledge_versions(id);

create table research_sessions (
  id uuid primary key,
  project_id uuid not null references projects(id),
  knowledge_version_id uuid not null references knowledge_versions(id),
  owner_user_id uuid not null references users(id),
  title text,
  status text not null,
  output_preference text,
  runtime_config_snapshot_id uuid references runtime_config_snapshots(id),
  created_at timestamptz not null,
  updated_at timestamptz not null
);

create table research_messages (
  id uuid primary key,
  research_session_id uuid not null references research_sessions(id),
  role text not null check (role in ('user', 'assistant', 'system')),
  content text not null,
  citations_json jsonb not null default '[]'::jsonb,
  created_at timestamptz not null
);

create table review_runs (
  id uuid primary key,
  project_id uuid not null references projects(id),
  knowledge_version_id uuid not null references knowledge_versions(id),
  owner_user_id uuid not null references users(id),
  title text not null,
  status text not null,
  runtime_config_snapshot_id uuid references runtime_config_snapshots(id),
  created_at timestamptz not null,
  updated_at timestamptz not null
);

create table review_chapters (
  id uuid primary key,
  review_run_id uuid not null references review_runs(id),
  chapter_order integer not null,
  title text not null,
  content text,
  status text not null,
  content_source text not null default 'agent_draft',
  citations_json jsonb not null default '[]'::jsonb,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique(review_run_id, chapter_order)
);

create table locks (
  id uuid primary key,
  lock_key text not null unique,
  owner_ref text not null,
  expires_at timestamptz not null,
  diagnostic_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null
);

create table export_jobs (
  id uuid primary key,
  owner_user_id uuid not null references users(id),
  project_id uuid references projects(id),
  target_type text not null,
  target_id uuid not null,
  format text not null,
  status text not null,
  storage_key text,
  diagnostic_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null,
  updated_at timestamptz not null
);

create table email_push_jobs (
  id uuid primary key,
  project_id uuid not null references projects(id),
  construction_run_id uuid references construction_runs(id),
  owner_user_id uuid not null references users(id),
  status text not null,
  recipient_snapshot_json jsonb not null default '[]'::jsonb,
  paper_scope_json jsonb not null default '[]'::jsonb,
  diagnostic_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null,
  updated_at timestamptz not null
);

create table viewpoints (
  id uuid primary key,
  owner_user_id uuid not null references users(id),
  type text,
  title text not null,
  body text not null,
  tags_json jsonb not null default '[]'::jsonb,
  contact text,
  status text not null check (status in ('published', 'hidden', 'deleted')),
  created_at timestamptz not null,
  updated_at timestamptz not null
);

create table audit_logs (
  id uuid primary key,
  actor_user_id uuid references users(id),
  action text not null,
  target_type text not null,
  target_id uuid,
  result text not null,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null
);
