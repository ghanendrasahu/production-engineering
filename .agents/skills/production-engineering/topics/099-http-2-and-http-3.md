---
topic: 99
title: HTTP/2 & HTTP/3
category: H
skill: production-engineering
status: stable
---

# 099 — HTTP/2 & HTTP/3

## 1. Topic name and metadata

- **Number:** 99 of 111
- **Title:** HTTP/2 & HTTP/3
- **Category:** H — Networking and Communication
- **Skill:** `production-engineering` ([SKILL.md](../SKILL.md))
- **Deep reference:** [networking-apis.md](../references/networking.md)
- **Topic file:** `.agents/skills/production-engineering/topics/099-http-2-and-http-3.md`

## 2. What it is

The modern binary HTTP transports. HTTP/2 (RFC 7540): multiplexed streams over one TCP connection with HPACK header compression. HTTP/3 (RFC 9114): same semantics over QUIC (UDP) — no TCP head-of-line blocking, faster handshakes, better mobility.

## 3. Why it exists

HTTP must multiplex and survive loss without head-of-line blocking.

## 4. The engineering problem it solves

HTTP/1.1's one-request-per-connection serializes requests (6-connection cap), repeats headers, and wastes TLS re-handshakes; H2 multiplexes; H3 additionally fixes loss behavior and connection migration.

## 5. How it works internally

H2: single TCP + N concurrent streams, flow control per stream and connection, HPACK compresses headers, server push (deprecated-ish), ALPN negotiation (`h2`). H3: QUIC streams inside UDP datagrams; 0-RTT resume; connection IDs survive network changes (WiFi→4G); streams fully independent — one lost packet blocks only its stream; QPACK header compression. Encryption-in-QUIC is mandatory (always encrypted). Practice: enable H2 at the proxy (Nginx `listen ... http2`), H3 where clients support (CDN edge); origin hops can stay H1/H2.

## 6. Architecture and design principles

Negotiated via ALPN at TLS (`h2`/`h3`); terminated at CDN/edge LB, end-to-end or mesh internally; multiplexing happens inside one connection; origin hops usually stay h1/h2.

**Design principles for this category:** Choose transport by semantics (ordering, latency, loss tolerance); name everything through discovery, never literals.

## 7. When to use it

Any internet-facing service — enable H2 (universal) and consider H3 at edge.

## 8. When NOT to use it

Internal single-connection simplicity is fine.

**Alternatives:** H1 keep-alive (works, costs more), gRPC.

## 9. Implementation strategies

```nginx
listen 443 ssl http2;            # H2 terminated at edge
add_header Alt-Svc 'h3=":443"; ma=86400';   # advertise H3 upgrade
```

`curl --http3 -I https://app` to verify; keep origin H2 + keepalive.

## 10. Production-grade implementation

**Scenario:** Asset-heavy page over H2: 40 requests over 1 connection, HPACK saves 70% header bytes; H3 on Cloudflare: p95 40→28ms on lossy mobile networks (1% loss kills H2, barely touches H3).

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

HTTP/2 mandatory to providers for many concurrent small calls; H3 helps streaming over lossy mobile.

## 15. Security considerations

Patch rapid-reset CVE-2023-44487; rate-limit resets at edge.

## 16. Performance considerations

Protocol choice is throughput choice: HTTP/2 multiplexing, gRPC streaming, QUIC vs TCP trade loss sensitivity against HOL blocking.

## 17. Common mistakes

H1.1 end-to-end "because simple"; H2 via plaintext h2c without understanding; unpatched rapid-reset; assuming H3 everywhere works (corp proxies); enabling H2 + ignoring stream limits.

## 18. Anti-patterns

The field anti-patterns for this topic are the same ones listed in section 17 — they cluster into four recurring shapes. Review code and incidents against these **red flags**:

- An unbounded resource (queue, pool, retry loop, cache, response) somewhere on the path — production favors bounded shapes everywhere (`#44 Backpressure`, `#1 Rate Limiting`).
- A correctness control without its verification: retries without idempotency, locks without TTL/fencing, caches without invalidation plans, migrations without rollback.
- Silent degradation: errors swallowed, fallback paths unmonitored, `success: true` on partial failure.
- A shared failure domain introduced for convenience — hard dependency, cross-tenant leakage, one config for all criticality levels.

If you spot one of these in review, stop and fix it before merging — it will page someone later.

## 19. Monitoring and observability

**Signals to emit:** `http2_streams_active`, `http2_rapid_resets`, h3 vs h2 TTFB

**Also watch:** service-level RED (rate/errors/duration), the dependency trees above and below this control, and cost (`#88 Cost Optimization`). Correlate logs, metrics, and traces via a shared `trace_id` (`#60 Distributed Tracing`, `#66 Observability`).

## 20. Testing strategies

curl --http2/--http3; browser waterfall comparison; loss injection (2% packet loss) comparing H2 vs H3; Rapid Reset regression (patched LB); keepalive reuse verification.

## 21. Deployment considerations

Protocol/version changes are deploys too: enable H2/H3 at the edge first, verify clients, then simplify origins; DNS/cert changes rehearsed with low TTL.

## 22. Production-readiness checklist

- [ ] H2 at proxy always
- [ ] H3 at CDN
- [ ] HPACK/keepalive everywhere
- [ ] Alert on 5xx + resets
- [ ] Keep-alive tuning
- [ ] H3 verification in browser tests
- [ ] Don't force H3 on origin for micro-optimizations
- [ ] Observability wired (metrics above), dashboards linked, alert runbook written
- [ ] Rollback or kill-switch verified < 5 minutes

## 23. Troubleshooting guide

- **Symptom:** H2 prioritizing browser bugs (nginx/nghttp2 old versions); HOL blocking under packet loss on H2 (H3 solves on lossy links); H2 behind LB with client resets (mitigate — use HTTP/2 end-to-end LB like AWS ALB); H3 fallback broken (Alt-Svc cached stale); buffering SSE/WS through H2 fine but not through broken middle-boxes; h2c vs tls confusion; HTTP/2 Rapid Reset DDoS (CVE-2023-44487 — patch and rate-limit resets).
  **Check:** the failure modes in section 5 and the anti-patterns in section 18; confirm configuration against section 9/10.
  **Fix:** apply the matching best practice in section 18, then re-verify with section 20 (tests) and section 19 (metrics).

## 24. Further reading and authoritative references

- https://www.rfc-editor.org/rfc/rfc9114
- https://www.rfc-editor.org/rfc/rfc7540

**Related topics in this library:** `#98 TCP vs UDP`, `#4 Reverse Proxies`, `#48 CDN`, `#24 Server-Sent Events` (H2 multiplex), `#100 gRPC` (HTTP/2 foundation).
