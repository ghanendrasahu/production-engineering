---
name: architecture-decision-record
title: Architecture Decision Record
---

# ADR-XXXX: <short title>

**Date:** YYYY-MM-DD · **Status:** proposed | accepted | superseded by ADR-YYY · **Deciders:** team/names

## Context

The problem, the constraints with numbers (traffic, data, latency, team, budget, compliance), and the consequences of the status quo. 3–8 sentences.

## Decision

What we chose, in one paragraph. What we explicitly reject, in one sentence each.

## Decision Criteria Classification (from the 111-topic framework)

For each load-bearing concept: CRITICAL / HIGH / MEDIUM / NOT APPLICABLE with one-line reasoning tied to requirements.

## Alternatives Considered

| Option | Trade-offs (perf / complexity / cost / consistency / ops) | Why rejected |
| --- | --- | --- |
| A | | |
| B | | |
| C (do nothing) | | |

## Consequences

**Positive:** … · **Negative/risks:** … · **Reversibility:** how hard to undo if wrong.

## Verification Plan

How we'll know it was right: metric, threshold, date (e.g., "p99 < 250ms at 3x current RPS by 2026-12-01"). Review date to revisit.

## Links

Design doc · related topics · incidents that motivated this · implementation PRs.
