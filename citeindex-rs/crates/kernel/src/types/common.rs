//! Common enums and shared types used across the kernel.
//!
//! T_type_contracts.md — Common Enums

use serde::{Deserialize, Serialize};

use super::claim::Claim;
use super::ids::{AgentName, MerkleHash};

/// The output an agent returns to the kernel after completing its inner loop.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentOutput {
    pub agent_name: AgentName,
    pub task_id: String,
    pub text: String,
    pub cite_anchor_count: usize,
    pub claims: Vec<Claim>,
    pub metadata: serde_json::Value,
    /// sha256 of entire output (I5).
    pub output_hash: MerkleHash,
}

/// The result of the VERIFY stage.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VerifyResult {
    pub verified_claims: Vec<super::claim::VerifiedClaim>,
    pub blocked_claims: Vec<super::claim::BlockedClaim>,
    pub guardrails_passed: bool,
    /// verified / total.
    pub verified_rate: f32,
}

/// CSL-JSON record for citation persistence.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CslRecord {
    pub id: String,
    #[serde(rename = "type")]
    pub csl_type: String,
    pub title: Option<String>,
    pub author: Option<Vec<CslName>>,
    pub issued: Option<CslDate>,
    #[serde(rename = "DOI")]
    pub doi: Option<String>,
    #[serde(rename = "container-title")]
    pub container_title: Option<String>,
    /// Additional CSL-JSON fields stored as a bag.
    #[serde(flatten)]
    pub extra: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CslName {
    pub family: Option<String>,
    pub given: Option<String>,
    pub literal: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CslDate {
    #[serde(rename = "date-parts")]
    pub date_parts: Option<Vec<Vec<i64>>>,
    pub raw: Option<String>,
}
