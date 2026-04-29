//! T5 — ExecutionFrame (I1–I5 container)
//!
//! The central data structure. One frame per scholar request. Contains all
//! state needed to execute, verify, commit, and replay a task.

use serde::{Deserialize, Serialize};

use super::admission::AdmissionTier;
use super::context_slot::{ContextSlot, Verified};
use super::ids::*;
use super::query_plan::QueryPlan;
use super::replay::ReplayGuarantee;
use super::state::FrameState;

/// GoalState — what the scholar asked for.
/// Populated at PLAN, evaluated at REFLECT.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GoalState {
    /// The original query text.
    pub original_query: String,
    /// Required aspects that must be covered.
    pub required_aspects: Vec<String>,
    /// Coverage threshold per aspect (default 0.6).
    pub coverage_threshold: f32,
    /// Current aspect coverage scores (updated during execution).
    pub aspect_coverage: std::collections::HashMap<String, f32>,
    /// Scholar-specified constraints (year range, quality tier, venue, etc.).
    pub constraints: Vec<Constraint>,
    /// Constraint violations detected during execution.
    pub constraint_violations: Vec<String>,
}

/// A scholar-specified constraint on retrieval or output.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Constraint {
    pub field: String,
    pub operator: ConstraintOp,
    pub value: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ConstraintOp {
    Eq,
    Gte,
    Lte,
    In,
    NotIn,
}

/// Resource usage tracking for an execution frame.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ResourceUsage {
    pub steps_taken: u32,
    pub tokens_used: u64,
    pub tool_calls: u32,
    pub wall_time_ms: u64,
    pub llm_calls: u32,
}

/// The central data structure. One frame per scholar request.
#[derive(Debug, Clone)]
pub struct ExecutionFrame {
    // ── Identity ──────────────────────────────────────────
    pub frame_id: FrameId,
    pub trace_id: TraceId,

    // ── Scholar intent ────────────────────────────────────
    pub goal_state: GoalState,
    pub skill: SkillName,
    pub project_id: Option<ProjectId>,

    // ── Model ─────────────────────────────────────────────
    pub model: ModelId,
    pub lora_adapter: Option<LoraAdapterId>,

    // ── State machine ─────────────────────────────────────
    pub state: FrameState,

    // ── Query planning ────────────────────────────────────
    pub query_plan: Option<QueryPlan>,

    // ── Context (I2) ──────────────────────────────────────
    pub context_slots: Vec<ContextSlot<Verified>>,

    // ── Retrieval state (I4) ──────────────────────────────
    pub index_merkle_root: MerkleHash,

    // ── Claims (I1) ───────────────────────────────────────
    pub verified_claims: Vec<super::claim::VerifiedClaim>,

    // ── Commit (I3) ───────────────────────────────────────
    pub commit_hash: Option<MerkleHash>,

    // ── Replay (I4) ───────────────────────────────────────
    pub replay_guarantee: ReplayGuarantee,

    // ── Load management ───────────────────────────────────
    pub admission_tier: AdmissionTier,

    // ── Resource tracking ─────────────────────────────────
    pub resource_usage: ResourceUsage,
}

impl ExecutionFrame {
    /// Create a new frame in INIT state.
    pub fn new(
        goal_state: GoalState,
        skill: SkillName,
        model: ModelId,
        admission_tier: AdmissionTier,
    ) -> Self {
        Self {
            frame_id: FrameId::new(),
            trace_id: TraceId::new(),
            goal_state,
            skill,
            project_id: None,
            model,
            lora_adapter: None,
            state: FrameState::Init,
            query_plan: None,
            context_slots: Vec::new(),
            index_merkle_root: MerkleHash::ZERO,
            verified_claims: Vec::new(),
            commit_hash: None,
            replay_guarantee: ReplayGuarantee::Exact,
            admission_tier,
            resource_usage: ResourceUsage::default(),
        }
    }
}
