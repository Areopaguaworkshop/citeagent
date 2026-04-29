//! T4 — ReplayGuarantee (I4 enforcement)
//!
//! Invariant I4: Retrieval replayable given identical index state.
//! At THINK: record `index_merkle_root`. At replay: assert match.

use serde::{Deserialize, Serialize};

/// Describes how faithfully this execution frame can be replayed.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ReplayGuarantee {
    /// Index state identical. BM25 results will be identical.
    /// All tool calls deterministic. Full replay possible.
    Exact,

    /// Index has changed since original execution.
    /// BM25 results may differ. Replay is best-effort.
    Approximate,

    /// Replay not possible. Model family changed, source document deleted,
    /// or agent used non-deterministic tool.
    Incompatible,
}
