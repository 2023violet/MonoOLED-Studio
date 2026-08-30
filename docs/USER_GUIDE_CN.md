# MonoOLED Studio 8.0 中文使用手册

## 统一工作区

MonoOLED Studio 8.0 默认只使用一个主窗口。Designer 是第一个文档 Tab；双击或打开位图后，Pixel Workspace 会在同一窗口新增资产 Tab；Font Lab 也以 Font Tab 打开。同一个资源重复打开会复用已有 Tab。

`Ctrl+S / Ctrl+Z / Ctrl+Y` 根据当前活动 Tab 自动作用于 Scene、Pixel 或 Font 编辑器。带 `●` 的 Tab 表示存在未保存修改。

## Designer 多选、对齐与测距

- 左键单击：单选并设为 Primary Selection。
- `Ctrl + 左键`：追加/取消对象，多选中的最后加入对象成为 Primary。
- 在空白画布拖动：框选多个对象。
- 对齐参考可选择：Selection Bounds、Primary Object、Canvas。
- 多选时 Canvas/Inspector 显示整体 Bounds 与间距信息，可继续执行水平/垂直分布。

## Pixel Workspace

固定产品语义：**左键绘制，右键擦除**。快速拖动使用 Bresenham 补点，一次按下→拖动→松开只产生一个 Undo。

- Zoom 选择 `Fit`：画布随当前可用区域自动适配。
- 中键拖动：平移。
- `Space + 左键`：平移。
- Canvas Size：修改点阵画布并选择 9 点锚定方式。
- Rotate 90/180/270、Flip、Crop Selection：像素级变换。
- `Insert Bitmap Text…`：选择项目 Font Pack，把真实字模像素直接插入当前点阵，一次插入只占一个 Undo。

任意角度旋转默认不提供为无损功能，因为 1-bit OLED 必须重新栅格化，容易改变字形。

## Font Lab

项目字体位于 `.oled/fonts/`。Font Lab 管理 FontPack：字宽/字高、Baseline、Advance、字符集合和真实 Glyph PNG。可以从 TTF/OTF 文件批量生成字形，也可以打开某个 Glyph 后逐像素修正。

Designer 的 `Bitmap Text` 使用同一 FontPack 真源；保存 Font Pack 后 Scene 重新渲染，不需要 Code AI 猜测字体像素。

## 新控件体系

核心下拉选择使用 `StudioSelect + StudioPopover`，关闭和打开状态属于同一套圆角/主题系统，不再使用 Windows 原生方形 QComboBox popup。数值输入也移除了旧式原生 SpinBox 步进按钮。

## Code AI Bridge

右上角 `AI` 默认关闭。用户主动开启后，软件只在 localhost 建立带随机 Session Token 的语义 JSON-RPC Bridge。权限分为 Observe / Edit / Full。

Code AI 可以读取或操作 Scene、Selection、对齐、Pixel、Font、Render、Validation 和 History；每次返回 revision、Framebuffer SHA 等结果。Render 还可返回 PNG、VLSB、Resolved Elements 和 Pixel Diff。

AI 修改使用 revision guard；如果用户已经在 AI 读取后修改了文档，旧 revision 的 AI 写入会被拒绝。多个 Scene 修改可以放入一个 transaction，用户一次 `Ctrl+Z` 即可整体撤销。

## 实机验证边界

软件和 Code AI 可以可靠验证 128×32 布局、字模、重叠、裁剪和 framebuffer 字节，但不能替代真实 SSD1316 驱动时序、OLED 亮度/拖影、电源、总线和 MCU 刷屏验证。


---

# V8.1 交互与显示可靠性说明

## 下拉选择器

V8.1 的 `StudioSelect` 使用 MonoOLED 自有 Popup。点击条目后浮层会**先关闭**，再在下一次事件循环提交选择，因此语言、主题、密度或 UI Scale 的较重更新不会再发生在浮层仍覆盖界面的时候。全应用同时最多存在一个 Studio Popup；靠近屏幕底部时自动向上展开，靠近屏幕边缘时限制在当前 `QScreen.availableGeometry` 内。

## 语言 / 主题 / 密度 / UI Scale

设置变化现在按作用域分发。语言变化只更新翻译和布局；主题/密度/UI Scale 只更新应用视觉与编辑器 overlay；Canvas、Pixel 输入、Autosave、Performance、Shortcuts 各自只更新对应子系统。UI-only 设置不会重新运行 OLED Renderer/Clinical Validation，也不会改变 framebuffer。

嵌入式 Pixel Workspace 与 Font Lab 通过 `EditorRegistry` 接收同一 Runtime Delta，不再依赖旧的独立 Pixel Window 列表。

## System 外观

System 模式从 Qt/OS 的系统颜色方案读取，而不是从已经被 MonoOLED 主题修改过的应用 Palette 推断，因此不会因为先前选择过 Dark/Light 而“粘住”。

## UI Scale

UI Scale 会统一影响控件高度、行高、字体、图标、间距、Panel margin、Navigator 和 Inspector 基础尺寸。DPI 仍由 Windows/Qt 管理，UI Scale 是用户额外的逻辑缩放，两者不混用。

## Windows 发布验证

正式 Windows GA 需要运行 `tools\BUILD_WINDOWS_GA.bat`。V8.1 Windows Gate 覆盖 100/125/150/175/200/225/250/300% DPI，并包含 Popup、语言/主题 transition、Embedded Pixel、Font Lab、Preferences 和 UI latency 测试。当前 Linux 源码封包环境不能替代该原生 Windows 证据。

# V8.2 原生下拉交互与主题显示说明

V8.2 将下拉控件的行为固定为：**第一次点击展开，第二次点击同一个控件立即收起；点击条目先收起再提交；Esc 收起且不改值；打开另一个下拉时旧下拉必须关闭。** 这套行为由显式 Popup 状态机管理，不再只依赖 `popup.isVisible()`。

下拉内容区现在是完全不透明的主题 Surface，并按真实字体内容计算宽度；短列表（例如吸附 Off/1/2/4/8 px）不会再强制展开到 180 px。Preferences 的根、页面和滚动视口都有明确主题背景，Dark / One Dark Pro 下不应再出现右侧白色页面。

Windows 正式发布前请运行 `tools\BUILD_WINDOWS_GA.bat`。V8.2 Gate 新增真实鼠标第二次关闭、Popup Alpha/透底、条目重叠、窄列表宽度与 Dark Preferences 截图验证。

---

## V8.3 Windows 运行与诊断

V8.3 把“核心自检”和“真实 GUI 启动”明确分开：

```text
python OLED模拟器\gui.py --core-check
python OLED模拟器\gui.py --startup-smoke
```

`--core-check` 只验证依赖、项目、Renderer 与 framebuffer；`--startup-smoke` 才会真正构造 `QApplication + OLEDDesignerWindow`。

如果开发机已经安装 Python 3.13、PySide6 和 Pillow，建议先运行：

```text
tools\CREATE_RUNTIME_ENV.bat
```

它会创建 `.venv-runtime`，供根目录兼容启动器优先定位。需要看到 Python/Qt 异常和日志时运行：

```text
tools\RUN_MONOOLED_DIAGNOSTIC.bat
```

面向普通用户发布时，应使用 `tools\BUILD_WINDOWS_GA.bat` 生成经过 Real-Qt 零-skip Gate 的 PyInstaller onedir 版本，而不是要求最终用户自行配置 Python。


## V8.4.1 Code AI 完整项目设计

V8.4.1 的 Automation API 1.1 支持 Code AI 在不模拟鼠标坐标的情况下完成多 Screen 项目编排，并可通过 `state.validate_schema / state.set_schema / state.validate` 原子化建立产品状态模型。建议 Agent 首先调用 `automation.capabilities` 与 `automation.describe_method` 自发现参数，再读取 `project.get_contract`、`scene.get_schema`、`state.get_schema`、Screen/Asset/Font。

状态模型修改前应先调用 `state.validate_schema`，使用 revision guard 和 transaction；完整设计完成后，应调用 `state.enumerate`、`render.all_states` 与 `validate.all_states` 证明仅合法状态进入矩阵，再使用 `project.save_all` 与 Studio 自己的 `export.*` 完成交付。协议完整定义见 `AUTOMATION_API_V1.json` 与 `CODE_AI_AUTOMATION_API_V1.md`。


## V8.4.2 Code AI 数据安全与长任务

Automation API 1.2 将“事务提交”和“磁盘保存”明确分离。Code AI 对 Scene 完成 transaction commit 后，如果内容尚未保存，`project.get.dirty` 必须保持为 `true`。此时直接调用 `project.open_screen` 会返回 `UNSAVED_CHANGES`，不会静默丢弃当前页面。需要切换时必须显式选择 `save_current=true` 或 `discard_current=true`。

对于数千状态的 `render.all_states / validate.all_states / export.all / export.code_ai_handoff`，建议先调用 `state.count` 估算规模；只需要总体结果时使用 summary 选项；需要长时间执行时使用 `job.start`，再通过 `job.status / job.result / job.cancel` 管理进度与取消。

# V8.4.3 Windows 发布验证说明

V8.4.3 不增加 Designer/Automation 功能，重点修复 Windows 发布门禁。源码交付中的 `.bat/.cmd` 均为 CRLF；`BUILD_WINDOWS_GA.bat` 不会把所有测试塞进一个 pytest 进程，而是使用 `RUN_WINDOWS_TEST_GROUPS.py` 分组执行 Host/Core，并在 100–300% DPI 下逐个隔离运行 `test_qt_*.py`。每组/每个 Qt 模块都有 timeout、JUnit 和日志；Real-Qt 仍要求 Windows 上 `0 failed / 0 skipped`。


## V12.3 Windows 发布方式

普通用户应从 GitHub Releases 下载 `MonoOLEDStudio_v1.0.0_Windows_x64.zip`，解压后直接双击 `MonoOLEDStudio\MonoOLEDStudio.exe`。普通用户不需要 Python，也不需要运行 BAT。开发者需要快速本地生成 EXE 时使用 `tools\BUILD_WINDOWS_QUICK.bat`；正式 GA 认证由 `tools\BUILD_WINDOWS_GA.bat` 执行，并由 `v1.0.0` tag 自动触发 GitHub Release。
