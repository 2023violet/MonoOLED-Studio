# MonoOLED Studio 1.1.0 中文使用手册

MonoOLED Studio 是面向 Windows 的通用 1-bit OLED 场景、像素资源和 FontPack 字模工作台。默认项目保持通用，不把具体产品内容混入发布基线。

## 首次使用

1. 发布包中双击 `MonoOLEDStudio.exe`；开发时可运行 `python src/gui.py`。
2. 打开或新建项目，在项目导航中选择场景。
3. 使用 `Ctrl+S` 保存；当前文档 Tab 决定保存、撤销和重做作用的编辑器。

主窗口把 Scene Designer、Pixel Studio 和 Font Lab 放在同一个 Tab 工作区中。同一资源再次打开时会复用已有 Tab。

## Scene Designer

单击元素进行选择；`Ctrl + 左键` 追加或取消选择；在空白画布拖动可框选。最后加入的元素是主选区。对齐和分布可选择以选区、主元素或画布为参考；当前选区的整体边界和间距会显示在 Inspector 中。

项目导航支持新建、复制、重命名和删除 Screen。切换 Screen 前会检查未保存修改。导出和代码交接入口位于项目操作中。

## Pixel Studio

Pixel Studio 在嵌入式 Tab 中编辑 1-bit 位图。左键拖动绘制，右键拖动擦除；支持 Fit 缩放、中键平移、九点锚定缩放、裁剪、旋转、翻转以及单步撤销/重做。导入 JPG/BMP 等非 PNG 文件后会另存为 PNG，不覆盖原文件。

右侧“取模与输出工作台”可选择当前画布、当前选区、Designer 当前帧或 FontPack，并明确设置四种取模走向、首点写入 bit7/bit0、亮点编码为 1/0、十六/十进制、自定义包装和 FontPack 索引。底部可以直接生成、复制、保存或只清除输出；“清除输出”不会清空画布。取模动画直接读取实际编码器的采样轨迹。完整公式和项目配置见 `OUTPUT_WORKBENCH.md`。

## Font Lab

FontPack 通常保存在项目的 `.oled/fonts/`。字库记录字宽字高、Baseline、Advance、字符集合和字模像素。需要时可从 TTF/OTF 批量生成字模，可选择相对于整个字体集合或相对于单字宽度的水平对齐，以及 1×/2×/4× 抗锯齿采样，再逐字检查或修正。Scene 的 `bitmap_text` 与 Font Lab 使用同一份 FontPack 真源。

## Automation API

可选的 localhost Code AI Bridge 提供语义化 JSON-RPC 2.0 接口。建议先调用 `automation.capabilities`，再读取项目和场景契约。编辑时使用 revision guard，多项 Scene 修改使用 transaction。事务提交先改变内存；需要调用 `project.save` 或 `project.save_all` 才会写入磁盘。

长任务使用 `job.start`、`job.status`、`job.result`、`job.cancel` 和 `job.release`。渲染可返回 PNG、VLSB 字节、framebuffer 哈希、解析后的几何和像素差异。完整协议见 `AUTOMATION_API_V1.md`。

## 导出与校验

可直接运行 `python src/validate.py <scene>` 校验场景，运行 `python src/exporter.py <scene> <output>` 导出场景，运行 `python src/batch_validate.py` 执行状态矩阵校验。GUI 和 Automation API 使用同一套 Renderer 与校验逻辑。

## Windows 发布

普通用户下载 `MonoOLEDStudio_v1.1.0_Windows_x64.zip`，解压后运行 `MonoOLEDStudio\MonoOLEDStudio.exe`，不需要 Python。开发者可使用 `tools\BUILD_WINDOWS_QUICK.bat`；正式发布认证使用 `tools\BUILD_WINDOWS_GA.bat` 和 Real-Qt 分组测试。

日志、自动保存、预览和资产缓存等运行时数据位于 `.oled/`，源码交付包会排除该目录。
