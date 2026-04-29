//! T7 — State Transition Guards
//!
//! Each transition is a function that checks preconditions and returns the
//! next state or a transition error. The kernel calls these — never skips them.

use super::commit::CommitState;
use super::common::{AgentOutput, VerifyResult};
use super::frame::ExecutionFrame;
use super::interrupt::Interrupt;
use super::state::FrameState;

/// Errors that prevent a state transition.
#[derive(Debug, thiserror::Error)]
pub enum TransitionError {
    #[error("guard failed: {from} → {to}: {reason}")]
    GuardFailed {
        from: String,
        to: String,
        reason: String,
    },
    #[error("interrupt received: {0}")]
    InterruptReceived(#[from] Interrupt),
}

/// Helper: check a boolean condition, return `TransitionError` on failure.
fn require(condition: bool, from: &str, to: &str, reason: &str) -> Result<(), TransitionError> {
    if condition {
        Ok(())
    } else {
        Err(TransitionError::GuardFailed {
            from: from.into(),
            to: to.into(),
            reason: reason.into(),
        })
    }
}

// ── INIT → PLAN ──────────────────────────────────────────────

pub fn guard_init_to_plan(frame: &ExecutionFrame) -> Result<(), TransitionError> {
    require(
        !frame.skill.0.is_empty(),
        "INIT",
        "PLAN",
        "skill must be loaded",
    )
}

// ── PLAN → THINK ─────────────────────────────────────────────

pub fn guard_plan_to_think(frame: &ExecutionFrame) -> Result<(), TransitionError> {
    require(
        frame.query_plan.is_some(),
        "PLAN",
        "THINK",
        "query plan must exist",
    )?;
    require(
        !frame.goal_state.required_aspects.is_empty(),
        "PLAN",
        "THINK",
        "at least one aspect required",
    )
}

// ── THINK → ACT ──────────────────────────────────────────────

pub fn guard_think_to_act(frame: &ExecutionFrame) -> Result<(), TransitionError> {
    require(
        !frame.context_slots.is_empty(),
        "THINK",
        "ACT",
        "context slots must be populated",
    )
    // ContextSlot<Verified> is enforced by the type system — no runtime check needed.
}

// ── ACT → VERIFY ─────────────────────────────────────────────

pub fn guard_act_to_verify(
    _frame: &ExecutionFrame,
    agent_output: &AgentOutput,
) -> Result<(), TransitionError> {
    require(
        !agent_output.text.is_empty(),
        "ACT",
        "VERIFY",
        "agent output must not be empty",
    )?;
    require(
        agent_output.cite_anchor_count > 0,
        "ACT",
        "VERIFY",
        "agent output must contain cite anchors",
    )
}

// ── VERIFY → COMMIT ──────────────────────────────────────────

pub fn guard_verify_to_commit(
    _frame: &ExecutionFrame,
    verify_result: &VerifyResult,
) -> Result<(), TransitionError> {
    require(
        verify_result.blocked_claims.is_empty(),
        "VERIFY",
        "COMMIT",
        "all claims must be verified",
    )?;
    require(
        verify_result.guardrails_passed,
        "VERIFY",
        "COMMIT",
        "guardrails must pass",
    )
}

// ── COMMIT → REFLECT ─────────────────────────────────────────

pub fn guard_commit_to_reflect(
    _frame: &ExecutionFrame,
    commit_state: &CommitState,
) -> Result<(), TransitionError> {
    // commit_hash is guaranteed by CommitState type (non-optional field — I3).
    require(
        !commit_state.csl_citations.is_empty(),
        "COMMIT",
        "REFLECT",
        "CSL citations must be persisted",
    )
}

// ── REFLECT → DONE ───────────────────────────────────────────

pub fn guard_reflect_to_done(frame: &ExecutionFrame) -> Result<(), TransitionError> {
    let coverage = &frame.goal_state.aspect_coverage;
    for aspect in &frame.goal_state.required_aspects {
        let score = coverage.get(aspect).copied().unwrap_or(0.0);
        require(
            score >= frame.goal_state.coverage_threshold,
            "REFLECT",
            "DONE",
            &format!(
                "aspect '{}' not covered (score={:.2}, threshold={:.2})",
                aspect, score, frame.goal_state.coverage_threshold
            ),
        )?;
    }
    require(
        frame.goal_state.constraint_violations.is_empty(),
        "REFLECT",
        "DONE",
        "no constraint violations allowed",
    )
}

// ── ANY → RECOVER ────────────────────────────────────────────

/// No guard — RECOVER is always allowed from ACT, VERIFY, or COMMIT.
pub fn transition_to_recover(current: FrameState) -> FrameState {
    FrameState::Recover {
        from: Box::new(current),
    }
}
