//! DKEE State Machine — the kernel's core execution loop.
//!
//! Drives an ExecutionFrame through:
//!   INIT → PLAN → THINK → ACT → VERIFY → COMMIT → REFLECT → DONE
//!
//! The kernel never calls an LLM directly. Agent interactions happen via
//! the IPC protocol (Phase 2/3). This module owns the state transitions
//! and invariant enforcement.

use crate::types::transitions;
use crate::types::{
    AgentOutput, CommitState, ExecutionFrame, FrameState, Interrupt, TransitionError, VerifyResult,
};

/// Result of a single state machine step.
#[derive(Debug)]
pub enum StepResult {
    /// Transitioned to the next state successfully.
    Advanced { new_state: FrameState },
    /// Frame reached terminal DONE state.
    Completed,
    /// Entered RECOVER state; recovery chain will be walked.
    EnteredRecovery { from: FrameState },
    /// A transition guard failed.
    GuardFailed(TransitionError),
    /// An interrupt was received.
    Interrupted(Interrupt),
}

/// The state machine driver. Validates guards and advances the frame.
///
/// This struct does NOT own the frame — it operates on a mutable reference.
/// External code (the kernel engine) owns the frame and calls `step()` or
/// `try_advance()` in a loop.
pub struct StateMachine;

impl StateMachine {
    /// Attempt to advance the frame to the next state.
    ///
    /// This checks the appropriate guard function for the current state
    /// and transitions if the guard passes. Returns `StepResult` indicating
    /// what happened.
    ///
    /// Some transitions require external data (e.g., ACT→VERIFY needs
    /// `AgentOutput`). Use the specific `advance_*` methods for those.
    pub fn try_advance_simple(frame: &mut ExecutionFrame) -> StepResult {
        match &frame.state {
            FrameState::Init => match transitions::guard_init_to_plan(frame) {
                Ok(()) => {
                    frame.state = FrameState::Plan;
                    StepResult::Advanced {
                        new_state: FrameState::Plan,
                    }
                }
                Err(e) => StepResult::GuardFailed(e),
            },
            FrameState::Plan => match transitions::guard_plan_to_think(frame) {
                Ok(()) => {
                    frame.state = FrameState::Think;
                    StepResult::Advanced {
                        new_state: FrameState::Think,
                    }
                }
                Err(e) => StepResult::GuardFailed(e),
            },
            FrameState::Think => match transitions::guard_think_to_act(frame) {
                Ok(()) => {
                    frame.state = FrameState::Act;
                    StepResult::Advanced {
                        new_state: FrameState::Act,
                    }
                }
                Err(e) => StepResult::GuardFailed(e),
            },
            FrameState::Reflect => match transitions::guard_reflect_to_done(frame) {
                Ok(()) => {
                    frame.state = FrameState::Done;
                    StepResult::Completed
                }
                Err(e) => StepResult::GuardFailed(e),
            },
            FrameState::Done => StepResult::Completed,
            _ => StepResult::GuardFailed(TransitionError::GuardFailed {
                from: frame.state.name().into(),
                to: "?".into(),
                reason: "use specific advance method for this transition".into(),
            }),
        }
    }

    /// ACT → VERIFY: requires AgentOutput.
    pub fn advance_act_to_verify(
        frame: &mut ExecutionFrame,
        agent_output: &AgentOutput,
    ) -> StepResult {
        match transitions::guard_act_to_verify(frame, agent_output) {
            Ok(()) => {
                frame.state = FrameState::Verify;
                StepResult::Advanced {
                    new_state: FrameState::Verify,
                }
            }
            Err(e) => {
                if frame.state.can_recover() {
                    let from = frame.state.clone();
                    frame.state = transitions::transition_to_recover(from.clone());
                    StepResult::EnteredRecovery { from }
                } else {
                    StepResult::GuardFailed(e)
                }
            }
        }
    }

    /// VERIFY → COMMIT: requires VerifyResult.
    pub fn advance_verify_to_commit(
        frame: &mut ExecutionFrame,
        verify_result: &VerifyResult,
    ) -> StepResult {
        match transitions::guard_verify_to_commit(frame, verify_result) {
            Ok(()) => {
                frame.state = FrameState::Commit;
                StepResult::Advanced {
                    new_state: FrameState::Commit,
                }
            }
            Err(e) => {
                if frame.state.can_recover() {
                    let from = frame.state.clone();
                    frame.state = transitions::transition_to_recover(from.clone());
                    StepResult::EnteredRecovery { from }
                } else {
                    StepResult::GuardFailed(e)
                }
            }
        }
    }

    /// COMMIT → REFLECT: requires CommitState.
    pub fn advance_commit_to_reflect(
        frame: &mut ExecutionFrame,
        commit_state: &CommitState,
    ) -> StepResult {
        match transitions::guard_commit_to_reflect(frame, commit_state) {
            Ok(()) => {
                frame.commit_hash = Some(commit_state.commit_hash.clone());
                frame.state = FrameState::Reflect;
                StepResult::Advanced {
                    new_state: FrameState::Reflect,
                }
            }
            Err(e) => {
                if frame.state.can_recover() {
                    let from = frame.state.clone();
                    frame.state = transitions::transition_to_recover(from.clone());
                    StepResult::EnteredRecovery { from }
                } else {
                    StepResult::GuardFailed(e)
                }
            }
        }
    }

    /// Handle an interrupt at any point during execution.
    pub fn handle_interrupt(frame: &mut ExecutionFrame, interrupt: Interrupt) -> StepResult {
        tracing::warn!(
            frame_id = %frame.frame_id,
            state = frame.state.name(),
            "Interrupt received: {interrupt}",
        );

        match &interrupt {
            Interrupt::UserAbort => {
                frame.state = FrameState::Done;
                StepResult::Interrupted(interrupt)
            }
            _ => {
                if frame.state.can_recover() {
                    let from = frame.state.clone();
                    frame.state = transitions::transition_to_recover(from.clone());
                    StepResult::EnteredRecovery { from }
                } else {
                    frame.state = FrameState::Done;
                    StepResult::Interrupted(interrupt)
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::context_slot::{BudgetZone, ContextSlot, Raw};
    use crate::types::ids::{CslId, QualityTier};
    use crate::types::{AdmissionTier, FrameState, GoalState, MerkleHash, ModelId, SkillName};

    fn make_frame() -> ExecutionFrame {
        ExecutionFrame::new(
            GoalState {
                original_query: "test query".into(),
                required_aspects: vec!["aspect1".into()],
                coverage_threshold: 0.6,
                aspect_coverage: std::collections::HashMap::new(),
                constraints: vec![],
                constraint_violations: vec![],
            },
            SkillName("literature_review".into()),
            ModelId("test/model".into()),
            AdmissionTier::Full,
        )
    }

    #[test]
    fn test_init_to_plan() {
        let mut frame = make_frame();
        assert_eq!(frame.state, FrameState::Init);

        let result = StateMachine::try_advance_simple(&mut frame);
        assert!(matches!(
            result,
            StepResult::Advanced {
                new_state: FrameState::Plan
            }
        ));
        assert_eq!(frame.state, FrameState::Plan);
    }

    #[test]
    fn test_plan_requires_query_plan() {
        let mut frame = make_frame();
        frame.state = FrameState::Plan;
        // No query plan set — guard should fail
        let result = StateMachine::try_advance_simple(&mut frame);
        assert!(matches!(result, StepResult::GuardFailed(_)));
    }

    #[test]
    fn test_think_requires_context_slots() {
        let mut frame = make_frame();
        frame.state = FrameState::Think;
        // No context slots — guard should fail
        let result = StateMachine::try_advance_simple(&mut frame);
        assert!(matches!(result, StepResult::GuardFailed(_)));
    }

    #[test]
    fn test_think_to_act_with_slots() {
        let mut frame = make_frame();
        frame.state = FrameState::Think;

        // Add a verified context slot
        let raw = ContextSlot::<Raw>::new("test content".into(), 10, BudgetZone::PrimaryRetrieval);
        let verified = raw
            .verify(
                CslId("test-csl".into()),
                MerkleHash::from_str_content("test"),
                None,
                Some(QualityTier::Gold),
            )
            .unwrap();
        frame.context_slots.push(verified);

        let result = StateMachine::try_advance_simple(&mut frame);
        assert!(matches!(
            result,
            StepResult::Advanced {
                new_state: FrameState::Act
            }
        ));
    }
}
