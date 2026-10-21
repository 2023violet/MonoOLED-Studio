# G5 证据记录 — 三平台发布候选

- 日期：2026-10-20
- 版本：`2.0.0-rc.1`
- 提交：`63a788a`（打包与工作流）、`a23d3fe`（最小窗口布局、Linux 中文字体）、`7f410af`（去掉布局绑定循环）；V1 基线工具 `618a556`；第二轮审查返工 `965fffb`、`33201c9`、`e1e8a6d`
- CI：`e1e8a6d` 上 workflow `Package (Rust V2)` run `39543459575`、`Rust`、`CI`（V1）全部通过（MEASURED）。返工前的首轮记录为 `7f410af` 上的 run `39533899180`
- Gate 状态：**代理自检完成；用户尚未审阅。** 按 spec §3，G5 由用户确认；本记录不发布任何 Release，产物只存在于 CI 运行的 artifacts 中。

## 1. 产物

| 平台 | 产物 | 大小（MiB） | SHA-256 | 构建方式 |
|---|---|---:|---|---|
| Windows x64 | `MonoOLED-Studio-2.0.0-rc.1-windows-x64.zip` | 11.1 | `84373f2be2d56f42a6e45069f94dd44cb5fedc9bcc0fac167f6e6e10d0a37632` | zip；静态 CRT（无需 VC++ 运行库）；exe 内嵌图标与版本资源 |
| macOS arm64 | `MonoOLED-Studio-2.0.0-rc.1-macos-arm64.dmg` | 11.3 | `1a871e663e1ea706e5f9a47b954e4be759d228921b4df7d651228866c15d7702` | ad-hoc 签名的 `.app`（无开发者身份、未公证）+ `hdiutil` dmg |
| Linux amd64 | `monooled-studio_2.0.0~rc.1_amd64.deb` | 11.0 | `0272cc7d220ceb8faf94a11b2e61230b7228f3e32e297207b6ea94db34d490a1` | `dpkg-deb`；CLI 安装为 `monooled-cli`（`/usr/bin/mono` 属于 Mono 运行时）；`Depends: libc6 (>= 2.39), …, fonts-noto-cjk \| fonts-wqy-microhei \| fonts-wqy-zenhei` |

产物来自 CI run `39543459575`。构建不可逐字节复现：每次运行的 SHA-256 不同，以 `SHA256SUMS` 与 run 编号为准。`libc6 (>= 2.39)` 由二进制导入的 `GLIBC_x.y` 符号算出，意味着只能装在 Ubuntu 24.04 / Debian 13 及更新的发行版上；更旧的系统会在安装时被 dpkg 拒绝，而不是运行时报错。

打包脚本：`tools/PACKAGE_RUST_RELEASE.py`（只用各平台自带工具，不下载任何东西）。工作流：`.github/workflows/package.yml`。

## 2. 安装实测

| 平台 | 安装方式 | 已验证 | 证据级别 |
|---|---|---|---|
| Windows（CI windows-latest） | 解压 zip | 两个可执行文件的版本号与工作区版本精确一致；已安装的 CLI 校验并导出 `curing_lite`；已安装的桌面程序分别用软件渲染器和默认渲染器打开项目并截图（1440×900，`g5/installed-Windows.png`、`g5/installed-Windows-default-renderer.png`），截图通过内容检查 | MEASURED（CI） |
| Windows（本机 Windows 10 19045） | 解压到新目录 | 同上，截图与 CI 一致；导入表不含 `vcruntime140.dll` / `api-ms-win-crt-*` | MEASURED |
| Linux（干净的 `ubuntu:24.04` 容器） | `apt-get install ./*.deb` | 容器里没有构建用的 -dev 包，运行库全部来自包自身的 Depends；`dpkg -s` 为 installed；apt 自动安装 `fonts-noto-cjk`；版本号精确一致；CLI 校验与导出；桌面程序在 Xvfb + 软件渲染器下截图，中文正常显示（`g5/installed-Linux.png`），截图通过内容检查 | MEASURED（CI） |
| macOS（CI macos-latest，arm64） | 挂载 dmg，复制 `.app` | 版本号精确一致；`codesign --verify --deep --strict` 通过（ad-hoc）；`spctl --assess` 结果为 rejected（未公证，符合预期）；CLI 导出；桌面程序分别用软件渲染器和默认渲染器截图（运行器显示器限制为 1100×700，`g5/installed-macOS.png`、`g5/installed-macOS-default-renderer.png`），截图通过内容检查 | MEASURED（CI） |

做不到或未做的：

- 在真人使用的 macOS / Linux 桌面上安装并操作：`NOT_VERIFIED`。CI 运行器不等于用户环境。
- Linux 默认（GL）渲染器：容器内没有 GPU，只测了软件渲染器，`NOT_VERIFIED`。
- 截图内容检查只能发现空白、纯色或几乎没有文字的窗口，不能证明每个字形都正确渲染；截图保留为 artifacts 供人工查看。
- macOS 没有开发者签名，也没有公证（只有 ad-hoc 签名）：首次打开会被 Gatekeeper 拦截。macOS 15 起右键 → 打开不再能放行，需要在"系统设置 → 隐私与安全性"中点"仍要打开"，或执行 `xattr -dr com.apple.quarantine "/Applications/MonoOLED Studio.app"`。真实 Mac 上的放行流程 `NOT_VERIFIED`。这是 spec 允许的范围（"dmg，未签名"）。
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
| 冷启动（创建进程 → 首帧，两边都从启动器的 `MONO_T0` 计时） | 1980 – 2236 ms | 925 – 1002 ms（重新构建后首次启动 2069 ms） | 约 2.1× |
| 空闲私有内存 | 75.9 – 76.2 MB | 67.8 – 68.9 MB | 约 0.9× |
| Pixel 笔画 → 画面 p95 | 约 15 ms（spec 记录的 V1 参考值，DOCUMENTED） | 20.4 – 21.7 ms（含合成器等待；应用工作约 5–6 ms） | 不可直接比较 |
| 主题切换 p95 | 约 46 ms（spec 记录的 V1 参考值，DOCUMENTED） | 17.3 – 19.9 ms | 约 2.4× |

说明：

- V1 探针经 venv 启动器再启动真正的解释器，多出一次进程创建；这一偏差对 V1 不利，倍数仅供参考。
- "50 屏"是同一 Screen 导出 50 次，两边做法相同（见 `G4_EVIDENCE.md` §4 工作负载说明）。
- V1 的笔画与主题切换没有可复用的测量钩子，这两行使用 spec 中已记录的 V1 参考值，测法与 V2 不同，不做严格比较。
- 两个版本的导出都按同一可靠性契约逐文件 fsync，完整证据包导出在两边都受磁盘同步速度限制。
- V2 仍未达标的预算（笔画延迟、完整证据包导出、冷启动、长任务阻塞 UI 线程）见 `G4_EVIDENCE.md` §4，需要用户决定。

## 5. 独立代理审查

第二轮独立子代理审查（覆盖 G4 返工与 G5，只读）结论：**REWORK REQUIRED**。审查者本地运行 `cargo test --workspace`、`cargo clippy -D warnings` 与治理测试均通过，并核对了 CI 产物的 SHA-256。处理如下（提交 `965fffb`）：

| # | 级别 | 问题 | 处理 |
|---|---|---|---|
| 1 | major | Font Lab 选"放弃"后包仍是脏的，打开其他项目也不会解绑，之后切换字形会把已放弃的修改自动保存回旧项目 | 放弃时关闭脏字库；`open_project` / `open_scene_file` 清除字库；新增测试 `discarded_font_edits_are_never_written_back` |
| 2 | minor | 字形生成进行中，`FontLab::save` 不写入却返回成功，关闭窗口时选"保存"会丢失修改 | `save` 在生成期间返回错误；生成期间所有切换都会等待并提示 |
| 3 | minor | 关闭处理在 `App` 已被借用时直接关闭窗口 | 改为保留窗口 |
| 4 | major | 冷启动从 `main()` 计时，与 V1 从创建进程计时不可比 | 两边都从启动器的 `MONO_T0` 计时，重新测量（§4） |
| 5 | major | UI 线程阻塞一行标 ✅，但同节写明不达标；spec 要求的 debug watchdog 不存在 | 该行改为 ❌；实现 debug 构建 watchdog（`watchdog.rs`） |
| 6 | major | CI 可能在产物损坏时仍通过：截图只检查尺寸；Linux 在带 -dev 包的主机上安装；"Automation bridge" 步骤名不符 | 新增截图内容检查（`tools/CHECK_SMOKE_SCREENSHOT.py`，对空白图会失败）；`.deb` 改在干净的 `ubuntu:24.04` 容器里安装和冒烟；步骤改名；版本号精确匹配 |
| 7 | minor | `.deb` 的 `libc6` 没有版本下限 | 从二进制的 `GLIBC_x.y` 符号计算下限 |
| 8 | minor | CI 只启动软件渲染器 | Windows / macOS 增加默认渲染器截图；Linux 容器内没有 GPU，仍只测软件渲染器 |
| 9 | minor | Gatekeeper 说明可能过时 | 改为 NOT_VERIFIED 并写明 macOS 15 的放行方式；`.app` 加 ad-hoc 签名，CI 报告 `codesign` / `spctl` 结果 |
| 10 | minor | 基准工作负载描述不准确 | G4 §4 写明"同一 Screen 导出 50 次"与"直接调用 pointer 处理函数" |
| 11 | minor | `SHA256SUMS` 追加写入；CI 只匹配程序名；每个连接在校验令牌前可缓冲 16 MiB | 前两项已修复；第三项保留：只监听 localhost，限 32 个连接（最坏约 1 GiB）；V1 `agent_bridge.py` 既不限行长也不限连接数，V2 已更严格。记录为已知风险 |

## 6. 用户确认

（待用户审阅。G6 的 push、打 tag、发布与删除 V1 都需要用户逐次明确确认。）
