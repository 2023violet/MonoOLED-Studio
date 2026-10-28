//! Screen gallery: one init-state card per screen, rendered off the UI thread
//! and cached until the active scene changes.

use std::collections::BTreeMap;
use std::sync::mpsc::{self, Receiver, TryRecvError};

use mono_core::CoreError;
use mono_core::render::render_scene;
use mono_core::state::init_state;
use mono_project::export::validate_scene;
use mono_project::project::ProjectWorkspace;
use mono_project::resources::DiskResources;
use mono_project::scene_io::load_project_scene;

/// Beyond this the gallery lists text only; rendering every screen would take
/// seconds and the wall stops being usable long before.
pub const MAX_SCREENS: usize = 200;

/// 0/1 pixels kept as bytes: `slint::Image` is not `Send`, so the worker ships
/// raw frames and the UI thread turns them into images.
#[derive(Clone)]
pub struct FrameImage {
    pub width: usize,
    pub height: usize,
    pub pixels: Vec<u8>,
}

#[derive(Clone)]
pub struct GalleryCard {
    pub id: String,
    pub label: String,
    pub category: String,
    pub blockers: usize,
    pub warnings: usize,
    pub annotations: usize,
    pub image: Option<FrameImage>,
}

pub struct GalleryJob {
    rx: Receiver<Result<Vec<GalleryCard>, CoreError>>,
}

impl GalleryJob {
    pub fn spawn(project: ProjectWorkspace, annotations: BTreeMap<String, usize>) -> Self {
        let (tx, rx) = mpsc::channel();
        std::thread::spawn(move || {
            let _ = tx.send(build_cards(&project, &annotations));
        });
        Self { rx }
    }

    /// `Some(result)` once the worker finished; `None` while it runs.
    pub fn poll(&self) -> Option<Result<Vec<GalleryCard>, CoreError>> {
        match self.rx.try_recv() {
            Ok(result) => Some(result),
            Err(TryRecvError::Empty) => None,
            Err(TryRecvError::Disconnected) => Some(Err(CoreError::new(
                "E-GALLERY",
                "gallery worker stopped without a result",
            ))),
        }
    }
}

pub fn build_cards(
    project: &ProjectWorkspace,
    annotations: &BTreeMap<String, usize>,
) -> Result<Vec<GalleryCard>, CoreError> {
    let screens = project.screens();
    let categories = categories(project);
    let mut resources = DiskResources::frozen();
    let mut cards = Vec::new();
    for screen in screens.iter().take(MAX_SCREENS) {
        let scene = match load_project_scene(project, Some(&screen.id)) {
            Ok(scene) => scene,
            Err(_) => continue,
        };
        let state = init_state(&scene.data);
        let findings = validate_scene(&scene.data, &project.root, Some(&state), &mut resources);
        let blockers = findings.iter().filter(|f| f.is_blocking()).count();
        let warnings = findings.len().saturating_sub(blockers);
        let image = render_scene(&scene.data, &project.root, &state, &mut resources)
            .ok()
            .map(|result| FrameImage {
                width: result.framebuffer.width().max(1),
                height: result.framebuffer.height().max(1),
                pixels: result.framebuffer.pixels().to_vec(),
            });
        cards.push(GalleryCard {
            id: screen.id.clone(),
            label: screen.label.clone(),
            category: category_for(&screen.id, categories.get(&screen.id).map(String::as_str)),
            blockers,
            warnings,
            annotations: annotations.get(&screen.id).copied().unwrap_or(0),
            image,
        });
    }
    sort_cards(&mut cards);
    Ok(cards)
}

/// Explicit `screens[].category` when present; read-only, never written back.
fn categories(project: &ProjectWorkspace) -> BTreeMap<String, String> {
    project
        .data
        .get("screens")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|screen| {
            let id = screen.get("id").and_then(serde_json::Value::as_str)?;
            let category = screen.get("category").and_then(serde_json::Value::as_str)?;
            (!category.trim().is_empty()).then(|| (id.to_string(), category.trim().to_string()))
        })
        .collect()
}

fn category_for(id: &str, explicit: Option<&str>) -> String {
    if let Some(category) = explicit {
        return category.to_string();
    }
    match id.split_once(['_', '-', '.']) {
        Some((prefix, _)) if !prefix.is_empty() => prefix.to_string(),
        _ => "Screens".to_string(),
    }
}

/// Deterministic order: category, label, id.
pub fn sort_cards(cards: &mut [GalleryCard]) {
    cards.sort_by(|a, b| {
        a.category
            .chars()
            .cmp(b.category.chars())
            .then_with(|| a.label.chars().cmp(b.label.chars()))
            .then_with(|| a.id.chars().cmp(b.id.chars()))
    });
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;
    use std::path::{Path, PathBuf};

    fn project(name: &str) -> (ProjectWorkspace, PathBuf) {
        let root = std::env::temp_dir().join(format!("mono-gallery-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        copy_dir(&repo.join("test_assets/projects/curing_lite"), &root);
        let root = mono_project::project::py_resolve(&root);
        let workspace = ProjectWorkspace::load(&root.join("project.oled.json")).unwrap();
        (workspace, root)
    }

    fn copy_dir(from: &Path, to: &Path) {
        std::fs::create_dir_all(to).unwrap();
        for entry in std::fs::read_dir(from).unwrap() {
            let entry = entry.unwrap();
            let target = to.join(entry.file_name());
            if entry.file_type().unwrap().is_dir() {
                copy_dir(&entry.path(), &target);
            } else {
                std::fs::copy(entry.path(), target).unwrap();
            }
        }
    }

    #[test]
    fn renders_one_card_per_screen() {
        let (project, root) = project("cards");
        let cards = build_cards(&project, &BTreeMap::new()).unwrap();
        assert_eq!(cards.len(), project.screens().len());
        assert!(cards.iter().all(|card| card.image.is_some()));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn reports_blockers_per_screen() {
        let (project, root) = project("blockers");
        let mut cards = build_cards(&project, &BTreeMap::new()).unwrap();
        assert!(cards.iter().all(|card| card.blockers == 0));
        // A placeholder without an asset file is a BLOCKER for that screen only.
        let scene_path = root.join("scenes/main_scene.json");
        let mut scene: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&scene_path).unwrap()).unwrap();
        scene["elements"]
            .as_array_mut()
            .unwrap()
            .push(serde_json::json!({
                "id": "broken",
                "type": "image",
                "x": 0,
                "y": 0,
                "w": 8,
                "h": 8,
                "assets": ["assets/missing.png"],
            }));
        std::fs::write(&scene_path, scene.to_string()).unwrap();
        cards = build_cards(&project, &BTreeMap::new()).unwrap();
        let card = cards.iter().find(|card| card.id == "main").unwrap();
        assert!(card.blockers > 0);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn sorts_and_groups_by_category() {
        let mut cards = vec![
            card("b", "Beta", "Ui"),
            card("a", "Alpha", "Ui"),
            card("z", "Zed", "Boot"),
        ];
        sort_cards(&mut cards);
        let order: Vec<&str> = cards.iter().map(|card| card.id.as_str()).collect();
        assert_eq!(order, ["z", "a", "b"]);
        assert_eq!(category_for("boot_logo", None), "boot");
        assert_eq!(category_for("main", None), "Screens");
        assert_eq!(category_for("main", Some("System")), "System");
    }

    fn card(id: &str, label: &str, category: &str) -> GalleryCard {
        GalleryCard {
            id: id.into(),
            label: label.into(),
            category: category.into(),
            blockers: 0,
            warnings: 0,
            annotations: 0,
            image: None,
        }
    }
}
