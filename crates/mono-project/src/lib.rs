//! MonoOLED Studio project persistence and filesystem boundary.
//!
//! Everything that touches disk lives here: PNG decoding, Font Pack files,
//! project manifests and atomic writes. `mono-core` stays IO-free.

pub mod asset_ops;
pub mod atomic;
pub mod autosave;
pub mod editor;
pub mod export;
pub mod fontpack_io;
pub mod image_io;
pub mod project;
pub mod resources;
pub mod review;
pub mod review_pack;
pub mod scene_io;
pub mod templates;
