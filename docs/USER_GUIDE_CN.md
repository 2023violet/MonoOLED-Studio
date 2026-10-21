# MonoOLED Studio 2 中文使用手册

MonoOLED Studio 是通用的 1-bit OLED 场景、像素资源和 Font Pack 字库工作台，支持 Windows、macOS 和 Linux。项目文件与 1.2.3 兼容，可以直接打开旧项目。

## 安装与首次使用

1. 从 GitHub Releases 下载对应平台的安装包，安装方式见 [README](../README.md#下载与安装)。
2. 启动后用"文件 → 打开项目"（`Ctrl+Shift+O`）选择 `project.oled.json`，或用 `Ctrl+N` 新建项目。也可以在启动时把项目路径作为参数传入：`monooled-studio path/to/project`。
3. 用 `Ctrl+S` 保存。

窗口顶部的分段按钮在四个工作区之间切换：设计（Scene Designer）、Pixel Studio（`Ctrl+Shift+P`）、Font Lab（`Ctrl+Shift+F`）和评审。`Ctrl+K` 打开命令面板，可按名称搜索并执行命令。

## Scene Designer

- 单击元素即可选择，`Ctrl + 左键`追加或取消选择，在空白画布上拖动可框选。最后加入的元素是主选区。
- 对齐和分布可以选择以选区、主元素或画布为参考，Inspector 中会显示选区的整体边界和间距。
- `Ctrl+G` 编组，`Ctrl+Shift+G` 取消编组。`Ctrl+1`、`Ctrl+2` 分别显示或隐藏导航栏和 Inspector。
- 项目导航支持新建、复制、重命名和删除 Screen。
- 切换 Screen、删除 Screen、打开其他项目或关闭窗口之前，如果有未保存的修改，会询问保存、放弃还是取消。Pixel Studio 和 Font Lab 里未保存的修改也一样。
- 自动保存默认每 3 分钟一次。程序异常退出后再次打开同一个 Screen 时，会提示恢复。

## Pixel Studio

- 左键拖动绘制，右键拖动擦除。一次拖动只占一步撤销。
- 工具包括铅笔、橡皮、直线、矩形、填充和选区。选区支持复制、剪切、粘贴、裁剪；画布支持旋转、翻转、反相、调整尺寸（九点锚定）和清空。
- 滚轮缩放，"缩放"下拉框可选 Fit 或固定倍率。中键拖动或按住空格拖动可平移。
- 用方向键移动画布光标后，Enter 点亮、Delete/Backspace 熄灭、Esc 隐藏光标。
- 画布上方和左侧有像素索引标尺，可在偏好设置中关闭。
- 打开 JPG/BMP 等非 PNG 图片时，先按阈值转换为 1-bit，保存时另存为 PNG，不会覆盖原文件。

### 取模与输出工作台

Inspector 的"输出"页是取模与输出工作台。

- **数据源**：当前 Pixel 画布、当前选区、当前 Designer 场景帧、项目 Font Pack，或一张图片。只有图片来源需要阈值转换，其他来源已经是 1-bit。
- **点阵**：四种取模方式、首点写入 bit7 还是 bit0、亮点编码为 1 还是 0。
- **格式**：文本数组或 BIN、十六进制或十进制、每行字节数、Font Pack 索引方式，以及各段的前缀和后缀。
- **输出配置**：可以另存为项目配置，随项目保存。
- **显示**：画布背景、网格线、像素填充和像素边框的颜色（点色块从调色板选取，或直接输入 `#RRGGBB`），像素大小，以及输出区的字体和字号。这些设置只影响显示，不会改变导出字节。

底部的输出区可以生成字模、复制数组、保存字模或清除输出。"清除输出"不会清空画布。完整公式见 [OUTPUT_WORKBENCH.md](OUTPUT_WORKBENCH.md)。

## Font Lab

- Font Pack 通常保存在项目的 `.oled/fonts/` 目录下，记录单元宽高、Baseline、Advance、字符集合和每个字形的像素。
- 可以从 TTF/OTF 字体文件批量生成字形，也可以不指定字体、使用内置 5×7 字形。可设置字号、阈值、对齐方式和抗锯齿采样。
- 生成在后台进行，进度显示在状态栏，生成期间界面可以继续使用。
- 在字形列表中选择字符即可逐像素修改；切换字符时，已修改的字形会自动保存。
- 场景中的 `bitmap_text` 与 Font Lab 使用同一份 Font Pack 数据。

## Automation API（Code AI Bridge）

"工具 → Code AI Bridge"会在本机回环地址上开启 JSON-RPC 2.0 接口，并显示端口和会话令牌。它与正在编辑的 Designer 会话共享状态，Agent 的每批修改在界面里是一步可撤销的操作。

- 建议先调用 `automation.capabilities`，再读取项目和场景契约。
- 编辑时使用 revision 校验，多项修改使用事务。事务提交只改变内存，调用 `project.save` 或 `project.save_all` 才会写入磁盘。
- 长任务使用 `job.start`、`job.status`、`job.result`、`job.cancel` 和 `job.release`。

不打开桌面程序时，也可以用命令行运行同一个接口：`mono bridge --project <project.oled.json> --permission edit`（Linux 上命令为 `monooled-cli`）。完整协议见 [AUTOMATION_API_V1.md](AUTOMATION_API_V1.md)。

## 命令行校验与导出

```bash
mono validate --project project.oled.json
mono export --project project.oled.json --output exports/latest
mono batch-validate --project project.oled.json
mono handoff --project project.oled.json
```

桌面程序、命令行和 Automation API 使用同一个渲染器和同一套校验逻辑。

## 偏好设置与数据位置

- 偏好设置（`Ctrl+,`）包括语言、外观、界面缩放、输入方式、自动保存、性能和快捷键。偏好文件与 1.2.3 相同：Windows 在 `%LOCALAPPDATA%\MonoOLEDStudio\preferences.json`，macOS 和 Linux 在 `~/.config/monooled-studio/preferences.json`（遵循 `XDG_CONFIG_HOME`）。
- 日志、自动保存、预览和资产缓存等运行时数据位于项目的 `.oled/` 目录。
