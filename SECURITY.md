# Security Policy

## Supported versions

Security updates are provided for the latest published release on GitHub
Releases (currently `v1.1.0`). Older versions may not receive fixes.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, report them privately. We aim to acknowledge reports and publish a
fix before public disclosure. Include as much detail as possible:

- The MonoOLED Studio version and Windows version.
- A description of the vulnerability and its impact.
- Steps to reproduce.
- Any proof-of-concept or suggested fix.

## Scope

MonoOLED Studio is a desktop authoring tool. Security reports are most
relevant for:

- Project/scene file parsing (untrusted `.oled.json`, imported bitmaps, fonts).
- The local automation API bridge that listens on localhost.
- Anything that executes code from, or writes outside of, the active project.

Please avoid reporting general usability issues here; use the issue tracker
instead.
