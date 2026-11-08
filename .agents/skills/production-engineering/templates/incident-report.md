---
name: incident-report
title: Incident Report
---

# INC-<YYYYMMDD>-<NNN> — <short description>

**Severity:** P1/P2/P3 · **Detected:** timestamp (alert | user | report) · **Mitigated:** timestamp · **Resolved:** timestamp · **Duration:** Xm
**Services:** ... · **IC:** ... · **Scribe:** ...

## Summary

Two sentences a non-engineer can repeat verbatim: what broke, who was affected, what fixed it.

## Impact

Users affected: N · Error rate at peak: % · Requests failed: N · Data integrity: none | reconciled | under review · SLO budget consumed: X min · Financial: $ (if known)

## Timeline (UTC, from scribe in-channel)

| Time | Event | Source |
| --- | --- | --- |
| 14:02 | alert `ErrorBudgetBurnFast` pages | alertmanager |
| 14:06 | IC declares P1; flag `checkout_v2` suspected | channel |
| 14:08 | kill switch OFF; error rate → 0.3% | flag console |
| 14:15 | confirmed stable; all-clear posted | channel |

## Mitigation Applied (exact commands / flips)

- `kubectl rollout undo deploy/checkout  # or flag OFF  # or failover`
- Verification steps that confirmed recovery.

## What Went Well / Poorly

- Well: … (fast detection, clean rollback, clear comms)
- Poorly: … (gap in this section feeds the postmortem)

## Immediate Follow-ups

- [ ] Draft postmortem within 48h (`#111`) — owner: ___
- [ ] Error budget charged; deploy freeze decision: (yes/no, why)
- [ ] Logs/traces preserved for the window; retention extended

**Full postmortem required for P1/P2.** This report is the seed; it is not the learning document.
