//! T11 — StructureAgent Types (v12)
//!
//! Output types for the StructureAgent. The agent suggests an argument flow
//! outline that the scholar reviews in the TUI.

use serde::{Deserialize, Serialize};

use super::ids::ClaimId;

/// Evidence coverage level for an outline node.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CoverageLevel {
    /// Sufficient evidence from indexed sources. (TUI: green)
    Full,
    /// Some evidence but incomplete. (TUI: grey)
    Partial,
    /// Missing evidence — gap identified. (TUI: amber)
    Gap,
}

/// Scholar's review decision on an outline node.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ScholarDecision {
    Accept,
    Reject,
    Modify { new_heading: String },
    Unsure,
}

/// A single node in the argument flow outline.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OutlineNode {
    /// Unique identifier within this outline.
    pub id: String,
    /// Suggested section heading.
    pub heading_suggestion: String,
    /// Claims that support this section, with source references.
    pub supporting_claims: Vec<ClaimId>,
    /// Prerequisite node IDs — this section logically depends on these.
    pub dependency_ids: Vec<String>,
    /// Evidence coverage level for this section.
    pub coverage: CoverageLevel,
    /// References to comparable sections in other papers in the taxonomy.
    pub comparable_section_refs: Vec<String>,
}

/// The output of StructureAgent: a suggested argument flow outline.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArgumentFlowOutline {
    pub nodes: Vec<OutlineNode>,
}
