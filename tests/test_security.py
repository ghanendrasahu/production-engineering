"""Security-specific repository checks.

These tests enforce the repo's security invariants so they cannot regress
silently: no tracked file may carry a credential-like pattern or a
machine-local path, CI must stay least-privilege, and core policy files must
exist.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

TRACKED = subprocess.check_output(["git", "ls-files"], cwd=REPO, text=True).splitlines()
TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".yml",
    ".yaml",
    ".txt",
    ".toml",
    ".json",
    ".cff",
    ".example",
    ".editorconfig",
}

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gho_[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)postgres(ql)?://[^:\s/'\"]+:[^@\s/'\"]+@"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
]


def _fragments():
    # Built from parts so this test file never contains the literals itself.
    return [
        "C:" + "\\Users\\",
        "ALL" + " PROJECTS",
        "ghanendrasahu" + "2911",
        "/Users/" + "ghane",
    ]


FORBIDDEN_FRAGMENTS = _fragments()


def _tracked_text_files():
    for f in TRACKED:
        p = REPO / f
        if p.suffix.lower() in TEXT_SUFFIXES or p.name in {
            ".gitignore",
            ".gitattributes",
            "LICENSE",
        }:
            yield f, p.read_text(encoding="utf-8", errors="ignore")


@pytest.mark.parametrize("pattern", SECRET_PATTERNS, ids=lambda p: p.pattern[:40])
def test_no_secret_patterns(pattern):
    offenders = [f for f, text in _tracked_text_files() if pattern.search(text)]
    assert not offenders, f"secret-like pattern found in: {offenders}"


@pytest.mark.parametrize("fragment", FORBIDDEN_FRAGMENTS, ids=lambda s: s[:30])
def test_no_machine_local_fragments(fragment):
    offenders = [f for f, text in _tracked_text_files() if fragment in text]
    assert not offenders, f"machine-local fragment {fragment!r} found in: {offenders}"


def test_env_files_gitignored():
    gi = (REPO / ".gitignore").read_text(encoding="utf-8")
    for need in (".env", "*.pem", "*.key"):
        assert need in gi


def test_ci_workflow_least_privilege():
    wf = (REPO / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
    assert "contents: read" in wf, "workflow must declare least-privilege permissions"


def test_security_policy_present():
    assert (REPO / "SECURITY.md").exists()


def test_no_absolute_personal_paths_in_docs():
    for f, text in _tracked_text_files():
        if f.startswith("docs/") or f.endswith(".md"):
            assert "C:\\Users\\" not in text
            assert "/home/ghane" not in text
