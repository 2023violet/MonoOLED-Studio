# MonoOLED Studio 8.4 — Final Project & Code AI Closure Complete Delivery

This package is the complete incremental source/product delivery built on the verified V8.3 tree.

## Release identity

- Product: **MonoOLED Studio**
- Version: **8.4.0**
- Release: **Final Project & Code AI Closure**
- Automation API: **1.0.0**

## What V8.4 closes

V8.4 preserves the V8.3 reliability/performance work and adds the final project-level Code AI orchestration layer: machine-readable capabilities/schema, Screen lifecycle, state enumeration/all-state proof, asset/pixel lifecycle, preview feedback and Studio-owned export/handoff.

## Important Windows boundary

The included root `MonoOLEDStudio.exe` remains the compatibility runtime-locator binary retained from the verified baseline. The updated V8.4 launcher source and the authoritative self-contained Windows application must be built on Windows through:

```text
Developer_Tools\BUILD_WINDOWS_EXE.bat
```

The Windows gate rejects any failed **or skipped** Real-Qt test.

For source/development use on an installed Python 3.13 + PySide6 machine, use:

```text
Developer_Tools\CREATE_RUNTIME_ENV.bat
```

## Code AI

Read:

- `OLED模拟器/AUTOMATION_API_V1.json`
- `OLED模拟器/CODE_AI_AUTOMATION_API_V1.md`
- `OLED模拟器/FINAL_PROJECT_CODE_AI_CLOSURE_V84.md`

An Agent should begin with `automation.capabilities` rather than assuming available commands.
