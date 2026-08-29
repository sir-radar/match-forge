//! Dependency-free boundary for the future Monte Carlo simulation engine.

#![forbid(unsafe_code)]

/// Reproducibility seed passed into future simulation operations.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SimulationSeed(u64);

impl SimulationSeed {
    /// Creates a seed without altering its bits.
    #[must_use]
    pub const fn new(value: u64) -> Self {
        Self(value)
    }

    /// Returns the exact seed value supplied by the caller.
    #[must_use]
    pub const fn value(self) -> u64 {
        self.0
    }
}

#[cfg(test)]
mod tests {
    use super::SimulationSeed;

    #[test]
    fn seed_round_trips_without_transformation() {
        let seed = SimulationSeed::new(u64::MAX);

        assert_eq!(seed.value(), u64::MAX);
    }
}
