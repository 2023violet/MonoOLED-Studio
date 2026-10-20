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

pub struct Agent {
    pub bridge: Bridge,
    pub service: Service,
}

impl App {
    /// Start the bridge on the live session; returns the started message.
    pub fn start_agent(&mut self) -> Result<String, CoreError> {
        let Some(session) = self.session.as_ref() else {
            return Err(CoreError::invalid(self.t("bench.no_project")));
        };
        let mut service = Service::new(session.doc.clone(), None, "edit")
            .map_err(|e| CoreError::invalid(e.message().to_string()))?;
        service.editor_attached = true;
        let bridge = Bridge::start(0).map_err(|e| CoreError::invalid(e.to_string()))?;
        let text = trf(
            &self.lang,
            "agent.bridge.started",
            &[
                ("host", "127.0.0.1".into()),
                ("port", bridge.port.to_string()),
                ("permission", "edit".into()),
                ("token", bridge.token.clone()),
            ],
        );
        self.log_event(format!("AGENT_BRIDGE on 127.0.0.1:{}", bridge.port));
        self.agent = Some(Agent { bridge, service });
        self.refresh_agent_status();
        Ok(text)
    }

    /// Tools → Agent Bridge (V1 `toggle_agent_bridge`).
    pub fn toggle_agent(&mut self) -> Result<(), CoreError> {
        if let Some(mut agent) = self.agent.take() {
            agent.bridge.stop();
            self.log_event("AGENT_BRIDGE off");
            self.refresh_agent_status();
            return Ok(());
        }
        let text = self.start_agent()?;
        rfd::MessageDialog::new()
            .set_title(self.t("agent.bridge.title"))
            .set_description(text)
            .set_buttons(rfd::MessageButtons::Ok)
            .show();
        Ok(())
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
        app.toggle_agent().unwrap();
        assert!(app.agent.is_none());
        let _ = std::fs::remove_dir_all(&root);
    }
}
