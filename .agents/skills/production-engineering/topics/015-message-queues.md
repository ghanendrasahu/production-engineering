---
topic: 15
title: Message Queues
category: A
skill: production-engineering
status: stable
---

# 015 — Message Queues

## 1. Topic name and metadata

- **Number:** 15 of 111
- **Title:** Message Queues
- **Category:** A — Backend Architecture and API Engineering
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [messaging-event-systems.md](../references/distributed-systems.md)
- **Topic file:** `.agents/skills/production-engineering/topics/015-message-queues.md`

## 2. What it is

A broker that stores messages from producers until consumers acknowledge them, providing at-least-once delivery, buffering, and load leveling.

## 3. Why it exists

Producers and consumers must live, fail, and scale independently.

## 4. The engineering problem it solves

Synchronous call chains couple availability (any hop down blocks the user), amplify load during bursts, and drop work during deploys. Queues let the system absorb 10x bursts and retry safely.

## 5. How it works internally

Producer publishes to a queue; broker persists (page cache + fsync in RabbitMQ, partition logs in Kafka); consumer prefetches N messages, processes, acks (or nacks → requeue/DLX). Delivery semantics: at-most-once (ack before work), at-least-once (ack after work — the sane default), exactly-once (transactions, Kafka EOS — real but narrow). Ordering holds per partition/queue only with single consumer or keyed partitions. Durability = durable queue + persistent messages in RabbitMQ; replication factor + min.insync.replicas in Kafka.

## 6. Architecture and design principles

API → broker (RabbitMQ / Redis Streams / SQS / Kafka) → worker fleet → results store. Web/API tier stays thin; workers scale independently.

**Design principles for this category:** Statelessness by design; every control is enforced at a boundary (edge/gateway/service); config over code; bounded resources everywhere.

## 7. When to use it

Work is longer than an HTTP budget, bursty, retryable, or must survive restarts — emails, reports, thumbnails, webhooks, inference.

## 8. When NOT to use it

The user needs the result of the work synchronously; volume is trivial (a DB table with `poll FOR UPDATE` is fine); team cannot operate a broker.

**Alternatives:** Postgres `SKIP LOCKED` queue table, Redis Streams, managed SQS, cron batches for very low frequency.

## 9. Implementation strategies

RabbitMQ: declare durable queue + DLX; prefetch 10-50; Celery against Redis/RabbitMQ; Kafka: topic with 6-12 partitions keyed by `user_id`, `acks=all`, `enable.idempotence=true`, `isolation.level=read_committed` for EOS pipelines.

```bash
rabbitmqadmin declare queue name=emails durable=true arguments='{"x-dead-letter-exchange":"dlx","x-max-length":100000}'
```

```python
import pika
conn = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq", heartbeat=30))
ch = conn.channel(); ch.queue_declare("emails", durable=True, arguments={"x-dead-letter-exchange": "dlx"})
ch.basic_qos(prefetch_count=20)
ch.basic_consume("emails", on_message, auto_ack=False)  # ack only after side effect commits
```

## 10. Production-grade implementation

**Scenario:** Image-thumbnail pipeline: 5k uploads/min peak vs 500 steady. API writes job to `images` queue; 30 Celery workers autoscale on queue depth (KEDA); prefetch 2 (CPU-bound); 99.5% of jobs finish < 2s; broker absorbs deploys without dropping work; failed jobs after 5 retries → DLQ + alert.

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
from fastapi import FastAPI
from celery import Celery
celery = Celery("tasks", broker="redis://redis:6379/0")

@app.post("/signup")
def signup(payload: Signup):
    user = create_user(payload)
    celery.send_task("tasks.send_welcome", args=[user.id])   # async, returns 202
    return {"id": user.id}, 202
```

## 13. Distributed-system considerations

Across instances this concept only works if the state it relies on (limits, locks, caches) is externalized — Redis, DB, or the edge — never in process memory alone.

## 14. AI/ML/LLM application examples where relevant

Document ingestion pipelines (parse → chunk → embed → index) belong on a queue: Celery/Arq workers, acks_late, prefetch 1, per-resource queues (OCR vs embed).

## 15. Security considerations

Queues carry PII — encrypt broker storage; ACL per service; TLS on the wire.

## 16. Performance considerations

The gateway/LB path adds ~1-3 ms; caches save 10-100x origin work; counters in Redis add one RTT — keep them on the hot path small.

## 17. Common mistakes

Auto-ack; no DLQ "because it never fails"; one giant queue for everything (no prioritisation); infinite retry on deterministic failures; producers that block indefinitely on a full broker; consumers without graceful shutdown.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `queue_depth`, `consumer_lag`, `message_age_seconds`, DLQ count

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

pytest + testcontainers (RabbitMQ/Redis): enqueue → consume → assert side effect; kill worker mid-task → message redelivered; poison message lands in DLQ after max attempts; load test at 3x expected rate to verify drain time; alert-fire drill on depth.

## 21. Deployment considerations

Roll out behind a canary or flag; watch 5xx + p99; rollback = traffic selector flip (gateway), not a rebuild.

## 22. Production-readiness checklist

- [ ] At-least-once + idempotent consumers
- [ ] Ack after commit
- [ ] Prefetch sized to throughput
- [ ] Explicit max queue length / TTL
- [ ] DLQ wired from day one
- [ ] Alert on depth and consumer lag
- [ ] Persistent messages for anything that matters
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Poison message requeued forever (no max attempts/DLQ) → consumer hot-loops, queue backs up; consumer acks before side effect → message lost on crash; unbounded queue → memory pressure, latency hours later (always cap `x-max-length` or alert on depth); consumer group rebalance storm during deploys; broker disk fills (unacked messages, no TTL) → broker down; visibility timeout shorter than job duration → duplicate concurrent processing.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://rabbitmq.com/docs/
- https://learn.microsoft.com/azure/architecture/patterns/competing-consumers

**Related topics in this library:** `#16 Pub/Sub`, `#17 Event-Driven Architecture`, `#20 Dead Letter Queues`, `#44 Backpressure`, `#14 Idempotency`, `#92 Throughput`.
