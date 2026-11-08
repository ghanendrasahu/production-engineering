---
topic: 55
title: Rollbacks
category: C
skill: production-engineering
status: stable
---

# 055 — Rollbacks

## 1. Topic name and metadata

- **Number:** 55 of 111
- **Title:** Rollbacks
- **Category:** C — Deployment and Production Operations
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [deployment-operations.md](../references/deployment.md)
- **Topic file:** `.agents/skills/production-engineering/topics/055-rollbacks.md`

## 2. What it is

Reverting a deploy to the last known-good state promptly — the most important and most neglected production capability; a rollback you haven't rehearsed doesn't exist.

## 3. Why it exists

The cheapest reliability feature is a rehearsed revert.

## 4. The engineering problem it solves

When production is on fire, the fastest fix is usually a revert; if rollback is manual archaeology, outages stretch for hours.

## 5. How it works internally

Artifact immutability (same image tag, same build — never rebuild for rollback) + fast traffic switch (`kubectl rollout undo`, ReplicaSet scale swap, LB target restore) + data compatibility (expand/contract means old code on new schema works). Database rollbacks: forward-fix usually beats down-migration; destructive contract migrations must ship days after code stops reading the column. Feature flags give a faster "rollback" of behavior without deploying anything.

## 6. Architecture and design principles

Deployment system + immutable artifact registry + database migration ledger + flag service; runbooks reference exact commands.

**Design principles for this category:** Everything declarative and reversible; the pipeline is the only writer; health must be observable from outside the process.

## 7. When to use it

Always designed-in.

## 8. When NOT to use it

It doesn't fit (data-destructive release) — then expand/contract to make it fit.

**Alternatives:** flags (fastest), canary auto-abort, blue-green flip, roll-forward fix.

## 9. Implementation strategies

```bash
git tag v1.4.3 && git push --tags                    # immutable artifacts
kubectl rollout undo deploy/api --to-revision=12
kubectl rollout status deploy/api --timeout=180s
python -c "import urllib.request; print(urllib.request.urlopen('https://app/healthz').status)"
```

Flags: set rollout flag to 0% → done in seconds, no deploy.

## 10. Production-grade implementation

**Scenario:** v2.6.1 checkout deploy error rate 4%; 5 minutes post-deploy canary auto-rollback already flipped traffic to v2.6.0; team confirmed p99 back to 150ms; RCA found bad cache-key change; fix deployed next morning behind canary.

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

Rollout safety across a fleet: probes, budgets, and automatic rollback are the distributed-systems controls for deployments — a bad pod must be ejected, not tolerated.

## 14. AI/ML/LLM application examples where relevant

Broken prompt found in prod? Flip the flag — that IS the rollback; then fix and re-canary.

## 15. Security considerations

Rollback restores vulnerabilities too — rotate after exposure, revert fast.

## 16. Performance considerations

Rollout mechanisms are free at steady state; the wins come from staying ahead of capacity — probes and autoscalers prevent disasters, not milliseconds.

## 17. Common mistakes

"Roll forward only" as ideology (sometimes right! but only with cheap deploys and great tests); rebuilding the artifact; down-migrations destructive in same release; no retention of old images; rollback runbooks owned by interns; confirming rollback by deploy logs alone.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `rollback_duration_seconds`, `rollback_success_rate`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Monthly rollback drill: deploy vN, then `rollout undo`, time it, verify health; restore-from-backup drill as last resort; flag kill-switch drill; mid-incident simulation.

## 21. Deployment considerations

Automate through CI/CD: GitHub Actions (or equivalent) → image by digest → canary/rolling → smoke → auto-rollback on burn-rate alert. No manual steps in the critical path.

## 22. Production-readiness checklist

- [ ] Immutable artifacts + registry retention ≥ 90 days
- [ ] One-command rollback documented
- [ ] Rehearse monthly
- [ ] Canary/flags for behavior-level undo
- [ ] Verify post-rollback (health + business KPI), not just deploy success
- [ ] Keep previous ReplicaSet warm
- [ ] Never delete the last two image tags
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Rebuild-on-rollback (new bits, new bugs — always redeploy the exact prior artifact); stateful rollback forgetting migrations (old code vs new schema); config drift between environments making "revert" lossy; partial rollback (API rolled back, worker not); rollback untested → fails mid-incident (permissions, image GC'd from registry); DNS-based rollback at default TTL; rollback without monitoring confirmation ("reverted" but still degraded — verify!).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#rolling-back-a-deployment

**Related topics in this library:** `#53 Canary Releases`, `#51 Feature Flags`, `#52 Blue-Green Deployment`, `#81 Database Migrations`, `#63 SLOs`.
