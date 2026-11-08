---
topic: 56
title: Health Checks
category: C
skill: production-engineering
status: stable
---

# 056 — Health Checks

## 1. Topic name and metadata

- **Number:** 56 of 111
- **Title:** Health Checks
- **Category:** C — Deployment and Production Operations
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [deployment-operations.md](../references/deployment.md)
- **Topic file:** `.agents/skills/production-engineering/topics/056-health-checks.md`

## 2. What it is

An endpoint (`/healthz`) reporting whether the process can serve requests; consumed by load balancers, orchestrators, and monitoring to route traffic and restart unhealthy instances.

## 3. Why it exists

Traffic must reach only instances that can serve right now.

## 4. The engineering problem it solves

Without an honest health signal, traffic goes to dead or degraded instances; without a separable liveness/readiness split, orchestrators either restart healthy-but-busy pods or keep broken ones in rotation.

## 5. How it works internally

Cheap check by design: process is up, event loop responsive, optionally critical dependencies (DB, Redis) within a fast deadline. Liveness (is the process broken → restart it) vs readiness (can it serve → route or not). Deep checks (all dependencies) in liveness cause restart storms when the DB blips — dependencies belong in readiness or a separate status page. Health responses include version and uptime for debugging.

## 6. Architecture and design principles

Service exposes `/healthz` (+ `/readyz`); LB/K8s probe it; monitoring scrapes it; responses must be cheap (< 50ms, no heavy queries).

**Design principles for this category:** Everything declarative and reversible; the pipeline is the only writer; health must be observable from outside the process.

## 7. When to use it

Always — mandatory for any deployable service.

## 8. When NOT to use it

N/a.

**Alternatives:** n/a (it's the contract with the platform).

## 9. Implementation strategies

```python
@app.get("/healthz")
def healthz():
    return {"status": "ok", "version": __version__, "uptime": int(time.monotonic() - START)}

@app.get("/readyz")
def readyz():
    try:
        engine.connect().execute(text("SELECT 1")).close()
    except Exception:
        raise HTTPException(503, "database not reachable")
    return {"status": "ready"}
```

K8s: `startupProbe` for slow boot (model loading), then liveness/readiness.

## 10. Production-grade implementation

**Scenario:** K8s API pods: startupProbe 60s allowance for model load; readiness hits DB+Redis with 1s timeout; liveness = process-only; an DB failover removed all pods from rotation cleanly (503 at gateway, zero phantom traffic to dead-backends); recovered when DB returned.

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

Inference readiness = model loaded + GPU healthy + vector DB reachable, not just /healthz 200.

## 15. Security considerations

Health output is recon data — status `ok` only, no versions, no deps.

## 16. Performance considerations

Rollout mechanisms are free at steady state; the wins come from staying ahead of capacity — probes and autoscalers prevent disasters, not milliseconds.

## 17. Common mistakes

Deep checks in liveness; readiness always OK; expensive health queries; health info leak; probe intervals too tight (CPU noise).

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `health_probe_status`, `health_check_failures_total`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Kill DB → readyz 503 → pod out of rotation → traffic zero 5xx (from LB); pod SIGSTOP → liveness fails → restart; startupProbe test with artificial boot delay; verify no DB queries in liveness path.

## 21. Deployment considerations

Automate through CI/CD: GitHub Actions (or equivalent) → image by digest → canary/rolling → smoke → auto-rollback on burn-rate alert. No manual steps in the critical path.

## 22. Production-readiness checklist

- [ ] Liveness = process-only
- [ ] Readiness = real dependencies with short deadline
- [ ] StartupProbe for slow init
- [ ] `/healthz` excluded from auth but minimal
- [ ] Cheap payload
- [ ] Include build version
- [ ] Alert on readyz flap
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Liveness checking DB → DB outage triggers every pod restart simultaneously → total outage minutes after DB recovers (connection storm); readiness always-200 → traffic to broken pods; healthcheck too expensive (full query) → probe itself overloads DB; no startup probe → slow-boot pods killed in restart loop; healthcheck exposed publicly leaking version/internal state; health endpoint = only route not behind LB (bypasses auth but leaks info — keep it minimal).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/

**Related topics in this library:** `#57 Liveness & Readiness Probes`, `#3 Load Balancing`, `#45 Autoscaling`, `#55 Rollbacks`, `#58 Monitoring`.
