//! T6 — FrameState (State Machine)
//!
//! The execution state machine.
//! INIT → PLAN → THINK → ACT → VERIFY → COMMIT → REFLECT → DONE
//! Any of ACT, VERIFY, COMMIT may transition to RECOVER.

use serde::{Deserialize, Serialize};

/// The execution state machine states.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum FrameState {
    Init,
    Plan,
    Think,
    Act,
    Verify,
    Commit,
    Reflect,
    Done,
    /// RECOVER tracks which state triggered recovery.
    Recover {
        from: Box<FrameState>,
    },
}

impl FrameState {
    /// Returns true if this is a terminal state.
    pub fn is_terminal(&self) -> bool {
        matches!(self, Self::Done)
    }

    /// Returns the human-readable name of this state.
    pub fn name(&self) -> &str {
        match self {
            Self::Init => "INIT",
            Self::Plan => "PLAN",
            Self::Think => "THINK",
            Self::Act => "ACT",
            Self::Verify => "VERIFY",
            Self::Commit => "COMMIT",
            Self::Reflect => "REFLECT",
            Self::Done => "DONE",
            Self::Recover { .. } => "RECOVER",
        }
    }

    /// Returns true if RECOVER can be entered from this state.
    pub fn can_recover(&self) -> bool {
        matches!(self, Self::Act | Self::Verify | Self::Commit)
    }
}
