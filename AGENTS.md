# AGENTS.md — MonoOLED Studio 代理指令

## 定位

面向 Windows 的单色 OLED 设计与取模工作台（PySide6 桌面应用）：Scene Designer 编排场景、Pixel Studio 编辑 1-bit 像素、Font Lab 制作字库、输出工作台生成固件数组。

## 怎么跑

```powershell
python -m pip install -r requirements.txt
python src/gui.py
```

- 测试依赖：`requirements-dev.txt`；构建依赖：`requirements-build.txt`（Python 3.13）。
- 当前版本见 `src/VERSION`；正式发布走 tag 触发的 CI（`.github/workflows/release-windows.yml`）。

## 验证纪律（先读这个再改代码）

- 全量回归**禁止**把整个 `tests/` 塞进单个 pytest 进程（已知堆损坏）；用 `tools/RUN_WINDOWS_TEST_GROUPS.py --phase source|qt` 分组隔离运行。
- 按改动选择最小充分测试的对照表、兼容性红线、发布纪律：见 [docs/AI_HANDOFF.md](docs/AI_HANDOFF.md)（仓库的开发交接真源，优先级高于本文件的摘要）。
- 行为变更先建立失败证据；只读诊断不授权修复；推送/打标签/发布仅在用户明确要求时执行。

## 目录与约定

| 路径 | 用途 |
| --- | --- |
| `src/` | 应用、编辑器、编码器、渲染器、Automation API |
| `tests/` | 核心、Qt、兼容性与发布工程回归 |
| `tools/` | Windows 构建、发布与验证工具 |
| `docs/` | 用户手册、格式契约、API、构建文档（索引见 `docs/README.md`） |
| `test_assets/` | 冻结的测试夹具与回归资源 |

- `.oled/`、`build/`、`dist/`、`release/`、`.artifacts/`、`src/reports/` 是本地运行/构建产物，不进源码提交。
- 新增正式文档必须同步 `docs/README.md` 索引。
- 项目成员路径必须解析在项目根内；原子写入与外部修改指纹是可靠性契约，不得绕过。

## 当前状态（2026-09-12）

- `v1.2.3` 已发布：修复主题切换遗漏隐藏控件（可见同步 repolish + 隐藏零延迟补齐）。
- 已知未修复：`tools/VERIFY_THEME_SWITCH_V101.py` 门禁脚本 signature 断言腐化（不在 CI 中）；详见 `docs/AI_HANDOFF.md` 第 11 节。
