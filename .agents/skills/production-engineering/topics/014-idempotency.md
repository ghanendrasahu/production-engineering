---
topic: 14
title: Idempotency
category: A
skill: production-engineering
status: stable
---

# 014 — Idempotency

## 1. Topic name and metadata

- **Number:** 14 of 111
- **Title:** Idempotency
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [backend-architecture.md](../references/architecture.md)
- **Topic file:** `.agents/skills/production-engineering/topics/014-idempotency.md`

## 2. What it is

A property of an operation such that performing it once or many times has the same observable effect; for APIs, the client supplies an idempotency key and the server dedupes by it.

## 3. Why it exists

Repeats of the same request must not charge, ship, or send twice.

## 4. The engineering problem it solves

Retries, double-clicks, webhook redeliveries, and client timeouts mean "did it happen?" is ambiguous; without idempotency, ambiguity charges cards twice, creates duplicate orders, and double-sends emails.

## 5. How it works internally

Client generates a unique key (UUID v4) per logical operation and sends it (e.g., `Idempotency-Key: 9b2f…`). Server runs a transaction: `INSERT INTO idempotency_keys(key, status, response) VALUES (...) ON CONFLICT DO NOTHING` (or Redis `SET key1 <hash> NX PX 86400000`); on conflict, returns the stored response instead of re-executing. Store request hash too — same key with different payload must be rejected (422). Keys expire with a TTL ≥ retry horizon (24h typical). The critical section must be atomic with the side effect (same DB transaction for DB writes; for external APIs, forward the same key to the downstream provider which supports idempotency — Stripe-style).

## 6. Architecture and design principles

API boundary + persistence layer (`idempotency_keys` table), plus downstream forwarding to providers that accept keys (Stripe, SendGrid). Middleware or dependency extracts the key; service layer performs check-and-execute in one transaction.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Any client-retried mutating call, webhooks, payment flows, order creation, queue consumers (at-least-once delivery).

## 8. When NOT to use it

Pure reads; internal calls with exactly-once transport (rare/nonexistent); operations where duplication is harmless and provably so.

**Alternatives:** natural unique constraints (email + order number), `#36 Optimistic Locking` for version-checked updates, "at-least-once + dedupe" instead of "exactly-once".

## 9. Implementation strategies

```python
# SQLAlchemy model sketch
class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))  # in_flight | done
    response: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

Flow in one DB transaction: SELECT key FOR UPDATE → if none: INSERT status=in_flight; execute side effect; UPDATE status=done + response; COMMIT. Concurrent duplicates block on the row lock and re-read the outcome.

## 10. Production-grade implementation

**Scenario:** Stripe-integration style `POST /v1/charges` with `Idempotency-Key` per user checkout attempt; DB transaction stores key + charge result atomically; retried request within 24h returns the original `200 {charge_id}` without re-calling Stripe; mismatched key+payload → `422`. Double-charge reports dropped to zero.

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

```python
@app.post("/payments")
async def create_payment(req: PaymentRequest, idempotency_key: str = Header(...), db: Session = Depends(get_db)):
    outcome = await idempotency.execute(db, idempotency_key, req.model_dump_json(), lambda: gateway.charge(req))
    return outcome.response
```

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

Every billable LLM call takes an idempotency key hash(tenant, feature, messages, model, params); duplicates return the cached response instead of double billing.

## 15. Security considerations

Idempotency keys must be protected as sensitive data; reject key+payload mismatch.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Client generates a key per retry attempt (defeats the purpose); dedup by request body hash only (breaks legit repeat orders); key check outside the transaction; no TTL; swallowing duplicate errors and returning 200 with a fabricated response that hides failure.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `idempotency_hits_total`, `idempotency_conflicts_total`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest: same key twice → origin called once, identical response both times; different payload same key → 422; concurrent requests with same key (asyncio.gather ×10) → single execution; key expiry behavior; Stripe-style integration test with provider test mode redelivering webhooks.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] One key per logical operation, from client
- [ ] Store request hash
- [ ] Atomic check-and-execute
- [ ] 422 on key+payload mismatch
- [ ] TTL ≥ 24h
- [ ] Return stored status+body
- [ ] Forward keys downstream
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Key stored in Redis but side effect committed separately → key lost, duplicate executes (store key in same DB/transaction); same key + different payload silently accepted → data corruption; TTL shorter than the retry window → duplicates recur after expiry; storing the response but not status=in_flight → concurrent duplicates both execute; downstream provider without idempotency support and no dedup → duplicate charge anyway; user retrying with a *new* key believing it is the same operation.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://learn.microsoft.com/azure/architecture/patterns/idempotent-consumer

**Related topics in this library:** `#12 Retries`, `#13 Exponential Backoff`, `#18 Distributed Transactions`, `#19 Saga Pattern`, `#36 Optimistic Locking`, `#101 Webhooks` (receivers must dedupe).
