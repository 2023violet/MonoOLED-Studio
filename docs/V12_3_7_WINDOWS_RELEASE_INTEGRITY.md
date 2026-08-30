# V12.3.7 Windows Release Integrity Hardening

V12.3.7 hardens the Windows GA and GitHub Release chain on top of the V12.3.6 product/source baseline. It does not redesign the editor UI or change project data formats.

## Release identity

- Tag pushes and manual `workflow_dispatch` both check out the exact requested release ref.
- `VERIFY_RELEASE_TAG.py --require-git-head` requires `src/VERSION`, the requested tag, checked-out `HEAD`, and the peeled tag commit to agree.
- The runtime package embeds `BUILD_INFO.json` containing product version, release tag and git commit.
- GA and the publisher re-verify that embedded commit against the checked-out release commit.

## Evidence integrity

- `.artifacts/windows_ga` is cleared before a new GA run.
- Settings visual evidence clears its output directory before capture.
- GitHub Actions uploads GA XML/log/visual evidence with `if: always()`, including failed certification runs.
- Every Real-Qt module/smoke process receives isolated `LOCALAPPDATA` and `APPDATA`, preventing test-order and DPI-state contamination.

## End-user runtime package

`tools/BUILD_WINDOWS_RUNTIME_ZIP.py` replaces `Compress-Archive` for the user-facing Windows ZIP.

The builder:

- enumerates files in deterministic order with fixed ZIP metadata;
- rejects unsafe/non-ASCII/developer/test paths and symlinks;
- excludes `test_assets` from the PyInstaller runtime;
- validates the complete temporary ZIP before atomically replacing an older candidate;
- writes an atomic SHA-256 sidecar;
- safely extracts the candidate into a fresh evidence directory.

The GA then executes the extracted end-user `MonoOLEDStudio.exe` with core, startup, layout, Settings and interaction smoke gates. Certification therefore validates the package users actually download, not only the pre-ZIP `dist` directory.

## Immutable GitHub Release assets

Existing assets for the same semantic-version tag are never overwritten with `--clobber`. A rerun downloads the published ZIP/SHA, re-verifies checksum/version/tag/git provenance, and succeeds only when the published checksum is identical to the local candidate. A mismatch aborts publication and requires explicit human intervention/new versioning.

## Tests

`tests/test_v1237_windows_release_integrity.py` covers exact-tag checkout, HEAD/tag commit binding, evidence reset/preservation, isolated Qt user state, deterministic runtime packaging, provenance, post-extraction EXE checks and immutable release behavior.

## Release identity

- Source version: `12.3.7`
- Git tag: `v12.3.7`
- Windows asset: `MonoOLEDStudio_v12.3.7_Windows_x64.zip`
- Checksum: `MonoOLEDStudio_v12.3.7_Windows_x64.zip.sha256`
