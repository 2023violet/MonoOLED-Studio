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

### 第一轮（代理审查，静态，2026-10-19）：`REWORK REQUIRED`

阻断项：
1. Automation 只覆盖约 25% 的方法，且只有一个 case；
2. 请求里记录的是带宏的模板（`$doc`、`$builtin:`），而且把确定性的 ID（`pixel:<path>`、`tx-<n>`）替换成了占位符；
3. 场景没有覆盖 placeholder、bitmap_text 和错误分支，同时 `except (OSError, ValueError)` 范围过宽；
4. 项目加载时的拒绝路径和保存失败回滚都没有 case。

重要项：
5. `--check` 按解析后的值比较，会被 Python 等值掩盖类型差异；不校验文件字节；不报告多余文件；把 Python/Pillow 版本当作漂移；
6. `replace_root` 会改写整个字符串中的反斜杠；
7. 格式化缺少自定义模板和拒绝用例；
8. 缺少加载已有 Font Pack 的 case。

次要项：
9. 预览 case 的输入只写了 Python 表达式；
10. 证据中的若干表述不准确；V1 删除后语料输入会缺失。

### 返工（全部处理）

| # | 处理 |
|---|---|
| 1、2 | `automation` 改为 18 个独立 case（16 个会话 + observe 权限会话 + 2 个原始请求），覆盖 `METHOD_SPECS` 中的**全部方法**，并在构建时强制检查覆盖。请求按实际发出的内容记录，不用宏。确定性 ID 原样保留。覆盖的错误码：`STALE_REVISION`、`METHOD_OR_FIELD_NOT_FOUND`、`PERMISSION_DENIED`、`UNSAVED_CHANGES`、`TRANSACTION_ERROR`、`INVALID_REQUEST`。只有 `elapsed_ms` 这一个键被替换。 |
| 3 | 新增 `fixtures/golden/inputs/synthetic/`（由 `tools/MAKE_GOLDEN_INPUTS.py` 生成一次后冻结）：一个覆盖全部 6 种元素的完整场景（36 帧），以及 8 个错误场景（缺字形、未知对齐方式、未知元素类型、半透明 alpha、非二值像素、Font Pack 缺字、缺资源、无效 schema）。只有 `FileNotFoundError` 被允许作为常规场景的预期结果；其余异常只允许出现在 `err_*` 场景中。 |
| 4 | 新增 20 个加载拒绝 case（schema、非对象、screens 类型、重复和大小写冲突的 ID 或路径、越界、指向根目录、Windows 保留名、active_screen、asset_dirs、output_workbench 的各种非法情况），以及 11 个变更 case（含 4 个"保存失败后内存状态回滚"）。 |
| 5 | `--check` 改为：按 canonical 字节比较每个 case；校验每个文件的 SHA 与 manifest 一致；报告多余文件；只把 `source_blobs` 当作漂移，环境版本移到 `reference.environment` 作为元数据。新增测试覆盖类别增删、blob 漂移、字节被改、多余文件、`True` 与 `1` 的类型变化。 |
| 6 | `replace_root` 只规范化紧跟在 `${PROJECT_ROOT}` 后面的路径段，并识别 `repr()` 形式的转义路径。 |
| 7 | 新增 4 个自定义模板 case（全部占位符、CRLF、自定义前后缀、`index_entries_per_line`、sidecar 与 binary 组合），以及 19 个 profile 拒绝或边界 case。 |
| 8 | 新增 `fontpack-committed-builtin-5x8-load`：加载已冻结在仓库中的 Font Pack。 |
| 9 | 预览 case 的输入改为写明像素公式。 |
| 10 | V1 内置场景已复制到 `fixtures/golden/inputs/builtin/`，语料不再依赖 `src/`。 |

`RasterProfile` 的 `alignment`、`offset_x`、`offset_y` 字段不被 `rasterize_image` 使用，只有 Font Lab 生成字形时才用到，因此由 `fonts` 类别覆盖。

### 返工后的语料

| 类别 | case | strict | semantic |
|---|---:|---:|---:|
| encoding | 132 | 132 | 0 |
| formatting | 117 | 117 | 0 |
| raster | 27 | 27 | 0 |
| scenes | 1166 | 1166 | 0 |
| projects | 61 | 61 | 0 |
| handoff | 4 | 4 | 0 |
| automation | 18 | 18 | 0 |
| fonts | 12 | 4 | 8 |

- `manifest.json` SHA-256：`36a692872daf860c86edad4240ea38d746e52d716a560e2531cace2a35982738`
- 钉住 34 个 V1 源文件的 blob。
- `python tools\EXPORT_GOLDEN_CORPUS.py --check` 的输出为 `golden corpus: OK`。
