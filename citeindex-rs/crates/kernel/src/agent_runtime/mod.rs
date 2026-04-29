//! Agent Runtime — I2_agent_runtime_contract.md
//!
//! NDJSON IPC protocol between the Rust kernel (parent) and Python agent
//! subprocesses (children). Defines message schemas, protocol state machine,
//! agent process lifecycle, and agent manifests.

use std::collections::HashSet;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use crate::types::ids::AgentName;

/// Protocol version for compatibility checks.
pub const PROTOCOL_VERSION: &str = "12.0";

/// Maximum NDJSON message size (10 MB).
pub const MAX_MESSAGE_SIZE: usize = 10 * 1024 * 1024;

// ── Agent State Machine ──────────────────────────────────────

/// Protocol state machine for an agent process.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AgentState {
    NotSpawned,
    Spawned,
    Initializing,
    Idle,
    Running,
    ShuttingDown,
    Dead,
}

// ── Incoming message routing (agent → kernel) ────────────────

/// Any message received from an agent on stdout.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum AgentMessage {
    #[serde(rename = "init_ack")]
    InitAck(InitAckPayload),
    #[serde(rename = "tool_call")]
    ToolCall(ToolCallPayload),
    #[serde(rename = "progress")]
    Progress(ProgressPayload),
    #[serde(rename = "llm_report")]
    LlmReport(LlmReportPayload),
    #[serde(rename = "result")]
    Result(ResultPayload),
    #[serde(rename = "error")]
    Error(ErrorPayload),
    #[serde(rename = "shutdown_ack")]
    ShutdownAck(ShutdownAckPayload),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InitAckPayload {
    pub agent_name: String,
    pub protocol_version: String,
    pub status: String,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCallPayload {
    pub call_id: String,
    pub tool: String,
    pub params: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProgressPayload {
    pub task_id: String,
    #[serde(default)]
    pub stage: String,
    #[serde(default)]
    pub iteration: u32,
    #[serde(default)]
    pub detail: String,
    #[serde(default)]
    pub tool_calls_so_far: u32,
    #[serde(default)]
    pub llm_calls_so_far: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmReportPayload {
    pub task_id: String,
    pub call_index: u32,
    pub model: String,
    pub model_tier: String,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub total_tokens: u64,
    pub latency_ms: u64,
    #[serde(default)]
    pub time_to_first_token_ms: u64,
    #[serde(default)]
    pub temperature: f32,
    #[serde(default)]
    pub max_tokens: u32,
    #[serde(default)]
    pub system_prompt: String,
    #[serde(default)]
    pub messages: Vec<serde_json::Value>,
    #[serde(default)]
    pub context_slot_ids: Vec<String>,
    #[serde(default)]
    pub context_source_ids: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResultPayload {
    pub task_id: String,
    pub status: String,
    pub output: serde_json::Value,
    pub output_hash: String,
    pub resource_usage: ResourceUsageReport,
}

/// Resource usage reported by agent.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ResourceUsageReport {
    #[serde(default)]
    pub llm_calls: u32,
    #[serde(default)]
    pub tool_calls: u32,
    #[serde(default)]
    pub input_tokens: u64,
    #[serde(default)]
    pub output_tokens: u64,
    #[serde(default)]
    pub wall_time_ms: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorPayload {
    pub task_id: String,
    pub error_type: String,
    pub message: String,
    #[serde(default)]
    pub recoverable: bool,
    pub partial_output: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShutdownAckPayload {
    pub agent_name: String,
}

// ── Agent Manifest ───────────────────────────────────────────

/// Agent manifest loaded from TOML config file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentManifest {
    pub agent: AgentSection,
    pub llm_contract: LlmContractSection,
    #[serde(default)]
    pub activation: ActivationSection,
    pub tools_allowed: ToolsAllowedSection,
    #[serde(default)]
    pub resources: ResourcesSection,
    #[serde(default)]
    pub inner_loop: InnerLoopSection,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentSection {
    pub name: String,
    #[serde(default)]
    pub version: String,
    #[serde(default)]
    pub domain: String,
    pub entry_point: String,
    #[serde(default)]
    pub description: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmContractSection {
    pub model_tier: String,
    #[serde(default = "default_grounding")]
    pub grounding: String,
    #[serde(default)]
    pub temperature: f32,
    #[serde(default = "default_max_tokens")]
    pub max_tokens: u32,
    #[serde(default)]
    pub output_schema: String,
}

fn default_grounding() -> String {
    "required".into()
}
fn default_max_tokens() -> u32 {
    4096
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ActivationSection {
    #[serde(default)]
    pub skill_bind: Vec<String>,
    #[serde(default)]
    pub trigger: String,
    #[serde(default)]
    pub priority: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolsAllowedSection {
    #[serde(default)]
    pub tools: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourcesSection {
    #[serde(default = "default_max_tool_calls")]
    pub max_tool_calls: u32,
    #[serde(default = "default_max_llm_calls")]
    pub max_llm_calls: u32,
    #[serde(default = "default_request_timeout")]
    pub request_timeout_s: u64,
}

fn default_max_tool_calls() -> u32 {
    20
}
fn default_max_llm_calls() -> u32 {
    5
}
fn default_request_timeout() -> u64 {
    300
}

impl Default for ResourcesSection {
    fn default() -> Self {
        Self {
            max_tool_calls: default_max_tool_calls(),
            max_llm_calls: default_max_llm_calls(),
            request_timeout_s: default_request_timeout(),
        }
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct InnerLoopSection {
    #[serde(default)]
    pub steps: Vec<String>,
}

impl AgentManifest {
    /// Load an agent manifest from a TOML file.
    pub fn load(path: &std::path::Path) -> anyhow::Result<Self> {
        let content = std::fs::read_to_string(path)?;
        let manifest: Self = toml::from_str(&content)?;
        Ok(manifest)
    }

    /// Get the set of tools this agent is allowed to call.
    pub fn tools_set(&self) -> HashSet<String> {
        self.tools_allowed.tools.iter().cloned().collect()
    }
}

// ── Timeout Constants ────────────────────────────────────────

pub const DEFAULT_INIT_TIMEOUT_S: u64 = 10;
pub const DEFAULT_REQUEST_TIMEOUT_S: u64 = 300;
pub const DEFAULT_TOOL_TIMEOUT_S: u64 = 30;
pub const SHUTDOWN_TIMEOUT_S: u64 = 3;
pub const MAX_RESPAWN_ATTEMPTS: u32 = 3;

/// Respawn backoff durations in milliseconds.
pub const RESPAWN_BACKOFF_MS: &[u64] = &[1_000, 5_000, 15_000];

// ── Agent Process (kernel-side) ──────────────────────────────

/// Kernel-side representation of an agent subprocess.
pub struct AgentProcess {
    pub name: AgentName,
    pub state: AgentState,
    pub entry_point: String,
    pub crash_count: u32,
    pub last_crash: Option<DateTime<Utc>>,
    pub current_task_id: Option<String>,
    pub manifest: AgentManifest,
    child: Option<tokio::process::Child>,
    stdin: Option<tokio::io::BufWriter<tokio::process::ChildStdin>>,
    stdout: Option<tokio::io::BufReader<tokio::process::ChildStdout>>,
}

impl AgentProcess {
    /// Create a new AgentProcess in NotSpawned state.
    pub fn new(manifest: AgentManifest) -> Self {
        Self {
            name: AgentName(manifest.agent.name.clone()),
            state: AgentState::NotSpawned,
            entry_point: manifest.agent.entry_point.clone(),
            crash_count: 0,
            last_crash: None,
            current_task_id: None,
            manifest,
            child: None,
            stdin: None,
            stdout: None,
        }
    }

    /// Spawn the agent subprocess and perform the init handshake.
    pub async fn spawn_and_init(
        &mut self,
        data_dir: &str,
        model: &str,
        model_tier: &str,
    ) -> anyhow::Result<()> {
        use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader, BufWriter};
        use tokio::process::Command;

        let parts: Vec<&str> = self.entry_point.split_whitespace().collect();
        if parts.is_empty() {
            anyhow::bail!("empty entry_point for agent {}", self.name.0);
        }

        let mut cmd = Command::new(parts[0]);
        for arg in &parts[1..] {
            cmd.arg(arg);
        }
        cmd.stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped());

        let mut child = cmd.spawn()?;
        self.state = AgentState::Spawned;

        let child_stdin = child
            .stdin
            .take()
            .ok_or_else(|| anyhow::anyhow!("failed to capture agent stdin"))?;
        let child_stdout = child
            .stdout
            .take()
            .ok_or_else(|| anyhow::anyhow!("failed to capture agent stdout"))?;

        let mut writer = BufWriter::new(child_stdin);
        let mut reader = BufReader::new(child_stdout);

        // Send init message
        self.state = AgentState::Initializing;
        let init_msg = serde_json::json!({
            "type": "init",
            "protocol_version": PROTOCOL_VERSION,
            "agent_name": self.manifest.agent.name,
            "config": {
                "model": model,
                "model_tier": model_tier,
                "max_tokens": self.manifest.llm_contract.max_tokens,
                "temperature": self.manifest.llm_contract.temperature,
                "tools_available": self.manifest.tools_allowed.tools,
                "skill": self.manifest.activation.skill_bind.first()
                    .unwrap_or(&String::new()),
                "data_dir": data_dir,
            }
        });

        let line = serde_json::to_string(&init_msg)? + "\n";
        writer.write_all(line.as_bytes()).await?;
        writer.flush().await?;

        // Read init_ack with timeout
        let mut ack_line = String::new();
        let read_result = tokio::time::timeout(
            std::time::Duration::from_secs(DEFAULT_INIT_TIMEOUT_S),
            reader.read_line(&mut ack_line),
        )
        .await;

        match read_result {
            Ok(Ok(0)) => {
                self.state = AgentState::Dead;
                anyhow::bail!("agent {} closed stdout during init", self.name.0);
            }
            Ok(Ok(_)) => {
                let ack: AgentMessage = serde_json::from_str(ack_line.trim())?;
                match ack {
                    AgentMessage::InitAck(payload) if payload.status == "ok" => {
                        self.state = AgentState::Idle;
                    }
                    AgentMessage::InitAck(payload) => {
                        self.state = AgentState::Dead;
                        anyhow::bail!(
                            "agent {} init failed: {}",
                            self.name.0,
                            payload.error.unwrap_or_default()
                        );
                    }
                    _ => {
                        self.state = AgentState::Dead;
                        anyhow::bail!("expected init_ack from {}, got other message", self.name.0);
                    }
                }
            }
            Ok(Err(e)) => {
                self.state = AgentState::Dead;
                anyhow::bail!("IO error reading init_ack from {}: {e}", self.name.0);
            }
            Err(_) => {
                self.state = AgentState::Dead;
                anyhow::bail!("init timeout for agent {}", self.name.0);
            }
        }

        self.child = Some(child);
        self.stdin = Some(writer);
        self.stdout = Some(reader);

        tracing::info!(agent = %self.name.0, "agent initialized successfully");
        Ok(())
    }

    /// Send a JSON message to the agent's stdin.
    pub async fn send(&mut self, msg: &serde_json::Value) -> anyhow::Result<()> {
        use tokio::io::AsyncWriteExt;

        let writer = self
            .stdin
            .as_mut()
            .ok_or_else(|| anyhow::anyhow!("agent {} not spawned", self.name.0))?;
        let line = serde_json::to_string(msg)? + "\n";
        writer.write_all(line.as_bytes()).await?;
        writer.flush().await?;
        Ok(())
    }

    /// Read one NDJSON message from the agent's stdout.
    pub async fn recv(&mut self) -> anyhow::Result<AgentMessage> {
        use tokio::io::AsyncBufReadExt;

        let reader = self
            .stdout
            .as_mut()
            .ok_or_else(|| anyhow::anyhow!("agent {} not spawned", self.name.0))?;
        let mut line = String::new();
        let n = reader.read_line(&mut line).await?;
        if n == 0 {
            self.state = AgentState::Dead;
            anyhow::bail!("agent {} closed stdout (EOF)", self.name.0);
        }
        let msg: AgentMessage = serde_json::from_str(line.trim())?;
        Ok(msg)
    }

    /// Send shutdown and wait for ack (best-effort).
    pub async fn shutdown(&mut self) -> anyhow::Result<()> {
        if self.state == AgentState::Dead || self.state == AgentState::NotSpawned {
            return Ok(());
        }

        self.state = AgentState::ShuttingDown;
        let shutdown_msg = serde_json::json!({"type": "shutdown"});
        if let Err(e) = self.send(&shutdown_msg).await {
            tracing::warn!(agent = %self.name.0, "failed to send shutdown: {e}");
        }

        let result = tokio::time::timeout(
            std::time::Duration::from_secs(SHUTDOWN_TIMEOUT_S),
            self.recv(),
        )
        .await;

        match result {
            Ok(Ok(AgentMessage::ShutdownAck(_))) => {
                tracing::info!(agent = %self.name.0, "graceful shutdown acknowledged");
            }
            _ => {
                tracing::warn!(
                    agent = %self.name.0,
                    "shutdown ack not received, killing process"
                );
            }
        }

        if let Some(ref mut child) = self.child {
            let _ = child.kill().await;
        }
        self.state = AgentState::Dead;
        Ok(())
    }

    /// Get the respawn backoff duration for the current crash count.
    pub fn respawn_backoff_ms(&self) -> Option<u64> {
        RESPAWN_BACKOFF_MS.get(self.crash_count as usize).copied()
    }
}

// ── Output hash verification (I5) ────────────────────────────

/// Verify the output hash (sha256) matches the output content.
pub fn verify_output_hash(output: &serde_json::Value, claimed_hash: &str) -> bool {
    use sha2::{Digest, Sha256};

    let serialized = serde_json::to_string(output).unwrap_or_default();
    let hash = Sha256::digest(serialized.as_bytes());
    let computed = format!("sha256:{}", hex::encode(hash));
    computed == claimed_hash
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_agent_manifest_parse() {
        let toml_str = r#"
[agent]
name = "TestAgent"
entry_point = "python -m test_agent"

[llm_contract]
model_tier = "cloud_standard"
temperature = 0.3
max_tokens = 2048
output_schema = "test_v1"

[activation]
skill_bind = ["test"]
trigger = "default"
priority = "foreground"

[tools_allowed]
tools = ["search_documents", "tree_load"]

[resources]
max_tool_calls = 10
max_llm_calls = 3
request_timeout_s = 120

[inner_loop]
steps = ["PLAN: plan", "THINK: think", "ACT: act"]
"#;
        let manifest: AgentManifest = toml::from_str(toml_str).unwrap();
        assert_eq!(manifest.agent.name, "TestAgent");
        assert_eq!(manifest.llm_contract.model_tier, "cloud_standard");
        assert_eq!(manifest.tools_allowed.tools.len(), 2);
        assert_eq!(manifest.resources.max_tool_calls, 10);
        let tools = manifest.tools_set();
        assert!(tools.contains("search_documents"));
        assert!(tools.contains("tree_load"));
    }

    #[test]
    fn test_agent_message_deserialize_init_ack() {
        let json = r#"{"type":"init_ack","agent_name":"Test","protocol_version":"12.0","status":"ok","error":null}"#;
        let msg: AgentMessage = serde_json::from_str(json).unwrap();
        assert!(matches!(msg, AgentMessage::InitAck(_)));
    }

    #[test]
    fn test_agent_message_deserialize_tool_call() {
        let json = r#"{"type":"tool_call","call_id":"uuid-1","tool":"search_documents","params":{"query":"test"}}"#;
        let msg: AgentMessage = serde_json::from_str(json).unwrap();
        match msg {
            AgentMessage::ToolCall(p) => {
                assert_eq!(p.tool, "search_documents");
                assert_eq!(p.call_id, "uuid-1");
            }
            _ => panic!("expected ToolCall"),
        }
    }

    #[test]
    fn test_agent_message_deserialize_result() {
        let json = r#"{"type":"result","task_id":"t1","status":"ok","output":{"text":"hi"},"output_hash":"sha256:abc","resource_usage":{"llm_calls":1,"tool_calls":2,"input_tokens":100,"output_tokens":50,"wall_time_ms":500}}"#;
        let msg: AgentMessage = serde_json::from_str(json).unwrap();
        assert!(matches!(msg, AgentMessage::Result(_)));
    }

    #[test]
    fn test_agent_message_deserialize_error() {
        let json = r#"{"type":"error","task_id":"t1","error_type":"llm_error","message":"rate limited","recoverable":true,"partial_output":null}"#;
        let msg: AgentMessage = serde_json::from_str(json).unwrap();
        match msg {
            AgentMessage::Error(p) => {
                assert!(p.recoverable);
                assert_eq!(p.error_type, "llm_error");
            }
            _ => panic!("expected Error"),
        }
    }

    #[test]
    fn test_verify_output_hash() {
        let output = serde_json::json!({"text": "hello world"});
        use sha2::{Digest, Sha256};
        let serialized = serde_json::to_string(&output).unwrap();
        let hash = Sha256::digest(serialized.as_bytes());
        let hash_str = format!("sha256:{}", hex::encode(hash));

        assert!(verify_output_hash(&output, &hash_str));
        assert!(!verify_output_hash(&output, "sha256:wrong"));
    }

    #[test]
    fn test_agent_process_new() {
        let manifest: AgentManifest = toml::from_str(
            r#"
[agent]
name = "Test"
entry_point = "python -m test"
[llm_contract]
model_tier = "local_base"
[activation]
[tools_allowed]
tools = []
"#,
        )
        .unwrap();

        let agent = AgentProcess::new(manifest);
        assert_eq!(agent.state, AgentState::NotSpawned);
        assert_eq!(agent.crash_count, 0);
        assert_eq!(agent.respawn_backoff_ms(), Some(1_000));
    }

    #[test]
    fn test_respawn_backoff() {
        let manifest: AgentManifest = toml::from_str(
            r#"
[agent]
name = "Test"
entry_point = "python -m test"
[llm_contract]
model_tier = "local_base"
[activation]
[tools_allowed]
tools = []
"#,
        )
        .unwrap();

        let mut agent = AgentProcess::new(manifest);
        assert_eq!(agent.respawn_backoff_ms(), Some(1_000));
        agent.crash_count = 1;
        assert_eq!(agent.respawn_backoff_ms(), Some(5_000));
        agent.crash_count = 2;
        assert_eq!(agent.respawn_backoff_ms(), Some(15_000));
        agent.crash_count = 3;
        assert_eq!(agent.respawn_backoff_ms(), None);
    }
}
