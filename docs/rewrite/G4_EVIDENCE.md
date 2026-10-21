# G4 证据记录 — 桌面应用与 Automation API

- 日期：2026-10-20
- 范围：`apps/mono-desktop`（Slint 1.18.1）、`crates/mono-automation`、`apps/mono-cli`（`bench`、`bridge`），以及 `mono-project`/`mono-font` 为此新增的模块
- 提交：`ca6feac`（G4a）、`edd1ddb`（G4c/G4d）、`76521a2`（G4b）、`337dbf1`（G4e）、`52858c3`（性能工具与导出并发写入）、`f46985c`（测试修正）；本文件随后续提交入库
- 测量环境：Windows 10 19045，本机显示器，release 构建（另注明者除外）
- Gate 状态：**代理自检完成；用户已于 2026-10-20 审阅（见 §8），四项性能预算按 ❌ 记录接受。** 按 spec §3，每个 G4 子 Gate 由用户确认，代理不得自行确认。

## 1. 子 Gate 内容与验收对照

| 子 Gate | 已实现 | 验收项（spec §3） | 结果 |
|---|---|---|---|
| G4a | 应用外壳（菜单、主题、语言、状态栏、原生对话框）；项目打开/保存；Pixel Studio（6 种工具、键盘绘制、缩放/平移/标尺、选区复制剪切粘贴裁剪、旋转/翻转/反相/清空、画布尺寸、导入并二值化、插入位图文字、PNG/BIN/C 头文件、字模生成）；输出工作台（5 种来源、配置编辑/另存/删除、生成/复制/保存） | 截图、测试、导出与语料一致、性能预算 | 截图 ✅；测试 ✅；导出 DOCUMENTED（见 §3）；性能见 §4 |
| G4b | Designer：选择/多选/拖动/对齐/分布/吸附/状态/时间线（G3 已有）；本阶段补齐模板、资源导入/转换/健康检查、位图文字、缩略图墙、自动保存与恢复、命令面板、面板开关、交互性能报告、V1 固定快捷键 | 同上 | 截图 ✅；测试 ✅；性能见 §4 |
| G4c | Font Lab：字形列表、共享像素画布编辑、切换时自动保存、生成/更新字形（后台线程 + 进度）、尺寸变更确认、TTF 自动排版、新建/打开字库 | 同上 | 截图 ✅；测试 ✅ |
| G4d | 偏好设置窗口（V1 七个分区、搜索、即时生效、保存状态）；可配置快捷键（冲突检测，窗口级分发）；浅色/深色/高对比；中文/英文 | 同上 | 截图 ✅；测试 ✅；主题切换性能 ✅ |
| G4e | Automation API 1.3.0：服务、5 个域分发器、事务、事件流、作业、localhost JSON-RPC（会话令牌、UI 线程排队执行）；`mono bridge`；桌面 Tools → Agent Bridge 共享 Designer 会话 | 回放 V1 录制的请求/响应，结果一致 | ✅ 18 个会话、152 步的响应一致；PNG/ZIP 编码器输出按内容比较（规则见 §2，MEASURED） |

截图（MEASURED，`--screenshot` 模式在真实窗口内截取）：`g4/designer_zh.png`、`g4/designer_dark.png`、`g4/designer_en.png`、`g4/pixel_studio.png`、`g4/font_lab.png`、`g4/preferences.png`、`g4/command_palette_en.png`。

截图之外的交互（鼠标绘制、拖动、对话框）由单元测试与代理脚本驱动验证，**未经真人操作**，标 `NOT_VERIFIED`（真人体验）。

## 2. Automation 语料回放（G4e，MEASURED）

- 命令：`cargo test -p mono-automation --release --test golden_automation`，退出码 0。
- 回放 `fixtures/golden/automation.json` 全部 18 个用例：16 个会话共 150 步 + 2 个原始请求，测试断言实际检查数为 152。
- 比较方式：响应按语料规则归一化（项目根 → `${PROJECT_ROOT}`、`elapsed_ms`）后**整体相等**；会话结束后的文件集合与语料 `files_sha256` 的键集合相等。
- 编码器相关字段按语料自身的说明（"PNG/ZIP file digests depend on the encoder; Rust compares them by content where applicable"）处理，属于 G1 偏差 4 的延伸。响应中的 `asset.*` 的 `sha256`/`bytes` 以及若干 `*_file`/ZIP 的 `sha256` 不比较字节；对应的**文件内容**按以下规则逐一比较，语料中出现、但没有规则的 PNG/ZIP 会让测试失败（审查返工后，MEASURED）：
  - `render.png`：`png_base64` 解码后与 V1 逐像素比较；`exports/preview.png` 与 V1 `render.png` 逐像素比较；
  - 导出目录中的每个 `reference/*.png`（共 169 个）：解码后的 VLSB 必须等于同名 `golden/*.bin`，后者与 V1 逐字节一致；
  - `exports/handoff.zip`：解压后 168 个 `golden/*.bin` 必须与 `export.all` 的同名文件逐字节一致；
  - `exports/golden_font.zip`：每个成员与 `fonts/golden/` 下的文件逐字节一致；
  - 字形 PNG：'A' 与 V1 `font.get_glyph` 响应的像素一致，'Z' 与 `font.update_glyph` 请求的像素一致，其余与内置 5×7 字形（G1 已证明与 V1 逐字节一致）一致；
  - `assets/golden/*.png`：8×4、全部点亮（与请求一致）；
  - `exports/annotated.png`：只比较尺寸（384×96），标注文字字体不同（偏差 3）；
  - 其余字段（VLSB 哈希、JSON 清单、错误码与消息、版本号、事件流）逐字节一致。
- ZIP 内的非 PNG 成员（契约 JSON、说明文件）没有 V1 逐成员摘要可比，只与本次导出的同名文件比较一致性，标 `DOCUMENTED`。
- 文本文件的 CRLF：V1 用 `write_text` 写的 Markdown 在 Windows 上为 CRLF（G1 偏差 2/12），测试接受 LF 内容按 CRLF 计算后的哈希。
- 另有 `bridge` 真实套接字测试（令牌校验、UI 线程排队执行、非法 JSON）和桌面端 Agent 测试（经 TCP 修改 Designer 实时会话，形成一步可撤销操作）；以及 `mono bridge` 与 Python 客户端的端到端冒烟（权限拒绝、令牌错误）。

## 3. 测试与 CI

- `cargo test --workspace`：全部通过（MEASURED，本机）。新增：mono-automation 7 个单元测试 + 回放；mono-desktop 28 个（像素、工作台、字库、偏好、快捷键、Agent、i18n 键覆盖等）；mono-project 5 个（模板库、自动保存、资源导入/转换）；mono-font 4 个。
- `cargo clippy --workspace --all-targets -- -D warnings`、`cargo fmt --check`、`cargo deny check`：通过（MEASURED）。
- 三平台 CI：`a79c315` 的 Rust run `39435560705` 三平台通过（首次在 Linux 上构建桌面应用）。`337dbf1` 的 run `39446456929` 在 Windows/macOS 失败，原因是一个测试把规范化后的路径与原始临时路径直接比较（macOS `/private/var`、Windows 8.3 短名），产品代码无误；`f46985c` 修正该测试，其 CI 结果见文末补记。
- 从桌面端导出与语料一致：桌面端的导出、交接包、C 头文件调用的是与语料测试相同的 `mono-project` 函数（`export_scene`、`build_handoff_package`、`framebuffer_to_c_header`），Agent 回放也经由同一路径。未做"在 GUI 中点击导出再与语料比对"的端到端测试，标 `DOCUMENTED`。

## 4. 性能预算（spec §5）

工具：`mono bench --project test_assets/projects/curing_lite/project.oled.json`（核心）与 `python tools/RUN_DESKTOP_BENCH.py --runs 3`（真实窗口，G2 同一测法：每次输入在上一帧 `AfterRendering` 后 2 ms 发出，延迟从输入计到画面渲染结束）。数值为 3 次运行。

工作负载说明（第二轮审查要求写明）：

- "50 个 Screen 导出"是把 `curing_lite` 的同一个 Screen 连续导出 50 次（50 个输出目录），资源缓存在批次内冻结；不是 50 个不同的 Screen。V1 基线用同样的做法。
- 笔画"输入"由基准直接调用 `App::pixel_pointer` 发出，不经过操作系统输入事件；系统输入队列的延迟不在测量范围内。
- 冷启动从启动器创建进程的时刻算起（`MONO_T0` 墙钟，与 V1 基线探针相同），包含操作系统创建进程和加载可执行文件；另报告 `main()` 之后的部分。

| 指标 | 预算 | 实测（3 次） | 结论 |
|---|---|---|---|
| 256×128 取模 + 格式化 p95 | ≤ 2 ms | 1.40 / 1.54 / 1.62 ms | ✅ |
| 50 个 Screen 导出：固件数据（渲染 + 取模 + 格式化 + 每屏一个原子文件） | ≤ 500 ms | 326 / 312 / 315 ms | ✅ |
| 50 个 Screen 导出：完整证据包（每屏 BIN/PNG/契约/清单/说明/校验报告 6 个持久化原子文件） | ≤ 500 ms | 1383 / 1268 / 1279 ms | ❌ |
| Pixel 笔画输入 → 画面 p95（256×128，8 倍） | ≤ 8 ms | 21.7 / 20.9 / 20.4 ms | ❌ |
| 　其中应用处理 + 渲染工作 | — | 处理 ≤ 1.0 ms；渲染 p95 4.3–4.7 ms | （≤ 8 ms） |
| 主题切换 p95 | ≤ 50 ms | 19.9 / 19.4 / 17.3 ms（渲染 p95 5.5 ms） | ✅ |
| 冷启动（创建进程 → 首帧渲染完成） | ≤ 1 s | 938 / 976 / 925 ms 与 949 / 1002 ms；重新构建后的首次启动 2069 ms（HYPOTHESIS：杀毒软件扫描新可执行文件）；其中 `main()` 之后 911–992 ms | ❌ 未达标（多次运行中有超标） |
| 空闲私有内存 | ≤ 80 MB | 67.8 / 68.6 / 68.9 MB | ✅ |
| UI 线程单次阻塞（最长同步处理） | ≤ 16 ms | 笔画与主题切换处理函数 ≤ 1.1 ms；导出全部、交接包、批量验证、缩略图墙、Agent 批处理会阻塞数百毫秒 | ❌ 未达标 |

未达标项的分析（MEASURED 数据 + 推断，推断部分标 HYPOTHESIS）：

1. **笔画延迟**：在帧中拆分后，应用自身工作约 5–6 ms（处理 ≤ 1 ms + 渲染 p95 ≤ 4.7 ms），其余 8–15 ms 是从输入到合成器调度下一帧的等待。隐藏检查器与输出面板、关闭网格/标尺/预览均不改变结果，说明不是界面复杂度。等待来自 Windows DWM/vsync 节拍（HYPOTHESIS：AfterRendering 位于交换缓冲之后，包含 vblank 等待）。G2 spike 的 7.4 ms 是在同一机器上测得的，原因尚未查明（可能与当时的合成器状态有关，HYPOTHESIS）。不关闭垂直同步无法压到 8 ms 以下；关闭会引入画面撕裂。**此项需要用户决定**：维持定义（目前不通过），或在不放宽数值的前提下明确预算指的是"应用处理 + 渲染工作"。代理不自行改变定义。
2. **完整证据包导出**：每个文件都按 V1 同样的可靠性契约写入（临时文件 + fsync + 重命名）。本机单次持久化写入约 5–7 ms，6 个文件 × 50 屏 = 300 次 fsync。已改为每批文件并发写入（从 2124 ms 降到约 1270 ms），但本机磁盘基本串行化 fsync。绕过 fsync 违反 AGENTS.md 的可靠性契约，不采用。spec 未说明"导出"指哪种，因此两种读法都列出，由用户在 Gate 中确认。
- UI 线程阻塞一项只测了笔画和主题切换。导出全部、交接包、批量验证、缩略图墙和 Agent 批处理都在 UI 线程上同步执行（与 V1 相同），会阻塞数百毫秒，**不满足 ≤ 16 ms**。改为后台执行属于后续工作。
- spec 要求的 debug 构建 watchdog 在第二轮审查后实现（`apps/mono-desktop/src/watchdog.rs`）：辅助线程每 5 ms 向事件循环投递一个探针，探针等待超过 16 ms 即在 stderr 报告。release 构建不启用。本机 debug 构建打开 `curing_lite` 时报告首帧前阻塞约 2.9 s（未优化构建，MEASURED）。

3. **冷启动**：事件循环在约 90–180 ms 进入；OpenGL 上下文与驱动初始化到首次 `RenderingSetup` 约 520–600 ms；首帧渲染约 400 ms（着色器编译、字形）。去掉指定中文字体对此无明显影响。可选方案（需要用户取舍）：首帧使用软件渲染器、延迟 GL 初始化等。

## 5. 记录在案的偏差

1. **字模生成（Pixel Studio → 字模生成）在没有字体文件时使用内置 5×7 字形**；V1 使用 DejaVuSans 或 Pillow 默认字体。属于 D6 的语义等价范围。
2. **输出工作台的"当前 Designer 场景帧"使用当前预览状态**；V1 使用场景初始状态。
3. **`render.annotated_preview` 的标注文字**用内置 5×7 字体（V1 为 Pillow 默认字体），并以 RGBA PNG 输出（V1 为 RGB）；框线与比例一致。
4. **偏好设置"重置工作区布局"**：Slint 面板没有可保存的几何布局，此按钮只恢复被隐藏的面板。**界面缩放（ui_scale）**在下次启动生效（Slint 在创建窗口时读取缩放系数）；V1 即时生效。
5. **桌面 Agent Bridge 每 60 ms 处理一次请求队列**（V1 为 10 ms 定时器）；超时语义相同（只在请求仍排队时返回 TIMEOUT）。
6. **会话令牌**由操作系统随机源播种的 `RandomState` 生成 24 字节（V1 为 `secrets.token_urlsafe(24)`）；仅用于本机回环接口。
7. **后台作业的失败类型**：V1 记录 Python 异常类名（如 `ExportBlockedError`）；Rust 只区分 `KeyError` 与 `ValueError`。取消语义与 V1 相同：只有因取消而停止才记为 `cancelled`，取消后又因其他原因失败则记为 `failed`。
8. **桥接连接限制**（Rust 新增的防护，V1 没有）：单行请求上限 16 MiB（超出即返回 `INVALID_JSON` 并关闭连接）、最多 32 个并发连接（超出返回 `BUSY`）、空闲 300 秒断开。
9. **矩阵级操作的资源缓存**：在一次渲染/校验/导出全部状态的过程中，每个资源文件只读取解码一次（批内视为不变）；交互式渲染仍按内容哈希校验每次读取，与 V1 一致。

## 6. 跳过项与已知限制

- 真人操作体验（拖动手感、输入法、DPI 150%）：`NOT_VERIFIED`。
- Linux/macOS 上的桌面性能与截图：未测，`NOT_VERIFIED`；CI 只证明能编译和测试通过。
- 真实 OLED 硬件：`NOT_VERIFIED`。
- 独立代理审查：见第 7 节。

## 7. 独立代理审查

### 第一轮（代理审查，静态 + 探针，2026-10-20）：`REWORK REQUIRED`

| # | 级别 | 发现 | 处理 |
|---|---|---|---|
| 1 | blocker | 关闭窗口、退出、打开项目/场景、新建项目时不询问未保存修改（Designer、Pixel Studio、Font Lab） | 新增 `guard.rs`：统一的保存/放弃/取消询问；窗口关闭（`on_close_requested`）、退出、打开、新建都先询问；4 个测试 |
| 2 | blocker | 切换页面时静默保存；删除页面先改项目再丢弃错误，绑定到已删除的文件 | 切换页面改为询问（V1 `_project_screen_changed`）；删除页面先询问、再修改项目、再绑定下一页，错误不再丢弃；测试覆盖 |
| 3 | blocker | Automation 切换页面后保留上一页的撤销历史与磁盘指纹（撤销会把旧页元素插入新页，保存失败） | 新增 `EditorSession::reset_scene`（V1 同名方法），`open_project_screen` 使用；桌面端 Agent 切换后重建差异基线；回归测试 `session_reset.rs` |
| 4 | major | 事务回滚不重置运行时状态（回滚 `state.set_schema` 后无法渲染） | 回滚时 `reset_scene`（与 V1 相同）；回归测试 |
| 5 | major | 回放测试对 PNG/ZIP 只检查"可解码/非空" | 改为 §2 中的逐项内容规则，未知文件判失败 |
| 6 | major | 本机任意进程可在验证令牌前耗尽内存或线程 | 单行上限、并发连接上限、空闲超时；测试覆盖（偏差 8） |
| 7 | minor | 非对象 JSON 返回 UNAUTHORIZED；假值 `params` 被拒绝 | 与 V1 对齐：`INVALID_JSON`；假值视为 `{}`；测试覆盖 |
| 8 | minor | 作业失败类型被合并；取消后的其他失败记为 cancelled | 取消判定已修正；类型合并记为偏差 7 |
| 9 | minor | 会话令牌不是 CSPRNG | 改用操作系统 CSPRNG（`getrandom`，已在依赖树中） |
| 10 | minor | 冷启动应写"未达标"；UI 阻塞一行未说明范围 | §4 已改 |
| 11 | minor | 自动保存恢复提示只在启动时出现 | 每次打开项目、场景或切换页面后都检查（与 V1 相同） |

返工后验证（MEASURED）：`cargo test --workspace` 全部通过（mono-desktop 32、mono-automation 9 + 回放 + 2 个回归）；`cargo clippy -D warnings`、`cargo fmt --check`、`cargo deny check` 通过。第二轮代理审查及其返工见 `G5_EVIDENCE.md` §5。

## 8. 用户确认

2026-10-20，用户在会话中答复（原文）：

> "Keep the four budgets as recorded FAILs and treat the G4/G5 evidence as reviewed. Then plan G6, but ask me before each tag, release or V1 deletion."

据此：G4 证据视为已审阅；四项未达标的性能预算（Pixel 笔画 p95、完整证据包导出、冷启动、UI 线程单次阻塞）维持记录为 ❌，不放宽数值、不改变定义，也不在 G6 前继续优化。G6 的每个 tag、发布与删除 V1 的操作仍需用户逐次确认。
