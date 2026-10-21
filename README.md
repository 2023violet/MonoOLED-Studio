# MonoOLED Studio 2

[![Release](https://img.shields.io/github/v/release/2023violet/MonoOLED-Studio?display_name=tag&sort=semver)](https://github.com/2023violet/MonoOLED-Studio/releases/latest)
[![Rust](https://github.com/2023violet/MonoOLED-Studio/actions/workflows/rust.yml/badge.svg)](https://github.com/2023violet/MonoOLED-Studio/actions/workflows/rust.yml)
[![Package](https://github.com/2023violet/MonoOLED-Studio/actions/workflows/package.yml/badge.svg)](https://github.com/2023violet/MonoOLED-Studio/actions/workflows/package.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**MonoOLED Studio 是面向嵌入式开发者的单色 OLED 设计与取模工具。** 在同一个工作台里编排界面、绘制像素资源、制作字库，再把画布、选区、场景或 Font Pack 转换成可以直接放进固件的数组或二进制数据。

2.0 用 Rust 重写，界面使用 Slint，支持 Windows、macOS 和 Linux。项目文件、偏好设置与 Automation API 1.3.0 都与 1.2.3 兼容。Python 1.x 的最后源码保存在 `v1-final` 标签。

## 下载与安装

从 **[GitHub Releases](https://github.com/2023violet/MonoOLED-Studio/releases/latest)** 下载对应平台的安装包。每个 Release 都附带 `SHA256SUMS`。

| 平台 | 安装包 | 安装方式 |
| --- | --- | --- |
| Windows x64 | `MonoOLED-Studio-<版本>-windows-x64.zip` | 解压后双击 `monooled-studio.exe`。不需要安装 VC++ 运行库。 |
| macOS（Apple Silicon / Intel） | `MonoOLED-Studio-<版本>-macos-arm64.dmg` / `-macos-x64.dmg` | 把应用拖进"应用程序"。应用没有开发者签名，首次打开会被拦截，需要在"系统设置 → 隐私与安全性"里点"仍要打开"。 |
| Linux amd64 / arm64 | `monooled-studio_<版本>_amd64.deb` / `_arm64.deb` | `sudo apt install ./monooled-studio_*.deb`。需要 Ubuntu 24.04、Debian 13 或更新的发行版，会自动安装中文字体。 |

校验下载文件：

```bash
sha256sum -c SHA256SUMS --ignore-missing
```

Windows PowerShell 中可以用 `Get-FileHash <文件> -Algorithm SHA256` 计算哈希，再与 `SHA256SUMS` 对照。

## 它解决什么问题

常见的 OLED 开发流程往往分散在几个互不兼容的工具里：一个排版界面，一个改像素，一个生成字模，最后还要手工调整数组格式。MonoOLED Studio 把这些步骤放进同一个项目，预览、校验和导出共用同一条确定性的渲染与编码路径。

`创建项目 → 编排场景/制作素材 → 配置取模规则 → 生成数组并核对预览 → 复制数组或保存文件 → 接入固件`

## 核心能力

### Scene Designer：编排 OLED 界面

- 在画布中组织场景元素和 1-bit 位图资源。
- 选择、多选、框选、对齐、分布、复制、锁定、撤销/重做。
- 管理多个 Screen，切换、删除或关闭前保护未保存的修改。
- 预览、校验和导出使用同一个渲染器。

### Pixel Studio：像素级编辑

- 左键绘制、右键擦除，支持插值笔迹，一次拖动只占一步撤销。
- 支持直线、矩形、填充、选区、裁剪、旋转、翻转、缩放、中键或空格平移，以及键盘绘制。
- 画布背景、网格线、像素填充和像素边框的颜色都可以自定义；它们只影响显示，不进入导出数据。

### 取模与输出工作台

数据来源可以是当前 Pixel 画布、当前选区、当前 Designer 场景帧、项目中的 Font Pack，或一张图片。

取模方式不用含义模糊的"阴码、阳码、顺向、逆向"，而是写明具体规则：

| 界面名称 | 采样方式 | 数据顺序 |
| --- | --- | --- |
| 逐行式 | 每行从左向右，每 8 点组成一个字节 | 完成一行后进入下一行 |
| 行列式 | 横向每 8 点组成一个块 | 先处理所有行的同一横向块 |
| 逐列式 | 每列从上向下，每 8 点组成一个字节 | 完成一列后进入下一列 |
| 列行式 | 垂直每 8 点组成一个页面 | 完成一页的所有列后进入下一页；适用于 SSD1306 VLSB |

每种方式都可以单独设置：

- 首点写入 `bit7` 或 `bit0`；
- 亮点编码为 `1` 或 `0`；
- 十六进制或十进制；
- 文本数组或原始 BIN；
- 自定义前后缀和每行字节数；
- Font Pack 索引写在数组内、写成单独文件，或不写。

精确公式见[取模与输出工作台文档](docs/OUTPUT_WORKBENCH.md)。

### Font Lab：制作可复现的字库

- 用 TTF/OTF 字体文件或内置 5×7 字形生成 Font Pack。
- 可设置字符范围、单元宽高、Baseline、Advance、阈值、对齐方式和抗锯齿采样。
- 字形可以逐像素修改，修改后与场景中的位图文本共用同一份数据。
- 生成在后台进行，不阻塞界面。

### Automation API 与 CLI

- 本地 JSON-RPC 2.0 接口（版本 `1.3.0`）供脚本或 Code AI 客户端读取项目、编辑场景、生成预览和导出数据。
- 只监听本机回环地址，每次会话使用随机令牌，素材不会上传到任何服务器。
- 支持 revision 校验、事务、异步任务，写入的文件限制在项目目录内。
- 桌面程序中通过"工具 → Code AI Bridge"开启，并与正在编辑的 Designer 会话共享状态。也可以用命令行单独运行。

完整契约见 [Automation API 文档](docs/AUTOMATION_API_V1.md)。

命令行工具（Windows/macOS 为 `mono`，Linux 安装后为 `monooled-cli`）：

```bash
mono validate --project path/to/project.oled.json
mono export --project path/to/project.oled.json --output out/
mono handoff --project path/to/project.oled.json --output handoff.zip
mono bridge --project path/to/project.oled.json --permission edit
```

## 输出的确定性

- 同一份已保存的 1-bit 素材，配合同一份输出配置，在任何平台上都生成相同的字节和 SHA-256。
- 已经是 1-bit 的画布、Framebuffer 和 Font Pack 字形不会再次阈值化。
- 彩色图片可以按亮度阈值或 RGB 联合阈值转换；完全透明的像素固定视为熄灭。

## 功能边界

- 输出目标是单色 1-bit 位图，不是通用的彩色图片编辑器。不支持 GIF。
- 内置取模模板是确定性的编码预设。它们是否匹配你的硬件，仍需要用已知正确的数组和实际屏幕来验证。
- 2.0 的已知限制（未达标的性能预算、未签名的 macOS 应用等）见 [CHANGELOG](CHANGELOG.md)。

## 文档

| 文档 | 内容 |
| --- | --- |
| [中文使用手册](docs/USER_GUIDE_CN.md) | 首次使用、Designer、Pixel Studio、Font Lab 与导出流程 |
| [English User Guide](docs/USER_GUIDE_EN.md) | English task-oriented guide |
| [取模与输出工作台](docs/OUTPUT_WORKBENCH.md) | 取模公式、位序、极性、补位、索引和项目配置 |
| [Automation API](docs/AUTOMATION_API_V1.md) | JSON-RPC 2.0 方法、数据契约和可靠性约束 |
| [Scene Schema](docs/SCENE_SCHEMA.md) | 场景文件格式 |
| [构建与发布](docs/BUILD.md) | 从源码构建、测试、打包与发布 |
| [设计系统](docs/DESIGN_SYSTEM.md) | 界面设计令牌与组件约束 |

## 从源码构建

需要 `rust-toolchain.toml` 中指定的 Rust 版本（rustup 会自动安装）。Linux 还需要以下开发包：

```bash
sudo apt install libfontconfig1-dev libxkbcommon-dev libxkbcommon-x11-dev libwayland-dev libx11-dev libxcursor-dev libxrandr-dev libxi-dev libgl1-mesa-dev libegl1-mesa-dev
```

启动桌面程序：

```bash
cargo run --release -p mono-desktop
```

运行测试（包含与 1.x 冻结黄金语料的一致性测试）：

```bash
cargo test --workspace
```

打包当前平台的安装包：

```bash
cargo build --release -p mono-desktop -p mono-cli
python tools/PACKAGE_RUST_RELEASE.py
```

详见[构建与发布](docs/BUILD.md)。

## 仓库结构

| 路径 | 用途 |
| --- | --- |
| `crates/mono-core` | 无界面核心：位图、取模、格式化、场景、渲染、Pixel 文档 |
| `crates/mono-project` | 项目持久化、原子写入、导出、资源、模板、自动保存 |
| `crates/mono-font` | TrueType 字形生成 |
| `crates/mono-automation` | Automation API 1.3.0 服务与本地 JSON-RPC 桥 |
| `apps/mono-desktop` | Slint 桌面程序 |
| `apps/mono-cli` | 命令行工具 |
| `fixtures/golden` | 由 1.x 导出的冻结黄金语料 |
| `test_assets` | 测试夹具项目和资源 |
| `tools` | 打包、截图检查、性能基准和治理脚本 |
| `docs` | 用户、格式、API、设计、构建和重写证据文档 |

## 参与项目

- 提交代码前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。
- 安全问题请按照 [SECURITY.md](SECURITY.md) 私下报告，不要公开提 Issue。
- 版本变化见 [CHANGELOG.md](CHANGELOG.md)。

## License

MonoOLED Studio 使用 [MIT License](LICENSE)。界面基于 [Slint](https://slint.dev)，按 Slint Royalty-free License 2.0 使用，"帮助 → 关于"中有相应署名。
