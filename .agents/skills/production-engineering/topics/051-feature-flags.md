---
topic: 51
title: Feature Flags
category: C
skill: production-engineering
status: stable
---

# 051 — Feature Flags

## 1. Topic name and metadata

- **Number:** 51 of 111
- **Title:** Feature Flags
- **Category:** C — Deployment and Production Operations
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [deployment-operations.md](../references/deployment.md)
- **Topic file:** `.agents/skills/production-engineering/topics/051-feature-flags.md`

## 2. What it is

A runtime switch (evaluated per user/context) that turns a code path on or off without redeploying; decouples *deploying* code from *releasing* behavior.

## 3. Why it exists

Deploying code and releasing behavior are different decisions.

## 4. The engineering problem it solves

Releasing features means reverting code when something breaks; long-lived branches and big-bang releases are risky and slow. Flags let you ship continuously and control exposure separately.

## 5. How it works internally

Flag service/SDK evaluates rules (percentage rollout, allowlist, segment, env) at runtime; decisions stream to SDKs with low-latency evaluation (in-memory + poller or SSE/stream); flag state is config, not code. Types: release flags (deploy dark, enable gradually), ops flags (kill switch), experiment flags (A/B), permission flags (rollout by plan). Flag debt: each flag needs an owner, a removal date, and cleanup tickets — unmanaged flags rot into unmaintainable branching.

## 6. Architecture and design principles

App → flag SDK → flag service (Unleash/LaunchDarkly/config-in-DB) with fallback to cached defaults if the flag service is down (never fail the request path).

**Design principles for this category:** Everything declarative and reversible; the pipeline is the only writer; health must be observable from outside the process.

## 7. When to use it

Continuous delivery, risky features, gradual migration, experimentation, kill switches.

## 8. When NOT to use it

Tiny one-off deploy (env var suffices).

**Alternatives:** env config for static toggles, blue-green/canary for infrastructure-level switches.

## 9. Implementation strategies

```python
import os, unleashclient  # or simple DB-backed table
def is_enabled(name: str, user_id: str) -> bool:
    bucket = int(hashlib.sha256(f"{name}:{user_id}".encode()).hexdigest(), 16) % 100
    row = cache.get(f"flag:{name}") or fetch_flag(name)   # default safe if missing
    if row["rollout_pct"] >= 100: return True
    if user_id in row["allowlist"]: return True
    return bucket < row["rollout_pct"]
```

## 10. Production-grade implementation

**Scenario:** Checkout v2 shipped dark; enabled for 1% for 2 days (no anomaly), 25% for a week, 100%; at 80% a payment-error spike appeared; ops flag flipped to 0% in 20 seconds — zero deploy, zero rollback, incident avoided; code stayed deployed until fixed.

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

Dependency `flags: FlagClient = Depends(get_flags)`; routes check `flags.enabled("new-checkout", user_id=user.id)`; flag changes stream in via polling every 10s; fall back to `False` (old path) on error.

## 13. Distributed-system considerations

Rollout safety across a fleet: probes, budgets, and automatic rollback are the distributed-systems controls for deployments — a bad pod must be ejected, not tolerated.

## 14. AI/ML/LLM application examples where relevant

Model and prompt rollouts behind flags (1%→25%→100%); instant kill switch per model/prompt version — no deploy needed to stop bleeding.

## 15. Security considerations

Flags flip prod behavior — audit who flips what; treat flag changes as deploys.

## 16. Performance considerations

Rollout mechanisms are free at steady state; the wins come from staying ahead of capacity — probes and autoscalers prevent disasters, not milliseconds.

## 17. Common mistakes

Flags in client-side code for security decisions; permanent flags; branching every function on 6 flags; flags without metrics (no way to tell if rollout is healthy); using flags to paper over missing rollback capability; no flag hygiene policy.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `flag_evaluations_total{flag}`, rollout cohort error rate

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest with flag override fixture (evaluate both paths); bucket distribution test (no skew); kill-switch drill (flip off mid-load, assert recovery); default-off test with flag service absent; E2E with flag on/off matrix.

## 21. Deployment considerations

Automate through CI/CD: GitHub Actions (or equivalent) → image by digest → canary/rolling → smoke → auto-rollback on burn-rate alert. No manual steps in the critical path.

## 22. Production-readiness checklist

- [ ] Sticky bucketing by user/tenant
- [ ] Server-side only for authz decisions
- [ ] Every flag has owner + expiry
- [ ] Flag audit log
- [ ] Kill switches for risky dependencies
- [ ] Default-off on missing config
- [ ] Flag-removal week each quarter
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Flag service down → all evaluations must have cached defaults (degraded, not dead); flag leak in error messages (incident reports say "flag new-checkout broke X" — fine internally, never to users); permission flags as security boundary used without server-side re-check; thousands of permanent flags making every code path branch — cleanup SLA essential; percentage rollout flapping (user sees feature then loses it) without sticky bucketing by user_id; flag + migration ordering mistakes (code expects schema rev N; flag on but migration not applied).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://martinfowler.com/articles/feature-toggles.html

**Related topics in this library:** `#52 Blue-Green Deployment`, `#53 Canary Releases`, `#51 Feature Flags` pairs with `#55 Rollbacks`, `#63 SLOs` (rollout health), `#82 Schema Versioning` (expand/contract before flag flip).
