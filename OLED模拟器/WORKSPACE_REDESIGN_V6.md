# MonoOLED Studio 6.0 Workspace Redesign

## Why this release exists

V5.x accumulated strong rendering, project, validation and export capabilities, but the GUI still behaved too much like a Bento dashboard. The resulting costs were excess vertical chrome, repeated card padding, poor information prioritization and an expensive drag event chain.

## Frozen architectural decision

Keep the existing Core. Replace only presentation and interaction orchestration.

- Machine truth: Project + Scene JSON.
- Pixel truth: Canonical Renderer.
- UI shell: PySide6/Qt professional workspace.
- Drag preview must never create a second renderer.

## Main decisions

1. Canvas-first layout.
2. Contextual Inspector; Runtime/Canvas Settings moved to State tab.
3. Problems/Diff/Log become a bottom drawer.
4. Design and Review are explicit modes; Pixel Studio is a task-specific workspace.
5. Splitter layout is persisted.
6. Compact mode hides lower-priority chrome before shrinking the canvas.
7. Fast drag preview defers validation/evidence to commit.
8. PerformanceProfiler records bounded preview/full-refresh timing samples.
9. Pixel selection can be moved directly and undone as one operation.

## Windows release gate

The Windows workflow executes:

- full source regression
- pytest-qt real interactions
- professional workspace interactions
- 100/125/150/200% DPI matrix
- layout smoke
- interaction smoke
- soak smoke
- PyInstaller onedir build
- EXE window/core checks
