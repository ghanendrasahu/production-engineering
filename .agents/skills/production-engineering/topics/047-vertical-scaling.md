---
topic: 47
title: Vertical Scaling
category: B
skill: production-engineering
status: stable
---

# 047 — Vertical Scaling

## 1. Topic name and metadata

- **Number:** 47 of 111
- **Title:** Vertical Scaling
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [scaling-caching.md](../references/performance.md)
- **Topic file:** `.agents/skills/production-engineering/topics/047-vertical-scaling.md`

## 2. What it is

Vertical scaling (scale-up) enlarges a single node — more CPU, RAM, disk, or bandwidth — instead of adding nodes. It preserves locality and simplicity but has a hard ceiling and usually needs a restart.

## 3. Why it exists

Sometimes making the one host bigger really is the right answer.

## 4. The engineering problem it solves

Small teams drown in replication and pooling overhead for workloads one well-sized box serves; but hitting the ceiling mid-growth forces an emergency migration under load.

## 5. How it works internally

Resize means stop/start or live migration, so connections drain and clients reconnect — pools, keepalives, and retry budgets all see a blip. Memory growth changes runtime behavior: heap or `innodb_buffer_pool_size` sized to ~70% of RAM, leaving room for page cache; Python's GIL means extra cores help IO-bound concurrency, not CPU-bound throughput. The kernel must scale too (`somaxconn`, file descriptors) or the bigger box still refuses connections. Past the socket, NUMA and memory bandwidth make doubling cores yield less than double throughput.

## 6. Architecture and design principles

Below the service: instance type, VM size, database instance class, or a Kubernetes VPA. Only connection pools and the LB need reconnection tolerance.

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Workload is small-to-moderate, state is local, or a single-writer database is the bottleneck.

## 8. When NOT to use it

High availability matters (one node = one point of failure), CPU-bound Python hits the GIL, or the largest instance is already in use.

**Alternatives:** horizontal scaling for stateless services, read replicas/sharding for databases, serverless (`#89 Cold Starts`) for spiky low volume.

## 9. Implementation strategies

VPA with bounded requests:

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata: {name: api-vpa}
spec:
  targetRef: {apiVersion: apps/v1, kind: Deployment, name: api}
  updatePolicy: {updateMode: "Auto"}
  resourcePolicy:
    containerPolicies:
      - containerName: api
        minAllowed: {cpu: 250m, memory: 512Mi}
        maxAllowed: {cpu: "8", memory: 16Gi}
```

## 10. Production-grade implementation

**Scenario:** A reporting service on 4 vCPU/16 GiB had p95 of 240ms as the cache and Postgres buffer pool fought for RAM. Moving to 16 vCPU/64 GiB with `shared_buffers=40GiB` dropped p95 to 90ms and major page faults from 900/s to <5/s, inside a 4-minute drain window with a 450s pool reconnect budget.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (Python)

find where more cores stop helping:

```python
import multiprocessing as mp
import time
from concurrent.futures import ThreadPoolExecutor

SECONDS = 2.0

def burn(_):
    end = time.perf_counter() + SECONDS
    while time.perf_counter() < end:
        pass                       # CPU-bound Python work

def run(factory, workers: int) -> float:
    start = time.perf_counter()
    with factory(workers) as pool:
        list(pool.map(burn, range(workers)))
    return time.perf_counter() - start

for n in (1, 2, 4, 8):
    print(n, run(mp.Pool, n), run(ThreadPoolExecutor, n))
```

## 12. FastAPI integration where relevant

size per-process queueing to the capacity bought:

```python
import os
from fastapi import FastAPI

cores = os.cpu_count() or 2
app = FastAPI(limit_concurrency=cores * int(os.environ.get("QUEUE_DEPTH", 64)))

@app.get("/ready")
def ready() -> dict:
    return {"cores": cores, "limit": app.router.concurrency_limit}
```

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

Bigger GPU (A100→H100) beats more replicas for large models — vertical first until VRAM ceiling, then tensor-parallel.

## 15. Security considerations

Bigger host doesn't change threat model — but concentration raises blast radius; treat accordingly.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

- Scale-up as the only strategy: every resize is an outage risk and the ceiling always arrives.
- Growing memory without fixing leaks.
- Choosing the largest instance "to be safe" with no utilization data.
- Vertical-only scaling of a stateless API that would scale linearly.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `cpu_headroom_ratio`, memory saturation, instance-class utilization

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Benchmark throughput at 1×, 2×, and 4× sizes to find the knee; fill 90% of RAM and assert graceful degradation without OOMKill; count failed requests during a resize; assert no swap (`vmstat 1` si/so ≈ 0) after the upgrade.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] - Measure saturation (steal, page faults, memory bandwidth) before buying bigger. - Reserve vertical scaling for the stateful tier where locality matters. - Run VPA in recommender mode first
- [ ] Enable `Auto` with disruption budgets. - Drain connections and back off reconnects around every resize.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Single point of failure: the enlarged node dies and there is no replica — full outage.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).
- **Symptom:** Unexpected resize during business hours drops every open connection.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).
- **Symptom:** GIL ceiling: more cores give ~0% gain on CPU-bound Python; cost per unit of work rises.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).
- **Symptom:** Leaks scale with memory: a bigger heap only delays the OOM.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://aws.amazon.com/ec2/instance-types/

**Related topics in this library:** `#46 Horizontal Scaling`, `#42 Garbage Collection`, `#41 Memory Leaks`, `#91 Latency`, `#88 Cost Optimization`, `#29 Read Replicas`
