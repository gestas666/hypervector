//! Bounded viewport over complete backend depth with independent side ranges.

use std::ops::Range;

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub(crate) struct DepthViewport {
    offset: usize,
    rows: usize,
    total: usize,
}

impl DepthViewport {
    pub(crate) fn resized(self, rows: usize, total: usize) -> Self {
        Self {
            offset: self.offset.min(total.saturating_sub(rows.max(1))),
            rows,
            total,
        }
    }

    pub(crate) fn moved(self, delta: isize) -> Self {
        Self {
            offset: self
                .offset
                .saturating_add_signed(delta)
                .min(self.total.saturating_sub(self.rows.max(1))),
            ..self
        }
    }

    pub(crate) fn page_size(self) -> isize {
        isize::try_from(self.rows.max(1)).unwrap_or(isize::MAX)
    }

    pub(crate) fn range(self, side_total: usize) -> Range<usize> {
        self.offset.min(side_total)..self.offset.saturating_add(self.rows).min(side_total)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_level_is_reachable_at_each_observed_capacity() {
        for rows in [1, 9, 16, 20, 40] {
            let mut viewport = DepthViewport::default().resized(rows, 20);
            let mut seen = std::collections::BTreeSet::new();
            for _ in 0..21 {
                seen.extend(viewport.range(20));
                viewport = viewport.moved(1);
            }
            assert_eq!(seen, (0..20).collect());
            assert_eq!(viewport.moved(isize::MIN).range(20).start, 0);
        }
    }

    #[test]
    fn resize_shrinking_book_and_unequal_sides_stay_bounded() {
        let bottom = DepthViewport::default().resized(1, 20).moved(isize::MAX);
        assert_eq!(bottom.range(20), 19..20);
        assert_eq!(bottom.resized(16, 20).range(20), 4..20);
        assert_eq!(bottom.resized(3, 5).range(5), 2..5);
        assert_eq!(bottom.range(2), 2..2);
        assert_eq!(bottom.resized(0, 20).range(20), 19..19);
        assert_eq!(bottom.resized(9, 0).range(0), 0..0);
    }

    #[test]
    fn pages_use_actual_visible_capacity_and_clamp_at_the_end() {
        let first = DepthViewport::default().resized(9, 20);
        let second = first.moved(first.page_size());
        assert_eq!(second.range(20), 9..18);
        assert_eq!(second.moved(second.page_size()).range(20), 11..20);
        assert_eq!(second.moved(-second.page_size()).range(20), 0..9);
        assert_eq!(DepthViewport::default().page_size(), 1);
    }
}
