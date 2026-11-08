# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
