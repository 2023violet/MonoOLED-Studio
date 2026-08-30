# V12.3.3 Resilience Hardening

V12.3.3 keeps the V12.3 Compact Preferences presentation, the V12.3.1 Settings Reliability Gate, and the V12.3.2 UX/data-safety transaction fixes. This release hardens failure paths that previously surfaced as confusing or unsafe desktop behavior.

## Closed failure paths

- Corrupt or unsupported image files now produce a stable user-visible import error instead of leaking Pillow exceptions through a Qt slot. Missing files remain `FileNotFoundError`; permission failures remain explicit OS errors.
- Pixel Studio PNG, BIN, and C-header actions catch write/validation failures and keep the editor state intact.
- Pixel PNG/BIN/C-header outputs use the shared atomic I/O path. Replacement failure preserves the previous target and removes the temporary file; PNG dirty state is only cleared after the atomic replace succeeds.
- Font Lab catches save failures. When changing glyphs, a failed autosave blocks the selection transition and restores the previous glyph selection so unsaved pixels are not silently abandoned.
- Autosave timer write failures no longer escape the timer slot. The status surface reports `Autosave failed`, exposes the underlying error as a tooltip, records `AUTOSAVE_FAIL`, and keeps the document dirty for a later retry.

## Active reliability baseline

V12.3.3 does not weaken previous gates. Windows GA must still execute the V12.3.1 Settings DPI matrix, Settings 500-cycle soak, visual golden capture, packaged EXE Settings smoke/soak, plus the V12.3.2 workflow/data-safety regressions.

## Release identity

- Source version: `12.3.3`
- Git tag: `v12.3.3`
- Windows asset: `MonoOLEDStudio_v12.3.3_Windows_x64.zip`
