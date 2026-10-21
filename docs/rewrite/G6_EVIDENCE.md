# G6 证据记录 — 切换准备（A 段）

- 日期：2026-10-20 至 2026-10-21
- 计划：`G6_CUTOVER_PLAN.md`
- 状态：**A 段完成，代理自检完成；用户尚未审阅。B 段（打 tag、删除 V1、发布）一步也没有执行，每一步都需要用户单独确认。**

## 1. 删除演练（A1）

在 scratchpad 的临时 git worktree 中删除 V1 的全部路径（清单见计划 §4），然后运行检查。共做了两次。

| 检出 | 检查 | 结果（MEASURED） |
|---|---|---|
| `969169f`（计划提交） | `cargo test --workspace --locked`、`cargo clippy -D warnings`、`cargo deny check`、release 构建、`PACKAGE_RUST_RELEASE.py` 打出 Windows zip | 全部通过 |
| `6b43543`（本地分支 `g6/cutover`，即 B2 的候选提交） | `cargo test --workspace --locked`、`cargo clippy -D warnings`、`cargo fmt --check`、`python -m pytest tools/tests`（21 通过，1 个跳过：Windows 上的符号链接用例） | 全部通过 |

- Rust 代码只读取 `fixtures/golden/` 和 `test_assets/`，两者都保留。
- 删除后，唯一依赖 V1 文件的工具是 `BUILD_AI_CONTEXT.py`（读取 `src/VERSION`），已改为从 `Cargo.toml` 读取版本号。

## 2. 治理与工具测试迁移（A2）

- `tests/test_rewrite_governance.py`、`tests/test_ai_context_builder.py` 移到 `tools/tests/`，内容不变，只改了仓库根目录的定位和版本来源。
- 新增 `tools/tests/test_release_tools.py`：空白截图必须被拒绝，已记录的安装截图必须通过，打包脚本的版本号必须等于工作区版本。
- `rust.yml` 新增 tooling job（Windows + Linux，pytest 固定为 9.1.1）。

## 3. 删除前发现的功能缺口

在删除 V1 前，把 V1 界面里的全部中文字面量（556 个）与 V2 的界面字符串和 Slint 源码逐一比对。结果发现 G4 漏掉了输出工作台的"显示"组。详情、性能对比和被否决的方案见 `G4_EVIDENCE.md` 的"G6 准备期间发现的功能缺口"一节。

- 补齐提交：`110581b`，性能返工 `b5ceb41`。
- 同一时段对比未加显示组的构建（MEASURED）：
  - 笔画 p95：无回退；
  - 渲染 p95：约 +1 ms；
  - 空闲内存：+12 MB，为 63–66 MB（预算 80 MB）。
- 该时段本机的帧节拍与之前不同：未改动的旧构建，主题切换 p95 也是约 40 ms。因此这一时段的绝对数值不能与 G4 §4 的表格直接比较，只能在同一时段内做相对比较。

## 4. 文档（A3）

V2 文档描述的是删除 V1 之后的仓库，因此和删除放在同一个本地提交里：分支 `g6/cutover` 上的 `6b43543`。这个分支没有推送。

- 共 361 个文件，+531 / −41737 行。
- 改写的文档：README、CONTRIBUTING、SECURITY、AGENTS、`docs/AI_HANDOFF.md`、中英文用户手册、新的 `docs/BUILD.md`（取代 `WINDOWS_BUILD.md`）、`tools/README.md`、Issue 与 PR 模板、`docs/ENGINEERING_HISTORY.md` 的结尾段落，以及 `.ai/CURRENT_STATE.md`。
- 对 `src/VERSION`、`VERIFY_PACKAGE`、`requirements*.txt`、`RUN_WINDOWS_TEST_GROUPS`、`WINDOWS_BUILD`、`release-windows`、`EXPORT_GOLDEN_CORPUS`、`pytest.ini` 做了全仓库检索。除历史记录外（`docs/rewrite/`、`.ai/records/`、`.ai/tasks/`、`fixtures/` 中的语料说明），没有残留引用。
- 文档中关于功能的说法逐条与代码核对过，例如：
  - CLI 参数和菜单位置；
  - Font Lab 字段与"字体文件或内置字形"；
  - 非 PNG 图片另存为 PNG；
  - 偏好文件路径；
  - crate 依赖方向。

## 5. 发布工作流与版本（A4、A5）

- 工作区版本改为 `2.0.0`，`CHANGELOG.md` 增加 2.0.0 一节（发布说明直接取自这一节）。提交 `7371ad7`。
- `release-rust.yml`：
  - `v2.*` tag 触发；
  - 检查 tag 与工作区版本一致，且 CHANGELOG 中有对应一节；
  - 复用 `package.yml` 构建并安装测试三个平台；
  - 生成 **草稿** Release，附带安装包和 `SHA256SUMS`；
  - 手动运行时是演练，不生成草稿。
- 演练 run `39558164718`（`7371ad7`，MEASURED）：
  - 版本检查通过；
  - 三个平台的打包与安装测试通过；
  - 收集到 3 个安装包：dmg 11.9 MB，zip 11.7 MB，deb 11.6 MB；
  - `SHA256SUMS` 与 CHANGELOG 发布说明都已生成；
  - 没有创建 Release（`gh release list` 中最新的仍是 v1.2.3）。
- 同一提交上的 `Rust`（`39558154133`）与 `CI`（V1，`39558154147`）都通过。
- push 触发的 `Package` run `39558156253` 被演练取消：两者使用同一个 concurrency group。没有失败的 job。修复：concurrency group 按触发事件区分（本提交）。

## 6. 未验证 / 风险

- `g6/cutover` 的完整三平台 CI：分支没有推送（推送需要用户同意），只有本地 Windows 上的检查（§1）。B2 推送后，CI 会在删除后的树上运行。
- 草稿 Release 的创建步骤（`gh release create --draft`）只能在真正打 tag 时运行，演练跳过了这一步。
- 其余缺口同 G5（真实用户安装、macOS Gatekeeper、Intel Mac、Linux arm64、真实 OLED 硬件）。

## 7. B 段（需要用户逐步确认）

| 步骤 | 内容 | 状态 |
|---|---|---|
| B1 | 在 main 当前 V1 状态打 annotated tag `v1-final` 并推送 | 待确认 |
| B2 | 把 `g6/cutover` 快进合入 main 并推送（删除 V1，换成 V2 文档） | 待确认 |
| B3 | 打 annotated tag `v2.0.0` 并推送，自动生成草稿 Release | 待确认 |
| B4 | 用户检查草稿后发布 | 待确认 |
