# Curing-Lite Clinical English 5x7 v2 — Glyph QA

## Stage result
v2 is a production candidate for the Clinical Standby/Running mode-label role.

## Changes from v1
- C: rounded top/bottom corners; restores the same curve language as O/G.
- G: rounded outer bowl while keeping a short internal horizontal spur.
- I: narrows top/bottom bars from 5 px to 3 px to reduce visual overweight in HIGH.
- Q: delays the diagonal tail until the lower two rows, preserving O/Q recognition.
- S: rounded terminal/corner construction, closer to the C/G/O family.
- W: finishes as a double-V shape instead of reopening at the baseline.

## Frozen family rules
- 5x7 fixed cell.
- 1 px monoline.
- Uppercase only.
- 1 px tracking.
- 6 px fixed advance.
- No antialiasing.
- No runtime scaling.
- 1 means foreground/lit pixel; 0 means background.
- Existing black-on-white PNGs are review sources only; black converts to mask bit 1.

## Clinical width verification
- NORMAL: 35 px / 36 px — PASS
- HIGH: 23 px / 36 px — PASS
- TURBO: 29 px / 36 px — PASS
- PULSE: 29 px / 36 px — PASS
- RAMP: 23 px / 36 px — PASS
- ORTHO: 29 px / 36 px — PASS
- CHECK: 29 px / 36 px — PASS

## Integration verification
- 7 modes x Standby/Running = 14 exact 128x32 screens generated.
- Each screen also emits one 512-byte VLSB framebuffer.
- No asset exceeds the framebuffer.
- NORMAL remains the width worst case at 35 px.
- No per-word special scaling or tracking is required.

## Gate to freeze
Before calling v2 final, visually sign off:
1. HIGH — especially I/G balance.
2. CHECK — especially C opening.
3. PULSE — especially S terminal shape.
4. NORMAL — N/M/R density and longest-word fit.
5. A-Z recognition pairs sheet.
