# Confirmed Decisions

本文件只保存用户已经确认、适合跨任务复用的工作流、产品或工程决定。建议、猜测、未决方案、TODO、brainstorming 和瞬时 Git 状态不属于本文件。

## ADR-001 — Existing governance remains authoritative

`AGENTS.md` 继续作为仓库 Agent 总入口，`docs/AI_HANDOFF.md` 继续承担产品定位、架构、兼容性、验证、发布纪律和 AI 接手导航。AI Workflow 不创建或引入重复的 `PROJECT_CONTEXT.md`。

## ADR-002 — `.ai/` is the repository-maintenance control plane

`.ai/` 保存 ChatGPT × Codex 的 TASK Contract、已确认工作流决定和长期状态。它不属于终端用户产品文档，因此不加入 `docs/README.md`，也不把维护工作流复制进 `docs/ai/`。

## ADR-003 — Transient repository state is queried dynamically

HEAD、工作区 dirty/clean、暂存项、未跟踪文件、本地与远端同步状态和推送状态都必须在执行前动态查询，不写入 `.ai/CURRENT_STATE.md`。未决的产品方案不属于已确认决定。

## ADR-004 — Preserve the runtime dark identifier and apply the approved dark visual there

产品方案 B 已确认：保留 `mode="dark"` 与系统深色到 `one-dark-pro` 的现有解析兼容性，不改为 `monooled-dark`。批准的 MonoOLED 深色 semantic tokens 应落实到实际可达的 `one-dark-pro`；`monooled-dark` 继续保留为公开主题标识和兼容资产，`high-contrast` 不受影响。

## ADR-005 — Rust full rewrite on main (main-only), superseding Rust ADR-001

用户于 2026-10-19 在对话中逐节确认以 Rust 全量重写 MonoOLED Studio，设计见 `docs/rewrite/2026-10-19-rust-rewrite-design.md`。本决定取代 `rust` 分支上的 Rust ADR-001（"Validation only，Full rewrite NOT APPROVED"）。

- D1 范围：功能对等 + 契约兼容；严格类输出与 V1 逐字节一致；UI 可重新设计，但不新增功能。
- D2 UI 框架：Slint vs Tauri 2 + React，由 G2 实测决定；排除 egui。
- D3 工作流：阶段 Gate。
- D4 V1 退役：打 `v1-final` tag 后，从 main 删除 Python 源码、测试和构建。
- D5 推进方式：先契约、逐步替换（黄金语料 → 无头 Core → UI spike → 工作区）。
- D6 字体：已存为 1-bit 的数据逐字节一致；从 TTF 新生成的字形只要求语义等价。
- 分支：main-only，不开长期分支。
- V1 从此 bugfix-only；凡影响契约输出的修复，必须同时更新黄金语料并记入证据。
- 证据分级：`MEASURED`、`DOCUMENTED`、`HYPOTHESIS`、`NOT_VERIFIED`。机器结果不代替真人测试。

本 ADR 不授予任何代理额外权限；操作授权以用户在当次会话中的明确指示为准。
