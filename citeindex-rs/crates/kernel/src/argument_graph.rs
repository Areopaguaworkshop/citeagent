//! ArgumentGraph SQLite database — S2_argument_graph_schema.md
//!
//! Implements the claims table, contradiction edges, citation graph,
//! and Jaccard pre-filter query defined in the S2 contract.

use anyhow::Context;
use rusqlite::params;

// ── Structs ──────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct ClaimRow {
    pub claim_id: String,
    pub doc_id: String,
    pub claim_text: String,
    pub verbatim_passage: String,
    pub polarity_tag: String,
    pub hierarchy_path: String,
    pub quality_tier: String,
    pub verified: bool,
}

#[derive(Debug, Clone)]
pub struct ContradictionEdge {
    pub edge_id: String,
    pub claim_a_id: String,
    pub claim_b_id: String,
    pub explanation: String,
    pub confidence: Option<f64>,
    pub detected_at: String,
}

#[derive(Debug, Clone)]
pub struct JaccardCandidate {
    pub claim_a: String,
    pub claim_b: String,
    pub jaccard: f64,
}

// ── Schema initialisation ────────────────────────────────────────────

/// Set PRAGMAs and create all tables, indexes, and views.
///
/// Idempotent — every DDL statement uses `IF NOT EXISTS`.
pub fn init_db(conn: &rusqlite::Connection) -> anyhow::Result<()> {
    conn.execute_batch("PRAGMA journal_mode = WAL;")
        .context("PRAGMA journal_mode")?;
    conn.execute_batch("PRAGMA foreign_keys = ON;")
        .context("PRAGMA foreign_keys")?;
    conn.execute_batch("PRAGMA synchronous = NORMAL;")
        .context("PRAGMA synchronous")?;

    conn.execute_batch(
        "
        -- schema_version
        CREATE TABLE IF NOT EXISTS schema_version (
            version      INTEGER PRIMARY KEY,
            applied_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            description  TEXT
        );

        -- claims
        CREATE TABLE IF NOT EXISTS claims (
            claim_id           TEXT PRIMARY KEY,
            doc_id             TEXT NOT NULL,
            claim_text         TEXT NOT NULL,
            verbatim_passage   TEXT NOT NULL,
            polarity_tag       TEXT NOT NULL CHECK (polarity_tag IN ('supports', 'contradicts', 'neutral')),
            hierarchy_path     TEXT NOT NULL,
            quality_tier       TEXT NOT NULL CHECK (quality_tier IN ('gold', 'silver', 'bronze')),
            verified           INTEGER NOT NULL DEFAULT 0,
            tree_node_id       TEXT NOT NULL,
            section_ref        TEXT,
            source_csl_id      TEXT,
            locator_type       TEXT NOT NULL CHECK (locator_type IN ('page', 'paragraph', 'section', 'timestamp', 'chapter')),
            locator_value      TEXT NOT NULL,
            merkle_hash        TEXT,
            verification_method TEXT CHECK (verification_method IN ('exact_match', 'fuzzy_match', 'llm_verified', 'manual')),
            similarity_score   REAL,
            verified_at        TEXT,
            created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            updated_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );

        -- claim_entities
        CREATE TABLE IF NOT EXISTS claim_entities (
            claim_id  TEXT NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
            entity    TEXT NOT NULL,
            PRIMARY KEY (claim_id, entity)
        );

        -- contradicts_edges
        CREATE TABLE IF NOT EXISTS contradicts_edges (
            edge_id          TEXT PRIMARY KEY,
            claim_a_id       TEXT NOT NULL REFERENCES claims(claim_id),
            claim_b_id       TEXT NOT NULL REFERENCES claims(claim_id),
            explanation      TEXT NOT NULL,
            confidence       REAL,
            detected_by      TEXT NOT NULL DEFAULT 'ContradictionAgent',
            detected_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            frame_id         TEXT,
            scholar_reviewed INTEGER NOT NULL DEFAULT 0,
            scholar_note     TEXT,
            CHECK (claim_a_id < claim_b_id)
        );

        -- citation_graph (I4 contract)
        CREATE TABLE IF NOT EXISTS citation_graph (
            citing_doc_id  TEXT NOT NULL,
            cited_doc_id   TEXT NOT NULL,
            PRIMARY KEY (citing_doc_id, cited_doc_id)
        );

        -- indexes
        CREATE INDEX IF NOT EXISTS idx_claims_polarity_hierarchy ON claims (polarity_tag, hierarchy_path);
        CREATE INDEX IF NOT EXISTS idx_claims_hierarchy           ON claims (hierarchy_path);
        CREATE INDEX IF NOT EXISTS idx_claims_doc                 ON claims (doc_id);
        CREATE INDEX IF NOT EXISTS idx_claims_verified            ON claims (verified);
        CREATE INDEX IF NOT EXISTS idx_claims_tier                ON claims (quality_tier);
        CREATE INDEX IF NOT EXISTS idx_entities_entity            ON claim_entities (entity);
        CREATE INDEX IF NOT EXISTS idx_entities_claim             ON claim_entities (claim_id);
        CREATE INDEX IF NOT EXISTS idx_contradicts_a              ON contradicts_edges (claim_a_id);
        CREATE INDEX IF NOT EXISTS idx_contradicts_b              ON contradicts_edges (claim_b_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_contradicts_pair    ON contradicts_edges (claim_a_id, claim_b_id);
        CREATE INDEX IF NOT EXISTS idx_cited                      ON citation_graph (cited_doc_id);

        -- views
        CREATE VIEW IF NOT EXISTS claims_with_entities AS
        SELECT c.*, GROUP_CONCAT(ce.entity, ', ') AS entities
        FROM claims c
        LEFT JOIN claim_entities ce ON c.claim_id = ce.claim_id
        GROUP BY c.claim_id;

        CREATE VIEW IF NOT EXISTS claims_with_contradictions AS
        SELECT c.*,
               COUNT(e.edge_id) AS contradiction_count
        FROM claims c
        LEFT JOIN contradicts_edges e
            ON c.claim_id = e.claim_a_id OR c.claim_id = e.claim_b_id
        GROUP BY c.claim_id;

        CREATE VIEW IF NOT EXISTS contradictions_full AS
        SELECT e.*,
               ca.claim_text AS claim_a_text,
               cb.claim_text AS claim_b_text,
               ca.doc_id     AS doc_a_id,
               cb.doc_id     AS doc_b_id
        FROM contradicts_edges e
        JOIN claims ca ON e.claim_a_id = ca.claim_id
        JOIN claims cb ON e.claim_b_id = cb.claim_id;

        -- seed schema version
        INSERT OR IGNORE INTO schema_version (version, description)
        VALUES (1, 'v12.0 initial schema');
        ",
    )
    .context("init_db: execute_batch")?;

    Ok(())
}

// ── Mutations ────────────────────────────────────────────────────────

/// Insert a claim and its associated entities inside a transaction.
#[allow(clippy::too_many_arguments)]
pub fn insert_claim(
    conn: &rusqlite::Connection,
    claim_id: &str,
    doc_id: &str,
    claim_text: &str,
    verbatim_passage: &str,
    polarity_tag: &str,
    hierarchy_path: &str,
    quality_tier: &str,
    tree_node_id: &str,
    section_ref: Option<&str>,
    source_csl_id: Option<&str>,
    locator_type: &str,
    locator_value: &str,
    entities: &[&str],
) -> anyhow::Result<()> {
    let tx = conn
        .unchecked_transaction()
        .context("insert_claim: begin transaction")?;

    tx.execute(
        "INSERT INTO claims (
            claim_id, doc_id, claim_text, verbatim_passage,
            polarity_tag, hierarchy_path, quality_tier,
            tree_node_id, section_ref, source_csl_id,
            locator_type, locator_value
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
        params![
            claim_id,
            doc_id,
            claim_text,
            verbatim_passage,
            polarity_tag,
            hierarchy_path,
            quality_tier,
            tree_node_id,
            section_ref,
            source_csl_id,
            locator_type,
            locator_value,
        ],
    )
    .context("insert_claim: INSERT INTO claims")?;

    for entity in entities {
        tx.execute(
            "INSERT INTO claim_entities (claim_id, entity) VALUES (?1, ?2)",
            params![claim_id, entity],
        )
        .context("insert_claim: INSERT INTO claim_entities")?;
    }

    tx.commit().context("insert_claim: commit")?;
    Ok(())
}

/// Insert a contradiction edge, enforcing canonical ordering (a < b).
pub fn insert_edge(
    conn: &rusqlite::Connection,
    edge_id: &str,
    claim_a_id: &str,
    claim_b_id: &str,
    explanation: &str,
    confidence: Option<f64>,
    frame_id: Option<&str>,
) -> anyhow::Result<()> {
    let (a, b) = if claim_a_id < claim_b_id {
        (claim_a_id, claim_b_id)
    } else {
        (claim_b_id, claim_a_id)
    };

    conn.execute(
        "INSERT INTO contradicts_edges (edge_id, claim_a_id, claim_b_id, explanation, confidence, frame_id)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
        params![edge_id, a, b, explanation, confidence, frame_id],
    )
    .context("insert_edge")?;

    Ok(())
}

// ── Queries ──────────────────────────────────────────────────────────

/// Return all contradiction edges involving `claim_id`.
pub fn query_contradictions(
    conn: &rusqlite::Connection,
    claim_id: &str,
) -> anyhow::Result<Vec<ContradictionEdge>> {
    let mut stmt = conn
        .prepare(
            "SELECT edge_id, claim_a_id, claim_b_id, explanation, confidence, detected_at
             FROM contradicts_edges
             WHERE claim_a_id = ?1 OR claim_b_id = ?1",
        )
        .context("query_contradictions: prepare")?;

    let rows = stmt
        .query_map(params![claim_id], |row| {
            Ok(ContradictionEdge {
                edge_id: row.get(0)?,
                claim_a_id: row.get(1)?,
                claim_b_id: row.get(2)?,
                explanation: row.get(3)?,
                confidence: row.get(4)?,
                detected_at: row.get(5)?,
            })
        })
        .context("query_contradictions: query_map")?;

    let mut edges = Vec::new();
    for row in rows {
        edges.push(row.context("query_contradictions: row")?);
    }
    Ok(edges)
}

/// Jaccard pre-filter: find claim pairs sharing entities above `min_jaccard`.
pub fn jaccard_prefilter(
    conn: &rusqlite::Connection,
    min_jaccard: f64,
) -> anyhow::Result<Vec<JaccardCandidate>> {
    let mut stmt = conn
        .prepare(
            "WITH entity_pairs AS (
                SELECT ea.claim_id AS claim_a, eb.claim_id AS claim_b,
                       COUNT(DISTINCT ea.entity) AS shared
                FROM claim_entities ea
                JOIN claim_entities eb ON ea.entity = eb.entity AND ea.claim_id < eb.claim_id
                GROUP BY ea.claim_id, eb.claim_id
            ),
            jaccard_pairs AS (
                SELECT ep.claim_a, ep.claim_b, ep.shared,
                       (SELECT COUNT(*) FROM claim_entities WHERE claim_id = ep.claim_a) AS count_a,
                       (SELECT COUNT(*) FROM claim_entities WHERE claim_id = ep.claim_b) AS count_b
                FROM entity_pairs ep
            )
            SELECT claim_a, claim_b,
                   CAST(shared AS REAL) / (count_a + count_b - shared) AS jaccard
            FROM jaccard_pairs
            WHERE CAST(shared AS REAL) / (count_a + count_b - shared) >= ?1",
        )
        .context("jaccard_prefilter: prepare")?;

    let rows = stmt
        .query_map(params![min_jaccard], |row| {
            Ok(JaccardCandidate {
                claim_a: row.get(0)?,
                claim_b: row.get(1)?,
                jaccard: row.get(2)?,
            })
        })
        .context("jaccard_prefilter: query_map")?;

    let mut candidates = Vec::new();
    for row in rows {
        candidates.push(row.context("jaccard_prefilter: row")?);
    }
    Ok(candidates)
}
