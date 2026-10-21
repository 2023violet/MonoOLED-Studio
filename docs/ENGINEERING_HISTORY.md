# Engineering History

MonoOLED Studio 1.1.0 is the current generic 1-bit OLED authoring product.

The former V12 engineering notes were consolidated here when the release and
documentation baseline moved to 1.0. They recorded delivery hardening rather
than separate product versions: Windows GA and reproducible runtime packaging;
FontPack validation; compact Preferences and accessibility; safe save/export,
autosave and corrupt-input recovery; project/screen transaction safety;
automation lifecycle/revision/long-job safeguards; and real-Qt DPI validation.

This history describes the Python 1.x line, whose source is kept at the
`v1-final` tag. The 2.0 Rust rewrite carries the same contracts; they are
checked against the frozen 1.x golden corpus (`fixtures/golden/`) and the
workspace tests. Current entry points are `BUILD.md`, `AUTOMATION_API_V1.md`
and the user guides.
