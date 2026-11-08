---
topic: 111
title: Postmortems
category: J
skill: production-engineering
status: stable
---

# 111 — Postmortems

## 1. Topic name and metadata

- **Number:** 111 of 111
- **Title:** Postmortems
- **Category:** J — Production Incident Management
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [production-operations.md](../references/incident-management.md)
- **Topic file:** `.agents/skills/production-engineering/topics/111-postmortems.md`

## 2. What it is

A blameless, written analysis after an incident — timeline, root cause(s) (5 Whys / fishbone), contributing factors, impact quantification, and owned action items — distributed so the org learns instead of repeating.

## 3. Why it exists

Organizations that don't learn repeat failures forever.

## 4. The engineering problem it solves

Without postmortems, every incident is a fresh surprise; errors repeat; the same failure class hits different teams every quarter; nothing improves.

## 5. How it works internally

Blameless means the system failed, not the person — the goal is every future engineer succeeding. Structure: Summary (2 sentences) → Impact (users affected, minutes, $, SLO/budget consumed) → Timeline (timestamped from scribe) → Root cause + contributing factors (5 Whys) → What went well/poorly → Action items with owners and deadlines (SMART, tracked to closure — no "we'll add tests" without dates) → Lessons for other teams. Review in a blameless meeting; publish internally (many companies publish externally too). Track themes across incidents to find systemic gaps (missing tests, weak review, unclear ownership).

## 6. Architecture and design principles

Scribe artifacts (channel timeline) -> incident report -> blameless review -> action items (owners/dates) -> shared postmortem index feeds SLO review, runbook updates and error-budget policy.

**Design principles for this category:** Mitigate first, understand later; blameless analysis; convert pain into permanent fixes.

## 7. When to use it

Every P1/P2 incident — mandatory; near-misses recommended.

## 8. When NOT to use it

N/a.

**Alternatives:** incident review meetings (cheaper, weaker) — acceptable for P3/P4 only.

<!--END-->

## 9. Implementation strategies

```
Template (see templates/postmortem.md):
Summary | Impact (users, $, duration) | Timeline table
Root cause + contributing factors | What worked / didn't
Action items: owner + due date + tracking link
Follow-up review: 4 weeks later
```

## 10. Production-grade implementation

**Scenario:** After the 2026 checkout outage: root cause = untested serialization path; contributing = no canary for checkout, alerting blindspot; actions: k6 regression gate (owner, done +1wk), checkout canary (done), provider status page subscription (done); published in engineering wiki; similar pattern caught in two other services the next month — zero incidents since.

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

AI postmortems must include eval scores and cost deltas — quality incidents are incidents.

## 15. Security considerations

Postmortems publish lessons, not secrets; names removed, controls added.

## 16. Performance considerations

Fast response saves the org, not the machine — tooling that shortens MTTA/MTTR pays for itself in one incident.

## 17. Common mistakes

Blame; postmortem as ceremony with no tracked actions; restricted visibility (lessons locked in one team); action-item infinity (20 vague items, zero closed); skipping small incidents; defensive writing ("it wasn't our fault"); no verification the action items exist at follow-up.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** action items closed ratio, repeat-incident rate by theme

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

n/a — verification = action-item closure at follow-up review; cluster reviews theme effectiveness.

## 21. Deployment considerations

Incident tooling changes ship like prod code: runbook updates are PRs; test paging paths after every change; postmortems close only when actions verified.

## 22. Production-readiness checklist

- [ ] Blameless language ("the deploy allowed a regression", never "X broke it")
- [ ] Written within 48h while memory fresh
- [ ] Impact quantified
- [ ] 3-7 action items with owners + dates
- [ ] Follow-up review at 30 days
- [ ] Publish and socialize
- [ ] Track theme clusters quarterly
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Blame creep (directly or by implication — "why did YOU merge this?") → next incident hidden; action items without owners/dates → nothing changes; postmortem skipped for "small" P2s (they teach most); timeline reconstructed from memory (inaccurate); no follow-up review (actions rot); postmortem written by the most-junior person; public status inconsistent with internal narrative.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://sre.google/sre-book/postmortem-culture/
- https://sre.google/workbook/postmortem-culture/

**Related topics in this library:** `#109 Production Incidents`, `#110 On-Call`, `#62 Alerts`, `#63 SLOs`, `#66 Observability`, `#87 Chaos Engineering` (drills feed postmortems).
