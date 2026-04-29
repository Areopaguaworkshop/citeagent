# PageIndex Integration Plan

## What Is PageIndex?

[VectifyAI/PageIndex](https://github.com/VectifyAI/PageIndex) is a **vectorless, reasoning-based RAG** system. Instead of chunking + embedding + vector similarity, it:

1. **Builds a hierarchical tree index** from a PDF (like a smart Table of Contents)
2. **Uses LLM reasoning** to navigate that tree and find relevant pages for a query

The tree looks like:
```json
{
  "doc_name": "paper.pdf",
  "structure": [
    {
      "title": "Financial Stability",
      "node_id": "0006",
      "start_index": 21,
      "end_index": 22,
      "summary": "The Federal Reserve ...",
      "nodes": [
        { "title": "Monitoring Vulnerabilities", "node_id": "0007", "start_index": 22, "end_index": 28, "summary": "..." }
      ]
    }
  ]
}
```

It uses **litellm** for LLM calls (supports Ollama natively) and **PyPDF2** for PDF text extraction.

---

## What CiteIndex Already Has (Overlaps & Conflicts)

| Aspect | PageIndex | CiteIndex | Conflict? |
|--------|-----------|-----------|-----------|
| **Tree structure** | `{title, node_id, start_index, end_index, summary, nodes}` — flat page ranges | `PageIndexTree` with `level_0` (CSL metadata) → `level_1..4` (section → subsection → locator → line) — richer, citation-aware | **Schema mismatch** — different JSON shapes |
| **PDF parsing** | PyPDF2 (basic text extraction) | MinerU (OCR, layout detection, multi-column, CJK vertical text, footnote isolation) | CiteIndex is **far superior** for scanned/CJK docs |
| **Page numbering** | Physical PDF page index (1-indexed) | Actual journal page numbers (mapped from CSL JSON or header/footer scanning via `page_extractor.py`) | **Different semantics** — PageIndex's "page 3" = 3rd PDF page; CiteIndex's "page 192" = printed page 192 |
| **Retrieval** | LLM reasoning over tree (agentic, multi-step) | BM25 deterministic keyword search via Tantivy | **Complementary** — not conflicting |
| **LLM framework** | `litellm` (direct completion calls) | `dspy` (structured signatures) | Different APIs but both support Ollama |
| **Citation/integrity** | None — no Merkle hashing, no CSL, no citation rendering | Core feature — SHA-256 per node, Merkle tree, Chicago citations, fail-closed integrity | PageIndex has **no concept of this** |
| **Tree building** | LLM-driven: detects TOC, asks LLM to extract structure, verifies, self-corrects | Rule-based: MinerU layout analysis → `content_list_to_document_structure()` in `mineru.py` | PageIndex tree quality may be better for well-structured PDFs; CiteIndex is better for OCR-heavy docs |

---

## Decisions (Confirmed)

| Question | Decision |
|----------|----------|
| **Q1: Which parts?** | **(c) Both** — Tree-building AND reasoning-based retrieval |
| **Q2: MinerU?** | **(a) Complement** — Keep MinerU for text extraction, use PageIndex LLM for section tree building |
| **Q3: Page numbers?** | **(a) Post-map** — PageIndex builds with physical indices, then map to actual page numbers via `page_extractor.py` |
| **Q4: glm-5.1:cloud scope?** | **(a) PageIndex only** — `ollama/glm-5.1:cloud` for PageIndex operations; keep `qwen3` for existing CiteIndex chat/generation |
| **Q5: Where?** | **(c) Both** — New pipeline (`pageindex_tree.py`) for ingestion + new agent (`pageindex_retrieval.py`) for retrieval |

---

## Implementation Plan

> **Status: All 4 phases complete.**

### Phase 1: Vendor PageIndex + Wire Ollama (`glm-5.1:cloud`) ✅

**Goal:** Get PageIndex running locally with `ollama/glm-5.1:cloud`, no external API.

1. Add `litellm>=1.83.0` to `pyproject.toml` dependencies.
2. Vendor PageIndex core into `citeindex/ingestion/pipelines/pageindex/`:
   - `page_index.py` — tree-building logic (TOC detection, LLM structure extraction, verification loop)
   - `utils.py` — litellm wrappers, JSON extraction, tree utilities
   - `retrieve.py` — `get_document_structure()`, `get_page_content()` for retrieval
   - `config.yaml` — **modified**: `model: "ollama/glm-5.1:cloud"`, not `gpt-4o`
   - `__init__.py`
3. **Skip**: `client.py` (workspace logic — CiteIndex has its own), OpenAI Agents SDK demo.
4. Smoke test: run `page_index_main()` on a corpus PDF with local Ollama.

**Files created:**
```
citeindex/ingestion/pipelines/pageindex/
├── __init__.py
├── page_index.py      (vendored, imports adjusted)
├── utils.py           (vendored, imports adjusted)
├── retrieve.py        (vendored, imports adjusted)
└── config.yaml        (model: ollama/glm-5.1:cloud)
```

### Phase 2: Tree-Building Pipeline (Ingestion) ✅

**Goal:** After MinerU parses a PDF, use PageIndex's LLM to build a better section hierarchy, then convert to CiteIndex's `PageIndexTree` format.

1. Create `citeindex/ingestion/pipelines/pageindex_tree.py`:

   ```
   Input:  pdf_path + MinerU output + CSL JSON + page_number_map
   Output: CiteIndex PageIndexTree JSON (same format as ipc.rs produces)
   ```

   **Data flow:**
   ```
   PDF ──→ PageIndex page_index_main()  ──→ PageIndex tree
                                              │
   MinerU middle.json ──→ page_extractor.py ──→ page_number_map
                                              │
   GROBID ──→ csl.json ─────────────────────→ │
                                              ▼
                              pageindex_to_citeindex_tree()
                                              │
                                              ▼
                              {doc_id}.citeindex.json
   ```

   **Schema conversion (PageIndex → CiteIndex PageIndexTree):**

   | PageIndex field | CiteIndex field | Transform |
   |----------------|----------------|-----------|
   | `structure[].title` | `SectionNode.heading` | Direct |
   | `structure[].node_id` | `SectionNode.node_id` | Prefix with `{doc_id}:section:` |
   | `structure[].start_index` | `SectionNode.page_range` (start) | Post-map via `page_number_map[physical_idx]` |
   | `structure[].end_index` | `SectionNode.page_range` (end) | Post-map via `page_number_map[physical_idx]` |
   | `structure[].summary` | `SectionNode.section_type` metadata | Store as extension field |
   | `structure[].nodes` | `SectionNode.children` → `SubsectionNode` | Recursive conversion |
   | (leaf nodes) | `LocatorNode` with `page_number`, `text_blocks` | MinerU text blocks attached per page range |
   | — | `level_0` (CSL metadata) | From GROBID/existing `csl.json` |
   | — | `ci_merkle_hash`, Merkle proofs | From existing Merkle pipeline |

2. Wire into `CiteIndexIngestionOrchestrator.ingest()` in `master.py`:
   - After MinerU parsing succeeds, run PageIndex tree-building as **optional enhancement**
   - If PageIndex succeeds → use its tree as section hierarchy
   - If PageIndex fails (LLM timeout, bad JSON) → fall back to current `content_list_to_document_structure()`
   - Add `--use-pageindex` flag to CLI / `IngestionConfig.use_pageindex: bool = False`

### Phase 3: Reasoning-Based Retrieval Agent ✅

**Goal:** Add LLM-driven tree-search retrieval as an alternative to BM25.

1. Create `citeindex/agents/pageindex_retrieval.py`:
   - Implements v12 agent contract (NDJSON protocol)
   - Tools exposed to the runtime:
     - `pageindex_get_structure(doc_id)` → returns tree without text (for LLM reasoning)
     - `pageindex_get_pages(doc_id, pages)` → returns page content for specific page ranges
     - `pageindex_search(query, doc_id)` → full agentic retrieval: LLM reasons over tree, fetches relevant pages, returns evidence
   - Uses `ollama/glm-5.1:cloud` via litellm (not dspy)
   - Returns results in same format as existing `retrieval.py` agent (ranked evidence list)

2. Register in Rust kernel `storage.rs`:
   - Add `pageindex_retrieval_agent.toml` manifest
   - Add `pageindex_search` tool to `tools_allowed` for relevant agents

3. Wire into query planner (`citeindex/agents/query_planner.py`):
   - Query planner classifies intent
   - **Keyword queries** → BM25 (existing `tantivy_search`)
   - **Reasoning-heavy queries** (multi-step, cross-section, "compare X and Y") → PageIndex tree-search
   - **Hybrid** → BM25 first for candidate docs, then PageIndex for section-level reasoning

### Phase 4: CLI & TUI Integration ✅

1. CLI: `citeindex ingest "paper.pdf" --use-pageindex` enables PageIndex tree-building
2. CLI: `citeindex search "query" --retrieval pageindex` uses reasoning-based retrieval
3. TUI: add `/pageindex` mode or integrate into existing `/search` with a toggle

---

## Key Technical Decisions

### LiteLLM + Ollama Configuration

PageIndex uses `litellm.completion()` directly. For local Ollama with `glm-5.1:cloud`:

```python
# No API key needed — Ollama is local
# litellm routes "ollama/glm-5.1:cloud" to http://localhost:11434 automatically
model = "ollama/glm-5.1:cloud"
```

The model is already pulled locally (confirmed: `glm-5.1:cloud` available on this machine).

### What We Skip (No API)

- `pageindex/client.py` — workspace/persistence logic (CiteIndex has its own under `corpus/.citeindex/`)
- PageIndex cloud API/MCP integration
- OpenAI Agents SDK demo (we use our own v12 agent runtime)

### What We Keep

- `pageindex/page_index.py` — core tree-building logic (TOC detection, LLM-driven structure extraction, verification, self-correction)
- `pageindex/utils.py` — LLM wrappers (litellm), JSON extraction, tree utilities
- `pageindex/retrieve.py` — `get_document_structure()`, `get_page_content()` for reasoning-based retrieval

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| `glm-5.1:cloud` may not follow PageIndex's JSON prompts as reliably as GPT-4o | Test with sample PDFs; tune prompts if needed; fall back to `qwen3` |
| PageIndex makes many LLM calls (TOC detection, structure extraction, verification, summary) — slow with local models | Add caching; make summary generation optional; parallelize where possible |
| PyPDF2 text extraction is poor for CJK/scanned PDFs | Use MinerU text + PageIndex structure (Phase 2 plan) |
| Two tree formats create maintenance burden | Single converter function; consider eventually migrating CiteIndex's tree to include PageIndex fields |
