# AGENTS.md — MonoOLED Studio 代理指令

## 定位

MonoOLED Studio 是跨平台（Windows / macOS / Linux）的单色 OLED 设计与取模工作台，用 Rust 编写，界面使用 Slint。主要功能：

- Scene Designer：编排场景；
- Pixel Studio：编辑 1-bit 像素；
- Font Lab：制作字库；
- 输出工作台：生成固件数组；
- Automation API 1.3.0 与 `mono` 命令行。

## 怎么跑

```bash
cargo run -p mono-desktop -- test_assets/projects/curing_lite
cargo run -p mono-cli -- validate --project test_assets/projects/curing_lite/project.oled.json
```

- 版本号：`Cargo.toml` 的 `[workspace.package] version`。
- 构建、打包与发布：见 [docs/BUILD.md](docs/BUILD.md)。
- Linux 需要的开发包：见 `README.md`。

## 验证纪律（先读这个再改代码）

- CI 门禁（三平台）：
  - `cargo fmt --all -- --check`
  - `cargo clippy --workspace --all-targets --locked -- -D warnings`
  - `cargo test --workspace --locked`
  - `python -m pytest tools/tests -q`
  - `cargo deny check`
- `fixtures/golden/` 是 1.x 冻结的黄金语料，不得为了让测试通过而改写；重新生成要从 `v1-final` 检出，并在重写证据中写明原因。
- 按改动选择最小充分测试、兼容性红线、发布纪律：见 [docs/AI_HANDOFF.md](docs/AI_HANDOFF.md)（开发交接真源，优先级高于本文件的摘要）。
- 行为变更先建立失败证据；只读诊断不授权修复；推送、打标签、发布只在用户明确要求时执行。
- GUI 运行与截图时，把 `APPDATA` / `LOCALAPPDATA` / `XDG_CONFIG_HOME` 指向临时目录，并在 `test_assets` 的副本上操作（打开 Screen 会写回项目清单）。

## 目录与约定

| 路径 | 用途 |
| --- | --- |
| `crates/` | `mono-core`（无界面核心）、`mono-project`（持久化与导出）、`mono-font`（字形生成）、`mono-automation`（Automation API） |
| `apps/` | `mono-desktop`（Slint 桌面程序）、`mono-cli`（命令行） |
| `fixtures/golden/` | 1.x 冻结黄金语料 |
| `test_assets/` | 冻结的测试夹具与回归资源 |
| `tools/` | 打包、截图检查、性能基准、治理脚本及其测试（`tools/tests/`） |
| `docs/` | 用户手册、格式契约、API、构建文档、重写证据（索引见 `docs/README.md`） |

- `target/`、`dist-rust/`、`.oled/` 是本地构建或运行产物，不进源码提交。
- 新增正式文档必须同步 `docs/README.md` 索引。
- 项目成员路径必须解析在项目根内；原子写入（临时文件 + fsync + 重命名）与外部修改指纹是可靠性契约，不得绕过。

## 当前状态

- 2.0 是 Rust 全量重写（ADR-005），设计见 `docs/rewrite/2026-10-19-rust-rewrite-design.md`，各 Gate 证据见 `docs/rewrite/`。
- Python 1.x 已从 `main` 删除，最后源码在 `v1-final` 标签。
- 已知未达标的性能预算与限制：见 `CHANGELOG.md` 2.0.0、后续版本的“已知限制”与 `docs/rewrite/G4_EVIDENCE.md` §4。

## AI Workflow Control Plane

长期架构、兼容性和验证规则继续以 `docs/AI_HANDOFF.md` 为导航真源。

跨 ChatGPT / Codex 的任务状态、已确认决策和 TASK Contract 位于 `.ai/`：

- `.ai/README.md`
- `.ai/DECISIONS.md`
- `.ai/CURRENT_STATE.md`
- `.ai/tasks/`

开始实施任务前必须读取 active TASK。TASK 只定义当前 scope，不得覆盖本文件、实时代码/测试事实或兼容性契约。

Codex 完成实现后只能推进到 `VERIFY`；`DONE` / `PASS` 必须由独立 Review 确认。

冷启动导航可运行 `python tools/BUILD_AI_CONTEXT.py` 生成 `.ai/GENERATED_CONTEXT.md`；该文件是可删除、可重建的派生索引，不替代 active TASK、实时 Git、源码/测试或权威文档的读取顺序。
