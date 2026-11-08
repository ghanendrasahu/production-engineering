---
topic: 98
title: TCP vs UDP
category: H
skill: production-engineering
status: stable
---

# 098 — TCP vs UDP

## 1. Topic name and metadata

- **Number:** 98 of 111
- **Title:** TCP vs UDP
- **Category:** H — Networking and Communication
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [networking-apis.md](../references/networking.md)
- **Topic file:** `.agents/skills/production-engineering/topics/098-tcp-vs-udp.md`

## 2. What it is

TCP: connection-oriented, ordered, reliable, congestion-controlled byte stream. UDP: connectionless datagrams — no ordering, no delivery guarantee, no flow control, minimal overhead.

## 3. Why it exists

Reliability vs overhead is a per-protocol design choice.

## 4. The engineering problem it solves

Picking the wrong transport loses latency/ordering needs or guarantees the wrong thing; both cross the same network, differently purposed.

## 5. How it works internally

TCP: 3-way handshake (1 RTT), sequence numbers + cumulative ACKs, retransmission (fast retransmit + RTO), congestion control (CUBIC/BBR), flow control window; head-of-line blocking across the single stream. UDP: send/receive, no state; app does its own reliability if needed. QUIC (HTTP/3) runs over UDP with its own reliability + multiplexed streams — no TCP HOL blocking, faster (0-RTT) handshake with TLS 1.3. Choose by: need ordered reliable bytes → TCP (HTTP, DB); need minimal latency and tolerate loss → UDP (voice, video, game state — WebRTC); need reliability without TCP's constraints → QUIC/HTTP3.

## 6. Architecture and design principles

Transport layer only: TCP(HTTP/DB/Redis clients) and UDP(DNS, WebRTC media, QUIC) share IP; choice happens per socket; middleboxes and firewalls filter differently per protocol — verify both traverse paths.

**Design principles for this category:** Choose transport by semantics (ordering, latency, loss tolerance); name everything through discovery, never literals.

## 7. When to use it

Transport design — TCP default; UDP for media/telemetry/QUIC.

## 8. When NOT to use it

Need reliable ordered delivery (don't force UDP).

**Alternatives:** QUIC for new protocols, SCTP (rarely), HTTP/2 over TCP (the universal default).

## 9. Implementation strategies

```python
import socket
# UDP: sendto, no connect; dedupe/reorder yourself
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# TCP: connect once (with timeout!), Nagle off for latency-critical
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
```

## 10. Production-grade implementation

**Scenario:** Voice calls over UDP (WebRTC): a lost packet retransmitted is useless (late > lost) — jitter buffer absorbs; backend API remains TCP/TLS/HTTP2; DNS lookups over UDP with TCP fallback (truncation/TC bit); internal metrics over UDP push (loss acceptable, no backpressure) — with 1% loss fine.

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

The network is the shared resource: ordering, loss, partitions, and clock skew are not pathologies — they are the medium. Design with them.

## 14. AI/ML/LLM application examples where relevant

Provider websockets (Realtime APIs) over TCP/TLS — watch corp-proxy traversal; keep HTTP/SSE fallback.

## 15. Security considerations

UDP amplification and spoofing — rate-limit 1780/1; prefer TCP/QUIC for sensitive data.

## 16. Performance considerations

Protocol choice is throughput choice: HTTP/2 multiplexing, gRPC streaming, QUIC vs TCP trade loss sensitivity against HOL blocking.

## 17. Common mistakes

UDP without app-level sequence numbers for ordered needs; TCP for high-rate telemetry where loss is fine (bloated); QUIC everywhere without corp-network testing; ignoring TCP handshake latency for far replicas.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `tcp_retransmits_total`, `udp_drops_total`, handshake RTT

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

Packet loss injection test (toxiproxy); latency jitter measurements; firewall traversal test; QUIC vs H2 A/B; retransmit rate monitoring.

## 21. Deployment considerations

Protocol/version changes are deploys too: enable H2/H3 at the edge first, verify clients, then simplify origins; DNS/cert changes rehearsed with low TTL.

## 22. Production-readiness checklist

- [ ] TCP for anything needing reliable ordered bytes (HTTP/DB/Redis clients)
- [ ] UDP only when loss-tolerant and latency-critical
- [ ] Enable TCP_NODELAY for request/response apps
- [ ] Keepalive < LB idle timeout
- [ ] Monitor retransmits
- [ ] No-UDP-keep-it-except-QUIC discipline
- [ ] Firewall rule audits for UDP ports
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** TCP HOL blocking under loss (one lost segment stalls all streams — HTTP/2 suffers; HTTP/3 fixes); UDP firewalled by corporate networks (fallback path needed); MTU blackholing; SYN backlog overflow (net.core.somaxconn); UDP sender flooding (no congestion control — small `send()` can saturate link); TCP retransmit ambiguity causing 200ms spikes; pooled TCP without keepalive → LB drops idle silently.
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.rfc-editor.org/rfc/rfc793
- https://www.rfc-editor.org/rfc/rfc768

**Related topics in this library:** `#99 HTTP/2 & HTTP/3`, `#97 DNS` (UDP+TCP), `#100 gRPC` (HTTP/2 over TCP), `#22 WebSockets` (TCP), `#75 DDoS Protection` (UDP floods).
