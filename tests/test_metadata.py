"""Metadata and content integrity tests for every topic document."""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOPICS = REPO / ".agents" / "skills" / "production-engineering" / "topics"

REQUIRED_SECTIONS = [
    "## 1. Topic name and metadata",
    "## 2. What it is",
    "## 3. Why it exists",
    "## 5. How it works internally",
    "## 7. When to use it",
    "## 8. When NOT to use it",
    "## 9. Implementation strategies",
    "## 10. Production-grade implementation",
    "## 12. FastAPI integration where relevant",
    "## 17. Common mistakes",
    "## 18. Anti-patterns",
    "## 19. Monitoring and observability",
    "## 20. Testing strategies",
    "## 22. Production-readiness checklist",
    "## 23. Troubleshooting guide",
    "## 24. Further reading and authoritative references",
]

FORBIDDEN = re.compile(r"\b(TODO|TBD|FIXME|lorem ipsum)\b", re.I)


def _topic_files():
    return list(TOPICS.glob("[0-9][0-9][0-9]-*.md"))


def test_all_topics_have_frontmatter():
    for f in _topic_files():
        text = f.read_text(encoding="utf-8")
        assert text.startswith("---\n"), f"{f.name}: missing frontmatter"
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        assert m, f"{f.name}: malformed frontmatter"
        for key in ("topic:", "title:", "category:", "skill:"):
            assert key in m.group(1), f"{f.name}: frontmatter missing {key}"


def test_frontmatter_number_matches_filename():
    for f in _topic_files():
        n = int(re.match(r"(\d+)-", f.name).group(1))
        text = f.read_text(encoding="utf-8")
        assert f"topic: {n}\n" in text or f"topic: {n}\r\n" in text, (
            f"{f.name}: topic field != filename"
        )


@pytest.mark.parametrize("f", _topic_files(), ids=lambda f: f.name)
def test_required_sections_present(f):
    text = f.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        assert section in text, f"{f.name}: missing '{section}'"


@pytest.mark.parametrize("f", _topic_files(), ids=lambda f: f.name)
def test_code_fences_balanced(f):
    assert f.read_text(encoding="utf-8").count("```") % 2 == 0, (
        f"{f.name}: unbalanced code fences"
    )


@pytest.mark.parametrize("f", _topic_files(), ids=lambda f: f.name)
def test_no_placeholder_text(f):
    assert not FORBIDDEN.search(f.read_text(encoding="utf-8")), (
        f"{f.name}: placeholder found"
    )


def test_all_topics_reference_their_reference_file():
    for f in _topic_files():
        text = f.read_text(encoding="utf-8")
        assert "../references/" in text, f"{f.name}: missing deep-reference link"
