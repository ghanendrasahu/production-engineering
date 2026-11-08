# Incident Management Reference

Running the response when production breaks: the incident itself, the humans on the hook, and what the organization learns.

| # | Concept | One-line use case |
|---|---|---|
| 109 | Production Incidents | Detect, mitigate, communicate, resolve |
| 110 | On-Call | Sustainable human response rotation |
| 111 | Postmortems | Blameless learning from failure |

### 109. Production Incidents

**Definition:** An unplanned degradation or outage of a production service requiring coordinated response; managed by severity, with roles (incident commander, comms, scribe) and a clock.

**Problem:** Unstructured response multiplies downtime, duplicates work, loses data (logs rotated), and burns trust; panic destroys information needed later.

**Internal Working:** Lifecycle: detection (alerts/users) → assess & declare (severity P1-P4) → assemble roles → mitigate first (roll back, flag off, failover — restore service, not root cause) → communicate (status page, stakeholders every 30min) → resolve → handoff to postmortem. Severity definitions: P1 = full outage/data risk, all hands, exec comms; P2 = major degradation, page team; P3 = minor, next business day; P4 = cosmetic backlog. Incident commander coordinates — single authority, not a committee. Scribe records timeline in real time (chat thread); every action timestamped; dashboards shared; mitigation chosen for speed, not elegance ("rollback now, fix later").

**Architecture:** PagerDuty/Opsgenie paging → dedicated incident channel (Slack/Teams) → status page → Zoom bridge for P1; tooling: incident.io, statuspage.

**Implementation:**

```
Incident response checklist:
□ Acknowledge page < 5min     □ Open incident channel
□ Assign IC + scribe          □ State severity (P1/P2)
□ Mitigate (rollback/flag)    □ Status page update every 30min
□ Confirm recovery signals    □ Hand off to on-call lead
```

**Production Example:** 02:14 P1: checkout 5xx 30%; IC declared, flagged `checkout_v2` OFF in 90 seconds → errors to 0.1%; comms tool updated; customers saw 6 minutes of degraded checkout, no data loss; 08:00 all-hands RCA started; suspected N+1 deploy; permanent fix + canary gate added next day.

**Failure Scenarios:** No IC (everyone debugging in parallel, nothing coordinated); mitigation by root-cause analysis instead of revert ("let me understand the bug first" while site is down); status page silence → support ticket storm; logs lost during incident (no archival); premature all-clear ("p99 back to normal" — but error budget is gone and root cause unknown); heroics instead of escalation; skipping the postmortem because "it's resolved".

**Best Practices:** Mitigate first, understand later; single IC; scribe timelines everything; status page + internal comms every 30min; severity matrix predefined; revert-by-default for deploy-linked incidents; never debug without a rollback ready; rotate ICs (no permanent heroes); blameless.

**Anti-Patterns:** Root-causing before restoring; two people "in charge"; silence externally; partial mitigations reported as fixed; incidents without declarations (below threshold but corrosive silent failures); P1 for everything (dilutes response).

**Trade-offs:** Performance (N/A); complexity (process discipline, tooling optional); cost (time); consistency (postmortems feed back into SLOs); maintainability (runbooks + drills).

**Testing:** Game days (simulated P1s); tabletop exercises; page-routing test; status page drill; MTTA/MTTR tracked per quarter.

**Related Concepts:** `#110 On-Call`, `#111 Postmortems`, `#53 Canary Releases`, `#55 Rollbacks`, `#108 Dependency Hell` (dependency incidents), `#65 Error Budgets`.

**Decision Criteria:** Use when: always — even trivial regressions deserve a severity call. Do not use when: local dev. Alternatives: n/a; severity-proportionate response scales to P3/P4 (fix async).

### 110. On-Call

**Definition:** A rotation of engineers responsible and empowered to respond to production alerts, escalate, and deploy mitigations — with compensation, tooling, and a humane load limit.

**Problem:** Without on-call, alerts page nobody and outages run until business hours; without humane on-call, you burn out your best engineers.

**Internal Working:** Rotation: weekly primary + secondary (escalation after 15min no-ack), handoff checklist (open incidents, silences in place, known fragile deploys, escalation contacts), compensation (pay or time off), actionable-alert policy (page only actionable P1/P2 — no CPU pages at 3am), follow-the-sun for global teams, load budgeting (≤ 1-2 pages per shift average — above that, fix the system, not the human). Tooling: PagerDuty/Opsgenie escalation policies, runbooks per alert, ChatOps for context gathering (deploys, recent PRs, dashboards), one-click rollback/flag access from the phone.

**Architecture:** PagerDuty/Opsgenie escalation policy -> primary/secondary rota -> runbook + ChatOps context (deploys, dashboards) -> optional one-click rollback/flag path; weekly handoff checklist governs continuity.

**Implementation:**

```
Escalation policy: primary (5min) → secondary (10min) → manager (15min)
Handoff: open incidents + silences expiry + pending deploys + known risks
Alert → runbook URL → steps → "if X, flip flag Y" one-click path
```

**Production Example:** Team of 8: weekly rota primary+secondary; 90-day metrics: 11 pages, 8 actionable, MTTA 4min, MTTR 18min; 3 noisy alerts identified and deleted; Q3 compensation: 8h time-off each on-call week; retention excellent; knowledge spread: no single person knows "the database thing".

**Failure Scenarios:** Always-on engineer burnout ("just one more page"); alert floods nobody reads; escalation to a manager who has no context; no compensation → attrition; on-call without authority to deploy mitigations ("I can't touch prod"); handoff omissions (silence expires mid-outage); hero mode: senior carries everything → SPOF knowledge; 24/7 single-timezone coverage for global product.

**Best Practices:** Page only actionable; ≤ 1-2 pages/shift target; comp time + cash; escalation policy; runbooks mandatory per alert; weekly handoff checklist; post-incident review each bad page (delete or fix it); shadowing for new members; follow-the-sun if possible; on-call health metric in engineering reviews; protect off-duty time (phone real silence).

**Anti-Patterns:** 24/7 solo on-call; pager as the monitoring solution; "you were on-call, so it's yours" culture; no comp; runbooks outdated; alerts with no owner; hero dependency; punitive response to incident mistakes (kills reporting).

**Trade-offs:** Performance (N/A); complexity (process + tooling); cost (comp ~10-15% of role); consistency (role clarity); maintainability (rotas documented; quarterly review).

**Testing:** Monthly alert-to-runbook walkthrough by a non-owning engineer; escalation drill; handoff audit; rotation load report (pages/shift); burnout survey per cycle.

**Related Concepts:** `#109 Production Incidents`, `#62 Alerts`, `#111 Postmortems`, `#63 SLOs`, `#65 Error Budgets`.

**Decision Criteria:** Use when: any production system with users — mandatory. Do not use when: pre-launch/internal throwaway. Alternatives: n/a — response capability is not optional; scope scales with system criticality.

### 111. Postmortems

**Definition:** A blameless, written analysis after an incident — timeline, root cause(s) (5 Whys / fishbone), contributing factors, impact quantification, and owned action items — distributed so the org learns instead of repeating.

**Problem:** Without postmortems, every incident is a fresh surprise; errors repeat; the same failure class hits different teams every quarter; nothing improves.

**Internal Working:** Blameless means the system failed, not the person — the goal is every future engineer succeeding. Structure: Summary (2 sentences) → Impact (users affected, minutes, $, SLO/budget consumed) → Timeline (timestamped from scribe) → Root cause + contributing factors (5 Whys) → What went well/poorly → Action items with owners and deadlines (SMART, tracked to closure — no "we'll add tests" without dates) → Lessons for other teams. Review in a blameless meeting; publish internally (many companies publish externally too). Track themes across incidents to find systemic gaps (missing tests, weak review, unclear ownership).

**Architecture:** Scribe artifacts (channel timeline) -> incident report -> blameless review -> action items (owners/dates) -> shared postmortem index feeds SLO review, runbook updates and error-budget policy.

**Implementation:**

```
Template (see templates/postmortem.md):
Summary | Impact (users, $, duration) | Timeline table
Root cause + contributing factors | What worked / didn't
Action items: owner + due date + tracking link
Follow-up review: 4 weeks later
```

**Production Example:** After the 2026 checkout outage: root cause = untested serialization path; contributing = no canary for checkout, alerting blindspot; actions: k6 regression gate (owner, done +1wk), checkout canary (done), provider status page subscription (done); published in engineering wiki; similar pattern caught in two other services the next month — zero incidents since.

**Failure Scenarios:** Blame creep (directly or by implication — "why did YOU merge this?") → next incident hidden; action items without owners/dates → nothing changes; postmortem skipped for "small" P2s (they teach most); timeline reconstructed from memory (inaccurate); no follow-up review (actions rot); postmortem written by the most-junior person; public status inconsistent with internal narrative.

**Best Practices:** Blameless language ("the deploy allowed a regression", never "X broke it"); written within 48h while memory fresh; impact quantified; 3-7 action items with owners + dates; follow-up review at 30 days; publish and socialize; track theme clusters quarterly; celebrate caught catches (near-misses count); leadership visibly doesn't punish.

**Anti-Patterns:** Blame; postmortem as ceremony with no tracked actions; restricted visibility (lessons locked in one team); action-item infinity (20 vague items, zero closed); skipping small incidents; defensive writing ("it wasn't our fault"); no verification the action items exist at follow-up.

**Trade-offs:** Performance (N/A); complexity (writing + meeting time); cost (2-4 engineer-hours per incident); consistency (template + review); maintainability (culture — requires sustained leadership reinforcement).

**Testing:** n/a — verification = action-item closure at follow-up review; cluster reviews theme effectiveness.

**Related Concepts:** `#109 Production Incidents`, `#110 On-Call`, `#62 Alerts`, `#63 SLOs`, `#66 Observability`, `#87 Chaos Engineering` (drills feed postmortems).

**Decision Criteria:** Use when: every P1/P2 incident — mandatory; near-misses recommended. Do not use when: n/a. Alternatives: incident review meetings (cheaper, weaker) — acceptable for P3/P4 only.

<!--END-->
