# G1 证据记录 — 无头 Core 对等

- 日期：2026-10-19
- 范围：`crates/mono-core`、`crates/mono-project`、`crates/mono-font`、`apps/mono-cli`
- 三平台 CI：GitHub Actions run `39335475935`（workflow `Rust`），对应提交 `69c9874`。Windows、Ubuntu、macOS 三个平台的 fmt、clippy `-D warnings`、`cargo test --locked`、CLI smoke 全部通过；cargo-deny 也通过（MEASURED）。
- V1 回归：同一提交上的 workflow `CI`（run `39335475948`）通过，其中包括 `test_committed_corpus_matches_v1`（MEASURED）。

## 1. 语料对等结果

| 类别 | 用例数 | Rust 结果 | 比较方式 |
|---|---:|---|---|
| encoding | 132 | 全部一致 | 字节、`padded_size`、trace 采样 |
| formatting | 117 | 全部一致 | 数据字节；文本、预览、sidecar 的 SHA 和全文；索引；校验错误的类型和消息 |
| raster | 27 | 全部一致，**含 9 个 LANCZOS 缩放用例** | 行和 VLSB 字节 |
| scenes | 1166 | 全部一致 | VLSB 字节、`resolved_elements`、`used_files`；错误用例按错误类型比较 |
| projects | 61 | 全部一致 | manifest 字节、文件快照、错误类型和消息、回滚 |
| fonts（strict） | 4 | 全部一致 | `fontpack.json` 字节、字形行、指标 |
| fonts（semantic） | 8 | 指标全部一致；逐像素一致率 0.922–0.983 | D6：每个用例 ≥ 0.92 |
| handoff | 4 个 ZIP，共 68 个条目 | 66 个条目逐字节或逐像素一致；2 个条目见偏差 2 | 见下 |
| automation | 18 个会话 | G4e 实现 | — |

## 2. 记录在案的偏差

1. **TTF 字形生成为 semantic**（D6）：Rust 用 `ab_glyph`，V1 用 Pillow/FreeType。G1 将阈值定为每个用例逐像素一致率 ≥ 0.92（实测最低 0.9224，即 5×8 单元格、无超采样），字形指标必须完全一致。
2. **交接包中的 3 个说明文件**（`HANDOFF_README.md`、`design_rules.md`、`asset_health.md`）：V1 用 `Path.write_text` 写入，所以在 Windows 上是 CRLF、在 Linux 上是 LF。Rust 在所有平台一律写 LF。测试只对这 3 个文件做换行归一化后比较。
3. **`thumbnail_wall.png`**：V1 的标签使用 Pillow 默认字体渲染，Rust 改用内置 5×7 字体。因此只比较画布尺寸，缩略图像素不在比较范围内。
4. **PNG 和 ZIP 的编码字节**：取决于编码器和 deflate 实现，按解码后的像素或条目内容比较。
5. **BMP 资源**：V1 依靠 Pillow 按内容识别格式（`curing_lite` 中有一个扩展名为 `.png` 的 BMP）。Rust 新增了按内容识别和最小 BMP 解码器（支持无压缩的 1/4/8/24/32 位）。
6. **AssetLibrary 持久缓存**：V1 会写 `.oled/asset_cache_v1.json`，Rust 的资源健康扫描不写这个缓存。它只是性能缓存，不影响输出。

## 3. 性能（初步，MEASURED，Windows debug/release 混合）

| 操作 | V1（Python） | Rust |
|---|---:|---:|
| 渲染 1166 个场景用例并比对 | 约 40 s（语料生成中的 scenes 类别） | 1.0–1.5 s（`cargo test` debug） |
| 全部 Rust 语料测试 | — | 约 12 s（debug，含 4 个交接 ZIP） |

正式的性能预算（spec §5）在 G4 中测量。

## 4. 依赖（cargo-deny 通过）

| crate | 位置 | 理由 |
|---|---|---|
| serde、serde_json（preserve_order）、indexmap | core、project | 场景和项目 JSON 需要保持键顺序，以便与 V1 逐字节一致 |
| sha2 | project | 指纹和 manifest |
| png 0.18 | project | PNG 编解码 |
| zip 9（仅 deflate） | project | 交接包；从 2.x 升级以修复 RUSTSEC-2026-0367/0368/0369 |
| ab_glyph | mono-font | TTF 字形；其间接依赖 ttf-parser 被标记为不再维护（RUSTSEC-2026-0192），已带理由忽略 |

与 spec §6.3 的偏差：`mono-core` 依赖了 `serde_json` 和 `indexmap`。原因是场景是动态 JSON 文档，渲染和状态语义必须直接作用于保持键顺序的 JSON。Core 仍然不做任何 IO。

## 5. 未运行或未覆盖

- Automation API 的 Rust 实现及其回放：G4e；
- Rust 版的 `simulate` 和会话日志：没有对应的 V1 语料（输出带时间戳），只做了 CLI smoke；
- 真实 OLED 硬件：`NOT_VERIFIED`。

## 6. 独立代理审查

### 第一轮（代理审查，静态，2026-10-19）：`REWORK REQUIRED`

| # | 发现 | 处理 |
|---|---|---|
| A1 | 图片文件头的宽高未经检查就直接分配内存；`FrameBuffer::new` 也没有上限 | PNG 和 BMP 解码前先按 Pillow 的阈值 89,478,485 像素检查；BMP 校验文件长度并限制调色板大小；`FrameBuffer` 边长上限为 8192。新增 `safety.rs` 回归测试 |
| A2 | 对用户提供的数值做 i64 运算会溢出，导致越界检查被绕过 | 校验器改用 i128 计算；渲染器中所有整数夹在 ±1e9 之间，绘制结果不变；状态矩阵改用 i128 或饱和运算；`eval_do` 改用 checked 运算，并对非整数报 TypeError |
| B3 | 清理和遍历目录时会跟随 symlink 或 junction | `prune` 跳过所有链接；资源扫描和 ZIP 遍历不再穿过链接（与 Python `rglob` 一致）；新增 junction 回归测试 |
| B4 | 测试没有钉住用例数 | 每个对比测试都断言实际检查数等于语料中的用例数；新增 `golden_manifest.rs`，校验各文件的 SHA 和用例数与 manifest 一致 |
| B5 | 场景错误用例只比较错误类型 | 保留这种比较方式，因为 V1 的消息中含有 Python repr 形式的绝对路径；作为偏差 7 记录在下方 |
| B6 | 字体语义比较只看总体一致率 | 新增每个字形 ≥ 0.70 的下限（实测最差 0.75），并检查行数和列数 |
| B7 | `zone: {}` 的处理与 V1 不一致 | 渲染器忽略空 zone，与 V1 的 `if zone:` 一致 |
| B8–B11 | `eval_do` 类型错误；`int(None)` 应报 TypeError；路径冲突检测比 V1 弱；casefold；空标签；`FileExistsError` 消息；Font Pack 的 `int()` 处理和链接安全 | 全部按 V1 语义修正（`posix_key` 归一化路径；`casefold`；空标签时回退到 ID；消息只含路径；Font Pack 字段走 `py_int` 并用 `py_resolve` 检查包含关系） |
| C | 临时文件可能复用已有路径 | 改用 `create_new` 创建，文件名加进程内计数器 |

### 补充偏差（D 项）

7. **场景错误用例只按错误类别比较**：V1 的消息中含有 Python `repr()` 形式的平台路径。
8. **图片格式范围**：只支持 PNG 和无压缩 BMP（1/4/8/24/32 位）。GIF、TIFF、WebP、JPEG、RLE 或位域 BMP 会报"无法识别"，资源健康检查中会列为无效资源。V1 通过 Pillow 能接受更多格式，但 MonoOLED 项目资源实际只用 PNG（以及误命名的 BMP）。
9. **16 位灰度 PNG**：Rust 取高字节，Pillow 截断到 255。只有非二值像素会有差别，而这类像素本来就会被资源规则拒绝。
10. **超大几何值**：渲染器把超出 ±1e9 像素的坐标夹到边界值，绘制结果不变，但 `resolved_elements` 中显示的是夹过之后的值。
11. **交接 ZIP 的确定性**：测试按名称比较条目内容，没有比较条目顺序、时间戳和权限。这几项由 `deterministic_zip` 的实现保证，属于 `DOCUMENTED`。
12. **3 个 CRLF 文件**：语料是在 Windows 上生成的。测试先在 Rust 输出中把 LF 转为 CRLF，再与语料比较，因此依赖语料的生成平台。
13. **没有 V1 语料直接覆盖的路径**：`check_design_rules`、导出被阻断的流程、`prune`、`select_export_states`、`eval_do`/`clamp_state`、`asset_health` 中的重复和无效资源。这些只通过 4 个交接包间接覆盖，或由 `safety.rs` 中的 Rust 单元测试覆盖。

§3 的性能数字来自本机运行，不能直接从仓库复现。正式的性能预算在 G4 中按 `mono-cli bench` 测量。

### 返工后的验证（MEASURED）

- `cargo test --workspace`：全部通过，包括新增的 `golden_manifest`（1 个）和 `safety`（7 个）。
- `cargo clippy --workspace --all-targets -- -D warnings`：0 个错误。
- `cargo fmt --all --check`：通过。
