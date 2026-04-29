//! Context Budget Zones — I5_context_budget_zones.md
//!
//! Controls how many tokens of source material are injected into the LLM
//! context window. Tokens are allocated across four zones, each serving
//! a different purpose. Eviction is deterministic (score-based).

pub mod assembly;

use serde::{Deserialize, Serialize};

use crate::types::admission::AdmissionTier;
use crate::types::context_slot::BudgetZone;

/// Total context budget computation.
#[derive(Debug, Clone)]
pub struct ContextBudget {
    pub total_model_tokens: usize,
    pub system_prompt_tokens: usize,
    pub agent_prompt_tokens: usize,
    pub output_reserve: usize,
    pub safety_margin_pct: f32,
    pub available_source_budget: usize,
}

impl ContextBudget {
    /// Compute available source budget from model and reservation parameters.
    pub fn compute(
        total: usize,
        system: usize,
        agent: usize,
        output: usize,
        safety_pct: f32,
    ) -> Self {
        let safety = (total as f32 * safety_pct) as usize;
        let available = total.saturating_sub(system + agent + output + safety);
        Self {
            total_model_tokens: total,
            system_prompt_tokens: system,
            agent_prompt_tokens: agent,
            output_reserve: output,
            safety_margin_pct: safety_pct,
            available_source_budget: available,
        }
    }
}

/// Zone allocation percentages. Must sum to 1.0.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ZoneAllocation {
    pub primary_retrieval_pct: f32,
    pub supporting_cites_pct: f32,
    pub memory_pct: f32,
    pub argument_graph_pct: f32,
}

impl Default for ZoneAllocation {
    fn default() -> Self {
        Self {
            primary_retrieval_pct: 0.40,
            supporting_cites_pct: 0.30,
            memory_pct: 0.20,
            argument_graph_pct: 0.10,
        }
    }
}

impl ZoneAllocation {
    /// Validate that zone percentages sum to 1.0.
    pub fn validate(&self) -> Result<(), String> {
        let sum = self.primary_retrieval_pct
            + self.supporting_cites_pct
            + self.memory_pct
            + self.argument_graph_pct;
        if (sum - 1.0).abs() > 0.001 {
            return Err(format!("zone allocation sums to {sum:.4}, expected 1.0"));
        }
        Ok(())
    }

    /// Compute token budget per zone.
    pub fn compute_zone_budgets(&self, available: usize) -> ZoneBudgets {
        ZoneBudgets {
            primary_retrieval: (available as f32 * self.primary_retrieval_pct) as usize,
            supporting_cites: (available as f32 * self.supporting_cites_pct) as usize,
            memory: (available as f32 * self.memory_pct) as usize,
            argument_graph: (available as f32 * self.argument_graph_pct) as usize,
        }
    }
}

/// Computed token budgets per zone.
#[derive(Debug, Clone)]
pub struct ZoneBudgets {
    pub primary_retrieval: usize,
    pub supporting_cites: usize,
    pub memory: usize,
    pub argument_graph: usize,
}

impl ZoneBudgets {
    /// Get the budget for a specific zone.
    pub fn for_zone(&self, zone: BudgetZone) -> usize {
        match zone {
            BudgetZone::PrimaryRetrieval => self.primary_retrieval,
            BudgetZone::SupportingCites => self.supporting_cites,
            BudgetZone::Memory => self.memory,
            BudgetZone::ArgumentGraph => self.argument_graph,
        }
    }

    /// Total tokens allocated across all zones.
    pub fn total(&self) -> usize {
        self.primary_retrieval + self.supporting_cites + self.memory + self.argument_graph
    }
}

/// Apply AdmissionTier to zone allocation.
///
/// Returns (adjusted allocation, budget multiplier).
pub fn apply_admission_tier(
    allocation: &ZoneAllocation,
    tier: &AdmissionTier,
) -> (ZoneAllocation, f32) {
    match tier {
        AdmissionTier::Full => (allocation.clone(), 1.0),
        AdmissionTier::Standard => (allocation.clone(), 0.8),
        AdmissionTier::Degraded => (
            ZoneAllocation {
                primary_retrieval_pct: 0.60,
                supporting_cites_pct: 0.40,
                memory_pct: 0.0,
                argument_graph_pct: 0.0,
            },
            0.5,
        ),
        AdmissionTier::Minimal => (
            ZoneAllocation {
                primary_retrieval_pct: 1.0,
                supporting_cites_pct: 0.0,
                memory_pct: 0.0,
                argument_graph_pct: 0.0,
            },
            0.3,
        ),
    }
}

/// Estimate token count for a text string.
///
/// Uses the 4-chars-per-token heuristic for English.
/// For CJK text (zh, ja), uses 2-chars-per-token.
pub fn estimate_tokens(text: &str, language: &str) -> usize {
    let chars = text.chars().count();
    match language {
        "zh" | "ja" => (chars as f32 / 2.0).ceil() as usize,
        _ => (chars as f32 / 4.0).ceil() as usize,
    }
}

/// Evict slots from a zone until total tokens fit within budget.
///
/// Keeps highest-scoring slots. Deterministic — same scores → same eviction.
/// Each slot is represented as (score, token_count, slot_id).
/// Returns the number of slots kept.
pub fn evict_zone(slots: &mut Vec<(f32, usize, String)>, zone_budget: usize) -> usize {
    slots.sort_by(|a, b| {
        b.0.partial_cmp(&a.0)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(a.1.cmp(&b.1))
            .then(a.2.cmp(&b.2))
    });

    let mut used = 0;
    let mut keep_count = 0;
    for slot in slots.iter() {
        if used + slot.1 > zone_budget {
            break;
        }
        used += slot.1;
        keep_count += 1;
    }

    slots.truncate(keep_count);
    keep_count
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_context_budget_compute() {
        let budget = ContextBudget::compute(200_000, 500, 300, 4096, 0.05);
        assert_eq!(budget.available_source_budget, 185_104);
    }

    #[test]
    fn test_context_budget_small_model() {
        let budget = ContextBudget::compute(8192, 500, 300, 2048, 0.05);
        assert_eq!(budget.available_source_budget, 4935);
    }

    #[test]
    fn test_zone_allocation_default_valid() {
        let alloc = ZoneAllocation::default();
        assert!(alloc.validate().is_ok());
    }

    #[test]
    fn test_zone_allocation_invalid() {
        let alloc = ZoneAllocation {
            primary_retrieval_pct: 0.50,
            supporting_cites_pct: 0.30,
            memory_pct: 0.20,
            argument_graph_pct: 0.20,
        };
        assert!(alloc.validate().is_err());
    }

    #[test]
    fn test_zone_budgets() {
        let alloc = ZoneAllocation::default();
        let budgets = alloc.compute_zone_budgets(185_104);
        assert_eq!(budgets.primary_retrieval, 74_041);
        assert_eq!(budgets.supporting_cites, 55_531);
        assert_eq!(budgets.memory, 37_020);
        assert_eq!(budgets.argument_graph, 18_510);
    }

    #[test]
    fn test_zone_budgets_for_zone() {
        let alloc = ZoneAllocation::default();
        let budgets = alloc.compute_zone_budgets(10_000);
        assert_eq!(budgets.for_zone(BudgetZone::PrimaryRetrieval), 4000);
        assert_eq!(budgets.for_zone(BudgetZone::Memory), 2000);
    }

    #[test]
    fn test_apply_admission_tier_full() {
        let alloc = ZoneAllocation::default();
        let (_, mult) = apply_admission_tier(&alloc, &AdmissionTier::Full);
        assert_eq!(mult, 1.0);
    }

    #[test]
    fn test_apply_admission_tier_degraded() {
        let alloc = ZoneAllocation::default();
        let (result, mult) = apply_admission_tier(&alloc, &AdmissionTier::Degraded);
        assert_eq!(mult, 0.5);
        assert_eq!(result.memory_pct, 0.0);
        assert_eq!(result.argument_graph_pct, 0.0);
    }

    #[test]
    fn test_apply_admission_tier_minimal() {
        let alloc = ZoneAllocation::default();
        let (result, mult) = apply_admission_tier(&alloc, &AdmissionTier::Minimal);
        assert_eq!(mult, 0.3);
        assert_eq!(result.primary_retrieval_pct, 1.0);
    }

    #[test]
    fn test_estimate_tokens_english() {
        assert_eq!(estimate_tokens("hello world", "en"), 3);
    }

    #[test]
    fn test_estimate_tokens_cjk() {
        assert_eq!(estimate_tokens("你好世界", "zh"), 2);
    }

    #[test]
    fn test_estimate_tokens_empty() {
        assert_eq!(estimate_tokens("", "en"), 0);
    }

    #[test]
    fn test_evict_zone() {
        let mut slots = vec![
            (0.9, 100, "a".to_string()),
            (0.8, 200, "b".to_string()),
            (0.7, 150, "c".to_string()),
            (0.5, 100, "d".to_string()),
        ];
        let kept = evict_zone(&mut slots, 350);
        assert_eq!(kept, 2);
        assert_eq!(slots.len(), 2);
    }

    #[test]
    fn test_evict_zone_all_fit() {
        let mut slots = vec![(0.9, 100, "a".to_string()), (0.8, 100, "b".to_string())];
        let kept = evict_zone(&mut slots, 500);
        assert_eq!(kept, 2);
    }

    #[test]
    fn test_evict_zone_none_fit() {
        let mut slots = vec![(0.9, 1000, "a".to_string())];
        let kept = evict_zone(&mut slots, 500);
        assert_eq!(kept, 0);
    }
}
