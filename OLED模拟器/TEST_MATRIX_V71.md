# MonoOLED Studio 7.1 — Verification Matrix

## A. Host/Core gates

| Domain | Gate |
|---|---|
| Preferences | malformed JSON, semantically malformed values, unknown/future key preservation, atomic save |
| Runtime wiring | every public default Preference has a named runtime effect |
| Commands | atomic shortcut rebinding and conflict rejection |
| Project | screen ID/path confinement; asset-root confinement |
| Assets | content-hash cache invalidation; import-target confinement |
| Autosave | atomic write; newest-invalid fallback; quarantine |
| PixelDocument | left/right semantics, interpolation, brush footprint, undo bound, VLSB length |
| Import | image pixel/dimension pre-allocation guard |
| C export | strict ASCII identifier normalization |
| Theme | complete semantic tokens; primary/muted contrast pair floor; mode resolution; UI scale |
| Renderer | existing canonical render/validation/export tests plus 1,400-frame deterministic stress |
| Clinical | 560 state combinations without ERROR/BLOCKER |
| Frozen truth | 464 product assets and 14 × 512B Golden hashes pinned to V7.0 |

## B. Adversarial stress gates

Executed by `Developer_Tools/VERIFY_V71_STRESS.py`:

- Preferences semantic fuzz: 1,000 payloads;
- PixelDocument randomized stress: 60 documents × 500 operations = 30,000 operations;
- Renderer stress: 14 clinical states × 100 cycles = 1,400 frames;
- VLSB byte-size invariant on every randomized PixelDocument operation;
- deterministic SHA-256 for every clinical state across all renderer cycles;
- frozen product/Golden integrity.

## C. Real Qt interaction gates

`tests/test_qt_v71_product_closure.py` and the retained prior Real-Qt suites cover:

- Production `StudioToolButton` Hover → Leave exact raster baseline;
- Selected → Hover → Leave → Unselected exact Normal raster;
- Tab keyboard focus → same-control mouse click clears keyboard focus ring;
- left draw / right erase;
- middle-button pan;
- Space+left pan;
- pan preference gates;
- Preferences shortcut conflict is rejected without partial persistence;
- Designer / Pixel Studio / Preferences construction and clipping checks.

## D. Windows production-surface matrix

Each Windows CI DPI process executes:

`4 themes × 2 languages × 3 densities = 24 configurations`.

Each configuration constructs and checks:

1. Designer;
2. Pixel Studio;
3. Preferences.

With four DPI factors:

`24 × 3 surfaces × 4 DPI = 288 production-surface constructions`.

DPI factors:

- 1.0 / 100%
- 1.25 / 125%
- 1.5 / 150%
- 2.0 / 200%

Themes:

- MonoOLED Light
- MonoOLED Dark
- One Dark Pro
- High Contrast

Languages:

- zh_CN
- en_US

Densities:

- Compact
- Comfortable
- Spacious

## E. Windows standalone gates

After the Real-Qt source gates pass, the Windows builder must:

1. install pinned runtime/build dependencies;
2. run the full source suite;
3. run the DPI/Real-Qt matrix;
4. build the PyInstaller onedir application;
5. run `MonoOLEDStudio.exe --check`;
6. run `--smoke-ms 900`;
7. run `--layout-smoke`;
8. run `--interaction-smoke`;
9. run `--soak-smoke`;
10. package the Windows onedir output and SHA-256 it.

## F. Status semantics

- **PASS**: executed in the stated environment and returned success.
- **SKIPPED**: test exists but a required runtime/dependency is absent.
- **PREPARED**: workflow/build gate exists but was not executed on this host.
- **UNVERIFIED**: no execution evidence; must never be described as PASS.
