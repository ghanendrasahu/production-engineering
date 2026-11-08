---
topic: 46
title: Horizontal Scaling
category: B
skill: production-engineering
status: stable
---

# 046 — Horizontal Scaling

## 1. Topic name and metadata

- **Number:** 46 of 111
- **Title:** Horizontal Scaling
- **Category:** B — Database Engineering and Distributed Systems
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [scaling-caching.md](../references/performance.md)
- **Topic file:** `.agents/skills/production-engineering/topics/046-horizontal-scaling.md`

## 2. What it is

Horizontal scaling adds more instances of the same service behind a load balancer instead of enlarging one. Capacity grows by adding nodes until a shared dependency becomes the bottleneck.

## 3. Why it exists

Scaling out adds capacity without new hosts — if state permits.

## 4. The engineering problem it solves

One large machine has a hard ceiling on CPU, RAM, and connections, and its failure takes the whole service down; the top of the instance ladder is also ruinously expensive per unit of capacity.

## 5. How it works internally

The LB keeps a membership set updated by health checks — three consecutive failures remove a target, a passing check re-adds it. Traffic spreads via round-robin, least-connections, or consistent hashing; scale-in drains (deregister, let connections finish) before termination. Since any node must serve any request, sessions and files move to shared stores, otherwise you need sticky sessions that break when nodes are replaced. Throughput scales near-linearly while nodes have headroom, then flattens as the database, pool, or lock service saturates.

## 6. Architecture and design principles

Behind a LoadBalancer/Ingress (`#3 Load Balancing`) in front of identical replicas, with state in Redis/Postgres and membership via service discovery (`#9 Service Discovery`).

**Design principles for this category:** Measure before mutating; the primary is the system of record; correctness invariants belong in constraints and transactions, not app code.

## 7. When to use it

Traffic exceeds one node, state is externalized, and you want redundancy as fault tolerance.

## 8. When NOT to use it

State cannot be externalized, coordination dominates (tight distributed locks), or load fits comfortably on one box.

**Alternatives:** vertical scaling for simplicity, sharding (`#30 Sharding`) when one logical dataset is the limit.

## 9. Implementation strategies

Deployment plus preStop drain:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: {name: api}
spec:
  replicas: 12
  selector: {matchLabels: {app: api}}
  template:
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: api
          image: registry.example.com/api:1.42.0
          ports: [{containerPort: 8080}]
          lifecycle:
            preStop: {exec: {command: ["sleep", "10"]}}
          readinessProbe: {httpGet: {path: /ready, port: 8080}}
```

## 10. Production-grade implementation

**Scenario:** A catalog API runs 12 replicas behind an ALB; a launch pushes 8k → 34k rps. Scaling to 40 replicas takes 50s and holds p95 at 170–195ms (was 1.4s, 11% 5xx). Sessions already lived in Redis; killing one node mid-load caused 0.4% errors for 8s.

**To reach production grade, combine the implementation in section 9 with these non-negotiables:**

- Wire the section 19 signals into dashboards and alerts *before* the rollout — an unmeasured control is decorative.
- Bake the control into the pipeline, not the runbook: IaC/CI enforces it on every deploy; humans should not be the enforcement layer (`#6 CI/CD`, `#104 Infrastructure as Code`).
- Load and failure-test it at 2x expected traffic, in staging with production-like data volume, before declaring it done (`#26 Query Optimization`, `#91 Latency`).
- Roll out behind a canary or flag with automatic rollback on SLO burn (`#53 Canary Releases`, `#51 Feature Flags`), and document the rollback path in the runbook.
- Verify the dependent data path explicitly: migrations, secrets, certificates, and IAM policies ship with the same change.

## 11. Code examples (Python)

state in Redis makes replicas interchangeable:

```python
import json, os, uuid
import redis

store = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

def load_cart(session_id: str) -> dict:
    raw = store.get(f"session:{session_id}")
    return json.loads(raw) if raw else {"id": session_id, "items": []}

def add_item(session_id: str, sku: str) -> dict:
    cart = load_cart(session_id)
    cart["items"].append(sku)
    store.setex(f"session:{session_id}", 3600, json.dumps(cart))
    return cart

sid = uuid.uuid4().hex
print(add_item(sid, "SKU-1"))
print(load_cart(sid))
```

## 12. FastAPI integration where relevant

a dependency that hides which replica answers:

```python
import json, os, redis
from fastapi import Depends, FastAPI, Header, HTTPException

app = FastAPI()
store = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

def get_session(x_session_id: str = Header(...)) -> dict:
    raw = store.get(f"session:{x_session_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="unknown session")
    return json.loads(raw)

@app.get("/cart")
def cart(session: dict = Depends(get_session)) -> dict:
    return session
```

## 13. Distributed-system considerations

Distributed state is the hard part: replicas, shards, and lock holders disagree by milliseconds; correctness must survive that disagreement — single-writer, consensus, or commutative designs.

## 14. AI/ML/LLM application examples where relevant

Horizontal replicas of inference servers; batch across them; KV cache rarely shared — measure per-replica efficiency.

## 15. Security considerations

More replicas, same policies — test policy enforcement per instance.

## 16. Performance considerations

DB performance dominates: connection pools, indexes, and lock discipline decide p99 more than any app code change.

## 17. Common mistakes

- Scaling nodes that keep local state — replicas diverge and lose data.
- Sticky sessions used to dodge externalizing state.
- Scaling out against a single primary database.
- No replica cap, so a retry storm scales without limit.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `rps_per_instance` variance, connection distribution

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Load test at 1, 4, and 12 replicas and plot throughput vs. replicas; delete a pod mid-test and assert errors stay <1%; audit that no session bytes live on local disk.

## 21. Deployment considerations

Ship with expand/contract migrations; zero-downtime requires old code on new schema during the roll — never deploy breaking DDL in the same release as the code that depends on it.

## 22. Production-readiness checklist

- [ ] - Make every node disposable: no local disk state, config from env/secrets, honest readiness checks. - Externalize sessions and uploads before scaling past one node. - Size connection pools for fleet size, never per-pod defaults. - Drain before SIGTERM with a preStop delay so the LB deregisters first.
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Stateful service scaled out: two replicas overwrite each other's local file — silent data loss.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).
- **Symptom:** Hot-key skew: one popular product drives 30% of traffic to a single replica at 8× median p99.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).
- **Symptom:** Pool exhaustion: 40 pods × 10 connections exceed Postgres's 200-connection cap — errors become "too many connections."
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).
- **Symptom:** Sticky sessions break across deploys: carts vanish when a node is replaced.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://kubernetes.io/docs/concepts/architecture/

**Related topics in this library:** `#3 Load Balancing`, `#47 Vertical Scaling`, `#32 Replication`, `#29 Read Replicas`, `#35 Eventual Consistency`, `#34 CAP Theorem`
