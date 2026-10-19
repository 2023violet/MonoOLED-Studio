# G2 证据记录 — UI 框架 spike（Slint vs Tauri）

- 日期：2026-10-19
- spike 代码：`spike/slint/`、`spike/tauri/`。两者都是可丢弃代码，不进入产品 workspace。
- 测量环境：Windows 10 19045，本机显示器；构建方式为 release。
- 方法：两个 spike 都在真实窗口和真实渲染器里，按同一套脚本自驱动运行：
  1. **画布**：256×128 位图按 8 倍缩放显示（2048×1024），连续落笔 400 次，每次改 1 个像素，测量从输入到画面呈现的延迟；
  2. **文本**：一次性加载 256KiB 的取模文本，测量首帧时间；
  3. **场景**：50 个元素同时平移 200 次，测量每次移动的延迟。
  
  空闲内存在窗口稳定 1.5 秒后采样。

## 1. 实测结果（MEASURED）

| 指标 | Slint 1.18.1（femtovg GPU） | Slint 1.18.1（software） | Tauri 2.12.0（WebView2） | 预算 |
|---|---:|---:|---:|---:|
| 空闲私有内存 | **29 MB** | 10 MB | **180 MB**（含 WebView 子进程） | ≤ 80 MB |
| 画布落笔 p50 / p95 | 6.2 / **7.4–7.6 ms** | — | 14.0 / 14.5 ms | p95 ≤ 8 ms |
| 256KiB 文本首帧，未虚拟化 | 217–230 ms | — | 56–57 ms | — |
| 256KiB 文本首帧，`ListView` 按行虚拟化 | **94 ms** | — | — | — |
| 50 个元素拖动 p50 / p95 | 6.0 / **7.3–7.4 ms** | — | 13.9 / 14.5 ms | — |
| 300 步工作负载耗时（理想值 4.8 s） | — | 5.61 s | — | — |

测量方法的差异：
- Slint 的延迟从改动数据开始，到 `AfterRendering` 回调为止；
- Tauri 用两次 `requestAnimationFrame` 等待绘制完成，这是 Web 端的常规做法，但通常会比 Slint 多算约一帧。

因此两者的延迟数字不能直接相减。但内存这一项不受测量方式影响，差距是确定的。

软件渲染回退（spec §3 要求测"无 GPU 或无 GL2"的情况）：
- Slint 设置 `SLINT_BACKEND=winit-software` 后可正常启动并渲染，空闲内存 10 MB。软件渲染器不支持渲染回调，所以这一项只测了总耗时，没有逐帧延迟；
- 这条回退路径正好覆盖 rust 分支上 egui 在 Windows runner 失败的场景（缺少 GL 2.0）。

## 2. 已有证据（DOCUMENTED，来自 ShareReady Gate 03，同一版本 Slint 1.18.1）

- 中文输入法：微软拼音能提交"你好"（MEASURED / PASS）；预编辑和候选窗口未测；
- 150% DPI 下发丝线清晰；中文和等宽字体垂直居中正确；
- AccessKit 默认启用；
- 许可证：选用 Royalty-free 2.0，需在"关于"中显示 AboutSlint。

## 3. 决定

**选定 Slint 1.18.1**，渲染器默认用 femtovg，失败时自动回退到 software。

| 依据 | 说明 |
|---|---|
| 内存预算 | Tauri 的 180 MB 超出 80 MB 预算；Slint 29 MB |
| 画布延迟预算 | Slint p95 7.4–7.6 ms，满足 ≤ 8 ms；Tauri 按它自己的测量方法也接近两帧 |
| 单一语言 | UI 和 Core 都是 Rust，不需要 TS 类型化 IPC 层 |
| 回退路径 | 有内置的软件渲染器，不依赖 GPU 或 WebView |
| 风险与应对 | 大文本首帧较慢，产品中的输出预览一律用 `ListView` 按行虚拟化，满足 V1 的 256KiB 预览契约；Linux 和 macOS 的运行证据在 G5 补齐 |

许可证：Slint 使用 Royalty-free 2.0，在"关于"对话框中显示 `AboutSlint`；产品代码仍为 MIT。

## 4. 限制与未验证项

- 本机只有 Windows，Linux 和 macOS 的 Slint 运行证据为 `NOT_VERIFIED`，由 G5 的三平台 CI 补齐；
- 真实 125%/150% DPI、跨显示器 DPI、读屏器：`NOT_VERIFIED`；
- 以上都是代理自动化测量，不代表真人体验。
