# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
