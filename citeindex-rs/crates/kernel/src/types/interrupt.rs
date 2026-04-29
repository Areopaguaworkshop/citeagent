//! T8 — Interrupt
//!
//! Typed interrupts. Each has specific handling behavior.
//! The kernel checks for pending interrupts at every state transition.

use serde::{Deserialize, Serialize};

/// Resource kinds tracked for budget enforcement.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ResourceKind {
    Tokens,
    Steps,
    ToolCalls,
    WallTime,
    LlmCalls,
}

/// Typed interrupts that can occur during execution.
#[derive(Debug, Clone, Serialize, Deserialize, thiserror::Error)]
pub enum Interrupt {
    /// Scholar requested abort. Frame transitions to DONE with partial output.
    #[error("user abort")]
    UserAbort,

    /// Wall time or per-node timeout exceeded.
    #[error("timeout: {elapsed_ms}ms exceeded {limit_ms}ms limit")]
    Timeout { limit_ms: u64, elapsed_ms: u64 },

    /// Token budget, step count, or tool call limit exceeded.
    #[error("budget exceeded: {resource:?} used {used}/{limit}")]
    BudgetExceeded {
        resource: ResourceKind,
        limit: u64,
        used: u64,
    },

    /// A guardrail check failed.
    #[error("guardrail violation [{guardrail_id}]: {description}")]
    GuardrailViolation {
        guardrail_id: String,
        description: String,
    },

    /// An agent process crashed, returned invalid output, or timed out.
    #[error("agent fault [{agent_name}]: {error}")]
    AgentFault { agent_name: String, error: String },
}
