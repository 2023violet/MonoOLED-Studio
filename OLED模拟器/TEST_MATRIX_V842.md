# MonoOLED Studio 8.4.2 — Test Matrix

## P0 data-safety tests

- transaction commit leaves unsaved Scene dirty;
- scene/state mutation leaves Scene dirty;
- project save clears dirty;
- dirty `project.open_screen` fails closed with `UNSAVED_CHANGES`;
- `save_current=true` persists before switch;
- `discard_current=true` explicitly discards;
- save/discard conflict is rejected;
- save failure leaves active screen unchanged;
- JSON-RPC exposes stable `UNSAVED_CHANGES` error code;
- active-screen delete/open paths use the same unsaved guard;
- 1,000 cross-screen commit/save/open/reopen soak: zero silent data loss.

## Contract tests

- Automation API version is 1.2.0 everywhere;
- machine contract matches production `METHOD_SPECS`;
- `history.commit.params.transaction` is required;
- `history.rollback.params.transaction` is required;
- bridge startup handshake version equals capabilities/contract version;
- V8.4.1 Font method parameter contracts remain self-describing.

## Long-operation tests

- `state.count` returns legal matrix count;
- summary render omits frame list;
- summary validation omits per-case finding list;
- summary export omits frame-hash payload;
- `job.start/status/result/cancel` are discoverable;
- job progress is monotonic;
- async render summary matches sync render summary;
- cooperative cancel reaches explicit terminal state;
- export job uses Studio-owned Exporter.

## Historical regression gates

- V8.2 native visual/Popup adversarial gate;
- V8.3 reliability/performance gate;
- V8.4 Project + Code AI graduation;
- V8.4.1 State Model graduation;
- V8.4.2 Automation Reliability graduation.

## Frozen truth gates

- 464/464 product assets byte-identical;
- 14/14 Clinical Golden byte-identical;
- each Golden is 512 bytes;
- no Renderer/VLSB contract drift.

## Packaging gates

- deterministic ZIP;
- complete `SHA256SUMS.txt`;
- no duplicate ZIP entries;
- no absolute or traversal paths;
- all non-ASCII names use ZIP UTF-8 flag;
- no `__pycache__`, `.pyc`, `.pytest_cache`, `.git`, build/dist/release transient content;
- `delivery_profile=source` requires source/test/developer release assets.

## Windows GA gate

Windows builder must execute all `test_qt_*.py` tests at:

`100 / 125 / 150 / 175 / 200 / 225 / 250 / 300 %`

Every JUnit file must contain:

`0 failed / 0 skipped`

The standalone is produced only after all V8.2–V8.4.2 release gates pass.
