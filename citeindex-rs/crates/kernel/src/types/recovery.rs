//! T8b — Typed Recovery Chain R1–R6 (v12)
//!
//! When the RECOVER state is entered (from ACT, VERIFY, or COMMIT),
//! the kernel walks the recovery chain R1 → R2 → R3 → R4 → R5 → R6.
//! Each step attempts a different recovery strategy. If any step succeeds,
//! execution resumes. If all steps fail, the frame transitions to DONE
//! with partial output.

use serde::{Deserialize, Serialize};

use super::common::AgentOutput;
use super::ids::{ModelId, QueryNodeId};
use super::state::FrameState;

/// The 6-step typed recovery chain.
/// Kernel walks steps in order. First success resumes execution.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum RecoveryStep {
    /// R1: Retry with exponential backoff. Max 3 retries.
    R1RetryBackoff { attempt: u32, backoff_ms: u64 },

    /// R2: Diagnostic analysis of the failure.
    /// No automatic fix — prepares context for R3+.
    R2Diagnostic { analysis: String },

    /// R3: Fallback to a simpler model.
    /// Cascade: cloud_premium → cloud_standard → local_base.
    R3Fallback {
        fallback_model: ModelId,
        original_model: ModelId,
    },

    /// R4: Compensatory parameter adjustment.
    /// Reduce max_tokens, lower temperature, shrink context budget.
    R4Compensatory { adjusted_params: CompensatoryParams },

    /// R5: Decompose into smaller sub-queries.
    R5Decompose {
        original_node_id: QueryNodeId,
        sub_queries: Vec<String>,
    },

    /// R6: Human-in-the-Loop escalation.
    R6HumanInLoop {
        prompt_to_scholar: String,
        batch_mode_action: BatchModeAction,
    },
}

/// Parameters adjusted in R4 compensatory recovery.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompensatoryParams {
    pub max_tokens: Option<usize>,
    pub temperature: Option<f32>,
    pub context_budget_pct: Option<f32>,
}

/// What to do at R6 when scholar is not present.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum BatchModeAction {
    /// Skip R6, fail frame with partial output.
    SkipAndFail,
    /// Queue a notification for scholar's next interactive session.
    QueueNotification { message: String },
}

/// The result of walking the recovery chain.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum RecoveryOutcome {
    /// A recovery step succeeded. Resume from this state.
    Recovered {
        step: RecoveryStep,
        resume_from: FrameState,
    },
    /// All 6 steps failed. Frame transitions to DONE with partial output.
    Exhausted {
        steps_attempted: Vec<RecoveryStep>,
        partial_output: Option<AgentOutput>,
    },
}
