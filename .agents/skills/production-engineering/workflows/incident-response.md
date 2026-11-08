# Workflow — Incident Response

For when production is on fire. Print this; follow it top to bottom.

## Declare (first 2 minutes)

- Severity: **P1** full outage/data loss · **P2** major degradation · **P3** minor · **P4** backlog.
- Open incident channel (`#inc-YYYYMMDD-slug`). Assign **Incident Commander**, **Comms**, **Scribe**. IC has final call authority.
- Scribe timeline starts now: every action + timestamp, posted in channel.

## Mitigate First — Understand Later

Pick the fastest reversible lever, in order of reliability:
1. **Redeploy/revert** — `kubectl rollout undo`, `helm rollback`, previous artifact digest (`#55`)
2. **Flag off** — flip the kill switch (`#51`)
3. **Failover** — DB promote, traffic switch to standby/other region (`#85`, `#86`)
4. **Shed** — rate-limit/503 non-critical traffic; scale up if capacity is the constraint
5. **Route around** — disable the broken feature; serve cached/static fallback

Execution: 2 minutes to watch metrics after any lever — 5xx flat/declining and p99 recovering ⇒ keep; otherwise revert the lever and try the next.

## Communicate (every 30 minutes, always)

- Status page: what's broken, impact, next update time. Internal channel: hypothesis, actions, blockers. Leadership: P1 ⇒ immediate Heads-up; budget burn charged to the SLO (`#65`).

## Stabilize & Watch

- Confirm recovery on metrics AND user signals (checkout success, delivery successes), not just HTTP 200s.
- Hold a 60-minute watch window post-mitigation; expect rebound (cache refill, retry storms, cron overlap).
- Capture logs/traces/metrics snapshots before any retention rotates them (`#59`, `#60`).

## Hand Off & Learn (within 24h)

- Declare all-clear explicitly; remove temporary mitigations only with IC sign-off.
- Write the incident report within 4h (`../templates/incident-report.md`), postmortem within 48h (`#111`): blameless, timeline, contributing factors, owned action items with dates.
- Freeze deploys until riskiest action items are scheduled; error-budget policy applied.
- Feed the theme back into tests, alerts, runbooks, and ADRs; re-drill the failure quarterly (`#87`).

## Never Do

- Root-cause analysis instead of mitigation while prod is down.
- Deploy unreviewed fixes mid-P1 (revert only).
- Heroics in isolation — ping the second responder now.
- Silence after resolution — publish the postmortem.
