---
topic: 54
title: Rolling Deployments
category: C
skill: production-engineering
status: stable
---

# 054 — Rolling Deployments

## 1. Topic name and metadata

- **Number:** 54 of 111
- **Title:** Rolling Deployments
- **Category:** C — Deployment and Production Operations
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [deployment-operations.md](../references/deployment.md)
- **Topic file:** `.agents/skills/production-engineering/topics/054-rolling-deployments.md`

## 2. What it is

Gradually replace instances of the old version with the new, maintaining service availability throughout (maxSurge/maxUnavailable budgets).

## 3. Why it exists

Replace instances gradually; never drop below serving capacity.

## 4. The engineering problem it solves

The default, cheap zero-downtime rollout — but without limits, updates can exceed capacity headroom and cause outage during the roll itself.

## 5. How it works internally

K8s Deployment strategy ` RollingUpdate{maxSurge: 25%, maxUnavailable: 0}` (or 1): creates new pod, waits Ready (readiness probe), terminates old (preStop hook → SIGTERM → grace period), repeats. Readiness gates "ready to serve"; termination drains connections. Database compatibility required during the roll (both versions live). Rollouts paused on probe failure; `kubectl rollout undo` reverts to previous ReplicaSet.

## 6. Architecture and design principles

Deployment controller + ReplicaSets; LB health checks deregister unready/terminating pods.

**Design principles for this category:** Everything declarative and reversible; the pipeline is the only writer; health must be observable from outside the process.

## 7. When to use it

Default for stateless services with capacity headroom.

## 8. When NOT to use it

Stateful/singleton workloads (use leader election + graceful handoff); breaking schema changes (expand/contract first); when you need instant full-switch semantics.

**Alternatives:** canary, blue-green, recreate (some dev workloads).

## 9. Implementation strategies

```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate: { maxSurge: 1, maxUnavailable: 0 }
  template:
    spec:
      terminationGracePeriodSeconds: 45
      containers:
      - name: app
        lifecycle: { preStop: { exec: { command: ["sh","-c","sleep 10"] } } }   # stop endpoints, drain LB
```

## 10. Production-grade implementation

**Scenario:** 8-replica API: maxSurge 2, maxUnavailable 0; deploy < 3 minutes; readiness = /readyz checks DB+Redis; preStop sleep 15s before SIGTERM; zero 5xx during roll; one bad pod failed readiness → roll paused, 4 pods still old but healthy; roll back with `rollout undo`.

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

GPU pods roll slowly (image pull + model load) — use startupProbe and surge=0 for inference Deployments.

## 15. Security considerations

During rolls, two versions coexist — both must validate inputs and tokens.

## 16. Performance considerations

Rollout mechanisms are free at steady state; the wins come from staying ahead of capacity — probes and autoscalers prevent disasters, not milliseconds.

## 17. Common mistakes

100% surge then kill-all (that's not rolling); readiness = liveness; no grace period; rolling with pending migration ordering; deploy without watching rollout; image tag `:latest`.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `rollout_duration_seconds`, `unavailable_replicas_current`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Rollout dry-run (`--dry-run=server`); staging roll under load asserting zero errors; kill-a-pod-mid-roll drill; migration-compatibility smoke; rollback drill timing.

## 21. Deployment considerations

Automate through CI/CD: GitHub Actions (or equivalent) → image by digest → canary/rolling → smoke → auto-rollback on burn-rate alert. No manual steps in the critical path.

## 22. Production-readiness checklist

- [ ] MaxUnavailable 0 when possible
- [ ] Readiness probes real (dependencies checked)
- [ ] PreStop drain sleep
- [ ] TerminationGrace ≥ longest request
- [ ] Resource requests/limits set so surge pods fit the cluster
- [ ] Monitor rollout duration and post-roll error rate
- [ ] `kubectl rollout undo` runbook
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** maxUnavailable too high → fleet capacity drops below demand → 503s; readiness too shallow (TCP check) → traffic hits not-yet-ready pods → errors; preStop missing → LB still routes to dying pods (connection refused); rollout of breaking migration mid-roll (old code on new schema) → exceptions; termination grace < in-flight request time → dropped requests; waiting for all pods to be old+new simultaneously impossible for stateful singletons.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://kubernetes.io/docs/tutorials/kubernetes-basics/update/update-app/

**Related topics in this library:** `#57 Liveness & Readiness Probes`, `#55 Rollbacks`, `#52 Blue-Green Deployment`, `#53 Canary Releases`, `#81 Database Migrations`, `#54 Rolling Deployments`.
