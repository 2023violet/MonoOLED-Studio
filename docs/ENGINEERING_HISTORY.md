# Engineering History

MonoOLED Studio 1.1.0 is the current generic 1-bit OLED authoring product.

The former V12 engineering notes were consolidated here when the release and
documentation baseline moved to 1.0. They recorded delivery hardening rather
than separate product versions: Windows GA and reproducible runtime packaging;
FontPack validation; compact Preferences and accessibility; safe save/export,
autosave and corrupt-input recovery; project/screen transaction safety;
automation lifecycle/revision/long-job safeguards; and real-Qt DPI validation.

Those safeguards remain implemented and tested. Their current operational
entry points are `WINDOWS_BUILD.md`, `AUTOMATION_API_V1.md`, the user guides,
the Windows build scripts, and the automated test suite.
