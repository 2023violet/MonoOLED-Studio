import sys
from pathlib import Path
import zipfile

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

from export_matrix import build_export_states
from exporter import export_scene
from handoff import build_handoff_package


def _scene(root: Path) -> dict:
    return {
        "_root": str(root),
        "schema_version": 1,
        "product": "Generic Export Fixture",
        "canvas": {"w": 16, "h": 8, "preview_scale": 4},
        "storage": {"layout": "VLSB", "polarity": "1 = lit", "bytes_per_frame": 16},
        "states": {
            "page": {"type": "enum", "values": ["HOME", "SETTINGS"], "init": "HOME"},
            "channel": {"type": "int", "min": 1, "max": 2, "init": 1},
        },
        "elements": [],
        "timeline": [],
    }


def test_generic_export_uses_schema_matrix_and_deterministic_handoff(tmp_path):
    scene = _scene(tmp_path)
    states = build_export_states(scene)

    exported = export_scene(scene, tmp_path / "export", states)
    first_zip = tmp_path / "handoff_a.zip"
    second_zip = tmp_path / "handoff_b.zip"
    handoff_a = build_handoff_package(
        scene,
        first_zip,
        states=states,
        integer_policy="representative",
    )
    handoff_b = build_handoff_package(
        scene,
        second_zip,
        states=states,
        integer_policy="representative",
    )

    assert len(states) == 4
    assert exported.frame_count == 4
    assert handoff_a.frame_count == handoff_b.frame_count == 4
    assert first_zip.read_bytes() == second_zip.read_bytes()
    with zipfile.ZipFile(first_zip) as archive:
        names = set(archive.namelist())
        assert sum(name.startswith("golden/") for name in names) == 4
        assert sum(name.startswith("reference/") for name in names) == 4
        report = archive.read("batch_validation.md").decode("utf-8")
        assert "Cases: **4**" in report
        assert "Blockers: **0**" in report
