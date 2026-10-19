#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

mod common;

use common::{Report, cases, hex, row_strings};
use mono_core::profiles::RasterProfile;
use mono_core::raster::{RgbaImage, rasterize};
use mono_core::{EncodingProfile, encode_bitmap};
use serde_json::json;

fn unhex(text: &str) -> Vec<u8> {
    (0..text.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&text[i..i + 2], 16).unwrap())
        .collect()
}

#[test]
fn raster_cases_match_v1() {
    let mut report = Report::default();
    let mut resize_failures = Vec::new();
    for case in cases("raster") {
        let id = case["id"].as_str().unwrap();
        let input = &case["input"];
        let source = &input["source"];
        let image = RgbaImage::new(
            source["width"].as_u64().unwrap() as usize,
            source["height"].as_u64().unwrap() as usize,
            unhex(source["rgba"]["hex"].as_str().unwrap()),
        )
        .unwrap();
        let profile: RasterProfile = serde_json::from_value(input["profile"].clone()).unwrap();
        let size = input["output_size"].as_array().map(|s| {
            (
                s[0].as_u64().unwrap() as usize,
                s[1].as_u64().unwrap() as usize,
            )
        });
        let bitmap = rasterize(&image, &profile, size).unwrap();
        let vlsb = encode_bitmap(&bitmap, &EncodingProfile::default());
        let ok = json!(row_strings(bitmap.rows())) == case["expected"]["rows"]
            && case["expected"]["vlsb"]["hex"] == hex(&vlsb.data);
        if !ok && size.is_some() {
            resize_failures.push(id.to_string());
        }
        report.check(id, ok, || {
            format!("rows {:?}", row_strings(bitmap.rows()).first())
        });
    }
    if !resize_failures.is_empty() {
        eprintln!("resize mismatches: {resize_failures:?}");
    }
    report.finish_exact("raster", common::count_cases("raster", |_| true));
}
