---
topic: 109
title: Production Incidents
category: J
skill: production-engineering
status: stable
---

# 109 — Production Incidents

## 1. Topic name and metadata

- **Number:** 109 of 111
- **Title:** Production Incidents
- **Category:** J — Production Incident Management
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [production-operations.md](../references/incident-management.md)
- **Topic file:** `.agents/skills/production-engineering/topics/109-production-incidents.md`

## 2. What it is

An unplanned degradation or outage of a production service requiring coordinated response; managed by severity, with roles (incident commander, comms, scribe) and a clock.

## 3. Why it exists

Incidents are routine; response must be too.

## 4. The engineering problem it solves

Unstructured response multiplies downtime, duplicates work, loses data (logs rotated), and burns trust; panic destroys information needed later.

## 5. How it works internally

Lifecycle: detection (alerts/users) → assess & declare (severity P1-P4) → assemble roles → mitigate first (roll back, flag off, failover — restore service, not root cause) → communicate (status page, stakeholders every 30min) → resolve → handoff to postmortem. Severity definitions: P1 = full outage/data risk, all hands, exec comms; P2 = major degradation, page team; P3 = minor, next business day; P4 = cosmetic backlog. Incident commander coordinates — single authority, not a committee. Scribe records timeline in real time (chat thread); every action timestamped; dashboards shared; mitigation chosen for speed, not elegance ("rollback now, fix later").

## 6. Architecture and design principles

PagerDuty/Opsgenie paging → dedicated incident channel (Slack/Teams) → status page → Zoom bridge for P1; tooling: incident.io, statuspage.

**Design principles for this category:** Mitigate first, understand later; blameless analysis; convert pain into permanent fixes.

## 7. When to use it

Always — even trivial regressions deserve a severity call.

## 8. When NOT to use it

Local dev.

**Alternatives:** n/a; severity-proportionate response scales to P3/P4 (fix async).

## 9. Implementation strategies

```
Incident response checklist:
□ Acknowledge page < 5min     □ Open incident channel
□ Assign IC + scribe          □ State severity (P1/P2)
□ Mitigate (rollback/flag)    □ Status page update every 30min
□ Confirm recovery signals    □ Hand off to on-call lead
```

## 10. Production-grade implementation

**Scenario:** 02:14 P1: checkout 5xx 30%; IC declared, flagged `checkout_v2` OFF in 90 seconds → errors to 0.1%; comms tool updated; customers saw 6 minutes of degraded checkout, no data loss; 08:00 all-hands RCA started; suspected N+1 deploy; permanent fix + canary gate added next day.

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

AI incidents: cost runaway, provider outage, prompt catastrophe, data leak — distinct runbooks per class.

## 15. Security considerations

Incident rooms are secrets hot zones — pre-warmed templates that strip env dumps.

## 16. Performance considerations

Fast response saves the org, not the machine — tooling that shortens MTTA/MTTR pays for itself in one incident.

## 17. Common mistakes

Root-causing before restoring; two people "in charge"; silence externally; partial mitigations reported as fixed; incidents without declarations (below threshold but corrosive silent failures); P1 for everything (dilutes response).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `mtta_seconds`, `mttr_minutes`, open-incident count, severity histogram

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Game days (simulated P1s); tabletop exercises; page-routing test; status page drill; MTTA/MTTR tracked per quarter.

## 21. Deployment considerations

Incident tooling changes ship like prod code: runbook updates are PRs; test paging paths after every change; postmortems close only when actions verified.

## 22. Production-readiness checklist

- [ ] Mitigate first, understand later
- [ ] Single IC
- [ ] Scribe timelines everything
- [ ] Status page + internal comms every 30min
- [ ] Severity matrix predefined
- [ ] Revert-by-default for deploy-linked incidents
- [ ] Never debug without a rollback ready
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** No IC (everyone debugging in parallel, nothing coordinated); mitigation by root-cause analysis instead of revert ("let me understand the bug first" while site is down); status page silence → support ticket storm; logs lost during incident (no archival); premature all-clear ("p99 back to normal" — but error budget is gone and root cause unknown); heroics instead of escalation; skipping the postmortem because "it's resolved".
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://sre.google/sre-book/managing-incidents/
- https://incident.io/blog

**Related topics in this library:** `#110 On-Call`, `#111 Postmortems`, `#53 Canary Releases`, `#55 Rollbacks`, `#108 Dependency Hell` (dependency incidents), `#65 Error Budgets`.
