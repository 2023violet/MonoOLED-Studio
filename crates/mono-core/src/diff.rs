//! Pixel-diff helpers shared by the desktop Review workspace and the
//! Automation `render.pixel_diff` method.

/// Pixel bounds of a change, half-open (`x + w`, `y + h`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DiffBox {
    pub x: usize,
    pub y: usize,
    pub w: usize,
    pub h: usize,
}

/// Number of differing pixels; a length mismatch counts as a change per extra
/// byte so a resized buffer can never look identical.
pub fn changed_count(a: &[u8], b: &[u8]) -> usize {
    a.iter()
        .zip(b)
        .filter(|(left, right)| left != right)
        .count()
        + a.len().abs_diff(b.len())
}

/// Bounds of the changed pixels. `None` when the frames are identical. When the
/// buffer lengths differ the only honest bound is the whole canvas.
pub fn changed_bbox(a: &[u8], b: &[u8], width: usize, height: usize) -> Option<DiffBox> {
    if a == b {
        return None;
    }
    if a.len() != b.len() || width == 0 || height == 0 {
        return Some(DiffBox {
            x: 0,
            y: 0,
            w: width,
            h: height,
        });
    }
    let (mut x0, mut y0) = (usize::MAX, usize::MAX);
    let (mut x1, mut y1) = (0, 0);
    for (i, (left, right)) in a.iter().zip(b).enumerate() {
        if left == right {
            continue;
        }
        let (x, y) = (i % width, i / width);
        x0 = x0.min(x);
        y0 = y0.min(y);
        x1 = x1.max(x + 1);
        y1 = y1.max(y + 1);
    }
    (x0 != usize::MAX).then(|| DiffBox {
        x: x0,
        y: y0,
        w: x1 - x0,
        h: y1 - y0,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn frame(width: usize, height: usize, changes: &[(usize, usize)]) -> Vec<u8> {
        let mut pixels = vec![0; width * height];
        for (x, y) in changes {
            pixels[y * width + x] = 1;
        }
        pixels
    }

    #[test]
    fn identical_frames_have_no_box() {
        let a = frame(8, 4, &[(1, 1)]);
        assert_eq!(changed_count(&a, &a), 0);
        assert_eq!(changed_bbox(&a, &a, 8, 4), None);
    }

    #[test]
    fn bbox_covers_every_changed_pixel() {
        let a = frame(8, 4, &[]);
        let b = frame(8, 4, &[(2, 1), (5, 3)]);
        assert_eq!(changed_count(&a, &b), 2);
        assert_eq!(
            changed_bbox(&a, &b, 8, 4),
            Some(DiffBox {
                x: 2,
                y: 1,
                w: 4,
                h: 3
            })
        );
    }

    #[test]
    fn changed_count_handles_size_mismatch() {
        let a = vec![0; 8];
        let b = vec![0; 6];
        assert_eq!(changed_count(&a, &b), 2);
        assert_eq!(
            changed_bbox(&a, &b, 4, 2),
            Some(DiffBox {
                x: 0,
                y: 0,
                w: 4,
                h: 2
            })
        );
    }
}
