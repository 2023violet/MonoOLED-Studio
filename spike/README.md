# G2 UI framework spike (throwaway)

Not product code. Each spike is a self-driving benchmark that opens a real window
and measures the three MonoOLED stress scenarios from the rewrite spec (G2):

1. 256x128 Pixel canvas at zoom 8: stroke latency from input to presented frame.
2. 256 KiB generated-code text preview: time to first presented frame.
3. Scene with 50 elements dragged together: per-move latency.

Run (outside the main workspace; build output goes to the target dir you choose):

    cargo run --release --manifest-path spike/slint/Cargo.toml -- report.json
    cargo run --release --manifest-path spike/tauri/Cargo.toml -- report.json

Results and the decision live in docs/rewrite/G2_EVIDENCE.md.
