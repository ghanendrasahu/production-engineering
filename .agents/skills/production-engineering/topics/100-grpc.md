---
topic: 100
title: gRPC
category: H
skill: production-engineering
status: stable
---

# 100 — gRPC

## 1. Topic name and metadata

- **Number:** 100 of 111
- **Title:** gRPC
- **Category:** H — Networking and Communication
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [networking-apis.md](../references/networking.md)
- **Topic file:** `.agents/skills/production-engineering/topics/100-grpc.md`

## 2. What it is

A high-performance RPC framework: Protocol Buffers + HTTP/2 transport, generating typed clients/servers with unary, server-streaming, client-streaming, and bidirectional streaming methods.

## 3. Why it exists

Typed RPC beats hand-maintained REST for internal services.

## 4. The engineering problem it solves

REST's JSON + text HTTP is verbose and manual; internal services need typed contracts, streaming, and sub-millisecond overhead — hand-rolling that over JSON wastes engineering time and bandwidth.

## 5. How it works internally

`.proto` schema → generated stubs; binary protobuf (compact, fast encode/decode); HTTP/2 multiplex with deadlines/metadata; flow control; status codes (OK, INVALID_ARGUMENT, DEADLINE_EXCEEDED…); interceptors for auth/logging/metrics; load balancing: client-side via lookaside or L7 proxy (Envoy/Linkerd) since connections are long-lived; health checking protocol; reflection for debugging. Deadlines propagate through the chain (set once at ingress, all hops honor remaining budget).

## 6. Architecture and design principles

Schema (.proto) -> generated stubs -> HTTP/2 channels via LB/L7 proxy; deadlines and metadata propagate end-to-end; Envoy/mesh or client-side LB spread long-lived streams; gateway transcode (grpc-gateway) for public REST consumers.

**Design principles for this category:** Choose transport by semantics (ordering, latency, loss tolerance); name everything through discovery, never literals.

## 7. When to use it

Internal service-to-service RPC, streaming telemetry, strict contracts.

## 8. When NOT to use it

Browser-facing public APIs (REST/JSON fine; grpc-web awkward); simple CRUD teams unfamiliar with proto; human-debuggable APIs matter.

**Alternatives:** REST+JSON, GraphQL, ConnectRPC, Twirp.

## 9. Implementation strategies

```proto
service Orders { rpc GetOrder (GetOrderRequest) returns (Order); rpc Watch (OrderId) returns (stream OrderEvent); }
message GetOrderRequest { string id = 1; }
```

```python
# generated: OrderStub(channel).GetOrder(req, timeout=2.0)
channel = grpc.aio.insecure_channel("orders:50051")
resp = await stub.GetOrder(GetOrderRequest(id="o_9"), timeout=2.0)
```

## 10. Production-grade implementation

**Scenario:** Internal `payment-authorize` p50 3ms (protobuf vs JSON); deadline propagation from gateway (2s budget) prevents orphaned work; streaming `Watch` replaced 2s polling for order status; Envoy LB spread long-lived connections across pods.

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

FastAPI itself is HTTP — gRPC is a sibling server (serve both: `grpc.aio` on 50051 + FastAPI on 8000); or use `grpc-gateway` to expose REST transcoding for external clients.

## 13. Distributed-system considerations

The network is the shared resource: ordering, loss, partitions, and clock skew are not pathologies — they are the medium. Design with them.

## 14. AI/ML/LLM application examples where relevant

Internal inference gRPC with protobuf streaming beats JSON for high-TPS — deadlines propagate.

## 15. Security considerations

Metadata is plaintext after HTTP/2 decrypt — TLS everywhere; deadline propagation.

## 16. Performance considerations

Protocol choice is throughput choice: HTTP/2 multiplexing, gRPC streaming, QUIC vs TCP trade loss sensitivity against HOL blocking.

## 17. Common mistakes

REST-over-grpc (GET-like RPC semantics ignored); unbounded streams without flow control; no deadlines; breaking protos without CI check; plaintext to internet; unversioned proto packages.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `grpc_server_handling_seconds`, `grpc_requests_total{code}`

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

buf breaking check in CI (buf breaking); integration against test server (grpcurl); deadline-cancellation test (client cancels mid-stream); load test with H2 multiplexing; contract suite per .proto; chaos: server killed mid-stream.

## 21. Deployment considerations

Protocol/version changes are deploys too: enable H2/H3 at the edge first, verify clients, then simplify origins; DNS/cert changes rehearsed with low TTL.

## 22. Production-readiness checklist

- [ ] Deadlines everywhere (start low, propagate)
- [ ] Reserved field numbers
- [ ] Stream for large payloads
- [ ] L7 LB (Envoy) or client-side LB
- [ ] Health checks via grpc.health.v1
- [ ] Protobuf lint (buf, breaking-change detection in CI)
- [ ] Deadlines in SLOs
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** Deadlines not propagated (whole chain hangs past caller's timeout); protobuf field number reuse breaking backcompat (never renumber; reserve removed tags); giant messages (4-8MB cap — chunk/stream); no server reflection in prod (debug pain); L4 LB with H2 long-lived connections → one pod saturated; error mapping to HTTP 5xx in gateway loses detail — map status codes deliberately; missing deadlines everywhere (default infinite hang).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://grpc.io/docs/
- https://grpc.io/docs/what-is-grpc/introduction/

**Related topics in this library:** `#99 HTTP/2 & HTTP/3`, `#11 Timeouts`, `#12 Retries`, `#101 Webhooks` (contrast sync vs async), `#100 gRPC` needs `#60 Distributed Tracing` for context, `#102 API Versioning` (proto evolution).
