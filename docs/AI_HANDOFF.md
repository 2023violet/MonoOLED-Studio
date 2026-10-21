# MonoOLED Studio AI 开发交接

> 面向接手本仓库维护、修复、功能开发和发布工作的 AI。
> 更新日期：2026-10-20（Asia/Shanghai）。对应 2.0（Rust 重写，ADR-005）切换完成后的 `main`。

## 1. 如何使用这份文档

这份文档用于导航和说明约束，不是比源码更高的永久真相。开始工作时，按以下优先级判断事实：

1. 用户当前明确提出的目标与限制；
2. 当前会话或仓库提供的 `AGENTS.md` 等代理指令；
3. 实时的 `git status`、当前源码、测试和构建产物；
4. `Cargo.toml` 中的版本号、机器可读契约（`crates/mono-automation/src/method_specs.json`）、项目格式、黄金语料；
5. 本文档以及 `docs/rewrite/` 中的历史快照。

本文档与实时证据冲突时，以实时证据为准，并查明变化来源。

## 2. 产品目标与边界

MonoOLED Studio 是跨平台（Windows / macOS / Linux）的通用单色 OLED 工作台，主要服务四类任务：

- Scene Designer：编排场景；
- Pixel Studio：编辑 1-bit 像素资源；
- Font Lab：维护 Font Pack；
- 取模与输出工作台：生成固件数组、索引或二进制数据。

此外还有 Automation API 1.3.0 和 `mono` 命令行。

产品边界是 `generic-1bit-oled`。`test_assets/projects/curing_lite/` 是回归夹具，不能把其中的医疗或业务规则提升为产品默认值。不支持 GIF。不要把仅由 host 测试证明的行为写成已验证的硬件能力。

## 3. 基线与真源

| 项目 | 真源或验证方法 |
| --- | --- |
| 产品版本 | `Cargo.toml` → `[workspace.package] version`；`monooled-studio --version` |
| 发布 | GitHub Releases；`git show-ref -d refs/tags/v<版本>` |
| 1.x 最后源码 | `v1-final` 标签（Python/PySide6，含黄金语料导出工具） |
| Automation API | `1.3.0`；`crates/mono-automation/src/method_specs.json`、`docs/AUTOMATION_API_V1.md` |
| 项目 schema | 顶层 `schema_version = 1`；`output_workbench.schema = 1`；`crates/mono-project/src/project.rs` |
| 与 1.x 的一致性 | `fixtures/golden/`（冻结语料）+ `crates/*/tests/golden_*.rs` |
| 重写决策与证据 | `.ai/DECISIONS.md` ADR-005；`docs/rewrite/`（spec、G0–G6 证据） |

## 4. 接手后的前十分钟

```bash
git status --short --branch
git log -5 --oneline --decorate
git worktree list
git rev-list --left-right --count origin/main...main
cargo test --workspace --locked
```

然后判断：

1. 当前分支、上游和用户要求是否一致；
2. 是否存在未提交的修改、未跟踪的文件，或其他工作树中的用户修改；
3. 用户要的是只读诊断、代码修改、发布，还是导出项目内容；
4. 需要的证据能否由现有测试获得，还是必须新增回归测试。

在检查工作区之前，不要执行清理、批量格式化、变基、强制推送、重打标签或删除分支。

## 5. 架构地图

### 5.1 Workspace

| Crate | 职责 |
| --- | --- |
| `crates/mono-core` | 无界面、无文件 I/O 的核心：帧缓冲、取模、格式化、输出配置、栅格化、场景状态与渲染、Pixel 文档、Font Pack 模型 |
| `crates/mono-project` | 文件系统边界：项目工作区、场景文件、原子写入、资源缓存、导出与 Code AI 交接、自动保存、模板、资源导入、编辑会话 |
| `crates/mono-font` | 从 TrueType 生成字形（Font Lab） |
| `crates/mono-automation` | Automation API 1.3.0：服务、5 个领域分发器、事务、事件、作业、localhost JSON-RPC 桥 |
| `apps/mono-desktop` | Slint 桌面程序（`ui/*.slint` + `src/*.rs`） |
| `apps/mono-cli` | `mono` 命令行：validate / export / simulate / batch-validate / handoff / asset-audit / c-header / bench / bridge |

依赖方向：`mono-core` ← `mono-font` ← `mono-project` ← `mono-automation` ← apps。核心 crate 不依赖 Slint。

### 5.2 渲染路径

`Scene JSON + State → mono_core::state / render → FrameBuffer → 预览、校验、导出、Automation`

- `mono-core/src/render.rs` 是唯一的生产渲染器。
- 桌面程序、CLI、Automation 和导出都复用它，不要为预览或自动化另写一套"近似渲染器"。
- 资源通过 `mono-project/src/resources.rs` 按内容哈希缓存。批量操作（渲染、校验、导出全部状态）使用 `DiskResources::frozen()`，在一批内每个资源只读一次。

### 5.3 唯一的取模与输出路径

`画布/选区/场景帧/Font Pack/图片 → 1-bit 位图 → EncodingProfile → 编码结果 → TextFormatProfile → 预览或文件`

- `mono-core/src/encoding.rs`：编码纯函数，负责遍历、位序、极性和补位。
- `mono-core/src/profiles.rs`：Raster / Encoding / Text 配置、校验与内置模板。
- `mono-core/src/formatter.rs`：文本或 BIN、进制、包装字段、预览截断和 Font Pack 索引。
- `apps/mono-desktop/src/workbench.rs`、`pixel_ui.rs`：工作台 UI 胶水。

| UI 名称 | `bit_axis` | `group_order` |
| --- | --- | --- |
| 逐行式 | `horizontal` | `row_major` |
| 行列式 | `horizontal` | `column_major` |
| 逐列式 | `vertical` | `column_major` |
| 列行式 | `vertical` | `row_major` |

`msb_first/lsb_first` 和 `one_is_lit/zero_is_lit` 是两个独立维度。不足 8 点时先补逻辑灭点，再应用极性。

### 5.4 桌面程序

- `main.rs`：负责启动参数、窗口接线、快捷键路由和定时器。定时器包括作业轮询（60 ms）和自动保存（5 s）。
  - 启动参数：`--screenshot`、`--action`、`--screen`、`--window-size`、`--bench`、`--lang`、`--theme`、`--workspace`、`--version`。
- `app.rs`：`App` 状态，以及 Designer 的绑定与刷新。
- `guard.rs`：未保存修改保护，覆盖 Designer、Pixel 和 Font Lab，询问保存、放弃或取消。
- `pixel.rs` / `pixel_ui.rs`：Pixel Studio。
- `display.rs` / `canvas.rs`：显示颜色与像素边框。
- `fontlab.rs` / `fontlab_ui.rs`：Font Lab，在后台线程生成字形。
- `prefs.rs` / `prefs_ui.rs`：偏好设置与快捷键。文件、键名与 1.x 兼容。
- `extras.rs`：模板、资源、自动保存恢复、命令面板、性能面板。
- `agent.rs`：桌面版 Agent Bridge。每批请求把实时会话借给 Service，处理完一批记为一步撤销。
- `bench.rs`：`--bench` 交互性能测量。
- `watchdog.rs`：debug 构建的 UI 线程阻塞报告。
- `ui/*.slint`：界面；`i18n/strings.json`：中英文界面字符串（有测试保证两种语言的键齐全）。

非交互运行（`--screenshot`、`--bench`、测试）不会弹出对话框：遇到未保存修改按 `scripted_choice` 处理，没有设置时视为取消。

### 5.5 Automation API

- `service.rs`：会话、revision、事件、事务、权限，以及 `editor_attached`（桌面共享会话时生效）。
- `dispatch.rs`：领域方法；`jobs.rs`：长任务；`ops.rs`：矩阵级操作。
- `bridge.rs`：JSON-RPC 入口与 TCP 传输。只监听 127.0.0.1，会话令牌来自 CSPRNG。限制为：单行 16 MiB、32 个连接、空闲 300 s。

API 1.3.0 是兼容性契约。`export.c_header`、`export.current`、`export.all` 和 Code AI 交接包的行为不能在没有版本升级和兼容方案的情况下静默改变。事务提交只改变内存状态，写盘需要显式保存。

### 5.6 两种"AI 交接"不要混淆

- 本文档：给仓库维护者或开发 AI 的导航与约束。
- `mono-project/src/export.rs` 的 handoff：为软件用户的 OLED 项目生成确定性的 Code AI 交接 ZIP。

## 6. 数据与兼容性契约

### 6.1 项目持久化

- 顶层 `schema_version` 保持 `1`；输出工作台使用可选的 `output_workbench.schema = 1`。
- 旧项目缺少输出配置时，打开项目不得仅为补默认值而改写项目文件。
- 配置保存失败时，恢复上一份有效的内存状态。
- 输出配置 ID 只能使用小写 ASCII 字母、数字、`_`、`-`，最长 64 字符。
- 项目成员路径必须解析在项目根目录内。
- 原子写入（临时文件 + fsync + 重命名）、外部修改指纹和 Windows 大小写碰撞检查是可靠性契约，不得为了性能绕过。完整证据包导出的性能预算未达标，正是这个原因，见 G4 证据 §4。

### 6.2 字节确定性

- 已经是 1-bit 的 Pixel 文档、帧缓冲和 Font Pack 字形不得再次阈值化。
- `invert_source` 属于栅格化，`polarity` 属于编码，两者不能合并。
- 显示颜色、网格、像素边框、缩放和输出字体不得进入编码结果。
- 文本模板是纯文本，只替换允许的占位符，不执行代码。
- 预览最多显示 256 KiB，可以截断，但保存必须写入完整结果。
- Font Pack 旁置索引中的 offset 和 byte length 必须与真实数据切片一致。

### 6.3 与 1.x 的一致性

- `cargo test` 中的 golden 测试保护以下内容：编码、栅格化、Font Pack、场景渲染、项目导出、交接包、Automation 回放（18 个会话、152 步）。
- PNG/ZIP 的编码器与 1.x 不同，按内容比较。
- 已记录的偏差见 `docs/rewrite/G1_EVIDENCE.md` 和 `docs/rewrite/G4_EVIDENCE.md`。新增偏差必须写进证据文件，不能静默改变。

## 7. 关键文件导航

| 目标 | 首先阅读 |
| --- | --- |
| 产品使用方式 | `README.md`、`docs/USER_GUIDE_CN.md` |
| 精确取模语义 | `docs/OUTPUT_WORKBENCH.md`、`crates/mono-core/src/encoding.rs` |
| 项目格式 | `crates/mono-project/src/project.rs`、`docs/SCENE_SCHEMA.md` |
| Automation API | `docs/AUTOMATION_API_V1.md`、`crates/mono-automation/src/method_specs.json` |
| 窗口与命令路由 | `apps/mono-desktop/src/main.rs`、`app.rs` |
| 场景渲染 | `crates/mono-core/src/render.rs`、`framebuffer.rs` |
| Pixel 性能 | `apps/mono-desktop/src/pixel_ui.rs`、`canvas.rs`、`bench.rs` |
| 字库生成 | `crates/mono-font`、`apps/mono-desktop/src/fontlab.rs` |
| 构建与发布 | `docs/BUILD.md`、`tools/PACKAGE_RUST_RELEASE.py`、`.github/workflows/` |
| 重写背景 | `docs/rewrite/`；`docs/ENGINEERING_HISTORY.md`（1.x 历史） |

## 8. 验证策略

### 8.1 按改动选择最小充分证据

- 核心编码与格式：`cargo test -p mono-core`
- 项目、导出、交接：`cargo test -p mono-project`
- Automation：`cargo test -p mono-automation`（含回放）
- 桌面逻辑：`cargo test -p mono-desktop`
- 界面外观：`monooled-studio <项目副本> --screen <id> --action <...> --screenshot out.png`。必须在临时偏好目录和项目副本上运行，并查看截图。
- 交互性能：`python tools/RUN_DESKTOP_BENCH.py --runs 3`，需要 release 构建。
- 工具与治理：`python -m pytest tools/tests -q`

### 8.2 完整门禁

`docs/BUILD.md` 中的 CI 检查全部通过（三平台）。不要把部分测试通过说成"全部通过"。最终报告应写明实际运行的命令、结果和未运行的门禁。

### 8.3 安装包

`package.yml` 会在三个平台上构建安装包，并在干净环境中安装和冒烟测试。只有这个工作流通过，才能说某个平台的安装包可用。

## 9. Git 与发布纪律

### 修改前

- 先运行 `git status --short --branch` 和 `git worktree list`。用户已有的修改属于用户，不要清理、覆盖或顺手格式化。
- 只读诊断不授权修复。

### 修改中

- 行为变更先建立失败证据，再写最小实现。
- 改动保持手术式，不重构无关的大文件。
- `target/`、`dist-rust/`、`.oled/` 不进入源码提交。
- 新增正式文档时，同步更新 `docs/README.md`。

### 提交与发布

- 只有用户明确要求时，才推送、创建 PR、打标签或发布。
- 发布前确认 `Cargo.toml` 版本、`CHANGELOG.md`、标签和产物名称一致。`release-rust.yml` 会检查前两者。
- tag 只生成草稿 Release，由维护者人工发布。已发布的标签和附件不可变：不移动标签，不强制推送，不用 `--clobber` 替换附件。

## 10. 已知风险与证据缺口

- **取模名称与硬件事实错配**：黄金数组只能证明编码公式自洽。没有目标驱动的已知正确数组和实际上屏结果，不能声称某个预设适配某块硬件。
- **性能预算**：2.0 有四项预算记录为未达标，见 G4 证据 §4。导出全部、交接包、批量校验和缩略图墙仍在 UI 线程上同步执行；debug 构建的 watchdog 会报告这些阻塞。
- **平台覆盖**：
  - 真人在 macOS 和 Linux 桌面上的使用、Linux 的 GL 渲染器、Intel Mac 与 Linux arm64 都未验证。
  - macOS 应用没有开发者签名，也未公证。
  - Linux 包要求 glibc ≥ 2.39。
- **不能从 host 证据推出硬件结论**：黄金向量、截图和自动化预览都不是实际 OLED 面板验证。

## 11. 下一位 AI 的任务协议

开始任务时：

1. 用一句话重述用户真正要达成的结果；
2. 检查工作区、分支、上游和相关文件；
3. 区分实时证据、已发布基线和待验证推测；
4. 找到最接近需求的现有测试与实现路径；
5. 只在答案会改变方案、且只有用户知道答案时提问。

结束任务时，交付信息至少包括：

- 改了什么，改了哪些文件；
- 运行了哪些验证，结果如何；
- 哪些门禁没有运行；
- 还有哪些风险或外部证据缺口；
- 是否已提交、推送、打标签或发布。

## 12. 相关文档

- [项目 README](../README.md)
- [中文使用手册](USER_GUIDE_CN.md)
- [取模与输出工作台](OUTPUT_WORKBENCH.md)
- [Automation API](AUTOMATION_API_V1.md)
- [Scene Schema](SCENE_SCHEMA.md)
- [构建与发布](BUILD.md)
- [重写设计与证据](rewrite/2026-10-19-rust-rewrite-design.md)
