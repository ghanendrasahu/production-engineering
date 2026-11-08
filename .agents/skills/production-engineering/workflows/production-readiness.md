# Workflow — Production Readiness Review

Run this before declaring any service/feature production-ready. Output a written verdict: SHIP / SHIP WITH FIXES / DO NOT SHIP.

## Phase 1 — Discovery

Read the service: entry points, dependencies, data stores, deploy config, tests, alerts. Walk the request path from `references/backend-engineering.md` and the failure path (dependency down/slow/lying).

## Phase 2 — The Audit (score each 0-2; 0 = missing)

| Area | Questions that must answer yes |
| --- | --- |
| **Correctness** | Transactions correct? Locks ordered? N+1 gone? Constraints at the DB? |
| **Timeouts & retries** | Every outbound call has connect+read timeout; retries capped, jittered, idempotent-only? |
| **Resources** | All queues/pools/payloads bounded? Backpressure at saturation? |
| **Data** | Migrations expand/contract? Indexes verified with EXPLAIN at prod-like size? Backup+restore tested? |
| **Health & rollout** | `/healthz`, `/readyz` correct? Canary/blue-green? Rollback rehearsed <5min? |
| **Observability** | RED metrics per route; trace_id in logs; P99 dashboards; alerts with runbooks; nobody pages on noise? |
| **Security** | Server-side authz per route? Secrets from manager? Input validation at boundary? OWASP basics (injection/XSS/SSRF) reviewed? |
| **Cost & capacity** | Saturation point known? Headroom ≥30%? LLM/token spend tagged and budgeted? |
| **Ops** | On-call owns it; SLOs agreed; postmortem path known; runbooks current? |

## Phase 3 — Findings

For each: `severity (CRITICAL/HIGH/MEDIUM/LOW) → concept number → concrete fix → owner → due`. Use `templates/production-audit.md` for a structured write-up (it mirrors this).

## Phase 4 — Verdict Rules

- Any CRITICAL open → DO NOT SHIP.
- HIGH open without compensating control and accepted-by-requester sign-off → DO NOT SHIP.
- Otherwise SHIP WITH FIXES (listed, dated) or SHIP.

## Phase 5 — Sign-off & Follow-Through

Written summary posted to the team; fixes tracked; a 30-day follow-up verifies the riskiest fixes landed (verify with the metrics/rollback drill, not a checkbox).
