//! Trace System — S7_trace_schema.md
//!
//! Every ExecutionFrame produces one trace. A trace is an ordered sequence
//! of spans in JSONL format recording state transitions, agent calls,
//! tool calls, LLM invocations, and progress.

use std::fs::{self, File};
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::state_machine::{StateMachine, StepResult};
use crate::types::ids::{FrameId, MerkleHash, ModelId, TraceId};
use crate::types::replay::ReplayGuarantee;
use crate::types::{AgentOutput, CommitState, ExecutionFrame, Interrupt, VerifyResult};

/// Unique identifier for a span within a trace.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct SpanId(pub Uuid);

impl SpanId {
    pub fn new() -> Self {
        Self(Uuid::new_v4())
    }
}

impl std::fmt::Display for SpanId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// Classification of a trace span.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SpanType {
    StateTransition,
    AgentRequest,
    AgentProgress,
    AgentResult,
    ToolCall,
    ToolResponse,
    LlmCall,
    VerifyGate,
    Commit,
    Coverage,
    ConstraintCheck,
    Interrupt,
    Error,
}

/// A single span in the trace.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Span {
    pub trace_id: TraceId,
    pub span_id: SpanId,
    pub parent_span_id: Option<SpanId>,
    pub started_at: DateTime<Utc>,
    pub ended_at: Option<DateTime<Utc>>,
    pub duration_ms: Option<i64>,
    pub span_type: SpanType,
    pub name: String,
    pub frame_id: FrameId,
    pub frame_state: String,
    pub payload: serde_json::Value,
}

impl Span {
    /// Create a new span starting now.
    pub fn new(
        trace_id: TraceId,
        frame_id: FrameId,
        span_type: SpanType,
        name: String,
        frame_state: String,
        parent_span_id: Option<SpanId>,
        payload: serde_json::Value,
    ) -> Self {
        Self {
            trace_id,
            span_id: SpanId::new(),
            parent_span_id,
            started_at: Utc::now(),
            ended_at: None,
            duration_ms: None,
            span_type,
            name,
            frame_id,
            frame_state,
            payload,
        }
    }

    /// Mark this span as finished.
    pub fn finish(&mut self) {
        let now = Utc::now();
        self.duration_ms = Some((now - self.started_at).num_milliseconds());
        self.ended_at = Some(now);
    }
}

/// Trace writer. One per ExecutionFrame.
/// Appends spans to a trace JSONL file.
pub struct TraceWriter {
    trace_id: TraceId,
    frame_id: FrameId,
    writer: BufWriter<File>,
    path: PathBuf,
}

impl TraceWriter {
    /// Create a new trace file for this execution.
    ///
    /// Path: `{traces_dir}/{YYYY-MM-DD}/{trace_id}.jsonl`
    pub fn new(trace_id: TraceId, frame_id: FrameId, traces_dir: &Path) -> anyhow::Result<Self> {
        let date = Utc::now().format("%Y-%m-%d").to_string();
        let date_dir = traces_dir.join(&date);
        fs::create_dir_all(&date_dir)?;

        let filename = format!("{}.jsonl", trace_id.0);
        let path = date_dir.join(&filename);
        let file = File::create(&path)?;
        let writer = BufWriter::new(file);

        tracing::debug!(trace_id = %trace_id.0, path = %path.display(), "trace file created");

        Ok(Self {
            trace_id,
            frame_id,
            writer,
            path,
        })
    }

    /// Write a span to the trace file.
    pub fn write_span(&mut self, span: &Span) -> anyhow::Result<()> {
        let json = serde_json::to_string(span)?;
        writeln!(self.writer, "{json}")?;
        self.writer.flush()?;
        Ok(())
    }

    /// Create and immediately write a completed span.
    pub fn record(
        &mut self,
        span_type: SpanType,
        name: &str,
        frame_state: &str,
        parent_span_id: Option<SpanId>,
        payload: serde_json::Value,
    ) -> anyhow::Result<SpanId> {
        let mut span = Span::new(
            self.trace_id.clone(),
            self.frame_id.clone(),
            span_type,
            name.to_string(),
            frame_state.to_string(),
            parent_span_id,
            payload,
        );
        span.finish();
        let span_id = span.span_id.clone();
        self.write_span(&span)?;
        Ok(span_id)
    }

    /// Record a state transition span.
    pub fn record_transition(
        &mut self,
        from: &str,
        to: &str,
        guard: &str,
        passed: bool,
        error: Option<&str>,
    ) -> anyhow::Result<SpanId> {
        self.record(
            SpanType::StateTransition,
            &format!("{from} → {to}"),
            from,
            None,
            serde_json::json!({
                "from": from,
                "to": to,
                "guard": guard,
                "guard_passed": passed,
                "guard_error": error,
            }),
        )
    }

    /// Record a tool call span.
    pub fn record_tool_call(
        &mut self,
        tool: &str,
        call_id: &str,
        caller: &str,
        params: &serde_json::Value,
        frame_state: &str,
        parent_span_id: Option<SpanId>,
    ) -> anyhow::Result<SpanId> {
        self.record(
            SpanType::ToolCall,
            tool,
            frame_state,
            parent_span_id,
            serde_json::json!({
                "tool": tool,
                "call_id": call_id,
                "caller": caller,
                "params": params,
            }),
        )
    }

    /// Record a tool response span.
    pub fn record_tool_response(
        &mut self,
        tool: &str,
        call_id: &str,
        result_count: usize,
        error: Option<&str>,
        frame_state: &str,
        parent_span_id: Option<SpanId>,
    ) -> anyhow::Result<SpanId> {
        self.record(
            SpanType::ToolResponse,
            &format!("{tool} response"),
            frame_state,
            parent_span_id,
            serde_json::json!({
                "tool": tool,
                "call_id": call_id,
                "result_count": result_count,
                "error": error,
            }),
        )
    }

    /// Record an error span.
    pub fn record_error(
        &mut self,
        name: &str,
        error_type: &str,
        message: &str,
        frame_state: &str,
    ) -> anyhow::Result<SpanId> {
        self.record(
            SpanType::Error,
            name,
            frame_state,
            None,
            serde_json::json!({
                "error_type": error_type,
                "message": message,
            }),
        )
    }

    /// Get the trace file path.
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Flush the writer.
    pub fn flush(&mut self) -> anyhow::Result<()> {
        self.writer.flush()?;
        Ok(())
    }
}

/// A state machine driver that automatically records trace spans for
/// every transition, interrupt, and recovery event.
pub struct TracedStateMachine<'a> {
    writer: &'a mut TraceWriter,
}

impl<'a> TracedStateMachine<'a> {
    pub fn new(writer: &'a mut TraceWriter) -> Self {
        Self { writer }
    }

    /// Advance simple transitions and record the trace span.
    pub fn try_advance_simple(&mut self, frame: &mut ExecutionFrame) -> StepResult {
        let from = frame.state.name().to_string();
        let result = StateMachine::try_advance_simple(frame);
        self.trace_step_result(&from, &result, frame);
        result
    }

    /// ACT → VERIFY with tracing.
    pub fn advance_act_to_verify(
        &mut self,
        frame: &mut ExecutionFrame,
        agent_output: &AgentOutput,
    ) -> StepResult {
        let from = frame.state.name().to_string();
        let result = StateMachine::advance_act_to_verify(frame, agent_output);
        self.trace_step_result(&from, &result, frame);
        result
    }

    /// VERIFY → COMMIT with tracing.
    pub fn advance_verify_to_commit(
        &mut self,
        frame: &mut ExecutionFrame,
        verify_result: &VerifyResult,
    ) -> StepResult {
        let from = frame.state.name().to_string();
        let result = StateMachine::advance_verify_to_commit(frame, verify_result);
        self.trace_step_result(&from, &result, frame);
        result
    }

    /// COMMIT → REFLECT with tracing.
    pub fn advance_commit_to_reflect(
        &mut self,
        frame: &mut ExecutionFrame,
        commit_state: &CommitState,
    ) -> StepResult {
        let from = frame.state.name().to_string();
        let result = StateMachine::advance_commit_to_reflect(frame, commit_state);
        self.trace_step_result(&from, &result, frame);
        result
    }

    /// Handle an interrupt with tracing.
    pub fn handle_interrupt(
        &mut self,
        frame: &mut ExecutionFrame,
        interrupt: Interrupt,
    ) -> StepResult {
        let from = frame.state.name().to_string();
        let result = StateMachine::handle_interrupt(frame, interrupt);
        self.trace_step_result(&from, &result, frame);
        result
    }

    /// Record the appropriate trace span based on the StepResult.
    fn trace_step_result(&mut self, from: &str, result: &StepResult, frame: &ExecutionFrame) {
        let _ = match result {
            StepResult::Advanced { new_state } => {
                let to = new_state.name();
                let guard = format!("guard_{}_to_{}", from.to_lowercase(), to.to_lowercase());
                self.writer.record_transition(from, to, &guard, true, None)
            }
            StepResult::Completed => self
                .writer
                .record_transition(from, "DONE", "terminal", true, None),
            StepResult::EnteredRecovery { from: failed_state } => self.writer.record_transition(
                from,
                "RECOVER",
                &format!("recovery_from_{}", failed_state.name().to_lowercase()),
                true,
                None,
            ),
            StepResult::GuardFailed(err) => {
                let msg = err.to_string();
                self.writer
                    .record_transition(from, "?", "guard", false, Some(&msg))
            }
            StepResult::Interrupted(interrupt) => self.writer.record(
                SpanType::Interrupt,
                &format!("Interrupt: {interrupt}"),
                from,
                None,
                serde_json::json!({
                    "interrupt_type": format!("{interrupt:?}"),
                    "frame_state_at_interrupt": from,
                    "action_taken": if frame.state.is_terminal() {
                        "transition_to_done"
                    } else {
                        "transition_to_recover"
                    },
                }),
            ),
        };
    }
}

/// Reads and queries trace JSONL files.
pub struct TraceReader;

impl TraceReader {
    /// Read all spans from a trace file.
    pub fn read_trace(path: &Path) -> anyhow::Result<Vec<Span>> {
        let content = fs::read_to_string(path)?;
        let mut spans = Vec::new();
        for line in content.lines() {
            if line.trim().is_empty() {
                continue;
            }
            let span: Span = serde_json::from_str(line)?;
            spans.push(span);
        }
        Ok(spans)
    }

    /// Find all trace files for a given date (YYYY-MM-DD) in the traces directory.
    pub fn list_traces(traces_dir: &Path, date: &str) -> anyhow::Result<Vec<PathBuf>> {
        let date_dir = traces_dir.join(date);
        if !date_dir.exists() {
            return Ok(Vec::new());
        }
        let mut paths = Vec::new();
        for entry in fs::read_dir(&date_dir)? {
            let entry = entry?;
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) == Some("jsonl") {
                paths.push(path);
            }
        }
        paths.sort();
        Ok(paths)
    }

    /// Filter spans by type from a loaded trace.
    pub fn filter_by_type<'a>(spans: &'a [Span], span_type: &SpanType) -> Vec<&'a Span> {
        spans.iter().filter(|s| &s.span_type == span_type).collect()
    }

    /// Find all spans matching a predicate.
    pub fn find_spans<F>(spans: &[Span], predicate: F) -> Vec<&Span>
    where
        F: Fn(&Span) -> bool,
    {
        spans.iter().filter(|s| predicate(s)).collect()
    }

    /// Get the total duration of a trace (first span start to last span end).
    pub fn trace_duration_ms(spans: &[Span]) -> Option<i64> {
        if spans.is_empty() {
            return None;
        }
        let start = spans.iter().map(|s| s.started_at).min()?;
        let end = spans.iter().filter_map(|s| s.ended_at).max()?;
        Some((end - start).num_milliseconds())
    }

    /// Extract a summary of the trace: counts per span type.
    pub fn trace_summary(spans: &[Span]) -> std::collections::HashMap<String, usize> {
        let mut counts = std::collections::HashMap::new();
        for span in spans {
            let key = serde_json::to_string(&span.span_type)
                .unwrap_or_else(|_| "unknown".into())
                .trim_matches('"')
                .to_string();
            *counts.entry(key).or_insert(0) += 1;
        }
        counts
    }
}

/// Replay verification — compares current index state against the
/// recorded state to determine if a trace can be replayed faithfully.
pub struct ReplayVerifier;

impl ReplayVerifier {
    /// Determine the replay guarantee by comparing the original execution
    /// state against the current state.
    ///
    /// - If index merkle root AND model match: `Exact`
    /// - If model matches but index changed: `Approximate`
    /// - If model changed: `Incompatible`
    pub fn check(
        original_merkle_root: &MerkleHash,
        current_merkle_root: &MerkleHash,
        original_model: &ModelId,
        current_model: &ModelId,
    ) -> ReplayGuarantee {
        if original_model != current_model {
            return ReplayGuarantee::Incompatible;
        }
        if original_merkle_root != current_merkle_root {
            return ReplayGuarantee::Approximate;
        }
        ReplayGuarantee::Exact
    }

    /// Check replay guarantee from a trace file's recorded state.
    /// Reads the trace, finds the first state_transition span that enters THINK
    /// (where index_merkle_root is recorded), extracts the recorded root,
    /// and compares against the current state.
    pub fn check_from_trace(
        trace_path: &Path,
        current_merkle_root: &MerkleHash,
        current_model: &ModelId,
    ) -> anyhow::Result<ReplayGuarantee> {
        let spans = TraceReader::read_trace(trace_path)?;

        // Find the commit span which has index_merkle_root
        let commit_spans = TraceReader::filter_by_type(&spans, &SpanType::Commit);
        if let Some(commit_span) = commit_spans.first() {
            let payload = &commit_span.payload;
            let recorded_root_str = payload
                .get("index_merkle_root")
                .and_then(|v: &serde_json::Value| v.as_str());
            let recorded_model_str = payload
                .get("model")
                .and_then(|v: &serde_json::Value| v.as_str());

            if let Some(root_str) = recorded_root_str {
                // Parse the recorded merkle root
                let recorded_root = parse_merkle_hash(root_str);
                let recorded_model = ModelId(recorded_model_str.unwrap_or("unknown").to_string());
                return Ok(Self::check(
                    &recorded_root,
                    current_merkle_root,
                    &recorded_model,
                    current_model,
                ));
            }
        }

        // No commit span found — replay not possible
        Ok(ReplayGuarantee::Incompatible)
    }
}

/// Parse a "sha256:hexstring" format MerkleHash, or all zeros on failure.
fn parse_merkle_hash(s: &str) -> MerkleHash {
    let hex_str = s.strip_prefix("sha256:").unwrap_or(s);
    let mut arr = [0u8; 32];
    if let Ok(bytes) = hex::decode(hex_str) {
        if bytes.len() == 32 {
            arr.copy_from_slice(&bytes);
        }
    }
    MerkleHash(arr)
}

/// Trace retention — cleans up old trace files based on configured retention days.
pub struct TraceRetention;

impl TraceRetention {
    /// Delete trace directories older than `retention_days`.
    /// Traces are stored in `{traces_dir}/{YYYY-MM-DD}/` directories.
    pub fn cleanup(traces_dir: &Path, retention_days: u32) -> anyhow::Result<CleanupReport> {
        let cutoff = Utc::now() - chrono::Duration::days(retention_days as i64);
        let cutoff_date = cutoff.format("%Y-%m-%d").to_string();

        let mut report = CleanupReport::default();

        if !traces_dir.exists() {
            return Ok(report);
        }

        for entry in fs::read_dir(traces_dir)? {
            let entry = entry?;
            let path = entry.path();
            if !path.is_dir() {
                continue;
            }

            let dir_name = match path.file_name().and_then(|n| n.to_str()) {
                Some(n) => n.to_string(),
                None => continue,
            };

            // Only process directories that look like dates (YYYY-MM-DD)
            if dir_name.len() != 10 || dir_name.chars().nth(4) != Some('-') {
                continue;
            }

            if dir_name < cutoff_date {
                // Count files before removal
                let file_count = fs::read_dir(&path)?.filter_map(|e| e.ok()).count();
                report.directories_removed += 1;
                report.files_removed += file_count;

                fs::remove_dir_all(&path)?;
                tracing::info!(dir = %dir_name, files = file_count, "removed expired trace directory");
            } else {
                report.directories_kept += 1;
            }
        }

        Ok(report)
    }
}

/// Summary of a trace cleanup operation.
#[derive(Debug, Clone, Default)]
pub struct CleanupReport {
    pub directories_removed: usize,
    pub files_removed: usize,
    pub directories_kept: usize,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::FrameState;

    fn make_trace_writer() -> (TraceWriter, PathBuf) {
        let dir = std::env::temp_dir().join(format!("citeindex_test_{}", Uuid::new_v4()));
        fs::create_dir_all(&dir).unwrap();
        let trace_id = TraceId::new();
        let frame_id = FrameId::new();
        let writer = TraceWriter::new(trace_id, frame_id, &dir).unwrap();
        (writer, dir)
    }

    #[test]
    fn test_span_new_and_finish() {
        let trace_id = TraceId::new();
        let frame_id = FrameId::new();
        let mut span = Span::new(
            trace_id,
            frame_id,
            SpanType::StateTransition,
            "INIT → PLAN".into(),
            "Init".into(),
            None,
            serde_json::json!({"from": "Init", "to": "Plan"}),
        );
        assert!(span.ended_at.is_none());
        span.finish();
        assert!(span.ended_at.is_some());
        assert!(span.duration_ms.is_some());
    }

    #[test]
    fn test_trace_writer_creates_file() {
        let (writer, dir) = make_trace_writer();
        let path = writer.path().to_path_buf();
        drop(writer);
        assert!(path.exists());
        // Cleanup
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_trace_writer_record_transition() {
        let (mut writer, dir) = make_trace_writer();
        let span_id = writer
            .record_transition("INIT", "PLAN", "guard_init_to_plan", true, None)
            .unwrap();
        assert!(!span_id.0.is_nil());

        // Read back the file
        let path = writer.path().to_path_buf();
        writer.flush().unwrap();
        drop(writer);

        let content = fs::read_to_string(&path).unwrap();
        assert!(!content.is_empty());
        let span: Span = serde_json::from_str(content.trim()).unwrap();
        assert_eq!(span.span_type, SpanType::StateTransition);
        assert_eq!(span.name, "INIT → PLAN");

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_span_type_serialization() {
        let json = serde_json::to_string(&SpanType::StateTransition).unwrap();
        assert_eq!(json, "\"state_transition\"");
        let json = serde_json::to_string(&SpanType::LlmCall).unwrap();
        assert_eq!(json, "\"llm_call\"");
    }

    // ── TracedStateMachine tests ─────────────────────────

    fn make_traced_frame_and_writer() -> (ExecutionFrame, TraceWriter, PathBuf) {
        use crate::types::{AdmissionTier, GoalState, ModelId, SkillName};
        let dir = std::env::temp_dir().join(format!("citeindex_traced_{}", Uuid::new_v4()));
        fs::create_dir_all(&dir).unwrap();
        let frame = ExecutionFrame::new(
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
        );
        let writer =
            TraceWriter::new(frame.trace_id.clone(), frame.frame_id.clone(), &dir).unwrap();
        (frame, writer, dir)
    }

    #[test]
    fn test_traced_init_to_plan() {
        let (mut frame, mut writer, dir) = make_traced_frame_and_writer();
        let mut tsm = TracedStateMachine::new(&mut writer);

        let result = tsm.try_advance_simple(&mut frame);
        assert!(matches!(
            result,
            StepResult::Advanced {
                new_state: FrameState::Plan
            }
        ));

        // Read trace file and verify a transition span was recorded
        let path = tsm.writer.path().to_path_buf();
        drop(tsm);
        writer.flush().unwrap();
        let spans = TraceReader::read_trace(&path).unwrap();
        assert_eq!(spans.len(), 1);
        assert_eq!(spans[0].span_type, SpanType::StateTransition);
        assert_eq!(spans[0].name, "INIT → PLAN");

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_traced_guard_failure_recorded() {
        let (mut frame, mut writer, dir) = make_traced_frame_and_writer();
        frame.state = FrameState::Plan; // No query plan set
        let mut tsm = TracedStateMachine::new(&mut writer);

        let result = tsm.try_advance_simple(&mut frame);
        assert!(matches!(result, StepResult::GuardFailed(_)));

        let path = tsm.writer.path().to_path_buf();
        drop(tsm);
        writer.flush().unwrap();
        let spans = TraceReader::read_trace(&path).unwrap();
        assert_eq!(spans.len(), 1);
        assert_eq!(spans[0].span_type, SpanType::StateTransition);
        // guard_passed should be false
        assert_eq!(spans[0].payload["guard_passed"], false);

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_traced_interrupt_recorded() {
        let (mut frame, mut writer, dir) = make_traced_frame_and_writer();
        let mut tsm = TracedStateMachine::new(&mut writer);

        let result = tsm.handle_interrupt(&mut frame, Interrupt::UserAbort);
        assert!(matches!(result, StepResult::Interrupted(_)));

        let path = tsm.writer.path().to_path_buf();
        drop(tsm);
        writer.flush().unwrap();
        let spans = TraceReader::read_trace(&path).unwrap();
        assert_eq!(spans.len(), 1);
        assert_eq!(spans[0].span_type, SpanType::Interrupt);

        let _ = fs::remove_dir_all(&dir);
    }

    // ── TraceReader tests ────────────────────────────────

    #[test]
    fn test_trace_reader_read_and_filter() {
        let (mut writer, dir) = make_trace_writer();
        writer
            .record_transition("INIT", "PLAN", "guard_init_to_plan", true, None)
            .unwrap();
        writer
            .record_error("test error", "TestError", "something failed", "PLAN")
            .unwrap();
        let path = writer.path().to_path_buf();
        writer.flush().unwrap();
        drop(writer);

        let spans = TraceReader::read_trace(&path).unwrap();
        assert_eq!(spans.len(), 2);

        let transitions = TraceReader::filter_by_type(&spans, &SpanType::StateTransition);
        assert_eq!(transitions.len(), 1);

        let errors = TraceReader::filter_by_type(&spans, &SpanType::Error);
        assert_eq!(errors.len(), 1);

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_trace_reader_list_traces() {
        let dir = std::env::temp_dir().join(format!("citeindex_list_{}", Uuid::new_v4()));
        let date = Utc::now().format("%Y-%m-%d").to_string();
        let date_dir = dir.join(&date);
        fs::create_dir_all(&date_dir).unwrap();

        // Create two fake trace files
        fs::write(date_dir.join("trace1.jsonl"), "").unwrap();
        fs::write(date_dir.join("trace2.jsonl"), "").unwrap();
        fs::write(date_dir.join("not_a_trace.txt"), "").unwrap();

        let traces = TraceReader::list_traces(&dir, &date).unwrap();
        assert_eq!(traces.len(), 2);

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_trace_reader_summary() {
        let (mut writer, dir) = make_trace_writer();
        writer
            .record_transition("INIT", "PLAN", "g1", true, None)
            .unwrap();
        writer
            .record_transition("PLAN", "THINK", "g2", true, None)
            .unwrap();
        writer.record_error("err", "E", "msg", "THINK").unwrap();
        let path = writer.path().to_path_buf();
        writer.flush().unwrap();
        drop(writer);

        let spans = TraceReader::read_trace(&path).unwrap();
        let summary = TraceReader::trace_summary(&spans);
        assert_eq!(summary["state_transition"], 2);
        assert_eq!(summary["error"], 1);

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_trace_reader_duration() {
        let (mut writer, dir) = make_trace_writer();
        writer
            .record_transition("INIT", "PLAN", "g1", true, None)
            .unwrap();
        writer
            .record_transition("PLAN", "THINK", "g2", true, None)
            .unwrap();
        let path = writer.path().to_path_buf();
        writer.flush().unwrap();
        drop(writer);

        let spans = TraceReader::read_trace(&path).unwrap();
        let duration = TraceReader::trace_duration_ms(&spans);
        assert!(duration.is_some());
        // Duration should be >= 0 (spans are recorded nearly instantly in tests)
        assert!(duration.unwrap() >= 0);

        let _ = fs::remove_dir_all(&dir);
    }

    // ── ReplayVerifier tests ─────────────────────────────

    #[test]
    fn test_replay_exact() {
        let root = MerkleHash::from_str_content("test index state");
        let model = ModelId("test/model".into());
        let result = ReplayVerifier::check(&root, &root, &model, &model);
        assert_eq!(result, ReplayGuarantee::Exact);
    }

    #[test]
    fn test_replay_approximate() {
        let root1 = MerkleHash::from_str_content("state v1");
        let root2 = MerkleHash::from_str_content("state v2");
        let model = ModelId("test/model".into());
        let result = ReplayVerifier::check(&root1, &root2, &model, &model);
        assert_eq!(result, ReplayGuarantee::Approximate);
    }

    #[test]
    fn test_replay_incompatible_model_change() {
        let root = MerkleHash::from_str_content("same state");
        let model1 = ModelId("test/model-v1".into());
        let model2 = ModelId("test/model-v2".into());
        let result = ReplayVerifier::check(&root, &root, &model1, &model2);
        assert_eq!(result, ReplayGuarantee::Incompatible);
    }

    // ── TraceRetention tests ─────────────────────────────

    #[test]
    fn test_retention_cleanup() {
        let dir = std::env::temp_dir().join(format!("citeindex_retention_{}", Uuid::new_v4()));
        fs::create_dir_all(&dir).unwrap();

        // Create an "old" directory (60 days ago)
        let old_date = (Utc::now() - chrono::Duration::days(60))
            .format("%Y-%m-%d")
            .to_string();
        let old_dir = dir.join(&old_date);
        fs::create_dir_all(&old_dir).unwrap();
        fs::write(old_dir.join("trace1.jsonl"), "{}").unwrap();
        fs::write(old_dir.join("trace2.jsonl"), "{}").unwrap();

        // Create a "recent" directory (today)
        let today = Utc::now().format("%Y-%m-%d").to_string();
        let today_dir = dir.join(&today);
        fs::create_dir_all(&today_dir).unwrap();
        fs::write(today_dir.join("trace3.jsonl"), "{}").unwrap();

        let report = TraceRetention::cleanup(&dir, 30).unwrap();
        assert_eq!(report.directories_removed, 1);
        assert_eq!(report.files_removed, 2);
        assert_eq!(report.directories_kept, 1);

        // Old dir should be gone
        assert!(!old_dir.exists());
        // Today's dir should remain
        assert!(today_dir.exists());

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_retention_no_traces_dir() {
        let dir = std::env::temp_dir().join(format!("citeindex_nodir_{}", Uuid::new_v4()));
        let report = TraceRetention::cleanup(&dir, 30).unwrap();
        assert_eq!(report.directories_removed, 0);
    }

    #[test]
    fn test_parse_merkle_hash_roundtrip() {
        let original = MerkleHash::from_str_content("test data");
        let display = format!("{original}"); // "sha256:hex..."
        let parsed = parse_merkle_hash(&display);
        assert_eq!(original, parsed);
    }
}
