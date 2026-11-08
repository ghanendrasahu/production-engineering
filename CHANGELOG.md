# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] — 2026-11-08

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
