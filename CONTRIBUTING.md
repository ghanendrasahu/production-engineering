# Contributing to Production Engineering Skills

Thank you for helping make production engineering knowledge accessible to every AI coding agent and every engineer. This repository is a community effort — beginners and experts are both welcome.

## Ground Rules

1. **Keep the 111-topic scope intact.** Do not remove, merge, rename, or renumber topics. New topics require an RFC-style proposal (see below).
2. **No placeholders.** Every document must stand alone. If you don't know the answer, research it, cite it, or leave a clearly marked `TODO(owner):` only in draft PRs — never in `main`.
3. **Accuracy over volume.** One precise, tested example beats ten vague paragraphs.
4. **No secrets, ever.** No API keys, tokens, real personal data, or private URLs in examples. Use obviously fake values (`sk_test_EXAMPLE`, `10.0.0.1`).
5. **Be kind.** Follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to Contribute

Pick a category — each maps to a label on our issue tracker:

| Category | What it means | Label |
|---|---|---|
| **Documentation corrections** | Fix wrong/outdated claims in any topic or doc, with sources | `documentation` |
| **New production engineering topics** | 112+ via proposal only — numbering is forever | `proposal` |
| **Runnable examples** | Real, tested examples (FastAPI, Postgres, Kafka, LLM pipelines) | `enhancement` |
| **Testing improvements** | Validation scripts, CI gates, failure-path tests | `testing` |
| **Agent compatibility** | Verify/adapt the skill for OpenCode, Claude Code, Cursor, Codex | `compatibility` |
| **Real-world production case studies** | Anonymized incident/migration/scale stories for docs | `documentation` |

Good entry points are labeled `good first issue`. Larger projects are labeled `help wanted`. Check the [issue list](https://github.com/ghanendrasahu/production-engineering/issues).

### Documentation Corrections

1. Fork the repo.
2. Branch: `git checkout -b fix/<topic-slug>`.
3. Edit the topic file under `topics/`.
4. Cite your source (RFC, official docs, paper) in the PR.
5. Run the validation commands below; open a PR.

### New production engineering topics

Open a [New skill proposal](https://github.com/ghanendrasahu/production-engineering/issues/new?template=new_skill_proposal.md) first — no surprise renumbers. Accepted proposals are implemented as 112+.

### Runnable examples

Examples must be minimal, runnable, and real — an actual app with actual commands. Include a README with exact steps and expected output.

### Testing improvements

Extend `tests/` or `scripts/`; keep runtime under ~5 seconds; never delete coverage to make CI pass.

### Agent compatibility

Test the skill against your agent; report findings as issues with your agent's version and the 3 prompts you tried. PRs welcome for manifest/setup changes that keep the library agent-independent.

### Production case studies

Anonymize fully (rename services, scrub tenants). Submit as a Discussion first — we decide placement together.

### Anything else

See [SUPPORT.md](SUPPORT.md) for where to ask what.

## Local Validation (required before PR)

```bash
pip install pytest
python scripts/check_topic_coverage.py     # 111 topics present, numbering 1..111, no duplicates
python scripts/validate_skills.py          # frontmatter, sections, links, fences, no secrets
python tests/test_skill_structure.py 2>/dev/null || pytest tests/ -v
python scripts/generate_topic_index.py --check
```

All checks must pass. CI runs the same on every PR.

## Style Guide

- Markdown with ATX headings (`#`), reference-style links where URLs are long.
- Code fences with language tags (`python`, `yaml`, `bash`, `sql`).
- Sentence case headings; one sentence per line is fine.
- Numbers must be stated as numbers (`99.9%`, `43.8 min per 30d`), never "very".
- Absolute claims ("always", "never") require a cited source or are reworded.

## Review Process

- One approving review from the maintainer (or two for scope changes).
- CI must be green.
- Squash merge preferred; commit messages use [Conventional Commits](https://www.conventionalcommits.org/) (`docs(retries): clarify jitter math`).

## Recognition

Contributors are listed in [README.md](README.md#acknowledgements) and release notes. Solid, repeated, accurate contributions may earn maintainership — ask.

## Questions?

[Discussions](https://github.com/ghanendrasahu/production-engineering/discussions) is the right place. Thank you for contributing.
