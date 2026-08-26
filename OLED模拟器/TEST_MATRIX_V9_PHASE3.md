# V9 Phase 3 Test Matrix

| Gate | Coverage | Expected evidence |
| --- | --- | --- |
| GEN-AUTO-001 | capabilities and method descriptions | API 1.2.0, 82 methods |
| GEN-AUTO-002 | empty project, two screens, save/reopen | both screen IDs and elements persist |
| GEN-AUTO-003 | identical four-field schema on both screens | declaration order and schema equality |
| GEN-AUTO-004 | FontPack, glyphs, 1-bit bitmap through API | resources load after reopen |
| GEN-AUTO-005 | unsaved switch and explicit save policy | `UNSAVED_CHANGES`, save/discard semantics |
| GEN-AUTO-006 | representative/full matrix | 80 cases for this fixture, count/enumerate agree |
| GEN-AUTO-007 | render and validate matrix | 512-byte framebuffer, zero blockers |
| GEN-AUTO-008 | export and handoff | deterministic frame set and safe package |
| GEN-AUTO-009 | asynchronous render job | terminal status and result evidence |
| GEN-AUTO-010 | cancel contract | inherited V8.4.2 cooperative cancellation regression |
| GEN-AUTO-011 | save/reopen truth | scene/schema/frame hashes remain stable |
| REGRESSION-001 | Phase 2 tests, compileall, diff check | no regression |

The default environment is host Python. Existing Linux Qt skips remain environmental evidence and
are not relabeled as Windows Real-Qt results. Windows deep validation is out of scope unless a
listed release, native Qt, DPI, renderer, framebuffer, codec, or platform-specific trigger occurs.
