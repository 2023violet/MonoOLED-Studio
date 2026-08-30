# V12.3.4 Autonomous Quality Hardening

V12.3.4 is an autonomous audit and hardening pass on top of V12.3.3. It deliberately avoids another visual redesign. The priority is user trust: an action must target the visible editor, destructive transitions must be transactional, failed writes must not partially mutate state, and creating/opening resources must never overwrite unrelated data.

## Closed issues

- Command Palette Save/Undo/Redo route through the active editor instead of always targeting the Scene.
- Pixel Studio asks before replacing a dirty document with Open Image.
- Pixel document identity is rekeyed when Open Image changes the active asset, without faking a save event.
- Pixel Open/Save As refuses a path already owned by another Pixel tab.
- Restore Autosave validates the recovery payload and protects the dirty Scene before replacement.
- Project/Scene/Screen transitions validate the target before prompting or committing.
- Screen activation rolls back the in-memory active screen when manifest persistence fails.
- Screen deletion validates the fallback Scene before deleting the current screen.
- ProjectWorkspace add/remove/asset-dir mutations roll back in-memory state on persistence failure.
- New projects and new screens refuse to overwrite existing project manifests or untracked Scene files.
- Multi-element delete is one atomic batch edit and one Undo/Redo step.
- All batch edits roll back partial mutations when the mutator raises.
- New Font Pack refuses to overwrite an existing pack; Open Font requires an existing fontpack.json.
- Pixel/Font constructors and Bitmap Text insertion surface user-facing errors rather than leaking Qt-slot exceptions.
- Last-project preference persistence is non-fatal and standalone Scene opening clears the stale project pointer.
- Shutdown preference write failure is logged without crashing the close path.

## Verification contract

`tests/test_v1234_autonomous_quality_hardening.py` is the regression contract for this pass. Existing V12.3.1 Settings Real-Qt/DPI/soak/visual gates, V12.3.2 UX/data-safety tests, and V12.3.3 resilience tests remain mandatory.

Release identity:

- Source version: `12.3.4`
- Git tag: `v12.3.4`
- Windows asset: `MonoOLEDStudio_v12.3.4_Windows_x64.zip`
