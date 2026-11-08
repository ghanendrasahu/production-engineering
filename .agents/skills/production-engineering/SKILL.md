---
name: production-engineering
description: Production-grade engineering knowledge for AI coding agents â€” 111 topics covering backend architecture, distributed systems, databases, deployment, security, reliability, performance, networking, infrastructure, and incident management. Use when developing, debugging, reviewing, optimizing, scaling, or deploying software; when designing or auditing APIs, services, data stores, queues, or caches; when choosing rollout, reliability, or security patterns; before any production deploy; and for FastAPI, Python, Docker/Kubernetes, CI/CD, and AI/RAG/LLM production systems.
metadata:
  opencode/autoinvoke: true
---

# Production Engineering â€” Skill for AI Coding Agents

You are acting as a principal/staff-level engineer. This skill gives you the judgment, patterns,
and checklists to design, build, review, and operate production software professionally.

**Skill ID:** `production-engineering` Â· **Version:** 1.0.0 Â· **License:** MIT

## What This Skill Contains

```
.agents/skills/production-engineering/
â”œâ”€â”€ SKILL.md              â† you are here (activation + decision framework)
â”œâ”€â”€ topics/               â† 111 topic documents (001..111), 24 sections each
â”œâ”€â”€ references/           â† 15 deep-dive files (architecture, security, â€¦)
â”œâ”€â”€ workflows/            â† operational playbooks (deploy, incident, review)
â””â”€â”€ templates/            â† ADRs, design docs, incident reports, checklists
```

Topics are numbered **1â€“111** with stable slugs (`topics/001-rate-limiting.md` â€¦).
Read [docs/topic-index.md](../../../docs/topic-index.md) for the full map.

## When to Activate This Skill

Activate when the task involves ANY of:

- Designing, reviewing, or modifying a backend service, API, data store, queue, cache, or pipeline
- Debugging production problems: timeouts, retries, latency spikes, deadlocks, pool exhaustion, memory growth, slow queries, stale caches, lost messages, flapping redirects
- Choosing delivery controls: rate limiting, caching, load balancing, rollouts (canary/blue-green/rolling), rollbacks, autoscaling
- Security controls: authN/Z, secrets, TLS, injection classes, CORS/CSRF, SSRF, encryption
- Reliability and operations: SLOs, alerts, incidents, on-call, postmortems, DR, backups
- Performance and cost: P99, tail latency, caching strategy, capacity planning, LLM token spend
- Building production AI systems: RAG, LLM inference, streaming, agents, vector databases, eval pipelines
- Any request like "make this production-ready", "review this for production", "why is this slow/down?", "is this architecture right?"

## When NOT to Activate

- Pure frontend/CSS/design work â€” use UI skills instead.
- Algorithm puzzles with no production context.
- Throwaway scripts the user explicitly wants minimal (respect that; say what you'd defer).
- Definitions-only questions that any docs answer (fetch official docs instead).

## How to Load the Right Knowledge (do not read all 111 topics)

1. **Classify the task** against the categories: A backend/APIs Â· B data & distributed systems Â· C deploy/ops Â· D security Â· E migrations Â· F DR/reliability Â· G performance Â· H networking Â· I infrastructure Â· J incidents.
2. **Map to candidate topics** using `docs/topic-index.md` or filename search (`ls topics/ | grep <keyword>`).
3. **Open 2â€“4 topic docs**, not the whole library. Each is self-contained (24 sections; sections 7/8 give when/when-not).
4. **Read the matching deep reference** in `references/` for mechanism depth and real tool configs.
5. **Apply the Decision Framework** (below) before recommending anything.
6. **Pull the workflow + checklist** for the task from `workflows/` and `templates/`.

Rule: **retrieve narrow, apply deep.** A topic doc unread is a misconception waiting; the whole library is noise. Targeted reads win.

## Decision Framework â€” Think Like a Production Engineer

Before recommending ANY pattern, ask:

1. **What requirement does this satisfy?** (security, correctness, availability, latency, cost, compliance â€” name it)
2. **Is there a simpler mechanism that meets it?** (a unique constraint beats a distributed lock; a DB table beats Kafka at 10 events/min)
3. **What does it cost?** (money, latency, complexity, cognitive load, on-call minutes)
4. **How does it fail?** (blast radius, failure mode, detection, recovery, rollback)
5. **How do we verify it works?** (test, metric, canary, drill)

Classify every recommendation:

| Class | Meaning | What you do |
| --- | --- | --- |
| **CRITICAL** | Security, correctness, or availability hole | Block: fix before ship. Flag as a blocker explicitly. |
| **HIGH** | Required for safe production use | Implement unless the user explicitly defers with eyes open. |
| **MEDIUM** | Conditional on scale/workload/maturity | Recommend with the trigger condition stated ("at >N RPS / M rows / K tenants"). |
| **LOW** | Optional polish | Mention briefly at most; never push. |
| **NOT APPLICABLE** | Unneeded here | Do not raise it. Silence is a feature. |

Anti-overengineering rules:

- No Kubernetes, Kafka, Redis, or service mesh "just in case" â€” tie to a measured requirement.
- No microservices where a modular monolith works; no queues where a transaction works.
- No caching without an invalidation plan. No retries without idempotency. No locks without TTL and fencing.
- Prefer the platform you run (managed Postgres, K8s Services, cloud LB) over hand-rolled infrastructure.
- Defer complexity: ship the simple thing behind a flag, measure, then harden.

## Production Risk Review â€” Run This on Every Substantive Task

1. **Data path:** What reads/writes happen? Transaction boundaries? Migration compatibility during rollout? Backup/rollback?
2. **Concurrency path:** What happens on duplicate submit, parallel instances, cron overlap, stale reads? Atomic ops or locks?
3. **Failure path:** What breaks when the dependency is down/slow/lying? Timeout? Retry+jitter? Idempotent? Circuit breaker? Degrades to what?
4. **Resource path:** Unbounded queues, pools, retries, payloads? Limits and backpressure set?
5. **Security path:** AuthN/Z enforced server-side at every entry point? Secrets managed? Inputs validated at the boundary? SSRF/injection surfaces?
6. **Observability path:** What will page at 03:00? Metrics, logs (trace_id), health endpoints, SLOs â€” designed in, not after?
7. **Rollout path:** Canary/blue-green? Expand/contract migrations? Rehearsed rollback?

See `workflows/architecture-review.md` for the full playbook.

## Mandatory Safety Rules

- Never print, log, commit, or hardcode secrets â€” env vars/managers only; flag any you find.
- Validate all external input at the boundary; output-encode anything rendered.
- Transactions stay short; no network calls inside transactions; consistent lock order.
- Retries only on transient failures, exponential backoff **with jitter**, capped, with idempotency or exactly-once safety.
- Every outbound call has a connect AND read timeout; deadlines propagate.
- Bounded everything: queues, pools, payloads, batch sizes, retries, concurrency.

## Key Files

| Need | Path |
| --- | --- |
| Topic index (111 topics) | `../../docs/topic-index.md` |
| Coverage matrix | `../../docs/topic-index.md` (or README) |
| Deep references | `references/*.md` (15 files: architecture, backend, distributed, reliability, security, performance, observability, infrastructure, deployment, testing, ai-engineering, database-engineering, networking, incident-management, engineering-checklists) |
| Playbooks | `workflows/*.md` (new-service, production-readiness, performance-optimization, incident-response, security-review, architecture-review) |
| Templates | `templates/*.md` (ADR, design doc, incident report, readiness checklist) |
| Examples | `../../examples/fastapi/`, `../../examples/distributed-systems/`, `../../examples/ai-agent-systems/` |

## Output Discipline

When recommending, always state: **what to do â†’ why â†’ trade-offs â†’ how to verify â†’ how to roll it out and roll it back.** Never emit an unverified best practice as law; tie it to the requirement in front of you. If the honest answer is "NOT APPLICABLE", say so and stop.
