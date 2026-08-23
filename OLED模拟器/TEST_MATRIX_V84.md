# MonoOLED Studio 8.4 — Test Matrix

## Host/Core gate

- all legacy V5–V8.3 regression suites;
- Automation API 1.0 direct project graduation;
- localhost JSON-RPC graduation;
- project Screen CRUD/reopenability;
- asset/pixel lifecycle;
- 560-state representative clinical enumeration/render/validation;
- canonical export/handoff;
- V8.2 adversarial UI-core stress;
- V8.3 reliability/performance stress;
- V8.4 final project/Code-AI gate;
- package integrity and frozen product truth;
- Python compileall;
- Windows-target launcher C syntax check on the packaging host.

## Windows Real-Qt mandatory gate

The Windows builder discovers **all** `test_qt_*.py` modules, including `test_qt_v84_project_automation.py`, and runs them at:

`100 / 125 / 150 / 175 / 200 / 225 / 250 / 300 %`.

JUnit is rejected if any test is skipped. Real-window startup/layout/interaction/soak smokes also run against the PyInstaller onedir executable.

## Code AI graduation acceptance

An Agent-capable service must successfully:

1. discover API and schemas;
2. create and open a Screen;
3. create and edit a Pixel asset;
4. bind it into the Scene;
5. render and validate canonical truth;
6. save the Project;
7. generate a Studio-owned handoff;
8. reopen the Project with the new Screen intact;
9. repeat capability/project observation through the localhost JSON-RPC transport.

## Release truth

Host PASS is not interpreted as Windows Real-Qt PASS. Windows GUI/standalone evidence is produced only by the Windows gate.
