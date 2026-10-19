//! `mono` — MonoOLED Studio headless CLI (V1 `cli.py` command set).

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use mono_core::c_header::framebuffer_to_c_header;
use mono_core::render::render_scene;
use mono_core::runtime::SceneRuntime;
use mono_core::state::{
    IntegerPolicy, State, build_export_states, init_state, select_export_states,
};
use mono_core::{CoreError, CoreResult};
use mono_project::atomic::atomic_write;
use mono_project::export::{
    asset_health, build_handoff_package, check_design_rules, export_scene, matrix_report,
    validate_matrix, validate_scene,
};
use mono_project::project::ProjectWorkspace;
use mono_project::resources::DiskResources;
use mono_project::scene_io::{
    SceneDoc, SessionLogger, frame_evidence, load_project_scene, load_scene,
};
use serde_json::{Value, json};

const USAGE: &str = "mono — MonoOLED Studio canonical CLI

USAGE:
    mono <command> [options]

COMMANDS:
    validate         validate the current scene/state
    export           export one or more states (golden BIN, reference PNG, contract)
    simulate         run the UI-state timeline and stream JSONL evidence
    batch-validate   validate a state combination matrix
    handoff          build the deterministic Code AI handoff ZIP
    asset-audit      scan project asset health
    c-header         export the current framebuffer as a C header
    version          print the version

SOURCE OPTIONS (all commands):
    --scene <file.json>       scene file
    --project <project.oled.json>  project; takes precedence over --scene

STATE OPTIONS (validate, simulate, c-header):
    --mode <v> --phase <v> --seconds <n> --battery <n>

MATRIX OPTIONS (export, handoff):
    --states <all|i,j|name>   --integer-policy <representative|boundaries|full>
    --max-cases <n>           --allow-large-matrix
";

struct Args {
    values: BTreeMap<String, String>,
    flags: Vec<String>,
}

impl Args {
    fn parse(raw: &[String]) -> CoreResult<Self> {
        let mut values = BTreeMap::new();
        let mut flags = Vec::new();
        let mut i = 0;
        while i < raw.len() {
            let arg = &raw[i];
            let Some(name) = arg.strip_prefix("--") else {
                return Err(CoreError::invalid(format!("unexpected argument: {arg}")));
            };
            if let Some((key, value)) = name.split_once('=') {
                values.insert(key.to_string(), value.to_string());
            } else if name == "allow-large-matrix" {
                flags.push(name.to_string());
            } else {
                let value = raw
                    .get(i + 1)
                    .ok_or_else(|| CoreError::invalid(format!("--{name} requires a value")))?;
                values.insert(name.to_string(), value.clone());
                i += 1;
            }
            i += 1;
        }
        Ok(Self { values, flags })
    }

    fn get(&self, key: &str) -> Option<&str> {
        self.values.get(key).map(String::as_str)
    }

    fn flag(&self, key: &str) -> bool {
        self.flags.iter().any(|f| f == key)
    }

    fn int(&self, key: &str, default: i64) -> CoreResult<i64> {
        match self.get(key) {
            None => Ok(default),
            Some(v) => v
                .parse()
                .map_err(|_| CoreError::invalid(format!("--{key} must be an integer"))),
        }
    }
}

fn load(args: &Args) -> CoreResult<(Option<ProjectWorkspace>, SceneDoc)> {
    if let Some(project) = args.get("project").filter(|p| !p.is_empty()) {
        let project = ProjectWorkspace::load(Path::new(project))?;
        let scene = load_project_scene(&project, None)?;
        return Ok((Some(project), scene));
    }
    let scene = args
        .get("scene")
        .ok_or_else(|| CoreError::invalid("--scene or --project is required"))?;
    Ok((None, load_scene(Path::new(scene), None)?))
}

fn state_from_args(scene: &SceneDoc, args: &Args) -> CoreResult<State> {
    let mut state = init_state(&scene.data);
    for key in ["mode", "phase"] {
        if let Some(value) = args.get(key) {
            if state.contains_key(key) {
                state.insert(key.into(), json!(value));
            }
        }
    }
    for key in ["seconds", "battery"] {
        if args.get(key).is_some() && state.contains_key(key) {
            state.insert(key.into(), json!(args.int(key, 0)?));
        }
    }
    Ok(state)
}

fn policy(args: &Args, default: &str) -> CoreResult<IntegerPolicy> {
    IntegerPolicy::parse(args.get("integer-policy").unwrap_or(default))
}

fn matrix(scene: &SceneDoc, args: &Args, default_policy: &str) -> CoreResult<Vec<(String, State)>> {
    let states = build_export_states(
        &scene.data,
        policy(args, default_policy)?,
        args.int("max-cases", 5000)?.max(0) as usize,
        args.flag("allow-large-matrix"),
    )?;
    let tokens: Vec<String> = args
        .get("states")
        .unwrap_or("all")
        .split(',')
        .filter(|t| !t.trim().is_empty())
        .map(str::to_string)
        .collect();
    select_export_states(states, if tokens.is_empty() { &[] } else { &tokens }).or_else(|e| {
        if tokens.is_empty() {
            Ok(vec![])
        } else {
            Err(e)
        }
    })
}

fn print_findings(findings: &[mono_project::export::Finding]) {
    for f in findings {
        let suffix = f
            .element_id
            .as_ref()
            .map(|id| format!(" [{id}]"))
            .unwrap_or_default();
        println!("{} {}{suffix}: {}", f.severity, f.code, f.message);
    }
}

fn cmd_validate(args: &Args) -> CoreResult<u8> {
    let (_, scene) = load(args)?;
    let state = state_from_args(&scene, args)?;
    let mut findings = validate_scene(
        &scene.data,
        &scene.root,
        Some(&state),
        &mut DiskResources::new(),
    );
    findings.extend(check_design_rules(
        &scene.data,
        scene.data.get("_design_rules").unwrap_or(&json!({})),
    ));
    let blocking = findings.iter().filter(|f| f.is_blocking()).count();
    print_findings(&findings);
    println!(
        "{}: {blocking} blocking finding(s), {} total",
        if blocking == 0 { "PASS" } else { "FAIL" },
        findings.len()
    );
    Ok(u8::from(blocking > 0))
}

fn cmd_export(args: &Args) -> CoreResult<u8> {
    let (_, scene) = load(args)?;
    let states = matrix(&scene, args, "representative")?;
    let output = PathBuf::from(args.get("output").unwrap_or("exports/latest"));
    let summary = export_scene(
        &scene.data,
        &scene.root,
        &output,
        &states,
        &mut |_, _, _| true,
    )?;
    println!(
        "PASS: exported {} frame(s) to {}",
        summary.frame_count,
        summary.output_dir.display()
    );
    for (name, digest) in &summary.frame_hashes {
        println!("  {name}: {digest}");
    }
    Ok(0)
}

fn cmd_simulate(args: &Args) -> CoreResult<u8> {
    let (_, scene) = load(args)?;
    let log_path = PathBuf::from(args.get("log").unwrap_or("logs/session.jsonl"));
    let steps = args.int("steps", 10)?;
    let interval: f64 = args
        .get("interval")
        .unwrap_or("1.0")
        .parse()
        .map_err(|_| CoreError::invalid("--interval must be a number"))?;
    let mut logger = SessionLogger::new(&log_path)?;
    let mut frames = Vec::new();
    {
        let mut runtime = SceneRuntime::new(&scene.data, Some(&mut logger))?;
        let overrides = state_from_args(&scene, args)?;
        for key in ["mode", "phase", "seconds", "battery"] {
            if args.get(key).is_some() && runtime.state.contains_key(key) {
                runtime.set_state(key, overrides[key].clone())?;
            }
        }
        let mut resources = DiskResources::new();
        for step in 0..=steps.max(0) {
            if step > 0 {
                if interval > 0.0 {
                    std::thread::sleep(std::time::Duration::from_secs_f64(interval));
                }
                runtime.step(&json!(1))?;
            }
            let result = render_scene(&scene.data, &scene.root, &runtime.state, &mut resources)?;
            frames.push(frame_evidence(
                &result,
                &runtime.state,
                runtime.elapsed,
                &scene.root,
            )?);
        }
    }
    for payload in frames {
        let fields: Vec<String> = ["mode", "phase", "seconds", "battery"]
            .iter()
            .filter_map(|k| {
                payload["state"]
                    .get(*k)
                    .map(|v| format!("{k}={}", mono_core::pyvalue::py_str(v)))
            })
            .collect();
        println!(
            "t={:04} {} sha256={}",
            payload["elapsed"].as_i64().unwrap_or(0),
            fields.join(" "),
            payload["sha256"].as_str().unwrap_or("")
        );
        if let Value::Object(map) = payload {
            logger.log("FRAME", map);
        }
    }
    logger.write_markdown(&log_path.with_extension("md"))?;
    println!("PASS: session log -> {}", log_path.display());
    Ok(0)
}

fn cmd_batch_validate(args: &Args) -> CoreResult<u8> {
    let (_, scene) = load(args)?;
    let states = build_export_states(
        &scene.data,
        policy(args, "boundaries")?,
        args.int("max-cases", 5000)?.max(0) as usize,
        args.flag("allow-large-matrix"),
    )?;
    let matrix: Vec<State> = states.into_iter().map(|(_, s)| s).collect();
    let summary = validate_matrix(&scene.data, &scene.root, &matrix, &mut |_, _, _| true)?;
    let target = PathBuf::from(args.get("output").unwrap_or("reports/batch_validation.md"));
    let mut report = matrix_report(&summary);
    let rules = check_design_rules(
        &scene.data,
        scene.data.get("_design_rules").unwrap_or(&json!({})),
    );
    if !rules.is_empty() {
        report.push_str("\n## Project Design Rules\n\n");
        for f in &rules {
            report.push_str(&format!("- **{}/{}**: {}\n", f.severity, f.code, f.message));
        }
    }
    atomic_write(&target, report.as_bytes())?;
    let blockers = summary.blockers + rules.iter().filter(|f| f.is_blocking()).count();
    println!(
        "{}: {} cases, {} findings, {blockers} blockers -> {}",
        if blockers == 0 { "PASS" } else { "FAIL" },
        summary.cases,
        summary.findings + rules.len(),
        target.display()
    );
    Ok(u8::from(blockers > 0))
}

fn cmd_handoff(args: &Args) -> CoreResult<u8> {
    let (_, scene) = load(args)?;
    let states = matrix(&scene, args, "representative")?;
    let output = PathBuf::from(
        args.get("output")
            .unwrap_or("exports/OLED_Code_AI_Handoff.zip"),
    );
    let summary = build_handoff_package(
        &scene.data,
        &scene.root,
        &output,
        &states,
        policy(args, "representative")?,
        &mut |_, _, _| true,
    )?;
    println!(
        "PASS: handoff {} frame(s) -> {}",
        summary.frame_count,
        output.display()
    );
    Ok(0)
}

fn cmd_asset_audit(args: &Args) -> CoreResult<u8> {
    let (project, scene) = load(args)?;
    let dirs = match project {
        Some(p) => p.asset_dirs(),
        None => scene
            .data
            .get("_asset_dirs")
            .and_then(Value::as_array)
            .map(|a| a.iter().map(mono_core::pyvalue::py_str).collect())
            .unwrap_or_else(|| vec!["assets".into()]),
    };
    let health = asset_health(&scene.root, &dirs, &Default::default())?;
    println!("Duplicate groups: {}", health.duplicates.len());
    println!(
        "Unused (without state usage input): {}",
        health.unused.len()
    );
    println!("Invalid: {}", health.invalid.len());
    for (path, error) in &health.invalid {
        println!("INVALID {path}: {error}");
    }
    Ok(u8::from(!health.invalid.is_empty()))
}

fn cmd_c_header(args: &Args) -> CoreResult<u8> {
    let (_, scene) = load(args)?;
    let state = state_from_args(&scene, args)?;
    let result = render_scene(&scene.data, &scene.root, &state, &mut DiskResources::new())?;
    let output = PathBuf::from(
        args.get("output")
            .ok_or_else(|| CoreError::invalid("--output is required"))?,
    );
    atomic_write(
        &output,
        framebuffer_to_c_header(
            &result.framebuffer,
            args.get("name").unwrap_or("oled_frame"),
        )?
        .as_bytes(),
    )?;
    println!("PASS: C header -> {}", output.display());
    Ok(0)
}

fn run(raw: &[String]) -> CoreResult<u8> {
    let Some((command, rest)) = raw.split_first() else {
        print!("{USAGE}");
        return Ok(2);
    };
    if command == "-h" || command == "--help" || command == "help" {
        print!("{USAGE}");
        return Ok(0);
    }
    if command == "version" || command == "--version" {
        println!("mono {}", env!("CARGO_PKG_VERSION"));
        return Ok(0);
    }
    let args = Args::parse(rest)?;
    match command.as_str() {
        "validate" => cmd_validate(&args),
        "export" => cmd_export(&args),
        "simulate" => cmd_simulate(&args),
        "batch-validate" => cmd_batch_validate(&args),
        "handoff" => cmd_handoff(&args),
        "asset-audit" => cmd_asset_audit(&args),
        "c-header" => cmd_c_header(&args),
        other => Err(CoreError::invalid(format!(
            "unknown command: {other}\n\n{USAGE}"
        ))),
    }
}

fn main() -> ExitCode {
    let raw: Vec<String> = std::env::args().skip(1).collect();
    match run(&raw) {
        Ok(code) => ExitCode::from(code),
        Err(error) => {
            if error.code == mono_project::export::EXPORT_BLOCKED {
                eprintln!("FAIL: {}", error.message);
            } else {
                eprintln!("ERROR: {}", error.message);
            }
            ExitCode::from(2)
        }
    }
}
