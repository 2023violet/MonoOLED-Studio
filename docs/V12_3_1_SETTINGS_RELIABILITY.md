# V12.3.1 Settings Reliability Gate

V12.3.1 does not redesign the V12.3 Compact Preferences visual language. It closes the reliability gaps discovered after V12.3 source tests passed while real Settings layouts could still overlap or reflow incorrectly.

## Root causes closed

- `SettingRow` now rebuilds its grid only when it actually crosses Standard/Compact mode.
- Responsive mode is derived from effective content width after page margins, not the whole Settings view or raw scroll viewport.
- Every Settings scroll viewport drives reflow on resize/layout/show/hide events, including vertical-scrollbar width changes.
- Horizontal scrolling is forbidden for Settings pages.
- Language changes always schedule geometry settling after text size hints change.
- Boolean settings use the same left-label/right-control baseline as select/numeric/button rows.
- The overlap detector checks only the active page and covers content overflow, row overflow, row-to-row overlap, section overlap, header overlap, internal row overlap, horizontal scrollbar presence, and responsive-mode mismatch.

## Windows Real-Qt release matrix

`tests/test_qt_settings_reliability_v1231.py` runs at every mandatory GA `QT_SCALE_FACTOR`:

`1.0 / 1.25 / 1.5 / 1.75 / 2.0 / 2.25 / 2.5 / 3.0`

Inside each DPI process, bounded pairwise cases cover:

- width: 700 / 760 / 900 / 980 / 1180 / 1440
- language: zh_CN / en_US
- UI scale: 90% / 100% / 110% / 125% / 150%
- density: Compact / Comfortable / Spacious
- appearance: System / Light / Dark
- all seven Settings pages

The same module performs a 500-cycle resize/page/language/theme/UI-scale/search soak.

## Executable release gates

The packaged Windows EXE must pass both:

- `--settings-smoke`: embedded Settings boundary matrix across every page
- `--settings-soak --settings-soak-cycles 500`: long-running Settings state-machine stress

`tools/VERIFY_SETTINGS_V1231.py` runs the source forms before packaging. The built EXE repeats the Settings smoke five times and the 500-cycle soak once.

## Visual evidence

`tools/CAPTURE_V1231_SETTINGS_GOLDENS.py` captures every Settings page for a bounded DPI/language/theme/density/UI-scale/window matrix. A screenshot is accepted only when the live view reports zero geometry violations. JSON geometry reports and PNGs are preserved in `.artifacts/windows_ga/settings_v1231_golden/` by GitHub Actions.

## Release decision

Source-only success is not sufficient to declare Settings layout closure. V12.3.1 is Windows-GA ready only after the zero-skip Real-Qt matrix, Settings reliability verifier, visual evidence capture, packaged EXE Settings smoke, and packaged EXE Settings soak all pass on `windows-latest`.
