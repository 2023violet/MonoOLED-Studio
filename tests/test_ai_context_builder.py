from __future__ import annotations

import ast
from pathlib import Path
import os
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools" / "BUILD_AI_CONTEXT.py"


def _git(cwd: Path, *args: str) -> str:
    env = os.environ.copy()
    env.update(
        GIT_AUTHOR_NAME="Context Test",
        GIT_AUTHOR_EMAIL="context@example.invalid",
        GIT_COMMITTER_NAME="Context Test",
        GIT_COMMITTER_EMAIL="context@example.invalid",
    )
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, env=env, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _repo(tmp_path: Path, *, active_task: str = "TASK-003") -> Path:
    repo = tmp_path / "fixture"
    (repo / ".ai" / "tasks").mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "docs").mkdir()
    (repo / "src" / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (repo / "docs" / "AI_HANDOFF.md").write_text("# Handoff\n", encoding="utf-8")
    (repo / ".ai" / "CURRENT_STATE.md").write_text(
        "# Current State\n\n"
        "- Project: MonoOLED Studio\n"
        "- Product version: 1.2.3\n"
        "- Current phase: Phase 3 — Context Builder\n"
        "- Last completed workflow task: TASK-002\n"
        f"- Active task: {active_task}\n"
        "- Independent Review: PENDING\n"
        "- Next workflow action: Implement and independently review the minimal read-only Context Builder\n"
        "- Popup native mask remains a DEFERRED FOLLOW-UP CANDIDATE\n",
        encoding="utf-8",
    )
    (repo / ".ai" / "DECISIONS.md").write_text(
        "# Confirmed Decisions\n\n## ADR-004 — Preserve the runtime dark identifier\n\nProduct Decision B remains confirmed.\n",
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text(".ai/GENERATED_CONTEXT.md\n", encoding="utf-8")
    _git(repo, "init", "-b", "main")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture baseline")
    (repo / "second.txt").write_text("second\n", encoding="utf-8")
    _git(repo, "add", "second.txt")
    _git(repo, "commit", "-m", "second fixture commit")
    return repo


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUILDER), "--repo-root", str(repo), *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def test_basic_snapshot_has_version_branch_head_state_decision_and_recent_commit(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = _run(repo, "--stdout", "--recent", "1")
    assert result.returncode == 0, result.stderr
    assert "Product version: 1.2.3" in result.stdout
    assert "Branch: main" in result.stdout
    assert _git(repo, "rev-parse", "HEAD") in result.stdout
    assert "second fixture commit" in result.stdout
    assert "Active task: TASK-003" in result.stdout
    assert "ADR-004" in result.stdout
    assert "DEFERRED FOLLOW-UP CANDIDATE" in result.stdout


def test_status_classification_and_no_content_leakage(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "staged.txt").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "staged.txt")
    (repo / "second.txt").write_text("modified\n", encoding="utf-8")
    (repo / "secret.txt").write_text("UNIQUE_SECRET_MARKER\n", encoding="utf-8")
    (repo / ".env").write_text("PASSWORD=UNIQUE_ENV_MARKER\n", encoding="utf-8")
    result = _run(repo, "--stdout")
    assert result.returncode == 0, result.stderr
    assert "Staged paths: staged.txt" in result.stdout
    assert "Modified tracked paths: second.txt" in result.stdout
    assert ".env" in result.stdout and "secret.txt" in result.stdout
    assert "UNIQUE_SECRET_MARKER" not in result.stdout
    assert "UNIQUE_ENV_MARKER" not in result.stdout


def test_no_upstream_and_no_active_task_are_nonfatal(tmp_path: Path) -> None:
    repo = _repo(tmp_path, active_task="NONE")
    result = _run(repo, "--stdout")
    assert result.returncode == 0, result.stderr
    assert "Upstream: NOT CONFIGURED" in result.stdout
    assert "Ahead / behind: NOT CONFIGURED" in result.stdout
    assert "Active task: NONE" in result.stdout
    assert "active TASK: NONE" in result.stdout


def test_stdout_does_not_create_default_file_and_default_output_is_atomic(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = _run(repo, "--stdout")
    assert result.returncode == 0, result.stderr
    assert not (repo / ".ai" / "GENERATED_CONTEXT.md").exists()
    result = _run(repo)
    assert result.returncode == 0, result.stderr
    output = repo / ".ai" / "GENERATED_CONTEXT.md"
    assert output.is_file()
    assert output.read_text(encoding="utf-8").startswith("# GENERATED AI CONTEXT\n")


def test_custom_output_and_recent_bounds(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = _run(repo, "--output", "packet.md", "--recent", "2")
    assert result.returncode == 0, result.stderr
    assert (repo / "packet.md").is_file()
    assert not (repo / ".ai" / "GENERATED_CONTEXT.md").exists()
    invalid = _run(repo, "--stdout", "--recent", "21")
    assert invalid.returncode != 0
    assert "--recent must be between 1 and 20" in invalid.stderr


def test_required_source_and_detached_head_fail_without_traceback(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "src" / "VERSION").unlink()
    missing = _run(repo, "--stdout")
    assert missing.returncode != 0
    assert "Required file is missing: src/VERSION" in missing.stderr
    assert "Traceback" not in missing.stderr

    repo = _repo(tmp_path / "detached")
    _git(repo, "checkout", "--detach", "HEAD")
    detached = _run(repo, "--stdout")
    assert detached.returncode != 0
    assert "Detached HEAD is not supported" in detached.stderr
    assert "Traceback" not in detached.stderr


def test_sources_are_preserved_and_gitignore_contract_is_present() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".ai/GENERATED_CONTEXT.md" in gitignore
    for relative in ("AGENTS.md", ".ai/DECISIONS.md", ".ai/CURRENT_STATE.md"):
        assert (ROOT / relative).is_file()


def test_builder_has_no_network_or_external_dependencies() -> None:
    tree = ast.parse(BUILDER.read_text(encoding="utf-8"))
    imported = {
        node.names[0].name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for _ in [node]
    }
    imported.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert imported <= {"__future__", "argparse", "os", "pathlib", "re", "subprocess", "sys", "tempfile"}
    assert not {"requests", "httpx", "socket", "urllib"} & imported
