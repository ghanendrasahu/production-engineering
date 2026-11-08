## Type of change

- [ ] Topic doc fix / improvement (which: `topics/`)
- [ ] New topic / numbering change (must reference approved proposal)
- [ ] Scripts / CI / tooling
- [ ] Examples / docs / governance
- [ ] Release notes / changelog

## Description

What changed and why. Link the issue: `Fixes #N`.

## Checklist

- [ ] I ran `python scripts/validate_skills.py` — passes
- [ ] I ran `python scripts/check_topic_coverage.py` — 111/111
- [ ] I ran `pytest tests/ -q` — green
- [ ] I ran `python scripts/generate_topic_index.py --check` — no drift
- [ ] No secrets, tokens, real personal data, or private URLs added
- [ ] Facts/claims verified against authoritative sources and cited where non-obvious
- [ ] Internal relative links resolve (docs/, topics/, references/)
- [ ] Examples are runnable (if code added) and follow repo style
- [ ] CHANGELOG updated (if user-facing change in a release)

## Validation output

Paste the tail of the validation run.
