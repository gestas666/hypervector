//! Hypervector core: pure Rust foundation for Phase 1 alpha discovery.

/// Placeholder identity used to confirm the workspace builds and tests.
pub fn ping() -> &'static str {
    "hypervector-core"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ping_returns_crate_name() {
        assert_eq!(ping(), "hypervector-core");
    }
}
