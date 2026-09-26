#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BitAxis {
    Horizontal,
    Vertical,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GroupOrder {
    RowMajor,
    ColumnMajor,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BitOrder {
    MsbFirst,
    LsbFirst,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Polarity {
    OneIsLit,
    ZeroIsLit,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct EncodingProfile {
    pub bit_axis: BitAxis,
    pub group_order: GroupOrder,
    pub bit_order: BitOrder,
    pub polarity: Polarity,
}

impl Default for EncodingProfile {
    fn default() -> Self {
        Self {
            bit_axis: BitAxis::Vertical,
            group_order: GroupOrder::RowMajor,
            bit_order: BitOrder::LsbFirst,
            polarity: Polarity::OneIsLit,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MonoBitmap {
    pub width: usize,
    pub height: usize,
    pub rows: Vec<Vec<u8>>,
}

impl MonoBitmap {
    pub fn from_rows(rows: Vec<Vec<u8>>) -> Result<Self, String> {
        if rows.is_empty() || rows[0].is_empty() {
            return Err("monochrome bitmap must not be empty".into());
        }
        let width = rows[0].len();
        if rows.iter().any(|row| row.len() != width) {
            return Err("monochrome bitmap rows must have equal width".into());
        }
        if rows.iter().flatten().any(|value| *value > 1) {
            return Err("monochrome bitmap values must be 0 or 1".into());
        }
        Ok(Self {
            width,
            height: rows.len(),
            rows,
        })
    }

    pub fn row_strings(&self) -> Vec<String> {
        self.rows
            .iter()
            .map(|row| row.iter().map(|value| char::from(b'0' + *value)).collect())
            .collect()
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EncodedOutput {
    pub data: Vec<u8>,
    pub padded_size: (usize, usize),
}

pub fn encode_bitmap(bitmap: &MonoBitmap, profile: EncodingProfile) -> EncodedOutput {
    let groups = groups(bitmap.width, bitmap.height, profile);
    let mut data = Vec::with_capacity(groups.len());
    for coordinates in groups {
        let mut value = 0u8;
        for (position, coordinate) in coordinates.iter().enumerate() {
            let source_bit = coordinate.map(|(x, y)| bitmap.rows[y][x]).unwrap_or(0);
            let encoded_bit = match profile.polarity {
                Polarity::OneIsLit => source_bit,
                Polarity::ZeroIsLit => 1 - source_bit,
            };
            let shift = match profile.bit_order {
                BitOrder::MsbFirst => 7 - position,
                BitOrder::LsbFirst => position,
            };
            value |= encoded_bit << shift;
        }
        data.push(value);
    }
    let padded_size = match profile.bit_axis {
        BitAxis::Horizontal => (bitmap.width.div_ceil(8) * 8, bitmap.height),
        BitAxis::Vertical => (bitmap.width, bitmap.height.div_ceil(8) * 8),
    };
    EncodedOutput { data, padded_size }
}

fn groups(
    width: usize,
    height: usize,
    profile: EncodingProfile,
) -> Vec<Vec<Option<(usize, usize)>>> {
    let mut result = Vec::new();
    match profile.bit_axis {
        BitAxis::Horizontal => {
            let blocks = width.div_ceil(8);
            match profile.group_order {
                GroupOrder::RowMajor => {
                    for y in 0..height {
                        for block in 0..blocks {
                            result.push(
                                (0..8)
                                    .map(|bit| {
                                        let x = block * 8 + bit;
                                        (x < width).then_some((x, y))
                                    })
                                    .collect(),
                            );
                        }
                    }
                }
                GroupOrder::ColumnMajor => {
                    for block in 0..blocks {
                        for y in 0..height {
                            result.push(
                                (0..8)
                                    .map(|bit| {
                                        let x = block * 8 + bit;
                                        (x < width).then_some((x, y))
                                    })
                                    .collect(),
                            );
                        }
                    }
                }
            }
        }
        BitAxis::Vertical => {
            let blocks = height.div_ceil(8);
            match profile.group_order {
                GroupOrder::ColumnMajor => {
                    for x in 0..width {
                        for block in 0..blocks {
                            result.push(
                                (0..8)
                                    .map(|bit| {
                                        let y = block * 8 + bit;
                                        (y < height).then_some((x, y))
                                    })
                                    .collect(),
                            );
                        }
                    }
                }
                GroupOrder::RowMajor => {
                    for block in 0..blocks {
                        for x in 0..width {
                            result.push(
                                (0..8)
                                    .map(|bit| {
                                        let y = block * 8 + bit;
                                        (y < height).then_some((x, y))
                                    })
                                    .collect(),
                            );
                        }
                    }
                }
            }
        }
    }
    result
}
