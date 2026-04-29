//! REST API types and handler logic — A1_openapi.yaml
//!
//! Defines request/response types for all 14 CiteIndex v12 API endpoints
//! and a router that dispatches to stub handlers returning JSON values.
//! The actual HTTP server binding (axum/actix) is deferred; this module
//! provides the kernel-side logic layer.

use std::collections::HashMap;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

// ── Error ────────────────────────────────────────────────────

/// Errors that can arise when handling an API request.
#[derive(Debug, thiserror::Error)]
pub enum ApiError {
    #[error("authentication required")]
    Unauthorized,

    #[error("invalid token")]
    InvalidToken,

    #[error("endpoint not found: {0}")]
    NotFound(String),

    #[error("bad request: {0}")]
    BadRequest(String),

    #[error("internal error: {0}")]
    Internal(String),
}

// ── Authentication ───────────────────────────────────────────

/// Bearer-token authentication context.
#[derive(Debug, Clone)]
pub struct ApiAuth {
    /// Expected bearer token. `None` means authentication is disabled.
    expected_token: Option<String>,
}

impl ApiAuth {
    /// Create an auth guard that requires the given bearer token.
    pub fn new(token: impl Into<String>) -> Self {
        Self {
            expected_token: Some(token.into()),
        }
    }

    /// Create an auth guard that permits all requests (no token required).
    pub fn open() -> Self {
        Self {
            expected_token: None,
        }
    }

    /// Validate an incoming `Authorization: Bearer <token>` value.
    pub fn validate(&self, bearer: Option<&str>) -> Result<(), ApiError> {
        match &self.expected_token {
            None => Ok(()),
            Some(expected) => match bearer {
                Some(tok) if tok == expected => Ok(()),
                Some(_) => Err(ApiError::InvalidToken),
                None => Err(ApiError::Unauthorized),
            },
        }
    }
}

// ── Request / Response types ─────────────────────────────────

// -- /api/cite ------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CiteRequest {
    pub claim: String,
    #[serde(default)]
    pub top_k: Option<u32>,
    #[serde(default)]
    pub project: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CiteResponse {
    pub claim: String,
    pub citations: Vec<Citation>,
    pub verified: bool,
    pub timestamp: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Citation {
    pub source_id: String,
    pub title: String,
    pub excerpt: String,
    pub score: f64,
    #[serde(default)]
    pub metadata: HashMap<String, Value>,
}

// -- /api/search ----------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchRequest {
    pub query: String,
    #[serde(default = "default_top_k")]
    pub top_k: u32,
    #[serde(default)]
    pub filters: HashMap<String, Value>,
}

fn default_top_k() -> u32 {
    10
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResponse {
    pub query: String,
    pub results: Vec<SearchResult>,
    pub total_hits: u64,
    pub fusion_method: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub doc_id: String,
    pub title: String,
    pub snippet: String,
    pub score: f64,
    pub score_breakdown: HashMap<String, f64>,
}

// -- /api/memory ----------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryQueryRequest {
    pub query: String,
    #[serde(default)]
    pub scope: Option<String>,
    #[serde(default)]
    pub limit: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryQueryResponse {
    pub entries: Vec<MemoryEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryEntry {
    pub id: String,
    pub content: String,
    pub relevance: f64,
    pub created_at: DateTime<Utc>,
}

// -- /api/explain ---------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExplainRequest {
    pub claim: String,
    #[serde(default)]
    pub trace_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExplainResponse {
    pub claim: String,
    pub attribution_chain: Vec<AttributionStep>,
    pub confidence: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AttributionStep {
    pub step: u32,
    pub description: String,
    pub source: Option<String>,
    pub score: f64,
}

// -- /api/replay ----------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReplayRequest {
    pub trace_id: String,
    #[serde(default = "default_replay_mode")]
    pub mode: ReplayMode,
}

fn default_replay_mode() -> ReplayMode {
    ReplayMode::Exact
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReplayMode {
    Exact,
    Approximate,
    DryRun,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReplayResponse {
    pub trace_id: String,
    pub mode: ReplayMode,
    pub status: String,
    pub steps_replayed: u32,
    #[serde(default)]
    pub divergences: Vec<String>,
}

// -- /api/eval ------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvalRequest {
    pub dataset: String,
    #[serde(default)]
    pub metrics: Vec<String>,
    #[serde(default)]
    pub params: HashMap<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvalResponse {
    pub eval_id: String,
    pub dataset: String,
    pub results: HashMap<String, f64>,
    pub started_at: DateTime<Utc>,
}

// -- /api/agent -----------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentInfo {
    pub name: String,
    pub enabled: bool,
    pub status: String,
    #[serde(default)]
    pub metadata: HashMap<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentListResponse {
    pub agents: Vec<AgentInfo>,
}

// -- /api/agent/register --------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentRegisterRequest {
    pub name: String,
    pub manifest: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentRegisterResponse {
    pub name: String,
    pub registered: bool,
    pub message: String,
}

// -- /api/agent/enable & /api/agent/disable --------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentToggleRequest {
    pub name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentToggleResponse {
    pub name: String,
    pub enabled: bool,
    pub message: String,
}

// -- /api/agent/run -------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentRunRequest {
    pub name: String,
    #[serde(default)]
    pub input: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentRunResponse {
    pub run_id: String,
    pub agent: String,
    pub status: String,
    #[serde(default)]
    pub output: Value,
}

// -- /api/agent/{name}/status ---------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentStatusResponse {
    pub name: String,
    pub status: String,
    pub uptime_secs: u64,
    #[serde(default)]
    pub last_run: Option<DateTime<Utc>>,
}

// -- /api/skillpack -------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillPackInfo {
    pub name: String,
    pub version: String,
    pub installed: bool,
    #[serde(default)]
    pub description: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillPackListResponse {
    pub packs: Vec<SkillPackInfo>,
}

// -- /api/skillpack/install -----------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillPackInstallRequest {
    pub name: String,
    #[serde(default)]
    pub version: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillPackInstallResponse {
    pub name: String,
    pub version: String,
    pub installed: bool,
    pub message: String,
}

// ── Router ───────────────────────────────────────────────────

/// Routes API calls to handler stubs. Holds references to kernel state
/// (currently empty — will be wired in Phase 2).
pub struct ApiRouter {
    auth: ApiAuth,
}

impl ApiRouter {
    pub fn new(auth: ApiAuth) -> Self {
        Self { auth }
    }

    /// Dispatch an API call by endpoint path.
    ///
    /// `bearer` is the raw bearer token (if any) from the Authorization
    /// header.  `body` is the parsed JSON request body (use
    /// `Value::Null` for GET endpoints without a body).
    pub fn handle(&self, path: &str, body: Value, bearer: Option<&str>) -> Result<Value, ApiError> {
        self.auth.validate(bearer)?;

        match path {
            "/api/cite" => self.handle_cite(body),
            "/api/search" => self.handle_search(body),
            "/api/memory" => self.handle_memory(body),
            "/api/explain" => self.handle_explain(body),
            "/api/replay" => self.handle_replay(body),
            "/api/eval" => self.handle_eval(body),
            "/api/agent" => self.handle_agent_list(),
            "/api/agent/register" => self.handle_agent_register(body),
            "/api/agent/enable" => self.handle_agent_toggle(body, true),
            "/api/agent/disable" => self.handle_agent_toggle(body, false),
            "/api/agent/run" => self.handle_agent_run(body),
            "/api/skillpack" => self.handle_skillpack_list(),
            "/api/skillpack/install" => self.handle_skillpack_install(body),
            other if other.starts_with("/api/agent/") && other.ends_with("/status") => {
                let name = other
                    .strip_prefix("/api/agent/")
                    .and_then(|s| s.strip_suffix("/status"))
                    .unwrap_or("");
                self.handle_agent_status(name)
            }
            _ => Err(ApiError::NotFound(path.to_string())),
        }
    }

    // ── Handler stubs ────────────────────────────────────────

    fn handle_cite(&self, body: Value) -> Result<Value, ApiError> {
        let req: CiteRequest =
            serde_json::from_value(body).map_err(|e| ApiError::BadRequest(e.to_string()))?;
        let resp = CiteResponse {
            claim: req.claim,
            citations: vec![],
            verified: false,
            timestamp: Utc::now(),
        };
        Ok(serde_json::to_value(resp).unwrap())
    }

    fn handle_search(&self, body: Value) -> Result<Value, ApiError> {
        let req: SearchRequest =
            serde_json::from_value(body).map_err(|e| ApiError::BadRequest(e.to_string()))?;
        let resp = SearchResponse {
            query: req.query,
            results: vec![],
            total_hits: 0,
            fusion_method: "weighted_sum".into(),
        };
        Ok(serde_json::to_value(resp).unwrap())
    }

    fn handle_memory(&self, body: Value) -> Result<Value, ApiError> {
        let _req: MemoryQueryRequest =
            serde_json::from_value(body).map_err(|e| ApiError::BadRequest(e.to_string()))?;
        let resp = MemoryQueryResponse { entries: vec![] };
        Ok(serde_json::to_value(resp).unwrap())
    }

    fn handle_explain(&self, body: Value) -> Result<Value, ApiError> {
        let req: ExplainRequest =
            serde_json::from_value(body).map_err(|e| ApiError::BadRequest(e.to_string()))?;
        let resp = ExplainResponse {
            claim: req.claim,
            attribution_chain: vec![],
            confidence: 0.0,
        };
        Ok(serde_json::to_value(resp).unwrap())
    }

    fn handle_replay(&self, body: Value) -> Result<Value, ApiError> {
        let req: ReplayRequest =
            serde_json::from_value(body).map_err(|e| ApiError::BadRequest(e.to_string()))?;
        let resp = ReplayResponse {
            trace_id: req.trace_id,
            mode: req.mode,
            status: "pending".into(),
            steps_replayed: 0,
            divergences: vec![],
        };
        Ok(serde_json::to_value(resp).unwrap())
    }

    fn handle_eval(&self, body: Value) -> Result<Value, ApiError> {
        let req: EvalRequest =
            serde_json::from_value(body).map_err(|e| ApiError::BadRequest(e.to_string()))?;
        let resp = EvalResponse {
            eval_id: Uuid::new_v4().to_string(),
            dataset: req.dataset,
            results: HashMap::new(),
            started_at: Utc::now(),
        };
        Ok(serde_json::to_value(resp).unwrap())
    }

    fn handle_agent_list(&self) -> Result<Value, ApiError> {
        let resp = AgentListResponse { agents: vec![] };
        Ok(serde_json::to_value(resp).unwrap())
    }

    fn handle_agent_register(&self, body: Value) -> Result<Value, ApiError> {
        let req: AgentRegisterRequest =
            serde_json::from_value(body).map_err(|e| ApiError::BadRequest(e.to_string()))?;
        let resp = AgentRegisterResponse {
            name: req.name,
            registered: true,
            message: "agent registered (stub)".into(),
        };
        Ok(serde_json::to_value(resp).unwrap())
    }

    fn handle_agent_toggle(&self, body: Value, enable: bool) -> Result<Value, ApiError> {
        let req: AgentToggleRequest =
            serde_json::from_value(body).map_err(|e| ApiError::BadRequest(e.to_string()))?;
        let resp = AgentToggleResponse {
            name: req.name,
            enabled: enable,
            message: if enable {
                "agent enabled (stub)".into()
            } else {
                "agent disabled (stub)".into()
            },
        };
        Ok(serde_json::to_value(resp).unwrap())
    }

    fn handle_agent_run(&self, body: Value) -> Result<Value, ApiError> {
        let req: AgentRunRequest =
            serde_json::from_value(body).map_err(|e| ApiError::BadRequest(e.to_string()))?;
        let resp = AgentRunResponse {
            run_id: Uuid::new_v4().to_string(),
            agent: req.name,
            status: "queued".into(),
            output: Value::Null,
        };
        Ok(serde_json::to_value(resp).unwrap())
    }

    fn handle_agent_status(&self, name: &str) -> Result<Value, ApiError> {
        if name.is_empty() {
            return Err(ApiError::BadRequest("agent name is empty".into()));
        }
        let resp = AgentStatusResponse {
            name: name.to_string(),
            status: "idle".into(),
            uptime_secs: 0,
            last_run: None,
        };
        Ok(serde_json::to_value(resp).unwrap())
    }

    fn handle_skillpack_list(&self) -> Result<Value, ApiError> {
        let resp = SkillPackListResponse { packs: vec![] };
        Ok(serde_json::to_value(resp).unwrap())
    }

    fn handle_skillpack_install(&self, body: Value) -> Result<Value, ApiError> {
        let req: SkillPackInstallRequest =
            serde_json::from_value(body).map_err(|e| ApiError::BadRequest(e.to_string()))?;
        let resp = SkillPackInstallResponse {
            name: req.name,
            version: req.version.unwrap_or_else(|| "latest".into()),
            installed: true,
            message: "skillpack installed (stub)".into(),
        };
        Ok(serde_json::to_value(resp).unwrap())
    }
}

// ── Tests ────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_cite_request_serialize() {
        let req = CiteRequest {
            claim: "The Earth orbits the Sun.".into(),
            top_k: Some(5),
            project: None,
        };
        let val = serde_json::to_value(&req).unwrap();
        assert_eq!(val["claim"], "The Earth orbits the Sun.");
        assert_eq!(val["top_k"], 5);

        let roundtrip: CiteRequest = serde_json::from_value(val).unwrap();
        assert_eq!(roundtrip.claim, req.claim);
        assert_eq!(roundtrip.top_k, req.top_k);
    }

    #[test]
    fn test_search_request_defaults() {
        let val = json!({ "query": "machine learning" });
        let req: SearchRequest = serde_json::from_value(val).unwrap();
        assert_eq!(req.query, "machine learning");
        assert_eq!(req.top_k, 10);
        assert!(req.filters.is_empty());
    }

    #[test]
    fn test_api_auth_valid_token() {
        let auth = ApiAuth::new("secret-token-123");
        assert!(auth.validate(Some("secret-token-123")).is_ok());
    }

    #[test]
    fn test_api_auth_invalid_token() {
        let auth = ApiAuth::new("secret-token-123");
        let err = auth.validate(Some("wrong-token")).unwrap_err();
        assert!(matches!(err, ApiError::InvalidToken));
    }

    #[test]
    fn test_api_auth_no_token_required() {
        let auth = ApiAuth::open();
        assert!(auth.validate(None).is_ok());
        assert!(auth.validate(Some("anything")).is_ok());
    }

    #[test]
    fn test_api_error_display() {
        let err = ApiError::Unauthorized;
        assert_eq!(err.to_string(), "authentication required");

        let err = ApiError::NotFound("/api/missing".into());
        assert_eq!(err.to_string(), "endpoint not found: /api/missing");

        let err = ApiError::BadRequest("missing field".into());
        assert_eq!(err.to_string(), "bad request: missing field");

        let err = ApiError::Internal("db connection lost".into());
        assert_eq!(err.to_string(), "internal error: db connection lost");

        let err = ApiError::InvalidToken;
        assert_eq!(err.to_string(), "invalid token");
    }

    #[test]
    fn test_replay_request_modes() {
        let exact = json!({ "trace_id": "t-001", "mode": "exact" });
        let req: ReplayRequest = serde_json::from_value(exact).unwrap();
        assert_eq!(req.mode, ReplayMode::Exact);

        let approx = json!({ "trace_id": "t-002", "mode": "approximate" });
        let req: ReplayRequest = serde_json::from_value(approx).unwrap();
        assert_eq!(req.mode, ReplayMode::Approximate);

        let dry = json!({ "trace_id": "t-003", "mode": "dry_run" });
        let req: ReplayRequest = serde_json::from_value(dry).unwrap();
        assert_eq!(req.mode, ReplayMode::DryRun);

        // Default mode when omitted
        let no_mode = json!({ "trace_id": "t-004" });
        let req: ReplayRequest = serde_json::from_value(no_mode).unwrap();
        assert_eq!(req.mode, ReplayMode::Exact);
    }

    #[test]
    fn test_agent_list_response_serialize() {
        let resp = AgentListResponse {
            agents: vec![
                AgentInfo {
                    name: "planner".into(),
                    enabled: true,
                    status: "idle".into(),
                    metadata: HashMap::new(),
                },
                AgentInfo {
                    name: "verifier".into(),
                    enabled: false,
                    status: "stopped".into(),
                    metadata: HashMap::from([("version".into(), json!("1.2.0"))]),
                },
            ],
        };
        let val = serde_json::to_value(&resp).unwrap();
        let agents = val["agents"].as_array().unwrap();
        assert_eq!(agents.len(), 2);
        assert_eq!(agents[0]["name"], "planner");
        assert_eq!(agents[1]["enabled"], false);
        assert_eq!(agents[1]["metadata"]["version"], "1.2.0");
    }

    #[test]
    fn test_router_handle_not_found() {
        let router = ApiRouter::new(ApiAuth::open());
        let err = router.handle("/api/nope", Value::Null, None).unwrap_err();
        assert!(matches!(err, ApiError::NotFound(_)));
    }

    #[test]
    fn test_router_handle_cite_stub() {
        let router = ApiRouter::new(ApiAuth::open());
        let body = json!({ "claim": "Water boils at 100°C." });
        let resp = router.handle("/api/cite", body, None).unwrap();
        assert_eq!(resp["claim"], "Water boils at 100°C.");
        assert_eq!(resp["verified"], false);
        assert!(resp["citations"].as_array().unwrap().is_empty());
    }

    #[test]
    fn test_router_auth_required() {
        let router = ApiRouter::new(ApiAuth::new("my-secret"));
        let body = json!({ "claim": "test" });

        // No token → Unauthorized
        let err = router.handle("/api/cite", body.clone(), None).unwrap_err();
        assert!(matches!(err, ApiError::Unauthorized));

        // Wrong token → InvalidToken
        let err = router
            .handle("/api/cite", body.clone(), Some("wrong"))
            .unwrap_err();
        assert!(matches!(err, ApiError::InvalidToken));

        // Correct token → success
        let resp = router.handle("/api/cite", body, Some("my-secret")).unwrap();
        assert_eq!(resp["claim"], "test");
    }

    #[test]
    fn test_router_agent_status() {
        let router = ApiRouter::new(ApiAuth::open());
        let resp = router
            .handle("/api/agent/planner/status", Value::Null, None)
            .unwrap();
        assert_eq!(resp["name"], "planner");
        assert_eq!(resp["status"], "idle");
    }
}
