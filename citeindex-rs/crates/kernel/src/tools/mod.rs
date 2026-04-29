//! Tool Dispatcher — I1_tool_dispatcher_contract.md
//!
//! The kernel's syscall layer. Agents never access indexes, databases, or
//! files directly. Every data operation goes through a tool call.

pub mod ag_query_claims;
pub mod ag_query_contradictions;
pub mod ag_write_edge;
pub mod csl_render;
pub mod delete_document;
pub mod index_claim;
pub mod index_document;
pub mod memory_save;
pub mod merkle_compute;
pub mod merkle_verify;
pub mod regex_search;
pub mod search_claims;
pub mod search_documents;
pub mod search_memory;
pub mod tree_load;
pub mod tree_traverse;

use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use crate::argument_graph;
use crate::indexes;
use crate::scoring::ScoreFusionWeights;
use crate::storage::StorageLayout;
use crate::types::ids::AgentName;

/// Tool call from an agent.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct ToolCall {
    pub tool: String,
    pub call_id: String,
    pub params: serde_json::Value,
}

/// Tool response back to agent.
#[derive(Debug, Clone, serde::Serialize)]
pub struct ToolResponse {
    pub call_id: String,
    pub result: Option<serde_json::Value>,
    pub error: Option<ToolErrorPayload>,
}

/// Serializable error payload for agent communication.
#[derive(Debug, Clone, serde::Serialize)]
pub struct ToolErrorPayload {
    pub error_type: String,
    pub message: String,
}

/// Tool errors.
#[derive(Debug, thiserror::Error)]
pub enum ToolError {
    #[error("permission denied: agent {agent} cannot call tool {tool}")]
    PermissionDenied { agent: String, tool: String },

    #[error("unknown tool: {0}")]
    UnknownTool(String),

    #[error("invalid params: {param}: {message}")]
    InvalidParams { param: String, message: String },

    #[error("not found: {resource_type} {id}")]
    NotFound { resource_type: String, id: String },

    #[error("index error: {0}")]
    IndexError(String),

    #[error("database error: {0}")]
    DatabaseError(String),

    #[error("io error: {0}")]
    IoError(String),

    #[error("merkle error: {0}")]
    MerkleError(String),

    #[error("not implemented: {0}")]
    NotImplemented(String),
}

impl ToolError {
    pub fn to_payload(&self) -> ToolErrorPayload {
        let error_type = match self {
            Self::PermissionDenied { .. } => "PermissionDenied",
            Self::UnknownTool(_) => "UnknownTool",
            Self::InvalidParams { .. } => "InvalidParams",
            Self::NotFound { .. } => "NotFound",
            Self::IndexError(_) => "IndexError",
            Self::DatabaseError(_) => "DatabaseError",
            Self::IoError(_) => "IoError",
            Self::MerkleError(_) => "MerkleError",
            Self::NotImplemented(_) => "NotImplemented",
        };
        ToolErrorPayload {
            error_type: error_type.to_string(),
            message: self.to_string(),
        }
    }
}

/// Agent manifest — defines which tools an agent may call.
#[derive(Debug, Clone)]
pub struct AgentManifest {
    pub name: String,
    pub tools_allowed: HashSet<String>,
}

/// Shared mutable state available to all tools.
///
/// Holds tantivy index handles (readers + writers) for the three indexes,
/// a SQLite connection for the ArgumentGraph, and score fusion weights.
pub struct ToolContext {
    // ── Tantivy indexes ──────────────────────────────────
    pub document_index: tantivy::Index,
    pub claim_index: tantivy::Index,
    pub memory_index: tantivy::Index,
    pub document_writer: Arc<Mutex<tantivy::IndexWriter>>,
    pub claim_writer: Arc<Mutex<tantivy::IndexWriter>>,
    pub memory_writer: Arc<Mutex<tantivy::IndexWriter>>,

    // ── SQLite ───────────────────────────────────────────
    pub argument_graph_db: Arc<Mutex<rusqlite::Connection>>,

    // ── Paths ────────────────────────────────────────────
    pub documents_dir: PathBuf,
    pub sources_dir: PathBuf,
    pub memory_sessions_dir: Option<PathBuf>,

    // ── Scoring ──────────────────────────────────────────
    pub score_fusion_weights: ScoreFusionWeights,

    // ── Memory access cache ──────────────────────────────
    pub memory_access_cache: HashMap<String, MemoryAccessEntry>,
}

/// Memory access metadata entry.
#[derive(Debug, Clone)]
pub struct MemoryAccessEntry {
    pub access_count: u64,
    pub last_accessed: String,
}

fn build_tool_context(
    document_index: tantivy::Index,
    claim_index: tantivy::Index,
    memory_index: tantivy::Index,
    argument_graph_db: rusqlite::Connection,
    documents_dir: PathBuf,
    sources_dir: PathBuf,
    memory_sessions_dir: Option<PathBuf>,
) -> anyhow::Result<ToolContext> {
    let document_writer = Arc::new(Mutex::new(document_index.writer(50_000_000)?));
    let claim_writer = Arc::new(Mutex::new(claim_index.writer(50_000_000)?));
    let memory_writer = Arc::new(Mutex::new(memory_index.writer(50_000_000)?));

    argument_graph::init_db(&argument_graph_db)?;

    Ok(ToolContext {
        document_index,
        claim_index,
        memory_index,
        document_writer,
        claim_writer,
        memory_writer,
        argument_graph_db: Arc::new(Mutex::new(argument_graph_db)),
        documents_dir,
        sources_dir,
        memory_sessions_dir,
        score_fusion_weights: ScoreFusionWeights::default(),
        memory_access_cache: HashMap::new(),
    })
}

/// Build a lightweight in-memory tool context backed by the kernel schemas.
///
/// This is useful for transitional runtimes that want to exercise the kernel
/// dispatcher without requiring the full on-disk v12 storage layout yet.
pub fn in_memory_context(documents_dir: PathBuf) -> anyhow::Result<ToolContext> {
    let document_index = tantivy::Index::create_in_ram(indexes::build_document_index_schema());
    indexes::register_tokenizers(&document_index);
    let claim_index = tantivy::Index::create_in_ram(indexes::build_claim_index_schema());
    indexes::register_tokenizers(&claim_index);
    let memory_index = tantivy::Index::create_in_ram(indexes::build_memory_index_schema());
    indexes::register_tokenizers(&memory_index);

    let conn = rusqlite::Connection::open_in_memory()?;
    build_tool_context(
        document_index,
        claim_index,
        memory_index,
        conn,
        documents_dir.clone(),
        documents_dir,
        None,
    )
}

/// Build a persistent tool context rooted in the canonical storage layout.
pub fn persistent_context(layout: &StorageLayout) -> anyhow::Result<ToolContext> {
    for dir in [
        &layout.root,
        &layout.indexes_dir,
        &layout.document_index_dir,
        &layout.memory_index_dir,
        &layout.claim_index_dir,
        &layout.documents_dir,
        &layout.sources_dir,
        &layout.structured_dir,
        &layout.citations_dir,
        &layout.memory_dir,
        &layout.sessions_dir,
    ] {
        fs::create_dir_all(dir)?;
    }

    let document_index = indexes::open_or_create_index(
        &layout.document_index_dir,
        indexes::build_document_index_schema(),
    )?;
    let claim_index = indexes::open_or_create_index(
        &layout.claim_index_dir,
        indexes::build_claim_index_schema(),
    )?;
    let memory_index = indexes::open_or_create_index(
        &layout.memory_index_dir,
        indexes::build_memory_index_schema(),
    )?;

    let conn = rusqlite::Connection::open(&layout.argument_graph_db)?;
    build_tool_context(
        document_index,
        claim_index,
        memory_index,
        conn,
        layout.documents_dir.clone(),
        layout.sources_dir.clone(),
        Some(layout.sessions_dir.clone()),
    )
}

fn legacy_search_target(params: &serde_json::Value) -> &str {
    params
        .get("index")
        .and_then(|v| v.as_str())
        .or_else(|| params.get("target").and_then(|v| v.as_str()))
        .unwrap_or("documents")
}

fn dispatch_legacy_tantivy_search(
    params: &serde_json::Value,
    ctx: &mut ToolContext,
) -> Result<serde_json::Value, ToolError> {
    match legacy_search_target(params) {
        "claim" | "claims" | "claim_index" => search_claims::execute(params, ctx),
        "memory" | "memory_index" => search_memory::execute(params, ctx),
        _ => search_documents::execute(params, ctx),
    }
}

fn dispatch_legacy_tantivy_index(
    params: &serde_json::Value,
    ctx: &mut ToolContext,
) -> Result<serde_json::Value, ToolError> {
    match legacy_search_target(params) {
        "claim" | "claims" | "claim_index" => index_claim::execute(params, ctx),
        "memory" | "memory_index" => memory_save::execute(params, ctx),
        _ => index_document::execute(params, ctx),
    }
}

/// Dispatch a tool call, enforcing agent permissions.
pub fn dispatch_tool_call(
    call: &ToolCall,
    agent_name: &AgentName,
    agent_manifest: &AgentManifest,
    ctx: &mut ToolContext,
) -> Result<ToolResponse, ToolError> {
    // 1. Check permission
    if !agent_manifest.tools_allowed.contains(&call.tool) {
        return Err(ToolError::PermissionDenied {
            agent: agent_name.0.clone(),
            tool: call.tool.clone(),
        });
    }

    // 2. Route to tool implementation
    let result = match call.tool.as_str() {
        "search_documents" => search_documents::execute(&call.params, ctx),
        "search_claims" => search_claims::execute(&call.params, ctx),
        "search_memory" => search_memory::execute(&call.params, ctx),
        "index_document" => index_document::execute(&call.params, ctx),
        "index_claim" => index_claim::execute(&call.params, ctx),
        "delete_document" => delete_document::execute(&call.params, ctx),
        "ag_query_claims" => ag_query_claims::execute(&call.params, ctx),
        "ag_query_contradictions" => ag_query_contradictions::execute(&call.params, ctx),
        "ag_write_edge" => ag_write_edge::execute(&call.params, ctx),
        "merkle_compute" => merkle_compute::execute(&call.params, ctx),
        "merkle_verify" => merkle_verify::execute(&call.params, ctx),
        "csl_render" => csl_render::execute(&call.params, ctx),
        "tree_load" => tree_load::execute(&call.params, ctx),
        "tree_traverse" => tree_traverse::execute(&call.params, ctx),
        "regex_search" => regex_search::execute(&call.params, ctx),
        "memory_save" => memory_save::execute(&call.params, ctx),
        "tantivy_search" => dispatch_legacy_tantivy_search(&call.params, ctx),
        "tantivy_index" => dispatch_legacy_tantivy_index(&call.params, ctx),
        _ => Err(ToolError::UnknownTool(call.tool.clone())),
    };

    match result {
        Ok(value) => Ok(ToolResponse {
            call_id: call.call_id.clone(),
            result: Some(value),
            error: None,
        }),
        Err(e) => Ok(ToolResponse {
            call_id: call.call_id.clone(),
            result: None,
            error: Some(e.to_payload()),
        }),
    }
}
