# MonoOLED Studio 6.0 Interaction Performance Baseline

Host benchmark on the bundled Curing-Lite 128x32 scene. Timing is environment-specific and is used to compare pipeline stages, not to claim Windows GUI FPS.

| Stage | Avg ms | P95 ms | Max ms |
|---|---:|---:|---:|
| Canonical Render | 3.484 | 5.074 | 18.694 |
| Validation | 16.160 | 19.381 | 32.567 |
| Evidence | 0.354 | 0.491 | 2.196 |
| Full pipeline | 19.292 | 22.023 | 26.189 |

## Design consequence

During pointer drag, MonoOLED Studio 6.0 uses the render-only fast-preview path and defers validation, diff, evidence logging and file-watcher maintenance until gesture commit. This avoids paying the full-pipeline cost for every mouse event.
