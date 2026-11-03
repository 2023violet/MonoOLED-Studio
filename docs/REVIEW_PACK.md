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

`--output` is an arbitrary destination, like `mono export --output`; it is not
confined to the project root. Only the default annotations sidecar is resolved
inside the project. `review/review.json` is meant to be committed;
`review/quarantine/` and the generated HTML are build artifacts.

`--json` prints `command`, `ok`, `exit_code`, `output`, `screens`, `frames`,
`annotations`, `blocking`, `blocking_frames`, `bytes` and `sha256`. `blocking`
counts the blocking findings of each screen's init frame; `blocking_frames`
counts the rendered frames (init and annotated states) that have at least one. Exit codes are unchanged:
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

## Blocking findings: written, but marked

The release gate does not apply to the review pack: it is written whatever the
findings, because reviewing problems is what it is for. When any
rendered frame has a `BLOCKER` or `ERROR` finding, the page opens with a static
banner, readable without JavaScript:

> Not a deliverable. N of M rendered frames have blocking findings (BLOCKER or
> ERROR). An export is refused while a blocking finding remains in any state it
> checks; this pack is for review only.

The text summary of `mono review-pack` prints `NOT A DELIVERABLE: …` and the
desktop status line names the count. The pack renders the init frame and the
annotated states only, not the export's state matrix, so the banner does not
predict the export verdict exactly: a pack without the banner does not prove
that an export will pass, and a blocker found only in an annotated state that
the matrix does not sample does not block the export. The export runs its own
gate.

## Determinism

Two runs over the same project and review file produce byte-identical HTML:

- screens are sorted by `(category, label, id)`; each screen's init frame comes
  first, then the states that carry annotations in review-file order
  (deduplicated by state map); annotations by `(screen, state, element, kind,
  id)`;
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
