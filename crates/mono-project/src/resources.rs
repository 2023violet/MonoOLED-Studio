//! Content-addressed render resource cache (V1 `resource_cache.RenderResources`).
//!
//! Files are hashed from their current bytes before a cached decode is reused,
//! so same-size/same-mtime edits are still picked up.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use mono_core::assets::{BitmapAsset, ModeFont, bitmap_from_rgba, parse_mode_font};
use mono_core::font::FontPack;
use mono_core::render::{Resources, posix};
use mono_core::{CoreError, CoreResult};
use sha2::{Digest, Sha256};

use crate::fontpack_io::{fontpack_fingerprint, load_font_pack};
use crate::image_io::decode_png;

pub fn hex_digest(data: &[u8]) -> String {
    Sha256::digest(data)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// Read a file, mapping "not found" to the V1 `FileNotFoundError` contract.
pub fn read_file(path: &Path) -> CoreResult<Vec<u8>> {
    std::fs::read(path).map_err(|e| io_error(path, &e))
}

pub fn io_error(path: &Path, error: &std::io::Error) -> CoreError {
    if error.kind() == std::io::ErrorKind::NotFound {
        CoreError::new(
            "E-IO-NOT-FOUND",
            format!("[Errno 2] No such file or directory: '{}'", posix(path)),
        )
    } else {
        CoreError::new("E-IO", format!("{}: {error}", posix(path)))
    }
}

#[derive(Default)]
pub struct DiskResources {
    bitmaps: HashMap<PathBuf, (String, Arc<BitmapAsset>)>,
    fonts: HashMap<PathBuf, (String, Arc<ModeFont>)>,
    packs: HashMap<PathBuf, (String, Arc<FontPack>)>,
}

impl DiskResources {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn decode_bitmap(path: &Path, raw: &[u8]) -> CoreResult<BitmapAsset> {
        let image = decode_png(raw)?;
        bitmap_from_rgba(
            &posix(path),
            image.width,
            image.height,
            &image.rgba,
            hex_digest(raw),
            &image.mode,
        )
    }
}

impl Resources for DiskResources {
    fn bitmap(&mut self, path: &Path) -> CoreResult<Arc<BitmapAsset>> {
        let raw = read_file(path)?;
        let digest = hex_digest(&raw);
        if let Some((cached, asset)) = self.bitmaps.get(path) {
            if *cached == digest {
                return Ok(asset.clone());
            }
        }
        let asset = Arc::new(Self::decode_bitmap(path, &raw)?);
        self.bitmaps
            .insert(path.to_path_buf(), (digest, asset.clone()));
        Ok(asset)
    }

    fn mode_font(&mut self, path: &Path) -> CoreResult<Arc<ModeFont>> {
        let raw = read_file(path)?;
        let digest = hex_digest(&raw);
        if let Some((cached, font)) = self.fonts.get(path) {
            if *cached == digest {
                return Ok(font.clone());
            }
        }
        let text = String::from_utf8(raw)
            .map_err(|_| CoreError::new("E-IO", format!("{}: not UTF-8", posix(path))))?;
        let font = Arc::new(parse_mode_font(&posix(path), &text)?);
        self.fonts
            .insert(path.to_path_buf(), (digest, font.clone()));
        Ok(font)
    }

    fn font_pack(&mut self, root: &Path) -> CoreResult<Arc<FontPack>> {
        let fingerprint = fontpack_fingerprint(root)?;
        if let Some((cached, pack)) = self.packs.get(root) {
            if *cached == fingerprint {
                return Ok(pack.clone());
            }
        }
        let pack = Arc::new(load_font_pack(root)?);
        self.packs
            .insert(root.to_path_buf(), (fingerprint, pack.clone()));
        Ok(pack)
    }
}
