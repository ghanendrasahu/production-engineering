---
topic: 57
title: Liveness & Readiness Probes
category: C
skill: production-engineering
status: stable
---

# 057 — Liveness & Readiness Probes

## 1. Topic name and metadata

- **Number:** 57 of 111
- **Title:** Liveness & Readiness Probes
- **Category:** C — Deployment and Production Operations
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [deployment-operations.md](../references/deployment.md)
- **Topic file:** `.agents/skills/production-engineering/topics/057-liveness-and-readiness-probes.md`

## 2. What it is

Kubernetes (or LB) mechanisms distinguishing **liveness** — is the process dead/hung (restart it) — from **readiness** — can it serve traffic right now (include/exclude from endpoints).

## 3. Why it exists

Is it dead?' and 'can it serve?' demand different answers.

## 4. The engineering problem it solves

Without probes, orchestrators send traffic to unready pods and keep zombie pods in rotation; with misdesigned probes, they restart healthy-but-busy pods and cascade outages.

## 5. How it works internally

kubelet probes: `httpGet`, `tcpSocket`, `exec` with `periodSeconds`, `timeoutSeconds`, `failureThreshold`, `initialDelaySeconds` (legacy) or `startupProbe` (preferred for slow boots — liveness suppressed until startup succeeds). Readiness failure → pod removed from EndpointSlice (no restart). Liveness failure → container restarted (with backoff via restartPolicy). Combination yields: startup → readiness gates traffic → liveness restarts hung apps.

## 6. Architecture and design principles

kubelet → probe endpoint; endpoints controller updates Service EndpointSlices; LB/ingress chase those.

**Design principles for this category:** Everything declarative and reversible; the pipeline is the only writer; health must be observable from outside the process.

## 7. When to use it

Always in K8s (and analogs in LB-based deploys).

## 8. When NOT to use it

Trivial one-shot containers (jobs).

**Alternatives:** `exec` probes, gRPC health checking protocol, LB target group health checks.

## 9. Implementation strategies

```yaml
startupProbe:
  httpGet: { path: /healthz, port: 8000 }
  periodSeconds: 5; failureThreshold: 30      # up to 150s to boot (LLM models)
livenessProbe:
  httpGet: { path: /healthz, port: 8000 }
  periodSeconds: 10; timeoutSeconds: 2; failureThreshold: 3   # restart after 30s hung
readinessProbe:
  httpGet: { path: /readyz, port: 8000 }
  periodSeconds: 5; timeoutSeconds: 1; failureThreshold: 2    # 10s out of rotation
```

## 10. Production-grade implementation

**Scenario:** Embedding API (4GB model load): startupProbe failureThreshold 40 (200s budget); before this, liveness killed pods every 60s mid-load → crash loop; after, clean rollout in 4 minutes.

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

Startup probe must tolerate 60-300s model loads; liveness must NOT restart during long generations.

## 15. Security considerations

Readiness must not echo dependency names or error details.

## 16. Performance considerations

Rollout mechanisms are free at steady state; the wins come from staying ahead of capacity — probes and autoscalers prevent disasters, not milliseconds.

## 17. Common mistakes

Liveness = readiness = `/healthz` with DB check; no startupProbe; period 1s; exec probes with heavy scripts; probes behind auth.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `readiness_transitions_total`, `liveness_restarts_total`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

SIGSTOP a pod → liveness restarts it; DB down → readyz out-of-rotation (not restart); artificial slow boot → startupProbe protects; rollout drill verifying traffic never hits unready pods (load test during deploy).

## 21. Deployment considerations

Automate through CI/CD: GitHub Actions (or equivalent) → image by digest → canary/rolling → smoke → auto-rollback on burn-rate alert. No manual steps in the critical path.

## 22. Production-readiness checklist

- [ ] StartupProbe absorbs slow boot
- [ ] Liveness = cheap process check only (never dependencies)
- [ ] Readiness = real readiness with 1s deadline
- [ ] Thresholds ≥ 3 failures
- [ ] Probes cheap enough to run every 5-10s
- [ ] Probe endpoints logged at debug level
- [ ] Align LB idle timeout with readiness.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Same endpoint for both probes with deep checks → liveness death spiral during DB blip; initialDelay too short for JVM/model load; timeout > period (overlap); failureThreshold 1 (one slow probe restarts healthy pod); exec probes spawning shells too heavy; probe logs filling disk (period 1s logging).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/

**Related topics in this library:** `#56 Health Checks`, `#54 Rolling Deployments`, `#45 Autoscaling`, `#85 Failover`, `#11 Timeouts`.
