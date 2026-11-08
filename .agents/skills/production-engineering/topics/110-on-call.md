---
topic: 110
title: On-Call
category: J
skill: production-engineering
status: stable
---

# 110 — On-Call

## 1. Topic name and metadata

- **Number:** 110 of 111
- **Title:** On-Call
- **Category:** J — Production Incident Management
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [production-operations.md](../references/incident-management.md)
- **Topic file:** `.agents/skills/production-engineering/topics/110-on-call.md`

## 2. What it is

A rotation of engineers responsible and empowered to respond to production alerts, escalate, and deploy mitigations — with compensation, tooling, and a humane load limit.

## 3. Why it exists

Alerts must wake humans sustainably or nobody answers them.

## 4. The engineering problem it solves

Without on-call, alerts page nobody and outages run until business hours; without humane on-call, you burn out your best engineers.

## 5. How it works internally

Rotation: weekly primary + secondary (escalation after 15min no-ack), handoff checklist (open incidents, silences in place, known fragile deploys, escalation contacts), compensation (pay or time off), actionable-alert policy (page only actionable P1/P2 — no CPU pages at 3am), follow-the-sun for global teams, load budgeting (≤ 1-2 pages per shift average — above that, fix the system, not the human). Tooling: PagerDuty/Opsgenie escalation policies, runbooks per alert, ChatOps for context gathering (deploys, recent PRs, dashboards), one-click rollback/flag access from the phone.

## 6. Architecture and design principles

PagerDuty/Opsgenie escalation policy -> primary/secondary rota -> runbook + ChatOps context (deploys, dashboards) -> optional one-click rollback/flag path; weekly handoff checklist governs continuity.

**Design principles for this category:** Mitigate first, understand later; blameless analysis; convert pain into permanent fixes.

## 7. When to use it

Any production system with users — mandatory.

## 8. When NOT to use it

Pre-launch/internal throwaway.

**Alternatives:** n/a — response capability is not optional; scope scales with system criticality.

## 9. Implementation strategies

```
Escalation policy: primary (5min) → secondary (10min) → manager (15min)
Handoff: open incidents + silences expiry + pending deploys + known risks
Alert → runbook URL → steps → "if X, flip flag Y" one-click path
```

## 10. Production-grade implementation

**Scenario:** Team of 8: weekly rota primary+secondary; 90-day metrics: 11 pages, 8 actionable, MTTA 4min, MTTR 18min; 3 noisy alerts identified and deleted; Q3 compensation: 8h time-off each on-call week; retention excellent; knowledge spread: no single person knows "the database thing".

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (inline in section 9)

This concept has no standalone Python surface — its artifacts are configuration,
templates, or pipeline steps. All runnable material for it lives inline in **section 9 (Implementation strategies)** and **section 12 (FastAPI integration)** where applicable. Do not force a toy example here.

## 12. FastAPI integration where relevant

Not applicable — this concept is infrastructure/protocol level; there is no FastAPI-specific surface. Apply it underneath FastAPI through configuration, middleware, or dependencies (section 9). Do not force a fake integration.

## 13. Distributed-system considerations

Incidents are distributed systems communicating under stress — the scribe + roles protocol is the consensus algorithm for humans.

## 14. AI/ML/LLM application examples where relevant

Page on cost burn rate and provider 5xx storm — not on single-request failures.

## 15. Security considerations

On-call = prod access — least privilege, break-glass audit, no shared accounts.

## 16. Performance considerations

Fast response saves the org, not the machine — tooling that shortens MTTA/MTTR pays for itself in one incident.

## 17. Common mistakes

24/7 solo on-call; pager as the monitoring solution; "you were on-call, so it's yours" culture; no comp; runbooks outdated; alerts with no owner; hero dependency; punitive response to incident mistakes (kills reporting).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `pages_per_shift`, escalation count, ack time, off-duty interruption count

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Monthly alert-to-runbook walkthrough by a non-owning engineer; escalation drill; handoff audit; rotation load report (pages/shift); burnout survey per cycle.

## 21. Deployment considerations

Incident tooling changes ship like prod code: runbook updates are PRs; test paging paths after every change; postmortems close only when actions verified.

## 22. Production-readiness checklist

- [ ] Page only actionable
- [ ] ≤ 1-2 pages/shift target
- [ ] Comp time + cash
- [ ] Escalation policy
- [ ] Runbooks mandatory per alert
- [ ] Weekly handoff checklist
- [ ] Post-incident review each bad page (delete or fix it)
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Always-on engineer burnout ("just one more page"); alert floods nobody reads; escalation to a manager who has no context; no compensation → attrition; on-call without authority to deploy mitigations ("I can't touch prod"); handoff omissions (silence expires mid-outage); hero mode: senior carries everything → SPOF knowledge; 24/7 single-timezone coverage for global product.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://sre.google/sre-book/being-on-call/
- https://pagerduty.com/docs/

**Related topics in this library:** `#109 Production Incidents`, `#62 Alerts`, `#111 Postmortems`, `#63 SLOs`, `#65 Error Budgets`.
