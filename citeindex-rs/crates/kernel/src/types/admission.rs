//! T9 — AdmissionTier (Load Management)
//!
//! Controls what features are available based on current system load.
//! The kernel evaluates system load at frame creation and may downgrade
//! the tier during execution if load increases.

use serde::{Deserialize, Serialize};

/// System load tiers. Higher tiers enable more features.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AdmissionTier {
    /// All features available. Assigned when system load < 50%.
    Full,
    /// Normal operation. Assigned when system load 50–75%.
    Standard,
    /// Reduced features. Assigned when system load 75–90%.
    Degraded,
    /// Minimum viable operation. Assigned when system load > 90%.
    Minimal,
}

impl AdmissionTier {
    pub fn allows_background_agents(&self) -> bool {
        matches!(self, Self::Full | Self::Standard)
    }

    pub fn allows_deep_traversal(&self) -> bool {
        matches!(self, Self::Full)
    }

    pub fn max_citation_expansion_hops(&self) -> u32 {
        match self {
            Self::Full => 3,
            Self::Standard => 2,
            Self::Degraded => 1,
            Self::Minimal => 0,
        }
    }

    pub fn allows_new_llm_calls_for_background(&self) -> bool {
        matches!(self, Self::Full | Self::Standard)
    }
}

/// Metrics the kernel uses to determine admission tier.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SystemLoad {
    pub active_frames: u32,
    pub pending_agent_requests: u32,
    pub memory_usage_pct: f32,
    pub llm_queue_depth: u32,
}

/// Thresholds for tier assignment. Configurable in config.toml.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AdmissionPolicy {
    pub full_max_load_pct: f32,
    pub standard_max_load_pct: f32,
    pub degraded_max_load_pct: f32,
}

impl Default for AdmissionPolicy {
    fn default() -> Self {
        Self {
            full_max_load_pct: 50.0,
            standard_max_load_pct: 75.0,
            degraded_max_load_pct: 90.0,
        }
    }
}

impl AdmissionPolicy {
    /// Evaluate system load and return the appropriate tier.
    pub fn evaluate(&self, load: &SystemLoad) -> AdmissionTier {
        let load_pct = load.memory_usage_pct;
        if load_pct < self.full_max_load_pct {
            AdmissionTier::Full
        } else if load_pct < self.standard_max_load_pct {
            AdmissionTier::Standard
        } else if load_pct < self.degraded_max_load_pct {
            AdmissionTier::Degraded
        } else {
            AdmissionTier::Minimal
        }
    }
}
