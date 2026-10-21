# Contributing to MonoOLED Studio

Thanks for taking the time to contribute! MonoOLED Studio is a cross-platform
(Windows, macOS, Linux) 1-bit OLED scene, pixel and font authoring workbench
written in Rust with a Slint user interface.

## Getting started

1. Fork the repository and clone it.
2. Create a feature branch: `git checkout -b feat/my-change`.
3. Install Rust with [rustup](https://rustup.rs). The pinned toolchain in
   `rust-toolchain.toml` is installed automatically on first build.
4. On Linux, install the desktop development packages:

```bash
sudo apt install libfontconfig1-dev libxkbcommon-dev libxkbcommon-x11-dev libwayland-dev libx11-dev libxcursor-dev libxrandr-dev libxi-dev libgl1-mesa-dev libegl1-mesa-dev
```

5. Run the checks before and after your change (the same ones CI runs):

```bash
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
python -m pytest tools/tests -q
```

`cargo deny check` enforces the dependency licence and advisory policy in
`deny.toml`.

## Making changes

- Keep changes focused; one logical change per commit.
- Match the existing code style and naming conventions.
- Do not add comments unless they clarify intent the code cannot.
- Update the relevant tests when you change behaviour. Behaviour that the
  golden corpus covers (`fixtures/golden/`) must keep matching it; the corpus
  is frozen output of the 1.x line and is not regenerated to make a test pass.
- Project files, preferences and the Automation API are compatibility
  contracts. Changing them needs a new version, method, profile or schema,
  not a silent change.
- Do not commit build artifacts (`target/`, `dist-rust/`) or runtime state
  (`.oled/`).

## Running the app

```bash
cargo run -p mono-desktop -- path/to/project.oled.json
cargo run -p mono-cli -- validate --project path/to/project.oled.json
```

## Packaging (maintainers)

```bash
cargo build --release -p mono-desktop -p mono-cli
python tools/PACKAGE_RUST_RELEASE.py
```

See [docs/BUILD.md](docs/BUILD.md). End users download packages from GitHub
Releases; do not commit binaries.

## Reporting issues

Open a GitHub issue and include:

- The MonoOLED Studio version (`monooled-studio --version`) and your operating
  system.
- Steps to reproduce.
- Expected vs. actual behaviour.
- Screenshots or the relevant `mono validate` / `mono export` output.

## Code of conduct

Please be respectful and constructive. Harassment or abusive behaviour will
not be tolerated.
