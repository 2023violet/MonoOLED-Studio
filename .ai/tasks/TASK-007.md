# TASK-007 — 2.2.0 Polish and Governance (Phase 4)

Status: VERIFY
Review Status: PENDING

## Goal

Implement the approved plan's Phase 4 (T18–T21): one term per concept in the Chinese UI (T18), Help menu entries plus hover tooltips and visible Pixel tool labels (T19), a New Project wizard instead of a bare folder picker (T20), and doc/version truth so `DESIGN_SYSTEM.md`, `AI_HANDOFF.md`, `README` index and release notes match the code (T21). Ship as 2.2.0 without changing Automation JSON, golden fixtures, or the frozen test assets.

## Background

Phases 1–3 (2.0.4, 2.0.5, 2.1.0) are in this worktree; TASK-004, TASK-005 and TASK-006 cover them (TASK-006 stops at `VERIFY`). The approved plan is `C:\Users\16429\.qoder\plans\faint-pool-trout.md`; this TASK covers its Phase 4 only. The CXO report found mixed terminology (Scene 被译成"页面/屏幕"), no in-app way to reach shortcuts/manual/support, icon-only Pixel tools, a bare folder picker for New Project, and design/handoff docs that still described pre-2.0 behaviour.

## Current Problem

- The Chinese UI mixed 页面/屏幕/场景 for the same concept and used several half-translated labels.
- Help had no Shortcuts/Manual/Report entry; icon-only buttons had no hover hint; Pixel tool buttons had no visible label and the selection outline was ambiguous on dark and light palettes.
- New Project asked only for a folder and then derived everything silently, with no way to name the project or set a canvas, and no validation before writing.
- `docs/DESIGN_SYSTEM.md` described the V1 `theme_system.py` palette; `AI_HANDOFF.md` lacked the 2.0.4–2.2.0 contracts; the version lived in four places with nothing keeping them equal.

## Evidence

- `apps/mono-desktop/i18n/strings.json` (zh_CN values), `apps/mono-desktop/ui/*.slint` labels
- `apps/mono-desktop/ui/main.slint` Help menu, `apps/mono-desktop/src/main.rs` `handle_action`
- `apps/mono-desktop/ui/widgets.slint` (`Button`, `IconButton`), `apps/mono-desktop/ui/pixel.slint` (`ToolRail`, selection overlay)
- `apps/mono-desktop/src/app.rs` `new_project`, `apps/mono-desktop/ui/new_project.slint`
- `docs/DESIGN_SYSTEM.md`, `docs/AI_HANDOFF.md`, `docs/README.md`, `Cargo.toml`, `.ai/CURRENT_STATE.md`, `CHANGELOG.md`

## Required Changes

1. **T18 — terminology:** one term per concept across the shell (场景 for the scene container, 像素工作室, 字库实验室, 差异评审, 实际输出预览, 帧缓冲, 叠加层, 像素基准, 生成位图数组), rewritten zh_CN values in `strings.json`, and a glossary appended to both user guides.
2. **T19 — help and affordances:** Help menu entries Keyboard Shortcuts / User Manual / Report an Issue wired to real actions; `Tooltip` on icon buttons and ordinary buttons via `changed has-hover`; visible short labels on Pixel tool buttons plus a contrasting outer stroke on the pixel selection outline.
3. **T20 — New Project wizard:** `new_project.slint` + `App::new_project` with a name (defaults to the folder name), canvas width/height (default 128×32), inline validation (height must be a positive multiple of 8) and no half-written project on failure.
4. **T21 — docs and version truth:** rewrite `DESIGN_SYSTEM.md` around `theme.slint`/`widgets.slint`; extend `AI_HANDOFF.md` with the 2.0.4–2.2.0 contracts; index the new docs in `docs/README.md`; add `tools/tests/test_version_consistency.py` tying `Cargo.toml`, `ui/main.slint`, `.ai/CURRENT_STATE.md` and `CHANGELOG.md` together.

## Architecture

- Terminology changes live only in `i18n/strings.json` values; keys stay stable so code and tests do not move.
- Help actions dispatch through the same `commands.rs` registry as the menu and palette (`shortcuts`, `open-docs`, `report-issue`), so no fourth command list appears.
- The wizard is a Rust-validated model (`NewProjectModel`) plus a thin dialog; the folder comes from `rfd`, the name/size from the dialog, and creation only runs after validation.
- Docs describe the current truth; the version test makes drift a CI failure instead of a review task.

## Out of Scope

Release, tagging and pushing are a separate, explicitly authorized close-out step. No Automation JSON shape changes, no golden/test_asset edits, no new features beyond the four items above.

## Protected Existing Work

- `fixtures/golden/` and `test_assets/` are frozen.
- The 2.0.4–2.1.0 changes in this worktree are approved context: do not revert or rewrite them.
- Atomic writes, fingerprints, external-modification guards, recent projects, asset write-back, save points, the command registry and the bridge token rules must remain intact.
- No pre-existing user work is present; verify with `git status` before each task.

## Constraints

- CI gates: `cargo fmt --all -- --check`; `cargo clippy --workspace --all-targets --locked -- -D warnings`; `cargo test --workspace --locked`; `python -m pytest tools/tests -q`; `cargo deny check`.
- GUI checks use isolated `APPDATA`/`LOCALAPPDATA`/`XDG_CONFIG_HOME` and copies of `test_assets`.
- New user-facing text needs both `en_US` and `zh_CN` values; `i18n` tests fail on missing keys.
- Bridge token must never be logged, persisted, or written to screenshots; binding stays 127.0.0.1.
- Stop at `Status: VERIFY`; independent review owns `DONE`/`PASS`.

## Allowed Files / Expected Area

- `apps/mono-desktop/i18n/strings.json`
- `apps/mono-desktop/src/{app.rs,main.rs,commands.rs,extras.rs}`
- `apps/mono-desktop/ui/{main.slint,widgets.slint,pixel.slint,new_project.slint}`
- `docs/{DESIGN_SYSTEM.md,AI_HANDOFF.md,README.md,USER_GUIDE_CN.md,USER_GUIDE_EN.md}`
- `tools/tests/test_version_consistency.py` (new)
- `AGENTS.md`, `CHANGELOG.md`, `Cargo.toml`, `Cargo.lock`, `.ai/tasks/TASK-007.md`, `.ai/CURRENT_STATE.md`

## Acceptance Criteria

1. The Chinese UI uses one term per concept wherever the concept appears.
2. Help offers Shortcuts, the manual and issue reporting, and all three resolve through the command registry; icon/ordinary buttons show tooltips; Pixel tools carry visible labels and the selection outline stays legible on every palette.
3. New Project validates name/canvas before writing, defaults the name from the folder, rejects a height that is not a multiple of 8 with an inline error, and cancels cleanly.
4. `DESIGN_SYSTEM.md`/`AI_HANDOFF.md` describe the current code; `docs/README.md` indexes them; the version-consistency test passes and fails on drift.
5. Full gates pass; golden/test_assets untouched.

## Verification Plan

- Focused: `cargo test -p mono-desktop new_project`, `i18n`, `prefs`; `python -m pytest tools/tests/test_version_consistency.py -q`.
- Full: fmt, clippy, workspace tests, pytest, deny.
- GUI (isolated configs, copied `test_assets`): Chinese terminology sweep; Help entries; tooltips and Pixel tool labels; New Project name/size/validation/cancel; layout at the default window size.
- `git status` and `git diff --stat` to confirm the frozen assets are untouched.

## Deliverables

Code, tests, GUI evidence, and a Result section listing actual commands/results, skipped checks, and deviations.

## Result

Implemented T18–T21 as described; stopped at `VERIFY` (independent review owns `DONE`/`PASS`).

### What changed

- **T18 terminology.** Rewrote ~30 zh_CN values so one term maps to one concept: 场景 for the scene container, plus 像素工作室 / 字库实验室 / 差异评审 / 实际输出预览 / 帧缓冲 / 叠加层 / 像素基准 / 生成位图数组; keys were left unchanged so code and tests did not move. Added a glossary appendix to `docs/USER_GUIDE_CN.md` and `docs/USER_GUIDE_EN.md`. GUI check: the shell, the Designer footer (`像素基准：规范渲染器 · VLSB · 1 = OLED 点亮`), the canvas note (`选中框与网格仅属于编辑器叠加层，不进入帧缓冲`) and every workspace tab read consistently in Chinese.
- **T19 help and affordances.** Help menu now offers Keyboard Shortcuts (`shortcuts`), the User Manual (`open-docs`: local `docs/USER_GUIDE_CN.md`/`USER_GUIDE_EN.md` when present, otherwise the GitHub copy) and Report an Issue (`report-issue`); all three live in `commands.rs` and open through `open_local_or_url` (`cmd /C start` / `open` / `xdg-open`). `widgets.slint` gained an exported `Tooltip` (`PopupWindow` shown from `changed has-hover`) used by icon buttons and ordinary buttons; Pixel tool buttons got visible short labels (铅笔/橡皮/直线/矩形/填充/选择) and a 94 px rail; the pixel selection outline draws a contrasting 1 px outer stroke (`#000000` on dark palettes, `#FFFFFF` on light) in addition to the existing 2 px `canvas-selection`. Verified in the GUI: the palette lists the shortcut entry and the Pixel rail shows labelled tools.
- **T20 New Project wizard.** `new_project.slint` (`NewProjectModel { visible, name, canvas-w:128, canvas-h:32, error }`) plus `App::new_project` → `create_project`; the name defaults to the folder name when empty, `canvas.0 > 0 && canvas.1 > 0 && canvas.1 % 8 == 0` is enforced before anything is written (a validation failure cannot leave files behind), and creation/IO failures surface as an inline error — `create_project` makes the directories before it writes, so an IO failure can leave the empty directories it had already created. The File menu / palette `新建项目…` (Ctrl+N) opens the wizard, which picks the folder through `rfd` on Create. Tests: `new_project_uses_requested_size`, `new_project_rejects_invalid_size`, `new_project_derives_name_from_folder_when_empty`. GUI check: `新建字库`-style modal layout confirmed for the dialog family; the wizard itself is covered by those tests.
- **T21 docs and version truth.** `docs/DESIGN_SYSTEM.md` rewritten around `theme.slint`/`widgets.slint` as the current truth (three theme modes, token tables, density, component/layout/accent rules); `AI_HANDOFF.md` §5.4 updated for `commands.rs`, the review workspace, asset origin/write-back and the bridge panel, with a new §6.1.1 listing the save-point, asset write-back, output-profile, recent-project, command-registry, finding-label and Slint `ComboBox` contracts; `docs/README.md` indexes the new material; `ui/theme.slint`'s header now states it is the current truth. `tools/tests/test_version_consistency.py` asserts `Cargo.toml [workspace.package].version` == `ui/main.slint` `version:` == `- Product version:` in `.ai/CURRENT_STATE.md` == a matching `## <version> - YYYY-MM-DD` heading in `CHANGELOG.md`; `CHANGELOG.md` gained 2.1.0 and 2.2.0 entries and `AGENTS.md` points at the changelog for known gaps.

### Verification (run in this worktree)

- `cargo fmt --all -- --check` — clean.
- `cargo clippy --workspace --all-targets --locked -- -D warnings` — clean.
- `cargo test --workspace --locked` — all suites pass (0 failures).
- `python -m pytest tools/tests -q` — 24 passed, 1 skipped, including `test_version_consistency.py`.
- `cargo deny check` — advisories/bans/licenses/sources ok.
- `git status` — `fixtures/golden/` and `test_assets/` untouched.

### Deviations and skipped checks

- The Help menu was verified through the registry test and the palette rather than by opening the native menu (the computer-use UIA `Invoke` pattern is not exposed for menu items).
- The New Project wizard was verified by unit tests and by the dialog family rendering in the GUI; the folder picker step was not driven end-to-end by hand.
- The 1100×700 / 1440×900 layout matrix was only exercised at the default window size.
- `agent.panel.stopped` read as the bare 未运行/Stopped when used as a status-bar message; it is now "Bridge 已停止"/"Bridge stopped" (found during the TASK-006 GUI pass and fixed here).

### Review status

Independent review was requested twice through the subagent dispatcher and both attempts failed to queue (model unavailable), so **no independent review has been performed**; `DONE`/`PASS` stay with an independent reviewer. An inline self-review checked:

- `legacy_custom_palette` fires only when `pixel_studio.palette_mode` is absent and a stored colour differs from the default; `merge` runs before the flag is set, so no other preference is rewritten.
- `App::new_project` validates size before calling `create_project`; `create_project` refuses to touch an existing manifest/main scene and writes directories first, so an IO failure can leave empty directories (documented) but never a project file.
- Every `selected(` handler in `ui/*.slint` treats the parameter as a label or reads `current-index`; `Segmented`/`TabStrip` declare `callback selected(int)` and pass an index.
- `tools/tests/test_version_consistency.py` reads the same four sources the release workflow checks (`Cargo.toml` version, `ui/main.slint` default, `CURRENT_STATE`, a `## <version> - ` changelog heading).