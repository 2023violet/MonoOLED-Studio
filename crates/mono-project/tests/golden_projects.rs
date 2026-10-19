#![allow(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::type_complexity
)]

mod common;

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use common::{Report, cases, hex};
use mono_core::profiles::{builtin_profile, validate_profile_id};
use mono_core::render::posix;
use mono_core::{CoreError, CoreResult};
use mono_project::project::{
    ProjectWorkspace, create_project, py_resolve, resolve_under_root, validate_screen_id,
};
use serde_json::{Map, Value, json};

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

fn class(error: &CoreError) -> &'static str {
    match error.code {
        "E-PROJ-PATH" => "InvalidProjectPath",
        "E-PROJ-EXTERNAL" => "ExternalProjectModificationError",
        "E-CORE-KEY" => "KeyError",
        "E-CORE-TYPE" => "TypeError",
        "E-IO-EXISTS" => "FileExistsError",
        _ => "ValueError",
    }
}

fn replace_root(text: &str, root: &Path) -> String {
    let root = py_resolve(root);
    let mut out = text
        .replace(&posix(&root), "${PROJECT_ROOT}")
        .replace(&root.display().to_string(), "${PROJECT_ROOT}");
    if let Some(i) = out.find("${PROJECT_ROOT}") {
        let (head, tail) = out.split_at(i);
        out = format!("{head}{}", tail.replace('\\', "/"));
    }
    out
}

fn error_value(error: &CoreError, root: &Path) -> Value {
    json!({"error": class(error), "message": replace_root(&error.message, root)})
}

fn snapshot(root: &Path) -> Value {
    let mut files = BTreeMap::new();
    fn walk(dir: &Path, root: &Path, files: &mut BTreeMap<String, String>) {
        let mut entries: Vec<_> = std::fs::read_dir(dir)
            .unwrap()
            .flatten()
            .map(|e| e.path())
            .collect();
        entries.sort();
        for path in entries {
            if path.is_dir() {
                walk(&path, root, files);
            } else if path.extension().is_some_and(|e| e == "json") {
                files.insert(
                    posix(path.strip_prefix(root).unwrap()),
                    hex(&std::fs::read(&path).unwrap()),
                );
            }
        }
    }
    walk(root, root, &mut files);
    Value::Object(files.into_iter().map(|(k, v)| (k, json!(v))).collect())
}

fn expected_files(value: &Value) -> Value {
    Value::Object(
        value
            .as_object()
            .unwrap()
            .iter()
            .map(|(k, v)| (k.clone(), v["hex"].clone()))
            .collect(),
    )
}

fn profiles_summary(project: &ProjectWorkspace) -> Value {
    let (active, profiles) = project.output_profiles().unwrap();
    let map: Map<String, Value> = profiles
        .into_iter()
        .map(|(id, p)| (id, p.to_json()))
        .collect();
    json!({"active": active, "profiles": map})
}

fn copy_dir(from: &Path, to: &Path) {
    std::fs::create_dir_all(to).unwrap();
    for entry in std::fs::read_dir(from).unwrap().flatten() {
        let target = to.join(entry.file_name());
        if entry.path().is_dir() {
            copy_dir(&entry.path(), &target);
        } else {
            std::fs::copy(entry.path(), target).unwrap();
        }
    }
}

fn temp(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "mono-golden-projects-{}-{name}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn outcome<T>(result: CoreResult<T>, root: &Path, ok: impl FnOnce(T) -> Value) -> Value {
    match result {
        Ok(value) => ok(value),
        Err(error) => error_value(&error, root),
    }
}

#[test]
fn project_cases_match_v1() {
    let repo = repo();
    let all: BTreeMap<String, Value> = cases("projects")
        .into_iter()
        .map(|c| (c["id"].as_str().unwrap().to_string(), c))
        .collect();
    let mut got: BTreeMap<String, Value> = BTreeMap::new();

    // Round-trip of the frozen curing_lite project.
    let work = temp("roundtrip");
    copy_dir(
        &repo.join("test_assets/projects/curing_lite"),
        &work.join("curing_lite"),
    );
    let manifest = work.join("curing_lite/project.oled.json");
    let before = std::fs::read(&manifest).unwrap();
    let mut project = ProjectWorkspace::load(&manifest).unwrap();
    got.insert(
        "project-curing_lite-open".into(),
        json!({"source": hex(&before), "name": project.name(), "active": project.active_screen(),
               "screens": project.screens().iter().map(|s| json!({"id": s.id, "label": s.label, "path": s.path})).collect::<Vec<_>>(),
               "asset_dirs": project.asset_dirs(), "output": profiles_summary(&project),
               "unchanged": std::fs::read(&manifest).unwrap() == before}),
    );
    project.save().unwrap();
    got.insert(
        "project-curing_lite-save".into(),
        json!(hex(&std::fs::read(&manifest).unwrap())),
    );

    // create_project + operation sequence.
    let root = temp("create").join("golden");
    let mut project = create_project(&root, "Golden", (128, 32)).unwrap();
    got.insert("project-create-golden-128x32".into(), snapshot(&root));
    let row = builtin_profile("row_msb_c51").unwrap();
    let steps: Vec<(&str, Box<dyn Fn(&mut ProjectWorkspace) -> CoreResult<()>>)> = vec![
        (
            "upsert-profile",
            Box::new(move |p| p.upsert_output_profile("my_row", &row, true)),
        ),
        (
            "set-active-profile",
            Box::new(|p| p.set_active_output_profile("ssd1306_vlsb_c")),
        ),
        (
            "delete-profile",
            Box::new(|p| p.delete_output_profile("my_row")),
        ),
        (
            "add-screen",
            Box::new(|p| {
                p.add_screen("status", Some("Status"), None, Some((128, 64)))
                    .map(|_| ())
            }),
        ),
        (
            "duplicate-screen",
            Box::new(|p| {
                p.duplicate_screen("status", "status_copy", Some("Copy"))
                    .map(|_| ())
            }),
        ),
        (
            "rename-screen",
            Box::new(|p| {
                p.rename_screen("status_copy", "renamed", Some("Renamed"))
                    .map(|_| ())
            }),
        ),
        (
            "remove-screen",
            Box::new(|p| p.remove_screen("renamed", true)),
        ),
    ];
    for (label, action) in steps {
        action(&mut project).unwrap();
        project.save().unwrap();
        got.insert(
            format!("project-op-{label}"),
            json!({"files": snapshot(&root), "output": profiles_summary(&project)}),
        );
    }
    let manifest = root.join("project.oled.json");
    let edited = String::from_utf8(std::fs::read(&manifest).unwrap())
        .unwrap()
        .replace("\"Golden\"", "\"Edited\"");
    std::fs::write(&manifest, edited).unwrap();
    got.insert(
        "project-save-rejects-external-modification".into(),
        error_value(&project.save().unwrap_err(), &root),
    );
    got.insert(
        "project-add-screen-rejects-case-collision".into(),
        error_value(
            &project.add_screen("STATUS", None, None, None).unwrap_err(),
            &root,
        ),
    );

    // Legacy project without output_workbench.
    let root = temp("legacy").join("legacy");
    create_project(&root, "Legacy", (128, 32)).unwrap();
    let manifest = root.join("project.oled.json");
    let mut data: Map<String, Value> =
        serde_json::from_slice(&std::fs::read(&manifest).unwrap()).unwrap();
    data.shift_remove("output_workbench");
    std::fs::write(
        &manifest,
        format!(
            "{}\n",
            mono_project::atomic::python_json(&Value::Object(data)).unwrap()
        ),
    )
    .unwrap();
    let before = std::fs::read(&manifest).unwrap();
    let project = ProjectWorkspace::load(&manifest).unwrap();
    got.insert("project-legacy-open-no-output-workbench".into(),
        json!({"source": hex(&before), "rewritten": std::fs::read(&manifest).unwrap() != before, "output": profiles_summary(&project)}));

    let mut report = Report::default();
    let check =
        |report: &mut Report, id: &str, ok: bool, detail: String| report.check(id, ok, || detail);

    // Compare the stateful sequences.
    let e = &all["project-curing_lite-open"]["expected"];
    let g = &got["project-curing_lite-open"];
    check(
        &mut report,
        "project-curing_lite-open",
        e["source"]["hex"] == g["source"]
            && e["loaded"]["name"] == g["name"]
            && e["loaded"]["active_screen"] == g["active"]
            && e["loaded"]["screens"] == g["screens"]
            && e["loaded"]["asset_dirs"] == g["asset_dirs"]
            && e["loaded"]["output"] == g["output"]
            && e["loaded"]["manifest_unchanged_after_open"] == g["unchanged"],
        format!("{g}"),
    );
    check(
        &mut report,
        "project-curing_lite-save",
        all["project-curing_lite-save"]["expected"]["saved"]["hex"]
            == got["project-curing_lite-save"],
        "save bytes".into(),
    );
    check(
        &mut report,
        "project-create-golden-128x32",
        expected_files(&all["project-create-golden-128x32"]["expected"]["files"])
            == got["project-create-golden-128x32"],
        format!("{}", got["project-create-golden-128x32"]),
    );
    for label in [
        "upsert-profile",
        "set-active-profile",
        "delete-profile",
        "add-screen",
        "duplicate-screen",
        "rename-screen",
        "remove-screen",
    ] {
        let id = format!("project-op-{label}");
        let e = &all[&id]["expected"];
        let g = &got[&id];
        check(
            &mut report,
            &id,
            expected_files(&e["files"]) == g["files"] && e["output"] == g["output"],
            format!("{g}"),
        );
    }
    for id in [
        "project-save-rejects-external-modification",
        "project-add-screen-rejects-case-collision",
    ] {
        check(
            &mut report,
            id,
            all[id]["expected"] == got[id],
            format!("{}", got[id]),
        );
    }
    let e = &all["project-legacy-open-no-output-workbench"];
    check(
        &mut report,
        "project-legacy-open-no-output-workbench",
        e["input"]["source"]["hex"] == got["project-legacy-open-no-output-workbench"]["source"]
            && e["expected"]["rewritten"]
                == got["project-legacy-open-no-output-workbench"]["rewritten"]
            && e["expected"]["output"] == got["project-legacy-open-no-output-workbench"]["output"],
        format!("{}", got["project-legacy-open-no-output-workbench"]),
    );

    // Stateless rejection / load cases driven entirely by their recorded input.
    let reject_root = temp("reject").join("reject");
    std::fs::create_dir_all(&reject_root).unwrap();
    let work = reject_root.parent().unwrap().to_path_buf();
    for (id, case) in &all {
        let input = &case["input"];
        let expected = &case["expected"];
        let value = if id.starts_with("path-reject-") {
            let member = input["member"]
                .as_str()
                .unwrap()
                .replace("${PROJECT_ROOT}", &posix(&py_resolve(&work)));
            outcome(
                resolve_under_root(&reject_root, &member, "project path"),
                &work,
                |_| json!({"accepted": true}),
            )
        } else if id.starts_with("screen-id-") {
            outcome(
                validate_screen_id(input["screen_id"].as_str().unwrap()),
                &work,
                |v| json!({"accepted": v}),
            )
        } else if id.starts_with("profile-id-") {
            outcome(
                validate_profile_id(input["profile_id"].as_str().unwrap()),
                &work,
                |v| json!({"accepted": v}),
            )
        } else if id.starts_with("project-load-") {
            let root = temp(id);
            std::fs::create_dir_all(root.join("scenes")).unwrap();
            let manifest = root.join("project.oled.json");
            std::fs::write(
                &manifest,
                format!(
                    "{}\n",
                    mono_project::atomic::python_json(&input["manifest"]).unwrap()
                ),
            )
            .unwrap();
            outcome(
                ProjectWorkspace::load(&manifest),
                &root,
                |p| json!({"loaded": true, "screens": p.screens().iter().map(|s| json!({"id": s.id, "label": s.label, "path": s.path})).collect::<Vec<_>>(), "output": profiles_summary(&p)}),
            )
        } else {
            continue;
        };
        report.check(id, value == *expected, || {
            format!("got {value} want {expected}")
        });
    }

    // Mutation and rollback sequence.
    let root = temp("mutate").join("mutate");
    let mut project = create_project(&root, "Mutate", (128, 32)).unwrap();
    let source = root.join("scenes/main.json");
    project
        .add_screen("second", Some("Second"), Some(&source), None)
        .unwrap();
    project.save().unwrap();
    let id = "project-op-add-screen-from-source";
    report.check(
        id,
        expected_files(&all[id]["expected"]["files"]) == snapshot(&root),
        || "files".into(),
    );
    let mut attempt =
        |label: &str,
         project: &mut ProjectWorkspace,
         action: &dyn Fn(&mut ProjectWorkspace) -> CoreResult<()>| {
            let before = serde_json::to_string(&project.data).unwrap();
            let mut value = outcome(action(project), &root, |()| json!({"ok": true}));
            let unchanged = serde_json::to_string(&project.data).unwrap() == before;
            let map = value.as_object_mut().unwrap();
            map.insert("data_unchanged".into(), json!(unchanged));
            let id = format!("project-op-{label}");
            let expected = &all[&id]["expected"];
            let ok = expected["data_unchanged"] == value["data_unchanged"]
                && expected.get("error") == value.get("error")
                && expected.get("message") == value.get("message")
                && expected_files(&expected["files"]) == snapshot(&root);
            report.check(&id, ok, || format!("got {value} want {expected}"));
        };
    attempt("set-active-screen-unknown", &mut project, &|p| {
        p.set_active_screen("ghost")
    });
    attempt("get-profile-unknown", &mut project, &|p| {
        p.set_active_output_profile("ghost")
    });
    attempt("delete-last-profile", &mut project, &|p| {
        p.delete_output_profile("ssd1306_vlsb_c")
    });
    attempt("set-asset-dirs", &mut project, &|p| {
        p.set_asset_dirs(&["assets".into(), "art".into()])
    });
    attempt("set-asset-dirs-escape", &mut project, &|p| {
        p.set_asset_dirs(&["../x".into()])
    });
    attempt("remove-screen-keep-file", &mut project, &|p| {
        p.remove_screen("second", false)
    });
    attempt("remove-last-screen", &mut project, &|p| {
        p.remove_screen("main", true)
    });
    let manifest = root.join("project.oled.json");
    let edited = String::from_utf8(std::fs::read(&manifest).unwrap())
        .unwrap()
        .replace("\"Mutate\"", "\"External\"");
    std::fs::write(&manifest, edited).unwrap();
    let raw = builtin_profile("raw_hex").unwrap();
    attempt("rollback-upsert-profile", &mut project, &move |p| {
        p.upsert_output_profile("rolled", &raw, true)
    });
    attempt("rollback-set-asset-dirs", &mut project, &|p| {
        p.set_asset_dirs(&["assets".into(), "other".into()])
    });
    attempt("rollback-add-screen", &mut project, &|p| {
        p.add_screen("third", None, None, None).map(|_| ())
    });
    attempt("rollback-rename-screen", &mut project, &|p| {
        p.rename_screen("main", "renamed", None).map(|_| ())
    });

    report.finish_exact("projects", common::count_cases("projects", |_| true));
}
