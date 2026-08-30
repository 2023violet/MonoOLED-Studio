from pathlib import Path
import sys

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from scene import load_scene, resolve, runtime_paths


def test_runtime_paths_in_source_tree_are_platform_native(tmp_path):
    module_file = tmp_path / 'project' / 'src' / 'scene.py'
    module_file.parent.mkdir(parents=True)
    module_file.write_text('# test', encoding='utf-8')
    root, scenes, logs = runtime_paths(module_file=module_file, frozen=False)
    assert root == tmp_path / 'project'
    assert scenes == tmp_path / 'project' / 'src' / 'scenes'
    assert logs == tmp_path / 'project' / 'src' / 'logs'


def test_runtime_paths_in_pyinstaller_onedir_bundle_are_platform_native(tmp_path):
    bundle = tmp_path / 'release' / 'MonoOLEDStudio'
    exe = bundle / 'MonoOLEDStudio.exe'
    root, scenes, logs = runtime_paths(
        module_file=tmp_path / 'irrelevant' / 'scene.py',
        frozen=True,
        meipass=bundle,
        executable=exe,
    )
    assert root == bundle
    assert scenes == bundle / 'src' / 'scenes'
    assert logs == bundle / 'logs'


def test_external_scene_uses_its_declared_project_root(tmp_path):
    project = tmp_path / 'external_project'
    scenes = project / 'scenes'
    scenes.mkdir(parents=True)
    scene_path = scenes / 'screen.json'
    scene_path.write_text(
        '{"project_root":"..","canvas":{"w":96,"h":16},"storage":{"layout":"VLSB","polarity":"1 = lit"},"states":{},"elements":[],"timeline":[]}',
        encoding='utf-8',
    )
    scene = load_scene(scene_path)
    assert Path(scene['_root']) == project.resolve()
    assert resolve('assets/icon.png', scene=scene) == (project / 'assets' / 'icon.png').resolve()
