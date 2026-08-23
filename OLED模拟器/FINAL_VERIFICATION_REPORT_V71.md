# MonoOLED Studio 7.1 — Final Verification Report

**Release:** Product Closure  
**Verification date:** 2026-08-23  
**Implementation baseline:** formal MonoOLED Studio 7.0 complete delivery  
**Baseline ZIP SHA-256:** `7210e33807643a6b1e743cf18aefa074fd51534f97e7e2bb0e2cbd2713256da7`

## 1. Release conclusion

V7.1 is a full-tree incremental upgrade of the formal V7.0 delivery. It is not the earlier reduced V7.1 reconstruction. Before release packaging, the V7.0 and V7.1 trees were compared with caches excluded:

- V7.0 baseline files: **653**
- baseline files missing from V7.1: **0**
- V7.1 adds Product Closure source/tests/reports while retaining all V7.0 delivery content.

Renderer/Scene/VLSB/clinical product truth was intentionally frozen while the Product/GUI shell was hardened.

## 2. Host regression

Fresh source-tree full suite on the packaging host:

```text
179 passed, 5 skipped, 0 failed
```

The five skips are explicitly attributable to unavailable PySide6 on the Linux packaging host:

- `test_qt_professional_workspace_v60.py`
- `test_qt_real_interactions_v51.py`
- `test_qt_v71_product_closure.py`
- `test_qt_v7_interactions.py`
- the PySide-dependent part of `test_gui.py`

These skips are not counted as Windows GUI passes.

## 3. Product-truth freeze

V7.1 carries baseline SHA-256 manifests produced from the formal V7.0 tree:

- `reports/frozen_product_assets_v70.json`
- `reports/frozen_golden_v70.json`

Executed V7.1 stress verification result:

- frozen product assets: **464 / 464 byte-identical**
- clinical Golden: **14 / 14 byte-identical**
- each Golden BIN: **512 bytes**

This proves the Product Closure work did not rewrite Curing-Lite UI bitmaps, font resources, battery/icon assets, or clinical Golden output.

## 4. P0/P1 closure evidence

### Preferences

Verified behaviors include:

- malformed `schema_version` does not crash loading;
- semantically malformed known values fall back per field;
- future/unknown keys survive normalization;
- fixed left-draw/right-erase semantics cannot be changed by stale preference files;
- writes use temporary file + flush/fsync + atomic replace;
- every public default Preference has a named Runtime Effect;
- Shortcut rebinding validates the whole candidate map before mutation.

### Project boundary

Regression tests verify rejection of:

- unsafe screen IDs;
- screen paths escaping project root;
- asset roots outside project root;
- asset import destinations escaping project root.

### Autosave/recovery

Verified:

- atomic snapshot writes;
- no `.tmp` residue on successful commit;
- corrupt newest snapshot is quarantined;
- recovery continues to the newest valid older snapshot.

### Asset Cache

A regression test mutates bitmap content while preserving both file size and mtime. V7.1 detects the change through content SHA-256 and does not return the stale cached asset hash.

### Pixel Studio

Verified at pure-host level:

- left draw / right erase core semantics;
- continuous Bresenham brush segment;
- 1–8 px brush footprint;
- one continuous gesture = one undo transaction;
- randomized VLSB invariants;
- oversized image check before Python pixel-matrix allocation;
- strict-ASCII C identifier generation.

## 5. Adversarial stress verification

Executed with `Developer_Tools/VERIFY_V71_STRESS.py`:

| Gate | Result |
|---|---:|
| Preferences malformed semantic fuzz | **1,000 payloads PASS** |
| PixelDocument randomized documents | **60** |
| Operations per document | **500** |
| PixelDocument total randomized operations | **30,000 PASS** |
| Renderer clinical states | **14** |
| Renderer cycles | **100** |
| Renderer frames | **1,400 PASS** |
| Framebuffer size | **512 B every frame** |
| Deterministic state hashes | **14 / 14 stable across all cycles** |
| Renderer average on this host | **2.643 ms/frame** |
| Renderer P95 on this host | **2.959 ms/frame** |

## 6. Clinical/state verification

The retained clinical matrix test executes:

`7 modes × 2 phases × 5 battery states × 8 seconds cases = 560 combinations`

Each state must render the expected framebuffer size and contain no `ERROR` or `BLOCKER` validation finding.

Result in the full Host/Core suite: **PASS**.

## 7. Interaction pipeline performance

A fresh `interaction_benchmark.py` run on this packaging host produced:

| Stage | Average | P95 |
|---|---:|---:|
| Render | 3.181 ms | 3.667 ms |
| Validation | 15.231 ms | 16.381 ms |
| Evidence | 0.336 ms | 0.444 ms |
| Full pipeline | 18.595 ms | 19.667 ms |

V7.1 retains the rule that high-frequency interaction should avoid unnecessary full validation; exact/full validation is selected according to the Runtime Preferences policy.

## 8. Deterministic Code AI handoff

V7.1 generated the 14-state handoff twice independently.

Both ZIPs were byte-identical:

`8c8994d91efae66f25fa4f2e71aa7770de1c129e15ee8abac0e20a65f93af04d`

Current artifact:

`exports/OLED_Code_AI_Handoff_v7.1.zip`

## 9. Real Qt V7.1 gate

V7.1 adds `tests/test_qt_v71_product_closure.py` and retains all prior Qt suites.

The V7.1 suite directly exercises Production controls/objects rather than only the pure state model:

- `StudioToolButton` hover/leave exact raster restoration;
- selected→hover→leave→unselected exact baseline;
- Tab keyboard focus → mouse click on the same control clears the keyboard focus property;
- real PixelCanvas middle-button pan;
- real PixelCanvas Space+left pan;
- pan preference gates;
- Preferences shortcut conflict rejection without partial save;
- Designer / Pixel Studio / Preferences layout construction.

### Windows configuration matrix

The Windows release workflow executes:

`4 DPI × 4 themes × 2 languages × 3 densities × 3 production surfaces = 288 production-surface constructions`

Production surfaces:

1. Designer
2. Pixel Studio
3. Preferences

### Status on this packaging host

**NOT EXECUTED / SKIPPED — PySide6 is unavailable.**

The Windows Real-Qt result must therefore be produced by the Windows workflow or `Developer_Tools/BUILD_WINDOWS_EXE.bat`. Prepared tests are not reported as PASS.

## 10. Windows executable boundary

The root `MonoOLEDStudio.exe` SHA-256 is:

`558c2115941aff959927dc6b29c6bd4ac5a746dc2c6854ea921efd2180615c87`

It is byte-identical to the formal V7.0 runtime-locator launcher. It is retained because it resolves and launches the source application from the delivery tree; it is **not** a newly built V7.1 self-contained executable.

The supported Python-free V7.1 Windows artifact is the PyInstaller onedir result generated only after the Windows Real-Qt/DPI gates pass.

**Windows standalone build status on this Linux host: NOT EXECUTED.**

## 11. Package integrity model

`VERIFY_PACKAGE.py` now verifies more than individual hashes:

- exact checksum coverage for all delivered files except `SHA256SUMS.txt` itself;
- no unmanaged delivered files;
- V7.1 version/manifest consistency;
- 464 frozen product-asset hashes;
- 14 frozen Golden hashes and 512-byte size;
- required Product Closure modules/documents;
- Windows Real-Qt gate wiring;
- native runtime-locator launcher PE/resource contract.

Final ZIP construction additionally checks duplicate names, unsafe paths, and UTF-8 filename metadata.

## 12. Accurate release status

### Executed and passed on this host

- Host/Core suite;
- Product Closure regression suite;
- clinical 560-state matrix;
- frozen 464 product assets;
- 14 Golden BIN;
- Preferences fuzz;
- Pixel randomized stress;
- Renderer deterministic stress;
- deterministic Code AI handoff;
- interaction pipeline benchmark.

### Prepared but not executed on this host

- PySide6 Real-Qt visual/interaction tests;
- four-DPI Windows matrix;
- Windows PyInstaller onedir build;
- Windows standalone smoke/soak gates.

This distinction is intentional and is part of the V7.1 release contract.
