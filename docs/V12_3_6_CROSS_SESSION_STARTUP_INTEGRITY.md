# V12.3.6 Cross-Session & Startup Integrity Hardening

V12.3.6 is an autonomous cross-session integrity pass on top of V12.3.5. It does not redesign the UI. It closes cases where a previous session, a second application instance, an external editor, or a crash residue could cause MonoOLED Studio to start incorrectly or overwrite newer data.

## 1. Startup restoration

`startup.last_project` is no longer trusted merely because the path exists. The stored project is prevalidated through the normal project manifest and active-scene load path before the main window is constructed. A missing, corrupt, unsupported, or otherwise unloadable remembered project is ignored and the application falls back to its normal startup source. The invalid remembered path is cleared on a best-effort basis so the same bad restore is not attempted indefinitely.

Shortcut conflict repair during startup is also non-fatal. If a repaired shortcut map cannot be persisted, the current session still starts with the safe in-memory bindings and records a diagnostic warning.

## 2. External modification protection

`SceneDocument` and `ProjectWorkspace` now retain content fingerprints for the disk state they loaded. Before replacing an existing scene or project manifest, the save boundary verifies that the disk content still matches that baseline.

If another MonoOLED Studio instance or an external tool has modified the file, save is refused instead of silently applying last-writer-wins. The external file remains untouched and the local document remains dirty so the user can explicitly reconcile the conflict.

Successful saves refresh the baseline fingerprint, so ordinary consecutive saves do not produce false positives. Scene fingerprints are bound to the path they describe, so Save-As/new-target flows do not reuse a stale fingerprint from the original file.

## 3. Windows-safe project identity

Screen IDs and screen paths are now checked with case-insensitive comparison in addition to their exact identity. A project cannot contain `HOME` and `home`, nor two screen entries that resolve to paths differing only by case. This prevents projects that work on a case-sensitive development filesystem but collide on Windows.

Same-ID label edits are transactional: if manifest persistence fails, the in-memory project returns to its prior state.

## 4. Transactional preferences

`PreferencesStore.set(..., save=True)` and `reset_section()` now roll back their in-memory mutation when persistence fails. A failed synchronous preference write therefore cannot leave the application believing a setting was committed when disk still contains the previous value.

The asynchronous Settings view continues to support deliberately pending in-memory changes with explicit save-failure feedback; the rollback rule applies to synchronous commit APIs.

## 5. Multi-instance temporary-file isolation

Atomic output now uses unique temporary siblings instead of a fixed `target.tmp` name. The shared atomic writer, Preferences, project manifest, Asset Library cache, Autosave, and Handoff ZIP paths all avoid cross-process temporary-file collisions while retaining same-directory atomic replacement semantics.

## 6. Session log recovery

GUI session log filenames include microseconds and the process ID, reducing collisions when multiple application instances start at nearly the same time.

Markdown session-report generation is tolerant of a truncated/corrupt JSONL record. Valid records are retained in the report and the damaged line is marked as skipped instead of causing the entire report to fail. Session Markdown generation remains an auxiliary shutdown artifact: a report failure is logged but cannot block application exit.

## 7. Verification contract

V12.3.6 adds `tests/test_v1236_cross_session_integrity.py`, covering:

- transactional preference rollback;
- Windows case-insensitive screen ID/path collision rejection;
- same-ID screen-label rollback;
- remembered-project prevalidation;
- unique atomic temporary siblings;
- external Scene/project modification detection and baseline refresh;
- crash-tolerant Session Markdown;
- non-fatal shutdown report and startup shortcut repair behavior.

The complete Source Gate and deterministic independent-package verification remain mandatory before release. Native PySide6/Real-Qt behavior is still certified by the Windows GA workflow rather than inferred from Linux source tests.

## 8. Release identity

- Source version: `12.3.6`
- Git tag: `v12.3.6`
- Windows asset: `MonoOLEDStudio_v12.3.6_Windows_x64.zip`
- Windows checksum: `MonoOLEDStudio_v12.3.6_Windows_x64.zip.sha256`
