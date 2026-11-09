//! One render asks its `Resources` for each distinct file once (TASK-018).
//!
//! The desktop session's resources read and hash a file on every lookup, so a
//! digits string, a repeated text font or several labels on one font pack used
//! to cost one disk read and SHA-256 per character or element.
#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use mono_core::CoreResult;
use mono_core::assets::{BitmapAsset, ModeFont};
use mono_core::font::FontPack;
use mono_core::render::{Resources, posix, render_scene};
use mono_core::state::State;
use serde_json::{Map, Value, json};

/// Serves fixed 1x1 assets and counts every lookup by path.
#[derive(Default)]
struct Counting {
    bitmaps: BTreeMap<String, usize>,
    fonts: BTreeMap<String, usize>,
    packs: BTreeMap<String, usize>,
}

impl Resources for Counting {
    fn bitmap(&mut self, path: &Path) -> CoreResult<Arc<BitmapAsset>> {
        *self.bitmaps.entry(posix(path)).or_default() += 1;
        Ok(Arc::new(BitmapAsset {
            path: posix(path),
            width: 1,
            height: 1,
            rows: vec![vec![1]],
            sha256: String::new(),
            source_mode: "1".into(),
            source_polarity: "lit".into(),
            inverted: false,
        }))
    }

    fn mode_font(&mut self, path: &Path) -> CoreResult<Arc<ModeFont>> {
        *self.fonts.entry(posix(path)).or_default() += 1;
        Ok(Arc::new(ModeFont::from([('A', vec![vec![1]])])))
    }

    fn font_pack(&mut self, root: &Path) -> CoreResult<Arc<FontPack>> {
        *self.packs.entry(posix(root)).or_default() += 1;
        let mut pack = FontPack::new("t", (1, 1), 0, 2)?;
        pack.set_glyph('A', vec![vec![1]], None)?;
        Ok(Arc::new(pack))
    }
}

fn root() -> PathBuf {
    std::env::temp_dir().join("mono-lookups-project")
}

fn scene(elements: Value) -> Map<String, Value> {
    serde_json::from_value(json!({
        "canvas": {"w": 64, "h": 8},
        "states": {},
        "elements": elements
    }))
    .unwrap()
}

#[test]
fn a_digits_string_reads_each_glyph_file_once() {
    let scene = scene(json!([
        {"id": "a", "type": "digits", "dir": "d", "pattern": "{d}.png", "bind": "n",
         "digit_w": 1, "digit_h": 1, "x": 0, "y": 0},
        {"id": "b", "type": "digits", "dir": "d", "pattern": "{d}.png", "bind": "n",
         "digit_w": 1, "digit_h": 1, "x": 0, "y": 2}
    ]));
    let state: State = serde_json::from_value(json!({"n": 11211})).unwrap();
    let mut resources = Counting::default();
    let result = render_scene(&scene, &root(), &state, &mut resources).unwrap();
    // Ten glyph lookups in the scene, two distinct files.
    assert_eq!(resources.bitmaps.len(), 2);
    assert!(
        resources.bitmaps.values().all(|count| *count == 1),
        "each glyph file must be looked up once per render: {:?}",
        resources.bitmaps
    );
    // The frame and the per-element asset lists are unchanged by the memo.
    assert_eq!(
        result
            .framebuffer
            .pixels()
            .iter()
            .filter(|p| **p != 0)
            .count(),
        10
    );
    assert_eq!(
        result.resolved_elements[0]["assets"]
            .as_array()
            .unwrap()
            .len(),
        5
    );
    assert_eq!(result.used_assets.len(), 2);
}

#[test]
fn a_font_header_and_a_font_pack_are_read_once_per_render() {
    let scene = scene(json!([
        {"id": "t1", "type": "text", "text": "A", "font_header": "f.h", "x": 0, "y": 0},
        {"id": "t2", "type": "text", "text": "AA", "font_header": "f.h", "x": 0, "y": 2},
        {"id": "p1", "type": "bitmap_text", "text": "A", "font_pack": "pack", "x": 0, "y": 4},
        {"id": "p2", "type": "bitmap_text", "text": "AA", "font_pack": "pack", "x": 0, "y": 6}
    ]));
    let mut resources = Counting::default();
    render_scene(&scene, &root(), &State::new(), &mut resources).unwrap();
    assert_eq!(resources.fonts.values().copied().collect::<Vec<_>>(), [1]);
    assert_eq!(resources.packs.values().copied().collect::<Vec<_>>(), [1]);
}

#[test]
fn every_render_looks_its_files_up_again() {
    // The memo lives for one render: the session's resources still see every
    // render, so a file changed on disk shows on the next frame.
    let scene = scene(json!([
        {"id": "a", "type": "digits", "dir": "d", "pattern": "{d}.png", "bind": "n",
         "digit_w": 1, "digit_h": 1, "x": 0, "y": 0}
    ]));
    let state: State = serde_json::from_value(json!({"n": 7})).unwrap();
    let mut resources = Counting::default();
    render_scene(&scene, &root(), &state, &mut resources).unwrap();
    render_scene(&scene, &root(), &state, &mut resources).unwrap();
    assert_eq!(resources.bitmaps.values().copied().collect::<Vec<_>>(), [2]);
}
