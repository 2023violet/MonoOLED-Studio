use crate::bitmap::{
    BitAxis, BitOrder, EncodingProfile, GroupOrder, MonoBitmap, Polarity, encode_bitmap,
};

pub fn sanitize_symbol(value: &str) -> String {
    let mut result = String::new();
    let mut pending_separator = false;
    for ch in value.chars() {
        if ch.is_ascii_alphanumeric() || ch == '_' {
            if pending_separator && !result.is_empty() {
                result.push('_');
            }
            result.push(ch);
            pending_separator = false;
        } else {
            pending_separator = true;
        }
    }
    if result.is_empty() {
        result = "oled_bitmap".into();
    }
    if result.chars().next().is_some_and(|ch| ch.is_ascii_digit()) {
        result = format!("bitmap_{result}");
    }
    result
}

pub fn legacy_pixel_c_export(
    bitmap: &MonoBitmap,
    symbol: &str,
) -> Result<(Vec<u8>, String), String> {
    let encoded = encode_bitmap(
        bitmap,
        EncodingProfile {
            bit_axis: BitAxis::Vertical,
            group_order: GroupOrder::RowMajor,
            bit_order: BitOrder::LsbFirst,
            polarity: Polarity::OneIsLit,
        },
    );
    let symbol = sanitize_symbol(symbol);
    let mut text = format!(
        "#define {symbol}_WIDTH {}\n#define {symbol}_HEIGHT {}\n#define {symbol}_BYTES {}\n\nstatic const unsigned char {symbol}[] = {{\n",
        bitmap.width,
        bitmap.height,
        encoded.data.len()
    );
    let values = encoded
        .data
        .iter()
        .map(|byte| format!("0x{byte:02X},"))
        .collect::<Vec<_>>();
    text.push_str("    ");
    text.push_str(&values.join(" "));
    text.push_str("\n};\n");
    Ok((encoded.data, text))
}
