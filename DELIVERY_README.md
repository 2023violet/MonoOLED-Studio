# V1.0.0 Initial Release Delivery

This package is the **release-ready GitHub source** for MonoOLED Studio **1.0.0**.

End users should not run Python or build scripts. The public Windows delivery channel is **GitHub Releases**, where a `v1.0.0` tag produces `MonoOLEDStudio_v1.0.0_Windows_x64.zip` and its SHA-256 sidecar after the Windows GA gate passes. After extraction the user starts `MonoOLEDStudio\MonoOLEDStudio.exe`.

Developers can use `tools\BUILD_WINDOWS_QUICK.bat` for a fast local EXE or `tools\BUILD_WINDOWS_GA.bat` for the full Windows Real-Qt/DPI certification path. `tools\BUILD_WINDOWS_EXE.bat` remains only as a compatibility wrapper to GA.

Release acceptance is defined by `VERIFY_PACKAGE.py`, the source regression suite, the Windows GA builder, the tag/version guard, and the V1.0.0 Startup/Settings/Font critical-path gates. Product-specific Curing-Lite data remains test-only under `test_assets/projects/curing_lite/`.

For deterministic source delivery, run `python tools/BUILD_DELIVERY_V120.py`.
