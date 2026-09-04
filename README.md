# MonoOLED Studio V1.1.0 — Output Workbench Release

[![Release](https://img.shields.io/github/v/release/2023violet/MonoOLED-Studio?display_name=tag&sort=semver)](https://github.com/2023violet/MonoOLED-Studio/releases/latest)
[![Windows](https://img.shields.io/badge/Windows-x64-0078D4?logo=windows)](https://github.com/2023violet/MonoOLED-Studio/releases/tag/v1.1.0)
[![CI](https://github.com/2023violet/MonoOLED-Studio/actions/workflows/ci.yml/badge.svg)](https://github.com/2023violet/MonoOLED-Studio/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**MonoOLED Studio 是面向嵌入式开发者的单色 OLED 设计与取模工具。** 你可以在同一个 Windows 工作台中编排界面、绘制像素资源、制作字库，并将画布、选区、场景或 Font Pack 转换为可直接接入固件的数组或二进制数据。

## 下载与启动

普通用户请从 **[GitHub Releases](https://github.com/2023violet/MonoOLED-Studio/releases/tag/v1.1.0)** 下载 [`MonoOLEDStudio_v1.1.0_Windows_x64.zip`](https://github.com/2023violet/MonoOLED-Studio/releases/download/v1.1.0/MonoOLEDStudio_v1.1.0_Windows_x64.zip)。

1. 解压 ZIP，保持文件夹内的文件结构不变。
2. 双击 `MonoOLEDStudio\MonoOLEDStudio.exe`。
3. 新建或打开项目，进入 Designer、Pixel Studio 或 Font Lab 开始工作。

Windows 发布包无需安装 Python、Git 或运行 BAT 文件。可同时下载 [SHA-256 校验文件](https://github.com/2023violet/MonoOLED-Studio/releases/download/v1.1.0/MonoOLEDStudio_v1.1.0_Windows_x64.zip.sha256) 验证文件完整性：

```powershell
Get-FileHash .\MonoOLEDStudio_v1.1.0_Windows_x64.zip -Algorithm SHA256
```

当前发布包的 SHA-256：

```text
30bab895adc8107e3fc6ebb431d159c15849729a848bd9338126c147d5300188
```

## 它解决什么问题

常见 OLED 开发流程往往被拆成互不兼容的工具：一个软件排版界面，一个软件修改像素，一个软件生成字模，最后还要手工调整数组格式。MonoOLED Studio 将这些步骤放进同一个项目，并让预览、编码和保存共用同一条确定性数据路径。

典型流程如下：

`创建项目 → 编排场景/制作素材 → 配置取模规则 → 检查真实编码动画 → 复制数组或保存文件 → 接入固件`

## 核心能力

### Scene Designer：编排 OLED 界面

- 在画布中组织场景元素与 1-bit 位图资源。
- 支持选择、多选、框选、对齐、分布、复制、锁定和撤销/重做。
- 管理多个 Screen，并在切换前保护未保存修改。
- 使用统一 Renderer 进行预览、校验和导出，减少界面预览与最终数据之间的偏差。

### Pixel Studio：像素级编辑

- 左键连续绘制、右键擦除，支持插值笔迹和单手势撤销。
- 支持选区、裁剪、旋转、翻转、Fit 缩放、中键平移和锚点缩放。
- 可编辑项目资源，也可作为临时画布独立使用。
- 绘制过程中采用局部缓存更新，输出预览在后台防抖刷新。

### 取模与输出工作台：直接生成固件数据

数据来源可以是：

- 当前 Pixel Studio 画布；
- 当前选区；
- 当前 Designer 场景帧；
- 项目中的 Font Pack。

编码规则不依赖含义模糊的“阴码、阳码、顺向、逆向”标签，而是明确配置：

| 界面名称 | 采样方式 | 数据顺序 |
| --- | --- | --- |
| 逐行式 | 每行从左向右，每 8 点组成一个字节 | 完成一行后进入下一行 |
| 行列式 | 横向每 8 点组成一个块 | 先处理所有行的同一横向块 |
| 逐列式 | 每列从上向下，每 8 点组成一个字节 | 完成一列后进入下一列 |
| 列行式 | 垂直每 8 点组成一个页面 | 完成一页的所有列后进入下一页；适用于 SSD1306 VLSB |

每种方式都可以独立设置：

- 第一个采样点写入 `bit7` 或 `bit0`；
- 亮点编码为 `1` 或 `0`；
- 十六进制或十进制文本；
- 原始 BIN、C Header、C51、自定义前后缀和每行字节数；
- Font Pack 索引顺序以及内联或独立索引文件。

底部操作区可以直接执行“生成字模、复制数组、保存字模、清除输出”。取模动画读取生产编码器的真实采样轨迹，会显示当前 8 个采样点、位映射和字节值，不使用只供演示的另一套算法。

### Font Lab：制作可复现字库

- 从系统字体或 TTF/OTF 生成 Font Pack。
- 设置字符范围、字宽字高、Baseline、Advance、Bearing 和像素偏移。
- 支持相对于字体集合或相对于单字宽度的对齐方式。
- 支持 1×、2×、4× 抗锯齿采样，最终结果严格归一化为 1-bit。
- 字形可继续在 Pixel Studio 中逐像素修正，并与场景中的位图文本共用同一份数据。

### Automation API：让工具链可编排

可选的本地 JSON-RPC 2.0 接口允许脚本或 Code AI 客户端读取项目、编辑场景、管理输出配置、生成预览并导出位图或字体数据。当前 API 版本为 `1.3.0`，支持 revision guard、事务、异步任务和受项目根目录约束的文件写入。

接口不是云服务，不需要将项目素材上传到远端。完整契约见 [Automation API 文档](docs/AUTOMATION_API_V1.md)。

## 输出配置与项目复现

取模配置可以随项目保存，包括栅格化、遍历方式、位序、极性和文本格式。显示颜色、缩放比例、输出区字体与动画速度只属于本机显示偏好，不会改变导出字节。

对于已经是 1-bit 的 Pixel 画布、Framebuffer 和 Font Pack 字形，软件不会再次执行颜色阈值处理。彩色图片可使用亮度阈值或 RGB 联合阈值转换，并将完全透明像素固定视为熄灭。

同一份已保存的 1-bit 素材和输出配置应在不同机器上生成相同的字节及 SHA-256。项目字段和精确编码公式见[取模与输出工作台文档](docs/OUTPUT_WORKBENCH.md)。

## 功能边界

- 当前以 **Windows x64** 桌面体验和发布验证为主。
- 输出目标是单色 `1-bit` 位图，不是通用彩色图片编辑器。
- V1.1.0 不支持 GIF 导入、多帧 GIF 编辑或 GIF 导出。
- 内置取模模板是确定性编码预设；目标硬件是否匹配，仍应使用已知正确数组和实际屏幕结果验证。
- 旧版 `export.c_header`、Pixel C Header、项目 schema 和 Code AI 交接包继续保持兼容。

## 文档

| 文档 | 内容 |
| --- | --- |
| [中文使用手册](docs/USER_GUIDE_CN.md) | 首次使用、Designer、Pixel Studio、Font Lab 与导出流程 |
| [English User Guide](docs/USER_GUIDE_EN.md) | English task-oriented guide |
| [取模与输出工作台](docs/OUTPUT_WORKBENCH.md) | 四种取模公式、位序、极性、补位、索引和项目配置 |
| [Automation API](docs/AUTOMATION_API_V1.md) | JSON-RPC 2.0 方法、数据契约和可靠性约束 |
| [Scene Schema](docs/SCENE_SCHEMA.md) | 场景文件格式 |
| [Windows 构建与发布](docs/WINDOWS_BUILD.md) | 开发构建、完整 GA 和发布流程 |
| [设计系统](docs/DESIGN_SYSTEM.md) | 桌面界面设计与组件约束 |

## 从源码运行

需要 Python 和 Windows 环境。安装运行时依赖后启动 Qt 主程序：

```powershell
python -m pip install -r requirements.txt
python src/gui.py
```

运行开发验证：

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
python VERIFY_PACKAGE.py
```

Windows 快速开发构建：

```bat
tools\BUILD_WINDOWS_QUICK.bat
```

完整 Windows GA 构建会执行源码回归、Real-Qt 多 DPI 测试、启动/布局/设置/字体/交互/soak 检查，并生成 ZIP 与 SHA-256：

```bat
tools\BUILD_WINDOWS_GA.bat
```

## 仓库结构

| 路径 | 用途 |
| --- | --- |
| `src/` | 应用程序、编辑器、编码器、渲染器和 Automation API |
| `tests/` | 核心、Qt、兼容性与发布工程回归测试 |
| `tools/` | Windows 构建、发布和交付验证工具 |
| `test_assets/` | 测试夹具及冻结的回归资源 |
| `docs/` | 用户、格式、API、设计和构建文档 |
| `.github/` | CI 与 GitHub Release 工作流 |

仓库根目录不存放可能过期的 EXE。面向用户的 Windows 二进制文件统一发布在 [GitHub Releases](https://github.com/2023violet/MonoOLED-Studio/releases)。

## 参与项目

- 提交代码前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。
- 安全问题请按照 [SECURITY.md](SECURITY.md) 私下报告，不要先公开 Issue。
- 版本变化记录见 [CHANGELOG.md](CHANGELOG.md)。

## License

MonoOLED Studio 使用 [MIT License](LICENSE)。
