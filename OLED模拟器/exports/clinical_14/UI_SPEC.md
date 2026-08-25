# Curing_Lite 光固化机 128x32 OLED OLED UI Specification

> Generated from scene JSON. Do not edit this document as the layout source of truth.

## Global Contract

- Canvas: **128×32**, monochrome 1-bit.
- Origin: `(0,0)` at top-left; X increases right, Y increases down.
- Bounds: `[x, x+w) × [y, y+h)`.
- Storage: **512-byte VLSB**, 4 pages × 128 columns; bit0 is the top pixel of each 8-pixel page.
- Polarity: `1 = OLED lit`, `0 = background`.
- Bitmap resize policy: `native_only` unless explicitly stated otherwise.
- Bitmap source polarity is normalized at load time: opaque black-on-white assets are inverted in memory; source files are not rewritten.

## Scene Element Definitions

| ID | Type | X | Y | W | H | Binding / Text |
|---|---|---:|---:|---:|---:|---|
| battery | image_seq | 5 | 2 | 11 | 28 | battery |
| hero_digits | digits | 45 | 3 |  |  | seconds |
| mode_label | text | 88 | 4 | 36 | 12 | {mode} |
| mode_icon | image | 94 | 19 | 24 | 12 |  |
| running_icon | image | 94 | 19 | 24 | 12 |  |

## CHECK_RUNNING

State: `battery=4, mode=CHECK, phase=running, seconds=300`

Golden BIN: `golden/check_running.bin`  
Reference PNG: `reference/check_running.png`  
SHA-256: `6a1e9ed8556b4a5c05bc21a05a7c7a426faa5f1c35bad9ffaed0e97c1e79440b`

| ID | Type | X | Y | W | H | Asset / Text |
|---|---|---:|---:|---:|---:|---|
| battery | image_seq | 5 | 2 | 11 | 28 | 电池图标 - 字宽11字高28/11-28电池图标4.png |
| hero_digits | digits | 45 | 3 | 43 | 27 | 300 |
| mode_label | text | 88 | 4 | 29 | 7 | CHECK |
| running_icon | image | 94 | 19 | 24 | 12 | Curing_Lite光固化机产品 - UI设计初稿/running.png |

## CHECK_STANDBY

State: `battery=4, mode=CHECK, phase=standby, seconds=300`

Golden BIN: `golden/check_standby.bin`  
Reference PNG: `reference/check_standby.png`  
SHA-256: `cd678033957468c460bd1c221293a97514d7c76eb062e1780b2d9fe5cf9e9264`

| ID | Type | X | Y | W | H | Asset / Text |
|---|---|---:|---:|---:|---:|---|
| battery | image_seq | 5 | 2 | 11 | 28 | 电池图标 - 字宽11字高28/11-28电池图标4.png |
| hero_digits | digits | 45 | 3 | 43 | 27 | 300 |
| mode_label | text | 88 | 4 | 29 | 7 | CHECK |
| mode_icon | image | 94 | 19 | 24 | 12 | Curing_Lite光固化机产品 - UI设计初稿/check.png |

## HIGH_RUNNING

State: `battery=4, mode=HIGH, phase=running, seconds=300`

Golden BIN: `golden/high_running.bin`  
Reference PNG: `reference/high_running.png`  
SHA-256: `d5ec096a3e540f71290d427c61896bda4eb1b563d53f2bd720e31995c272d649`

| ID | Type | X | Y | W | H | Asset / Text |
|---|---|---:|---:|---:|---:|---|
| battery | image_seq | 5 | 2 | 11 | 28 | 电池图标 - 字宽11字高28/11-28电池图标4.png |
| hero_digits | digits | 45 | 3 | 43 | 27 | 300 |
| mode_label | text | 88 | 4 | 23 | 7 | HIGH |
| running_icon | image | 94 | 19 | 24 | 12 | Curing_Lite光固化机产品 - UI设计初稿/running.png |

## HIGH_STANDBY

State: `battery=4, mode=HIGH, phase=standby, seconds=300`

Golden BIN: `golden/high_standby.bin`  
Reference PNG: `reference/high_standby.png`  
SHA-256: `25b872f076619def7ee30e788d4eeac8f0af91ba53ae41ca97e7f01117d6d043`

| ID | Type | X | Y | W | H | Asset / Text |
|---|---|---:|---:|---:|---:|---|
| battery | image_seq | 5 | 2 | 11 | 28 | 电池图标 - 字宽11字高28/11-28电池图标4.png |
| hero_digits | digits | 45 | 3 | 43 | 27 | 300 |
| mode_label | text | 88 | 4 | 23 | 7 | HIGH |
| mode_icon | image | 94 | 19 | 24 | 12 | Curing_Lite光固化机产品 - UI设计初稿/high.png |

## NORMAL_RUNNING

State: `battery=4, mode=NORMAL, phase=running, seconds=300`

Golden BIN: `golden/normal_running.bin`  
Reference PNG: `reference/normal_running.png`  
SHA-256: `de165c3952ccf40bda06cabab9e2eca5edf96465bcc59274831dc4d06f8aeb02`

| ID | Type | X | Y | W | H | Asset / Text |
|---|---|---:|---:|---:|---:|---|
| battery | image_seq | 5 | 2 | 11 | 28 | 电池图标 - 字宽11字高28/11-28电池图标4.png |
| hero_digits | digits | 45 | 3 | 43 | 27 | 300 |
| mode_label | text | 88 | 4 | 35 | 7 | NORMAL |
| running_icon | image | 94 | 19 | 24 | 12 | Curing_Lite光固化机产品 - UI设计初稿/running.png |

## NORMAL_STANDBY

State: `battery=4, mode=NORMAL, phase=standby, seconds=300`

Golden BIN: `golden/normal_standby.bin`  
Reference PNG: `reference/normal_standby.png`  
SHA-256: `737f147eac9c89faf8c339360afd3cc895be9bc4db4519a792fce5e477836b59`

| ID | Type | X | Y | W | H | Asset / Text |
|---|---|---:|---:|---:|---:|---|
| battery | image_seq | 5 | 2 | 11 | 28 | 电池图标 - 字宽11字高28/11-28电池图标4.png |
| hero_digits | digits | 45 | 3 | 43 | 27 | 300 |
| mode_label | text | 88 | 4 | 35 | 7 | NORMAL |
| mode_icon | image | 94 | 19 | 24 | 12 | Curing_Lite光固化机产品 - UI设计初稿/normal.png |

## ORTHO_RUNNING

State: `battery=4, mode=ORTHO, phase=running, seconds=300`

Golden BIN: `golden/ortho_running.bin`  
Reference PNG: `reference/ortho_running.png`  
SHA-256: `e6b22640adb6de81712eb10c55f10e14785b0ef7f7968672172f6f73d7b47f79`

| ID | Type | X | Y | W | H | Asset / Text |
|---|---|---:|---:|---:|---:|---|
| battery | image_seq | 5 | 2 | 11 | 28 | 电池图标 - 字宽11字高28/11-28电池图标4.png |
| hero_digits | digits | 45 | 3 | 43 | 27 | 300 |
| mode_label | text | 88 | 4 | 29 | 7 | ORTHO |
| running_icon | image | 94 | 19 | 24 | 12 | Curing_Lite光固化机产品 - UI设计初稿/running.png |

## ORTHO_STANDBY

State: `battery=4, mode=ORTHO, phase=standby, seconds=300`

Golden BIN: `golden/ortho_standby.bin`  
Reference PNG: `reference/ortho_standby.png`  
SHA-256: `96a73634f1771a139767725aa270a3aa40febb26c4249b2e31f525f83dc76b5d`

| ID | Type | X | Y | W | H | Asset / Text |
|---|---|---:|---:|---:|---:|---|
| battery | image_seq | 5 | 2 | 11 | 28 | 电池图标 - 字宽11字高28/11-28电池图标4.png |
| hero_digits | digits | 45 | 3 | 43 | 27 | 300 |
| mode_label | text | 88 | 4 | 29 | 7 | ORTHO |
| mode_icon | image | 94 | 19 | 24 | 12 | Curing_Lite光固化机产品 - UI设计初稿/ortho.png |

## PULSE_RUNNING

State: `battery=4, mode=PULSE, phase=running, seconds=300`

Golden BIN: `golden/pulse_running.bin`  
Reference PNG: `reference/pulse_running.png`  
SHA-256: `bab886efd7a802d8a2eebe026adbf3aa11fc8414f0001924e0bdf7c71ccba20b`

| ID | Type | X | Y | W | H | Asset / Text |
|---|---|---:|---:|---:|---:|---|
| battery | image_seq | 5 | 2 | 11 | 28 | 电池图标 - 字宽11字高28/11-28电池图标4.png |
| hero_digits | digits | 45 | 3 | 43 | 27 | 300 |
| mode_label | text | 88 | 4 | 29 | 7 | PULSE |
| running_icon | image | 94 | 19 | 24 | 12 | Curing_Lite光固化机产品 - UI设计初稿/running.png |

## PULSE_STANDBY

State: `battery=4, mode=PULSE, phase=standby, seconds=300`

Golden BIN: `golden/pulse_standby.bin`  
Reference PNG: `reference/pulse_standby.png`  
SHA-256: `671c49afa5710cd5bf01d98ceb45c86f80c69775f539b7b129fc36d80a7d3483`

| ID | Type | X | Y | W | H | Asset / Text |
|---|---|---:|---:|---:|---:|---|
| battery | image_seq | 5 | 2 | 11 | 28 | 电池图标 - 字宽11字高28/11-28电池图标4.png |
| hero_digits | digits | 45 | 3 | 43 | 27 | 300 |
| mode_label | text | 88 | 4 | 29 | 7 | PULSE |
| mode_icon | image | 94 | 19 | 24 | 12 | Curing_Lite光固化机产品 - UI设计初稿/pulse.png |

## RAMP_RUNNING

State: `battery=4, mode=RAMP, phase=running, seconds=300`

Golden BIN: `golden/ramp_running.bin`  
Reference PNG: `reference/ramp_running.png`  
SHA-256: `3156269fa844abc4255396f3243b972fe7e3c5d789121e6d6c65cf2067eb4141`

| ID | Type | X | Y | W | H | Asset / Text |
|---|---|---:|---:|---:|---:|---|
| battery | image_seq | 5 | 2 | 11 | 28 | 电池图标 - 字宽11字高28/11-28电池图标4.png |
| hero_digits | digits | 45 | 3 | 43 | 27 | 300 |
| mode_label | text | 88 | 4 | 23 | 7 | RAMP |
| running_icon | image | 94 | 19 | 24 | 12 | Curing_Lite光固化机产品 - UI设计初稿/running.png |

## RAMP_STANDBY

State: `battery=4, mode=RAMP, phase=standby, seconds=300`

Golden BIN: `golden/ramp_standby.bin`  
Reference PNG: `reference/ramp_standby.png`  
SHA-256: `c19eaa6dbd202942d7013ac30100b12dc9a8fe8345ef6e297d32d974cfbdda7d`

| ID | Type | X | Y | W | H | Asset / Text |
|---|---|---:|---:|---:|---:|---|
| battery | image_seq | 5 | 2 | 11 | 28 | 电池图标 - 字宽11字高28/11-28电池图标4.png |
| hero_digits | digits | 45 | 3 | 43 | 27 | 300 |
| mode_label | text | 88 | 4 | 23 | 7 | RAMP |
| mode_icon | image | 94 | 19 | 24 | 12 | Curing_Lite光固化机产品 - UI设计初稿/ramp.png |

## TURBO_RUNNING

State: `battery=4, mode=TURBO, phase=running, seconds=300`

Golden BIN: `golden/turbo_running.bin`  
Reference PNG: `reference/turbo_running.png`  
SHA-256: `a133702bd6d49f1bbb8337d12fb989e1ca3e25aff41bb4ead1eb5035fd3a202b`

| ID | Type | X | Y | W | H | Asset / Text |
|---|---|---:|---:|---:|---:|---|
| battery | image_seq | 5 | 2 | 11 | 28 | 电池图标 - 字宽11字高28/11-28电池图标4.png |
| hero_digits | digits | 45 | 3 | 43 | 27 | 300 |
| mode_label | text | 88 | 4 | 29 | 7 | TURBO |
| running_icon | image | 94 | 19 | 24 | 12 | Curing_Lite光固化机产品 - UI设计初稿/running.png |

## TURBO_STANDBY

State: `battery=4, mode=TURBO, phase=standby, seconds=300`

Golden BIN: `golden/turbo_standby.bin`  
Reference PNG: `reference/turbo_standby.png`  
SHA-256: `20134251636c276f874246ecff8f93e80b94e7b3c2c6a1c6705d7effce9b035e`

| ID | Type | X | Y | W | H | Asset / Text |
|---|---|---:|---:|---:|---:|---|
| battery | image_seq | 5 | 2 | 11 | 28 | 电池图标 - 字宽11字高28/11-28电池图标4.png |
| hero_digits | digits | 45 | 3 | 43 | 27 | 300 |
| mode_label | text | 88 | 4 | 29 | 7 | TURBO |
| mode_icon | image | 94 | 19 | 24 | 12 | Curing_Lite光固化机产品 - UI设计初稿/turbo.png |
