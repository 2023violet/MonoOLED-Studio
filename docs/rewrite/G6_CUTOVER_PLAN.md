# G6 切换计划 — V1 封存、删除 Python、发布 v2.0.0

- 日期：2026-10-20
- 依据：spec §3 G6 行（"给 V1 打 `v1-final` tag；从 main 删除 Python、PyInstaller 和 Python CI；发布 v2.0.0"，"用户确认；push、tag、发布逐次确认"），以及用户 2026-10-20 的指示："ask me before each tag, release or V1 deletion"。
- 前置条件：G4、G5 已由用户审阅（见 `G4_EVIDENCE.md` §8、`G5_EVIDENCE.md` §6）。四项性能预算按 ❌ 记录接受，不在 G6 前继续优化。
- 状态：**计划，尚未执行任何不可逆步骤。**

## 1. 分两段执行

| 段 | 内容 | 是否需要用户确认 |
|---|---|---|
| A 准备 | 本地提交，可回退；不打 tag，不删 V1，不发布 | 不需要逐步确认（按 spec，push 只在需要 CI 证据时进行） |
| B 切换 | 打 tag、删除 V1、发布 | **每一步单独确认**（⛔） |

## 2. A 段：准备（本地、可回退）

- **A1 删除演练**：在临时 git worktree（scratchpad 内，不在仓库目录里）删除 §4 列出的 V1 路径，然后运行 `cargo test --workspace`、`cargo clippy -D warnings`、`cargo deny check` 和打包脚本，证明 V2 不依赖 V1 文件。已知：Rust 代码只读取 `fixtures/golden`（其中有 V1 内置场景的冻结副本）和 `test_assets/`，两者都保留。演练结果写入 `G6_EVIDENCE.md`。
- **A2 治理测试迁移**：`tests/test_rewrite_governance.py` 会随 `tests/` 一起删除。改为 `tools/CHECK_GOVERNANCE.py`（检查同样的 ADR-005 与 CURRENT_STATE 规则），由 `rust.yml` 运行。
- **A3 文档改为 V2**：
  - `README.md`：安装、运行和构建说明。
  - `CONTRIBUTING.md`：cargo 工作流。
  - `SECURITY.md`：Automation 桥。
  - `AGENTS.md`：怎么跑、验证纪律、目录。
  - `docs/AI_HANDOFF.md`：V2 导航真源，V1 部分指向 `v1-final`。
  - 用户手册中文版和英文版：去掉 Python 启动方式，补上安装包说明与 Gatekeeper 放行方式。
  - `docs/WINDOWS_BUILD.md`：改写为三平台构建。
  - `docs/AUTOMATION_API_V1.md`：协议仍为 1.3.0，删去 Python 客户端示例，改为 `mono bridge`。
  - Issue 模板里的 `src/VERSION`：改为 `--version`。
  - `docs/README.md` 索引同步更新。
  - `CHANGELOG.md` 增加 2.0.0 条目，写明四项未达标预算和已知限制。
- **A4 发布工作流**：新增 tag 触发的 `release-rust.yml`。它复用 `package.yml` 的构建、安装测试和截图检查，然后把三个安装包和 `SHA256SUMS` 上传到一个 **草稿** Release；草稿不公开。删除 `release-windows.yml` 属于 B2。
- **A5 版本号**：工作区版本 `2.0.0-rc.1` → `2.0.0`（Cargo.toml、Cargo.lock），本地提交。

A 段完成后，push 一次以取得三平台 CI 证据（与 G5 相同的规则），然后进入 B 段。

## 3. B 段：切换（每步单独确认）

| 步骤 | 操作 | 影响 | 回退 |
|---|---|---|---|
| ⛔ B1 | 在当前 V1 最后状态打 annotated tag `v1-final`（候选：B2 删除提交的父提交，即 main 上 A 段之后的最新提交），并 push 这个 tag | 公开、长期存在 | 未被他人使用前可删除远程 tag；不覆盖、不移动已发布的 tag |
| ⛔ B2 | 在 main 上用一个提交删除 §4 的 V1 路径，push | V1 代码只保留在 `v1-final` 与历史中 | `git revert` 该提交 |
| ⛔ B3 | 打 annotated tag `v2.0.0` 并 push，触发 `release-rust.yml` 生成草稿 Release | 公开 tag；草稿不公开 | 同 B1 |
| ⛔ B4 | 用户检查草稿 Release 的说明、产物和校验和后，将其发布 | 对所有人公开 | 可撤回为草稿或删除，但下载过的人无法撤回 |

每一步执行前，我会说明具体的提交、tag 名称和命令，等用户明确回复后再执行。

## 4. 删除清单（B2）

删除：
- `src/`
- `tests/`
- `pytest.ini`
- `requirements.txt`、`requirements-dev.txt`、`requirements-build.txt`
- `VERIFY_PACKAGE.py`、`DELIVERY_MANIFEST.json`、`DELIVERY_README.md`、`SHA256SUMS.txt`
- `.github/workflows/ci.yml`、`.github/workflows/release-windows.yml`
- `tools/` 下的 V1 构建、交付与验证脚本：
  - `BUILD_*`、`VERIFY_*`、`CAPTURE_*`
  - `MonoOLEDStudio.spec`、`build_icon_res.py`
  - `CREATE_RUNTIME_ENV.bat`、`RUN_MONOOLED_DIAGNOSTIC.bat`、`RUN_WINDOWS_TEST_GROUPS.py`
  - `PUBLISH_GITHUB_RELEASE.ps1`、`Legacy_Scripts/`
- 依赖 V1 源码的语料与基线工具：
  - `EXPORT_GOLDEN_CORPUS.py`、`EXPORT_AUTOMATION_API_V1.py`、`MAKE_GOLDEN_INPUTS.py`、`golden_corpus/`
  - `MEASURE_V1_BASELINE.py`

  它们生成的语料已冻结在 `fixtures/golden/`，需要重新生成时从 `v1-final` 检出。

保留：
- `apps/`、`crates/`、`fixtures/`、`test_assets/`、`docs/`、`.ai/`
- `tools/PACKAGE_RUST_RELEASE.py`、`tools/CHECK_SMOKE_SCREENSHOT.py`、`tools/RUN_DESKTOP_BENCH.py`、`tools/BUILD_AI_CONTEXT.py`、新的 `tools/CHECK_GOVERNANCE.py`
- `tools/README.md`（改写）

待定（在 B2 确认时一并询问）：
- `spike/`（G2 框架选型的 Slint / Tauri 原型）：建议删除，证据已在 `G2_EVIDENCE.md`。
- `docs/ENGINEERING_HISTORY.md`：建议保留，作为历史记录。

## 5. 不在 G6 范围内

- 四项未达标性能预算的优化（用户已决定按 ❌ 记录）。
- 代码签名、公证、MSI 安装程序、Intel Mac 与 Linux arm64 包（G5 记录为 NOT_VERIFIED / 未构建）。
- 不改动 worktree `C:/Users/16429/.codex/worktrees/monooled-rust-v2/MonoOLED-Studio`、`rust` 分支和已有的 git stash。
