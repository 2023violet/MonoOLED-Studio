# MonoOLED Studio 8.2 Test Matrix

## Host/Core gate

- Complete existing test suite.
- V8.2 popup state-machine tests.
- Production Select inventory contract: 7 Designer + 10 Preferences + 3 Pixel = 20 core StudioSelect construction points.
- Content-aware popup sizing contract.
- Preferences semantic-surface contract.
- Frozen assets and Golden verification.

## Adversarial V8.2 stress

- 1,000 malformed Preferences payloads.
- 432 theme/mode/language/density/UI-scale semantic combinations.
- 10,000 runtime Preference transitions.
- 20,000 generic popup screen-geometry cases.
- **100,000 PopupStateMachine transitions.**
- **50,000 popup content-sizing + screen-placement cases.**
- 60 theme/density/UI-scale semantic-surface stylesheet cases.
- 120 responsive layout cases.
- 10,000 Selection transitions.
- 30,000 PixelDocument operations.
- deterministic FontPack generation.
- 1,000 Automation/JSON-RPC calls.
- 1,400 deterministic Renderer frames.

## V8.2 Real-Qt interaction gate

`tests/test_qt_v82_studio_select_state_machine.py` validates the reported user paths with real `QTest` events:

1. first anchor click opens;
2. second anchor click closes and stays closed after later event-loop turns;
3. public `showPopup()/hidePopup()` API;
4. item commit closes before signals;
5. narrow Snap popup is not forced to 180 px;
6. only one Studio popup visible;
7. popup content screenshot is alpha-opaque and cannot reveal a deliberately red bleed-through surface underneath;
8. Escape closes without changing selection;
9. item visual rectangles do not overlap.

`tests/test_qt_v82_preferences_theme_surface.py` validates:

- One Dark Preferences content area raster is dark instead of a native white page;
- all Preferences StudioSelect instances can open/close through the production API;
- changing Preferences page closes the old page popup.

## Windows DPI gate

All existing V8.1 Real-Qt tests plus V8.2 tests run at:

- 100%
- 125%
- 150%
- 175%
- 200%
- 225%
- 250%
- 300%

A Windows GA build must have **0 failed / 0 skipped Real-Qt V8.2 tests**.

## Product invariants

Appearance/language/popup changes must not change:

- product Scene data;
- framebuffer bytes;
- 14 clinical Golden hashes;
- 464 frozen asset hashes;
- active document content.
