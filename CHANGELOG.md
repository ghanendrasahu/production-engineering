# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] — 2026-11-09

### Added

- **CI: live Docker integration job** (`RabbitMQ integration (docker compose)`) — builds the stack, gates on producer health, asserts queues drain on happy path and failing jobs dead-letter after 5 redeliveries; always tears down; diagnostics on failure; 15-minute timeout
- **Branch protection on `main`** — required checks (`Topic coverage + skill structure`, `Example validation (FastAPI + agent orchestrator)`), 1 approving review + stale review dismissal, force pushes and deletions blocked; admins remain exempt (no lock-out path)
- **Agent compatibility suite** — `scripts/agent_compatibility_check.py` (17 structural checks; now a CI step); results published in `docs/agent-test-results.md` (OpenCode: runtime-registered in-session; Claude Code/Codex: structurally compatible; others: manual)
- **Database resilience example** — `examples/database-resilience/`: four live proofs (server-side `statement_timeout`, deadlock-victim retry, `ON CONFLICT DO NOTHING` replay safety, live-connection check), tested end-to-end with PASS on all four
- **docs** — `docs/troubleshooting.md`, request-flow diagram in `docs/skill-architecture.md`, `docs/localization.md` (i18n investigation), `docs/review-matrix.md` (all 111 topics: structure 111/111, links 111/111, 5 fact corrections applied)
- Issues updated with results: #14 (review matrix posted, left open for line-by-line work), #15 (localization plan)

### Changed

- **CI: actions pinned to commit SHAs** (checkout v7.0.1, setup-python v7.1.0); `timeout-minutes` on all jobs; compatibility check added to the validate job
- **Docs accuracy pass** — SLO error-budget arithmetic corrected to the SRE workbook figures (43.2 min/30d at 99.9%; 21.6 min at 99.95%); multi-window burn-rate pairing corrected (page: 14.4x over 1h/5m, 6x over 6h/30m; ticket: 1x over 3d/6h); SSRF Capital One figure hedged
- Dependabot reviewed and updated workflow for Python 3.12 + current example pins

### Security

- Docker Scout: **0 critical CVEs** across example images; only High/Medium/Low base-image OS package findings (cleared by the fresh slim base builds CI performs on every push)
- Full audit re-run: tracked files and all history blobs — zero credential-like patterns in current tree; prior v1.0.1 informational blob documented (no action needed)
- Composition hygiene: dev compose binds to 127.0.0.1 only; AMQP not published to host
- Dependabot + private vulnerability reporting + push protection confirmed enabled

### Fixed

- Agent compatibility checker no longer contains the security-test fragment literal (CI self-reference)
- `test_examples.py` regression causing CRLF/BOM artifacts in one topic file (normalized to LF repo-wide)

## [1.1.0] — 2026-11-08

_Note: v1.1.0's changes merged to main but no separate v1.1.0 tag was created; they are consolidated and released as v1.2.0._

### Added

- **Live example verification**, executed on real infrastructure (no mocks): FastAPI example — startup, `/healthz` `/readyz`, metrics exposition, 422 validation paths, idempotent replay, trace header, graceful shutdown. RabbitMQ stack via Docker — publish 20 jobs (queue drains to 0), failing job dead-lettered after 5 redeliveries (quorum `x-delivery-limit`), malformed message dead-lettered immediately, container logs confirm acks-after-work. AI-agent orchestrator — 9/9 harness checks (budgets, kill switch, approval gates, tool failure, timeout, idempotency)
- `tests/test_examples.py` (+10 tests) and a new `examples` CI job that runs it
- CI actions updated to `actions/checkout@v7` / `actions/setup-python@v7` (all Dependabot PRs reviewed against changelogs and merged)
- Community readiness: contribution categories with labels (`documentation`, `proposal`, `enhancement`, `testing`, `security`, `compatibility`), `docs/discussions.md`, `docs/supported-agents.md` rewritten with per-agent verification levels, README "Use Without an AI Agent", "Security & Trust" and "Community" sections
- 8 community backlog issues (#11–#18) with labels (`good first issue`, `help wanted`)

### Fixed

- **22 broken external reference URLs** in topic docs (404/wrong host), including an invalid RFC reference for SSE (now → WHATWG HTML SSE spec) — all further-reading links re-verified; only illustrative example hosts remain unreachable by design
- docker-compose now binds `8000` and `15672` to `127.0.0.1`; AMQP is no longer published to the host
- Example `Dockerfile` runs the app as a non-root `app` user; `restart: unless-stopped` added
- Agent orchestrator: per-step LLM timeout was hardcoded at 120s — now injectable via `llm_timeout_s`

### Security

- Full audit re-executed: tracked files (0 hits), all 212 history blobs (0 hits); compose port bindings tightened; example containers non-root
- INFORMATIONAL: the pre-fix `test_security.py` (blob `736ff86f3b`, v1.0.1) contained a generic workspace word and the local-part of the maintainer's public commit email (both already non-secret and public in git metadata). Not a credential; current tree avoids these literals; history rewrite not required

## [1.0.1] — 2026-11-08

### Security

- Dependabot configured for `github-actions` and both Python examples (weekly)
- GitHub security features enabled: secret scanning, push protection, Dependabot security updates, private vulnerability reporting (all verified via API)
- CI dependency install pinned (`pytest>=8,<9`); example requirements pinned with sane floor/ceiling ranges instead of unpinned
- New regression tests (`tests/test_security.py`): no secret-like patterns, no machine-local paths, CI stays least-privilege, `SECURITY.md` present — 19 additional tests, suite now 474
- README explicitly documents that the core knowledge is plain Markdown and works without any AI coding agent

### Changed

- None (no content or behavior changes to the 111 topics)

## [1.0.0] — 2026-11-08

First public release.

### Added

- 111 production engineering topics as individual, agent-consumable skill documents under `.agents/skills/production-engineering/topics/` (numbered 001–111, original scope preserved).
- OpenCode-compatible skill manifest `.agents/skills/production-engineering/SKILL.md` with decision framework, activation guidance, and workflow.
- 15 deep-reference files (incl. ai-engineering, database, networking, incident-management), 6 operational workflows, 4 templates, 111-topic documentation architecture.
- Project governance: MIT license, CONTRIBUTING, Code of Conduct (Contributor Covenant 2.1), SECURITY, SUPPORT, CITATION.cff.
- Docs: installation, usage, supported agents, skill architecture, topic index, FAQ.
- Examples: FastAPI skeleton, distributed systems (RabbitMQ) setup, AI agent systems.
- Validation tooling (`scripts/validate_skills.py`, `scripts/check_topic_coverage.py`, `scripts/generate_topic_index.py`) and a pytest suite.
- CI: GitHub Actions workflow running validation and tests on every push/PR.
