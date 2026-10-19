//! Bitmap encoding (V1 `bitmap_encoding.py`): traversal, bit order, polarity and padding.

use serde::{Deserialize, Serialize};

use crate::bitmap::MonoBitmap;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BitAxis {
    Horizontal,
    Vertical,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum GroupOrder {
    RowMajor,
    ColumnMajor,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BitOrder {
    LsbFirst,
    MsbFirst,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Polarity {
    OneIsLit,
    ZeroIsLit,
}

/// Field order matches V1 `EncodingProfile.to_dict()`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields, default)]
pub struct EncodingProfile {
    pub bit_axis: BitAxis,
    pub group_order: GroupOrder,
    pub bit_order: BitOrder,
    pub polarity: Polarity,
}

impl Default for EncodingProfile {
    /// SSD1306 VLSB: vertical bytes, page rows, LSB at the top, 1 = lit.
    fn default() -> Self {
        Self {
            bit_axis: BitAxis::Vertical,
            group_order: GroupOrder::RowMajor,
            bit_order: BitOrder::LsbFirst,
            polarity: Polarity::OneIsLit,
        }
    }
}

/// One encoded byte and the source pixels it sampled; `None` marks padding.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TraceStep {
    pub index: usize,
    pub value: u8,
    pub coordinates: [Option<(usize, usize)>; 8],
    pub source_bits: [u8; 8],
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EncodedOutput {
    pub data: Vec<u8>,
    pub width: usize,
    pub height: usize,
    pub padded_size: (usize, usize),
    pub profile: EncodingProfile,
}

impl EncodedOutput {
    pub fn byte_count(&self) -> usize {
        self.data.len()
    }

    /// Recompute the sampling of byte `index` (identical to V1 `trace_step`).
    pub fn trace_step(&self, bitmap: &MonoBitmap, index: usize) -> Option<TraceStep> {
        if index >= self.data.len() {
            return None;
        }
        let coordinates = group_coordinates(bitmap.width(), bitmap.height(), &self.profile, index);
        let source_bits = coordinates.map(|c| c.map_or(0, |(x, y)| bitmap.get(x, y)));
        Some(TraceStep {
            index,
            value: self.data[index],
            coordinates,
            source_bits,
        })
    }
}

fn group_count(width: usize, height: usize, profile: &EncodingProfile) -> usize {
    match profile.bit_axis {
        BitAxis::Horizontal => width.div_ceil(8) * height,
        BitAxis::Vertical => height.div_ceil(8) * width,
    }
}

/// Coordinates of group `index` for the V1 traversal order.
fn group_coordinates(
    width: usize,
    height: usize,
    profile: &EncodingProfile,
    index: usize,
) -> [Option<(usize, usize)>; 8] {
    let mut out = [None; 8];
    match profile.bit_axis {
        BitAxis::Horizontal => {
            let blocks = width.div_ceil(8);
            let (block, y) = match profile.group_order {
                GroupOrder::RowMajor => (index % blocks, index / blocks),
                GroupOrder::ColumnMajor => (index / height, index % height),
            };
            for (bit, slot) in out.iter_mut().enumerate() {
                let x = block * 8 + bit;
                if x < width {
                    *slot = Some((x, y));
                }
            }
        }
        BitAxis::Vertical => {
            let blocks = height.div_ceil(8);
            let (x, block) = match profile.group_order {
                GroupOrder::ColumnMajor => (index / blocks, index % blocks),
                GroupOrder::RowMajor => (index % width, index / width),
            };
            for (bit, slot) in out.iter_mut().enumerate() {
                let y = block * 8 + bit;
                if y < height {
                    *slot = Some((x, y));
                }
            }
        }
    }
    out
}

/// Encode `bitmap`; padding bits are logical "off" before polarity is applied.
pub fn encode_bitmap(bitmap: &MonoBitmap, profile: &EncodingProfile) -> EncodedOutput {
    let (width, height) = (bitmap.width(), bitmap.height());
    let count = group_count(width, height, profile);
    let mut data = Vec::with_capacity(count);
    for index in 0..count {
        let coordinates = group_coordinates(width, height, profile, index);
        let mut value = 0u8;
        for (position, coordinate) in coordinates.iter().enumerate() {
            let source = coordinate.map_or(0, |(x, y)| bitmap.get(x, y));
            let encoded = match profile.polarity {
                Polarity::OneIsLit => source,
                Polarity::ZeroIsLit => 1 - source,
            };
            let shift = match profile.bit_order {
                BitOrder::MsbFirst => 7 - position,
                BitOrder::LsbFirst => position,
            };
            value |= encoded << shift;
        }
        data.push(value);
    }
    let padded_size = match profile.bit_axis {
        BitAxis::Horizontal => (width.div_ceil(8) * 8, height),
        BitAxis::Vertical => (width, height.div_ceil(8) * 8),
    };
    EncodedOutput {
        data,
        width,
        height,
        padded_size,
        profile: *profile,
    }
}
