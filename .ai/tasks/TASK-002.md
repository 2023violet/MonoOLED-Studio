# TASK-002 — Close Theme Visual Workstream and Apply Approved Dark Palette

## Status

VERIFY

## Goal

在不改变主题 routing、公开主题标识、偏好持久化或 high-contrast 的前提下，收口既有 Theme Visual Workstream：浅色继续使用 `monooled-light`，实际可达的深色 `one-dark-pro` 使用已批准的暗青灰/cyan semantic tokens。

## Product Decision

方案 B 已锁定：

```text
light -> monooled-light
dark -> one-dark-pro
system + system_dark=False -> monooled-light
system + system_dark=True -> one-dark-pro
```

不得把 `dark` routing 改为 `monooled-dark`。

## Pre-Task Baseline

TASK-002 开始前已存在并受保护的用户工作：

- `docs/DESIGN_SYSTEM.md`
- `src/qt_theme.py`
- `src/theme_system.py`
- `src/ui_metrics.py`
- `tests/test_qt_theme.py`
- `tests/test_v10_ui_craft_contract.py`
- `BLOCKED.md`
- `PROGRESS.md`

这些文件的 SHA-256 baseline 在实施前已读取并记录于本轮交接证据中。TASK-002 的新增修改可通过本文件的 scope 与 Git diff 审计区分。

## Failure Evidence

实施前的可重复检查显示：`dark` 与系统深色均解析到 `one-dark-pro`，而 `one-dark-pro` 的 36 个 semantic tokens 中有 35 个不同于已批准的 `monooled-dark` tokens；例如 `accent.primary` 为旧的 `#61AFEF`，批准值为 `#12ccd8`。

## Required Changes

- 将批准的 `monooled-dark` semantic token set 同步到 `one-dark-pro`。
- 保留 `monooled-dark`、`one-dark-pro`、`high-contrast` 和 `REQUIRED_TOKENS` contract。
- 保持 routing 与用户 mode persistence 语义不变。
- 将 `qt_theme.py` 的圆角说明同步到当前 12/8/16/8 scale。
- 增加 runtime dark token 回归断言。
- 修正直接运行时主题测试的颜色大小写比较，使 Qt 颜色序列化与 semantic token 表示一致。
- 将已确认的方案 B 持久化到 `.ai/DECISIONS.md` 和 `.ai/CURRENT_STATE.md`。

## Review Rework — Explicit Scope Authorization

第一次 Independent Review 将 `tests/test_qt_v81_transition_latency.py` 标记为原始 Allowed Product Files 之外的 scope expansion。该文件直接验证 runtime theme application；批准的暗色 token 使用小写 hex 表示后，原断言把 `QColor.name().upper()` 与小写 token 直接比较，暴露了测试断言的大小写规范化问题。

用户在本次 Review Rework 中明确授权将该文件加入 TASK-002 Allowed Files。保留一行最小修复：对 semantic token 也调用 `.upper()` 后比较。该授权只覆盖颜色字符串大小写规范化，不允许修改 latency contract、阈值、计时逻辑或其他 v81 行为。

## Allowed Files / Expected Area

- Existing user-work files listed in `Pre-Task Baseline` may receive only the
  scoped theme/token/radius updates above.
- `tests/test_qt_v81_transition_latency.py` is explicitly authorized by the
  Review Rework to contain only the one-line case-insensitive runtime color
  assertion repair described above. No latency or other v81 behavior may change.
- `.ai/CURRENT_STATE.md`, `.ai/DECISIONS.md`, and this TASK contract are
  workflow control-plane changes.

## Review Rework Allowed Files

本次第一次 Independent Review 的 rework 只允许触及以下文件：

- `.ai/tasks/TASK-002.md`
- `.ai/CURRENT_STATE.md`（仅用于准确记录 deferred conflict）
- `.ai/DECISIONS.md`（仅保留已确认的方案 B）
- `tests/test_qt_v81_transition_latency.py`（仅一行颜色字符串大小写规范化）

本次 rework 不再修改任何生产主题代码、圆角实现、设计文档、其他测试、
`src/ui_controls.py`、`BLOCKED.md` 或 `PROGRESS.md`。

## Popup Radius Review — Deferred Follow-Up Candidate

历史发现保留：`docs/DESIGN_SYSTEM.md` 将 Popups 列入 Panel 12px；`src/ui_controls.py` 的 `StudioPopover` 原生 mask、注释和现有测试仍明确锁定 6px transient radius。

本次 Review Rework 将该问题从 TASK-002 当前实现范围 carve out，标记为 `DEFERRED FOLLOW-UP CANDIDATE`。TASK-002 不修改 `src/ui_controls.py`，不修改 popup tests 以伪造一致，也不创建 TASK-003。该冲突不被宣布为已解决。

## Acceptance Criteria

1. `dark` 与 `system_dark=True` 继续解析到 `one-dark-pro`；light routing 保持 `monooled-light`。
2. 实际可达的 `one-dark-pro` 使用批准的完整暗色 semantic token set。
3. 所有主题继续满足 `REQUIRED_TOKENS`，high-contrast 和 mode persistence compatibility 保持不变。
4. TASK-002 scope 内的 panel/control/pill/menu radius tokens、设计文档和相关 tests 一致。
5. `tests/test_qt_v81_transition_latency.py` 的授权扩展只包含颜色字符串大小写规范化，不改变 latency contract 或其他 v81 行为。
6. `StudioPopover` native 6px mask 与 Design System popup classification 的冲突被明确记录为 deferred follow-up candidate。
7. TASK-002 不通过修改 out-of-scope `ui_controls.py` 或降低 popup tests 来掩盖该冲突。
8. PRE-TASK-002 user work 与 TASK-002 changes 可审计区分，`BLOCKED.md` / `PROGRESS.md` 不被清理或提交。
9. `.ai/CURRENT_STATE.md`、`.ai/DECISIONS.md` 和本 TASK contract 准确记录方案 B 与 deferred conflict。
10. 不发生无关代码重构；本阶段停在 `VERIFY / PENDING`。
11. TASK-002 没有任何未经授权的 staging、commit、push、PR、tag 或 release；Review Baseline publication 仅在用户后续明确授权后执行，并严格限制为批准的 10 文件，未包含 `BLOCKED.md` / `PROGRESS.md`，也未执行 force/rebase/PR/tag/release/history rewrite。

## Out of Scope

- 改变 routing、删除或重命名任何主题；
- 修改 high-contrast、Preferences 架构、主题选择 UI、Automation API、schema、构建或发布；
- 修改 `ui_controls.py` 以绕过 popup mask 冲突；
- 清理、删除或提交 `BLOCKED.md`、`PROGRESS.md`；

## Initial Implementation Boundary

TASK-002 本地 implementation / verification 阶段最初未授权 staging、commit、push、PR、tag、release、rebase、stash、reset、clean。

## Review-baseline Publication Authorization

TASK-002 在 `VERIFY / PENDING` 阶段后，用户单独授权建立 GitHub Independent Review Baseline。该 publication 只允许以下 10 个文件：

```text
.ai/CURRENT_STATE.md
.ai/DECISIONS.md
.ai/tasks/TASK-002.md
docs/DESIGN_SYSTEM.md
src/qt_theme.py
src/theme_system.py
src/ui_metrics.py
tests/test_qt_theme.py
tests/test_v10_ui_craft_contract.py
tests/test_qt_v81_transition_latency.py
```

Review Baseline 使用 commit message：

```text
feat(theme): apply approved MonoOLED dark visual system
```

并以 normal fast-forward push 发布到 `origin/main`。`BLOCKED.md` 与 `PROGRESS.md` 明确排除。该授权不包括 force push、force-with-lease、amend、rebase、merge、PR、tag、release 或 history rewrite。

第一次稳定 Review Baseline 为：

```text
d7641e7097bd7d94873936912cc5ddefef47603e
```

该 SHA 是 TASK-002 的 Review Evidence，不属于 `.ai/CURRENT_STATE.md` 的瞬时 Git 状态。

## Verification Plan

- 运行 `tests/test_qt_theme.py`；
- 运行 `tests/test_v10_ui_craft_contract.py`；
- 运行 `tests/test_theme_model_v101.py`；
- 运行 `tests/test_qt_theme_transaction_v101.py`；
- 运行 `tests/test_qt_v81_transition_latency.py`；
- 复核此前已完成且直接覆盖 TASK-002 runtime behavior 的 targeted tests；
- 检查 `REQUIRED_TOKENS`、high-contrast、diff scope 和 protected workspace；
- 不把 targeted tests 描述为 full regression；不运行单进程 `pytest tests/`。

## Result

TASK-002 local implementation 首先完成并停在 `VERIFY / PENDING`。第一轮 contract review 发现两个问题：v81 scope expansion 与 popup radius conflict。两项已完成 rework：v81 测试文件获得后续明确授权，popup native mask 冲突 carve out 为 `DEFERRED FOLLOW-UP CANDIDATE`。

随后用户单独授权建立 GitHub Review Baseline。该 publication 严格包含批准的 10 个文件，排除了 `BLOCKED.md` / `PROGRESS.md`，并使用 normal fast-forward push 发布到 `origin/main`。第一次稳定 Review Baseline 为 `d7641e7097bd7d94873936912cc5ddefef47603e`。当前仍等待最终 Independent Re-review。

## Review Status

PENDING
