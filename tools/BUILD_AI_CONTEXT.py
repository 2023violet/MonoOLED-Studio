"""Build a disposable, read-only AI navigation packet for this repository."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


class ContextBuildError(RuntimeError):
    """A user-actionable context build failure."""


def _run_git(repo_root: Path, *args: str, allow_failure: bool = False, strip_output: bool = True) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise ContextBuildError("Git is required but could not be started") from exc
    output = result.stdout.strip() if strip_output else result.stdout.rstrip("\r\n")
    if result.returncode and not allow_failure:
        detail = result.stderr.strip() or output or "unknown Git error"
        raise ContextBuildError(f"Git command failed: {detail}")
    return output


def _repo_root(requested: str | None) -> Path:
    candidate = Path(requested).expanduser().resolve() if requested else Path(__file__).resolve().parents[1]
    if not candidate.is_dir():
        raise ContextBuildError("Repository root does not exist")
    actual = _run_git(candidate, "rev-parse", "--show-toplevel")
    if not actual:
        raise ContextBuildError("The selected path is not a Git repository")
    root = Path(actual).resolve()
    if root != candidate:
        raise ContextBuildError("--repo-root must point to the repository root")
    return root


def _read_required(repo_root: Path, relative: str) -> str:
    path = repo_root / relative
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ContextBuildError(f"Required file is missing: {relative}") from exc
    except OSError as exc:
        raise ContextBuildError(f"Could not read required file: {relative}") from exc


def _state_value(text: str, label: str, default: str = "NONE") -> str:
    pattern = re.compile(rf"^\s*-\s*{re.escape(label)}\s*:\s*(.+?)\s*$", re.IGNORECASE)
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1).strip()
    return default


def _active_task_path(repo_root: Path, active_task: str) -> str:
    if active_task.upper() in {"NONE", "N/A", "NOT CONFIGURED"}:
        return "NONE"
    if not re.fullmatch(r"TASK-\d+", active_task, re.IGNORECASE):
        return "NONE"
    candidate = repo_root / ".ai" / "tasks" / f"{active_task}.md"
    return f".ai/tasks/{active_task}.md" if candidate.is_file() else "NONE"


def _decision_entries(text: str) -> list[str]:
    lines = text.splitlines()
    entries: list[str] = []
    for index, line in enumerate(lines):
        match = re.match(r"^##\s+(ADR-\d+)\s+[—-]\s+(.+?)\s*$", line)
        if not match:
            continue
        summary = ""
        for following in lines[index + 1 :]:
            if following.startswith("## "):
                break
            if following.strip():
                summary = re.sub(r"[`*]", "", following.strip())
                break
        summary = re.sub(r"\s+", " ", summary)
        if len(summary) > 120:
            summary = summary[:117].rstrip() + "..."
        entries.append(f"{match.group(1)} — {match.group(2)}" + (f": {summary}" if summary else ""))
    return entries


def _deferred_items(text: str) -> list[str]:
    lines = text.splitlines()
    found: list[str] = []
    for index, line in enumerate(lines):
        lowered = line.lower()
        if "deferred" not in lowered and "unresolved" not in lowered:
            continue
        start = index
        if not line.lstrip().startswith("-"):
            while start > 0 and not lines[start].lstrip().startswith("-"):
                start -= 1
        end = index + 1
        while end < len(lines) and lines[end].strip() and not lines[end].lstrip().startswith("-"):
            end += 1
        item = re.sub(r"\s+", " ", " ".join(part.strip() for part in lines[start:end]))
        if item not in found:
            found.append(item)
    return found


def _status_paths(repo_root: Path) -> tuple[list[str], list[str], list[str]]:
    raw = _run_git(repo_root, "status", "--porcelain=v1", strip_output=False)
    staged: list[str] = []
    modified: list[str] = []
    untracked: list[str] = []
    for line in raw.splitlines():
        if len(line) < 3:
            continue
        index_status, worktree_status = line[0], line[1]
        path = line[3:]
        if index_status == "?" and worktree_status == "?":
            untracked.append(path)
        else:
            if index_status not in {" ", "?"}:
                staged.append(path)
            if worktree_status not in {" ", "?"}:
                modified.append(path)
    return staged, modified, untracked


def _format_paths(paths: list[str]) -> str:
    return ", ".join(paths) if paths else "NONE"


def _build_context(repo_root: Path, recent: int) -> str:
    version = _read_required(repo_root, "src/VERSION").strip()
    if not version:
        raise ContextBuildError("Required file is empty: src/VERSION")
    state = _read_required(repo_root, ".ai/CURRENT_STATE.md")
    decisions = _read_required(repo_root, ".ai/DECISIONS.md")

    branch = _run_git(repo_root, "branch", "--show-current")
    if not branch:
        raise ContextBuildError("Detached HEAD is not supported for context generation")
    head = _run_git(repo_root, "rev-parse", "HEAD")
    upstream = _run_git(repo_root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", allow_failure=True)
    if upstream:
        counts = _run_git(repo_root, "rev-list", "--left-right", "--count", "@{upstream}...HEAD")
        parts = counts.split()
        if len(parts) != 2:
            raise ContextBuildError("Could not determine upstream ahead/behind state")
        behind, ahead = parts
        sync = f"behind {behind}, ahead {ahead}"
        remote = upstream.split("/", 1)[0] if "/" in upstream else upstream
    else:
        sync = "NOT CONFIGURED (no upstream)"
        remote = "NOT CONFIGURED"

    staged, modified, untracked = _status_paths(repo_root)
    commits = _run_git(repo_root, "log", "-n", str(recent), "--pretty=format:%h%x09%s").splitlines()
    active_task = _state_value(state, "Active task")
    lines = [
        "# GENERATED AI CONTEXT",
        "GENERATED FILE — DERIVED CONTEXT ONLY",
        "NOT AUTHORITATIVE",
        "REGENERATE BEFORE USE",
        "",
        "> Warning: live authoritative sources win if this generated packet conflicts with them.",
        "> This file is a navigation index, not a replacement for source files, tests, or TASK contracts.",
        "",
        "## Repository",
        f"- Project: {repo_root.name}",
        f"- Product version: {version}",
        "- Repository-relative context: .",
        "",
        "## Git snapshot",
        f"- Branch: {branch}",
        f"- HEAD: {head}",
        f"- Remote: {remote}",
        f"- Upstream: {upstream or 'NOT CONFIGURED'}",
        f"- Ahead / behind: {sync}",
        f"- Staged paths: {_format_paths(staged)}",
        f"- Modified tracked paths: {_format_paths(modified)}",
        f"- Untracked paths: {_format_paths(untracked)}",
        "",
        "## Workflow",
        f"- Current phase: {_state_value(state, 'Current phase')}",
        f"- Last completed workflow task: {_state_value(state, 'Last completed workflow task')}",
        f"- Active task: {active_task}",
        f"- Active TASK path: {_active_task_path(repo_root, active_task)}",
        f"- Independent Review: {_state_value(state, 'Independent Review')}",
        f"- Next workflow action: {_state_value(state, 'Next workflow action')}",
        "",
        "## Confirmed decisions",
    ]
    decisions_found = _decision_entries(decisions)
    lines.extend(f"- {entry}" for entry in decisions_found or ["NONE"])
    lines.extend(["", "## Deferred or unresolved issues"])
    deferred = _deferred_items(state)
    lines.extend(f"- {item.lstrip('- ').strip()}" for item in deferred or ["NONE explicitly recorded"])
    lines.extend(["", "## Recent commits"])
    lines.extend(f"- {entry}" for entry in commits or ["NONE"])
    lines.extend([
        "",
        "## Recommended next reads",
        "- AGENTS.md",
        "- .ai/README.md",
        "- .ai/DECISIONS.md",
        "- .ai/CURRENT_STATE.md",
        f"- {_active_task_path(repo_root, active_task)}" if _active_task_path(repo_root, active_task) != "NONE" else "- active TASK: NONE",
        "- docs/AI_HANDOFF.md",
        "- This generated context is an index; read live authoritative sources before important decisions.",
        "",
    ])
    return "\n".join(lines)


def _output_path(repo_root: Path, value: str) -> Path:
    candidate = (repo_root / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    try:
        candidate.relative_to(repo_root)
    except ValueError as exc:
        raise ContextBuildError("--output must remain inside the repository root") from exc
    if not candidate.parent.is_dir():
        raise ContextBuildError("Output directory does not exist")
    return candidate


def _write_atomic(path: Path, content: str) -> None:
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise ContextBuildError(f"Could not atomically write {path.name}") from exc
    finally:
        if temporary:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only derived AI context packet")
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument("--stdout", action="store_true", help="write the packet to stdout only")
    output_group.add_argument("--output", help="custom repository-relative output path")
    parser.add_argument("--recent", type=int, default=5, help="number of recent commits to include (1-20)")
    parser.add_argument("--repo-root", help="repository root for isolated validation")
    args = parser.parse_args(argv)
    if not 1 <= args.recent <= 20:
        parser.error("--recent must be between 1 and 20")
    try:
        root = _repo_root(args.repo_root)
        content = _build_context(root, args.recent)
        if args.stdout:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="strict", newline="\n")
            sys.stdout.write(content)
            return 0
        target = _output_path(root, args.output or ".ai/GENERATED_CONTEXT.md")
        _write_atomic(target, content)
        display = target.relative_to(root).as_posix()
        print(f"Wrote {display}")
        return 0
    except ContextBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
