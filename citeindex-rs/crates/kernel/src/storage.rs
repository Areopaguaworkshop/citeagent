//! Storage layout — S5_storage_layout.md
//!
//! Defines the canonical `~/.citeindex/` directory tree and provides
//! `init()` to create it with default configuration files.

use std::fs;
use std::path::{Path, PathBuf};

/// All canonical paths under `CITEINDEX_HOME`.
#[derive(Debug, Clone)]
pub struct StorageLayout {
    /// Root directory (`~/.citeindex` or override).
    pub root: PathBuf,

    // ── config/ ───────────────────────────────────────────
    pub config_dir: PathBuf,
    pub config_toml: PathBuf,
    pub scholarly_ace_toml: PathBuf,
    pub skills_dir: PathBuf,
    pub agents_dir: PathBuf,
    pub taxonomy_dir: PathBuf,
    pub synonyms_dir: PathBuf,
    pub skillpacks_toml: PathBuf,

    // ── ACE playbooks ─────────────────────────────────────
    pub global_playbook: PathBuf,
    pub projects_dir: PathBuf,

    // ── indexes/ ──────────────────────────────────────────
    pub indexes_dir: PathBuf,
    pub document_index_dir: PathBuf,
    pub memory_index_dir: PathBuf,
    pub claim_index_dir: PathBuf,

    // ── documents/ ────────────────────────────────────────
    pub documents_dir: PathBuf,
    pub sources_dir: PathBuf,
    pub structured_dir: PathBuf,
    pub figures_dir: PathBuf,
    pub tables_dir: PathBuf,
    pub transcripts_dir: PathBuf,

    // ── citations/ ────────────────────────────────────────
    pub citations_dir: PathBuf,
    pub argument_graph_db: PathBuf,

    // ── memory/ ───────────────────────────────────────────
    pub memory_dir: PathBuf,
    pub memory_access_db: PathBuf,
    pub sessions_dir: PathBuf,

    // ── lora/ ─────────────────────────────────────────────
    pub lora_dir: PathBuf,
    pub adapters_dir: PathBuf,

    // ── fine_tune/ ────────────────────────────────────────
    pub fine_tune_dir: PathBuf,
    pub fine_tune_samples_dir: PathBuf,
    pub fine_tune_failure_dir: PathBuf,

    // ── traces/ ───────────────────────────────────────────
    pub traces_dir: PathBuf,

    // ── logs/ ─────────────────────────────────────────────
    pub logs_dir: PathBuf,
    pub agent_logs_dir: PathBuf,

    // ── run/ ──────────────────────────────────────────────
    pub run_dir: PathBuf,
    pub agent_pids_dir: PathBuf,

    // ── tmp/ ──────────────────────────────────────────────
    pub tmp_dir: PathBuf,
    pub ingest_tmp_dir: PathBuf,
}

impl StorageLayout {
    /// Build layout from a root directory.
    pub fn new(root: PathBuf) -> Self {
        let config_dir = root.join("config");
        let documents_dir = root.join("documents");
        let memory_dir = root.join("memory");
        let lora_dir = root.join("lora");
        let fine_tune_dir = root.join("fine_tune");
        let logs_dir = root.join("logs");
        let run_dir = root.join("run");
        let tmp_dir = root.join("tmp");
        let indexes_dir = root.join("indexes");

        Self {
            // config/
            config_toml: config_dir.join("config.toml"),
            scholarly_ace_toml: config_dir.join("scholarly_ace.toml"),
            skills_dir: config_dir.join("skills"),
            agents_dir: config_dir.join("agents"),
            taxonomy_dir: config_dir.join("taxonomy"),
            synonyms_dir: config_dir.join("synonyms"),
            skillpacks_toml: config_dir.join("skillpacks.toml"),
            config_dir,

            // ACE playbooks
            global_playbook: root.join("scholar_playbook.toml"),
            projects_dir: root.join("projects"),

            // indexes/
            document_index_dir: indexes_dir.join("document_index"),
            memory_index_dir: indexes_dir.join("memory_index"),
            claim_index_dir: indexes_dir.join("claim_index"),
            indexes_dir,

            // documents/
            sources_dir: documents_dir.join("sources"),
            structured_dir: documents_dir.join("structured"),
            figures_dir: documents_dir.join("figures"),
            tables_dir: documents_dir.join("tables"),
            transcripts_dir: documents_dir.join("transcripts"),
            documents_dir,

            // citations/
            argument_graph_db: root.join("citations").join("argument_graph.db"),
            citations_dir: root.join("citations"),

            // memory/
            memory_access_db: memory_dir.join("memory_access.db"),
            sessions_dir: memory_dir.join("sessions"),
            memory_dir,

            // lora/
            adapters_dir: lora_dir.join("adapters"),
            lora_dir,

            // fine_tune/
            fine_tune_samples_dir: fine_tune_dir.join("samples"),
            fine_tune_failure_dir: fine_tune_dir.join("failure_dataset"),
            fine_tune_dir,

            // traces/
            traces_dir: root.join("traces"),

            // logs/
            agent_logs_dir: logs_dir.join("agents"),
            logs_dir,

            // run/
            agent_pids_dir: run_dir.join("agents"),
            run_dir,

            // tmp/
            ingest_tmp_dir: tmp_dir.join("ingest"),
            tmp_dir,

            root,
        }
    }

    /// Resolve the storage root from CLI flag, env var, or default.
    ///
    /// Priority:
    /// 1. `override_path` (from `--data-dir` CLI flag)
    /// 2. `CITEINDEX_HOME` environment variable
    /// 3. `~/.citeindex` (default)
    pub fn resolve(override_path: Option<&Path>) -> Self {
        let root = if let Some(p) = override_path {
            p.to_path_buf()
        } else if let Ok(env) = std::env::var("CITEINDEX_HOME") {
            PathBuf::from(env)
        } else {
            dirs::home_dir()
                .unwrap_or_else(|| PathBuf::from("."))
                .join(".citeindex")
        };
        Self::new(root)
    }

    /// Return the per-project playbook path.
    pub fn project_playbook(&self, project_id: &str) -> PathBuf {
        self.projects_dir
            .join(project_id)
            .join("scholar_playbook.toml")
    }

    /// Return the per-project playbook history directory.
    pub fn project_playbook_history(&self, project_id: &str) -> PathBuf {
        self.projects_dir.join(project_id).join("playbook_history")
    }

    /// Return the trace directory for a specific date (YYYY-MM-DD).
    pub fn trace_date_dir(&self, date: &str) -> PathBuf {
        self.traces_dir.join(date)
    }
}

/// Initialize the `~/.citeindex/` directory tree.
///
/// Creates all directories and writes default configuration files.
/// If the root already exists, this is a no-op unless `force` is true.
pub fn init(layout: &StorageLayout, force: bool) -> anyhow::Result<()> {
    if layout.root.exists() && !force {
        tracing::info!(
            "CiteIndex home already exists at {:?}, skipping init",
            layout.root
        );
        return Ok(());
    }

    tracing::info!("Initializing CiteIndex home at {:?}", layout.root);

    // Create all directories
    let dirs = [
        &layout.root,
        &layout.config_dir,
        &layout.skills_dir,
        &layout.agents_dir,
        &layout.taxonomy_dir,
        &layout.synonyms_dir,
        &layout.projects_dir,
        &layout.indexes_dir,
        &layout.document_index_dir,
        &layout.memory_index_dir,
        &layout.claim_index_dir,
        &layout.documents_dir,
        &layout.sources_dir,
        &layout.structured_dir,
        &layout.figures_dir,
        &layout.tables_dir,
        &layout.transcripts_dir,
        &layout.citations_dir,
        &layout.memory_dir,
        &layout.sessions_dir,
        &layout.lora_dir,
        &layout.adapters_dir,
        &layout.fine_tune_dir,
        &layout.fine_tune_samples_dir,
        &layout.fine_tune_failure_dir,
        &layout.traces_dir,
        &layout.logs_dir,
        &layout.agent_logs_dir,
        &layout.run_dir,
        &layout.agent_pids_dir,
        &layout.tmp_dir,
        &layout.ingest_tmp_dir,
    ];

    for dir in &dirs {
        fs::create_dir_all(dir)?;
        tracing::debug!("Created {:?}", dir);
    }

    // Write default config files (only if they don't exist or force=true)
    write_default_if_missing(&layout.config_toml, DEFAULT_CONFIG_TOML, force)?;
    write_default_if_missing(
        &layout.scholarly_ace_toml,
        DEFAULT_SCHOLARLY_ACE_TOML,
        force,
    )?;
    write_default_if_missing(
        &layout.global_playbook,
        DEFAULT_SCHOLAR_PLAYBOOK_TOML,
        force,
    )?;
    write_default_if_missing(&layout.skillpacks_toml, DEFAULT_SKILLPACKS_TOML, force)?;

    // Write default agent manifests
    for (filename, content) in DEFAULT_AGENT_MANIFESTS {
        let path = layout.agents_dir.join(filename);
        write_default_if_missing(&path, content, force)?;
    }

    // Write default taxonomy
    write_default_if_missing(
        &layout.taxonomy_dir.join("default.toml"),
        DEFAULT_TAXONOMY_TOML,
        force,
    )?;

    // Write default synonyms
    write_default_if_missing(
        &layout.synonyms_dir.join("default.toml"),
        DEFAULT_SYNONYMS_TOML,
        force,
    )?;

    tracing::info!("CiteIndex home initialized at {:?}", layout.root);
    Ok(())
}

fn write_default_if_missing(path: &Path, content: &str, force: bool) -> anyhow::Result<()> {
    if path.exists() && !force {
        return Ok(());
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, content)?;
    tracing::debug!("Wrote {:?}", path);
    Ok(())
}

// ── Default file templates ────────────────────────────────────

const DEFAULT_CONFIG_TOML: &str = r#"# CiteIndex v12.0 — Master Configuration
# See: instruction/contracts/S5_storage_layout.md

[llm]
# Model routing tiers
cloud_premium = "anthropic/claude-sonnet-4-20250514"
cloud_standard = "anthropic/claude-sonnet-4-20250514"
local_base = "ollama/llama3"
personal = "ollama/llama3"         # with LoRA adapter

[retrieval]
weak_signal_threshold = 0.40
weak_signal_max_hops = 3
weak_signal_deep_limit = 3
weak_signal_deep_model_tier = "cloud_standard"

[score_fusion]
w_bm25 = 0.55
w_hierarchy = 0.15
w_citation_degree = 0.12
w_recency = 0.10
w_claim_density = 0.08

[admission]
full_max_load_pct = 50.0
standard_max_load_pct = 75.0
degraded_max_load_pct = 90.0

[lora]
# active_adapter = "lora-2026-03-20-1500triplets"
# base_model = "llama3"

[api]
port = 7432
# bearer_token = ""
rate_limit_per_min = 60

[traces]
retention_days = 30

[kernel]
python_bin = "python"
"#;

const DEFAULT_SCHOLARLY_ACE_TOML: &str = r#"# CiteIndex v12.0 — ACE Scholar Adaptation Layer Configuration
# See: instruction/contracts/S9_ace_schema.md

[scholarly_ace]
enabled = true
reflector_model_tier = "cloud_standard"
reflector_temperature = 0.0
reflector_max_tokens = 2048
reflector_trigger = "post_commit"       # post_commit | manual | nightly

[curator]
similarity_threshold = 0.75
max_entries_per_section = 12
auto_approve_confidence = 0.90
merkle_commit_on_write = true

[synonym_evolution]
pending_review_max = 50
auto_flush_approved = false

[coverage_gap_feed]
feed_to_gap_agent = true
min_sessions_unfilled = 2
"#;

const DEFAULT_SCHOLAR_PLAYBOOK_TOML: &str = r#"# CiteIndex v12.0 — Global Scholar Playbook
# See: instruction/contracts/S9_ace_schema.md
# This file is managed by the PlaybookCurator. Manual edits are allowed.

[meta]
project_id = ""
domain_path = ""
version = 0
curator_run = ""

[strategies.retrieval]
helpful = []
harmful = []

[strategies.citation]
helpful = []
harmful = []

[strategies.pitfall]
entries = []

[synonym_evolution]
pending_review = []
approved = []

[coverage_gaps]
detected = []
"#;

const DEFAULT_SKILLPACKS_TOML: &str = r#"# CiteIndex v12.0 — Installed Skill Packs Registry
# See: instruction/contracts/S10_skill_packs_schema.md
# Managed by `citeindex skillpack install/uninstall`. Do not edit manually.
"#;

const DEFAULT_TAXONOMY_TOML: &str = r#"# CiteIndex v12.0 — Default Taxonomy
# Hierarchy paths for document classification.
# Format: key = ["child1", "child2"]

[roots]
children = ["cs", "math", "physics", "biology", "medicine", "chemistry",
            "engineering", "social_sciences", "humanities", "law"]

[cs]
children = ["nlp", "ml", "cv", "systems", "theory", "security", "hci", "databases"]

[cs.nlp]
children = ["transformers", "icl", "rag", "summarization", "translation", "parsing"]

[cs.ml]
children = ["deep_learning", "reinforcement_learning", "optimization", "scaling", "generative"]
"#;

const DEFAULT_SYNONYMS_TOML: &str = r#"# CiteIndex v12.0 — Default Synonym Expansion Tables
# Used by BM25 query expansion and ACE synonym evolution.

[synonyms]
LLM = ["large language model", "large language models"]
NLP = ["natural language processing"]
ICL = ["in-context learning"]
CoT = ["chain-of-thought", "chain of thought"]
RAG = ["retrieval-augmented generation", "retrieval augmented generation"]
RL = ["reinforcement learning"]
CV = ["computer vision"]
GAN = ["generative adversarial network", "generative adversarial networks"]
"#;

/// Default agent manifest templates (filename, content).
const DEFAULT_AGENT_MANIFESTS: &[(&str, &str)] = &[
    (
        "coordinator_agent.toml",
        r#"[agent]
name = "CoordinatorAgent"
entry_point = "python -m citeindex.agents.coordinator"

[llm_contract]
model_tier = "cloud_standard"
grounding = "not_required"
temperature = 0.0
max_tokens = 512
output_schema = "query_plan_v1"

[activation]
skill_bind = ["*"]
trigger = "always"
priority = "foreground"

[tools_allowed]
tools = []

[inner_loop]
steps = [
    "PLAN: Decompose compound queries into DAG",
    "THINK: Assign agents to query nodes",
    "ACT: Dispatch to assigned agents in topological order",
]
"#,
    ),
    (
        "librarian_agent.toml",
        r#"[agent]
name = "LibrarianAgent"
entry_point = "python -m citeindex.agents.librarian"

[llm_contract]
model_tier = "cloud_standard"
grounding = "required"
temperature = 0.0
max_tokens = 2048
output_schema = "retrieval_plan_v1"

[activation]
skill_bind = ["literature_review", "gap_identification"]
trigger = "retrieval_needed"
priority = "foreground"

[tools_allowed]
tools = ["tantivy_search", "tree_load", "search_memory"]

[inner_loop]
steps = [
    "PLAN: Determine retrieval strategy from query plan node",
    "THINK: Execute BM25 search via tantivy, apply score fusion",
    "ACT: Assemble context slots from ranked results",
]
"#,
    ),
    (
        "ingest_agent.toml",
        r#"[agent]
name = "IngestAgent"
entry_point = "python -m citeindex.agents.ingest"

[llm_contract]
model_tier = "cloud_standard"
grounding = "required"
temperature = 0.0
max_tokens = 4096
output_schema = "pageindex_tree_v1"

[activation]
skill_bind = ["ingest"]
trigger = "document_submitted"
priority = "foreground"

[tools_allowed]
tools = ["tree_load", "tantivy_index"]

[inner_loop]
steps = [
    "PLAN: Detect resource type (PDF, URL, media)",
    "THINK: Run ingestion pipeline (OCR, GROBID, layout detection)",
    "ACT: Build PageIndex JSON Tree, compute Merkle hash, index in tantivy",
]
"#,
    ),
    (
        "claim_extraction_agent.toml",
        r#"[agent]
name = "ClaimExtractionAgent"
entry_point = "python -m citeindex.agents.claim_extraction"

[llm_contract]
model_tier = "cloud_standard"
grounding = "required"
temperature = 0.0
max_tokens = 2048
output_schema = "claim_array_v1"

[activation]
skill_bind = ["claim_extraction", "ingest"]
trigger = "post_ingest"
priority = "background"

[tools_allowed]
tools = ["tree_load", "tantivy_search"]

[inner_loop]
steps = [
    "PLAN: Load PageIndex Tree sections",
    "THINK: Extract factual claims from each section",
    "ACT: Output Vec<Claim> with polarity tags and entities",
]
"#,
    ),
    (
        "contradiction_agent.toml",
        r#"[agent]
name = "ContradictionAgent"
entry_point = "python -m citeindex.agents.contradiction"

[llm_contract]
model_tier = "cloud_premium"
grounding = "required"
temperature = 0.0
max_tokens = 2048
output_schema = "contradiction_edges_v1"

[activation]
skill_bind = ["contradiction_detection"]
trigger = "new_claims_indexed"
priority = "background"

[tools_allowed]
tools = ["tantivy_search", "ag_query_contradictions", "tree_load"]

[inner_loop]
steps = [
    "PLAN: Stage 1 — tantivy entity jaccard pre-filter on claim_index",
    "THINK: Stage 2 — LLM pairwise comparison on candidate pairs",
    "ACT: Write CONTRADICTS edges to ArgumentGraph",
]
"#,
    ),
    (
        "gap_identification_agent.toml",
        r#"[agent]
name = "GapIdentificationAgent"
entry_point = "python -m citeindex.agents.gap_identification"

[llm_contract]
model_tier = "cloud_standard"
grounding = "required"
temperature = 0.3
max_tokens = 2048
output_schema = "gap_report_v1"

[activation]
skill_bind = ["gap_identification"]
trigger = "/gap command"
priority = "foreground"

[tools_allowed]
tools = ["tantivy_search", "tree_load", "search_memory"]

[inner_loop]
steps = [
    "PLAN: Identify required aspects from goal state",
    "THINK: Search corpus for coverage of each aspect",
    "ACT: Report uncovered aspects with suggested search terms",
]
"#,
    ),
    (
        "literature_review_agent.toml",
        r#"[agent]
name = "LiteratureReviewAgent"
entry_point = "python -m citeindex.agents.literature_review"

[llm_contract]
model_tier = "cloud_premium"
grounding = "required"
temperature = 0.3
max_tokens = 4096
output_schema = "literature_review_v1"

[activation]
skill_bind = ["literature_review"]
trigger = "default"
priority = "foreground"

[tools_allowed]
tools = ["tantivy_search", "tree_load", "search_memory", "ag_query_contradictions"]

[inner_loop]
steps = [
    "PLAN: Build retrieval strategy from query plan",
    "THINK: Multi-hop retrieval with citation expansion",
    "ACT: Synthesize answer with inline citations [Author, Year]",
]
"#,
    ),
    (
        "hierarchy_classification_agent.toml",
        r#"[agent]
name = "HierarchyClassificationAgent"
entry_point = "python -m citeindex.agents.hierarchy_classification"

[llm_contract]
model_tier = "cloud_standard"
grounding = "required"
temperature = 0.0
max_tokens = 1024
output_schema = "hierarchy_path_v1"

[activation]
skill_bind = ["ingest", "claim_extraction"]
trigger = "deterministic_confidence < 0.70"
priority = "generation"

[tools_allowed]
tools = ["tree_load"]

[inner_loop]
steps = [
    "PLAN: Load taxonomy from config/taxonomy/*.toml",
    "THINK: Keyword match against taxonomy nodes (deterministic)",
    "ACT: If confidence < 0.70, LLM fallback to suggest path",
]
"#,
    ),
    (
        "structure_agent.toml",
        r#"[agent]
name = "StructureAgent"
entry_point = "python -m citeindex.agents.structure"

[llm_contract]
model_tier = "cloud_premium"
grounding = "required"
temperature = 0.3
max_tokens = 4096
output_schema = "argument_flow_outline_v1"

[activation]
skill_bind = ["structure"]
trigger = "/structure command"
priority = "generation"

[tools_allowed]
tools = ["tantivy_search", "ag_query_contradictions", "tree_load", "regex_search"]

[inner_loop]
steps = [
    "PLAN: Load PageIndex trees and ArgumentGraph CONTRADICTS edges",
    "THINK: Map claims to logical dependencies (foundational vs contested)",
    "ACT: LLM suggests outline with headings, claims, dependencies, coverage",
]
"#,
    ),
    (
        "pageindex_retrieval_agent.toml",
        r#"[agent]
name = "PageIndexRetrievalAgent"
entry_point = "python -m citeindex.agents.pageindex_retrieval"

[llm_contract]
model_tier = "cloud_standard"
grounding = "required"
temperature = 0.0
max_tokens = 4096
output_schema = "retrieval_result_v1"

[activation]
skill_bind = ["pageindex_search", "reasoning_retrieval"]
trigger = "reasoning_query"
priority = "foreground"

[tools_allowed]
tools = ["tree_load", "tantivy_search"]

[inner_loop]
steps = [
    "PLAN: Load PageIndex tree structure for target documents",
    "THINK: LLM reasons over tree hierarchy to identify relevant sections",
    "ACT: Fetch page content for identified sections, return ranked evidence",
]
"#,
    ),
];
