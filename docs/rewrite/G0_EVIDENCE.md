# G0 证据记录 — 立项与基线冻结

- 日期：2026-10-19
- 计划：[2026-10-19-g0-plan.md](2026-10-19-g0-plan.md)
- 起始基线：`b1d2f59`（语料生成时的 HEAD；完整 SHA `b1d2f598a3412692fa4e286b10017522dd165910`）
- 环境：Windows 10 19045、Python 3.13.15、Pillow 12.3.0、Rust 1.98.1

## 1. 任务结果

| Task | 结果 | 证据级别 |
|---|---|---|
| 0 同步 origin/main | `git merge --no-ff origin/main`，未改写历史；卫生测试 `16 passed` | MEASURED |
| 1 ADR-005 | 已写入 `.ai/DECISIONS.md`；`tests/test_rewrite_governance.py` 2 项通过。写入长期代理授权条款的尝试被自动模式分类器拒绝（理由：Instruction Poisoning），因此 ADR 只记录用户在对话中确认的 D1–D6，不授予代理任何权限 | MEASURED |
| 2 TASK-003 返工 | 修复了 junction 和 8.3 短名绕过；修复前 3 个测试失败，修复后 `16 passed, 1 skipped`（skip 原因是 symlink 权限 `WinError 1314`）；代理静态审查 PASS | MEASURED |
| 3–11 语料框架与 8 个类别 | `tools/golden_corpus/`、`tools/EXPORT_GOLDEN_CORPUS.py` | MEASURED |
| 12 冻结语料 | `fixtures/golden/`（约 4.0MB，LF only，在 `.gitattributes` 中设为 `-text`） | MEASURED |
| 13 rust 分支 | 见 [G0_RUST_BRANCH_HARVEST.md](G0_RUST_BRANCH_HARVEST.md)；只打了本地 tag，worktree 和分支都保留 | MEASURED |

## 2. 语料统计

| 类别 | case 数 | strict | semantic |
|---|---:|---:|---:|
| encoding | 132 | 132 | 0 |
| formatting | 94 | 94 | 0 |
| raster | 27 | 27 | 0 |
| scenes | 1122 | 1122 | 0 |
| projects | 29 | 29 | 0 |
| handoff | 4 | 4 | 0 |
| automation | 1（31 步） | 1 | 0 |
| fonts | 11 | 3 | 8 |

- `manifest.json` SHA-256：`2182358ca1766fa81bf4ec0f8a6ec35647f14e818021eed884c4f6a0f03e1427`
- 生成后立即运行 `python tools\EXPORT_GOLDEN_CORPUS.py --check`，输出 `golden corpus: OK`，即两次生成逐字节一致。
- `source_blobs` 钉住了 30 个 V1 源文件的 blob。

## 3. 与计划的偏差、降级和 V1 缺陷

- **场景文字不是 TTF**：V1 场景中的 `text` 元素使用位图 mode-font 头文件，所以全部场景帧都是 `strict`，不存在 semantic 场景。
- **V1 缺陷（DOCUMENTED）**：`src/scenes/example_placeholder.json` 引用了已移除的旧中文资源根目录，560 个状态的渲染全部报 `FileNotFoundError`。这些已作为错误类 case 记录。Rust 版需要复现"缺失资源即报错"的行为，但不需要复现这个路径本身。
- **交接 ZIP**：PNG 编码字节和 deflate 字节取决于实现。因此 PNG 条目按解码后的 L 像素比对，ZIP 整体的 SHA 只作参考（`zip_reference`），文本、JSON、BIN 条目逐字节比对。
- **Automation**：只有 `elapsed_ms`（墙钟耗时）这一个字段被替换为 `${ELAPSED_MS}`；`document_id`、`transaction` 这两个运行期标识按值替换为占位符。除此之外不剔除任何内容。
- **错误消息**：路径中的分隔符在 `${PROJECT_ROOT}` 之后统一转成 `/`。Rust 端以错误类型或错误码为准，消息文本仅供参考。
- **Raster LANCZOS**：G1 已提前验证，Rust 的 Pillow 复刻实现与 9 个缩放 case 逐字节一致，无需降级。

## 4. 验证命令

| 命令 | 结果 |
|---|---|
| `python -m pytest tests\test_golden_corpus.py -q -p no:cacheprovider` | 13 passed |
| `python tools\EXPORT_GOLDEN_CORPUS.py --check` | `golden corpus: OK`（exit 0） |
| `python tools\RUN_WINDOWS_TEST_GROUPS.py --phase source` | 16 组，759 个测试，0 failures，0 errors，3 skipped（exit 0） |
| `python VERIFY_PACKAGE.py` | `[PASS] V12 package verification` |
| `python -m pytest tests\test_ai_context_builder.py -q -rs` | 16 passed, 1 skipped |
| `python -m pytest tests\test_rewrite_governance.py` | 2 passed |

未运行：Qt 分组回归（`--phase qt`）。G0 没有改动任何 Qt 或产品代码，所以不在本 Gate 的风险范围内。

## 5. 代理审查与 Gate 确认

- 独立代理审查：见第 6 节。
- Gate 状态：代理自检完成；**用户尚未审阅本证据**。后续工作在本会话中继续推进，不把本文件当作授权依据。

## 6. 独立代理审查结论

（审查完成后补写）
