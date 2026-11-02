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
| UI 线程单次阻塞（最长同步处理） | ≤ 16 ms | 笔画与主题切换处理函数 ≤ 1.1 ms。导出全部、交接包、批量验证、缩略图墙原本阻塞数百毫秒，2.0.1 之后（`f82540a`）改为后台执行：启动一次只占用 UI 线程约 5 ms（release，curing_lite 全状态矩阵）。Agent 通过桥同步调用 `render.all_states`、`validate.all_states`、`export.all` 时，现在先在 UI 线程上做版本与权限检查，再在工作线程上按快照计算，响应不变（`bridge::tests::matrix_calls_are_answered_off_the_draining_thread_with_the_same_result`）。152 步回放不经过桥，不受影响 | ⚠️ 长任务与 Agent 长调用已离开 UI 线程（MEASURED：单元与集成测试；未做真人交互测量）。Designer 几何编辑部分达标：125 元素场景 3.79–4.46 ms、`curing_lite` 夹具 1.78–2.10 ms 达标；50 digits 场景 21.4–22.7 ms、1005 元素压力场景 20.5–23.1 ms 未达标。该数字只覆盖基准发出的几何编辑、笔画和主题切换；状态编辑与整轮刷新另见下方 TASK-006 小节 |

未达标项的分析（MEASURED 数据 + 推断，推断部分标 HYPOTHESIS）：

1. **笔画延迟**：在帧中拆分后，应用自身工作约 5–6 ms（处理 ≤ 1 ms + 渲染 p95 ≤ 4.7 ms），其余 8–15 ms 是从输入到合成器调度下一帧的等待。隐藏检查器与输出面板、关闭网格/标尺/预览均不改变结果，说明不是界面复杂度。等待来自 Windows DWM/vsync 节拍（HYPOTHESIS：AfterRendering 位于交换缓冲之后，包含 vblank 等待）。G2 spike 的 7.4 ms 是在同一机器上测得的，原因尚未查明（可能与当时的合成器状态有关，HYPOTHESIS）。不关闭垂直同步无法压到 8 ms 以下；关闭会引入画面撕裂。**此项需要用户决定**：维持定义（目前不通过），或在不放宽数值的前提下明确预算指的是"应用处理 + 渲染工作"。代理不自行改变定义。
2. **完整证据包导出**：每个文件都按 V1 同样的可靠性契约写入（临时文件 + fsync + 重命名）。本机单次持久化写入约 5–7 ms，6 个文件 × 50 屏 = 300 次 fsync。已改为每批文件并发写入（从 2124 ms 降到约 1270 ms），但本机磁盘基本串行化 fsync。绕过 fsync 违反 AGENTS.md 的可靠性契约，不采用。spec 未说明"导出"指哪种，因此两种读法都列出，由用户在 Gate 中确认。
- UI 线程阻塞一项原先只测了笔画和主题切换；导出全部、交接包、批量验证、缩略图墙自 2.0.1（`f82540a`）起已改为后台执行，启动一次只占 UI 线程约 5 ms，Agent 批处理同样按快照在工作线程计算。校验也已离开 UI 线程，仍留在其上的是各处理函数的刷新体（渲染与模型重建）；数字见下方 TASK-006 小节，`max_handler_ms` 不代表所有处理函数。
- spec 要求的 debug 构建 watchdog 在第二轮审查后实现（`apps/mono-desktop/src/watchdog.rs`）：辅助线程每 5 ms 向事件循环投递一个探针，探针等待超过 16 ms 即在 stderr 报告。release 构建不启用。本机 debug 构建打开 `curing_lite` 时报告首帧前阻塞约 2.9 s（未优化构建，MEASURED）。

3. **冷启动**：事件循环在约 90–180 ms 进入；OpenGL 上下文与驱动初始化到首次 `RenderingSetup` 约 520–600 ms；首帧渲染约 400 ms（着色器编译、字形）。去掉指定中文字体对此无明显影响。可选方案（需要用户取舍）：首帧使用软件渲染器、延迟 GL 初始化等。

### 2026-10-31 Designer 编辑路径（TASK-012）

§4 原先没有一次场景编辑的数字：`stroke_p95_ms` 测的是 Pixel 工作区（基准会切到 workspace 1 和 256×128 文档），Designer 的按键路径从未进过表。本轮用同一个 G2 测法补测：`RUN_DESKTOP_BENCH.py --runs 3` 打开项目后、切到 Pixel 之前驱动 Inspector 的 X 字段 40 次（`designer_edit_p95_ms`），并在同一进程内对每个刷新入口取中位数（`panel_*_ms`）。场景规模由 `tools/BENCH_DESIGNER_PROJECT.py` 生成：把 `curing_lite` 复制到临时目录，追加 N 个 placeholder 或 K 个 digits 元素，并把含内容的页面设为活动页面；`test_assets/` 不被写入。

改动前（release，3 次运行，区间）：

| 工作负载 | designer_edit p95 | max_handler | panel_canvas | panel_validation |
|---|---|---|---|---|
| 1005 元素（1000 placeholder） | 466.6–480.3 ms | 444.6–492.0 ms | 374.9–418.7 ms | 23.5–28.9 ms |
| 55 元素（50 digits） | 214.8–254.8 ms | 216.1–261.5 ms | 38.5–44.1 ms | 131.1–150.5 ms |

改动后（同一台机器、同一测法、2026-11-01 第二轮返工后的最终 release 构建，每个工作负载 3 次运行）：

| 工作负载 | designer_edit p95 | max_handler | panel_canvas | panel_validation（会话缓存） | panel_validation_worker（工作线程实际路径） |
|---|---|---|---|---|---|
| 1005 元素 | 49.9–50.9 ms | 20.5–23.1 ms | 9.3–10.9 ms | 22.1–23.9 ms | 22.4–23.7 ms |
| 55 元素（50 digits） | 32.4–36.2 ms | 21.4–22.7 ms | 15.9–17.3 ms | 85.6–88.4 ms | 82.4–88.7 ms |
| 125 元素 | 20.2–20.8 ms | 3.79–4.46 ms | 1.77–2.01 ms | 6.87–7.41 ms | 6.78–8.27 ms |
| `curing_lite` 夹具 | 16.4–17.6 ms | 1.78–2.10 ms | 0.58–0.81 ms | 3.77–4.05 ms | 4.24–5.20 ms |

`max_handler_ms` 只统计基准发出的几何编辑、笔画和主题切换。其余处理函数在 UI 线程上的成本（中位数；每次采样前先等上一轮校验结束，所以包含校验快照克隆，但不含校验本身）。60 ms tick 上的工作（快照克隆、启动线程、`apply_findings`）不计入任何一行，本轮没有直接测量：

| 工作负载 | panel_refresh_all（刷新体，不含切屏时的读盘、建会话和基线渲染） | panel_state_edit | panel_geometry_edit | 空闲私有内存 |
|---|---|---|---|---|
| 1005 元素 | 11.1–13.4 ms | 8.2–10.3 ms | 15.5–17.6 ms | 194.0–201.4 MB |
| 55 元素（50 digits） | 15.1–16.0 ms | 14.2–14.8 ms | 14.9–16.2 ms | 81.3–84.2 MB |
| 125 元素 | 2.88–3.16 ms | 2.22–2.51 ms | 2.84–3.58 ms | 86.7–93.1 MB |
| `curing_lite` 夹具 | 1.21–1.37 ms | 0.93–1.16 ms | 1.08–1.61 ms | 75.0–79.5 MB |

（125 元素场景没有改动前的同法数据：它是第一轮测量之后才加进来的。`designer_edit_p95_ms` 含从输入到画面渲染结束的等待，与笔画一样受合成器节拍影响；`max_handler_ms` 是处理函数本身。3 次运行的区间在两个方向上都不是边界：第一轮独立 Review 在 1005 元素上测到过 28.8 ms 的 `max_handler`、60.8 ms 的 `designer_edit`，在夹具上测到过 22.7 ms 的 `designer_edit`；第二轮 Review 在 125 元素上测到过 12.7 ms 的 `max_handler`，并在同一构建的空闲机器上把 50 digits 测成 15.9–16.9 ms（3 次中 2 次超 16）。本文连续两轮测得的 50 digits 都是 21–23 ms，最早一轮是 15.3–16.8 ms，所以这个差异更像机器状态，不像代码回退，但原因未隔离。不论哪组数字，最坏值都超过 16 ms，判定为未达标。）

1005 元素改动后每一毫秒的去向（同一轮、中位数）：`panel_canvas_ms` 9.3–10.9，其中核心 `render_scene` 6.0–7.2（`panel_render_ms`）；`panel_navigator_ms` 3.0–3.7（整份元素列表的模型重建，与几何无关）；`panel_geometry_edit_ms` 15.5–17.6 是每次采样都真实改值、并包含校验快照克隆的完整处理函数（此前该行连续写入同一个值，后两次采样跳过了编辑事务，所以旧数字不能用来归因）；`panel_set_geometry_ms` 4.1–5.6 是事务本身（撤销快照对 1005 个元素做三次克隆和一次深比较，沿用 V1 的整数组撤销模型）；其余为模型写入与校验快照克隆。

改了什么：

1. `App::refresh_canvas` 的覆盖层与 `hit_test` 改读 `render_scene` 已经解析出的 rects，不再对每个元素调 `EditorSession::geometry(id)`；两条路径共用同一个 rect 优先级函数（完整 zone → 完整显式 rect → 渲染结果），所以画出来的框和点中的框一致（`mono_project::editor::overlay_rect`）。旧实现的 `geometry` 为找一个 id 克隆整个 `elements` 数组；text/digits 元素还会在临时场景上再渲染一次。1005 元素时这是 1005×(1005 元素克隆 + 线性扫描)，`panel_canvas` 从 374.9–418.7 ms 降到 9.3–10.9 ms；50 digits 场景从 38.5–44.1 降到 15.9–17.3。`EditorSession::elements` 改为借用切片，新增 `geometry_of` 接收元素与场景的分离借用，供整场景行走使用。
2. 校验移出 UI 线程：几何编辑、状态编辑、规则编辑和 `refresh_all`（切屏、打开、Agent 刷新）都把 scene/root/state/rules 快照交给工作线程，结果带 epoch 回到 60 ms 作业 tick，只应用最新 epoch；前一个结果落地前不会启动新的一轮，期间的编辑把 epoch 推高，落地后再校验最新状态。切屏时被放弃的那一轮可能还在收尾，但它的结果会被丢弃，所以准确的说法是"最多应用一个结果"，不是"最多一个线程在跑"。工作线程断连时清掉接收端并记日志，之后的编辑可以重新启动校验。脚本化 `dump:findings` 在读取前同步等待，GUI 校验的结果不变。校验本身仍按内容哈希读取资源（与 G4 §9 的 V1 对齐），工作线程每轮使用新的资源缓存，digit 密集场景一次 82.4–88.7 ms，现在只占工作线程。代价是 findings 更新变晚：一次编辑最坏要等在途的一轮、下一轮和两次 60 ms tick，持续编辑时结果会因 epoch 过期被丢弃，停手后才更新。
3. 新增回归测试 `crates/mono-project/tests/overlay_geometry.rs`：在夹具场景上逐元素断言"覆盖层的 rect == Inspector 的 geometry"，并固定"隐藏且无坐标"的兜底行为。它第一次运行就抓到本轮实现中途的一处分歧（`overlay_rect` 初稿让 zone 内 text 的覆盖层用了字形盒，Inspector 报 zone rect；这个分歧从未发布过，2.1.0 的覆盖层直接调用 `geometry`），据此在覆盖层里统一为 Inspector 的优先级：完整 zone → 完整显式 rect → 渲染结果（元素自身字段优先，覆盖不完整 zone）。测试直接调用生产函数，不再保留副本。

测得但本轮不改：

- `refresh_canvas` 里的 `effective_rules()` 克隆：早期一次临时测量为 0.006–0.013 ms，基准没有这一行，无法复核；
- `start_export` 在 UI 线程上的代表性状态矩阵：3.0–5.7 ms（560 个状态），单次调用；
- 每次编辑的整轮刷新：各面板中位数相加即函数体总量，没有发现重复计算。

预算结论：

- **UI 线程单次阻塞 ≤16 ms**：125 元素场景（`max_handler` 3.79–4.46 ms）与 `curing_lite` 夹具（1.78–2.10 ms）达标，这两个场景的状态编辑和刷新体中位数也都低于 4 ms；50 digits 场景（21.4–22.7 ms，见上方运行差异）与 1005 元素压力场景（20.5–23.1 ms）未达标。剩余下限是每次编辑都要重建的帧缓冲（1005 元素 6.0–7.2 ms，50 digits 14.9–16.6 ms）、覆盖层与差异模型构建以及 V1 的整数组撤销快照（1005 元素 4.1–5.6 ms）。压到 16 ms 以下需要增量或离屏帧缓冲，属于渲染器改动；本轮不改，也不改预算定义。
- **空闲私有内存 ≤80 MB**：预算只针对 `curing_lite` 夹具，75.0–79.5 MB（最终构建 3 次；更早的同代码构建曾测到 80.5 MB，超过预算，该项在运行间波动）。生成场景只报告不判定，`RUN_DESKTOP_BENCH.py` 对它们输出 `pass: null`：55 元素 81.3–84.2 MB、125 元素 86.7–93.1 MB、1005 元素 194.0–201.4 MB，都高于 80 MB。基准现在包含 40 次 Designer 画布渲染，与 §4 原记录的 67.8–68.9 MB 不是同一工作量，不能直接相减；HYPOTHESIS：差异主要来自分配器保留，而不是代码长期持有（`last_resolved` 保存每个元素解析后的条目）。
- 范围外的三份预算本轮未动，保持"未达标"：笔画 p95 重测 15.0–25.7 ms（四个工作负载合计；Pixel 编辑器，等待 vsync，定义仍待用户决定）；50 屏完整证据包未重测（fsync 可靠性契约，见分析 2）；冷启动 1108–1641 ms，重新构建后的首次启动 2385 ms（渲染器/后端实验，见分析 3）。

### 2026-11-02 整合后重测（TASK-015）

上面 TASK-012 的数字是在 2.3.0 整合（TASK-014）之前测的。本轮在整合后的树上重测（`integrate/2.4.0` 之上的 TASK-015 分支，release 构建，Windows 10，同一台机器，同一测法，每项 3 次运行）。机器没有隔离：桌面常驻程序照常运行，测量期间没有并行的构建或测试。

核心基准（`mono bench --project test_assets/projects/curing_lite/project.oled.json`，3 次）：

| 指标 | 预算 | 实测（3 次） | 结论 |
|---|---|---|---|
| 256×128 取模 + 格式化 p95 | ≤ 2 ms | 1.88 / 2.04 / 1.84 ms | ❌ 3 次中 1 次超标（整合前 1.40–1.62） |
| 50 个 Screen 导出：固件数据 | ≤ 500 ms | 290 / 307 / 335 ms | ✅ |
| 50 个 Screen 导出：完整证据包 | ≤ 500 ms | 1665 / 1654 / 1749 ms | ❌（整合前 1268–1383） |

桌面基准（`python tools/RUN_DESKTOP_BENCH.py --runs 3`；生成场景由 `tools/BENCH_DESIGNER_PROJECT.py --elements 1000` 与 `--elements 0 --digits 50` 生成，区间为 3 次的最小–最大）：

| 指标 | `curing_lite` 夹具 | 1005 元素 | 55 元素（50 digits） |
|---|---|---|---|
| designer_edit p95 | 23.7–62.1 ms | 62.2–102.7 ms | 61.7–81.4 ms |
| max_handler（预算 ≤ 16 ms） | 4.26–10.63 ms ✅ | 31.0–73.2 ms ❌ | 49.3–72.7 ms ❌ |
| panel_canvas | 0.56–0.65 ms | 6.96–11.70 ms | 17.8–29.7 ms |
| panel_render | 0.56–1.23 ms | 5.40–6.78 ms | 16.4–17.5 ms |
| panel_validation（会话缓存） | 3.11–3.67 ms | 19.2–31.2 ms | 78.6–118.9 ms |
| panel_validation_worker | 3.21–7.01 ms | 20.9–31.9 ms | 82.6–92.2 ms |
| panel_refresh_all | 2.55–4.96 ms | **306.9–517.3 ms** | 58.4–73.7 ms |
| panel_state_edit | 1.23–3.02 ms | 13.2–17.9 ms | 28.2–34.0 ms |
| panel_geometry_edit | 1.92–2.76 ms | 19.1–29.2 ms | 26.2–32.4 ms |
| panel_set_geometry | 0.03–0.06 ms | 3.84–6.10 ms | 0.28–0.52 ms |
| 空闲私有内存 | 62.2–63.7 MB ✅（≤ 80 MB） | 180.5–189.1 MB（只报告） | 69.9–71.1 MB（只报告） |
| 笔画 p95（预算 ≤ 8 ms） | 39.9–47.2 ms ❌ | 24.6–38.6 ms | 38.1–40.1 ms |
| 　其中笔画渲染 p95 | 15.7–19.3 ms | 8.6–16.3 ms | 11.1–12.7 ms |
| 主题切换 p95（预算 ≤ 50 ms） | 35.2–48.1 ms ✅ | 25.4–31.4 ms | 27.9–38.5 ms |
| 冷启动（预算 ≤ 1 s） | 955 / 1120 / 994 ms ❌ | 1404–2648 ms | 1074–1263 ms |

结论：

- **整合带来了回退**：1005 元素的 `panel_refresh_all` 从 11.1–13.4 ms 变成 306.9–517.3 ms；50 digits 从 15.1–16.0 ms 变成 58.4–73.7 ms；两个生成场景的 `max_handler` 都从 20–23 ms 升到 31–73 ms。夹具上 `max_handler` 4.26–10.63 ms，仍在 16 ms 以内。
- 原因（HYPOTHESIS，只读诊断，未计时、未修改）：2.3.0 把 `refresh_review()` 加进了 `App::refresh_all_inner`，所以不在 Review 工作区时也会每次刷新都执行。它会再渲染一次场景、生成 C 头文件，并对当前元素和基线元素做 O(n²) 的比较；每一对都要经 `py_str` 分配 id 字符串，被修改的元素还要做深比较。1005 元素时大约是一百万次比较，量级与多出来的 300–500 ms 相符。`panel_*` 各行没有单独统计 Review 刷新，所以这一项没有直接的数字。修复（例如只在 Review 可见时刷新，比较时按 id 建索引）不属于 TASK-015 的范围，需要单独立项。
- 笔画、主题切换和 Designer 编辑的等待时间整体高于整合前：笔画渲染 p95 在夹具上是 15.7–19.3 ms，整合前是 4.3–4.7 ms。这三项都受合成器节拍影响（分析 1），本轮没有把机器状态和代码差异分开，所以不判断是不是回退。
- 证据包导出（1654–1749 ms）和取模 p95（一次 2.04 ms）比整合前慢，但导出路径在这次整合中没有改动，差异没有隔离；这两项按实测记为未达标。
- 结论表沿用上面的定义，没有改动任何预算。

## 5. 记录在案的偏差

1. **字模生成（Pixel Studio → 字模生成）在没有字体文件时使用内置 5×7 字形**；V1 使用 DejaVuSans 或 Pillow 默认字体。属于 D6 的语义等价范围。
2. **输出工作台的"当前 Designer 场景帧"使用当前预览状态**；V1 使用场景初始状态。
3. **`render.annotated_preview` 的标注文字**用内置 5×7 字体（V1 为 Pillow 默认字体），并以 RGBA PNG 输出（V1 为 RGB）；框线与比例一致。
4. **偏好设置"重置工作区布局"**：Slint 面板没有可保存的几何布局，此按钮只恢复被隐藏的面板。**界面缩放（ui_scale）**在下次启动生效（Slint 在创建窗口时读取缩放系数）；V1 即时生效。
5. **桌面 Agent Bridge 每 60 ms 处理一次请求队列**（V1 为 10 ms 定时器）；超时语义相同（只在请求仍排队时返回 TIMEOUT）。
6. **会话令牌**由操作系统 CSPRNG（`getrandom`）生成 24 字节（V1 为 `secrets.token_urlsafe(24)`）；仅用于本机回环接口。
7. **后台作业的失败类型**：V1 记录 Python 异常类名（如 `ExportBlockedError`）；Rust 只区分 `KeyError` 与 `ValueError`。取消语义与 V1 相同：只有因取消而停止才记为 `cancelled`，取消后又因其他原因失败则记为 `failed`。
8. **桥接连接限制**（Rust 新增的防护，V1 没有）：单行请求上限 16 MiB（超出即返回 `INVALID_JSON` 并关闭连接）、最多 32 个并发连接（超出返回 `BUSY`）、空闲 300 秒断开。
10. **输出工作台"显示"组**（G6 准备期间补齐，见下方说明）：颜色只接受 `#RGB`、`#RRGGBB`、`#AARRGGBB` 三种十六进制写法（V1 的 `QColor` 还接受 `red` 等颜色名；已保存的颜色名在 V2 中按默认颜色显示）；取色使用 16 色预设面板加十六进制输入（V1 为系统颜色对话框）；输出字体为自由填写的字体名（V1 为系统字体下拉框，Slint 不提供字体枚举）。
11. **成员路径限制在项目根内**（Rust 新增的防护，V1 的 `scene.resolve` 不限制）：`../`、根外绝对路径和 `pattern` 穿越在校验时报 `ASSET_PATH_ESCAPE`，渲染时返回 `E-CORE-PATH`，文件不会被打开。检查是词法的：项目内指向根外的链接不会被发现，根的 8.3 别名和经链接的写法会被拒绝；Windows 上绝对路径可与根相差 ASCII 大小写或 `\\?\` 前缀；已知限制：在区分大小写的 Windows 文件夹中，这样的绝对路径可能指向只差 ASCII 大小写的同级目录。相对成员（包括序列的 `dir` 加 `pattern`）精确比较。外部场景声明的 `project_root` 决定它自己的根。这改变 2.1.0 的行为，见 CHANGELOG 的 Compatibility。
12. **阻断报告只到首个阻断帧**：V1 和 2.1.0 先验证完整矩阵再写报告，现在 `export`、`handoff` 在第一个阻断帧停止，报告表头写明检查了矩阵中的多少帧。`batch-validate` 仍覆盖全矩阵。同样见 CHANGELOG 的 Compatibility。
9. **矩阵级操作的资源缓存**：在一次渲染/校验/导出全部状态的过程中，每个资源文件只读取解码一次（批内视为不变）；交互式渲染仍按内容哈希校验每次读取，与 V1 一致。

### G6 准备期间发现的功能缺口

2026-10-20 在删除 V1 前，把 V1 界面中的所有中文字面量与 V2 的界面字符串逐一比对，发现 G4 漏掉了输出工作台的"显示"组：画布背景、网格线、像素填充和像素边框的颜色，像素大小，输出字体与字号，以及"重置显示"。V1 默认会在每个亮像素周围画 1 px 黄色边框，V2 之前没有。

已补齐：
- `apps/mono-desktop/src/display.rs` 与 `canvas.rs`：颜色校验、保存与应用。像素边框先合并为网格边线段，只保留可见单元格范围内的部分，与 V1 只绘制重绘区域一致。
- 同一时段对比未加显示组的构建（MEASURED）：笔画 p95 不变，渲染 p95 约 +1 ms，空闲内存 +12 MB（63–66 MB，预算 80 MB）。
- 两种被否决的方案（MEASURED）：
  - 按行裁剪的位图：GL 渲染器为每个裁剪生成一份纹理，内存 375 MB；
  - 单个 Path：内存 178 MB，笔画 45 ms。
- 画布原点改为取整像素：原点落在半像素时，GL 渲染器绘制的像素图比网格矩形偏 1 px（修复前即存在）。
- 软件渲染器下，线段端点约有 60 个像素与 GL 结果不同。
- 偏好键与 V1 相同（`pixel_studio.canvas_background` 等）。
- 测试：`display::tests` 3 个、`canvas::tests` 2 个。
- 截图验证（本机 MEASURED）。

比对中其余未命中的字面量都是措辞不同或只用于错误信息，功能已存在：图片来源、阈值提示、时间线错误等。

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
