"""Structural tests for the skill library. Run with: pytest tests/ -q"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / ".agents" / "skills" / "production-engineering"


def test_skill_root_exists():
    assert SKILL.is_dir()


def test_skill_md_exists_with_frontmatter():
    skill = SKILL / "SKILL.md"
    assert skill.exists()
    text = skill.read_text(encoding="utf-8")
    assert re.match(r"^---\n.*?\n---\n", text, re.S)
    assert "name: production-engineering" in text
    assert "description:" in text


def test_required_directories_and_files():
    expected_dirs = ["topics", "references", "workflows", "templates"]
    for d in expected_dirs:
        assert (SKILL / d).is_dir(), f"missing dir: {d}"
    expected_references = {
        "architecture.md",
        "backend-engineering.md",
        "distributed-systems.md",
        "reliability.md",
        "security.md",
        "performance.md",
        "observability.md",
        "infrastructure.md",
        "deployment.md",
        "testing.md",
        "ai-engineering.md",
        "engineering-checklists.md",
        "database-engineering.md",
        "networking.md",
        "incident-management.md",
    }
    found = {p.name for p in (SKILL / "references").glob("*.md")}
    assert expected_references <= found, (
        f"missing references: {expected_references - found}"
    )
    workflows = {p.name for p in (SKILL / "workflows").glob("*.md")}
    assert len(workflows) == 6
    templates = {p.name for p in (SKILL / "templates").glob("*.md")}
    assert len(templates) == 4


def test_topics_directory_has_111_files():
    assert len(list((SKILL / "topics").glob("*.md"))) == 111


def test_docs_examples_scripts_present():
    for rel in ["docs/topic-index.md", "docs/installation.md", "docs/faq.md"]:
        assert (REPO / rel).exists()
    assert (REPO / "examples" / "fastapi" / "app.py").exists()
    assert (REPO / "scripts" / "validate_skills.py").exists()
    assert (REPO / "scripts" / "check_topic_coverage.py").exists()
    assert (REPO / "scripts" / "generate_topic_index.py").exists()
