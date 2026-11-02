"""Docs that describe the app the code actually is.

Each assertion names the source that proves it, so a failure points at the file
to read rather than at a sentence to argue about. These are the claims a
maintainer changed or deleted while making the interface and the manuals tell the
same story (2.0.3 round: controls that lied). Run with the rest of the governance
suite: `python -m pytest tools/tests -q`.

Code anchors match against whitespace-normalised source, so a behaviour-
preserving `cargo fmt` reflow cannot break this file; a claim that stops being
true can.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE_EN = ROOT / "docs" / "USER_GUIDE_EN.md"
GUIDE_CN = ROOT / "docs" / "USER_GUIDE_CN.md"
HANDOFF = ROOT / "docs" / "AI_HANDOFF.md"
AGENTS = ROOT / "AGENTS.md"
APP_RS = ROOT / "apps" / "mono-desktop" / "src" / "app.rs"
GUARD_RS = ROOT / "apps" / "mono-desktop" / "src" / "guard.rs"
MAIN_RS = ROOT / "apps" / "mono-desktop" / "src" / "main.rs"
PREFS_UI_RS = ROOT / "apps" / "mono-desktop" / "src" / "prefs_ui.rs"
FONTLAB_RS = ROOT / "apps" / "mono-desktop" / "src" / "fontlab.rs"
PIXEL_UI_RS = ROOT / "apps" / "mono-desktop" / "src" / "pixel_ui.rs"
MAIN_SLINT = ROOT / "apps" / "mono-desktop" / "ui" / "main.slint"
DESIGNER_SLINT = ROOT / "apps" / "mono-desktop" / "ui" / "designer.slint"
FONTLAB_SLINT = ROOT / "apps" / "mono-desktop" / "ui" / "fontlab.slint"
PROJECT_RS = ROOT / "crates" / "mono-project" / "src" / "project.rs"
EDITOR_RS = ROOT / "crates" / "mono-project" / "src" / "editor.rs"
WIDGETS_SLINT = ROOT / "apps" / "mono-desktop" / "ui" / "widgets.slint"
PIXEL_SLINT = ROOT / "apps" / "mono-desktop" / "ui" / "pixel.slint"
PREFERENCES_SLINT = ROOT / "apps" / "mono-desktop" / "ui" / "preferences.slint"
FONT_RS = ROOT / "crates" / "mono-font" / "src" / "lib.rs"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def code(path: Path) -> str:
    """Source with every run of whitespace collapsed, for anchor matching."""
    return re.sub(r"\s+", " ", read(path))


def paragraphs(text: str) -> list[str]:
    return [block for block in text.split("\n\n") if block.strip()]


def test_guides_agree_the_canvas_has_no_marquee():
    """Pressing empty canvas only clears the selection.

    Proved by the pointer handler in app.rs: a miss calls `selection.clear()` and
    drops `self.drag`, so nothing a rubber-band rectangle could grow from is
    started there.
    """
    assert (
        "None => { if !shift { self.selection.clear(); } self.drag = None; }"
        in code(APP_RS)
    ), "empty-canvas press no longer only clears the selection; re-read the guides"
    english = read(GUIDE_EN).lower()
    assert "marquee" not in english and "rubber-band" not in english
    for line in read(GUIDE_CN).splitlines():
        if "框选" in line:
            assert "没有框选" in line, f"the CN guide claims a marquee again: {line}"


def test_rename_screen_is_documented_and_really_wired():
    """The Navigator renames the active page and re-binds the session.

    Proved by `rename_screen` in project.rs, `rename_active_screen` in guard.rs
    (which drops the session before switching) and the `rename-screen` action.
    """
    assert "pub fn rename_screen" in read(PROJECT_RS)
    assert "fn rename_active_screen" in read(GUARD_RS)
    assert '"rename-screen"' in read(MAIN_RS)
    assert "Rename" in read(GUIDE_EN), "the EN guide stopped documenting rename"
    assert "重命名" in read(GUIDE_CN), "the CN guide stopped documenting rename"


def test_viewing_a_screen_does_not_rewrite_the_manifest():
    """AGENTS.md and both guides say switching pages writes nothing.

    Proved by the guide sentences and by the absence of the old claim; the write
    itself lives in `save`, not in the screen switch.
    """
    agents = read(AGENTS)
    assert "打开 Screen 会写回项目清单" not in agents, "AGENTS.md revived the old claim"
    assert "切换页面" in agents, "AGENTS.md stopped stating the read-only rule"
    assert "does not rewrite `project.oled.json`" in read(GUIDE_EN)
    assert "不会改写 `project.oled.json`" in read(GUIDE_CN)


def test_structural_manifest_edits_say_they_write_immediately():
    """Design rules and page structure bypass the `•` dirty dot, on purpose.

    Proved by `set_design_rules` routing through `transact` (change + save), not
    merely by both names existing somewhere in the file.
    """
    body = read(PROJECT_RS)
    start = body.index("pub fn set_design_rules")
    assert "transact" in body[start : start + 700], (
        "set_design_rules no longer writes through transact; "
        "both guides say a rules edit is on disk before the panel replies"
    )
    assert "written as you edit them" in read(GUIDE_EN)
    assert "编辑即写入" in read(GUIDE_CN)


def test_handoff_no_longer_calls_background_jobs_synchronous():
    """Export, handoff, batch validation and the thumbnail wall leave the UI thread.

    Proved by `start_background` in app.rs, which those actions call.
    """
    assert "fn start_background" in read(APP_RS)
    offenders = []
    for block in paragraphs(read(HANDOFF)):
        mentions_work = any(
            token in block
            for token in ("export-all", "export_all", "交接包", "批量验证", "缩略图墙")
        )
        if mentions_work and ("同步执行" in block or "synchronously" in block.lower()):
            offenders.append(block[:80])
    assert not offenders, f"handoff still calls worker work synchronous: {offenders}"
    assert "worker" in read(HANDOFF).lower() or "线程" in read(HANDOFF)


def test_zones_toggle_is_documented_and_draws():
    """The canvas Zones switch feeds the overlay from `design_rules`.

    Proved by `show-zones` on the canvas plus the loop that renders it, and by
    `apply_canvas_preferences` reading the `canvas.zones` preference.
    """
    designer = read(DESIGNER_SLINT)
    assert "in property <bool> show-zones" in designer
    assert "for zone in root.zones" in designer, "nothing renders the zone overlay"
    assert 'bool("canvas.zones")' in read(PREFS_UI_RS)
    assert "Zones" in read(GUIDE_EN)
    assert "区域" in read(GUIDE_CN)


def test_state_schema_and_design_rules_tabs_exist():
    """The Inspector exposes the state schema and the design rules editor.

    Proved by the `inspector-tab == 3` and `== 4` panels and by the session and
    project methods behind them.
    """
    designer = read(DESIGNER_SLINT)
    assert "inspector-tab == 3" in designer
    assert "inspector-tab == 4" in designer
    assert "pub fn set_state_schema" in read(EDITOR_RS)
    # Five tabs do not fit the Inspector at the window minimum, so the strip says
    # Schema / Rules. The guides have to name what the user actually reads.
    assert '"tab.schema"' in code(DESIGNER_SLINT) and '"tab.rules"' in code(DESIGNER_SLINT)
    assert "State schema" in read(GUIDE_EN)
    assert "**Schema**" in read(GUIDE_EN)
    assert "状态结构" in read(GUIDE_CN)
    assert "**结构**" in read(GUIDE_CN)


def test_glyph_offsets_are_documented_and_reach_the_generator():
    """Font Lab's offset rows are engine options, not decoration.

    Proved by the two rows binding and editing, and by `GenerateOptions.offset`
    taking the form values.
    """
    slint = read(FONTLAB_SLINT)
    assert 'edit("offset_x"' in slint and 'edit("offset_y"' in slint
    assert "FontModel.offset-x" in slint and "FontModel.offset-y" in slint
    assert "self.form.offset_x, self.form.offset_y" in code(FONTLAB_RS)
    assert "offset" in read(GUIDE_EN).lower()
    assert "偏移" in read(GUIDE_CN)


def test_the_offset_rows_stay_reachable_with_no_font_file():
    """Clearing the font file must not strand a non-zero offset.

    A leftover offset is itself what makes a TrueType source required, so rows
    gated on `font-path` would trap the form in a state that cannot generate.
    Proved by both rows being plain always-editable spin boxes, and by `mono-font`
    refusing with a message that names the offset rather than the characters.
    """
    slint = code(FONTLAB_SLINT)
    for axis in ("offset_x", "offset_y"):
        needle = (
            "minimum: -64; maximum: 64; enabled: !FontModel.busy; "
            f'edited(v) => {{ FontModel.edit("{axis}", v); }}'
        )
        assert needle in slint, f"the {axis} row is gated on something but busy"
    assert '"a TrueType font is required because the built-in OLED font carries no glyph offset"' in code(
        FONT_RS
    )
    assert "offset must be between -64 and 64" in read(FONT_RS)


def test_cancelling_a_running_job_has_a_visible_control():
    """The status bar offers Cancel while a job runs, not only the palette.

    Proved by the `AppModel.busy` block in main.slint bound to `cancel-job`.
    """
    main = read(MAIN_SLINT)
    assert 'AppModel.action("cancel-job")' in main
    assert "if AppModel.busy" in main
    assert "Cancel" in read(GUIDE_EN)
    assert "取消" in read(GUIDE_CN)


def test_the_workbench_scene_source_reports_the_real_failure():
    """A failed render is reported as a failed render.

    Proved by `bench_items` in pixel_ui.rs: `current_framebuffer()` must propagate
    rather than relabel a render failure as "open a project first" — the same
    "says one thing, does another" pattern this round exists to end.
    """
    body = code(PIXEL_UI_RS)
    needle = "current_framebuffer()"
    swallowed = [
        body[at : at + 60]
        for at in range(len(body))
        if body.startswith(needle, at) and ".map_err" in body[at : at + 60]
    ]
    assert not swallowed, f"a framebuffer failure is being relabelled: {swallowed}"


def test_every_dialog_really_closes_on_the_backdrop():
    """Both guides promise a click outside the card dismisses any dialog.

    Proved by `Scrim` in widgets.slint: its TouchArea covers the dimmed area and
    emits `dismissed`, every component that inherits Scrim handles that callback,
    and nothing switches `dismissable` off. A dialog added without the handler
    would trap the window, and the sentence in the manuals would be a lie.
    """
    assert (
        "clicked => { if (root.dismissable) { root.dismissed(); } }" in code(WIDGETS_SLINT)
    ), "the dimmed area no longer emits dismissed"
    assert "clicking the dimmed area outside it" in read(GUIDE_EN)
    assert "遮罩" in read(GUIDE_CN)
    scrims = []
    for path in (MAIN_SLINT, PIXEL_SLINT, PREFERENCES_SLINT, DESIGNER_SLINT):
        for chunk in re.split(r"\n\}[ \t]*\n", read(path)):
            found = re.search(r"component (\w+) inherits Scrim", chunk)
            if found:
                scrims.append((path.name, found.group(1), chunk))
    assert len(scrims) >= 8, f"expected the eight scrim dialogs, found {[n for _, n, _ in scrims]}"
    for file, name, chunk in scrims:
        assert "dismissed =>" in chunk, f"{file}: {name} has no way out but Escape"
    for path in (MAIN_SLINT, PIXEL_SLINT, PREFERENCES_SLINT, DESIGNER_SLINT, WIDGETS_SLINT):
        assert "dismissable: false" not in code(path), f"{path.name} makes a dialog undismissable"
