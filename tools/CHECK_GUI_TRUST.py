"""End-to-end checks for the interface-truth fixes, driving the real desktop binary.

The unit tests pin each module; this script pins the seams a user actually
touches: keyboard focus after modals, what the settings page renders, the zone
overlay behind its saved switch, what the status bar says while a job runs,
what the next undo reverts, how the Inspector edits the state schema and the
project's design rules, how a screen rename re-binds its session, the dirty dot
across undo, the export gate in front of the C-header writer, the glyph offsets
that reach the font generator, and the Font Lab and Inspector layouts at the
minimum window size. Every case opens a throwaway copy of
`test_assets/projects/curing_lite` with APPDATA / LOCALAPPDATA / XDG_CONFIG_HOME
pointed at a temp directory, so no user state and no fixture is touched.

Each run ends with a screenshot so the event loop quits by itself; the script
reads the `SELFCHECK` lines the app prints for scripted `--action` runs. This
needs a display and is therefore a maintainer check, not part of the CI gate.

Usage: python tools/CHECK_GUI_TRUST.py [--exe PATH] [--keep]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'test_assets' / 'projects' / 'curing_lite'
BLOCKER = {'id': 'gate_probe', 'type': 'placeholder', 'x': 126, 'y': 0, 'w': 4, 'h': 4}
MIN_WINDOW = (1100, 700)
RUN_TIMEOUT = 180


def default_exe() -> Path:
    name = 'monooled-studio' + ('.exe' if os.name == 'nt' else '')
    return ROOT / 'target' / 'debug' / name


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'{path} is not a PNG')
    width, height = struct.unpack('>II', data[16:24])
    return width, height


def selfcheck(log: str, key: str) -> list[str]:
    prefix = f'SELFCHECK {key}='
    return [line[len(prefix):] for line in log.splitlines() if line.startswith(prefix)]


def one(log: str, key: str) -> str:
    values = selfcheck(log, key)
    if len(values) != 1:
        raise AssertionError(f'expected one SELFCHECK {key}, got {values}')
    return values[0]


class Runner:
    def __init__(self, exe: Path, root: Path):
        self.exe = exe
        self.root = root

    def case_dir(self, tag: str) -> Path:
        work = self.root / tag
        (work / 'appdata').mkdir(parents=True)
        (work / 'localappdata').mkdir(parents=True)
        (work / 'xdg').mkdir(parents=True)
        return work

    def project(self, work: Path, blocker: bool = False) -> Path:
        project = work / 'project'
        shutil.copytree(PROJECT, project)
        if blocker:
            scene_path = project / 'scenes' / '123.json'
            scene = json.loads(scene_path.read_text(encoding='utf-8'))
            scene['elements'].append(dict(BLOCKER))
            scene_path.write_text(json.dumps(scene, indent=2), encoding='utf-8')
        return project

    def preferences(self, work: Path) -> Path:
        if os.name == 'nt':
            return work / 'localappdata' / 'MonoOLEDStudio' / 'preferences.json'
        return work / 'xdg' / 'monooled-studio' / 'preferences.json'

    def run(self, work: Path, project: Path, actions: list[str], extra: list[str] | None = None) -> str:
        shot = work / 'shot.png'
        cmd = [str(self.exe), str(project), '--screenshot', str(shot), *(extra or [])]
        for action in actions:
            cmd += ['--action', action]
        env = dict(os.environ)
        env.update({
            'APPDATA': str(work / 'appdata'),
            'LOCALAPPDATA': str(work / 'localappdata'),
            'XDG_CONFIG_HOME': str(work / 'xdg'),
        })
        print('  $ ' + ' '.join(f'"{part}"' if ' ' in part else part for part in cmd[1:]))
        try:
            done = subprocess.run(
                # The app prints UTF-8; on a GBK locale the default decoding
                # kills the reader thread and stdout comes back as None.
                cmd, cwd=ROOT, env=env, capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=RUN_TIMEOUT,
            )
        except subprocess.TimeoutExpired as error:
            raise AssertionError(f'app did not exit within {RUN_TIMEOUT}s (modal swallowed the quit?)') from error
        if done.stdout is None or done.stderr is None:
            raise AssertionError('could not read the app output (stdout/stderr not captured)')
        log = done.stdout + done.stderr
        if done.returncode != 0:
            raise AssertionError(f'app exited {done.returncode}\n{log}')
        return log


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_overlays_and_focus(runner: Runner) -> None:
    """R1/R9: every modal closes on Escape and hands the keyboard back."""
    work = runner.case_dir('overlay-focus')
    actions = ['dump:pixel-tool']
    for opener, name in [
        ('preferences', 'preferences'),
        ('about', 'about'),
        ('command-palette', 'picker'),
        ('new-screen', 'prompt'),
        ('pixel:canvas-size', 'pixel'),
    ]:
        actions += [opener, 'dump:overlay', 'key:escape', 'dump:overlay']
    actions += ['key:m', 'dump:pixel-tool']
    log = runner.run(work, runner.project(work), actions, ['--workspace', '1'])
    overlays = selfcheck(log, 'overlay')
    expected = []
    for name in ['preferences', 'about', 'picker', 'prompt', 'pixel']:
        expected += [name, 'none']
    expect(overlays == expected, f'modal Escape sequence {overlays} != {expected}')
    tools = selfcheck(log, 'pixel.tool')
    expect(len(tools) == 2, f'expected two tool dumps, got {tools}')
    expect(tools[0] != '5', f'bare "m" must change the tool, started at {tools[0]}')
    expect(tools[-1] == '5', f'bare "m" after modals selected {tools[-1]}, expected 5 (select)')


def check_preferences_page(runner: Runner) -> None:
    """R2: a flat dotted shortcut is rendered, and an edit is flushed to disk."""
    work = runner.case_dir('prefs-page')
    path = runner.preferences(work)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'shortcuts': {'project.save': 'Ctrl+Alt+S'}}), encoding='utf-8')
    actions = [
        'preferences',
        'pref-section:4',  # keyboard: the section that renders the shortcut rows
        'dump:prefs-shortcut',
        'pref-edit:shortcuts.project.save=Ctrl+Shift+S',
        'pref-section:1',  # leaving the section flushes the pending edit
        'pref-section:4',
        'dump:prefs-shortcut',
    ]
    log = runner.run(work, runner.project(work), actions)
    stored = selfcheck(log, 'shortcut.project.save')
    rows = selfcheck(log, 'shortcut.project.save.row')
    expect(stored == ['Ctrl+Alt+S', 'Ctrl+Shift+S'], f'stored chords {stored}')
    expect(rows == ['Ctrl+Alt+S', 'Ctrl+Shift+S'], f'settings rows {rows} (page must render the stored chord)')
    saved = json.loads(path.read_text(encoding='utf-8'))
    shortcuts = saved.get('shortcuts', {})
    expect(shortcuts.get('project.save') == 'Ctrl+Shift+S', f'edit not flushed: {shortcuts.get("project.save")!r}')
    expect('project' not in shortcuts, 'shortcuts must stay flat (dotted keys), not nested')


def check_zones_overlay(runner: Runner) -> None:
    """R2/WP2: the canvas carries the project's design zones and the switch survives a restart."""
    work = runner.case_dir('zones-overlay')
    project = runner.project(work)

    log = runner.run(work, project, ['dump:zones'])
    shutil.copy(work / 'shot.png', work / 'zones-off.png')
    expect(one(log, 'zones') == '2 shown=false', f'fresh overlay state {one(log, "zones")!r}')

    actions = [
        'preferences',
        'pref-section:2',  # canvas: the section holding the zones switch
        'pref-edit:canvas.zones=true',
        'pref-section:3',  # leaving the section flushes the pending edit
        'dump:zones',
    ]
    log = runner.run(work, project, actions)
    expect(one(log, 'zones') == '2 shown=true', f'after the edit {one(log, "zones")!r}')
    saved = json.loads(runner.preferences(work).read_text(encoding='utf-8'))
    expect(saved.get('canvas', {}).get('zones') is True, f'canvas.zones not persisted: {saved.get("canvas")}')

    # A second process: the saved preference has to reach the canvas on its own.
    log = runner.run(work, project, ['dump:zones'])
    shutil.copy(work / 'shot.png', work / 'zones-on.png')
    expect(one(log, 'zones') == '2 shown=true', 'canvas.zones is not restored at startup')

    off = (work / 'zones-off.png').read_bytes()
    on = (work / 'zones-on.png').read_bytes()
    expect(off != on, 'the zone overlay changed nothing on screen')


def check_job_busy_and_cancel(runner: Runner) -> None:
    """R5/WP3: a background job owns the status bar, clears it, and can be cancelled."""
    work = runner.case_dir('job-busy')
    project = runner.project(work)

    log = runner.run(
        work, project, ['dump:job', 'batch-validate', 'dump:job', 'job-later:700']
    )
    busy = selfcheck(log, 'busy')
    expect(busy == ['false', 'true'], f'busy sequence {busy}')
    texts = selfcheck(log, 'busy.text')
    expect(len(texts) == 2 and texts[1] != '', f'no busy label while the job runs: {texts!r}')
    expect(
        texts[1] == selfcheck(log, 'status.text')[1],
        f'busy label and status line disagree at job start: {texts[1]!r}',
    )
    expect(one(log, 'busy.later') == 'false', 'busy was never cleared after the job finished')
    finished = one(log, 'status.text.later')

    log = runner.run(work, project, ['batch-validate', 'cancel-job', 'job-later:700'])
    expect(one(log, 'busy.later') == 'false', 'a cancelled job left busy set')
    cancelled = one(log, 'status.text.later')
    expect(cancelled != '', 'the status bar is silent after cancelling')
    expect(cancelled != finished, f'cancel reported the same outcome as finishing: {cancelled!r}')


def check_undo_names_its_step(runner: Runner) -> None:
    """R3/WP3: the Edit menu says what the next undo really reverts."""
    work = runner.case_dir('undo-label')
    actions = ['dump:undo-label', 'add-placeholder', 'dump:undo-label', 'undo', 'dump:undo-label']
    log = runner.run(work, runner.project(work), actions)
    tokens = selfcheck(log, 'undo.token')
    texts = selfcheck(log, 'undo.text')
    expect(tokens == ['none', 'add_placeholder', 'none'], f'undo stack {tokens}')
    expect(texts[0] == texts[2], f'plain undo label changed with no step pending: {texts!r}')
    expect(texts[1] != texts[0], f'the menu still says only {texts[0]!r}')
    expect(texts[0] in texts[1], f'menu text {texts[1]!r} does not read as an undo')


def check_state_schema_editing(runner: Runner) -> None:
    """R6/WP4: the Inspector edits the state schema, and an invalid draft never reaches disk."""
    work = runner.case_dir('state-schema')
    project = runner.project(work)
    scene = project / 'scenes' / '123.json'

    def saved_init() -> object:
        states = json.loads(scene.read_text(encoding='utf-8')).get('states', {})
        return states.get('battery', {}).get('init')

    actions = [
        'dump:states',
        'schema:add-variable:battery:',
        'dump:states',
        'schema:set-init:battery:9999',
        'dump:states',
        'save',
    ]
    log = runner.run(work, project, actions)
    states = selfcheck(log, 'states')
    expect(states[0].startswith('vars:0'), f'fresh scene should have no variables: {states[0]!r}')
    expect(states[1] == 'vars:1 relations:0 valid:true names:battery', f'after add: {states[1]!r}')
    expect('valid:false' in states[2], f'out-of-range init was accepted: {states[2]!r}')
    expect(
        'min/max' in selfcheck(log, 'states.errors')[2],
        'the validator message never reached the panel',
    )
    expect(saved_init() == 0, f'the rejected draft reached disk: init={saved_init()!r}')

    # Restart with the committed default, then correct it: only now is 2 valid.
    log = runner.run(work, project, ['dump:states', 'schema:set-init:battery:2', 'dump:states', 'save'])
    states = selfcheck(log, 'states')
    expect('valid:true' in states[1], f'corrected init stayed invalid: {states[1]!r}')
    expect(saved_init() == 2, f'saved init should be the corrected value, got {saved_init()!r}')


def check_screen_rename_rebinds_session(runner: Runner) -> None:
    """R7/WP5: renaming a screen moves the file, re-binds the session, and does not resurrect it."""
    work = runner.case_dir('rename-screen')
    project = runner.project(work)
    actions = [
        'dump:screen-ids',
        'rename-screen',
        'dump:overlay',
        'prompt-answer:renamed',
        'dump:screen-ids',
        'add-placeholder',
        'save',
    ]
    log = runner.run(work, project, actions)
    ids = selfcheck(log, 'screen.ids')
    expect(ids == ['main,123', 'main,renamed'], f'screen ids {ids}')
    expect(selfcheck(log, 'overlay') == ['prompt'], 'the rename prompt did not open')
    paths = selfcheck(log, 'session.path')
    expect(paths[1].endswith('renamed.json'), f'session not re-bound: {paths[1]!r}')
    expect((project / 'scenes' / 'renamed.json').is_file(), 'the renamed scene file is missing')
    expect(
        not (project / 'scenes' / '123.json').exists(),
        'a later save resurrected the renamed-away file',
    )
    manifest = json.loads((project / 'project.oled.json').read_text(encoding='utf-8'))
    expect(manifest.get('active_screen') == 'renamed', f'active screen {manifest.get("active_screen")!r}')


def check_design_rules_editing(runner: Runner) -> None:
    """R7/WP5: a zone edit writes the manifest at once and the findings follow without a reopen."""
    work = runner.case_dir('design-rules')
    project = runner.project(work)
    manifest = project / 'project.oled.json'
    actions = [
        'open-screen:main',
        'dump:findings',
        'rules:set-zone:0:w:2',
        'dump:findings',
        'dump:rules',
        'rules:set-zone:0:h:abc',
        'dump:rules',
    ]
    log = runner.run(work, project, actions)
    findings = selfcheck(log, 'findings')
    expect('ELEMENT_OUTSIDE_ZONE' not in findings[0], f'baseline findings {findings[0]!r}')
    expect('ELEMENT_OUTSIDE_ZONE' in findings[1], f'after the zone edit: {findings[1]!r}')
    rules = json.loads(manifest.read_text(encoding='utf-8'))['design_rules']
    expect(rules['zones']['battery']['w'] == 2, f'zone edit not written: {rules["zones"]}')
    expect(rules['zones']['battery']['h'] == 32, f'rejected edit reached disk: {rules["zones"]}')
    expect(
        'battery.h' in selfcheck(log, 'rules.errors')[1],
        f'the rejected coordinate was not named: {selfcheck(log, "rules.errors")}',
    )


def check_dirty_undo(runner: Runner) -> None:
    """R3: the dirty dot follows the document, so undo back to the save point is clean."""
    work = runner.case_dir('dirty-undo')
    actions = ['dump:dirty', 'add-placeholder', 'dump:dirty', 'undo', 'dump:dirty']
    log = runner.run(work, runner.project(work), actions)
    states = selfcheck(log, 'dirty')
    expect(states == ['false', 'true', 'false'], f'dirty sequence {states}')


def check_export_gate(runner: Runner) -> None:
    """R4/R7: a blocking scene stops the C-header writer and says so in a dialog."""
    work = runner.case_dir('export-gate')
    project = runner.project(work, blocker=True)
    header = work / 'frame.h'
    actions = [
        f'export-c-header:{header}',
        'dump:overlay',
        'key:escape',
        'dump:overlay',
        'key:m',
        'dump:pixel-tool',
    ]
    log = runner.run(work, project, actions, ['--workspace', '1'])
    overlays = selfcheck(log, 'overlay')
    expect(overlays == ['blocked', 'none'], f'blocked dialog sequence {overlays}')
    expect(not header.exists(), f'a blocked export wrote {header}')
    report = project / '.oled' / 'validation_report.md'
    expect(report.is_file(), f'missing report at {report}')
    text = report.read_text(encoding='utf-8')
    expect('DRAFT_PLACEHOLDER' in text, 'report must name the blocking finding')
    expect(one(log, 'pixel.tool') == '5', 'bare keys must work again after the blocked dialog closes')


def check_fontlab_min_size(runner: Runner) -> None:
    """R8: Font Lab keeps all three columns at the minimum window size."""
    work = runner.case_dir('fontlab-size')
    runner.run(work, runner.project(work), [], ['--workspace', '2', '--window-size', '1166x800'])
    shot = work / 'shot.png'
    expect(shot.is_file(), f'missing screenshot {shot}')
    width, height = png_size(shot)
    expect(width >= MIN_WINDOW[0] and height >= MIN_WINDOW[1], f'screenshot {width}x{height} below the window minimum')
    expect(shot.stat().st_size > 20_000, f'screenshot looks blank ({shot.stat().st_size} bytes)')
    print(f'  screenshot for review: {shot}')


def check_fontlab_offsets_reach_the_form(runner: Runner) -> None:
    """R11/WP6: the generator's offset rows land in the form the engine reads.

    Both sides are dumped: `form` is what `GenerateOptions.offset` gets, `model`
    is what the two SpinBox rows show. A row that only moved the model would be a
    control that lies, and the engine would then rasterize where the user did not
    ask it to.
    """
    work = runner.case_dir('fontlab-offsets')
    project = runner.project(work)
    actions = [
        'new-font-pack',
        'prompt-answer:Clinical 5x7',
        'dump:font-offset',
        'font-edit:offset_x:3',
        'font-edit:offset_y:-2',
        'dump:font-offset',
    ]
    log = runner.run(work, project, actions, ['--workspace', '2'])
    dumps = selfcheck(log, 'font.offset')
    expect(len(dumps) == 2, f'expected two offset dumps, got {dumps}')
    expect(dumps[0] == 'form0,0 model0,0', f'a fresh pack starts offset: {dumps[0]!r}')
    expect(dumps[1] == 'form3,-2 model3,-2', f'the offset rows did not reach the form: {dumps[1]!r}')


def check_font_pack_stays_in_the_project(runner: Runner) -> None:
    """TASK-013: a scene member cannot list or open a font pack outside the root."""
    work = runner.case_dir('fontlab-outside')
    project = runner.project(work)
    outside = work / 'outside-pack'
    outside.mkdir()
    (outside / 'fontpack.json').write_text(
        json.dumps({'schema': 1, 'name': 'Outside', 'cell': {'w': 5, 'h': 8}, 'glyphs': {}}),
        encoding='utf-8',
    )
    scene_path = project / 'scenes' / 'main_scene.json'
    scene = json.loads(scene_path.read_text(encoding='utf-8'))
    scene['elements'].append({
        'id': 'outside', 'type': 'bitmap_text', 'font_pack': '../outside-pack',
        'text': 'A', 'x': 0, 'y': 0,
    })
    scene_path.write_text(json.dumps(scene), encoding='utf-8')
    inside = project / 'fonts' / 'inside-pack'
    inside.mkdir(parents=True)
    (inside / 'fontpack.json').write_text((outside / 'fontpack.json').read_text(encoding='utf-8'), encoding='utf-8')
    actions = [
        'open-screen:main',
        'dump:font-offset',
        'font:open:../outside-pack',
        'dump:font-offset',
        'font:open:fonts/inside-pack',
        'dump:font-offset',
    ]
    log = runner.run(work, project, actions, ['--workspace', '2'])
    dumps = selfcheck(log, 'font.offset')
    expect(dumps[:2] == ['none', 'none'], f'a pack outside the project was opened: {dumps}')
    expect(dumps[2] == 'form0,0 model0,0', f'a pack inside the project did not open: {dumps}')


def check_canvas_click_picks_the_topmost_element(runner: Runner) -> None:
    """TASK-012: a click on the real canvas answers from the rects the frame resolved."""
    work = runner.case_dir('canvas-click')
    project = runner.project(work)
    scene_path = project / 'scenes' / '123.json'
    scene = json.loads(scene_path.read_text(encoding='utf-8'))
    scene['elements'] = [
        {'id': 'below', 'type': 'placeholder', 'x': 0, 'y': 0, 'w': 16, 'h': 16},
        {'id': 'above', 'type': 'placeholder', 'x': 8, 'y': 8, 'w': 16, 'h': 16},
    ]
    scene_path.write_text(json.dumps(scene), encoding='utf-8')
    actions = [
        'canvas-click:10:10',
        'dump:primary',
        'canvas-click:2:2',
        'dump:primary',
        'canvas-click:60:20',
        'dump:primary',
    ]
    picks = selfcheck(runner.run(work, project, actions), 'selection.primary')
    expect(picks == ['above', 'below', 'none'], f'the click picked {picks}')


def check_selection_names_the_multi_select(runner: Runner) -> None:
    """R11/WP6: the Inspector says how many elements are in the selection.

    The property fields describe the primary element only, so a selection of two
    has to say so; one element must stay quiet about it.
    """
    work = runner.case_dir('selection-count')
    project = runner.project(work)
    scene_path = project / 'scenes' / '123.json'
    scene = json.loads(scene_path.read_text(encoding='utf-8'))
    scene['elements'] += [
        {'id': 'count_a', 'type': 'placeholder', 'x': 8, 'y': 8, 'w': 8, 'h': 8},
        {'id': 'count_b', 'type': 'placeholder', 'x': 24, 'y': 8, 'w': 8, 'h': 8},
    ]
    scene_path.write_text(json.dumps(scene, indent=2), encoding='utf-8')

    log = runner.run(work, project, ['navigator:1', 'select-later:count_a', 'later:500:dump:selection'])
    expect(one(log, 'selection.text') == '', f'a single element got a count line: {one(log, "selection.text")!r}')

    log = runner.run(
        work, project,
        ['navigator:1', 'select-later:count_a', 'select-later:+count_b', 'later:500:dump:selection'],
    )
    text = one(log, 'selection.text')
    expect('2' in text and text != 'inspector.selected_count', f'multi-select line wrong: {text!r}')
    print(f'  screenshot for review: {work / "shot.png"}')


def check_scroll_to_selection(runner: Runner) -> None:
    """R10: selecting a row that is off-screen scrolls the list to it.

    Adjacent rows are picked so that the highlight itself cannot explain the
    difference: without a viewport move both screenshots are byte-identical.
    """
    work = runner.case_dir('scroll-list')
    project = runner.project(work)
    scene_path = project / 'scenes' / '123.json'
    scene = json.loads(scene_path.read_text(encoding='utf-8'))
    scene['elements'] += [
        {'id': f'probe_{i:02d}', 'type': 'placeholder', 'x': (i % 12) * 10, 'y': (i % 3) * 10, 'w': 8, 'h': 8}
        for i in range(40)
    ]
    scene_path.write_text(json.dumps(scene, indent=2), encoding='utf-8')
    shots = {}
    for row in ('probe_38', 'probe_39'):
        runner.run(work, project, ['navigator:1', f'select-later:{row}'])
        shots[row] = (work / 'shot.png').read_bytes()
        (work / f'shot-{row}.png').write_bytes(shots[row])
    expect(shots['probe_38'] != shots['probe_39'],
           'the element list never scrolled: adjacent selections render identically')


def check_inspector_tabs_at_min_size(runner: Runner) -> None:
    """R11/WP4+WP5: all five Inspector tabs render inside the narrow panel.

    The State schema and Design rules tabs are new, and at the window minimum the
    Inspector is about 310px wide, so the tab strip cannot show every full label.
    Each tab is opened at that size and its pixels kept: five identical shots
    would mean the strip stopped switching or a body renders nothing at all, and
    the last one is left for a human to read the wording.
    """
    work = runner.case_dir('inspector-min-size')
    project = runner.project(work)
    shots = []
    for tab in range(5):
        runner.run(work, project, ['open-screen:main', f'inspector-tab:{tab}'], ['--window-size', '1166x800'])
        shot = work / 'shot.png'
        expect(shot.is_file(), f'missing screenshot for tab {tab}')
        shots.append(shot.read_bytes())
        (work / f'shot-tab-{tab}.png').write_bytes(shots[-1])
    width, height = png_size(work / 'shot.png')
    expect(width >= MIN_WINDOW[0] and height >= MIN_WINDOW[1], f'screenshot {width}x{height} below the window minimum')
    expect(len(set(shots)) == 5, 'the Inspector tabs render identically, so the strip is not switching')
    print(f'  screenshot for review: {work / "shot-tab-4.png"}')


CHECKS = [
    check_overlays_and_focus,
    check_preferences_page,
    check_zones_overlay,
    check_job_busy_and_cancel,
    check_undo_names_its_step,
    check_state_schema_editing,
    check_screen_rename_rebinds_session,
    check_design_rules_editing,
    check_dirty_undo,
    check_export_gate,
    check_fontlab_min_size,
    check_fontlab_offsets_reach_the_form,
    check_font_pack_stays_in_the_project,
    check_canvas_click_picks_the_topmost_element,
    check_selection_names_the_multi_select,
    check_scroll_to_selection,
    check_inspector_tabs_at_min_size,
]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--exe', type=Path, default=default_exe(), help='desktop binary (default: debug build)')
    parser.add_argument('--keep', action='store_true', help='keep the temp tree for inspection')
    args = parser.parse_args(argv)
    exe = args.exe.resolve()
    if not exe.is_file():
        print(f'missing {exe}; build it first with: cargo build -p mono-desktop', file=sys.stderr)
        return 2
    root = Path(tempfile.mkdtemp(prefix='mono-gui-trust-'))
    runner = Runner(exe, root)
    failed = 0
    try:
        for check in CHECKS:
            print(f'{check.__name__}: {check.__doc__.splitlines()[0]}')
            try:
                check(runner)
            except AssertionError as error:
                failed += 1
                print(f'FAIL {check.__name__}: {error}', file=sys.stderr)
            else:
                print(f'PASS {check.__name__}')
            print()
    finally:
        if args.keep:
            print(f'kept {root}')
        else:
            shutil.rmtree(root, ignore_errors=True)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
