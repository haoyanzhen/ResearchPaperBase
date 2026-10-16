# Agents.md

Author: haoyanzhen
Date:   2026-06-01
Updated: 2026-10-16
Document version: v1.0

This file introduce the main aim and structure of this project.

## Main aim

Accomplish a web app as a deep search and research scholar workspace.

- Can manage users, personal/system LLM configuration, paper data source configuration, notification configuration, and Project permissions.
- Can generate and manage Project search terms, retrieve papers from multiple sources, deduplicate, screen, parse, analyze, and publish them into Project Knowledge Versions, with email push for new valid papers.
- Can support Project Workspace operations for Construction Runs, Research Sessions, Review Runs, knowledge asset viewing, exports, and workspace recovery.
- Can make Graph-RAG based research conversations and literature reviews on a research topic based on a Project Knowledge Version.
- Can support multiple users to collaborate through Project permissions and publish independent viewpoints without changing referenced Project or paper state.

## Core boundaries

- Workspace restores user working context and does not own Project knowledge assets or change Run, Session, or Knowledge Version business state.
- Construction Run is the writer of the Project knowledge base; only a successful Construction Run can publish a Knowledge Version.
- Research Session and Review Run bind to a Knowledge Version when created and must not be silently rewritten after that Knowledge Version changes.
- ProjectPaper and DocumentAsset are Project-scoped assets; sharing a paper identity must not automatically expose uploaded files or private analysis across Projects.
- Agent-generated content must not silently overwrite human-confirmed or human-edited content.

## Version control

- The major version of the current project is 1; project design documents remain at `v1.x`.
- When changing a project-owned document with an explicit version, increment that document's minor version and update its date. For a previously unversioned document, start at `v1.0`.
- Source files are tracked through Git; per-file version headers are not required.
- Third-party dependencies, lockfile formats, and database migration identifiers follow their own versioning rules. Do not rewrite them merely to match the project version.

## Verify current state

- At the start of a task, read [project status](docs/PROJECT_STATUS.md), the [design index](docs/design/README.md), and task-relevant files; inspect the Git working tree.
- Check completion claims against actual files and execution evidence. Distinguish planned work, executed work, and verified results.
- If documentation and actual state conflict, report the discrepancy as pending verification. Do not claim completion or delete or restore files merely to make reality match the documentation.
- Pause only operations that depend on the unresolved discrepancy; continue independent work. Keep implementation status in the project status entry point rather than duplicating it here.

## AI execution and human decisions

- Independently complete local implementation, fixes, tests, and necessary documentation updates within the authorized scope. Do not repeatedly ask for confirmation of already authorized work.
- Changes to business semantics, permission boundaries, human-content protection, knowledge-version binding, or product phasing require an explicit human decision unless already authorized.
- A deferred item or backlog entry is not execution authorization. If additional scope is needed, explain it and pause only the dependent work while continuing work within scope.
- When a decision is needed, present: the question, available evidence, options and their effects, the recommended option, and the work blocked by the decision.

## Verification requirements

- New or changed business behavior requires corresponding automated verification. Bug fixes should add regression tests that reproduce the defect.
- Run checks relevant to the change. If verification cannot be executed, record the reason, unverified scope, and follow-up commands; do not report acceptance as passed.
- For documentation-only changes, check references, versions, and consistency; unrelated application tests are not required.
- Database tests must explicitly use an isolated test environment and must not fall back to a business database configuration. Verify that test writes, including commits inside services, remain isolated and can be cleaned up.
- Mock LLMs, paper providers, and email services by default. Real integration checks require an explicit test target and a statement of external side effects; any action requiring authorization must already be authorized.
- Mock tests, health checks, and archived-fragment tests do not substitute for end-to-end acceptance.
- Once the new engineering entry points are established, document verified installation, test, and build commands. Do not copy old commands without checking their applicability.

## Work Style

Work in small, reviewable increments.

For each task:
1. Restate the goal briefly.
2. Identify the files that need to change.
3. Make the smallest sufficient change.
4. Add or update automated verification for changed business behavior; use reference, version, and consistency checks for documentation-only changes.
5. Run relevant checks and report actual results, or explain why they could not run and what remains unverified.
6. Summarize the diff.
7. Explain remaining risks or unknowns.
