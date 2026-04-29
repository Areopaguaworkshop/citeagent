# CiteIndex Project Report

> "AI research knowledge infrastructure with citation indexing and Merkle-verified retrieval."
> — `pyproject.toml`, v0.11.0

---

## 1. Project Overview

CiteIndex is a **hybrid Rust + Python** academic research system whose defining promise is: *every claim is traced, verified, and cited — no hallucinations*. It ingests documents (PDF, URL, media, DJVU, Office), extracts structured citation metadata, builds Merkle-verified text node trees, indexes them with deterministic BM25 (no embeddings), and answers research queries with SHA-256–anchored evidence chains.

| Aspect | Detail |
|--------|--------|
| **Version** | 0.11.0 |
| **Author** | ajia \<yyjfwoaini@gmail.com\> |
| **License** | MIT |
| **Python** | ≥ 3.12 |
| **Entry point** | `citeindex = citeindex.cli:main` |
| **Build system** | hatchling 1.26.3 |

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Rust Layer (citeindex-rs)                │
│  ┌──────────┐   ┌──────────┐   ┌───────────┐   ┌─────────┐  │
│  │   TUI     │   │  Kernel  │   │   Core    │   │ Plugins │  │
│  │ (ratatui) │──▶│ (DKEE)  │──▶│ (Engine)  │   │ Manager │  │
│  └──────────┘   └────┬─────┘   └─────┬─────┘   └─────────┘  │
│                      │               │                       │
│           ┌──────────┴───────────────┘                       │
│           │  AgentRuntime (3 NDJSON bridges)                │
│           │  Coordinator │ Librarian │ Ingest                │
│           └──────────┬───────────────────────────────────────┼─┐
└──────────────────────┼───────────────────────────────────────┘ │
                       │ stdin/stdout NDJSON                     │
┌──────────────────────┼───────────────────────────────────────┐ │
│           Python Layer (citeindex/)                           │ │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌────────────────┐   │ │
│  │Ingestion│ │ Agents  │ │    CLI    │ │ Citation Style │   │ │
│  │ Pipeline│ │(7-step) │ │ (argparse)│ │  (citeproc)    │   │ │
│  └─────────┘ └─────────┘ └──────────┘ └────────────────┘   │ │
│           ┌──────────────────────────────┐                    │ │
│           │  Agent Harness (CLI wrapper) │                    │ │
│           │  (cli-anything-citeindex)    │                    │ │
│           └──────────────────────────────┘                    │ │
└──────────────────────────────────────────────────────────────┘──┘
```

### 2.1 Rust Workspace (`citeindex-rs/`)

Four crates in a Cargo workspace:

| Crate | Role | Key Source |
|-------|------|-----------|
| **core** | Engine orchestrator, config, IPC bridge, memory, Merkle | `engine.rs`, `ipc.rs`, `memory.rs`, `merkle.rs`, `config.rs` |
| **kernel** | DKEE state machine, 17 tools, Tantivy+SQLite storage, argument graph, traces, recovery, API | `state_machine.rs`, `storage.rs`, `tools/mod.rs`, `argument_graph.rs`, `api.rs`, `recovery.rs`, 26 modules total |
| **tui** | Terminal UI: chat/search/ingest/pageindex modes, panels, themes | `app.rs`, `mode.rs`, `ui.rs`, `panels.rs`, `theme.rs`, `input.rs` |
| **plugins** | Plugin lifecycle: discover, install (local/git), enable/disable | `manager.rs`, `runner.rs`, `manifest.rs` |

**DKEE State Machine** — The kernel drives execution through 8 states:

```
INIT → PLAN → THINK → ACT → VERIFY → COMMIT → REFLECT → DONE
```

With guard validation at each transition, and a 6-tier recovery chain (R1 retry → R6 human-in-the-loop) for failures at ACT→VERIFY or VERIFY→COMMIT.

**17 Kernel Tools** — Agents can call back into the Rust kernel via NDJSON `tool_call` messages:

| Tool | Purpose |
|------|---------|
| `search_documents` | Tantivy full-text search on document index |
| `search_claims` | Tantivy search on claim index |
| `search_memory` | Tantivy search on memory index |
| `index_document` | Add document to Tantivy index |
| `index_claim` | Add claim to claim index |
| `delete_document` | Remove document from indexes |
| `ag_query_claims` | SQLite argument graph: query claims |
| `ag_query_contradictions` | SQLite argument graph: find contradictions |
| `ag_write_edge` | SQLite argument graph: add edge |
| `merkle_compute` | Compute SHA-256 Merkle hash |
| `merkle_verify` | Verify Merkle proof |
| `csl_render` | Render CSL-JSON to formatted citation |
| `tree_load` | Load PageIndex tree from storage |
| `tree_traverse` | Navigate PageIndex tree hierarchy |
| `regex_search` | Regular expression search on stored text |
| `memory_save` | Persist memory entry (JSONL + Tantivy) |
| `tantivy_search` / `tantivy_index` | Direct Tantivy operations |

**Storage Layout** — `~/.citeindex/` (or `corpus/.citeindex/`):

```
~/.citeindex/
├── config/           # Default TOML configs, agent manifests, taxonomy, synonyms
├── indexes/          # Tantivy: document_index, claim_index, memory_index
├── documents/
│   ├── sources/      # Original PDFs (immutable)
│   ├── structured/   # PageIndex trees (.citeindex.json)
│   └── transcripts/  # Media transcripts (.transcript.json)
├── citations/        # CSL-JSON artifacts
├── memory/           # JSONL per-thread chat memory
├── lora/             # LoRA fine-tune data
├── fine_tune/        # Training sets
├── traces/           # JSONL execution traces (YYYY-MM-DD/)
├── logs/             # Runtime logs
├── run/              # PID files, sockets
└── tmp/              # Temporary scratch
```

### 2.2 Python Package (`citeindex/`)

#### Core Modules

| Module | Purpose |
|--------|---------|
| `cli.py` | CLI entry point: `ingest`, `search`, `chat`, `memory`, `plugin` subcommands |
| `main.py` | Legacy `CitationExtractor` — URL-based citation extraction |
| `model.py` | `CitationLLM` — DSPy-based LLM extraction (book/thesis/journal/chapter/page numbers); `ImprovedPageNumberExtractor` — sophisticated PDF page detection |
| `llm.py` | `get_llm_model()` — returns `dspy.LM` configured for Ollama or Gemini |
| `search.py` | `search_for_missing_info()` — local Perplexica API search for missing metadata |
| `utils.py` | 40+ utilities: PDF handling, CSL conversion, author parsing, URL cleaning |
| `citation_style.py` | `format_bibliography()` — renders CSL-JSON via citeproc-py with bundled CSL styles |
| `type_judge.py` | Rule-based document type classification (thesis/article/book/etc.) |
| `vertical_handler.py` | Vertical CJK text detection (PPStructureV3/PaddleOCR) and rotation handling |
| `vertical_llm.py` | `VerticalCitationLLM` — extends CitationLLM for traditional Chinese/Japanese vertical text |
| `ocr_lang_detect.py` | FastText language detection → Tesseract OCR language string |
| `ocr_text_clean_before_llm.py` | OCR text cleaning: blank page filtering, content detection, noise removal |
| `file_converter.py` | Office/DJVU → PDF conversion (LibreOffice, ddjvu, PyMuPDF) |
| `page_extractor.py` | `PageNumberExtractor` — extract page numbers from MinerU middle JSON |

#### Agent Pipeline (`citeindex/agents/`)

Seven deterministic agents in a strict pipeline:

```
┌───────────┐    ┌──────────┐    ┌──────────────┐    ┌────────────┐
│ Ingestion │───▶│ Indexing │───▶│ Query Planner│───▶│ Retrieval  │
└───────────┘    └──────────┘    └──────────────┘    └─────┬──────┘
                                                            │
                     ┌──────────────┐    ┌────────────┐    │
                     │  Integrity  │◀───│ Generation │◀───┘
                     └──────────────┘    └─────┬──────┘
                                               │
                                    ┌──────────┴──────┐
                                    │ Clarification   │
                                    │ (if ambiguous)  │
                                    └─────────────────┘
```

| Agent | Input | Output | Mechanism |
|-------|-------|--------|-----------|
| **CorpusLoader** | Corpus root path | `all_nodes`, `csl_registry`, `merkle_registry` | Walk corpus dirs, load JSON artifacts |
| **IndexingAgent** | Nodes + CSL | `inverted_index`, `section_index`, `cross_source_links` | `simple_v1` tokenizer (CJK-aware), BM25-style postings |
| **QueryPlanner** | User query string | `QueryPlan` (intent, terms, filters, retrieval_policy) | Heuristic intent detection, CJK phrase preservation |
| **RetrievalAgent** | QueryPlan + Index | `ranked_nodes[]` | 3-stage: metadata filter → BM25 scoring → trace filter |
| **ClarificationAgent** | Ambiguous QueryPlan | `ClarificationPacket` (up to 3 questions) | LLM-generated questions when query is vague |
| **GenerationAgent** | Ranked nodes + CSL | `AnswerMachine` (evidence items) + `answer_human` (Markdown) | Extractive (default) or LLM-based; Chicago author-date citations |
| **IntegrityVerifier** | AnswerMachine + registries | `IntegrityReport` (approved/rejected) | 5-check fail-closed: node exists, hash match, Merkle proof, citation key, claim evidence |

#### Ingestion Pipeline (`citeindex/ingestion/`)

The `CiteIndexIngestionOrchestrator` routes input to one of four sub-pipelines:

**Digital PDF** (`pipelines/digital_pdf.py`):
```
PDF → GROBID (metadata) → MinerU (layout) → DSPy reconciliation
    → document structure (pages/columns/paragraphs/lines)
    → Merkle tree → retrieval index
```

**Scanned PDF** (`pipelines/scanned_pdf.py`):
```
PDF → OCRmyPDF (normalize) → PaddleOCR (vertical detect) → MinerU (layout)
    → Tesseract (text) → GROBID (citations) → document structure
    → Merkle tree → retrieval index
```

**URL Article** (`pipelines/url_article.py`):
```
URL → Playwright/requests (fetch) → trafilatura (content)
    → Zotero (metadata) → CSL JSON → deterministic chunking
    → hashes → Merkle tree → store
```

**Media** (`pipelines/media.py`):
```
URL/File → yt-dlp (download) → ffmpeg (audio) → WhisperX (transcription)
    → pyannote (diarization, optional) → CSL JSON → chunking
    → hashes → Merkle tree → store
```

#### v12 Runtime (`agents/v12_runtime.py`)

The NDJSON protocol adapter (≈950 lines) bridges Rust kernel ↔ Python agents:

| Agent | Available Kernel Tools |
|-------|----------------------|
| CoordinatorAgent | search_memory, tantivy_search, memory_save, tree_load, tree_traverse, csl_render |
| LibrarianAgent | tantivy_search, tree_load, search_memory |
| IngestAgent | tree_load, tantivy_index, merkle_compute |
| ClaimExtractionAgent | tree_load, tree_traverse, index_claim, merkle_compute |
| ContradictionAgent | search_claims, ag_query_claims, ag_query_contradictions, ag_write_edge |
| GapIdentificationAgent | search_documents, search_claims, tree_load |
| LiteratureReviewAgent | search_documents, search_claims, search_memory, csl_render, tree_load, tree_traverse |
| HierarchyClassificationAgent | tree_load |
| StructureAgent | search_claims, ag_query_contradictions, tree_load, regex_search |

**Crash recovery**: Up to 3 respawns with exponential backoff (1s, 5s, 15s). Counter resets after 1 hour of stability.

### 2.3 Agent Harness (`agent-harness/`)

A separate Python package `cli-anything-citeindex` providing a richer CLI on top of the core engine:

```
cli-anything-citeindex
├── project   — corpus management
├── ingest    — document ingestion
├── search    — search queries
├── chat      — chat with citations
├── memory    — memory search & listing
├── export    — bibliography rendering
├── session   — session management (undo/redo/save/load)
└── repl      — interactive REPL with prompt_toolkit
```

Uses `CiteIndexBackend` as a single adapter wrapping the `citeindex` Python package.

---

## 3. Workflows in Detail

### 3.1 Workflow: Ingestion (Data In)

```
User → citeindex ingest <path_or_url>
         │
         ▼
    ┌─────────────────────────────────┐
    │  CiteIndexIngestionOrchestrator │
    │  detect_resource_type()         │
    └───────┬─────────────────────────┘
            │
   ┌────────┼──────────┬─────────────┬──────────────┐
   ▼        ▼          ▼             ▼              ▼
digital_pdf scanned_pdf  url_article   media    office/djvu
   │        │          │             │         (convert→pdf)
   │        │          │             │              │
   ▼        ▼          ▼             ▼              ▼
┌──────┐ ┌──────┐ ┌──────────┐ ┌───────┐    ┌──────────┐
│GROBID│ │OCRmy │ │Playwright│ │yt-dlp │    │LibreOffice│
│metadata│ │PDF  │ │trafilatura│ │ffmpeg │    │/ddjvu    │
└──┬───┘ └──┬───┘ └────┬─────┘ └───┬───┘    └─────┬────┘
   │        │          │           │              │
   ▼        ▼          ▼           ▼              ▼
┌──────┐ ┌──────┐ ┌──────────┐ ┌───────┐    ┌──────────┐
│MinerU│ │Paddle│ │  Zotero   │ │WhisperX│   │(delegate  │
│layout│ │OCR   │ │  metadata │ │transcr.│   │to digital │
└──┬───┘ └──┬───┘ └────┬─────┘ └───┬───┘    │or scanned)│
   │        │          │           │         └──────────┘
   ▼        ▼          ▼           ▼
┌─────────────────────────────────────┐
│  DSPy reconciliation + CSL JSON     │
│  Document structure builder          │
│  Merkle tree generation (SHA-256)   │
│  Retrieval index generation          │
└──────────────┬──────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│  Standardize CSL JSON                │
│  (add ci_ extensions: content_hash,  │
│   merkle_root, source_type,          │
│   ingestion_timestamp)               │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│  Store to corpus/                    │
│  ├── csl.json                        │
│  ├── document.json                   │
│  ├── merkle.json                     │
│  ├── index.json                      │
│  └── ingestion_output.json           │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│  v12: Tantivy index + .citeindex/    │
│  (if Rust kernel is running)         │
└──────────────────────────────────────┘
```

### 3.2 Workflow: Search (Data Out — Deterministic)

```
User → citeindex search "query terms"
         │
         ▼
    ┌──────────────┐
    │ CorpusLoader │  ← Walk corpus/, load all csl.json/document.json/merkle.json
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ IndexingAgent│  ← simple_v1 tokenizer, CJK-aware, stop-word filtered
    │              │    Build: inverted_index, section_index, cross_source_links
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ QueryPlanner │  ← Detect intent (fact/comparison/timeline/definition/citation_lookup)
    │              │    Extract exact phrases (CJK-preserved)
    │              │    Build must/should metadata filters
    │              │    Select retrieval policy
    └──────┬───────┘
           │
           ▼
    ┌─────────────────────────────────────────┐
    │           RetrievalAgent                │
    │  Stage 1: Metadata filter               │
    │    → Filter nodes by author/year/type    │
    │  Stage 2: BM25 scoring (k1=1.2, b=0.75) │
    │    + phrase boost (+5.0)                 │
    │    + section boost (+3.0)                │
    │  Stage 3: Trace filter                   │
    │    → Drop nodes missing sha256/source_id │
    │  Tie-break: score → phrase → section     │
    │             → page → node_id             │
    └──────┬──────────────────────────────────┘
           │
           ▼
    ┌──────────────────────────────────────────┐
    │ Enrich with citations                    │
    │ → Lookup CSL record by source_id         │
    │ → format_bibliography() via citeproc-py   │
    │ → Return ranked results with citations    │
    └──────────────────────────────────────────┘
```

### 3.3 Workflow: Chat (Data Out — LLM + Integrity)

```
User → citeindex chat --prompt "question"
         │
         ▼
    ┌───────────────┐
    │ CorpusLoader  │ ──▶ IndexingAgent ──▶ QueryPlanner
    └───────────────┘
                                        │
                              ┌─────────┴─────────┐
                              │ clarification_     │
                              │ required?          │
                              └────┬──────────┬────┘
                              Yes  │          │ No
                                   ▼          │
                          ┌──────────────┐    │
                          │Clarification │    │
                          │Agent         │    │
                          │(up to 3 ?s)  │    │
                          └──────────────┘    │
                                   │          │
                                   ▼          ▼
                           ┌─────────────────────┐
                           │  RetrievalAgent     │
                           │  (3-stage BM25)     │
                           └──────────┬──────────┘
                                      │
                                      ▼
                           ┌─────────────────────┐
                           │  GenerationAgent     │
                           │                      │
                           │  Build EvidenceItems │
                           │  ├─ node_id          │
                           │  ├─ source_id        │
                           │  ├─ sha256            │
                           │  ├─ merkle_proof[]   │
                           │  ├─ citation_key     │
                           │  └─ citation_rendered│
                           │                      │
                           │  Generate answer:    │
                           │  ├─ Extractive:     │
                           │  │  blockquotes with │
                           │  │  inline citations│
                           │  └─ LLM-based:      │
                           │     "Based ONLY on  │
                           │      evidence…"     │
                           └──────────┬──────────┘
                                      │
                                      ▼
                           ┌─────────────────────┐
                           │  IntegrityVerifier  │
                           │  (5 checks, fail-   │
                           │   closed)           │
                           │                     │
                           │  1. Node exists     │
                           │  2. Hash match      │
                           │  3. Merkle proof    │
                           │  4. Citation key    │
                           │  5. Claim evidence  │
                           │                     │
                           │  Any fail → REJECT  │
                           │  All pass → APPROVE │
                           └──────────┬──────────┘
                                      │
                                      ▼
                           ┌─────────────────────┐
                           │  Save Memory        │
                           │  JSONL per thread   │
                           │  v12: Tantivy +     │
                           │  SQLite memory      │
                           └─────────────────────┘
```

**Chat output format:**

```json
{
  "status": "ok",
  "query_id": "q-abc123def456",
  "answer_human": "## Query: ...\n> Evidence text\n> — [Author Year] (node: `s5.1.p5`)",
  "answer_machine": {
    "schema_version": "1.0.0",
    "query_id": "...",
    "answer": "...",
    "evidence": [
      {
        "node_id": "s5.1.p5",
        "sha256": "abc123...",
        "document_merkle_root": "def456...",
        "merkle_proof": ["leaf_hash", "...", "root_hash"],
        "citation_key": "Author2023Title",
        "citation_rendered": "Author, A. (2023). Title. Journal, 1(2), 3–4."
      }
    ]
  },
  "integrity": {
    "status": "approved",
    "checks": [...],
    "violations": []
  },
  "thread": "default"
}
```

### 3.4 Workflow: v12 Runtime (Rust ↔ Python IPC)

```
┌────────────────────────────────────────────────────────┐
│                     Rust Kernel                         │
│                                                        │
│  ┌─────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   TUI    │───▶│ DKEE State   │───▶│ ToolDispatc. │  │
│  │ (ratatui)│    │ Machine      │    │ (17 tools)   │  │
│  └─────────┘    └──────┬───────┘    └──────┬───────┘  │
│                        │                    │           │
│                        ▼                    │           │
│                 ┌──────────────┐            │           │
│                 │ AgentRuntime │◄───────────┘           │
│                 │ (3 bridges)  │  tool_response         │
│                 └──────┬───────┘                       │
└────────────────────────┼────────────────────────────────┘
                         │ NDJSON over stdin/stdout
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
  ┌────────────┐ ┌────────────┐ ┌────────────┐
  │Coordinator │ │ Librarian  │ │   Ingest   │
  │  Agent     │ │  Agent     │ │   Agent    │
  │ (Python)   │ │ (Python)   │ │ (Python)   │
  └────────────┘ └────────────┘ └────────────┘
```

**Protocol sequence:**

```
Kernel                  Agent
  │                       │
  │──── init ────────────▶│
  │◀─── init_ack ────────│  (protocol version check)
  │                       │
  │──── request ────────▶│  {task_id, inputs}
  │                       │
  │  ┌─── tool_call ──────│  (agent needs kernel tool)
  │  │                    │
  │──▶ tool_response ────▶│  (kernel executes tool, returns result)
  │  │                    │
  │  │◀── progress ───────│  (optional progress updates)
  │  │◀── llm_report ────│  (optional LLM trace spans)
  │  └                   │
  │◀─── result ──────────│  {output, output_hash, resource_usage}
  │                       │
  │   OR                  │
  │◀─── error ────────────│  {classification, message}
  │                       │
  │  (loop back to IDLE)  │
```

### 3.5 Workflow: Agent-Harness REPL

```
User → cli-anything-citeindex repl
         │
         ▼
    ┌──────────────────────────────────┐
    │  prompt_toolkit REPL            │
    │  (autocomplete, history)         │
    └───────┬──────────────────────────┘
            │
   ┌────────┼──────────┬──────────────┬─────────────┐
   ▼        ▼          ▼              ▼             ▼
project   ingest     search         chat         memory
   │        │          │              │             │
   ▼        ▼          ▼              ▼             ▼
CiteIndexBackend ──▶ CiteIndexIngestionOrchestrator
                  ──▶ ChatPipeline / SearchPipeline
                  ──▶ CiteIndexSession (undo/redo)
```

---

## 4. Data Models

### 4.1 PageIndex JSON Tree (Canonical Document Schema)

```
Level 0: CSL-JSON root
  ├─ id, type, title, author, issued, DOI, URL
  └─ ci_* extensions (content_hash, merkle_root, source_type, ingestion_timestamp)

Level 1: Major sections
  ├─ heading, section_type, page_range
  └─ children: [Level 2]

Level 2: Subsections
  ├─ heading, section_number
  └─ children: [Level 3]

Level 3: Locators
  ├─ page_number / paragraph_number / timestamp
  └─ text_blocks[] / transcript_text

Level 4: Lines (primary sources only)
  ├─ line_number, text, line_type
  └─ (leaf nodes with SHA-256)
```

### 4.2 Answer Machine (Unified Output Schema)

```json
{
  "schema_version": "1.0.0",
  "query_id": "q-...",
  "answer": "...",
  "evidence": [
    {
      "node_id": "s5.1.p5",
      "source_id": "Author2023Title",
      "sha256": "abc123...",
      "document_merkle_root": "def456...",
      "merkle_proof": ["step1_hash", "step2_hash", "root_hash"],
      "citation_key": "Author2023Title",
      "citation_rendered": "Author, A. (2023). Title. Journal, 1(2), 3–4.",
      "section_path": "Chapter 5 > Section 1"
    }
  ]
}
```

### 4.3 Merkle Tree Structure

Every text node gets a SHA-256 hash. The tree aggregates:

```
line → paragraph → column → page → document → merkle_root
```

Each evidence item in an answer walks from its leaf hash up to the document root, producing a **Merkle proof** that can be independently verified.

---

## 5. Key Dependencies

| Category | Dependency | Purpose |
|----------|-----------|---------|
| **LLM** | `dspy-ai>=2.6.27` | DSPy programmatic LLM calls |
| | `litellm>=1.83.0` | Multi-backend LLM routing |
| **OCR** | `ocrmypdf` | PDF normalization and OCR |
| | `paddleocr`, `paddlepaddle` | CJK vertical text detection |
| | `fasttext` | Language detection for OCR |
| **PDF** | `pymupdf` | PDF manipulation |
| | `mineru[all]>=2.6.4` | Layout analysis (magic-pdf) |
| **Citation** | `citeproc-py` | CSL-JSON → formatted bibliography |
| **Web** | `crawl4ai` | Web crawling |
| | `trafilatura` | HTML → clean text extraction |
| | `playwright` | JS-rendered page fetching |
| **Media** | `whisperx` | Audio transcription |
| | `pyannote-audio` | Speaker diarization |
| | `pymediainfo` | Media metadata extraction |
| **CJK** | `pypinyin` | Chinese pinyin indexing |
| **Storage** | (Rust) `tantivy` | Full-text search index |
| | (Rust) `rusqlite` | SQLite for argument graph |
| **CLI** | `click` | Agent-harness CLI |
| | `prompt-toolkit` | REPL with completion |
| **TUI** | (Rust) `ratatui` | Terminal UI framework |

---

## 6. Contract System (`.agent/`, `instruction/contracts/`)

The project uses YAML contract files to define the schema for every pipeline stage:

| Contract | Scope |
|----------|-------|
| `I1_tool_dispatcher_contract.md` | 16-tool kernel syscall layer (LOCKED) |
| `I2_agent_runtime_contract.md` | NDJSON IPC protocol (LOCKED) |
| `S1_citeindex_tree_schema.md` | PageIndex JSON Tree schema (LOCKED) |
| `S5_storage_layout.md` | Full directory layout (LOCKED) |
| Stage schemas: `ingestion_input.yaml` → `ingestion_output.yaml` → `indexing_input.yaml` → … → `integrity_output.yaml` | Pipeline stage I/O |
| `answer_machine.yaml` | Unified answer schema |

Pipeline definitions in `.agent/pipeline/`:
- `citeindes_master_ingestion.yaml` — Master orchestrator
- `digital_pdf_ingestion.yaml` — 7-stage digital PDF pipeline
- `scanned_pdf_ingestion.yaml` — 8-stage scanned PDF pipeline
- `url_article_ingestion.yaml` — 12-step URL pipeline
- `media_ingestion.yaml` — 14-step media pipeline
- `chat_mode.yaml` — Legacy chat flow (LEGACY)
- `search_subcommand.yaml` — Search pipeline
- `rust_core_orchestration.yaml` — Rust core orchestrator
- `frontend_ui_rust.yaml` — Rust TUI frontend

**Precedence**: `instruction/contracts/*` > `instruction/Summary.md` > Rust implementation > `.agent/` (legacy)

---

## 7. Design Principles

1. **No embeddings** — All retrieval is BM25 keyword search, deterministic and reproducible
2. **Merkle-verified** — Every text node has SHA-256; document integrity is a Merkle tree
3. **Fail-closed integrity** — Any hash/Merkle/citation check failure → reject the entire answer
4. **Citation cascade** — GROBID (deterministic) → DSPy+LLM (fallback) → PDF metadata (last resort)
5. **7 deterministic agents** — Fixed pipeline, no dynamic agent chaining
6. **CJK-first** — Vertical text detection, CJK phrase preservation in search, pinyin indexing
7. **Source-of-truth hierarchy** — Contracts first, then docs, then implementation, then legacy
8. **Session memory** — JSONL per thread with Merkle DAG integrity; v12 adds Tantivy+SQLite

---

## 8. Test Coverage

| Area | Tests | Status |
|------|-------|--------|
| Bibliography formatting | `tests/test_style.py` (2 tests) | ✅ |
| Citation extraction | `citeindex/tests/test_citation.py` | In-package |
| LLM extraction | `citeindex/tests/test_llm_extraction.py` | In-package |
| CJK phrase search | `citeindex/tests/test_search_cjk_phrase.py` | In-package |
| v12 runtime | `citeindex/tests/test_v12_runtime.py` | In-package |
| Rust (in-file `#[cfg(test)]`) | State machine, Merkle, memory, storage, traces, API, CLI | ✅ |
| Agent-harness | `test_full_e2e.py`, `test_core.py` | In-package |
| **Integration/e2e** | No formal CI pipeline detected | ⚠️ |

---

## 9. Example Corpus

The `corpus/` directory contains **243 ingested document folders**, primarily from the "光从东方来" (Light from the East) website covering Syriac studies, Eastern Orthodox theology, and Chinese classical texts. The `example/` directory has **56 CSL-JSON/YAML files** demonstrating the range of source types: academic papers, CJK classical texts, URL citations, YouTube videos, OCR manuscripts.

---

*Report generated from project source analysis. Last updated: 2026-04-26.*