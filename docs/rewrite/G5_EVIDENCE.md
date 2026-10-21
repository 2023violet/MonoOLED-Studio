# G5 证据记录 — 三平台发布候选

- 日期：2026-10-20
- 版本：`2.0.0-rc.1`
- 提交：`63a788a`（打包与工作流）、`a23d3fe`（最小窗口布局、Linux 中文字体）、`7f410af`（去掉布局绑定循环）；V1 基线工具 `618a556`
- CI：`7f410af` 上 workflow `Package (Rust V2)` run `39533899180`、`Rust` run `39533899193`、`CI`（V1）run `39533899232` 全部通过（MEASURED）
- Gate 状态：**代理自检完成；用户尚未审阅。** 按 spec §3，G5 由用户确认；本记录不发布任何 Release，产物只存在于 CI 运行的 artifacts 中。

## 1. 产物

| 平台 | 产物 | 大小 | SHA-256 | 构建方式 |
|---|---|---:|---|---|
| Windows x64 | `MonoOLED-Studio-2.0.0-rc.1-windows-x64.zip` | 11.1 MB | `c479b98e27ea75435a8b675802a49438808ded81809f5ad2477412a6f36d2d6e` | zip；静态 CRT（无需 VC++ 运行库）；exe 内嵌图标与版本资源 |
| macOS arm64 | `MonoOLED-Studio-2.0.0-rc.1-macos-arm64.dmg` | 11.4 MB | `1e1eaaa030127d8c23c89c169a1f3098be3954f0dcbfe7145cade05d90aff692` | 未签名 `.app` + `hdiutil` dmg |
| Linux amd64 | `monooled-studio_2.0.0~rc.1_amd64.deb` | 11.0 MB | `050614ad7219982d4a01ab0cfee4fd5c29ce1cf3984d3a66bec499c9ed5c52b0` | `dpkg-deb`；CLI 安装为 `monooled-cli`（`/usr/bin/mono` 属于 Mono 运行时） |

打包脚本：`tools/PACKAGE_RUST_RELEASE.py`（只用各平台自带工具，不下载任何东西）。工作流：`.github/workflows/package.yml`。

## 2. 安装实测

| 平台 | 安装方式 | 已验证 | 证据级别 |
|---|---|---|---|
| Windows（CI windows-latest） | 解压 zip | 两个可执行文件 `--version` / `version`；已安装的 CLI 校验并导出 `curing_lite`；已安装的桌面程序在软件渲染器下打开项目并截图（1440×900，`g5/installed-Windows.png`） | MEASURED（CI） |
| Windows（本机 Windows 10 19045） | 解压到新目录 | 同上，截图与 CI 一致；导入表不含 `vcruntime140.dll` / `api-ms-win-crt-*` | MEASURED |
| Linux（CI ubuntu-latest） | `apt-get install ./*.deb` | `dpkg -s` 为 installed；apt 自动安装字体依赖 `fonts-noto-cjk`；`monooled-studio --version`、`monooled-cli version`；CLI 导出；桌面程序在 Xvfb + 软件渲染器下截图，中文正常显示（`g5/installed-Linux.png`） | MEASURED（CI） |
| macOS（CI macos-latest，arm64） | 挂载 dmg，复制 `.app` | 两个可执行文件版本号；CLI 导出；桌面程序截图（运行器显示器限制为 1100×700，`g5/installed-macOS.png`） | MEASURED（CI） |

做不到或未做的：

- 在真人使用的 macOS / Linux 桌面上安装并操作：`NOT_VERIFIED`。CI 运行器不等于用户环境。
- macOS 未签名、未公证：首次打开会被 Gatekeeper 拦截，需要右键 → 打开。这是 spec 允许的范围（"dmg，未签名"）。
- Intel Mac（x86_64）与 Linux arm64 包：未构建，`NOT_VERIFIED`。
- Windows 安装程序（MSI/NSIS）：spec 允许"安装包或 zip"，本 Gate 只提供 zip。
- 卸载流程：Linux `apt remove` 与 macOS 拖入废纸篓未测，`NOT_VERIFIED`。

## 3. 本 Gate 发现并修复的问题（来自 CI 截图）

1. **Linux 没有中文字体时界面中文全部空白**（第一次 CI 截图）。修复：`.deb` 依赖 `fonts-noto-cjk | fonts-wqy-microhei | fonts-wqy-zenhei`；第二次 CI 截图中文正常。
2. **最小窗口 1100×700 时 Designer 右侧检查器被截断**（macOS CI 截图）。修复：侧栏宽度随窗口变化；画布标题区改为两行；长标签与按钮可省略显示。本机用新增的 `--window-size 1100x700` 复现并验证，中英文均不溢出。
3. Windows 发布版原本依赖 `vcruntime140.dll`：改为静态 CRT。

## 4. 与 V1 的性能对比（MEASURED，本机 Windows 10，同一工作负载）

工具：V2 `mono bench`、`tools/RUN_DESKTOP_BENCH.py`；V1 `tools/MEASURE_V1_BASELINE.py`（V1 代码原样导入，用 `.venv-build` 中的 PySide6 6.11.2）。均为 3 次运行。

| 指标 | V1（Python + PySide6） | V2（Rust + Slint） | 倍数 |
|---|---:|---:|---:|
| 256×128 取模 + 格式化 p95 | 33.2 – 34.8 ms | 1.4 – 1.6 ms | 约 22× |
| 50 屏固件数据导出 | 503 – 507 ms | 312 – 326 ms | 约 1.6× |
| 50 屏完整证据包导出 | 2625 – 2669 ms | 1268 – 1383 ms | 约 2× |
| 冷启动（启动 → 首帧） | 1980 – 2236 ms | 872 – 985 ms（另有超过 1 s 的运行） | 约 2.2× |
| 空闲私有内存 | 75.9 – 76.2 MB | 67.8 – 68.9 MB | 约 0.9× |
| Pixel 笔画 → 画面 p95 | 约 15 ms（spec 记录的 V1 参考值，DOCUMENTED） | 20.4 – 21.7 ms（含合成器等待；应用工作约 5–6 ms） | 不可直接比较 |
| 主题切换 p95 | 约 46 ms（spec 记录的 V1 参考值，DOCUMENTED） | 17.3 – 19.9 ms | 约 2.4× |

说明：

- V1 的笔画与主题切换没有可复用的测量钩子，这两行使用 spec 中已记录的 V1 参考值，测法与 V2 不同，不做严格比较。
- 两个版本的导出都按同一可靠性契约逐文件 fsync，完整证据包导出在两边都受磁盘同步速度限制。
- V2 仍未达标的预算（笔画延迟、完整证据包导出、冷启动、长任务阻塞 UI 线程）见 `G4_EVIDENCE.md` §4，需要用户决定。

## 5. 独立代理审查

（待补记。）

## 6. 用户确认

（待用户审阅。G6 的 push、打 tag、发布与删除 V1 都需要用户逐次明确确认。）
