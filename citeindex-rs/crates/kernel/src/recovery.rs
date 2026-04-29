//! Recovery Chain Runner — walks R1→R6 when RECOVER state is entered.
//!
//! Each step attempts a different recovery strategy. First success resumes
//! execution. If all 6 steps fail, the frame transitions to DONE with
//! partial output.

use crate::types::ids::ModelId;
use crate::types::recovery::{BatchModeAction, CompensatoryParams, RecoveryOutcome, RecoveryStep};
use crate::types::state::FrameState;

/// Maximum retry attempts for R1.
pub const MAX_R1_RETRIES: u32 = 3;

/// Backoff schedule for R1 retries (milliseconds).
pub const R1_BACKOFF_MS: &[u64] = &[1_000, 3_000, 10_000];

/// Model fallback cascade for R3.
pub const MODEL_CASCADE: &[&str] = &["cloud_premium", "cloud_standard", "local_base"];

/// Configuration for the recovery chain.
#[derive(Debug, Clone)]
pub struct RecoveryConfig {
    pub max_retries: u32,
    pub enable_r5_decompose: bool,
    pub enable_r6_hitl: bool,
    pub batch_mode: bool,
}

impl Default for RecoveryConfig {
    fn default() -> Self {
        Self {
            max_retries: MAX_R1_RETRIES,
            enable_r5_decompose: true,
            enable_r6_hitl: true,
            batch_mode: false,
        }
    }
}

/// Walk the recovery chain R1→R6 for a failed state.
///
/// Returns a `RecoveryOutcome` indicating whether recovery succeeded
/// and which state to resume from, or that all steps were exhausted.
///
/// The caller (state machine) invokes each step. This function builds
/// the step sequence and evaluates results.
pub fn build_recovery_chain(
    failed_state: &FrameState,
    current_model: &ModelId,
    config: &RecoveryConfig,
) -> Vec<RecoveryStep> {
    let mut steps = Vec::new();

    // R1: Retry with exponential backoff
    for attempt in 0..config.max_retries {
        let backoff_ms = R1_BACKOFF_MS
            .get(attempt as usize)
            .copied()
            .unwrap_or(10_000);
        steps.push(RecoveryStep::R1RetryBackoff {
            attempt: attempt + 1,
            backoff_ms,
        });
    }

    // R2: Diagnostic
    steps.push(RecoveryStep::R2Diagnostic {
        analysis: String::new(), // filled by caller after analysis
    });

    // R3: Model fallback
    let current_tier = &current_model.0;
    if let Some(fallback) = next_model_in_cascade(current_tier) {
        steps.push(RecoveryStep::R3Fallback {
            fallback_model: ModelId(fallback.into()),
            original_model: current_model.clone(),
        });
    }

    // R4: Compensatory parameter adjustment
    steps.push(RecoveryStep::R4Compensatory {
        adjusted_params: CompensatoryParams {
            max_tokens: Some(1024),        // reduce from default
            temperature: Some(0.0),        // lower temperature
            context_budget_pct: Some(0.5), // halve context
        },
    });

    // R5: Decompose (if enabled and state allows)
    if config.enable_r5_decompose {
        steps.push(RecoveryStep::R5Decompose {
            original_node_id: crate::types::ids::QueryNodeId::new(),
            sub_queries: vec![], // filled by caller
        });
    }

    // R6: Human-in-the-Loop
    if config.enable_r6_hitl {
        let batch_action = if config.batch_mode {
            BatchModeAction::QueueNotification {
                message: format!(
                    "Recovery exhausted at state {}. Scholar input needed.",
                    failed_state.name()
                ),
            }
        } else {
            BatchModeAction::SkipAndFail
        };

        steps.push(RecoveryStep::R6HumanInLoop {
            prompt_to_scholar: format!(
                "The system encountered a failure at the {} stage and automated \
                 recovery was unsuccessful. Would you like to modify the query \
                 or adjust constraints?",
                failed_state.name()
            ),
            batch_mode_action: batch_action,
        });
    }

    steps
}

/// Try to find the next model in the fallback cascade.
fn next_model_in_cascade(current: &str) -> Option<&'static str> {
    // Find current position in cascade, return next
    for (i, &tier) in MODEL_CASCADE.iter().enumerate() {
        if current.contains(tier) {
            return MODEL_CASCADE.get(i + 1).copied();
        }
    }
    None
}

/// Evaluate a recovery attempt result and determine the outcome.
pub fn evaluate_recovery(
    steps: Vec<RecoveryStep>,
    success_at: Option<usize>,
    failed_state: &FrameState,
) -> RecoveryOutcome {
    match success_at {
        Some(idx) => {
            let resume_from = match failed_state {
                FrameState::Act => FrameState::Think,     // retry from THINK
                FrameState::Verify => FrameState::Act,    // retry from ACT
                FrameState::Commit => FrameState::Verify, // retry from VERIFY
                _ => FrameState::Plan,                    // fallback
            };
            RecoveryOutcome::Recovered {
                step: steps[idx].clone(),
                resume_from,
            }
        }
        None => RecoveryOutcome::Exhausted {
            steps_attempted: steps,
            partial_output: None,
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_build_recovery_chain_default() {
        let config = RecoveryConfig::default();
        let model = ModelId("anthropic/cloud_premium".into());
        let steps = build_recovery_chain(&FrameState::Act, &model, &config);

        // 3 retries + diagnostic + fallback + compensatory + decompose + hitl = 8
        assert_eq!(steps.len(), 8);
        assert!(matches!(
            steps[0],
            RecoveryStep::R1RetryBackoff { attempt: 1, .. }
        ));
        assert!(matches!(steps[3], RecoveryStep::R2Diagnostic { .. }));
        assert!(matches!(steps[4], RecoveryStep::R3Fallback { .. }));
        assert!(matches!(steps[5], RecoveryStep::R4Compensatory { .. }));
        assert!(matches!(steps[6], RecoveryStep::R5Decompose { .. }));
        assert!(matches!(steps[7], RecoveryStep::R6HumanInLoop { .. }));
    }

    #[test]
    fn test_build_recovery_chain_no_fallback() {
        let config = RecoveryConfig::default();
        let model = ModelId("ollama/local_base".into()); // already at bottom
        let steps = build_recovery_chain(&FrameState::Act, &model, &config);

        // No R3 fallback since already at local_base
        let has_fallback = steps
            .iter()
            .any(|s| matches!(s, RecoveryStep::R3Fallback { .. }));
        assert!(!has_fallback);
    }

    #[test]
    fn test_build_recovery_chain_minimal() {
        let config = RecoveryConfig {
            max_retries: 1,
            enable_r5_decompose: false,
            enable_r6_hitl: false,
            ..Default::default()
        };
        let model = ModelId("test/model".into());
        let steps = build_recovery_chain(&FrameState::Verify, &model, &config);

        // 1 retry + diagnostic + compensatory = 3 (no fallback, no R5, no R6)
        assert_eq!(steps.len(), 3);
    }

    #[test]
    fn test_evaluate_recovery_success() {
        let steps = vec![
            RecoveryStep::R1RetryBackoff {
                attempt: 1,
                backoff_ms: 1000,
            },
            RecoveryStep::R1RetryBackoff {
                attempt: 2,
                backoff_ms: 3000,
            },
        ];

        let outcome = evaluate_recovery(steps, Some(1), &FrameState::Act);
        match outcome {
            RecoveryOutcome::Recovered { step, resume_from } => {
                assert!(matches!(
                    step,
                    RecoveryStep::R1RetryBackoff { attempt: 2, .. }
                ));
                assert_eq!(resume_from, FrameState::Think);
            }
            _ => panic!("expected Recovered"),
        }
    }

    #[test]
    fn test_evaluate_recovery_exhausted() {
        let steps = vec![RecoveryStep::R1RetryBackoff {
            attempt: 1,
            backoff_ms: 1000,
        }];

        let outcome = evaluate_recovery(steps.clone(), None, &FrameState::Act);
        assert!(matches!(outcome, RecoveryOutcome::Exhausted { .. }));
    }

    #[test]
    fn test_next_model_cascade() {
        assert_eq!(
            next_model_in_cascade("cloud_premium"),
            Some("cloud_standard")
        );
        assert_eq!(next_model_in_cascade("cloud_standard"), Some("local_base"));
        assert_eq!(next_model_in_cascade("local_base"), None);
        assert_eq!(next_model_in_cascade("unknown"), None);
    }

    #[test]
    fn test_resume_state_mapping() {
        let steps = vec![RecoveryStep::R1RetryBackoff {
            attempt: 1,
            backoff_ms: 1000,
        }];

        // ACT failure → resume from THINK
        let o = evaluate_recovery(steps.clone(), Some(0), &FrameState::Act);
        assert!(matches!(
            o,
            RecoveryOutcome::Recovered {
                resume_from: FrameState::Think,
                ..
            }
        ));

        // VERIFY failure → resume from ACT
        let o = evaluate_recovery(steps.clone(), Some(0), &FrameState::Verify);
        assert!(matches!(
            o,
            RecoveryOutcome::Recovered {
                resume_from: FrameState::Act,
                ..
            }
        ));

        // COMMIT failure → resume from VERIFY
        let o = evaluate_recovery(steps, Some(0), &FrameState::Commit);
        assert!(matches!(
            o,
            RecoveryOutcome::Recovered {
                resume_from: FrameState::Verify,
                ..
            }
        ));
    }
}
