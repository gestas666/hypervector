//! Read-only keyboard movement through the selected backend book.

use crate::app::App;

impl App {
    /// Scroll exact backend levels without changing the selected market or book.
    pub fn move_cohort_depth(&mut self, delta: isize) {
        self.cohort_depth_viewport
            .set(self.cohort_depth_viewport.get().moved(delta));
    }

    /// Page by the actual visible ladder height, bounded by the complete book.
    pub fn page_cohort_depth(&mut self, direction: isize) {
        let step = self.cohort_depth_viewport.get().page_size();
        self.move_cohort_depth(step.saturating_mul(direction));
    }
}
