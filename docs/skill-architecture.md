# Skill Architecture

How this repository is laid out and why — read this before adding topics or restructuring.

## Directory Map

```
.agents/skills/production-engineering/     ← skill root; ID == directory name
├── SKILL.md                               ← activation contract: when to load, how to think, decision framework
├── topics/                                ← the knowledge: 111 atomic topic documents
│   ├── 001-rate-limiting.md
│   └── … 111 … 111-postmortems.md
├── references/                            ← mechanism-deep, cross-topic reference (15 files)
│   ├── architecture.md   backend-engineering.md   distributed-systems.md
│   ├── reliability.md    security.md              performance.md
│   ├── observability.md  infrastructure.md         deployment.md
│   ├── testing.md        ai-engineering.md        engineering-checklists.md
│   ├── database-engineering.md   networking.md    incident-management.md
├── workflows/                             ← task-shaped playbooks (new-service, deploy, incident…)
└── templates/                             ← ADR, TDD, incident report, readiness checklist
```

Repo-level extras: `docs/` (human docs), `examples/` (runnable), `scripts/` (validation), `tests/` (pytest), `.github/` (CI + templates).

## The Topic Document Contract (every topic complies)

1. **Linking policy** — topics link across to each other by `#number Name`; references and topics may link by relative path. No external link is required for correctness (they are "further reading", not normative).
2. **Numbering is forever** — 1–111; slugs stable; additions require a proposal (`.github/ISSUE_TEMPLATE/new_skill_proposal.md`) and are appended as 112+.
3. **Self-containment** — a topic opened cold must be comprehensible; deep context lives in references.
4. **Structure** — YAML frontmatter (`topic`, `title`, `category`, `skill`, `status`) then 24 fixed sections (metadata → what/why → mechanism → use/don't → implementation → production → code → FastAPI → distributed → AI → security → performance → common mistakes/anti-patterns → monitoring → testing → deployment → checklist → troubleshooting → further reading).
5. **Verification over vibes** — every topic carries metrics to emit (§19), a test strategy (§20), and a readiness checklist (§22). If a claim can't be checked, it doesn't belong.

## Why This Layout

- **Agents retrieve, they don't memorize.** 24 small sections beat one 600-page wall; targeted reads keep the agent fast and un-anchored.
- **Topics are the unit of change** — a PR touches 1 topic + generated index; conflicts stay small; review stays mechanical (checklist per section).
- **References compress skills, references don't replace them** — mechanism once, applied everywhere via cross-references.
- **Validation is objective** — `scripts/check_topic_coverage.py` enforces numbering/identity; `validate_skills.py` enforces structure/links/fences/secrets; `generate_topic_index.py --check` enforces the index; CI runs all three.

## Invariants Enforced by CI

- 111 topics, numbers 1–111, filenames `NNN-slug.md` matching number+slug rule
- frontmatter valid; 24 sections present per topic
- all relative links inside the skill resolve
- no secrets/tokens (regex scan)
- docs/topic-index.md matches generated content

## Evolution Rules (how to extend without breaking agents)

- Never reorder/renumber topics; add 112+.
- Never change `name` in SKILL.md (ID is the registry key).
- Breaking content changes bump the minor version and get a CHANGELOG entry.
- Deprecations: mark `status: deprecated` + migration note; removal only in a major release with 2-release notice.
