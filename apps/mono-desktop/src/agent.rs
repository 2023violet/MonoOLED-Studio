//! Code AI Agent Bridge in the desktop app (V1 `QtAutomationBridge` +
//! `toggle_agent_bridge`): Automation API 1.3.0 on 127.0.0.1 with `edit`
//! permission, operating on the Designer's live session.
//!
//! Requests are executed on the UI thread from the job timer: the Designer's
//! session, project and selection are lent to the service for each batch and
//! taken back afterwards, so there is exactly one source of truth.

use mono_automation::{Bridge, Service};
use mono_core::CoreError;
use serde_json::Value;
use slint::Global;

use crate::app::{App, ss};
use crate::i18n::trf;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum BridgePermission {
    Observe,
    #[default]
    Edit,
    Full,
}

impl BridgePermission {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Observe => "observe",
            Self::Edit => "edit",
            Self::Full => "full",
        }
    }

    pub fn index(self) -> i32 {
        match self {
            Self::Observe => 0,
            Self::Edit => 1,
            Self::Full => 2,
        }
    }

    pub fn from_index(index: i32) -> Self {
        match index {
            0 => Self::Observe,
            2 => Self::Full,
            _ => Self::Edit,
        }
    }

    pub fn label_key(self) -> &'static str {
        match self {
            Self::Observe => "agent.permission.observe",
            Self::Edit => "agent.permission.edit",
            Self::Full => "agent.permission.full",
        }
    }
}

pub struct Agent {
    pub bridge: Bridge,
    pub service: Service,
    pub permission: BridgePermission,
}

impl App {
    /// Start the bridge on the live session with the pending permission.
    pub fn start_agent(&mut self) -> Result<String, CoreError> {
        let permission = self.pending_permission;
        self.start_agent_with(permission)?;
        let text = match &self.agent {
            Some(agent) => trf(
                &self.lang,
                "agent.status.local",
                &[("port", agent.bridge.port.to_string())],
            ),
            None => String::new(),
        };
        Ok(text)
    }

    pub fn start_agent_with(&mut self, permission: BridgePermission) -> Result<(), CoreError> {
        let Some(session) = self.session.as_ref() else {
            return Err(CoreError::invalid(self.t("bench.no_project")));
        };
        let mut service = Service::new(session.doc.clone(), None, permission.as_str())
            .map_err(|e| CoreError::invalid(e.message().to_string()))?;
        service.editor_attached = true;
        let bridge = Bridge::start(0).map_err(|e| CoreError::invalid(e.to_string()))?;
        self.log_event(format!(
            "AGENT_BRIDGE on 127.0.0.1:{} permission={}",
            bridge.port,
            permission.as_str()
        ));
        self.pending_permission = permission;
        self.agent = Some(Agent {
            bridge,
            service,
            permission,
        });
        self.refresh_agent_status();
        self.refresh_agent_panel();
        Ok(())
    }

    pub fn stop_agent(&mut self) {
        if let Some(mut agent) = self.agent.take() {
            agent.bridge.stop();
            self.log_event("AGENT_BRIDGE off");
            self.refresh_agent_status();
            self.refresh_agent_panel();
        }
    }

    /// Switch permission; a running bridge restarts so the new permission is
    /// enforced by a fresh token (old clients are locked out).
    pub fn set_agent_permission(&mut self, permission: BridgePermission) -> Result<(), CoreError> {
        let was_running = self.agent.is_some();
        self.pending_permission = permission;
        if was_running {
            self.stop_agent();
            self.start_agent_with(permission)?;
        } else {
            self.refresh_agent_panel();
        }
        Ok(())
    }

    /// Panel actions: start/stop, copy, permission change.
    pub fn agent_action(&mut self, action: &str) -> Result<(), CoreError> {
        match action {
            "start" => {
                self.start_agent()?;
                self.set_status(self.t("agent.panel.started"));
            }
            "stop" => {
                self.stop_agent();
                self.set_status(self.t("agent.panel.stopped"));
            }
            "copy-token" => {
                let token = self
                    .agent
                    .as_ref()
                    .map(|agent| agent.bridge.token.clone())
                    .unwrap_or_default();
                self.copy_bridge_text(&token, "agent.copied.token");
            }
            "copy-endpoint" => {
                let endpoint = self
                    .agent
                    .as_ref()
                    .map(|agent| agent.bridge.endpoint(agent.permission.as_str()).to_string())
                    .unwrap_or_default();
                self.copy_bridge_text(&endpoint, "agent.copied.endpoint");
            }
            other => {
                if let Some(index) = other.strip_prefix("permission:") {
                    self.set_agent_permission(BridgePermission::from_index(
                        index.parse().unwrap_or(1),
                    ))?;
                    self.set_status(self.t("agent.permission.changed"));
                }
            }
        }
        Ok(())
    }

    fn copy_bridge_text(&mut self, text: &str, status_key: &str) {
        if text.is_empty() {
            return;
        }
        match arboard::Clipboard::new().and_then(|mut clipboard| clipboard.set_text(text)) {
            Ok(()) => {
                let message = self.t(status_key);
                self.set_status(message);
            }
            Err(error) => self.error(&CoreError::invalid(format!("clipboard: {error}"))),
        }
    }

    pub fn refresh_agent_panel(&self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let model = crate::AgentModel::get(&ui);
        model.set_can_start(self.can_agent());
        match &self.agent {
            Some(agent) => {
                model.set_running(true);
                model.set_host(ss("127.0.0.1"));
                model.set_port(agent.bridge.port as i32);
                model.set_permission(agent.permission.index());
                model.set_token(ss(&agent.bridge.token));
                model.set_endpoint(ss(format!("127.0.0.1:{}", agent.bridge.port)));
                model.set_status(ss(trf(
                    &self.lang,
                    "agent.panel.running",
                    &[
                        ("port", agent.bridge.port.to_string()),
                        ("permission", self.t(agent.permission.label_key())),
                    ],
                )));
            }
            None => {
                model.set_running(false);
                model.set_host(ss("127.0.0.1"));
                model.set_port(0);
                model.set_permission(self.pending_permission.index());
                model.set_token(ss(""));
                model.set_endpoint(ss(""));
                model.set_status(ss(self.t("agent.panel.idle")));
            }
        }
    }

    pub fn refresh_agent_status(&self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let text = match &self.agent {
            Some(agent) => trf(
                &self.lang,
                "agent.status.local",
                &[("port", agent.bridge.port.to_string())],
            ),
            None => self.t("agent.off"),
        };
        crate::AppModel::get(&ui).set_agent_text(ss(text));
    }

    /// Timer tick: execute queued requests against the live session.
    pub fn poll_agent(&mut self) {
        let Some(mut agent) = self.agent.take() else {
            return;
        };
        let Some(mut session) = self.session.take() else {
            self.agent = Some(agent);
            return;
        };
        let service = &mut agent.service;
        std::mem::swap(&mut service.session, &mut session);
        std::mem::swap(&mut service.project, &mut self.project);
        if let Some(project) = service.project.as_ref() {
            service.project_root = project.root.clone();
        } else {
            service.project_root = service.session.doc.root.clone();
        }
        service.source_path = Some(service.session.doc.path.clone());
        service.selection = self.selection.clone();
        service.sync_baseline();
        let responses = agent.bridge.drain(service);
        std::mem::swap(&mut service.session, &mut session);
        std::mem::swap(&mut service.project, &mut self.project);
        self.selection = service.selection.clone();
        self.session = Some(session);
        self.agent = Some(agent);
        if responses.is_empty() {
            return;
        }
        let rebind = responses.iter().any(|r| {
            r.pointer("/result/active_screen_changed") == Some(&Value::Bool(true))
                || r.pointer("/result/project_structure_changed") == Some(&Value::Bool(true))
        });
        for response in &responses {
            let summary = match response.get("error") {
                Some(error) => format!("AGENT_COMMAND error {error}"),
                None => format!(
                    "AGENT_COMMAND ok revision={}",
                    response
                        .pointer("/result/revision")
                        .cloned()
                        .unwrap_or(Value::Null)
                ),
            };
            self.log_event(summary);
        }
        if rebind {
            self.rebaseline();
            self.scan_project_files();
        }
        self.refresh_all();
        if let Some(ui) = self.ui.upgrade() {
            crate::AppModel::get(&ui).set_agent_text(ss(self.t("agent.connected")));
        }
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;
    use std::io::{BufRead, BufReader, Write};

    fn copy_dir(from: &std::path::Path, to: &std::path::Path) {
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

    fn app(name: &str) -> (App, std::path::PathBuf) {
        let root = std::env::temp_dir().join(format!("mono-agent-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let repo = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        copy_dir(&repo.join("test_assets/projects/curing_lite"), &root);
        let prefs = crate::prefs::Preferences::load_from(root.join("prefs.json"));
        let mut app = App::new(slint::Weak::default(), prefs);
        app.open_project(&root.join("project.oled.json")).unwrap();
        app.open_screen("main").unwrap();
        (app, root)
    }

    #[test]
    fn permission_change_restarts_with_new_token() {
        let (mut app, root) = app("permission");
        app.start_agent_with(BridgePermission::Edit).unwrap();
        let before = app.agent.as_ref().unwrap().bridge.token.clone();
        app.set_agent_permission(BridgePermission::Observe).unwrap();
        let agent = app.agent.as_ref().unwrap();
        assert_eq!(agent.permission, BridgePermission::Observe);
        assert_eq!(agent.service.permission, "observe");
        assert_ne!(agent.bridge.token, before);
        app.stop_agent();
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn stop_and_start_regenerates_token() {
        let (mut app, root) = app("restart");
        app.start_agent_with(BridgePermission::Edit).unwrap();
        let first = app.agent.as_ref().unwrap().bridge.token.clone();
        app.stop_agent();
        assert!(app.agent.is_none());
        app.start_agent_with(BridgePermission::Full).unwrap();
        let agent = app.agent.as_ref().unwrap();
        assert_ne!(agent.bridge.token, first);
        assert_eq!(agent.service.permission, "full");
        app.stop_agent();
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn endpoint_shape_unchanged() {
        let (mut app, root) = app("endpoint");
        app.start_agent_with(BridgePermission::Edit).unwrap();
        let agent = app.agent.as_ref().unwrap();
        let endpoint = agent.bridge.endpoint(agent.permission.as_str());
        assert_eq!(endpoint["host"], "127.0.0.1");
        assert!(endpoint["port"].as_u64().is_some_and(|port| port > 0));
        assert_eq!(endpoint["permission"], "edit");
        assert_eq!(endpoint["token"], agent.bridge.token);
        assert_eq!(
            endpoint["automation_api"],
            mono_automation::service::API_VERSION
        );
        app.stop_agent();
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn token_never_appears_in_log() {
        let (mut app, root) = app("log");
        app.start_agent_with(BridgePermission::Edit).unwrap();
        let first = app.agent.as_ref().unwrap().bridge.token.clone();
        app.set_agent_permission(BridgePermission::Observe).unwrap();
        let second = app.agent.as_ref().unwrap().bridge.token.clone();
        assert!(
            app.log
                .iter()
                .all(|line| !line.contains(&first) && !line.contains(&second))
        );
        app.stop_agent();
        let _ = std::fs::remove_dir_all(root);
    }
    #[test]
    fn agent_edits_the_live_designer_session_as_one_undo_step() {
        let root = std::env::temp_dir().join(format!("mono-agent-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let repo = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        copy_dir(&repo.join("test_assets/projects/curing_lite"), &root);
        let prefs = crate::prefs::Preferences::load_from(root.join("prefs.json"));
        let mut app = App::new(slint::Weak::default(), prefs);
        app.open_project(&root.join("project.oled.json")).unwrap();
        app.open_screen("main").unwrap();
        app.start_agent().unwrap();
        let (port, token) = {
            let agent = app.agent.as_ref().unwrap();
            (agent.bridge.port, agent.bridge.token.clone())
        };
        let client = std::thread::spawn(move || {
            let mut stream = std::net::TcpStream::connect(("127.0.0.1", port)).unwrap();
            let request = serde_json::json!({"jsonrpc": "2.0", "id": 7, "method": "scene.update_element",
                "params": {"id": "mode_label", "changes": {"x": 77}}, "token": token});
            stream
                .write_all(
                    format!(
                        "{request}
"
                    )
                    .as_bytes(),
                )
                .unwrap();
            let mut line = String::new();
            BufReader::new(stream).read_line(&mut line).unwrap();
            serde_json::from_str::<Value>(&line).unwrap()
        });
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
        while !client.is_finished() && std::time::Instant::now() < deadline {
            app.poll_agent();
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
        let response = client.join().unwrap();
        assert_eq!(response["result"]["changed_elements"][0], "mode_label");
        let session = app.session.as_mut().unwrap();
        let x = session.element("mode_label").unwrap()["x"].clone();
        assert_eq!(x, serde_json::json!(77));
        assert!(session.can_undo());
        session.undo();
        // The fixture's mode_label is zone-positioned (no `x`); undo restores that.
        assert!(session.element("mode_label").unwrap().get("x").is_none());
        app.stop_agent();
        assert!(app.agent.is_none());
        let _ = std::fs::remove_dir_all(&root);
    }
}
