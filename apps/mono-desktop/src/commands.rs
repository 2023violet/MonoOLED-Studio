//! Single source of truth for commands: menu actions, palette entries, default
//! shortcuts and fixed chords all derive from [`COMMANDS`]. Adding a command
//! means adding one entry here (plus its dispatch branch).

use serde_json::{Map, Value};

/// What a command needs to run. `ctx` describes the current app context.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Requirement {
    None,
    Document,
    Project,
    Scene,
    PixelOrFont,
}

impl Requirement {
    /// Whether a command with requirement `self` is usable in `ctx`.
    pub fn available(self, ctx: Requirement) -> bool {
        match self {
            Self::None => true,
            Self::Document => !matches!(ctx, Self::None | Self::Project),
            Self::Project => ctx != Self::None,
            Self::Scene => matches!(ctx, Self::Scene | Self::Document),
            Self::PixelOrFont => matches!(ctx, Self::PixelOrFont | Self::Document),
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct CommandSpec {
    pub id: &'static str,
    pub label_key: &'static str,
    pub action: &'static str,
    pub default_chord: Option<&'static str>,
    pub configurable: bool,
    pub palette: bool,
    pub requires: Requirement,
}

const fn cmd(
    id: &'static str,
    label_key: &'static str,
    action: &'static str,
    default_chord: Option<&'static str>,
    configurable: bool,
    palette: bool,
    requires: Requirement,
) -> CommandSpec {
    CommandSpec {
        id,
        label_key,
        action,
        default_chord,
        configurable,
        palette,
        requires,
    }
}

use Requirement::{Document, None as Always, PixelOrFont, Project, Scene};

pub const COMMANDS: &[CommandSpec] = &[
    // Configurable shortcuts first: `spec_for_action` prefers the user-bound entry.
    cmd(
        "preferences.open",
        "action.preferences",
        "preferences",
        Some("Ctrl+,"),
        true,
        true,
        Always,
    ),
    cmd(
        "workspace.canvas_only",
        "view.canvas_only",
        "canvas-only",
        Some("Ctrl+Space"),
        true,
        true,
        Always,
    ),
    cmd(
        "project.save",
        "action.save",
        "save",
        Some("Ctrl+S"),
        true,
        true,
        Document,
    ),
    cmd(
        "designer.undo",
        "action.undo",
        "undo",
        Some("Ctrl+Z"),
        true,
        true,
        Document,
    ),
    cmd(
        "designer.redo",
        "action.redo",
        "redo",
        Some("Ctrl+Y"),
        true,
        true,
        Document,
    ),
    cmd(
        "pixel.pencil",
        "pixel.tool.Pencil",
        "pixel-tool:0",
        Some("B"),
        true,
        true,
        PixelOrFont,
    ),
    cmd(
        "pixel.select",
        "pixel.tool.Select",
        "pixel-tool:5",
        Some("M"),
        true,
        true,
        PixelOrFont,
    ),
    cmd(
        "pixel.fill",
        "pixel.tool.Fill",
        "pixel-tool:4",
        Some("F"),
        true,
        true,
        PixelOrFont,
    ),
    // File
    cmd(
        "new-project",
        "action.new_project",
        "new-project",
        Some("Ctrl+N"),
        false,
        true,
        Always,
    ),
    cmd(
        "open-project",
        "action.open_project",
        "open-project",
        Some("Ctrl+Shift+O"),
        false,
        true,
        Always,
    ),
    cmd(
        "open-scene",
        "action.open_scene",
        "open-scene",
        Some("Ctrl+O"),
        false,
        true,
        Always,
    ),
    cmd(
        "export-current",
        "action.export_current",
        "export-current",
        None,
        false,
        true,
        Document,
    ),
    cmd(
        "export-all",
        "action.export_all",
        "export-all",
        None,
        false,
        true,
        Document,
    ),
    cmd(
        "handoff",
        "action.handoff",
        "handoff",
        Some("Ctrl+Shift+E"),
        false,
        true,
        Document,
    ),
    cmd(
        "export-c-header",
        "action.export_c_header",
        "export-c-header",
        None,
        false,
        true,
        Document,
    ),
    cmd(
        "thumbnail-wall",
        "action.thumbnail_wall",
        "thumbnail-wall",
        None,
        false,
        true,
        Document,
    ),
    cmd("exit", "action.exit", "exit", None, false, false, Always),
    // Edit
    cmd(
        "add-placeholder",
        "action.add_placeholder",
        "add-placeholder",
        None,
        false,
        false,
        Project,
    ),
    cmd(
        "assign-bitmap",
        "action.assign_bitmap",
        "assign-bitmap",
        None,
        false,
        false,
        Scene,
    ),
    cmd(
        "duplicate",
        "action.duplicate",
        "duplicate",
        None,
        false,
        false,
        Scene,
    ),
    cmd(
        "delete",
        "action.delete",
        "delete",
        None,
        false,
        false,
        Scene,
    ),
    cmd("lock", "action.lock", "lock", None, false, false, Scene),
    cmd(
        "unlock",
        "action.unlock",
        "unlock",
        None,
        false,
        false,
        Scene,
    ),
    cmd("hide", "action.hide", "hide", None, false, false, Scene),
    cmd("show", "action.show", "show", None, false, false, Scene),
    cmd("snap", "align.snap", "snap", None, false, false, Scene),
    // Arrange
    cmd("front", "action.front", "front", None, false, false, Scene),
    cmd("back", "action.back", "back", None, false, false, Scene),
    cmd(
        "group",
        "action.group",
        "group",
        Some("Ctrl+G"),
        false,
        false,
        Scene,
    ),
    cmd(
        "ungroup",
        "action.ungroup",
        "ungroup",
        Some("Ctrl+Shift+G"),
        false,
        false,
        Scene,
    ),
    cmd(
        "align:left",
        "align.left",
        "align:left",
        None,
        false,
        false,
        Scene,
    ),
    cmd(
        "align:right",
        "align.right",
        "align:right",
        None,
        false,
        false,
        Scene,
    ),
    cmd(
        "align:top",
        "align.top",
        "align:top",
        None,
        false,
        false,
        Scene,
    ),
    cmd(
        "align:bottom",
        "align.bottom",
        "align:bottom",
        None,
        false,
        false,
        Scene,
    ),
    // View
    cmd(
        "workspace:0",
        "workspace.design",
        "workspace:0",
        None,
        false,
        true,
        Always,
    ),
    cmd(
        "workspace:1",
        "workspace.pixel",
        "workspace:1",
        Some("Ctrl+Shift+P"),
        false,
        true,
        Always,
    ),
    cmd(
        "workspace:2",
        "workspace.font",
        "workspace:2",
        Some("Ctrl+Shift+F"),
        false,
        true,
        Always,
    ),
    cmd(
        "workspace:3",
        "workspace.review",
        "workspace:3",
        None,
        false,
        true,
        Always,
    ),
    cmd(
        "diagnostics",
        "action.diagnostics",
        "diagnostics",
        Some("Ctrl+J"),
        false,
        true,
        Always,
    ),
    cmd(
        "toggle-navigator",
        "view.navigator",
        "toggle-navigator",
        Some("Ctrl+1"),
        false,
        true,
        Always,
    ),
    cmd(
        "toggle-inspector",
        "view.inspector",
        "toggle-inspector",
        Some("Ctrl+2"),
        false,
        true,
        Always,
    ),
    cmd(
        "reset-workspace",
        "view.reset_workspace",
        "reset-workspace",
        None,
        false,
        true,
        Always,
    ),
    // Tools
    cmd(
        "asset-health",
        "action.asset_health",
        "asset-health",
        None,
        false,
        true,
        Project,
    ),
    cmd(
        "save-template",
        "action.save_template",
        "save-template",
        None,
        false,
        true,
        Project,
    ),
    cmd(
        "insert-template",
        "action.insert_template",
        "insert-template",
        None,
        false,
        true,
        Project,
    ),
    cmd(
        "convert-asset",
        "action.convert_asset",
        "convert-asset",
        None,
        false,
        true,
        Project,
    ),
    cmd(
        "agent-bridge",
        "action.agent_bridge",
        "agent-bridge",
        None,
        false,
        true,
        Document,
    ),
    cmd(
        "bitmap-text",
        "action.bitmap_text",
        "bitmap-text",
        None,
        false,
        false,
        Always,
    ),
    cmd(
        "autosave",
        "action.autosave",
        "autosave",
        None,
        false,
        false,
        Always,
    ),
    cmd(
        "restore-autosave",
        "action.restore_autosave",
        "restore-autosave",
        None,
        false,
        false,
        Always,
    ),
    cmd(
        "command-palette",
        "command.title",
        "command-palette",
        Some("Ctrl+K"),
        false,
        true,
        Always,
    ),
    cmd(
        "batch-validate",
        "action.batch_validate",
        "batch-validate",
        None,
        false,
        true,
        Document,
    ),
    cmd(
        "performance",
        "performance.title",
        "performance",
        None,
        false,
        true,
        Always,
    ),
    cmd(
        "cancel-job",
        "action.cancel_job",
        "cancel-job",
        None,
        false,
        true,
        Always,
    ),
    cmd(
        "shortcuts",
        "action.shortcuts",
        "shortcuts",
        None,
        false,
        true,
        Always,
    ),
    // Help
    cmd("about", "action.about", "about", None, false, false, Always),
    cmd(
        "open-docs",
        "action.docs",
        "open-docs",
        None,
        false,
        false,
        Always,
    ),
    cmd(
        "report-issue",
        "action.report_issue",
        "report-issue",
        None,
        false,
        false,
        Always,
    ),
    cmd(
        "toggle-play",
        "action.play",
        "toggle-play",
        None,
        false,
        false,
        Scene,
    ),
    cmd("step", "action.step", "step", None, false, false, Scene),
    cmd(
        "reset-runtime",
        "action.reset",
        "reset-runtime",
        None,
        false,
        false,
        Scene,
    ),
];

/// Configurable shortcut ids, in Preferences display order.
pub const CONFIGURABLE: [&str; 8] = [
    "preferences.open",
    "workspace.canvas_only",
    "project.save",
    "designer.undo",
    "designer.redo",
    "pixel.pencil",
    "pixel.select",
    "pixel.fill",
];

/// Normalised shortcut text for comparisons (`ctrl+s` == `Ctrl+S`).
pub fn normalize_shortcut(text: &str) -> String {
    text.split('+')
        .map(|part| part.trim().to_lowercase())
        .collect::<Vec<_>>()
        .join("+")
}

pub fn spec(id: &str) -> Option<&'static CommandSpec> {
    COMMANDS.iter().find(|spec| spec.id == id)
}

/// Default bindings for the configurable commands (`shortcuts` preference object).
pub fn default_shortcuts() -> Value {
    let mut map = Map::new();
    for id in CONFIGURABLE {
        if let Some(chord) = spec(id).and_then(|spec| spec.default_chord) {
            map.insert(id.to_string(), Value::String(chord.to_string()));
        }
    }
    Value::Object(map)
}

/// The command's effective chord: the user binding when configurable, otherwise
/// the registry default.
pub fn chord_for(spec: &CommandSpec, shortcuts: &Value) -> Option<String> {
    if spec.configurable {
        shortcuts
            .get(spec.id)
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|chord| !chord.is_empty())
            .map(str::to_string)
    } else {
        spec.default_chord.map(str::to_string)
    }
}

/// Fixed (non-configurable) chord → action id.
pub fn fixed_action(chord: &str) -> Option<&'static str> {
    let wanted = normalize_shortcut(chord);
    COMMANDS
        .iter()
        .filter(|spec| !spec.configurable)
        .find(|spec| {
            spec.default_chord
                .is_some_and(|bound| normalize_shortcut(bound) == wanted)
        })
        .map(|spec| spec.action)
}

pub fn palette_commands(ctx: Requirement) -> Vec<&'static CommandSpec> {
    COMMANDS
        .iter()
        .filter(|spec| spec.palette && spec.requires.available(ctx))
        .collect()
}

/// Whether an action id (including dynamic families) is registered/handled.
pub fn is_known(action: &str) -> bool {
    if COMMANDS.iter().any(|spec| spec.action == action) {
        return true;
    }
    const DYNAMIC: [&str; 4] = ["align:", "workspace:", "pixel-open:", "pixel-tool:"];
    DYNAMIC.iter().any(|prefix| action.starts_with(prefix))
        || action.starts_with("pixel-inspector:")
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
    use super::*;
    use std::collections::BTreeSet;

    #[test]
    fn registry_ids_unique() {
        let mut ids = BTreeSet::new();
        for spec in COMMANDS {
            assert!(ids.insert(spec.id), "duplicate command id {}", spec.id);
            assert_ne!(
                crate::i18n::tr("en_US", spec.label_key),
                spec.label_key,
                "missing English label for {}",
                spec.label_key
            );
        }
    }

    #[test]
    fn defaults_match_registry() {
        let defaults = default_shortcuts();
        let object = defaults.as_object().expect("shortcuts object");
        assert_eq!(object.len(), CONFIGURABLE.len());
        for id in CONFIGURABLE {
            let spec = spec(id).unwrap_or_else(|| panic!("missing spec {id}"));
            assert!(spec.configurable, "{id} must be configurable");
            assert_eq!(
                object.get(id).and_then(Value::as_str),
                spec.default_chord,
                "{id}"
            );
        }
        let configurable: Vec<_> = COMMANDS
            .iter()
            .filter(|spec| spec.configurable)
            .map(|spec| spec.id)
            .collect();
        assert_eq!(configurable, CONFIGURABLE.to_vec());
    }

    #[test]
    fn palette_actions_are_dispatchable() {
        let commands = palette_commands(Requirement::Document);
        assert!(commands.len() >= 25);
        for spec in commands {
            assert!(is_known(spec.action), "unregistered {}", spec.action);
            assert!(!spec.action.starts_with("align:"));
        }
        let pixel: Vec<_> = palette_commands(Requirement::PixelOrFont)
            .iter()
            .map(|spec| spec.action)
            .collect();
        assert!(pixel.contains(&"pixel-tool:0"));
        let empty: Vec<_> = palette_commands(Requirement::None)
            .iter()
            .map(|spec| spec.action)
            .collect();
        assert!(empty.contains(&"preferences"));
        assert!(!empty.contains(&"save"));
    }

    #[test]
    fn fixed_chords_do_not_collide() {
        let mut seen = BTreeSet::new();
        for spec in COMMANDS.iter().filter(|spec| !spec.configurable) {
            if let Some(chord) = spec.default_chord {
                let normal = normalize_shortcut(chord);
                assert!(seen.insert(normal.clone()), "{chord} is bound twice");
            }
        }
        let defaults = default_shortcuts();
        for spec in COMMANDS.iter().filter(|spec| spec.configurable) {
            let chord = chord_for(spec, &defaults).expect("configurable default");
            assert!(
                seen.insert(normalize_shortcut(&chord)),
                "{chord} collides with a fixed chord"
            );
        }
    }

    #[test]
    fn slint_menu_actions_are_known() {
        let source = include_str!("../ui/main.slint");
        let mut rest = source;
        let mut checked = 0;
        while let Some(start) = rest.find("AppModel.action(\"") {
            rest = &rest[start + "AppModel.action(\"".len()..];
            let Some(end) = rest.find('"') else { break };
            let action = &rest[..end];
            assert!(
                is_known(action),
                "main.slint action {action} is not registered"
            );
            checked += 1;
            rest = &rest[end..];
        }
        assert!(checked >= 40, "only {checked} menu actions found");
    }
}
