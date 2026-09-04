from __future__ import annotations

import hashlib
import base64
from io import BytesIO
import sys
import time
from pathlib import Path

import pytest
from PIL import Image

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from automation_service import StudioAutomationService, UnsavedChangesError
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


REQUIRED_METHODS = {
    "project.create_screen",
    "project.open_screen",
    "project.save_all",
    "state.get_schema",
    "state.validate_schema",
    "state.set_schema",
    "state.enumerate",
    "state.count",
    "scene.create_element",
    "scene.update_element",
    "font.create_pack",
    "font.generate_glyphs",
    "font.get_pack",
    "font.get_glyph",
    "font.set_metrics",
    "pixel.create",
    "pixel.paint",
    "pixel.save",
    "render.current",
    "render.framebuffer",
    "render.png",
    "render.all_states",
    "validate.current",
    "validate.all_states",
    "export.all",
    "export.code_ai_handoff",
    "job.start",
    "job.status",
    "job.result",
    "job.cancel",
}


def _service(tmp_path: Path):
    project = create_project(tmp_path / "generic", name="Generic Automation Graduation", canvas=(128, 32))
    scene_path = project.screen_path("main")
    scene = load_scene(scene_path, project_root=project.root)
    scene["_project_path"] = str(project.path)
    scene["_asset_dirs"] = list(project.asset_dirs)
    service = StudioAutomationService(
        scene,
        source_path=scene_path,
        permission="full",
        copy_scene=False,
        project_workspace=project,
    )
    service.call("project.rename_screen", {"screen_id": "main", "new_id": "generic_status", "label": "Generic Status"})
    service.call("project.create_screen", {"screen_id": "generic_detail", "label": "Generic Detail", "open": True})
    service.call("project.open_screen", {"screen_id": "generic_status", "discard_current": True})
    return project, service


def _bridge_call(service: StudioAutomationService, method: str, params: dict | None = None):
    response = dispatch_json_rpc(service, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
    if "error" in response:
        raise ValueError(response["error"]["message"])
    return response["result"]


def _configure_screen(service: StudioAutomationService, screen_id: str, *, x: int, create_resources: bool):
    service.call("project.open_screen", {"screen_id": screen_id, "save_current": True})
    checked = service.call("state.validate_schema", {"schema": SCHEMA})
    assert checked["valid"] is True
    service.call("state.set_schema", {"schema": SCHEMA})
    if create_resources:
        font = service.call(
            "font.create_pack",
            {"path": "fonts/generic", "name": "Generic 5x8", "cell": [5, 8], "baseline": 7, "advance": 6},
        )
        font_id = font["font_id"]
        service.call("font.generate_glyphs", {"font_id": font_id, "characters": "HOMESETTINGSOFN"})
        service.call("font.set_metrics", {"font_id": font_id, "baseline": 7, "advance": 6})
        bitmap = service.call("pixel.create", {"path": "assets/generic_marker.png", "width": 8, "height": 8})
        service.call("pixel.paint", {"document_id": bitmap["document_id"], "x": 1, "y": 1, "value": 1})
        service.call("pixel.save", {"document_id": bitmap["document_id"]})
    else:
        font_id = "fonts/generic"
    tx = _bridge_call(service, "history.begin_transaction", {"_expected_revision": service.revision})["transaction"]
    _bridge_call(service,
        "scene.create_element",
        {"_transaction": tx, "element": {"id": f"{screen_id}_label", "type": "bitmap_text", "text": "{page}", "font_pack": font_id, "x": x, "y": 2}},
    )
    _bridge_call(service,
        "scene.create_element",
        {"_transaction": tx, "element": {"id": f"{screen_id}_marker", "type": "image", "asset": "assets/generic_marker.png", "x": x, "y": 20, "w": 8, "h": 8}},
    )
    _bridge_call(service, "history.commit", {"transaction": tx})
    service.call("project.save_all", {})


def _wait_job(service: StudioAutomationService, job_id: str, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = service.call("job.status", {"job_id": job_id})
        if status["state"] in {"completed", "failed", "cancelled"}:
            return status
        time.sleep(0.01)
    raise AssertionError(f"job did not reach terminal state: {job_id}")


def test_generic_api_capabilities_are_discoverable_and_stable(tmp_path):
    _, service = _service(tmp_path)
    capabilities = service.call("automation.capabilities", {})
    assert capabilities["api_version"] == "1.3.0"
    methods = {item["method"] for item in capabilities["methods"]}
    assert len(methods) == 92
    assert REQUIRED_METHODS <= methods
    for method in REQUIRED_METHODS:
        description = service.call("automation.describe_method", {"method": method})
        assert description["method"]["method"] == method


def test_generic_two_screen_api_only_graduation_and_reopen(tmp_path):
    project, service = _service(tmp_path)
    _configure_screen(service, "generic_status", x=8, create_resources=True)
    _configure_screen(service, "generic_detail", x=64, create_resources=False)

    service.call("project.open_screen", {"screen_id": "generic_status", "save_current": True})
    representative = service.call("state.enumerate", {"integer_policy": "representative", "include_states": True})
    assert representative["cases"] == 80
    assert list(representative["states"][0]) == ["page", "channel", "level", "alarm"]
    assert service.call("state.count", {"integer_policy": "representative"})["cases"] == 80
    assert service.call("state.enumerate", {"integer_policy": "full", "summary_only": True})["cases"] == 80
    assert service.call("validate.all_states", {"integer_policy": "representative"})["blockers"] == 0
    rendered = service.call("render.all_states", {"integer_policy": "representative", "summary_only": True})
    assert rendered["cases"] == 80 and rendered["framebuffer_bytes"] == 512

    current = service.call("render.current", {})
    assert current["framebuffer"]["bytes"] == 512
    png = service.call("render.png", {})
    image = Image.open(BytesIO(base64.b64decode(png["png_base64"])))
    assert png["width"] == 128 and png["height"] == 32 and image.mode == "1"

    export_a = service.call("export.all", {"output_dir": "exports/status_a", "integer_policy": "representative"})
    export_b = service.call("export.all", {"output_dir": "exports/status_b", "integer_policy": "representative"})
    assert export_a["frame_count"] == export_b["frame_count"] == 80
    assert export_a["frame_hashes"] == export_b["frame_hashes"]
    handoff = service.call("export.code_ai_handoff", {"path": "exports/status_handoff.zip", "integer_policy": "representative"})
    assert Path(handoff["path"]).exists()
    handoff_repeat = service.call("export.code_ai_handoff", {"path": "exports/status_handoff_repeat.zip", "integer_policy": "representative"})
    assert Path(handoff["path"]).read_bytes() == Path(handoff_repeat["path"]).read_bytes()

    job = service.call("job.start", {"operation": "render.all_states", "arguments": {"integer_policy": "representative", "summary_only": True}})
    status = _wait_job(service, job["job_id"])
    assert status["state"] == "completed"
    assert service.call("job.result", {"job_id": job["job_id"]})["result"]["cases"] == 80

    service.call("scene.update_element", {"id": "generic_status_label", "changes": {"x": 9}})
    with pytest.raises(UnsavedChangesError, match="UNSAVED_CHANGES"):
        service.call("project.open_screen", {"screen_id": "generic_detail"})
    service.call("project.open_screen", {"screen_id": "generic_detail", "save_current": True})
    service.call("project.save_all", {})

    reopened = ProjectWorkspace.load(project.path)
    assert {screen.id for screen in reopened.screens} == {"generic_status", "generic_detail"}
    reopened_path = reopened.screen_path("generic_status")
    reopened_scene = load_scene(reopened_path, project_root=reopened.root)
    reopened_scene["_project_path"] = str(reopened.path)
    reopened_scene["_asset_dirs"] = list(reopened.asset_dirs)
    reopened_service = StudioAutomationService(
        reopened_scene,
        source_path=reopened_path,
        permission="full",
        copy_scene=False,
        project_workspace=reopened,
    )
    assert reopened_service.call("state.get_schema", {})["schema"]["variables"] == SCHEMA["variables"]
    assert {element["id"] for element in reopened_service.call("scene.list_elements", {})["elements"]} >= {
        "generic_status_label",
        "generic_status_marker",
    }

    service.call("project.open_screen", {"screen_id": "generic_status", "save_current": True})
    before = service.call("export.all", {"output_dir": "exports/reopen_a", "integer_policy": "representative"})
    after = reopened_service.call("export.all", {"output_dir": "exports/reopen_b", "integer_policy": "representative"})
    assert before["frame_hashes"] == after["frame_hashes"]
    assert hashlib.sha256(Path(handoff["path"]).read_bytes()).hexdigest() == handoff["sha256"]


def test_generic_unsaved_policy_and_job_cancel_are_explicit(tmp_path):
    _, service = _service(tmp_path)
    _configure_screen(service, "generic_status", x=8, create_resources=True)
    _configure_screen(service, "generic_detail", x=64, create_resources=False)
    service.call("project.open_screen", {"screen_id": "generic_status", "save_current": True})
    service.call("scene.update_element", {"id": "generic_status_label", "changes": {"x": 9}})
    with pytest.raises(UnsavedChangesError, match="UNSAVED_CHANGES"):
        service.call("project.open_screen", {"screen_id": "generic_detail"})
    with pytest.raises(ValueError, match="mutually exclusive"):
        service.call("project.open_screen", {"screen_id": "generic_detail", "save_current": True, "discard_current": True})
    service.call("project.open_screen", {"screen_id": "generic_detail", "discard_current": True})
    service.call("project.open_screen", {"screen_id": "generic_status"})
    status_label = next(e for e in service.call("scene.list_elements", {})["elements"] if e["id"] == "generic_status_label")
    assert status_label["x"] == 8
    started = service.call("job.start", {"operation": "validate.all_states", "arguments": {"integer_policy": "full", "summary_only": True}})
    cancelled = service.call("job.cancel", {"job_id": started["job_id"]})
    assert cancelled["cancel_requested"] is True
    terminal = _wait_job(service, started["job_id"])
    assert terminal["state"] in {"cancelled", "completed"}


def test_generic_matrix_guards_fail_closed(tmp_path):
    _, service = _service(tmp_path)
    service.call("project.open_screen", {"screen_id": "generic_status", "discard_current": True})
    invalid = {"variables": {"bad-name": {"type": "enum", "values": ["A"], "init": "A"}}}
    assert service.call("state.validate_schema", {"schema": invalid})["valid"] is False
    with pytest.raises(ValueError, match="invalid state schema"):
        service.call("state.set_schema", {"schema": invalid})
    service.call("state.set_schema", {"schema": {"variables": {}, "relations": []}})
    assert service.call("state.enumerate", {"integer_policy": "representative"})["states"] == [{}]


def test_generic_graduation_runner_writes_machine_readable_evidence(tmp_path):
    from run_v9_phase3_generic_graduation import run_graduation

    result = run_graduation(tmp_path / "run", tmp_path / "evidence")

    assert result["phase"] == "V9 Phase 3"
    assert result["gate"] == "PASS"
    assert result["known_blockers"] == 0
    assert result["known_p0_p1"] == 0
    assert result["evidence_confidence"] == "High"
    assert result["windows_real_qt"] == "Not rerun (no trigger)"
    assert {step["status"] for step in result["steps"]} == {"observed_pass"}
    assert (tmp_path / "evidence" / "v9_phase3_generic_graduation.json").exists()
    assert (tmp_path / "evidence" / "v9_phase3_generic_graduation.md").exists()
