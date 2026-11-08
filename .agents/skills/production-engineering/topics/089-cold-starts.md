---
topic: 89
title: Cold Starts
category: G
skill: production-engineering
status: stable
---

# 089 — Cold Starts

## 1. Topic name and metadata

- **Number:** 89 of 111
- **Title:** Cold Starts
- **Category:** G — Performance Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [performance-engineering.md](../references/performance.md)
- **Topic file:** `.agents/skills/production-engineering/topics/089-cold-starts.md`

## 2. What it is

The extra latency of the first invocation after a serverless/container instance is created — runtime boot, dependency load, app initialization (model loading, connection setup) before the first byte of business logic runs.

## 3. Why it exists

The first request sets expectations; cold starts ruin it.

## 4. The engineering problem it solves

Spiky p99s, timeouts on the unlucky first request, and quiet ruin of demos and real user flows for serverless workloads with bursty, low traffic.

## 5. How it works internally

Phases: platform provisioning (VM/microVM — Firecracker ~100-200ms) → runtime init (language boot; JVM slowest) → function init (imports, global scope) → handler execution. Mitigations: **provisioned concurrency** (always-warm instances — pay for idle), snapstart (JVM snapshot restore — ms), custom runtimes (Rust/Go boot fastest; Python/Node modest), lazy-init vs eager-init tradeoff (global scope runs once warm; per-request cold cost lands on first call), smaller deployment packages (cold init scales with code size), dependency trimming, and warming pings (synthetic traffic every N min — works, but burns money and can mask real scale-to-zero economics).

## 6. Architecture and design principles

FaaS (Lambda/Cloud Run) cold path; containers reuse warm instances; keep-alive pools for LLM SDKs; DB connections established outside handler (global).

**Design principles for this category:** Measure distributions, not averages; optimize the top offender; quantify every trade-off in latency, memory, and cost.

## 7. When to use it

Serverless user-facing latency SLOs tight — apply warm pools.

## 8. When NOT to use it

Batch jobs (cold irrelevant).

**Alternatives:** always-on containers (ECS/K8s — simplest), snapstart, smaller runtimes.

## 9. Implementation strategies

```python
# Lambda-style: init outside the handler
import boto3, os
s3 = boto3.client("s3")          # initialized once per warm instance
import pydantic, heavy_lib       # cost lands on cold start only

def handler(event, context):
    return {"statusCode": 200, "body": do_work(event)}
```

Cloud Run: `min-instances=1`; Lambda: provisioned concurrency = N; measure with `X-Amz-Total-Matched` / trace duration cold vs warm.

## 10. Production-grade implementation

**Scenario:** OCR API on Lambda: 4s cold starts (Tesseract import) killing 2% of requests at the 3s ALB timeout; fixed: provisioned concurrency 2 + lazy DB pool; cold p99 4s→180ms (warm), no failures; cost +$60/month vs lost conversions.

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

uvicorn worker with model preloaded in lifespan startup; `min_instances ≥ 1` in Cloud Run so first user never pays the load; startupProbe sends traffic only after lifespan completes.

## 13. Distributed-system considerations

Tail latency is a distributed phenomenon: one slow shard/hop dominates fanout latency — measure the parent and the children separately.

## 14. AI/ML/LLM application examples where relevant

Provisioned concurrency or min-instances for chat endpoints — cold model load ruins first impressions.

## 15. Security considerations

Rebuild cold images frequently — stale CVE patches hide in cold paths.

## 16. Performance considerations

The entire point: measure distributions, find the top offender, fix, re-measure — every claim here is a benchmark waiting to happen.

## 17. Common mistakes

Eager-loading everything every invocation; 500MB layers; pings every 5min at scale ("it works but costs 4x"); synchronous heavy init per request; no min-instances on user-facing Cloud Run; ignoring cold latency in SLOs.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `cold_start_total`, `cold_start_latency_seconds`, warm ratio

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Load test from zero replicas → first-request latency; assert p99 within SLO; deployment canary warms instance; metric for cold-start ratio (`cold_start_total / total`); chaos: scale-to-zero drill.

## 21. Deployment considerations

Performance changes ship behind A/B: measure p50/p95/p99 and cost before/after on real traffic; hedge, don't gamble.

## 22. Production-readiness checklist

- [ ] Global-scope init
- [ ] Small packages (strip dev deps)
- [ ] Go/Rust for latency-critical FaaS
- [ ] Provisioned concurrency where SLOs demand
- [ ] Min-instances=1 for always-feeling-fast
- [ ] Measure cold vs warm separately
- [ ] Connection reuse outside handler
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Cold start + retry = 2× cold cost (timeout at client while Lambda still runs); container scale-from-zero on cron bursts all cold simultaneously; giant dependency layer (300MB) → every deploy re-cold; "keep-warm" ping firing every 5min prevents scale-to-zero — costs money, no burst benefit at random times; JVM without snapstart; health checks not excluding cold instances → LB sends traffic to booting pods.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://docs.aws.amazon.com/lambda/
- https://cloud.google.com/run/docs/configurations/container-contract

**Related topics in this library:** `#90 Serverless Limits`, `#91 Latency`, `#93 P99 Latency`, `#45 Autoscaling`, `#89 Cold Starts` mitigates `#90 Serverless Limits`.
