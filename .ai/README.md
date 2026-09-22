# ChatGPT × Codex Workflow Protocol

`.ai/` 是 MonoOLED Studio 的 repository-maintenance control plane。它保存跨会话的任务契约、已确认决定和长期工作状态，不替代产品文档、架构导航或实时代码事实。

产品架构、兼容性、验证和发布导航继续以 [`docs/AI_HANDOFF.md`](../docs/AI_HANDOFF.md) 为真源。`.ai/` 不建立 `PROJECT_CONTEXT.md`，也不进入 `docs/README.md` 的产品文档索引。

## Authority and read order

判断项目事实时按以下顺序处理：

1. 用户当前明确目标与限制；
2. `AGENTS.md`；
3. 实时仓库事实：Git、源码、测试、机器可读契约、版本和清单；
4. 用户已经确认且仍有效的 `.ai/DECISIONS.md`；
5. `docs/AI_HANDOFF.md` 的架构导航、兼容性和验证说明；
6. `.ai/CURRENT_STATE.md`；
7. AI 对话总结。

如果这些层级冲突，报告 `AUTHORITY CONFLICT`，不要自行选取一个结果。TASK 只规定本轮 scope、限制、验收和验证方式；如果 TASK 假设与仓库事实冲突，报告 `TASK ASSUMPTION CONFLICT`。

## Roles

### User

- 做最终产品决定；
- 授权实施、确认 scope；
- 批准高风险或外部操作；
- 决定未决产品方案。

### ChatGPT

```text
需求澄清
→ 读取 GitHub / 权威资料
→ 分析
→ 生成 TASK Contract
→ 独立 Review
→ PASS / REWORK REQUIRED
```

ChatGPT 不因为 Codex 声称 `done` 或 `all tests passed` 就直接判定完成，必须重新读取证据。

### Codex

```text
READ
→ VERIFY ASSUMPTIONS
→ SCOPE
→ ESTABLISH FAILURE EVIDENCE
→ IMPLEMENT
→ TEST
→ DIFF REVIEW
→ REPORT
→ VERIFY
```

Codex 必须保护进入任务前的用户修改，区分 `PRE-EXISTING USER WORK` 和本轮 TASK 改动，并按实际运行结果报告验证。Codex 不得自行把 `VERIFY` 推进为 `DONE`，也不得把 `PENDING` 推进为 `PASS`。

## TASK lifecycle

```text
DRAFT → APPROVED → IN_PROGRESS → VERIFY → DONE
```

独立 Review 结果只有 `PASS` 或 `REWORK REQUIRED`。出现 `REWORK REQUIRED` 时，必须形成明确修复范围；Codex 不应无限扩大范围自行修复。

每个任务文件使用以下结构：

```text
Status
Goal
Background
Current Problem
Evidence
Required Changes
Out of Scope
Protected Existing Work
Constraints
Allowed Files / Expected Area
Acceptance Criteria
Verification Plan
Deliverables
Result
Review Status
```

## Operating rules

- 任务开始时先读取本文件、`AGENTS.md`、相关 `docs/AI_HANDOFF.md` 章节和 active TASK。
- 进入任务时已有的修改、未跟踪文件和本地证据均属于受保护上下文，除非用户明确授权，不得清理、覆盖、暂存、提交或共享。
- 瞬时 Git 状态必须在执行前动态查询；长期状态文件不得保存精确 HEAD、dirty/clean、暂存列表、未跟踪列表或推送状态。
- 没有用户明确授权时，不执行 push、PR、tag、release、force push、rebase、stash 或 clean。
- 验证命令必须与任务风险匹配，并报告实际运行的命令、结果、跳过项和未运行门禁。
