# MonoOLED Studio Rust 重写设计（V2）

- 日期：2026-10-19
- 状态：设计已逐节确认（第 1–3 节，用户，2026-10-19）；书面 spec 待用户审阅
- 适用分支：`main`（main-only，不开长期分支）
- 取代：`rust` 分支上的 Rust ADR-001（"Validation only，Full rewrite NOT APPROVED"）。正式取代在 G0 以 `.ai/DECISIONS.md` 新增 ADR-005 生效，本文件本身不改变 `DECISIONS.md`。

## 1. 目标与已确认决定

### 1.1 用户要达成的结果

用 Rust 重写 MonoOLED Studio，使其：

1. 可以在 Windows、macOS、Linux 三个平台安装使用（出安装包，而不只是能编译）；
2. 交互流畅，不再出现"改一处就卡死"的情况；
3. 结构清晰，沿用 FirmwareSight（已发布）和 ShareReady（进行中）两个项目积累的 Rust 工作流经验。

### 1.2 已确认决定（2026-10-19）

| # | 决定 | 内容 |
|---|---|---|
| D1 | 范围 | **功能对等 + 契约兼容**：以 V1.2.3 的四个工作区为范围，能打开旧 `project.oled.json`，严格类输出与 V1 逐字节一致。UI 可以重新设计，但不新增功能。 |
| D2 | UI 框架 | **Slint vs Tauri 2 + React 实测后决定**（G2）。egui 排除：本仓库 Phase 1 在 Windows CI 上出现 `egui_glow requires opengl 2.0+` 启动失败；ShareReady 实测中 egui 的中文对齐和空闲内存（411MB）也最差。 |
| D3 | 工作流 | **阶段 Gate + 连续本地授权**（仿照 ShareReady）。 |
| D4 | V1 退役 | 达到对等后，**打 `v1-final` tag，再从 main 删除** Python 源码、测试和 PyInstaller 构建；黄金语料和兼容夹具保留。 |
| D5 | 推进方式 | **方式 A：先契约、逐步替换**。先导出黄金语料，再做无头 Core 对等，然后 UI spike，最后逐个工作区实现。 |
| D6 | 字体字节 | 已存为 1-bit 的 Font Pack、位图和项目必须**逐字节一致**；从 TTF **新生成**的字形只要求**语义等价**，不要求逐字节一致。 |

### 1.3 不做的事

- 不新增 V1.2.3 之外的产品功能，不加设备管理器、串口/HID、云同步、遥测或自动更新。
- 不在 core 中引入 async-first 设计或 Tokio。
- 代码签名、公证和许可证变更不在本设计范围内，需要另行决定。

## 2. 目标架构

### 2.1 仓库布局（main 上，与 V1 并存）

```text
MonoOLED-Studio/
├── Cargo.toml              workspace（edition 2024）
├── rust-toolchain.toml     钉到 1.98.1（与 FirmwareSight 一致）
├── deny.toml               cargo-deny：许可证、安全公告、重复依赖
├── crates/
│   ├── mono-core/          纯 Rust、同步、无 IO、无 UI
│   └── mono-project/       项目持久化与文件系统边界
├── apps/
│   ├── mono-cli/           无头导出、校验、语料对比、bench
│   └── mono-desktop/       G2 选定的 Slint 或 Tauri 外壳
├── fixtures/golden/        从 V1 导出的冻结语料（V1 删除后仍保留）
├── spike/                  G2 可丢弃 spike 代码（标注 throwaway）
├── docs/rewrite/           本设计和各 Gate 证据记录
└── src/ tests/ tools/      Python V1：重写期间只修 bug，G6 打 tag 后删除
```

只有当依赖或复用确实需要时才拆出新 crate，候选为 `mono-font`（TTF 栅格化依赖）和 `mono-automation`（JSON-RPC 1.3.0）。不预先建满 crate。

### 2.2 职责边界

| 单元 | 职责 | 依赖 |
|---|---|---|
| `mono-core` | FrameBuffer、MonoBitmap、编码（`bit_axis`、`group_order`、`msb_first/lsb_first`、`one_is_lit/zero_is_lit`、补位）、`trace_step()`、Raster/Encoding/Text 输出配置、格式化、Scene 模型与生产 Renderer、PixelDocument 与撤销历史、Font Pack 模型 | 仅 `serde` |
| `mono-project` | `project.oled.json`（schema 1、`output_workbench.schema = 1`）读写与校验、原子写入、项目根内路径约束、外部修改指纹、Windows 大小写冲突检测、资源库、图片解码、Code AI 交接 ZIP | core + 第 6 节允许的依赖 |
| `mono-cli` | 导出、校验、语料对比（`mono-cli golden`）、性能计时（`mono-cli bench`） | core、project |
| `mono-desktop` | 只做 UI：输入、视图、主题、多语言、任务调度。**不重新实现任何取模、渲染或校验逻辑** | core、project、选定的框架 |

GUI、CLI、Automation API 和导出全部复用同一个生产 Renderer 和同一条取模路径：

`画布/选区/场景帧/Font Pack → MonoBitmap → EncodingProfile → EncodedOutput → TextFormatProfile → 预览或文件`

### 2.3 数据流与线程模型

```text
UI 事件 → Command（core，同步、只做很小的改动）→ 文档变更 + 脏区域
        → UI 只重绘缓存图像的脏区域
重活（取模、格式化、栅格化、字体生成、全部导出）
        → 任务队列 worker 线程（std::thread + channel）
        → 每个任务带 generation ID，只保留最新的；旧结果直接丢弃
        → 结果投递回 UI 线程，UI 永不等待
保存   → mono-project：比对外部修改指纹 → 临时文件 + fsync → 原子替换
```

规则：

- **UI 线程永远不执行取模、栅格化、字体生成或全部导出。**
- 任务句柄由 UI 状态持有，任务的生命周期由所有权决定。这样可以从结构上杜绝 V1 中"排队的完成信号被丢弃，导致 `_running` 永久卡住"那类缺陷。
- 连续手势只产生一步撤销；撤销快照按位压缩，总预算 64MB，自适应步数上限。
- Pixel 鼠标移动热路径不得重算完整编码，也不得重建整张文档图像。

### 2.4 必须保留的 V1 契约

以 `docs/AI_HANDOFF.md` 第 6 节和 `docs/OUTPUT_WORKBENCH.md` 为准，至少包括：

- 顶层 `schema_version = 1`；输出配置 ID 只能使用小写 ASCII、数字、`_`、`-`，最长 64 字符；
- 打开缺少输出配置的旧项目时，不得仅为补默认值而改写文件；首次真实修改时才持久化；
- 配置保存失败时恢复上一份有效的内存状态；
- 已经是 1-bit 的数据不再阈值化；`invert_source` 属于栅格化，`polarity` 属于编码，两者不合并；
- 显示颜色、网格、缩放和输出字体不进入编码结果；
- 文本模板只替换允许的占位符，不执行代码；
- 预览最多显示 256KiB，保存写完整结果；
- Font Pack sidecar 索引的 offset 和长度与真实数据切片一致；
- 旧 `export.c_header`、Legacy Pixel C Header、Code AI 交接包、SSD1306 VLSB 默认语义、Automation API 1.3.0 既有方法。

四种传统模式到字段的映射保持不变：

| UI 名称 | `bit_axis` | `group_order` |
| --- | --- | --- |
| 逐行式 | `horizontal` | `row_major` |
| 行列式 | `horizontal` | `column_major` |
| 逐列式 | `vertical` | `column_major` |
| 列行式 | `vertical` | `row_major` |

### 2.5 错误模型

- 每个 crate 有自己的错误类型。面向用户的错误有稳定错误码（例如 `E-PROJ-003`），由 i18n 表翻译成中文或英文。
- `mono-core` 禁止 `unwrap`、`expect`、`panic`，用 clippy lint 强制执行。
- 任何文件写入失败都不能留下半个文件，也不能改变原文件。
- 路径相关错误只报告项目相对路径，不在用户可见消息中暴露绝对路径。

## 3. Gate 划分与验收

每个 Gate 都**由用户确认**，确认记录写在该 Gate 证据文件的末尾。代理不得自行确认 Gate。

G1、G2、G4 的每个子 Gate、G5 结束时，各由一个独立子代理审查一次，并标注为"代理审查"，不得冒充真人审查。

| Gate | 内容 | 验收 |
|---|---|---|
| **G0 立项与基线冻结** | ① `.ai/DECISIONS.md` 新增 ADR-005「Rust 全量重写，main-only」，取代 Rust ADR-001；写入连续本地授权条款 ② V1 冻结功能，只修 bug ③ 新增 `tools/EXPORT_GOLDEN_CORPUS.py`，从 V1 导出语料到 `fixtures/golden/`，带 manifest 和 SHA-256 ④ 吸收 `rust` 分支的 goldens 思路；经用户确认后打归档 tag 并删除该分支 ⑤ 收尾 TASK-003：修复 `--output` 经 Windows junction 写入 `.git` 或仓库外的问题，补 junction 回归测试，再走独立 Review | 语料连续生成两次 SHA 完全相同；覆盖清单（第 4 节）由用户确认 |
| **G1 无头 Core 对等** | 实现 `mono-core`、`mono-project`、`mono-cli`，由 `mono-cli golden` 逐项对比语料 | 严格类语料 100% 逐字节一致；语义类（新生成字形）：字形指标完全一致，每个字形的像素差异写入报告，阈值由用户在 G1 确定；三平台 CI 全绿 |
| **G2 UI 框架 spike** | Slint vs Tauri 2 + React，用三个场景对比：① 256×128 画布在 1–32 倍缩放下手绘 ② 256KiB 取模文本预览的滚动和刷新 ③ Scene 中 50 个元素多选拖动 + 智能参考线。另测：中文输入法提交与预编辑、100%/150% DPI、空闲内存、无 GPU 或无 GL2 时的软件渲染回退、三平台 CI 出包 | 交出实测对比表，由用户选定框架；spike 代码不进入产品代码 |
| **G3 设计系统** | 把 `docs/DESIGN_SYSTEM.md` 和 ADR-004 的深色 token 迁移到选定框架（token 同时作为 Rust 常量或框架全局）；覆盖浅色/深色/高对比、中文/英文，画出关键状态的高保真图 | 用户确认，设计基线冻结并标版本号 |
| **G4a** | 应用外壳、项目打开/保存、输出工作台、Pixel Studio | 每个子 Gate：真实操作截图；相关测试通过；从桌面端导出的结果与语料一致；性能预算达标 |
| **G4b** | Scene Designer（选择、多选、框选、对齐与分布、状态与变量） | 同上 |
| **G4c** | Font Lab（含后台生成） | 同上 |
| **G4d** | 偏好设置、快捷键（闭合命令命名空间）、主题、多语言 | 同上 |
| **G4e** | Automation API 1.3.0、Code AI 交接 ZIP | 回放 V1 录制的 JSON-RPC 请求/响应，结果一致 |
| **G5 三平台发布候选** | Windows（安装包或 zip）、macOS（dmg，未签名）、Linux（AppImage 或 deb） | 能在真实系统上安装的逐项实测，做不到的标 `NOT_VERIFIED`；产出与 V1 的性能对比 |
| **G6 切换** | 给 V1 打 `v1-final` tag；从 main 删除 Python、PyInstaller 和 Python CI；发布 v2.0.0 | 用户确认；push、tag、发布逐次确认 |

出现后来才发现的问题时，退回到受影响的 Gate 修订，不在后续 Gate 中绕过。

## 4. 黄金语料（G0）

由 `tools/EXPORT_GOLDEN_CORPUS.py` 在 V1 上生成，输出到 `fixtures/golden/`。每条语料记录输入、参数、输出字节和 SHA-256，并标注类别：`strict`（逐字节一致）或 `semantic`（语义等价）。

| 类别 | 覆盖内容 | 级别 |
|---|---|---|
| 取模矩阵 | 4 种模式 × 2 种位序 × 2 种极性 × 多种尺寸，包括宽高不是 8 的倍数的情况 | strict |
| 格式化输出 | 文本/BIN、十六进制/十进制、包装字段、预览截断与完整保存、Font Pack 索引 | strict |
| 图片转 1-bit | 阈值模式、亮度、RGB 权重、反相 | strict（重采样若无法精确复刻，在 G1 降为 semantic 并记录原因） |
| 场景渲染 | 默认与示例场景在每个状态下的 FrameBuffer | strict（含 TTF 文字的元素为 semantic） |
| 项目往返 | schema 1 项目、不带 `output_workbench` 的旧项目（验证打开时不改写）、路径越界与大小写冲突拒绝 | strict |
| 旧导出 | `export.c_header`、Legacy Pixel C Header | strict |
| Code AI 交接包 | ZIP manifest 与各条目内容 | strict（时间戳等字段按 V1 既有规则处理，不做宽泛剔除） |
| Automation API | 既有方法的 JSON-RPC 请求/响应录制 | strict |
| Font Pack | 加载已有 1-bit Font Pack | strict |
| Font Pack | 从 TTF 新生成 | semantic |

不允许为了让语料通过，而宽泛地删除时间戳、路径或空白差异。

## 5. 性能预算

在 G2 和 G4 实测。未达标的不能通过 Gate，也不得放宽门槛。

| 指标 | 预算 | V1 参考值 |
|---|---|---|
| Pixel 笔画从输入到画面呈现 p95（256×128，8 倍缩放） | ≤ 8ms | 全量重建约 15ms |
| 256×128 取模 + 格式化 | ≤ 2ms | — |
| 50 个 Screen 全部导出 | ≤ 500ms | — |
| 主题切换 p95 | ≤ 50ms | 约 46ms（8 档 DPI） |
| 冷启动 | ≤ 1s | — |
| 空闲内存 | ≤ 80MB | — |
| UI 线程单次阻塞 | ≤ 16ms（debug 构建内置 watchdog，超出即报告） | — |

## 6. 测试、CI 与依赖

### 6.1 测试策略

| 层 | 方法 |
|---|---|
| Core | 单元测试 + 黄金语料测试（`cargo test` 直接读取 `fixtures/golden/`） |
| 取模 | 完整参数矩阵；另加属性测试，验证"解码后再编码结果不变" |
| 项目 | 用 `test_assets/` 中的旧项目做兼容往返；覆盖路径越界、Windows 大小写冲突、junction、symlink |
| UI | 选定框架的测试后端；每个 Gate 附真实操作截图 |
| 性能 | `mono-cli bench` 自带计时程序，不额外引入基准测试依赖 |
| API | 回放 V1 录制的 JSON-RPC 请求/响应 |

### 6.2 CI

- 新增 `.github/workflows/rust.yml`，在 Windows、macOS、Ubuntu 上运行：`cargo fmt --check`、`cargo clippy --workspace --all-targets --locked -- -D warnings`、`cargo test --workspace --locked`、语料对比。
- 单独一个 job 运行 cargo-deny。
- 打包 job 从 G5 开始加入。
- 现有 Python CI 和 `release-windows.yml` 保留到 G6，供 V1 修 bug 使用。

### 6.3 依赖基线

| 位置 | 允许 | 说明 |
|---|---|---|
| `mono-core` | `serde` | 尽量只有这一个。图片解码不进入 core，core 只接收 RGBA 缓冲区 |
| `mono-project` | `serde_json`、`sha2`、`zip`、`png`（`image` 只开最小 feature） | |
| 字体栅格化 | `fontdue`、`ab_glyph`、`swash` 三选一 | G1 时对照 V1 语义实测后再选 |
| Automation 传输 | 优先只用标准库 `TcpListener` | G4e 时根据 V1 `agent_bridge` 的实际协议决定 |
| 禁止 | core 中用 Tokio；async-first 设计；网络客户端；直接用 wgpu；遥测 | |

新增任何依赖都要写明：哪项需求需要它、为什么标准库或现有依赖不够、许可证、维护状况、对二进制体积和构建的影响。所有构建使用 `--locked`。

## 7. 工作流与证据

### 7.1 连续本地授权（G0 时写入 ADR-005 后生效）

Gate 之内，代理可以连续进行可逆的本地开发、测试和本地提交，不需要逐步确认。

以下操作仍需用户逐次明确确认：

- push、创建 PR、打远端 tag、发布；
- 删除或移动用户文件，或删除 V1 路径；
- 删除分支、改写历史、强制推送；
- 修改密钥、认证、权限或安全设置；
- 替换已冻结的黄金语料，或放宽验收标准。

### 7.2 证据规则

- 证据分级：`MEASURED`、`DOCUMENTED`、`HYPOTHESIS`、`NOT_VERIFIED`。
- 每个 Gate 在 `docs/rewrite/` 下留一份简短证据记录，包含：完整 SHA、实际运行的命令和退出码、结果、跳过项、已知限制。
- 机器结果不能代替真人测试；CI 打包成功也不等于安装后可用。
- `.ai/CURRENT_STATE.md` 只保存指向本设计和当前 Gate 的指针，不复制内容，也不保存瞬时 Git 状态。

## 8. 风险

| 风险 | 应对 |
|---|---|
| TTF 栅格化结果与 V1 的 PIL/FreeType 不一致 | 已按 D6 定为 semantic；G1 对比三个候选库，并由用户确定像素差异阈值 |
| 图片重采样无法精确复刻 | G1 实测；做不到时降为 semantic 并记录原因 |
| UI 框架在某个平台不可用（例如 egui 的 GL2 问题） | G2 必须测软件渲染回退并在三平台 CI 出包；失败的框架不进入 G3 |
| Linux WebKitGTK 差异（如果选 Tauri） | G2 场景必须在 Ubuntu 上实测 |
| Slint 许可证（如果选 Slint） | 使用 Royalty-free 2.0 时须在"关于"中显示 AboutSlint，G2 时由用户确认 |
| V1 在重写期间继续出 bug | V1 只修 bug；每次修复如果影响契约输出，必须同步更新语料，并记录在证据文件中 |
| 不能从主机证据推导硬件结论 | 与 V1 相同：黄金向量和截图都不是实际 OLED 面板验证，相关结论标 `NOT_VERIFIED` |

## 9. 下一步

1. 用户审阅本 spec。
2. 审阅通过后，编写 G0 的实施计划。
3. G0 第一步：写入 ADR-005 和连续本地授权。
