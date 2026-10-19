# MonoOLED-Studio 跨平台与 Rust V2 路线评审

评审日期：2026-09-25  
评审对象：`Rust + egui/eframe`、Core / Device / App / Desktop 分层、Windows / Linux / macOS 三平台路线  
评审范围：技术可行性、产品价值、当前市场位置、框架选择、迁移顺序、发行与维护成本  
评审结论：**路线走得通；完整重写不是当前最优解，分阶段迁移才是。**

## 结论先行

这份路线解决了真正的问题：跨平台不是把一个 GUI 框架换成另一个，而是把领域数据、文件格式、设备通信、平台适配、构建、签名和测试边界分开。`Core / Device / App / Desktop` 这个方向是正确的，也比“把现有 Python/Qt 代码翻译成 Rust”可靠得多。

对于当前的 MonoOLED-Studio，我建议采用下面的技术基线：

```text
Rust stable
纯 Rust Core
egui + eframe 作为第一版 Rust Desktop UI
DeviceTransport 作为设备边界
std::thread + channel 作为第一阶段后台模型
三平台 CI 从第一个 Rust crate 开始
Python/Qt V1 继续作为行为基准和可用产品
```

这里有一个关键修正：**Rust + egui/eframe 是当前最值得做的候选方案，不是未经验证的绝对最优解。**

最稳妥的产品决策是：

1. 不立即推倒 V1；
2. 先在旁路建立 Rust Core；
3. 先迁移一个可测量的 Pixel Studio 纵向切片；
4. 在 Windows、Linux、macOS 上同时跑 CI；
5. 只有当兼容性、交互、发行和设备验证都达到门槛，才继续迁移 Font Studio、项目管理和设备面板。

如果目标是“尽快交付更多 OLED 功能”，继续维护现有 PySide6/Qt 的机会成本更低。如果目标是“把产品变成长期维护的三平台嵌入式工具”，Rust Core + egui 值得投入。两者不是同一天完成的选择，而是先用 PoC 把选择变成证据。

## 1. 评审使用的真实产品基线

当前仓库不是一个待验证的空壳，而是已经有明确行为契约的 Windows 产品：

- 版本为 `1.2.3`，当前发布重点是 Windows x64；
- 产品包含 Scene Designer、Pixel Studio、Font Lab、取模与输出工作台、Automation API；
- `src/` 当前约 88 个 Python 文件、约 15,659 行；`tests/` 当前约 157 个 Python 文件、约 11,304 行；
- 现有确定性核心已经分散在 `bitmap_encoding.py`、`framebuffer.py`、`render.py`、`project_workspace.py`、`font_pack.py` 和 Automation API 中；
- 项目 schema、输出配置、旧导出格式、Font Pack 和 VLSB 语义已有兼容性测试；
- 当前 CI 工作流以 Windows source gate 为主，尚未形成 Windows / Linux / macOS 的产品级发布矩阵；
- 本产品的价值不是普通的表单 CRUD，而是“低分辨率像素编辑 + 字库生成 + 场景预览 + 确定性固件输出 + 可选设备通信”。

这意味着重构的第一目标应该是**保留现有行为并提取边界**，而不是重新发明产品模型。当前的 `bitmap_encoding`、项目路径约束、原子写入、Renderer 和 Automation API 已经提供了很好的迁移边界。

## 2. 这份路线判断正确的地方

### 2.1 跨平台的难点不在 GUI API

路线对这一点判断准确。真正会把三个系统拉开的地方包括：

- 串口、HID、USB、CAN 的枚举和权限；
- Linux udev 规则与 Wayland/X11 依赖；
- macOS `/dev/cu.*` 与 `/dev/tty.*`、代码签名和 notarization；
- Windows 驱动、签名、安装包和 Defender 信誉；
- 文件路径、大小写、换行、字体发现和字体回退；
- 原生文件对话框、剪贴板、系统托盘、窗口恢复和高 DPI；
- 每个平台的 CI runner、缓存、产物、安装和升级验证。

所以“同一套源码、同一套领域逻辑、分别构建各平台原生发行物”是正确目标。不存在一个把 Windows `.exe` 复制到 macOS 就运行的纯 Rust 单二进制方案。

### 2.2 MonoOLED 的交互模型确实适合 immediate mode

Pixel Studio 的核心循环是：输入指针位置、计算像素坐标、修改位图、重绘局部结果。这类自定义画布是 egui 的强项。egui 官方把自己定位为纯 Rust、可运行在 native 和 web 的 immediate-mode GUI，`eframe` 是官方应用框架；native 侧可以使用 `egui-wgpu` 或其他后端。[egui 官方仓库](https://github.com/emilk/egui) 说明了这一定位，`eframe` 的平台 feature 也明确包含 Linux、Windows 和 macOS 相关支持。[eframe feature 配置](https://github.com/emilk/egui/blob/main/crates/eframe/Cargo.toml)

这能减少 Qt 中事件、Scene、View、Item、Overlay 和 repaint 之间的状态分散，但只对适合 immediate mode 的部分成立。设置页、项目树、可访问性、复杂文本输入、菜单、原生对话框、窗口布局和系统集成仍然需要明确的应用状态与平台适配。

### 2.3 Core / Device / App / Desktop 是正确的长期边界

最重要的不是 Rust 语法，而是让领域规则不依赖 GUI 和操作系统：

```text
桌面 UI / CLI / 自动化测试
          │
       App State
          │
   Domain / Project / Render
          │
      DeviceTransport
          │
  Serial / HID / USB / CAN
          │
 Windows / macOS / Linux adapter
```

Core 应能单独运行 `cargo test`，并用固定输入产生固定字节、固定 JSON 和固定预览结果。UI 只消费状态、发出命令和显示事件；UI 不直接打开串口、不直接写项目文件、不复制编码公式。

## 3. 需要修正的隐含假设

### 3.1 Rust 不会自动解决 UI 卡顿

Rust 可以降低内存安全风险、减少解释器和运行时依赖，并使后台任务的所有权边界更清楚。但 UI 卡顿通常来自错误的状态模型、主线程工作、过度重绘、锁竞争或不受控的任务生命周期。把同样的耦合代码翻译成 Rust，仍然会卡。

性能目标必须写成可测量的契约：

- 像素拖拽从输入到画面更新的 p95；
- 预览缓存重建次数；
- 字库生成在主线程占用的时间；
- 项目打开、保存、全状态导出的耗时；
- 三个平台的启动时间、内存和首帧时间。

先从当前 Python/Qt 版本采集基线，再判断 Rust 是否真的改善。不要用“Rust 更快”替代测量。

### 3.2 egui 不是 Qt 的全功能替代品

egui 非常适合自定义画布和工具型界面，但它不会自动提供 Qt 级别的桌面产品能力。重构前必须验证：

- 键盘导航和可访问性；
- 中文输入法、组合文字和字体回退；
- 原生文件对话框、剪贴板和拖放；
- 多窗口、窗口恢复、系统缩放和高 DPI；
- 菜单、快捷键、上下文菜单、托盘和通知；
- 文本测量、基线、字体加载和跨平台渲染差异；
- Linux X11 与 Wayland 的运行和打包；
- UI 自动化测试是否足以覆盖关键交互。

Pixel Studio 的画布可以先用 egui 验证，整个产品是否适合 egui 需要更多证据。

### 3.3 “固定 Cargo.lock”不是完整的供应链策略

Cargo lockfile 能固定依赖解析结果，Cargo 官方也把它描述为帮助确定性构建和避免外部依赖变化的机制。[Cargo FAQ](https://doc.rust-lang.org/cargo/faq.html) 但仍需要同时管理：

- Rust toolchain 与 MSRV；
- `cargo fmt`、`cargo clippy` 和 `cargo test --locked`；
- crate license、SBOM 和漏洞扫描；
- native system libraries；
- build script、下载器和平台 SDK；
- release artifact 的签名、哈希和可复现性。

“锁版本”是起点，不是维护计划。

### 3.4 通信库统一 API，不等于设备体验统一

`serialport` 提供跨平台高层串口 trait，并明确区分 POSIX 与 Windows 的底层实现。[serialport 文档](https://docs.rs/serialport/latest/serialport/) `hidapi` 也支持 Windows native、Linux hidraw/libusb 和 macOS 的不同后端。[hidapi 文档](https://docs.rs/hidapi/latest/hidapi/) 这证明路线可行，但不消除：

- Linux udev 权限；
- macOS 设备访问与端口命名；
- Windows 驱动和设备占用；
- VID/PID、序列号、接口号、固件版本和协议版本；
- 超时、重连、半包、取消、设备拔出和升级失败。

`DeviceTransport` 应只负责传输抽象，协议解析和设备状态机应放在独立的 `mono_device_protocol` 或类似边界中。

## 4. 当前市场位置与产品机会

跨平台本身不是足够的卖点。单色 OLED 资产转换已经有免费、低门槛工具：`image2cpp` 可以把图像和字节数组互转，并直接面向 Arduino、Adafruit 和 SparkFun 一类单色显示使用场景。[image2cpp](https://github.com/javl/image2cpp) 还有更完整的嵌入式显示设计产品，例如 Lopaka 主打屏幕布局、代码导出、字体和多种嵌入式目标。[Lopaka](https://lopaka.app/) SquareLine Studio 则围绕 LVGL 提供更通用的嵌入式 UI 设计和导出，并采用订阅定价。[SquareLine Studio](https://squareline.io/) SEGGER AppWizard 代表了更成熟、商业化、带配套转换器和支持体系的嵌入式工具路线。[SEGGER emWin/AppWizard](https://www.segger.com/products/user-interface/emwin/)

因此 MonoOLED-Studio 的竞争点应该是：

1. **确定性**：同一项目、同一配置，在不同机器输出相同字节和哈希；
2. **端到端工作流**：场景、像素、字库、编码、预览和固件输出在一个项目中闭环；
3. **低分辨率专业性**：128×32、128×64、SSD1306/SH1106 一类 1-bit 目标的像素级预览和取模语义；
4. **工程可审计性**：黄金数组、schema、导出清单、CLI 和 Automation API；
5. **离线与隐私**：设计资源不必上传云端，适合嵌入式和受限环境；
6. **设备闭环**：能够发现设备、发送资源、读取状态并保留可重放的通信日志。

“换成 Rust”是实现这些优势的手段，不是用户购买理由。“支持三个平台”是扩张条件，也不是单独的产品差异化。

### 4.1 目标用户应先分层

| 用户层 | 真正购买/采用原因 | 跨平台价值 | 需要的证据 |
| --- | --- | --- | --- |
| Arduino/个人开发者 | 快速把图片和字模变成数组 | macOS/Linux 可用，安装简单 | 30 秒完成导出、无需配置环境 |
| 嵌入式工程师 | 输出正确、可复现、可审查 | 团队机器系统不一致时有价值 | 黄金向量、schema、CLI、CI |
| 小型硬件团队 | 设计、字体、项目、设备联调一体化 | macOS/Linux 开发机接入 | 真实设备矩阵、权限诊断、更新策略 |
| 工业/医疗配套团队 | 可验证、可维护、生命周期支持 | 三平台可能是采购要求 | 追踪、审计、签名、许可证、验证文档 |

第一阶段不应该同时服务所有层。建议先服务“嵌入式工程师 + 小型硬件团队”，用确定性和设备闭环建立壁垒，再考虑工业/医疗等级要求。

## 5. 框架选择评审

| 方案 | 适合的产品形态 | 优点 | 主要风险 | 结论 |
| --- | --- | --- | --- | --- |
| 现有 PySide6/Qt | 继续交付桌面功能 | 代码、测试、交互经验都在；桌面控件和生态成熟 | Python 运行时与打包复杂，现有 CI 偏 Windows，跨平台验证尚未形成 | 继续作为 V1 行为基准和短期交付线 |
| Rust + egui/eframe | 像素编辑器、开发工具、离线工作台 | 自定义绘制自然，纯 Rust，跨平台目标清晰，Core 与 UI 容易分开 | immediate-mode 的大型应用组织、文本/IME/可访问性、API 演进、Linux 依赖 | 当前 V2 第一候选 |
| Rust + Slint | 固定流程的工业 HMI、产品化桌面 UI、未来嵌入式 | 声明式 UI，Rust 业务层，面向桌面和嵌入式 | 需要引入 DSL；GPL、Royalty-free、Commercial 三种许可路径必须提前定案 | 作为 egui PoC 失败或转向正式 HMI 时的第二候选 |
| Rust + GPUI | GPU 加速编辑器、类似 Zed 的复杂工具 | GPU、文本和编辑器经验强 | 官方仓库仍声明 pre-1.0、actively developed，版本间可能 breaking；系统依赖与生态边界更窄 | 研究候选，不作为当前基线 |
| Rust + Tauri | 管理后台、Web 风格工具、协作和云服务 | 前端生态大，Rust 后端，利用系统 WebView，包体可以较小 | HTML/CSS/JS 与 Rust 两套系统；Windows、macOS、Linux 使用不同 WebView，像素画布一致性和离线设备交互复杂 | 设备管理门户可考虑，Pixel Studio 主界面不优先 |
| Flutter + Rust FFI | 消费级视觉产品、多端统一体验 | UI 组件和视觉开发效率高 | Dart + Rust + FFI 两套运行模型；对现有纯 Rust Core 目标没有额外优势 | 当前不推荐 |

### 5.1 egui 的位置

egui 适合作为第一候选，不是因为它“最成熟”或“十年 API 不变”。官方项目仍在持续演进。它的实际优势是：Pixel Studio 的核心交互和渲染模型与 immediate mode 相符，且可以用 Rust 直接连接 Core，不需要 WebView、JavaScript bridge 或额外 FFI 层。

### 5.2 Slint 什么时候更优

如果产品以后变成固定流程、强视觉规范、需要设计师和工程师共同维护的工业 HMI，Slint 需要认真评估。Slint 官方提供 Rust、C++、JavaScript、Python 等绑定，支持桌面、移动、Web 和嵌入式；但其许可需要在 GPLv3、Royalty-free 和 Commercial 之间做明确选择，并遵守 attribution 或商业许可条件。[Slint 项目许可说明](https://github.com/slint-ui/slint) [Slint FAQ](https://github.com/slint-ui/slint/blob/master/FAQ.md)

如果未来产品进入医疗设备配套软件，框架选择还必须服从验证、追踪、变更控制和供应链要求。不能把“换成 Slint”或“换成 Rust”写成合规结论。

### 5.3 为什么不把 GPUI 作为第一选择

GPUI 已经是可获取、可运行的 Rust GUI 框架，也有 Zed 的真实产品经验。路线文本纠正“没有 crates.io 包”是有价值的。但 GPUI 官方 README 仍明确说明它处于 pre-1.0、actively developed 状态，版本之间可能有 breaking changes，并且平台后端和系统依赖需要由应用自己配置。[GPUI 官方 README](https://github.com/zed-industries/zed/blob/main/crates/gpui/README.md)

这不是“GPUI 不能用”，而是 MonoOLED-Studio 的产品收益还不足以支付框架变化、文档和生态边界的风险。

### 5.4 为什么不把 Tauri 放在 Pixel Studio 第一位

Tauri 的官方定位是用系统 WebView 承载 HTML/CSS/JavaScript 前端，并由 Rust 提供后端能力；它的优势是包体小和前端生态大。[Tauri 官方介绍](https://v2.tauri.app/start/) 但不同系统的 WebView、字体、输入法和渲染行为仍有差异。它适合设置中心、设备管理门户、项目浏览器或以后云端协作界面，不适合在第一版重写 Pixel Studio 的像素编辑主画布。

## 6. 推荐的 Rust V2 架构

原路线的四层方向正确，但应把文件格式、协议和平台服务再拆清楚：

```text
mono_core
  Bitmap / FrameBuffer / Glyph / Scene model
  Encoding / Rendering / Validation pure logic

mono_project
  JSON schema / migrations / project IO / atomic save

mono_device
  DeviceTransport / protocol state machine / discovery model
  Serial / HID / USB / CAN adapters

mono_app
  Commands / events / reducer-like AppState
  Undo-Redo / jobs / cancellation / device session state

mono_desktop
  egui / eframe views
  native dialogs / clipboard / tray / OS integration

mono_cli
  batch conversion / golden fixtures / CI and automation entrypoint
```

关键规则：

- `mono_core` 不依赖 egui、eframe、PySide、Windows、macOS 或 Linux；
- `mono_core` 不直接读写文件；文件行为属于 `mono_project`；
- UI 只能发命令、消费状态和显示事件；
- 设备协议不能散落在 UI callback 里；
- OS-specific `cfg` 只出现在 adapter 和少量启动/发行代码中；
- Python V1 与 Rust V2 在迁移期间都必须复用同一批 golden fixtures；
- CLI 与 GUI 使用同一个 Core，避免重新出现“预览一套逻辑、导出另一套逻辑”。

不要把 `mono_core` 做成新的大杂烩。位图、字体、场景、项目 IO、设备协议和 UI 状态应有明确依赖方向。

## 7. 设备通信与并发建议

第一阶段不引入 Tokio 是合理的。当前产品主要是本地桌面工具，串口和字体生成都可以使用 blocking API 加后台线程。推荐：

```text
egui main thread
        │ Command
        ▼
bounded worker channel
        │
  std::thread worker
        ├─ serial / HID operation
        ├─ font generation
        └─ file processing
        │ Event / Progress / Error / Cancelled
        ▼
egui main thread
```

但要从第一天写清楚：

- 命令是否可取消；
- 设备拔出后 worker 如何退出；
- channel 是否有界；
- 任务是否允许并发；
- 进度事件是否丢弃或合并；
- 关闭窗口时如何 join 或取消 worker；
- 同一个设备会话能否被多个命令同时使用。

当产品需要 TCP、WebSocket、多设备并发、OTA 或云端服务时，再为具体模块引入 Tokio。不要为了“Rust 项目看起来完整”而全局异步化。

## 8. 三平台 CI 与发行策略

“第一周就有三平台 CI”是这份路线中最值得保留的要求，但 CI 应分层：

### Pull Request 阶段

- Windows x64；
- Linux x64，至少覆盖 X11 和 Wayland 依赖安装；
- macOS，覆盖 Apple Silicon，必要时保留 Intel 构建；
- `cargo fmt --check`；
- `cargo clippy --all-targets --all-features -- -D warnings`；
- `cargo test --locked`；
- Core golden tests；
- CLI smoke；
- 无硬件的 MockTransport 测试；
- 生成并检查三平台 artifact 的文件清单。

### Nightly 或受控硬件阶段

- 真实串口、HID 设备矩阵；
- 设备拔出、重连、权限错误和固件版本不匹配；
- 真实 OLED 屏幕上的已知正确数组；
- 安装、卸载、升级和回滚。

### Release 阶段

- Windows 签名和安装包验证；
- macOS Developer ID 签名与 notarization；
- Linux AppImage/deb 的依赖和 udev 说明；
- 每个 artifact 的 SHA-256、构建提交和版本元数据。

Microsoft 的 Windows 应用文档区分 MSIX、Store 重签名和普通 Win32 EXE/MSI 的签名责任。[Windows code signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options) Apple 也要求分发的 Developer ID 软件完成 notarization，Gatekeeper 会使用 notarization ticket 判断软件状态。[Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)

因此，三平台 CI 不能只代表“编译通过”，而应覆盖安装、运行、权限和交付。

## 9. 迁移顺序

### 阶段 0：冻结行为基准

先不写 Rust UI，建立以下 golden evidence：

- 既有 `bitmap_encoding` 输入到输出字节；
- VLSB、位序、极性、补位和文本格式；
- Project schema 与旧项目 round-trip；
- Font Pack manifest、metrics、glyph pixels；
- Scene render 与 state matrix；
- Automation API 关键响应和错误；
- 代表性截图和性能基线；
- 已知 Windows 设备通信日志。

阶段 0 的退出条件是：任何 Rust 实现都能与 Python 参考输出比较，且差异有明确解释。

### 阶段 1：Rust Core

优先迁移：

1. `MonoBitmap` / `FrameBuffer`；
2. 编码 profile、遍历、位序、极性和 trace；
3. project schema 读写与路径约束；
4. Font Pack manifest、glyph metrics 和 1-bit 数据；
5. CLI golden runner。

这一阶段不引入 egui、不接真实设备、不改 V1 行为。

### 阶段 2：最小 egui 纵向切片

只做一个 Pixel Studio：

- 固定画布尺寸；
- 铅笔和橡皮；
- 缩放和网格；
- 一个撤销/重做链；
- 使用 Rust Core 生成预览和输出；
- Windows、Linux、macOS CI 同时运行。

退出条件不是“窗口能打开”，而是交互、golden output、缩放、输入法/键盘和三平台窗口运行都达到预定门槛。

### 阶段 3：Font Studio 与项目管理

在 Core 通过后再迁移 Font Lab、项目打开/保存、Screen 管理和输出工作台。重点验证字体回退、中文字符、baseline、advance、字形尺寸和旧 Font Pack 兼容。

### 阶段 4：Device 面板

先做 MockTransport 和协议状态机，再做 Serial/HID 后端，最后接真实硬件。设备面板不能成为 UI 直接控制 OS 句柄的地方。

### 阶段 5：并行 Beta 与发行

Rust V2 与 Python/Qt V1 并行一段时间，使用同一批项目和 golden fixtures。只有 V2 能打开真实项目、产生相同输出、通过三平台安装和设备 smoke，才考虑宣布 V1 退役。

## 10. 迁移验收门槛

在正式扩大 Rust 投入前，应满足以下门槛：

| 领域 | 必须证明的结果 |
| --- | --- |
| 兼容性 | 既有 golden vectors 全部通过；差异逐项有说明 |
| 项目 | 现有项目能打开、保存、再次打开；schema 和路径约束不退化 |
| 导出 | Python 与 Rust 生成的字节、文本和索引一致 |
| 字体 | 代表性 TTF/OTF、中文字符和 metrics 与基准一致 |
| 交互 | Pixel Studio 拖拽、缩放、撤销/重做在目标机器上达到基线 |
| 并发 | 长任务不阻塞 UI，可取消、可报告错误、可安全关闭 |
| 设备 | Mock 全覆盖，真实设备至少有 Windows 验证和一个 POSIX 验证 |
| 三平台 | CI、启动、文件对话框、字体加载和输出 smoke 均通过 |
| 发行 | Windows 签名、macOS notarization、Linux 安装说明和 artifact 哈希可复核 |
| 维护 | 能在不修改 UI 的情况下替换设备后端或导出格式 |

如果 Core 通过但 egui 在中文输入、可访问性、原生文件流或复杂布局上失败，应重新比较 Slint 和 Qt，而不是继续用更多临时适配代码掩盖问题。

## 11. 主要风险

| 风险 | 影响 | 处理方式 |
| --- | --- | --- |
| 迁移范围失控 | V1 功能停滞，V2 长期不可用 | 先 Core 和单一 Pixel slice，设阶段退出条件 |
| 行为差异 | 用户生成的固件字节改变 | golden vectors、旧项目 round-trip、双实现对照 |
| 字体差异 | 字形布局和中文显示变化 | 固定字体夹具、metrics fixtures、平台字体矩阵 |
| egui 桌面能力不足 | 设置、输入法、可访问性返工 | 早期做真实交互 PoC，必要时转 Slint/Qt |
| GPUI API 变化 | UI 维护成本上升 | 不作为第一基线，限定研究范围 |
| Linux/macOS 设备权限 | 用户无法连接硬件 | udev、端口选择、权限诊断和真实设备 CI |
| 发行合规 | 安装被系统拦截 | 早做签名、notarization、包管理和升级测试 |
| 许可证误判 | 商业发行受限 | 锁定 UI 框架与依赖许可证，建立 SBOM 和法律审查 |
| 两套产品长期并行 | 重复修复、文档分叉 | 设 V1/V2 退出条件和明确支持周期 |
| 团队 Rust 能力不足 | 交付速度下降 | 先 Core 小范围试点，统一 lint、review 和错误模型 |

## 12. 许可证与商业化判断

当前仓库是 MIT。Rust 生态中需要逐个检查依赖，尤其是 GUI、字体、图形后端、HID 和打包工具。

如果继续使用 Qt/PySide6，Qt 的开源与商业许可有明确义务和模块差异；Qt 官方强调 LGPL/GPL 条件、商业许可和二者不能混用的边界。[Qt licensing](https://www.qt.io/development/qt-framework/qt-licensing) 这不是 Rust 自动消失的问题，只是许可证组合不同。

Slint 的许可路径更需要在立项时决定：开源、Royalty-free 桌面分发和商业/嵌入式许可分别有不同条件。[Slint FAQ](https://github.com/slint-ui/slint/blob/master/FAQ.md)

建议在框架 PoC 通过后立刻生成：

- `Cargo.lock`；
- 依赖许可证清单；
- SBOM；
- Windows/macOS/Linux 发行依赖清单；
- 代码签名和密钥保管方案；
- 组件升级和 CVE 处理流程。

## 13. 最终技术与产品决策

### 推荐决策

采用**分阶段 Rust V2**：

```text
保留 Python/Qt V1 可用性
        │
        ├─ Rust mono_core + golden fixtures
        ├─ Rust mono_device + MockTransport
        ├─ Rust mono_cli
        └─ egui/eframe Pixel Studio vertical slice
                    │
                    └─ 三平台 CI / 安装 / 真实设备验证
```

第一版 Rust Desktop 选择 egui/eframe，原因是它与像素画布和定制绘制的匹配度高，且能保持 Rust Core 与 UI 在同一个语言体系内。它必须通过实际桌面能力 PoC，而不能仅凭框架介绍决定。

### 暂不推荐

- 不直接全量重写；
- 不因为 GPUI 可用就把它列为默认；
- 不把 Tokio、Actor、Repository、Service 等抽象一次性引入；
- 不把 Tauri 作为 Pixel Studio 主架构；
- 不先做漂亮 UI 再补 Core 和协议；
- 不等半年后才开始 Linux/macOS CI；
- 不把“跨平台”当成唯一市场卖点。

### 重新评估条件

以下任一情况发生时，应重新比较 egui、Slint、Qt 和 Tauri：

- 目标用户明确要求工业 HMI、设计师协作或医疗验证；
- 中文输入、字体、可访问性或原生桌面能力无法达到验收门槛；
- 商业许可、签名或供应链审查无法接受；
- 设备协议需要厂商 SDK，Rust 绑定成本明显高于 Qt/Python；
- Core 迁移不能保持现有字节和项目兼容性；
- 用户并不需要 Linux/macOS，而 Rust 重构会明显减慢功能交付。

## 最终判断

这条路线**技术上走得通**，其中“领域 Core 与 UI/设备/平台分离”“第一天建立三平台 CI”“先做 golden tests 再迁移”“第一阶段使用线程和 channel”都是值得保留的判断。

它不是“Rust + egui 一定是当前市场和产品的绝对最优解”。对 MonoOLED-Studio，当前最优解是：**以现有产品为行为基准，先做 Rust Core 和 egui Pixel Studio 的可验证纵向切片，把跨平台、设备通信、发行和用户需求同时纳入验收。**

如果这个切片通过，Rust + egui/eframe 就成为有证据支撑的 V2 基线；如果它在桌面产品能力、许可或设备发行上失败，Slint 或继续使用 Qt 都是更理性的选择。这样做能把一次不可逆的大重写，变成几个可以停止、比较和回滚的产品决策。

## 参考资料

- [egui 官方仓库与平台说明](https://github.com/emilk/egui)
- [eframe 官方 feature 配置](https://github.com/emilk/egui/blob/main/crates/eframe/Cargo.toml)
- [GPUI 官方 README](https://github.com/zed-industries/zed/blob/main/crates/gpui/README.md)
- [Slint 项目与许可说明](https://github.com/slint-ui/slint)
- [Slint FAQ 与许可条件](https://github.com/slint-ui/slint/blob/master/FAQ.md)
- [Tauri 官方架构介绍](https://v2.tauri.app/start/)
- [serialport Rust crate](https://docs.rs/serialport/latest/serialport/)
- [hidapi Rust crate](https://docs.rs/hidapi/latest/hidapi/)
- [Cargo lockfile 与跨平台说明](https://doc.rust-lang.org/cargo/faq.html)
- [Qt licensing](https://www.qt.io/development/qt-framework/qt-licensing)
- [Windows code signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)
- [Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [image2cpp](https://github.com/javl/image2cpp)
- [Lopaka embedded display design toolkit](https://lopaka.app/)
- [SquareLine Studio](https://squareline.io/)
- [SEGGER emWin/AppWizard](https://www.segger.com/products/user-interface/emwin/)
