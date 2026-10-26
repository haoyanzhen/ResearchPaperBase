# Agents.md

Author: haoyanzhen
Date:   2026-06-01
Updated: 2026-10-25
Document version: v1.2

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
- A full-project task map is planning, not execution authorization. Continue through an explicitly authorized queue without per-task approval; pause only work dependent on an unresolved business decision or required milestone acceptance.
- A deferred item or backlog entry is not execution authorization. If additional scope is needed, explain it and pause only the dependent work while continuing work within scope.
- When a decision is needed, present: the question, available evidence, options and their effects, the recommended option, and the work blocked by the decision.

## Codex delivery principles

- Humans own business decisions and milestone acceptance; Codex owns implementation quality, requirement-oriented tests, independent review, verification, and engineering closeout within the authorized scope. Per-task human review is not a gate.
- Deliver small slices defined by observable behavior, including rejection and failure paths. Make routine engineering choices independently and explain material tradeoffs; do not expand scope through incidental refactoring or backlog work.
- Preserve existing working-tree changes. Bind review and verification to the actual artifact, including relevant uncommitted and untracked files, rather than HEAD alone.
- Self-review the diff, requirement coverage, critical boundaries, and execution evidence; complete independent review, coverage repair, behavior-preserving simplification, and final verification before engineering closeout. Fix independently resolvable defects without waiting for human review.
- Keep design completion, code completion, automated verification, and human acceptance distinct. Never infer human approval from passing checks or claim overall acceptance from a partial slice.
- Engineering delivery, business decision, and milestone acceptance procedures are maintained in the [implementation entry](docs/IMPLEMENTATION_ENTRY.md); task-specific scope, traceability, evidence, and decisions are recorded using the [task template](tasks/example.md), without duplicating those procedures here.

## Verification requirements

- Codex must write requirement-oriented test cases for every testable requirement and ensure they pass. Apply this obligation to every requirement in the authorized delivery scope, including affected existing requirements; track remaining project requirements explicitly without treating backlog as execution authorization.
- Derive test inputs, expected observable results, and prohibited side effects from requirements and approved rules, not from the implementation. Maintain traceability from each requirement to scenarios, executable tests, and current execution evidence; test counts or code coverage alone do not prove requirement coverage.
- Cover applicable success, rejection, failure, boundary, duplicate, concurrency, authorization, version-binding, and human-content-protection cases. Bug fixes require a regression test that reproduces the defect. Exercise real persistence and deterministic interleavings where the requirement depends on commits or races.
- Run all required cases for the delivery and affected regressions, repair defects, and rerun until they pass before declaring verification complete. Do not remove or weaken assertions, skip required cases, or change requirements merely to obtain a passing result. If a requirement is ambiguous or not yet executable, record the specific gap and resolve it through the existing decision or dependency process; it is not covered or passed.
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
4. Apply the verification requirements above to all in-scope testable requirements; use reference, version, and consistency checks for documentation-only changes.
5. Run relevant checks and report actual results, or explain why they could not run and what remains unverified.
6. Summarize the diff.
7. Explain remaining risks or unknowns.
