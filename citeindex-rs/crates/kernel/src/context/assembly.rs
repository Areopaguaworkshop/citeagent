//! Context Assembly — THINK-stage orchestration.
//!
//! Fills the four context budget zones in priority order:
//! 1. PrimaryRetrieval → from search_documents / search_claims
//! 2. SupportingCites → from citation expansion
//! 3. Memory → from search_memory
//! 4. ArgumentGraph → from ag_query_contradictions
//!
//! Each zone is filled up to its token budget, with deterministic
//! score-based eviction when candidates exceed budget.

use crate::types::admission::AdmissionTier;
use crate::types::context_slot::{BudgetZone, ContextSlot, Raw, Verified};
use crate::types::ids::{CslId, MerkleHash, QualityTier};

use super::{
    apply_admission_tier, estimate_tokens, evict_zone, ContextBudget, ZoneAllocation, ZoneBudgets,
};

/// Input configuration for context assembly.
#[derive(Debug, Clone)]
pub struct AssemblyConfig {
    pub total_model_tokens: usize,
    pub system_prompt_tokens: usize,
    pub agent_prompt_tokens: usize,
    pub output_reserve: usize,
    pub safety_margin_pct: f32,
    pub zone_allocation: ZoneAllocation,
    pub admission_tier: AdmissionTier,
    pub language: String,
}

impl Default for AssemblyConfig {
    fn default() -> Self {
        Self {
            total_model_tokens: 200_000,
            system_prompt_tokens: 500,
            agent_prompt_tokens: 300,
            output_reserve: 4096,
            safety_margin_pct: 0.05,
            zone_allocation: ZoneAllocation::default(),
            admission_tier: AdmissionTier::Full,
            language: "en".into(),
        }
    }
}

/// Result of context assembly — the assembled context ready for the agent.
#[derive(Debug)]
pub struct AssembledContext {
    pub slots: Vec<ContextSlot<Verified>>,
    pub zone_budgets: ZoneBudgets,
    pub total_tokens_used: usize,
    pub slots_by_zone: ZoneSlotCounts,
}

/// Count of slots per zone.
#[derive(Debug, Default)]
pub struct ZoneSlotCounts {
    pub primary_retrieval: usize,
    pub supporting_cites: usize,
    pub memory: usize,
    pub argument_graph: usize,
}

/// A candidate slot before verification and eviction.
#[derive(Debug, Clone)]
pub struct SlotCandidate {
    pub content: String,
    pub source_id: CslId,
    pub merkle_hash: MerkleHash,
    pub quality_tier: QualityTier,
    pub zone: BudgetZone,
    pub score: f32,
    pub language: String,
}

/// Plan the context assembly: compute budgets and zone allocations.
///
/// This is step 1-4 of the I5 assembly flow. The actual filling (steps 5-8)
/// is done by the caller using the returned budgets.
pub fn plan_assembly(config: &AssemblyConfig) -> (ZoneBudgets, f32) {
    let budget = ContextBudget::compute(
        config.total_model_tokens,
        config.system_prompt_tokens,
        config.agent_prompt_tokens,
        config.output_reserve,
        config.safety_margin_pct,
    );

    let (adjusted_alloc, multiplier) =
        apply_admission_tier(&config.zone_allocation, &config.admission_tier);

    let effective_budget = (budget.available_source_budget as f32 * multiplier) as usize;
    let zone_budgets = adjusted_alloc.compute_zone_budgets(effective_budget);

    (zone_budgets, multiplier)
}

/// Assemble verified context slots from candidates, applying eviction per zone.
pub fn assemble_context(
    candidates: Vec<SlotCandidate>,
    zone_budgets: &ZoneBudgets,
) -> AssembledContext {
    // Group candidates by zone
    let mut primary: Vec<(f32, usize, String)> = Vec::new();
    let mut supporting: Vec<(f32, usize, String)> = Vec::new();
    let mut memory: Vec<(f32, usize, String)> = Vec::new();
    let mut ag: Vec<(f32, usize, String)> = Vec::new();

    let mut candidate_map: std::collections::HashMap<String, SlotCandidate> =
        std::collections::HashMap::new();

    for (i, c) in candidates.into_iter().enumerate() {
        let token_count = estimate_tokens(&c.content, &c.language);
        let key = format!("slot_{i}");
        let entry = (c.score, token_count, key.clone());
        match c.zone {
            BudgetZone::PrimaryRetrieval => primary.push(entry),
            BudgetZone::SupportingCites => supporting.push(entry),
            BudgetZone::Memory => memory.push(entry),
            BudgetZone::ArgumentGraph => ag.push(entry),
        }
        candidate_map.insert(key, c);
    }

    // Evict per zone
    evict_zone(&mut primary, zone_budgets.primary_retrieval);
    evict_zone(&mut supporting, zone_budgets.supporting_cites);
    evict_zone(&mut memory, zone_budgets.memory);
    evict_zone(&mut ag, zone_budgets.argument_graph);

    let mut counts = ZoneSlotCounts::default();
    counts.primary_retrieval = primary.len();
    counts.supporting_cites = supporting.len();
    counts.memory = memory.len();
    counts.argument_graph = ag.len();

    // Convert surviving candidates to verified slots
    let mut slots = Vec::new();
    let mut total_tokens = 0;

    let all_surviving: Vec<(f32, usize, String)> = primary
        .into_iter()
        .chain(supporting)
        .chain(memory)
        .chain(ag)
        .collect();

    for (_score, tokens, key) in &all_surviving {
        if let Some(c) = candidate_map.remove(key) {
            let raw = ContextSlot::<Raw>::new(c.content, *tokens, c.zone);
            match raw.verify(c.source_id, c.merkle_hash, None, Some(c.quality_tier)) {
                Ok(verified) => {
                    total_tokens += tokens;
                    slots.push(verified);
                }
                Err(_) => {
                    tracing::warn!(key = key, "failed to verify context slot");
                }
            }
        }
    }

    AssembledContext {
        slots,
        zone_budgets: zone_budgets.clone(),
        total_tokens_used: total_tokens,
        slots_by_zone: counts,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_candidate(content: &str, zone: BudgetZone, score: f32) -> SlotCandidate {
        SlotCandidate {
            content: content.into(),
            source_id: CslId("src1".into()),
            merkle_hash: MerkleHash::ZERO,
            quality_tier: QualityTier::Gold,
            zone,
            score,
            language: "en".into(),
        }
    }

    #[test]
    fn test_plan_assembly_full_tier() {
        let config = AssemblyConfig::default();
        let (budgets, mult) = plan_assembly(&config);
        assert_eq!(mult, 1.0);
        assert!(budgets.primary_retrieval > 0);
        assert!(budgets.memory > 0);
    }

    #[test]
    fn test_plan_assembly_degraded_tier() {
        let config = AssemblyConfig {
            admission_tier: AdmissionTier::Degraded,
            ..Default::default()
        };
        let (budgets, mult) = plan_assembly(&config);
        assert_eq!(mult, 0.5);
        assert_eq!(budgets.memory, 0);
        assert_eq!(budgets.argument_graph, 0);
    }

    #[test]
    fn test_assemble_context_basic() {
        let candidates = vec![
            make_candidate(
                "Primary content here for the scholar",
                BudgetZone::PrimaryRetrieval,
                0.9,
            ),
            make_candidate("Memory from previous session", BudgetZone::Memory, 0.7),
        ];

        let budgets = ZoneBudgets {
            primary_retrieval: 1000,
            supporting_cites: 500,
            memory: 500,
            argument_graph: 200,
        };

        let result = assemble_context(candidates, &budgets);
        assert_eq!(result.slots.len(), 2);
        assert_eq!(result.slots_by_zone.primary_retrieval, 1);
        assert_eq!(result.slots_by_zone.memory, 1);
        assert!(result.total_tokens_used > 0);
    }

    #[test]
    fn test_assemble_context_eviction() {
        // Create many candidates that exceed budget
        let candidates: Vec<SlotCandidate> = (0..10)
            .map(|i| {
                make_candidate(
                    &"word ".repeat(100), // ~25 tokens each
                    BudgetZone::PrimaryRetrieval,
                    1.0 - i as f32 * 0.1,
                )
            })
            .collect();

        let budgets = ZoneBudgets {
            primary_retrieval: 100, // Only room for ~4 slots
            supporting_cites: 0,
            memory: 0,
            argument_graph: 0,
        };

        let result = assemble_context(candidates, &budgets);
        assert!(result.slots.len() < 10);
        assert!(result.slots_by_zone.primary_retrieval < 10);
    }
}
