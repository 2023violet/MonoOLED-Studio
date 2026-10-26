//! MonoOLED Studio headless core.
//!
//! Deterministic, synchronous and free of IO and UI dependencies. Every byte
//! this crate produces is checked against the frozen V1 golden corpus in
//! `fixtures/golden/`.

pub mod assets;
pub mod bitmap;
pub mod c_header;
pub mod diff;
pub mod encoding;
pub mod error;
pub mod font;
pub mod formatter;
pub mod framebuffer;
pub mod pixel;
pub mod profiles;
pub mod pyvalue;
pub mod raster;
pub mod render;
pub mod runtime;
pub mod state;

pub use bitmap::MonoBitmap;
pub use encoding::{
    BitAxis, BitOrder, EncodedOutput, EncodingProfile, GroupOrder, Polarity, TraceStep,
    encode_bitmap,
};
pub use error::{CoreError, CoreResult};
pub use framebuffer::FrameBuffer;
