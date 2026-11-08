# Localization (i18n) Investigation

Status: **investigated — not started** (tracked in issue #15)

## Options

| Option | Pros | Cons | Who drives it |
|---|---|---|---|
| Community translation PRs (per-topic `docs/i18n/<lang>/topics/…`) | Zero tooling; reviewable per topic; honest scope | No coverage guarantee; drift risk as topics evolve | Contributors (good first issue) |
| Crowdin (hosted) | Preview/review workflow per string; translation memory | Needs an account owner, ongoing sync overhead, strings are long Markdown — translation memory helps less than for UI strings | Maintainer (needs account) |
| Weblate (self-hosted) | Open source; great Git integration | Operational burden (another service to run, backup, secure) | Maintainer + infrastructure |
| Machine translation + human review | Fast first pass for 111 docs | Draft quality below repo's bar — violates "no placeholders" | Mixed; review required |

## Recommendation

Community PRs first (pt-BR, es, de, hi) + translation guide in `docs/` + CI check that translated topics stay within ±10% of English line count and keep the 24 sections. Crowdin only if demand materializes; Weblate not justified at current size. Terms of art (SLO, P99, DLQ, fencing, backpressure) stay English in all languages.

## What blocks starting

Nothing technical — only a volunteer to own the first translation (pt-BR). Watch issue #15 for the kickoff.
