from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from automation_service import StudioAutomationService
from agent_bridge import dispatch_json_rpc
from project_workspace import ProjectWorkspace, create_project
from scene import load_scene


SCHEMA = {
    "variables": {
        "page": {"type": "enum", "values": ["HOME", "SETTINGS"], "init": "HOME"},
        "channel": {"type": "int", "min": 1, "max": 4, "init": 2},
        "level": {"type": "int", "values": [0, 25, 50, 75, 100], "init": 50},
        "alarm": {"type": "enum", "values": ["OFF", "ON"], "init": "OFF"},
    },
    "relations": [],
}


def _service(project: ProjectWorkspace, screen_id: str) -> StudioAutomationService:
    path = project.screen_path(screen_id)
    scene = load_scene(path, project_root=project.root)
    scene["_project_path"] = str(project.path)
    scene["_asset_dirs"] = list(project.asset_dirs)
    return StudioAutomationService(
        scene,
        source_path=path,
        permission="full",
        copy_scene=False,
        project_workspace=project,
    )


class Recorder:
    def __init__(self, service: StudioAutomationService):
        self.service = service
        self.steps: list[dict] = []

    def call(self, method: str, params: dict | None = None, **kwargs):
        started = time.perf_counter()
        try:
            result = self.service.call(method, params or {}, **kwargs)
        except Exception as exc:
            self.steps.append(
                {
                    "method": method,
                    "status": "blocked_api_step",
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "revision": self.service.revision,
                    "active_screen": self.service.project.active_screen if self.service.project else None,
                    "error": {"code": type(exc).__name__, "message": str(exc)},
                }
            )
            raise
        self.steps.append(
            {
                "method": method,
                "status": "observed_pass",
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "revision": self.service.revision,
                "active_screen": self.service.project.active_screen if self.service.project else None,
                "result": _result_summary(result),
            }
        )
        return result

    def bridge_call(self, method: str, params: dict | None = None):
        started = time.perf_counter()
        response = dispatch_json_rpc(
            self.service,
            {"jsonrpc": "2.0", "id": len(self.steps) + 1, "method": method, "params": params or {}},
        )
        if "error" in response:
            error = response["error"]
            self.steps.append(
                {
                    "method": method,
                    "status": "blocked_api_step",
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "revision": self.service.revision,
                    "active_screen": self.service.project.active_screen if self.service.project else None,
                    "error": error,
                }
            )
            raise ValueError(error["message"])
        result = response["result"]
        self.steps.append(
            {
                "method": method,
                "status": "observed_pass",
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "revision": self.service.revision,
                "active_screen": self.service.project.active_screen if self.service.project else None,
                "result": _result_summary(result),
            }
        )
        return result


def _result_summary(result: dict) -> dict:
    kept = {}
    for key in ("api_version", "cases", "frame_count", "framebuffer_bytes", "blockers", "valid", "sha256", "path", "state"):
        if key in result:
            kept[key] = result[key]
    return kept


def _configure_screen(recorder: Recorder, screen_id: str, x: int, create_resources: bool) -> None:
    recorder.call("project.open_screen", {"screen_id": screen_id, "save_current": True})
    checked = recorder.call("state.validate_schema", {"schema": SCHEMA})
    if not checked["valid"]:
        raise AssertionError(checked["errors"])
    recorder.call("state.set_schema", {"schema": SCHEMA}, expected_revision=recorder.service.revision)
    if create_resources:
        font = recorder.call(
            "font.create_pack",
            {"path": "fonts/generic", "name": "Generic 5x8", "cell": [5, 8], "baseline": 7, "advance": 6},
        )
        recorder.call("font.generate_glyphs", {"font_id": font["font_id"], "characters": "HOMESETTINGSOFN"})
        recorder.call("font.set_metrics", {"font_id": font["font_id"], "baseline": 7, "advance": 6})
        bitmap = recorder.call("pixel.create", {"path": "assets/generic_marker.png", "width": 8, "height": 8})
        recorder.call("pixel.paint", {"document_id": bitmap["document_id"], "x": 1, "y": 1, "value": 1})
        recorder.call("pixel.save", {"document_id": bitmap["document_id"]})
    tx = recorder.bridge_call("history.begin_transaction", {"_expected_revision": recorder.service.revision})["transaction"]
    recorder.bridge_call(
        "scene.create_element",
        {"_transaction": tx, "element": {"id": f"{screen_id}_label", "type": "bitmap_text", "text": "{page}", "font_pack": "fonts/generic", "x": x, "y": 2}},
    )
    recorder.bridge_call(
        "scene.create_element",
        {"_transaction": tx, "element": {"id": f"{screen_id}_marker", "type": "image", "asset": "assets/generic_marker.png", "x": x, "y": 20, "w": 8, "h": 8}},
    )
    recorder.bridge_call("history.commit", {"transaction": tx})
    recorder.call("project.save_all")


def _wait_job(recorder: Recorder, job_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = recorder.call("job.status", {"job_id": job_id})
        if result["state"] in {"completed", "failed", "cancelled"}:
            return result
        time.sleep(0.01)
    raise TimeoutError(f"job did not reach terminal state: {job_id}")


def _write_reports(result: dict, evidence_dir: Path) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    json_path = evidence_dir / "v9_phase3_generic_graduation.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# V9 Phase 3 Generic Automation Graduation",
        "",
        f"- Phase 3 GA Release Gates = {result['gate']}",
        f"- Known blockers = {result['known_blockers']}",
        f"- Known P0/P1 = {result['known_p0_p1']}",
        f"- Evidence confidence = {result['evidence_confidence']}",
        f"- Windows Real-Qt deep validation = {result['windows_real_qt']}",
        "",
        "| Step | Status | Duration ms |",
        "| --- | --- | ---: |",
    ]
    lines.extend(f"| `{step['method']}` | {step['status']} | {step['duration_ms']} |" for step in result["steps"])
    (evidence_dir / "v9_phase3_generic_graduation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_graduation(project_root: str | Path, evidence_dir: str | Path) -> dict:
    project_root = Path(project_root).resolve()
    evidence_dir = Path(evidence_dir).resolve()
    project = create_project(project_root, name="Generic Automation Graduation", canvas=(128, 32))
    recorder = Recorder(_service(project, "main"))
    try:
        capabilities = recorder.call("automation.capabilities")
        if capabilities["api_version"] != "1.2.0" or len(capabilities["methods"]) != 84:
            raise AssertionError("Automation API identity changed")
        recorder.call("project.rename_screen", {"screen_id": "main", "new_id": "generic_status", "label": "Generic Status"})
        recorder.call("project.create_screen", {"screen_id": "generic_detail", "label": "Generic Detail"})
        _configure_screen(recorder, "generic_status", 8, True)
        _configure_screen(recorder, "generic_detail", 64, False)
        for screen_id in ("generic_status", "generic_detail"):
            recorder.call("project.open_screen", {"screen_id": screen_id, "save_current": True})
            count = recorder.call("state.count", {"integer_policy": "representative"})
            rendered = recorder.call("render.all_states", {"integer_policy": "representative", "summary_only": True})
            validated = recorder.call("validate.all_states", {"integer_policy": "representative", "summary_only": True})
            if count["cases"] != 80 or rendered["cases"] != 80 or validated["blockers"] != 0:
                raise AssertionError(f"unexpected matrix result for {screen_id}")
            recorder.call("export.all", {"output_dir": f"exports/{screen_id}", "integer_policy": "representative", "summary_only": True})
            recorder.call("export.code_ai_handoff", {"path": f"exports/{screen_id}.zip", "integer_policy": "representative", "summary_only": True})
        started = recorder.call(
            "job.start",
            {"operation": "render.all_states", "arguments": {"integer_policy": "representative", "summary_only": True}},
        )
        terminal = _wait_job(recorder, started["job_id"])
        if terminal["state"] != "completed":
            raise AssertionError(terminal)
        recorder.call("job.result", {"job_id": started["job_id"]})
        recorder.call("project.save_all")
        reopened = ProjectWorkspace.load(project.path)
        reopened_recorder = Recorder(_service(reopened, "generic_status"))
        reopened_recorder.call("state.get_schema")
        reopened_recorder.call("render.framebuffer")
        reopened_recorder.call("validate.all_states", {"integer_policy": "representative", "summary_only": True})
        recorder.steps.extend(reopened_recorder.steps)
    except Exception:
        result = {
            "phase": "V9 Phase 3",
            "gate": "FAIL",
            "known_blockers": sum(step["status"] == "blocked_api_step" for step in recorder.steps),
            "known_p0_p1": 0,
            "evidence_confidence": "Low",
            "windows_real_qt": "Not rerun (no trigger)",
            "steps": recorder.steps,
        }
        _write_reports(result, evidence_dir)
        raise
    result = {
        "phase": "V9 Phase 3",
        "gate": "PASS",
        "known_blockers": 0,
        "known_p0_p1": 0,
        "evidence_confidence": "High",
        "windows_real_qt": "Not rerun (no trigger)",
        "project_manifest_sha256": hashlib.sha256(project.path.read_bytes()).hexdigest(),
        "steps": recorder.steps,
    }
    _write_reports(result, evidence_dir)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the V9 Phase 3 Generic Automation Graduation")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--evidence-dir", required=True)
    args = parser.parse_args()
    result = run_graduation(args.project_root, args.evidence_dir)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
