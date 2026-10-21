# Build, Test and Release

## End users

Do not build locally. Download the package for your platform from **GitHub Releases** and check it against `SHA256SUMS`; see the [README](../README.md) for installation.

## Toolchain

- Rust is pinned in `rust-toolchain.toml` and installed by rustup on first use.
- Linux needs these development packages for the Slint desktop app:

```bash
sudo apt install libfontconfig1-dev libxkbcommon-dev libxkbcommon-x11-dev libwayland-dev libx11-dev libxcursor-dev libxrandr-dev libxi-dev libgl1-mesa-dev libegl1-mesa-dev
```

- Windows MSVC builds link the C runtime statically (`.cargo/config.toml`), so the binaries need no Visual C++ redistributable.
- Python 3 is used only by the packaging and tooling scripts in `tools/`. It is not a runtime dependency.

## Checks (what CI runs)

`.github/workflows/rust.yml` runs these checks on Windows, macOS and Linux for every push:

```bash
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
python -m pytest tools/tests -q
```

The same workflow also runs `cargo deny check` (licences, bans, sources, advisories; policy in `deny.toml`).

`cargo test` includes the golden-corpus parity tests. Byte-level outputs (VLSB, BIN, C headers, contracts) must match the corpus exactly, and PNG and ZIP outputs are compared by content. The corpus in `fixtures/golden/` is frozen 1.x output and is never regenerated to make a test pass. To regenerate it, check out the `v1-final` tag and use its `tools/EXPORT_GOLDEN_CORPUS.py`, then record why in the rewrite evidence.

## Performance measurements

```bash
cargo run --release -p mono-cli -- bench --project test_assets/projects/curing_lite/project.oled.json
cargo build --release -p mono-desktop
python tools/RUN_DESKTOP_BENCH.py --runs 3
```

- The first command measures the core budgets: encode+format, 50-screen exports and the durable-write baseline.
- `RUN_DESKTOP_BENCH.py` measures stroke latency, theme switch, cold start from process spawn, and idle memory in the real window.
- Budgets and the latest results are in `docs/rewrite/G4_EVIDENCE.md` §4.
- In debug builds, a UI-thread watchdog prints every block longer than 16 ms to stderr.

## Packaging

```bash
cargo build --release --locked -p mono-desktop -p mono-cli
python tools/PACKAGE_RUST_RELEASE.py
```

This writes the current platform's package and `SHA256SUMS` to `dist-rust/`.

| Platform | Package | Notes |
| --- | --- | --- |
| Windows | `MonoOLED-Studio-<ver>-windows-x64.zip` | Single folder with `monooled-studio.exe`, `mono.exe`, LICENSE and NOTICE. |
| macOS | `MonoOLED-Studio-<ver>-macos-arm64.dmg` | `.app` bundle with an ad-hoc signature. No Developer ID and not notarised. |
| Linux | `monooled-studio_<ver>_amd64.deb` | Installs to `/usr/lib/monooled-studio`, with links `/usr/bin/monooled-studio` and `/usr/bin/monooled-cli`. The `libc6` floor is computed from the binaries, and a CJK font is a dependency. |

The scripts only use each platform's own tools (`zipfile`, `hdiutil`, `codesign`, `dpkg-deb`, `objdump`); nothing is downloaded.

`.github/workflows/package.yml` builds and install-tests the packages on every relevant push to `main`:

- Windows installs from the zip; Linux installs the `.deb` in a clean `ubuntu:24.04` container; macOS installs from the dmg.
- Each installed program is version-checked, the installed CLI runs `validate` and `export`, and the installed desktop app takes screenshots with the software renderer and with the default renderer (Linux: software renderer only).
- `tools/CHECK_SMOKE_SCREENSHOT.py` rejects blank screenshots.
- The packages and screenshots are kept as workflow artifacts.

## Releasing

1. Set `[workspace.package] version` in `Cargo.toml` and add a `## <version> - <date>` section to `CHANGELOG.md`. Commit and let CI pass.
2. Optionally run the **Release (Rust V2)** workflow by hand (`workflow_dispatch`). This is a dry run: it does everything except create the release.
3. Push an annotated tag `v<version>`. `.github/workflows/release-rust.yml` then:
   - checks that the tag matches the workspace version and the changelog;
   - runs the package workflow;
   - creates a **draft** GitHub Release with the three packages, `SHA256SUMS` and the changelog section as notes.
4. A maintainer reviews the draft and publishes it by hand.

Published tags and release assets are immutable: never move a tag, force-push or replace assets with `--clobber`.
