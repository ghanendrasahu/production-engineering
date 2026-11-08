# Workflow — Architecture Review

Structured design review for new systems or significant changes. Input: a design doc or ADR. Output: questions answered, risks named, verdict documented.

## Preconditions

Reviewer must know: requirements (functional + NFRs), current architecture, traffic/data projections, team composition, and the change's blast radius. If the design doc doesn't state these, send it back — reviewing without them is theater.

## The Review Questions (in this order)

1. **Necessity** — What breaks if we build nothing? What is the simplest thing that works? (The answer is often 'a module in the monolith'.)
2. **Boundaries** — Service/module ownership and contracts? Who consumes each API? Breaking-change story on day 2?
3. **Data** — System of record? Consistency model per entity (strong vs eventual)? Migration path? Backup/rollback? Data lifecycle (TTL/retention/GDPR)?
4. **Failure** — Dependency slow/down/lying behavior specified? Timeouts, retries+jitter, idempotency, breakers, fallbacks, degraded modes? Failure of the new component itself — detected how, recovered how?
5. **Scale** — Saturation point identified? Headroom at 3x today's traffic? What must change at 10x — and is that path pre-built or pre-acknowledged?
6. **Security** — Trust boundaries; identity propagation; secrets handling; least privilege; data classification; compliance needs.
7. **Operations** — Deploys (canary/blue-green), probes, SLOs, alerts with runbooks, rollback, on-call ownership, DR relationship to this service.
8. **Cost** — Estimated infra + per-request (and LLM token) cost at current and 10x scale vs team budget; biggest cost lever named.
9. **Complexity budget** — Count the new moving parts (services, queues, datastores, IAM policies). Each one needs a line item justifying its existence against requirement 1.

## Findings Format

`[Severity] [Area] Statement → Evidence → Recommendation → Alternative considered → Verification`

Example: `[HIGH][Data] "User search will do full-table LIKE scans" → docs §3, no index → add trigram index + query budget; alternative: external search service rejected as premature → EXPLAIN test in CI`.

## Verdict

- **APPROVE** — questions answered; risks documented and owned.
- **APPROVE WITH CONDITIONS** — list them; conditions are merge-blocking; re-review on completion.
- **REJECT** — simplest-sufficient requirement violated, or an unaddressable risk named; propose the simpler alternative explicitly.

## Reviewer Ethics

Attack the design, not the designer. Every concern pairs with either a fix or an accepted-risk note. If you don't understand something, say so — that's usually a documentation bug, which is a finding.
