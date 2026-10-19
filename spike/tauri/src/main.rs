//! G2 spike (throwaway): self-driving Tauri 2 benchmark for MonoOLED stress scenarios.

use std::sync::OnceLock;

static OUT: OnceLock<String> = OnceLock::new();

/// Private bytes of this process plus its WebView child processes (Windows).
fn tree_private_bytes() -> u64 {
    let pid = std::process::id();
    let script = format!(
        "$all=Get-CimInstance Win32_Process; $ids=@({pid}); do {{ $n=$ids.Count; $ids=@($all | Where-Object {{ $ids -contains $_.ProcessId -or $ids -contains $_.ParentProcessId }} | ForEach-Object ProcessId | Sort-Object -Unique) }} while ($ids.Count -ne $n); ($all | Where-Object {{ $ids -contains $_.ProcessId }} | Measure-Object -Property PrivatePageCount -Sum).Sum"
    );
    std::process::Command::new("powershell")
        .args(["-NoProfile", "-Command", &script])
        .output()
        .ok()
        .and_then(|o| String::from_utf8_lossy(&o.stdout).trim().parse::<u64>().ok())
        .unwrap_or(0)
}

#[tauri::command]
fn idle_memory() -> u64 {
    tree_private_bytes()
}

#[tauri::command]
fn report(app: tauri::AppHandle, json: String) {
    let path = OUT.get().cloned().unwrap_or_else(|| "tauri-report.json".into());
    let _ = std::fs::write(path, format!("{json}\n"));
    app.exit(0);
}

fn main() {
    let _ = OUT.set(std::env::args().nth(1).unwrap_or_else(|| "tauri-report.json".into()));
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![idle_memory, report])
        .run(tauri::generate_context!())
        .expect("tauri");
}
