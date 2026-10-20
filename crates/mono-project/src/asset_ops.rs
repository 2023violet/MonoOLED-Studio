//! Asset import and OLED normalisation (V1 `asset_library.import_asset`,
//! `asset_convert.convert_bitmap`).

use std::path::{Path, PathBuf};

use mono_core::{CoreError, CoreResult};

use crate::atomic::atomic_write;
use crate::image_io::encode_bitmap_png;
use crate::project::resolve_under_root;
use crate::resources::{DiskResources, hex_digest, io_error, read_file};

fn is_image(path: &Path) -> bool {
    path.extension()
        .map(|e| e.to_string_lossy().to_lowercase())
        .is_some_and(|e| e == "png" || e == "bmp")
}

/// V1 `import_asset(source, target_dir='assets/imported')`: validate, then copy
/// into the project; a different file with the same name gets a hash suffix.
pub fn import_asset(root: &Path, source: &Path) -> CoreResult<PathBuf> {
    if !source.is_file() {
        return Err(CoreError::new(
            "FileNotFoundError",
            source.display().to_string(),
        ));
    }
    if !is_image(source) {
        let suffix = source
            .extension()
            .map(|e| format!(".{}", e.to_string_lossy()))
            .unwrap_or_default();
        return Err(CoreError::invalid(format!(
            "unsupported image type: {suffix}"
        )));
    }
    let raw = read_file(source)?;
    DiskResources::decode_bitmap(source, &raw)?;
    let target_root = resolve_under_root(root, "assets/imported", "asset import target")?;
    std::fs::create_dir_all(&target_root).map_err(|e| io_error(&target_root, &e))?;
    let name = source
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default();
    let mut target = target_root.join(&name);
    let digest = hex_digest(&raw);
    if target.exists() && hex_digest(&read_file(&target)?) != digest {
        let stem = source
            .file_stem()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or_default();
        let suffix = source
            .extension()
            .map(|e| e.to_string_lossy().to_lowercase())
            .unwrap_or_default();
        target = target_root.join(format!("{stem}_{}.{suffix}", &digest[..8]));
    }
    if !target.exists() {
        atomic_write(&target, &raw)?;
    }
    Ok(target)
}

/// V1 `convert_bitmap`: canonical OLED preview asset (black background, white lit pixels).
pub fn convert_bitmap(source: &Path, target: &Path) -> CoreResult<PathBuf> {
    let raw = read_file(source)?;
    let asset = DiskResources::decode_bitmap(source, &raw)?;
    let png = encode_bitmap_png(asset.width, asset.height, &asset.rows)?;
    atomic_write(target, &png)?;
    Ok(target.to_path_buf())
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    #[test]
    fn import_dedupes_by_content_and_rejects_non_images() {
        let root = std::env::temp_dir().join(format!("mono-assetops-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let src_dir = root.join("src");
        std::fs::create_dir_all(&src_dir).unwrap();
        let a = src_dir.join("icon.png");
        std::fs::write(
            &a,
            encode_bitmap_png(2, 2, &[vec![1, 0], vec![0, 1]]).unwrap(),
        )
        .unwrap();
        let project = root.join("project");
        std::fs::create_dir_all(&project).unwrap();
        let first = import_asset(&project, &a).unwrap();
        assert_eq!(first, project.join("assets/imported/icon.png"));
        assert_eq!(import_asset(&project, &a).unwrap(), first);
        std::fs::write(
            &a,
            encode_bitmap_png(2, 2, &[vec![1, 1], vec![0, 1]]).unwrap(),
        )
        .unwrap();
        let second = import_asset(&project, &a).unwrap();
        assert_ne!(second, first);
        assert!(
            second
                .file_name()
                .unwrap()
                .to_string_lossy()
                .starts_with("icon_")
        );
        let txt = src_dir.join("note.txt");
        std::fs::write(&txt, b"x").unwrap();
        assert!(import_asset(&project, &txt).is_err());
        let converted = convert_bitmap(&a, &project.join("assets/converted/icon.png")).unwrap();
        assert!(converted.is_file());
        let _ = std::fs::remove_dir_all(&root);
    }
}
