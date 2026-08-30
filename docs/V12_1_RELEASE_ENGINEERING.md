# V12.1 Release Engineering Closure

V12.1 separates product development, certification, and end-user distribution.

- **CI:** fast source verification for pushes and pull requests.
- **Quick Build:** developer convenience path for producing a local EXE without GA certification.
- **GA Build:** native Windows source, Real-Qt/DPI, executable smoke and soak certification.
- **Release:** semver tag → Windows GA → deterministic named Windows ZIP + SHA-256 → GitHub Release.
- **End-user contract:** download, extract, double-click `MonoOLEDStudio.exe`; no Python and no BAT execution.

The application remains an onedir PyInstaller distribution. The complete `MonoOLEDStudio` directory is the application unit; copying only the EXE away from its bundled runtime is unsupported.
