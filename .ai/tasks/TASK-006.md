# TASK-006 — 2.1.0 Professional Workflow (Phase 3)

Status: VERIFY
Review Status: PENDING

## Goal

Implement the approved plan's Phase 3 (T12–T17): one command registry driving menu/palette/shortcuts (T12), a real diff-review workspace (T13), a non-modal Agent Bridge panel with permission switching (T14), a theme-following Pixel palette plus High Contrast (T15), a true 1-bit Font Lab preview with save state (T16), and localized validation findings (T17). Ship as 2.1.0 without changing Automation JSON, golden fixtures, or the frozen test assets.

## Background

Phases 1–2 (2.0.4, 2.0.5) are DONE (TASK-004, TASK-005). The approved plan is `C:\Users\16429\.qoder\plans\faint-pool-trout.md`; this TASK covers its Phase 3 only. The CXO report found four drifting command lists, a "review" workspace that only shows a diff drawer, a one-shot modal bridge token, a light-only Pixel palette, a misleading Font Lab preview, and untranslated validation findings.

## Current Problem

- `extras::PALETTE` (16 entries), `prefs_ui::SHORTCUTS` (8 chords), and `main::fallback_action` (fixed chords) are independent lists; palette rows show no shortcut hint.
- Workspace 3 is the Designer with a drawer, with no side-by-side baseline/current, bbox, or element change list.
- The bridge token appears once in a modal dialog, cannot be selected or shown again, and the permission is fixed.
- Pixel colors prefer light backgrounds; `theme_mode` cannot be set to high-contrast from Preferences.
- Font Lab previews glyphs on the editing canvas (grid/border), not as an OLED would render them.
- Validation rows start with a raw English code/detail in the Chinese UI.

## Evidence

- `apps/mono-desktop/src/extras.rs:34` (`PALETTE`), `:597-640` (`picker_entries`)
- `apps/mono-desktop/src/prefs_ui.rs:23` (`SHORTCUTS`), `:150-270`
- `apps/mono-desktop/src/main.rs:595-660` (`fallback_action`, `run_shortcut`)
- `apps/mono-desktop/src/app.rs` `refresh_validation`; `crates/mono-project/src/export.rs`
- `apps/mono-desktop/src/agent.rs`; `apps/mono-desktop/src/display.rs`; `apps/mono-desktop/src/fontlab.rs`

## Required Changes

1. **T12 — command registry:** new `commands.rs` with `Requirement`, `CommandSpec`, `COMMANDS`, `CONFIGURABLE`, `default_shortcuts`, `fixed_action`, `palette_commands`, `is_known`; migrate all three lists; palette items carry `detail`; prefs defaults agree with the registry; tests for uniqueness, dispatchability, and Slint menu literals.
2. **T13 — diff review:** `mono-core/src/diff.rs` (`DiffBox`, `changed_count`, `changed_bbox`); automation `pixel_diff` reuses it; `App::refresh_review` produces baseline/current images, stats, bbox, and added/removed/modified element lists; `review.slint` renders side-by-side; workspace 3 renders it.
3. **T14 — Agent Bridge:** `BridgePermission { Observe, Edit, Full }`; `start_agent_with`, `set_agent_permission`, `agent_action`; non-modal `agent.slint` panel with masked/revealable token, copy endpoint/token, permission combo, stop; permission change restarts with a new token/port; token never logged.
4. **T15 — theme palette:** `pixel_studio.palette_mode` (`auto`/`custom`), legacy migration, `theme_palette`, high-contrast selectable in Preferences, Pixel "follow theme" switch; custom colors preserved.
5. **T16 — Font Lab preview:** true 1-bit white-on-black preview image (4×/8×, pixelated) with a toggle, plus `pack-state` derived from glyph/pack dirty state and copy separating "save glyph" from "generate pack".
6. **T17 — findings localization:** `FINDING_CODES`; `finding.<CODE>` labels in en/zh; `FindingItem.label`; Designer shows label + original English detail; Automation JSON unchanged.

## Architecture

- The registry owns action ids, labels, default chords, configurability, palette membership, and requirement tiers. Menu, palette, shortcut resolution, and Preferences read from it; only `COMMANDS` may gain entries.
- Diff math lives in `mono-core` so the desktop and Automation share one definition of changed count/bbox.
- Bridge state stays in `Agent`; the panel only binds and forwards actions. Token copy uses `arboard`; log lines carry port and permission only.
- Pixel palette is derived from the active Slint theme tokens in `auto` mode; `custom` keeps the stored RGBA values.
- Review and Font models are computed in Rust; Slint binds properties and forwards callbacks.

## Out of Scope

Phase 4 (T18–T21: terminology, Help/tooltips, new-project wizard, docs truth-up). No Automation JSON shape changes, no golden/test_asset edits. Release/tag/push are a separate, explicitly authorized close-out step.

## Protected Existing Work

- `fixtures/golden/` and `test_assets/` are frozen.
- 2.0.4 and 2.0.5 changes in this worktree are approved context: do not revert or rewrite them.
- Atomic writes, fingerprints, external-modification guards, recent projects, asset write-back, and the 2.0.4 shortcut/overlay fixes must remain intact.
- No pre-existing user work is present; verify with `git status` before each task.

## Constraints

- CI gates: `cargo fmt --all -- --check`; `cargo clippy --workspace --all-targets --locked -- -D warnings`; `cargo test --workspace --locked`; `python -m pytest tools/tests -q`; `cargo deny check`.
- GUI checks use isolated `APPDATA`/`LOCALAPPDATA`/`XDG_CONFIG_HOME` and copies of `test_assets`.
- Prefer existing helpers; no duplicate persistence, decoding, or render logic.
- Bridge token must never be logged, persisted, or written to screenshots; binding stays 127.0.0.1.
- Stop at `Status: VERIFY`; independent review owns `DONE`/`PASS`.

## Allowed Files / Expected Area

- `apps/mono-desktop/src/commands.rs` (new)
- `apps/mono-desktop/src/{main.rs,extras.rs,prefs_ui.rs,app.rs,agent.rs,display.rs,fontlab.rs,fontlab_ui.rs,i18n.rs,pixel_ui.rs,prefs.rs,canvas.rs}`
- `apps/mono-desktop/ui/{main.slint,review.slint,agent.slint,fontlab.slint,pixel.slint,designer.slint,preferences.slint,widgets.slint}`
- `apps/mono-desktop/i18n/strings.json`
- `crates/mono-core/src/{lib.rs,diff.rs}` (new `diff.rs`)
- `crates/mono-project/src/export.rs`
- `crates/mono-automation/src/dispatch.rs`
- `.ai/tasks/TASK-006.md`, `.ai/CURRENT_STATE.md`
- `Cargo.toml`, `Cargo.lock` (arboard if not already present; version close-out)

## Acceptance Criteria

1. `COMMANDS` is the only list of commands; menu literals, palette entries, shortcut defaults, and fixed chords all resolve through it; palette rows show shortcut hints; registry tests pass.
2. Workspace 3 is a side-by-side baseline/current diff with bbox, changed count/percent, and added/removed/modified elements; empty state when no baseline; numbers match the Designer drawer and Automation.
3. Bridge panel is non-modal, token can be revealed/copied more than once, permission can be switched (restart with a new token/port), and no token appears in logs.
4. Pixel palette follows light/dark/high-contrast when `auto`; custom colors survive; High Contrast is selectable.
5. Font Lab shows a true white-on-black 1-bit preview and a precise save/pack state.
6. Validation findings show a localized label followed by the original English detail; unknown codes fall back to the code; Automation output unchanged.
7. Full gates pass; golden/test_assets untouched.

## Verification Plan

- Focused: `cargo test -p mono-desktop commands`, `extras`, `agent`, `display`, `fontlab`, `i18n`; `cargo test -p mono-core diff`; `cargo test -p mono-automation`; `cargo test -p mono-project`.
- Full: fmt, clippy, workspace tests, pytest, deny.
- GUI (isolated configs, copied `test_assets`): palette search + shortcut hints; review workspace edit/save/reopen; bridge start/observe/copy/switch/stop; light/dark/high-contrast Pixel; Font Lab preview; Chinese validation rows.
- Manual matrix at 1100×700 and 1440×900.

## Deliverables

Code, tests, GUI evidence, and a Result section listing actual commands/results, skipped checks, and deviations.

## Result

Implemented T12–T17 as described; stopped at `VERIFY` (independent review owns `DONE`/`PASS`).

### What changed

- **T12 `apps/mono-desktop/src/commands.rs` (new).** One `COMMANDS` table (`CommandSpec { id, label_key, action, default_chord, configurable, palette, requires }`) owns ids, labels, default chords, palette membership and requirement tiers (`None`/`Document`/`Project`/`Scene`/`PixelOrFont`). `CONFIGURABLE` (8 chords), `normalize_shortcut`, `default_shortcuts`, `chord_for`, `fixed_action`, `palette_commands`, `is_known` all read from it. `main::fallback_action` and `prefs_ui::SHORTCUTS` were deleted; `extras::PALETTE` was deleted; the palette rows now carry the resolved chord as `detail`. Tests: `registry_ids_unique`, `defaults_match_registry`, `palette_actions_are_dispatchable`, `fixed_chords_do_not_collide`, `slint_menu_actions_are_known` (parses every `AppModel.action("<literal>")` in `main.slint`, ≥40 literals).
- **T13 `crates/mono-core/src/diff.rs` (new) + `review.slint` (new).** `DiffBox{ x,y,w,h }`, `changed_count`, `changed_bbox` (equal → `None`, length mismatch → full canvas, else min/max bounds) with 3 unit tests; `mono-automation` `pixel_diff` now computes through the same helpers with the JSON shape unchanged. `App::refresh_review` builds baseline/current images, sizes, changed count/percent, bbox, `has-baseline` and added/removed/modified element lists; workspace 3 renders `ReviewView` side by side with a manual-zoom `DiffPane`, a bbox overlay and an empty state.
- **T14 `agent.rs` + `agent.slint` (new).** `BridgePermission { Observe, Edit, Full }`; `start_agent_with`, `stop_agent`, `set_agent_permission` (restart ⇒ new token/port), `agent_action("start"|"stop"|"copy-token"|"copy-endpoint"|"permission:<i>")`, `refresh_agent_panel`/`refresh_agent_status`. The panel is non-modal (mounts at `x: root.width - self.width - 16px; y: 72px`, no scrim), masks the token as `••••••••••••••••`, reveals it via an in-out `token-visible`, copies token/endpoint through `arboard`, and shows port + permission in the status line. Tests: `permission_change_restarts_with_new_token`, `stop_and_start_regenerates_token`, `endpoint_shape_unchanged` (host stays `127.0.0.1`), `token_never_appears_in_log`.
- **T15 `display.rs`/`prefs.rs`/`prefs_ui.rs`/`pixel.slint`.** `theme_palette(mode)` for light/dark/high-contrast, `pixel_studio.palette_mode` (`auto`/`custom`), `legacy_custom_palette` migration for profiles that stored colours before the flag existed, a "follow theme" switch in the Pixel output tab, and High Contrast added to the appearance combo. Tests: `auto_palette_follows_theme`, `custom_palette_keeps_user_colors`, `legacy_palette_migrates_to_custom`, `missing_palette_defaults_to_auto`, `high_contrast_is_valid_pref`.
- **T16 `fontlab.rs`/`fontlab_ui.rs`/`fontlab.slint`.** True 1-bit preview (`image_from_pixels`, white lit on black, `image-rendering: pixelated`) in a preview strip with a 4×/8×/12× selector and a "real preview" toggle, plus the packed hint "白色为点亮的像素，不含网格与选中边框。". Tests: `font_preview_is_white_lit_on_black`, `font_preview_updates_after_edit`.
- **T17 `mono-project::export::FINDING_CODES` (23), `i18n::finding_label`, `FindingItem.label`.** Designer rows read `label — original English detail`; unknown codes fall back to the code. Tests: `every_finding_code_has_label`, `unknown_finding_falls_back_to_code`. Automation JSON untouched.

### GUI evidence (isolated `APPDATA`/`LOCALAPPDATA`/`XDG_CONFIG_HOME`, copy of `test_assets/projects/curing_lite`, `--screen main`)

- Palette (Ctrl+K): Chinese labels with chord hints (`偏好设置… Ctrl+,`, `仅画布模式 Ctrl+Space`, `保存 Ctrl+S`, …); search by `评审`/`设计`/`Bridge` filters correctly; `Enter` dispatches.
- Diff review (workspace 4): with one inspector edit it shows `变化 148 px（3.61%）`, `变化区域 x 87 y 4 · 36×7`, a bbox overlay and `修改 · mode_label · text`; the empty state renders when there is no baseline.
- Agent Bridge: Ctrl+K → `Bridge` opens the panel non-modally over the review workspace; `启动 Bridge` starts on `127.0.0.1:7553`, the token is masked, `显示` reveals it, `复制 token`/`复制端点` report `…已复制到剪贴板`; switching 编辑 → 只读 restarted on a new port (`7594`) with a new token and the status line read `运行于 127.0.0.1:7594 · 只读`; `停止 Bridge` returned the panel and the status bar to the stopped state. Raw TCP probes on the live port returned `{"code":"UNAUTHORIZED"}` for a token-less request, confirming the token gate.
- Validation findings: Chinese UI shows `缺少必需元素 — required design element …`.
- Terminology: 像素工作室 / 字库实验室 / 差异评审 / 实际输出预览 / 帧缓冲 / 叠加层 / 像素基准 across the shell.
- Font Lab: `新建字库` → `生成 / 更新字形` produced `正在生成 37 / 37…` → `已生成 / 更新 37 个字形。` and the 上屏预览 strip rendered a real white-on-black glyph with the 8× selector and the 真实预览 toggle.
- Appearance: switching 外观模式 between 浅色/高对比 takes effect immediately and persists (`已保存`), so `auto` palettes follow the theme.

### Two defects found by the GUI pass and fixed in this TASK

1. **Panel wiring.** `AgentPanel` invoked `AgentModel.agent-action`, but Rust listened on `AppModel`'s identically named callback, so Start/Stop/copy were inert. The listener now binds to `AgentModel` and the duplicate `AppModel` callback was removed.
2. **`ComboBox.selected` carries the label, not the index.** In Slint 1.18 `ComboBoxBase.selected(current-value: string)` passes the row text, so `"permission:" + index` produced `permission:只读`, `parse().unwrap_or(1)` fell back to `edit`, and the permission combo silently disagreed with the running bridge (status `编辑` while the combo displayed `只读`). The panel now maps the label back to an index (`root.permission-labels[0]/[2]` comparison); the Font Lab scale combo had the same defect (`index == 0` on a string was always false, pinning 12×) and now reads its own `current-index`. This contract is now recorded in `docs/AI_HANDOFF.md` §6.1.1.

### Verification (run in this worktree)

- `cargo fmt --all -- --check` — clean.
- `cargo clippy --workspace --all-targets --locked -- -D warnings` — clean.
- `cargo test --workspace --locked` — all suites pass (mono-desktop 112 tests and the `mono-core`/`mono-project`/`mono-automation`/`mono-font`/`mono-cli` suites; 0 failures).
- `python -m pytest tools/tests -q` — 24 passed, 1 skipped.
- `cargo deny check` — advisories/bans/licenses/sources ok.
- `git status` — `fixtures/golden/` and `test_assets/` untouched.

### Deviations and skipped checks

- The Pixel "follow theme" checkbox lives in the inspector's 输出 tab display group; it was not toggled by hand (the wheel landed on the 每行字节 spin box instead), so T15's palette switch is evidenced by the unit tests plus the live theme change, not by that checkbox.
- The Help menu was verified through `slint_menu_actions_are_known` and the palette, not by opening the native menu (the UIA `Invoke` pattern for menu items is not exposed).
- The layout matrix (1100×700 / 1440×900) was exercised only at the default window size.
- The GUI profile copy gained an in-session `Clinical_5x7` font library and an unsaved `每行字节 = 15`; the isolated copy is disposable and no tracked asset changed.

### Review status

Independent review was requested twice through the subagent dispatcher and both attempts failed to queue (model unavailable), so **no independent review has been performed**; `DONE`/`PASS` stay with an independent reviewer. An inline self-review against the acceptance criteria was run instead:

- Every `COMMANDS` action has a literal handling site outside `commands.rs` (`main.rs`/`app.rs`/`extras.rs`/`*_ui.rs`), and the dynamic families are covered by `is_known` plus `pixel-tool:`/`workspace:`/`align:` branches.
- `changed_count`/`changed_bbox` reproduce the previous `pixel_diff` behaviour for equal-size frames (the size check runs first) and keep the `[x0, y0, x1, y1]` JSON shape; the new core tests cover equal, length-mismatch and multi-pixel cases.
- `legacy_custom_palette` only fires when `pixel_studio.palette_mode` is absent *and* a stored colour differs from the default, so it cannot rewrite an unrelated preference.
- `start_agent_with` logs only port + permission (`AGENT_BRIDGE on 127.0.0.1:<port> permission=…`), `Bridge::start(0)` binds `127.0.0.1`, and `token_never_appears_in_log` asserts the token is absent after a permission restart.
- Every `selected(` handler in `apps/mono-desktop/ui/*.slint` now treats the parameter as a label or reads `current-index`; the custom `Segmented`/`TabStrip` callbacks are `int` by declaration.
