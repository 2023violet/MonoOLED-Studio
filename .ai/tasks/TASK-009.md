# TASK-009 — 2.3.0 device preview and review loop

Status: VERIFY
Review Status: PENDING

## Goal

Turn the static Designer preview into a device-level verification and review
loop, and surface the evidence the exporter already produced: real playback and
runtime events, a committable annotation sidecar, Review's code/device dual view
with contract evidence, a screen gallery overlay, and a deterministic offline
review pack. No scene-schema, Automation-JSON, golden-fixture or
`test_assets/` changes.

## Background

The 2.2.x Designer could only edit a generic state and describe a position
(`ui/designer.slint` State tab); the Play button was dead because Rust never set
`playing` and simply called `step(1)`; runtime events never reached the GUI;
screens were a flat text list without thumbnails; the Review baseline lived only
in memory and had no C-code view; and annotations were limited to computed
validation findings. Meanwhile `render_scene`, `framebuffer_to_c_header`,
`hex_spaced`, `atomic_write`, the background-job runner and the command registry
already provided everything needed to close that loop.

## Planned work (T22–T28)

| Task | Delivered |
| --- | --- |
| T22 | `VecRuntimeLog`, `SceneRuntime::attach`, `*_logged` editor calls, `preview.rs`, 60 ms playback tick, device bezel, event feed, boundary caption |
| T23 | `crates/mono-project/src/review.rs`: `review/review.json` sidecar (atomic write, fingerprint refusal, quarantine, schema guard) |
| T24 | Annotations UI (`ui/notes.slint`), stale badge, derived presets, named scenarios |
| T25 | `export::frame_for_state`, Review Device/Code switch, evidence panel, contract discovery/adoption, copy hash |
| T26 | Gallery overlay (`ui/gallery.slint`, `src/gallery.rs`), worker + fingerprint cache, search/filters/badges, open in Designer/Review |
| T27 | `crates/mono-project/src/review_pack.rs`, `mono review-pack`, File → Review pack |
| T28 | Docs, i18n, version 2.3.0 |

## Evidence (implementer)

- Playback: `crates/mono-core/src/runtime.rs` (`RuntimeRecord`, `VecRuntimeLog`,
  `attach`), `crates/mono-project/src/editor.rs` (`step_logged`,
  `reset_runtime_logged`, `set_state_logged`, `fingerprint`),
  `apps/mono-desktop/src/preview.rs`, `apps/mono-desktop/src/app.rs`
  (`preview_step`, `preview_reset`, `preview_tick`), `src/main.rs` timer.
- Review sidecar: `crates/mono-project/src/review.rs` (+ `read_annotations`).
- Annotations and presets: `apps/mono-desktop/ui/notes.slint`,
  `src/app.rs` (`begin_note` … `save_scenario`, `build_presets`).
- Review evidence: `crates/mono-project/src/export.rs::frame_for_state`,
  `ui/review.slint`, `src/app.rs` (`evidence_view`, `adopt_contract`,
  `discover_contract`, `copy_frame_hash`).
- Gallery: `apps/mono-desktop/src/gallery.rs`, `ui/gallery.slint`,
  `src/app.rs` (`ensure_gallery`, `fill_gallery`, `gallery_stamp_value`).
- Review pack: `crates/mono-project/src/review_pack.rs`,
  `apps/mono-cli/src/main.rs` (`cmd_review_pack`), `src/app.rs`
  (`start_review_pack`), `ui/main.slint` (File/View menu).
- Version truth: `Cargo.toml`, `apps/mono-desktop/ui/main.slint`,
  `CHANGELOG.md`, this file and `.ai/CURRENT_STATE.md` all report 2.3.0.

## Verification (commands actually run)

- `cargo fmt --all -- --check`
- `cargo clippy --workspace --all-targets --locked -- -D warnings`
- `cargo test --workspace --locked`
- `python -m pytest tools/tests -q`
- `cargo deny check`
- CLI: `mono review-pack` twice → identical SHA-256 and byte-identical files.
- GUI (isolated `APPDATA`/`LOCALAPPDATA`/`XDG_CONFIG_HOME`, project copy):
  device bezel + play/pause/step/reset + event feed; note create/edit/delete
  writing `review/review.json`; Review Device/Code with `golden match`; gallery
  search/filters and the 评审 action opening Review; review pack opened in a
  headless browser (frames, annotation card, elements, hash).

## Defects found during GUI verification and fixed here

- The annotation dialog stretched its combo/title/body rows over the whole
  scrim; the dialog now has an explicit 520×400 size with stretch on the body
  only.
- Note rows hid their Edit/Delete buttons because `shrink` buttons had no width;
  the row was restructured and the buttons sized explicitly.
- The two diff panes had different widths (title-dependent preferred width), so
  the same frame rendered at two zoom factors; both panes now start at zero
  preferred width.
- `Ctrl+Shift+G` collided with an existing fixed chord, so the gallery command
  uses `Ctrl+Shift+L`.
- The playback controls were below presets and state rows, so the headline
  feature was off-screen; Play/Step/Reset and the runtime position now sit
  directly under the device bezel.

## Out of scope

No key/hardware event model, no motor/buzzer/BLE/power simulation, no second
renderer or L2 badge, no fifth workspace tab (gallery is an overlay), no
Automation JSON or scene-schema change, no cross-screen persistent baseline, no
annotation replies/status transitions, and no Automation write API for
annotations.

## Result

Implemented and verified locally as described above. `DONE`/`PASS` remain with
an independent reviewer, per `.ai/README.md`.
