//! T10 — QueryPlan + QueryNode (Query Planner)
//!
//! The Query Planner decomposes compound queries into a typed DAG.
//! Each node in the DAG is a unit of work assigned to an agent.
//! CoordinatorAgent walks the DAG, activating agents in topological order.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use super::common::AgentOutput;
use super::ids::{AgentName, PlanId, QueryNodeId};

/// How the query was classified by the Query Planner.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum QueryType {
    /// Single topic, single agent activation.
    Simple,
    /// Multiple sub-queries detected. DAG has parallel branches.
    Compound,
    /// Follow-up to a previous query in this session.
    Continuation { previous_plan_id: PlanId },
}

/// Retrieval mode per the RetrievalRouter specification.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum RetrievalMode {
    /// Exact keyword match. BM25 primary.
    KeywordExact,
    /// Claim-level search in claim_index. For fact-checking queries.
    ClaimCentric,
    /// Broad topic exploration. Hierarchy boost weighted higher.
    Exploratory,
    /// Low-signal retrieval. WeakSignal escalation enabled.
    WeakSignal,
    /// Augment retrieval with memory from prior sessions.
    MemoryAugmented,
}

/// Execution priority.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Priority {
    /// Foreground — scholar is waiting for this result.
    Foreground,
    /// Background — runs when foreground work allows.
    Background,
}

/// Search depth.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Depth {
    /// Fast scan. Top results only.
    Shallow,
    /// Normal operation. Balanced coverage.
    Standard,
    /// All relevant sources consulted. No shortcuts.
    Exhaustive,
}

/// Status of a query node within the DAG.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum QueryNodeStatus {
    Pending,
    Running,
    Completed,
    Failed { error: String },
    Skipped { reason: String },
}

/// A single unit of work in the query plan DAG.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryNode {
    pub node_id: QueryNodeId,
    pub sub_query: String,
    pub assigned_agent: AgentName,
    pub retrieval_mode: RetrievalMode,
    pub status: QueryNodeStatus,
    pub priority: Priority,
    pub depth: Depth,
    pub result: Option<AgentOutput>,
}

/// Edge type in the query plan DAG.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum QueryEdgeType {
    /// `to` requires the output of `from` as input.
    DataDependency,
    /// `to` should run after `from` for better context, but can proceed without.
    SoftDependency,
}

/// Directed edge in the query plan DAG.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryEdge {
    pub from: QueryNodeId,
    pub to: QueryNodeId,
    pub edge_type: QueryEdgeType,
}

/// A query plan is a directed acyclic graph of query nodes.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryPlan {
    pub plan_id: PlanId,
    pub original_query: String,
    pub query_type: QueryType,
    pub nodes: Vec<QueryNode>,
    pub edges: Vec<QueryEdge>,
    pub created_at: DateTime<Utc>,
}
