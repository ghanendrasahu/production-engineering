---
topic: 101
title: Webhooks
category: H
skill: production-engineering
status: stable
---

# 101 — Webhooks

## 1. Topic name and metadata

- **Number:** 101 of 111
- **Title:** Webhooks
- **Category:** H — Networking and Communication
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [networking-apis.md](../references/networking.md)
- **Topic file:** `.agents/skills/production-engineering/topics/101-webhooks.md`

## 2. What it is

HTTP callbacks: a service POSTs a signed event payload to a URL you register — server-to-server push replacing polling of the provider's API.

## 3. Why it exists

Providers push events instead of being polled.

## 4. The engineering problem it solves

Polling `GET /orders/:id` every 5s wastes both sides and adds lag; webhooks deliver the fact once, as it happens.

## 5. How it works internally

Provider → your HTTPS endpoint with JSON body + signature headers (Stripe: `Stripe-Signature: t=…,v1=…` HMAC-SHA256 of `t.body` with your signing secret; GitHub `X-Hub-Signature-256`). Security steps in order: raw body (before parsing!) → verify HMAC → constant-time compare → timestamp freshness (replay protection ±5min) → validate schema → **respond 2xx fast** → process async via queue. Delivery is at-least-once: expect duplicates — dedupe by event id. Failing endpoint → provider retries with backoff (Stripe: 3 days) then may disable it.

## 6. Architecture and design principles

Provider -> your public HTTPS endpoint -> signature verify + dedupe -> enqueue (202) -> async worker processes; egress-allowlisted sender; results recorded for audit and redrive.

**Design principles for this category:** Choose transport by semantics (ordering, latency, loss tolerance); name everything through discovery, never literals.

## 7. When to use it

Provider supports webhooks — always enable alongside redirects.

## 8. When NOT to use it

Fully internal flows where you control both sides and durability needs exceed provider retry horizon.

**Alternatives:** polling (last resort), provider-managed sync APIs, message buses for internal events.

## 9. Implementation strategies

```python
@app.post("/webhooks/stripe")
async def stripe_hook(request: Request):
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    event = stripe.Webhook.construct_event(body, sig, WEBHOOK_SECRET)  # raises on bad sig
    dedupe_key = f"wh:{event.id}"
    if not redis.set(dedupe_key, "1", nx=True, ex=86400): return {"ok": True}  # dup
    celery.send_task("tasks.process_payment_event", args=[event.to_dict()])
    return {"ok": True}
```

## 10. Production-grade implementation

**Scenario:** Payments via Stripe: 40% of order confirmations arrive via webhook vs redirect (user closed tab); HMAC verified, dedup by event.id (TTL 7d), processed via Celery; endpoint hinted at `orders-svc:443/webhooks/stripe` via egress allowlist; average delivery 300-900ms; redelivery storm during an outage handled by dedupe.

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

Above; always: idempotent consumer + DLQ + redrive; respond before processing (avoid provider timeouts → redelivery storms).

## 13. Distributed-system considerations

The network is the shared resource: ordering, loss, partitions, and clock skew are not pathologies — they are the medium. Design with them.

## 14. AI/ML/LLM application examples where relevant

Provider webhooks (batch/fine-tune done) — HMAC verify, dedupe, process async.

## 15. Security considerations

HMAC-SHA256 signature verify (raw body), timestamp window, dedupe — or no trust.

## 16. Performance considerations

Protocol choice is throughput choice: HTTP/2 multiplexing, gRPC streaming, QUIC vs TCP trade loss sensitivity against HOL blocking.

## 17. Common mistakes

Parsing before verifying; 200-after-processing; processing inline of 30s webhook timeout; trusting payload fields without signature; no dedupe; exposing webhook path publicly with weak secret; 5xx on nonfatal event types.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `webhook_delivery_success_ratio`, delivery latency, redeliveries

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest with generated valid/invalid HMAC; replay old timestamp → reject; duplicate delivery → single processing; processing-failure → DLQ; provider test-mode deliveries; end-to-end with stripe-cli/github-cli.

## 21. Deployment considerations

Protocol/version changes are deploys too: enable H2/H3 at the edge first, verify clients, then simplify origins; DNS/cert changes rehearsed with low TTL.

## 22. Production-readiness checklist

- [ ] HMAC verify (raw body, constant-time, timestamp window)
- [ ] Dedupe by event id with TTL
- [ ] Fast 2xx + async processing
- [ ] DLQ + redrive tooling
- [ ] Alert on repeated 4xx/5xx from provider
- [ ] Signature secret rotation with overlap window
- [ ] Schema-tolerant parsing
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Responding after processing (provider timeout → retries → duplicates; dedupe still catches it — but queue bloats); signature verified AFTER json parsing applied to raw body (must verify bytes); missing replay-timestamp check (old captured request replayed); endpoint returns 500 (provider disables after repeated failures — alert); schema drift (provider adds fields — additive only, tolerate); no dedupe (double charge!); webhook URL enumeration (use unguessable path or mTLS); secret committed in repo.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://docs.stripe.com/webhooks
- https://docs.github.com/en/webhooks

**Related topics in this library:** `#14 Idempotency`, `#20 Dead Letter Queues`, `#15 Message Queues`, `#73 Encryption in Transit`, `#80 SSRF` (keep webhook egress allowlisted).
