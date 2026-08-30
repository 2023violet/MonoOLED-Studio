# V12.3.2 UX Hardening

V12.3.2 keeps the V12.3 compact Preferences visual system and the V12.3.1 Settings Reliability Gate. This release hardens everyday workflows where a UI can appear functional while acting on the wrong context, losing unsaved work, or silently failing.

## UX invariants

1. **Settings is a command boundary.** While Settings is active, Save flushes pending preferences; Undo/Redo do not route into a hidden Scene, Pixel Studio, or Font Lab editor.
2. **Search is jump-to, not layout mutation.** Search may navigate and highlight a setting, but highlight styling must not change row geometry. Matching help text and bilingual aliases are searchable; offscreen matches are scrolled into view. `Ctrl+F` is scoped to Settings and `Esc` clears the query.
3. **Preference feedback is non-blocking but explicit.** Saving, save success, save failure, shortcut conflicts, and search misses have visible/accessibility feedback without permanently consuming layout space.
4. **Imported source assets are never overwritten by format conversion.** Pixel Studio `save_png()` always produces PNG. A non-PNG source (JPG/BMP/etc.) requires Save As rather than overwriting the imported file.
5. **Save As migrates editor identity.** When an embedded Pixel editor moves from one asset path to another, `EditorRegistry` rekeys the same editor so later tab activation, close, runtime preference broadcasts, and duplicate-open detection use one identity.
6. **Dirty state is editor-level.** Font Lab metric edits count as unsaved work even when the current glyph bitmap itself is clean. Tab close and application exit check the editor-level dirty contract.
7. **Save means save succeeded.** Choosing Save and then cancelling Save As, encountering a write error, or remaining dirty aborts tab/application close.
8. **Workspace replacement is transactional.** Screen switches and deletion guard the active Scene. Opening/New Project or opening an arbitrary Scene additionally guards dirty auxiliary editors. Invalid target files are loaded/preflighted before old project-bound editors are discarded.
9. **Language is complete across the workbench.** Scene, Settings, and Font editor tab titles retranslate together; current configured shortcuts remain truthful in tooltips.
10. **Popup keyboard behavior follows focus.** StudioSelect keyboard open/close is handled on its real focus proxy, not only the outer wrapper.

## Regression gates

Source behavior is covered by `tests/test_v1232_ux_hardening.py`. Real Qt interactions are covered by `tests/test_qt_v1232_ux_hardening.py` and are automatically included in the Windows Real-Qt inventory used by the GA release workflow.

V12.3.2 does not weaken the V12.3.1 requirements: the Windows GA must still run the Settings DPI matrix, 500-cycle Settings soak, visual golden capture, packaged EXE Settings smoke, and packaged EXE Settings soak with zero unexpected skips.
