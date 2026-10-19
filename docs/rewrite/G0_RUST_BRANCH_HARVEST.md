# G0 — `rust` 分支吸收记录

- 日期：2026-10-19
- 来源：本地分支 `rust`（tip `9c1572b`）及其 worktree `C:/Users/16429/.codex/worktrees/monooled-rust-v2/MonoOLED-Studio`
- 记录人：代理（本会话）

## 1. 语料覆盖对照

`rust` 分支的 `test_assets/rust_v2/goldens.json` 共 13 个 case，全部被新的 `fixtures/golden/` 覆盖：

| rust 分支 case | kind | 新语料中的对应 |
|---|---|---|
| `encoding-h-r-m` … `encoding-v-r-l`（8 个） | encoding | `encoding` 类别：4 种模式 × 2 种位序 × 2 种极性 × 8 种尺寸，共 128 个 case |
| `polarity-padding` | encoding | `enc-13x17-*-zero_is_lit`、`enc-10x7-*`、`enc-1x1-*` |
| `framebuffer-boundary` | framebuffer | `fb-128x32-pixels-and-mask`、`fb-16x8-negative-origin-mask`、`fb-8x7-vlsb-rejects-partial-page` |
| `builtin-5x7` | font | `fontpack-builtin-5x8-roundtrip`、`fontpack-builtin-6x10-roundtrip` |
| `legacy-project` | project | `project-legacy-open-no-output-workbench`、`project-curing_lite-open` |
| `legacy-pixel-c-export` | export | `fmt-legacy_pixel_c-*`（16 个） |

结论：`MEASURED` — 新语料是 rust 分支语料的超集，不需要补充 case。

## 2. 从 Phase 1 证据中保留的经验（G2 spike 时使用）

来源：`git show rust:.ai/rust/PHASE-1-EVIDENCE.md`、`PHASE-1-REPORT.md`。

- GitHub Windows runner 的会话中没有 OpenGL 2.0。`egui_glow` 因此直接启动失败（`egui_glow requires opengl 2.0+`）。G2 必须验证候选框架在**无 GPU、无 GL2** 时的软件渲染回退。
- Linux X11 需要 `libxkbcommon-x11-0`；在 CI 中用 `xvfb-run`，并设置 `LIBGL_ALWAYS_SOFTWARE=1`。
- Wayland 可以用 weston headless 尝试；失败时必须作为一次尝试记录下来，不能静默豁免。
- "自驱动 GUI 证据模式"的设计值得沿用：
  - 在真实事件循环、真实布局和真实渲染器中，由程序按真实布局计算坐标并驱动手势处理函数；
  - 最后写出 JSON 报告，任一步失败时以非零码退出；
  - 不声称做了 OS 级事件注入。
- 手势契约：一次连续手势只产生一个撤销步骤；直线预览在目标移动后必须清除旧预览；缩放和平移不得改变文档像素。

## 3. worktree 中未提交的设计稿

worktree 中有**未提交**的修改：
- 新文件 `DESIGN.md`（Raycast 设计语料）；
- 新文件 `docs/RUST_UI_DESIGN.md`（状态为"选定方向，待实现"）；
- 改动过的 `AGENTS.md` 和 `docs/README.md`。

这些属于受保护的已有工作，本会话**没有修改、提交、移动或删除**它们。

`docs/RUST_UI_DESIGN.md` 记录的方向如下，与框架无关的部分在 G3 采纳：
- Raycast 风格的深色开发者工具语言；
- 四级 surface（`#07080a`、`#0d0d0d`、`#101111`、`#121212`），hairline 为 `#242728`；
- 强调色只用于表达状态：蓝表示焦点，绿表示成功，黄表示警告，红表示错误；主按钮为白底黑字；
- 字体用 Inter，退回系统 sans；间距以 4px 为基准；
- 主布局：工作区工具条 + 左侧工具栏 + 中央 OLED 画布 + 右侧 Inspector + 状态栏；
- OLED 画布的颜色、网格和缩放不进入导出数据。

更正（2026-10-19，G3 开始前）：前一版本记录写的是"G3 采用该 Raycast 方向"。但 `.ai/DECISIONS.md` 的 ADR-004 是用户已确认的决定：深色外观使用批准的 MonoOLED 深色 token，并落实到 `one-dark-pro`。而该 Raycast 稿既未提交，也未经用户确认。按 `.ai/README.md` 的权威顺序，已确认的 ADR 优先。

因此 G3 沿用 V1 `theme_system.py` 的三套主题（`monooled-light`、`one-dark-pro`、`high-contrast`），保持 token 值不变。Raycast 稿只作为参考保留在 worktree 中，不采用。

## 4. 归档动作

| 动作 | 结果 |
|---|---|
| 本地 tag `archive/rust-v2-validation` → `9c1572b` | 已创建（见下方命令） |
| push tag | 未执行：取证不需要，属于对外操作 |
| 删除 worktree | **不执行**：worktree 含有未提交的设计稿 |
| 删除本地或远端 `rust` 分支 | **不执行**：保留该分支以便回溯，不属于产品完成的必要步骤 |
