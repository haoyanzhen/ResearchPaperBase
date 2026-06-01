# Agents.md

Author: haoyanzhen
Date:   2026-06-01

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

- The major version of the current project is: 1
- The major version number of all files should be consistent with the major version of the project.
- The minor version should increase on the basis of the original version number. 

## Work Style

Work in small, reviewable increments.

For each task:
1. Restate the goal briefly.
2. Identify the files that need to change.
3. Make the smallest sufficient change.
4. Add or update tests if possible.
5. Run relevant tests if possible.
6. Summarize the diff.
7. Explain remaining risks or unknowns.
