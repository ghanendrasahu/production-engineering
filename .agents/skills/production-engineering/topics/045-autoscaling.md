---
topic: 45
title: Autoscaling
category: B
skill: production-engineering
status: stable
---

# 045 — Autoscaling

## 1. Topic name and metadata

- **Number:** 45 of 111
- **Title:** Autoscaling
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [scaling-caching.md](../references/performance.md)
- **Topic file:** `.agents/skills/production-engineering/topics/045-autoscaling.md`

## 2. What it is

Autoscaling automatically adds or removes capacity in response to live metrics via target-tracking, step, or scheduled policies, replacing static capacity guesses with a feedback loop.

## 3. Why it exists

Demand is spiky; capacity must follow it automatically.

## 4. The engineering problem it solves

Provisioning for peak wastes budget at 3 AM; provisioning for average collapses in a flash crowd — idle spend or 5xx errors.

## 5. How it works internally

A controller samples CPU, rps, or queue depth and computes `desired = ceil(current × observed / target)` clamped to min/max. The HPA applies 0s scale-out and 300s scale-in stabilization windows plus policies like +100% replicas/15s out and −2 pods/60s in to prevent oscillation; AWS target-tracking alarms fire only after repeated breaching evaluations with a 300s cooldown. Scale-in is cordon → drain → SIGTERM; scale-out must finish scheduling, image pull, and readiness before the LB routes traffic — that pipeline is the lag.

## 6. Architecture and design principles

Above the Deployment/node group: reads Prometheus or CloudWatch, acts through the kube-scheduler or ASG API, and registers targets with the LoadBalancer.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Traffic is variable, the service is stateless or state is externalized, and metrics are trustworthy.

## 8. When NOT to use it

Startup takes minutes, capacity is bounded by one database, or metrics/alerting are unreliable.

**Alternatives:** scheduled scaling for predictable curves, queue-driven scaling (`#15 Message Queues`), or a fixed over-provisioned fleet when traffic is flat.

## 9. Implementation strategies

Kubernetes HPA:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: {name: api-hpa}
spec:
  scaleTargetRef: {apiVersion: apps/v1, kind: Deployment, name: api}
  minReplicas: 4
  maxReplicas: 60
  metrics:
    - type: Resource
      resource: {name: cpu, target: {type: Utilization, averageUtilization: 65}}
  behavior:
    scaleDown: {stabilizationWindowSeconds: 300, policies: [{type: Pods, value: 2, periodSeconds: 60}]}
```

## 10. Production-grade implementation

**Scenario:** Flash crowd: 4 replicas at 450 rps each scale to 60 in 45s; p95 moves from 320ms with 6% 503s to 95ms. Scale-in then stabilizes to 6 replicas over 300s, cutting nightly spend ~55% versus a fixed 60-replica fleet.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (Python)

target tracking with direction-aware cooldowns:

```python
import math, time
from dataclasses import dataclass

@dataclass
class Tracker:
    target: float
    lo: int = 4
    hi: int = 60
    out_cd: float = 15.0
    in_cd: float = 300.0
    changed: float = float("-inf")

    def desired(self, now: float, current: int, metric: float) -> int:
        cand = max(self.lo, min(self.hi, math.ceil(current * metric / self.target)))
        if cand == current:
            return current
        cd = self.out_cd if cand > current else self.in_cd
        if now - self.changed < cd:
            return current
        self.changed = now
        return cand

t = Tracker(target=450.0)
replicas = 4
for now, rps in [(0, 900), (60, 45), (660, 45)]:
    replicas = t.desired(now, replicas, rps)
print(replicas)
```

## 12. FastAPI integration where relevant

Prometheus metrics that KEDA or a custom-metrics HPA consumes:

```python
from fastapi import FastAPI
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

app = FastAPI()
REQS = Counter("http_requests_total", "requests", ["path", "status"])

@app.middleware("http")
async def observe(request, call_next):
    resp = await call_next(request)
    REQS.labels(request.url.path, str(resp.status_code)).inc()
    return resp

@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

Scale inference on queue depth + GPU util via KEDA — never CPU (GPU is the constraint); scale-up minutes, so keep warm floor.

## 15. Security considerations

Nodes come and go — secrets via runtime injection (CSI/env), never baked into images.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

- Autoscaling on CPU only — misses request spikes and IO wait.
- No `maxReplicas` cap — a retry storm scales into a five-figure bill.
- Scaling stateful singletons as if they were stateless pods.
- Scale-in without drain, truncating in-flight requests.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `hpa_replicas_desired/current`, scale-up latency

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Load test 0.5×–5× baseline with k6 and assert replicas track the curve with p95 inside SLO; break the metrics endpoint and confirm alerts fire; scale in during an open batch and assert graceful drain.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] - Scale on request rate or in-flight concurrency
- [ ] Keep CPU secondary. - Asymmetric behavior: fast scale-out, slow stabilized scale-in. - Keep `minReplicas` ≥ what survives one node loss. - Pre-pull images and fail readiness until caches are warm.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Scale-out lag: image pull plus warmup takes 40s while demand doubles every 20s — p95 hits 2s.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).
- **Symptom:** Metric loss: a Prometheus scrape failure freezes the HPA.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).
- **Symptom:** Scale-in kills in-flight work: a 90s batch dies at SIGTERM.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).
- **Symptom:** Oscillation: a target near steady-state load causes endless up/down cycles.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/
- https://keda.sh/docs/

**Related topics in this library:** `#8 Kubernetes`, `#91 Latency`, `#92 Throughput`, `#44 Backpressure`, `#56 Health Checks`, `#88 Cost Optimization`
