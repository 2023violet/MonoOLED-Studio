# MonoOLED Studio — Code AI Handoff Contract v7.1

Machine truth is **Project Workspace + Scene JSON**. Pixel truth is the **Canonical Renderer framebuffer**. GUI overlays and Pixel Studio editing tools never become an alternate rendering contract.

A deterministic handoff ZIP contains the human-readable UI specification, machine JSON contract, asset manifest, reference PNGs, Golden VLSB BIN files and validation evidence. Firmware should be accepted by byte comparison against Golden output rather than visual approximation.

Pixel Studio may produce PNG, VLSB BIN, C Header and glyph resources; once an asset is bound into a Scene, its production behavior is still governed by the same Scene/Renderer/Validation path.
