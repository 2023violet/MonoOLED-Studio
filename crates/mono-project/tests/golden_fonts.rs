#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

mod common;

use std::path::PathBuf;

use common::{Report, cases, hex, row_strings};
use mono_core::font::{DEFAULT_CHARACTERS, FontPack, GlyphMetrics};
use mono_core::profiles::Alignment;
use mono_font::{GenerateOptions, load_font, rasterize_characters};
use mono_project::fontpack_io::{load_font_pack, save_font_pack};
use serde_json::{Map, Value, json};

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

fn temp(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("mono-golden-fonts-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn glyphs(pack: &FontPack) -> Value {
    let mut chars: Vec<char> = pack.characters().collect();
    chars.sort();
    Value::Object(
        chars
            .into_iter()
            .map(|c| {
                let g = pack.glyph(c).unwrap();
                (
                    format!("U+{:04X}", c as u32),
                    json!({"rows": row_strings(g.rows.iter().map(Vec::as_slice)), "bearing_x": g.metrics.bearing_x,
                           "bearing_y": g.metrics.bearing_y, "advance": g.metrics.advance}),
                )
            })
            .collect::<Map<String, Value>>(),
    )
}

fn persisted(root: &std::path::Path, pack: &FontPack) -> Value {
    let loaded = load_font_pack(root).unwrap();
    let mut assets: Vec<String> = std::fs::read_dir(root.join("glyphs"))
        .unwrap()
        .flatten()
        .map(|e| e.file_name().to_string_lossy().into_owned())
        .collect();
    assets.sort();
    json!({"cell": [pack.cell.0, pack.cell.1], "baseline": pack.baseline, "advance": pack.advance,
           "manifest": hex(&std::fs::read(root.join("fontpack.json")).unwrap()), "glyph_assets": assets,
           "glyphs": glyphs(pack), "reload_matches": glyphs(&loaded) == glyphs(pack)})
}

#[test]
fn strict_font_pack_cases_match_v1() {
    let all: Map<String, Value> = cases("fonts")
        .into_iter()
        .map(|c| (c["id"].as_str().unwrap().to_string(), c))
        .collect();
    let mut report = Report::default();
    let compare = |report: &mut Report, id: &str, got: &Value| {
        let e = &all[id]["expected"];
        let ok = e["cell"] == got["cell"]
            && e["baseline"] == got["baseline"]
            && e["advance"] == got["advance"]
            && e["manifest"]["hex"] == got["manifest"]
            && e["glyph_assets"] == got["glyph_assets"]
            && e["glyphs"] == got["glyphs"]
            && e["reload_matches"] == got["reload_matches"];
        report.check(id, ok, || {
            format!(
                "got {}",
                serde_json::to_string(got)
                    .unwrap()
                    .chars()
                    .take(600)
                    .collect::<String>()
            )
        });
    };
    for cell in [(5usize, 8usize), (6, 10)] {
        let root = temp(&format!("builtin{}x{}", cell.0, cell.1));
        let mut pack = FontPack::with_recommended("Builtin", cell).unwrap();
        rasterize_characters(
            &mut pack,
            DEFAULT_CHARACTERS,
            None,
            &GenerateOptions::default(),
        )
        .unwrap();
        save_font_pack(&root, &pack, None).unwrap();
        compare(
            &mut report,
            &format!("fontpack-builtin-{}x{}-roundtrip", cell.0, cell.1),
            &persisted(&root, &pack),
        );
    }
    let root = temp("manual");
    let mut pack = FontPack::new("Manual 中文", (8, 8), 6, 9).unwrap();
    pack.set_glyph(
        '中',
        (0..8)
            .map(|y| {
                (0..8)
                    .map(|x| u8::from(x == 3 || x == 4 || y == 2 || y == 5))
                    .collect()
            })
            .collect(),
        Some(GlyphMetrics {
            bearing_x: 0,
            bearing_y: 0,
            advance: 9,
        }),
    )
    .unwrap();
    pack.set_glyph(
        'A',
        (0..8)
            .map(|y| (0..8).map(|x| u8::from((x + y) % 3 == 0)).collect())
            .collect(),
        Some(GlyphMetrics {
            bearing_x: 1,
            bearing_y: -1,
            advance: 7,
        }),
    )
    .unwrap();
    save_font_pack(&root, &pack, None).unwrap();
    compare(
        &mut report,
        "fontpack-manual-8x8-cjk-roundtrip",
        &persisted(&root, &pack),
    );

    let committed = repo().join("fixtures/golden/inputs/synthetic/fonts/builtin_5x8");
    let loaded = load_font_pack(&committed).unwrap();
    let e = &all["fontpack-committed-builtin-5x8-load"]["expected"];
    report.check(
        "fontpack-committed-builtin-5x8-load",
        e["name"] == json!(loaded.name)
            && e["glyphs"] == glyphs(&loaded)
            && e["cell"] == json!([loaded.cell.0, loaded.cell.1]),
        || "committed pack mismatch".into(),
    );
    report.finish("fonts strict");
}

/// Semantic cases (D6): metrics must match exactly; pixel agreement is measured and bounded.
#[test]
fn generated_font_cases_are_semantically_equivalent() {
    let font =
        load_font(std::fs::read(repo().join("test_assets/fonts/DejaVuSans.ttf")).unwrap()).unwrap();
    let mut report = Report::default();
    let mut summary = Vec::new();
    for case in cases("fonts")
        .into_iter()
        .filter(|c| c["level"] == "semantic")
    {
        let id = case["id"].as_str().unwrap().to_string();
        let input = &case["input"];
        let expected = &case["expected"];
        let cell = (
            input["cell"][0].as_u64().unwrap() as usize,
            input["cell"][1].as_u64().unwrap() as usize,
        );
        let mut pack = FontPack::with_recommended("DejaVu", cell).unwrap();
        let options = GenerateOptions {
            font_size: input["font_size"].as_i64().unwrap(),
            threshold: input["threshold"].as_i64().unwrap(),
            antialias_scale: input
                .get("antialias_scale")
                .and_then(Value::as_i64)
                .unwrap_or(1),
            alignment: if input.get("alignment").and_then(Value::as_str) == Some("font_set") {
                Alignment::FontSet
            } else {
                Alignment::GlyphWidth
            },
            ..GenerateOptions::default()
        };
        rasterize_characters(
            &mut pack,
            input["characters"].as_str().unwrap(),
            Some(&font),
            &options,
        )
        .unwrap();
        let got = glyphs(&pack);
        let (mut same, mut total, mut metric_mismatch) = (0usize, 0usize, 0usize);
        for (key, want) in expected["glyphs"].as_object().unwrap() {
            let have = &got[key];
            if have["bearing_x"] != want["bearing_x"]
                || have["bearing_y"] != want["bearing_y"]
                || have["advance"] != want["advance"]
            {
                metric_mismatch += 1;
            }
            for (a, b) in have["rows"]
                .as_array()
                .unwrap()
                .iter()
                .zip(want["rows"].as_array().unwrap())
            {
                for (p, q) in a.as_str().unwrap().chars().zip(b.as_str().unwrap().chars()) {
                    total += 1;
                    same += usize::from(p == q);
                }
            }
        }
        let agreement = same as f64 / total.max(1) as f64;
        summary.push(format!("{id}: pixel agreement {:.4}", agreement));
        let metrics_ok = expected["cell"] == json!([pack.cell.0, pack.cell.1])
            && expected["baseline"] == json!(pack.baseline)
            && expected["advance"] == json!(pack.advance)
            && metric_mismatch == 0;
        report.check(
            &id,
            metrics_ok && agreement >= SEMANTIC_PIXEL_AGREEMENT,
            || format!("metrics_ok={metrics_ok} agreement={agreement:.4}"),
        );
    }
    eprintln!("{}", summary.join("\n"));
    report.finish("fonts semantic");
}

/// G1 threshold for TrueType-generated glyphs (D6), measured against V1 FreeType output.
const SEMANTIC_PIXEL_AGREEMENT: f64 = 0.92;
