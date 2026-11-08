# Contributing to Production Engineering Skills

Thank you for helping make production engineering knowledge accessible to every AI coding agent and every engineer. This repository is a community effort — beginners and experts are both welcome.

## Ground Rules

1. **Keep the 111-topic scope intact.** Do not remove, merge, rename, or renumber topics. New topics require an RFC-style proposal (see below).
2. **No placeholders.** Every document must stand alone. If you don't know the answer, research it, cite it, or leave a clearly marked `TODO(owner):` only in draft PRs — never in `main`.
3. **Accuracy over volume.** One precise, tested example beats ten vague paragraphs.
4. **No secrets, ever.** No API keys, tokens, real personal data, or private URLs in examples. Use obviously fake values (`sk_test_EXAMPLE`, `10.0.0.1`).
5. **Be kind.** Follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to Contribute

### Improve an existing topic doc

1. Fork the repo.
2. Branch: `git checkout -b improve/<topic-slug>`.
3. Edit `.agents/skills/production-engineering/topics/<NNN-slug>.md`.
4. Keep the required structure (see [Skill Architecture](docs/skill-architecture.md)): metadata frontmatter + all applicable sections.
5. If your change affects claims, update `COVERAGE`/topic index if applicable (`python scripts/generate_topic_index.py`).
6. Run validation locally (below).
7. Open a PR using the template.

### Report an error

Open a [Bug report](https://github.com/ghanendrasahu/production-engineering/issues/new?template=bug_report.md) with:

- The topic file and line, the incorrect claim, a source (RFC/docs/paper) showing correct behavior.

### Propose a new topic

Open a [New skill proposal](https://github.com/ghanendrasahu/production-engineering/issues/new?template=new_skill_proposal.md) answering:

- What problem does it solve? Where does it fit in the numbered scope (or is it out of scope)?
- Is it a duplicate of an existing topic? (We will usually point you there.)
- Who maintains it?

New topics go through review: proposal → discussion → design comment → PR. Expect feedback; it makes the library better.

### Add an example

Examples in `examples/` must be minimal, runnable, and real (a real FastAPI app, a real compose file). Include a README with exact commands to run.

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
