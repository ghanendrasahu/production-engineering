# Usage

## Activating the Skill

- **OpenCode / Claude Code**: `@production-engineering <your task>`, or let auto-activation route it (triggers on "production-ready", "deploy", "reliability", "SLO", "incident", "scale", "cache", etc.).
- **Manual**: paste the specific topic doc into your agent's context and ask it to apply it.

## The Working Loop

1. **Frame the task** in one sentence + what "better" means (fewer 5xx? lower p99? faster deploys? safer merges?).
2. **Load narrowly**: open only the candidate topics (`docs/topic-index.md`) — usually 2–5.
3. **Classify each recommendation** with the CRITICAL/HIGH/MEDIUM/LOW/NOT-APPLICABLE table from SKILL.md. Challenge any CRITICAL without evidence.
4. **Ask for the plan, not the code** — the agent should propose: approach → trade-offs → verification → rollout/rollback → only then code.
5. **Gate on checklists**: deployment → `checklists`/`templates/production-readiness-checklist.md`; security → `workflows/security-review.md`; data → `database-review`-style checks in the audit template.
6. **Record decisions**: ADR for anything you'll forget the reason for (`templates/architecture-decision-record.md`).

## Prompts That Work (steal these)

**Review a service:**

```
@production-engineering Audit this service for production readiness.
Focus: failure paths, timeouts/retries, data integrity, health probes,
rollback. CRITICAL/HIGH/MEDIUM classification per finding.
```

**Design a system:**

```
@production-engineering Design a webhook ingestion service for 5k events/s
with at-least-once delivery and a 99.9% success SLO. Compare queue choices,
define DLQ + redrive, and list the 8 decisions I must sign off.
```

**Debug an incident:**

```
@production-engineering p99 on /checkout jumped 120ms → 900ms after last
night's deploy. Walk me through systematic triage with concrete queries.
```

**Plan a migration:**

```
@production-engineering We need to add a NOT NULL column to orders
(110M rows). Produce expand/contract plan with zero downtime and the
rollback at each step.
```

**Teach me:**

```
@production-engineering Explain idempotency and fencing to a junior.
Use topics 14 and 38; include one FastAPI example and one failure story.
```

## Reading a Topic Doc

Every topic doc has 24 sections. The ones to read first: **7/8 (when / when NOT)**, then **22 (readiness checklist)** and **23 (troubleshooting)**. Mechanism-heavy sections (5, 9, 10) are reference material — consult as you implement.

## What This Skill Deliberately Won't Do

Banish buzzword compliance; add infrastructure you don't need; bless designs without failure modes; accept unmeasured "best practices"; replace your judgment — it augments it.
