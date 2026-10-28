# Review pack (HTML)

`mono review-pack` (and File → Review pack in the desktop app) writes one
self-contained HTML file that a firmware or hardware reviewer can open offline:
no app, no project, no network.

```bash
mono review-pack --project project.oled.json --output review/review.html
mono review-pack --project project.oled.json --output review/review.html --json
```

Options:

| Option | Meaning |
| --- | --- |
| `--project <project.oled.json>` | required; the pack covers every screen |
| `--output <file.html>` | required; the destination file |
| `--annotations <file>` | review JSON; defaults to `<project>/review/review.json` |
| `--json` | print one JSON object instead of the text summary |

`--json` prints `command`, `ok`, `exit_code`, `output`, `screens`, `frames`,
`annotations`, `blocking`, `bytes` and `sha256`. Exit codes are unchanged:
0 success, 2 error (with a JSON error object when `--json` is present).

## What is in the file

- Every screen, sorted by `(category, label, id)`.
- The init frame of each screen plus up to eight distinct states that carry
  annotations (deduplicated by their state map).
- For each frame: the raw VLSB bytes (base64), SHA-256, lit-pixel count, byte
  size, the state map, validation findings, visible elements (`id`, type,
  `x,y`, `w×h`), the C header and the spaced hex dump.
- All annotations, sorted by screen, state, element, kind and id, with their
  anchor and recorded evidence.
- A contract page: coordinate contract, VLSB byte/bit formula, polarity,
  per-frame hashes, design rules.

The page renders frames with `canvas` and `image-rendering: pixelated`, switches
between Device and Code, shows pixel coordinates under the cursor, copies a
frame hash, and filters screens by All / Blocking / Annotated or by search.

## Determinism

Two runs over the same project and review file produce byte-identical HTML:

- screens are sorted by `(category, label, id)`, frames by their state map,
  annotations by `(screen, state, element, kind, id)`;
- the file contains no generation timestamp and no absolute path;
- the JSON embedded in the page escapes `<`, `>`, `&`, U+2028 and U+2029, so
  annotation text cannot close the script tag.

The pack is written atomically (temporary file, fsync, rename).

## What the pack does not claim

Frames come from the same canonical renderer that writes `ui_contract.json`, so
each frame hash can be compared with that contract's `golden_sha256` for the
same state. MonoOLED Studio has one renderer; the pack explicitly states that it
makes no L2 (two-independent-implementations) claim. There is also no key or
hardware event model in this build: states are explicit presets, and the page
says so.

## Comparing with the contract

```bash
mono export --project project.oled.json --output exports/latest
mono review-pack --project project.oled.json --output review/review.html
```

The `init` frame hash in the pack for a screen must equal the
`golden_sha256` of the matching `state` in `exports/latest/ui_contract.json`.
The app's Review evidence panel performs the same comparison live and shows
`golden match` or `frame changed`.
