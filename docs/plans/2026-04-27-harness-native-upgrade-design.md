# CiteIndex Harness-Native Upgrade Design

> **Philosophy**: Harness-native architecture with academic rigor as the differentiator
> **Reference Systems**: Claude Code (async generator loop), Codex (sandbox + subagent), OpenCode (multi-agent + LSP), SafeHarness (4-layer security), AgentVerify (LTL model checking)
> **Date**: 2026-04-27

---

## 0. Design Principles

1. **The harness is the moat** — The model changes; the harness persists. Every safety property, verification contract, and academic integrity guarantee is *enforced by code*, not by prompts.
2. **Academic rigor is the differentiator** — No other agent system offers Merkle-verified evidence chains, cryptographic reproducibility, or formal trace contracts. We double down.
3. **Harness-native, not pipeline-native** — Replace the fixed 7-agent pipeline with a dynamic agent loop + subagent spawning. The pipeline becomes one *execution strategy* among many.
4. **Deterministic fences everywhere** — Every non-deterministic boundary (LLM output, tool result, external API) gets a deterministic verification layer.
5. **Capability integrity as first-class invariant** — Adopt G1 (capability integrity), G2 (behavioral verifiability), G3 (interaction auditability) from arXiv:2603.14332.

---

## 1. Target Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                      CITAGENT (Harness v2.0)                        │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │  Session     │  │  Agent Loop  │  │  Tool Registry          │   │
│  │  Governor     │  │  (async gen) │  │  (self-describing,      │   │
│  │  (LTL mon.)  │  │              │  │   perm-gated, sandboxed) │   │
│  └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘   │
│         │                  │                         │               │
│  ┌──────┴──────────────────┴─────────────────────────┴────────────┐  │
│  │                   Verification Ladder                         │  │
│  │  L0: Schema check  →  L1: Static analysis  →  L2: Linter     │  │
│  │  L3: Compilation  →  L4: Unit test  →  L5: Merkle proof      │  │
│  │  L6: LLM audit (independent context)                          │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │  Memory      │  │  Context     │  │  Hook System             │   │
│  │  Architecture│  │  Assembly    │  │  (PreTool/PostTool/      │   │
│  │  (LTM/STM/  │  │  & Budget    │  │   Notification/Stop)     │   │
│  │   Episodic/ │  │  (zone-based │  │                          │   │
│  │   Graph)    │  │   + compact) │  │                          │   │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                  SafeHarness 4-Layer Security                 │   │
│  │  Inform (sanitize input) → Verify (casual tiered) →         │   │
│  │  Constrain (least-privilege tools) → Correct (rollback)     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              Cryptographic Binding & Provenance               │   │
│  │  Ed25519 capability tokens · SHA-256 Merkle chains           │   │
│  │  Signed interaction audit trails · Reproducibility certs      │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │
│              NDJSON IPC Bridge (Rust Kernel ↔ Guest Agents)          │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                  Rust Kernel (preserved + extended)          │   │
│  │  DKEE State Machine · Tantivy · SQLite · Merkle Engine       │   │
│  │  18+ Kernel Tools · Argument Graph · Trace System             │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                  Domain Skill Packs (Academic)                │   │
│  │  Citation Skill · Ingestion Skill · Research Skill            │   │
│  │  Integrity Skill · Literature Review Skill · Argument Analysis│   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                  TUI / CLI / Remote API                       │   │
│  │  ratatui TUI · click REPL · WebSocket app-server             │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. The Agent Loop (Replacing the Fixed Pipeline)

### Current (v0.11)
```
CorpusLoader → Indexing → QueryPlanner → Retrieval → Generation → Integrity → [Done]
```
Fixed, 7-step, no branching, no replanning, no subagents.

### Target (v2.0)
```
User prompt
    │
    ▼
Session Governor (LTL monitor) ── validates transition
    │
    ▼
Agent Loop (async generator):
    ┌─────────────────────────────────────────────────┐
    │  1. Context Assembly                             │
    │     - Load system prompt (modular, cacheable)    │
    │     - Inject skill context (lazy, on-demand)     │
    │     - Compress/compact if over budget             │
    │     - Inject verification ladder state            │
    │                                                   │
    │  2. LLM Call (streamed, cancellable)              │
    │     - Model routing (plan→small, act→large)       │
    │     - Structured output enforcement (JSON schema)│
    │     - Backpressure on token rate                  │
    │                                                   │
    │  3. Tool Dispatch (parallel-batched)              │
    │     - Permission check (deny/ask/allow)           │
    │     - Sandbox selection (ro/workspace/full)        │
    │     - Concurrent reads, serial writes             │
    │     - PreTool hook → execute → PostTool hook      │
    │                                                   │
    │  4. Verification Ladder                           │
    │     - L0-L5: deterministic gates                  │
    │     - L6: independent LLM audit (if required)     │
    │     - Fail → recover/escalate/replan              │
    │                                                   │
    │  5. Subagent Spawning (optional)                  │
    │     - Spawn with isolated context                 │
    │     - Prompt cache reuse (↓90% cost)              │
    │     - Wait/cancel/send_input/close lifecycle       │
    │                                                   │
    │  6. State Transition                              │
    │     - DKEE: PLAN→THINK→ACT→VERIFY→COMMIT→DONE    │
    │     - Session Governor checks LTL invariants      │
    │     - Trace emission (MAT format)                 │
    │                                                   │
    │  7. Memory Update                                 │
    │     - Active extraction (MemReader-style)          │
    │     - Store/retrieve/consolidate/forget            │
    │     - Episodic + graph memory integration          │
    │                                                   │
    │  8. Yield / Continue / Cancel                      │
    │     - Stream partial results to TUI/CLI            │
    │     - User can interrupt at any point              │
    └─────────────────────────────────────────────────┘
```

**Key differences from v0.11**:
- The loop is not a pipeline — it's an *async generator* that yields partial results, accepts cancellation, and can dynamically branch
- Subagents are spawned *within* the loop, not as separate long-lived daemons
- Verification happens *at every step*, not just at the end
- Memory is updated *during* reasoning, not after

---

## 3. Core Subsystems (New)

### 3.1 Session Governor (LTL Monitor)

Implements AgentVerify-style temporal logic monitoring on the agent's control flow.

**Runtime monitor** (O(1) per event):
- Every DKEE state transition checked against LTL invariants
- Invariants include: "VERIFY must precede COMMIT", "no tool call outside granted capability set", "every evidence citation must have valid Merkle proof before appearing in output"
- Violation → immediate session termination or forced recovery

**Post-hoc auditor** (Büchi automaton on trace):
- Exhaustive analysis of complete execution traces
- Detects liveness violations: "every PLAN must eventually reach DONE"
- Detects safety violations: "no unverifiable interior agent in a verified chain" (Chain Verifiability Theorem)

**Implementation**: Extend `trace.rs` (919 lines) with LTL invariant checker. Add invariant specification language in `instruction/contracts/`.

### 3.2 Tool Registry & Router

**Current**: 18 hardcoded Rust tools, permission-gated per agent manifest.

**Target**:
- `ToolRegistry`: self-describing tools with JSON Schema input/output, permission level, concurrency safety flag, sandbox requirement
- `ToolRouter`: dispatch with approval check → sandbox selection → execute → result validation
- `ToolSearch`: BM25-powered semantic search over available tools (like Codex's `tool_search`), enabling lazy MCP tool discovery
- `ToolGenesis`: 7-stage governance pipeline (spec→sandbox→static→unit→audit→register→activate) for new tools, inspired by MARIA OS
- **Parallel batch execution**: concurrent read-only tools (up to 10), serial write tools

**Academic tools become first-class in the registry**:
| Tool | Type | Sandbox | Permission |
|------|------|---------|------------|
| `read_corpus` | read | none | allow |
| `search_bm25` | read | none | allow |
| `search_claims` | read | none | allow |
| `merkle_verify` | read | none | allow |
| `cite_render` | read | none | allow |
| `tree_traverse` | read | none | allow |
| `ingest_document` | write | workspace | ask |
| `index_document` | write | workspace | ask |
| `edit_claim` | write | workspace | ask |
| `ag_write_edge` | write | workspace | ask |
| `memory_save` | write | workspace | allow |
| `memory_consolidate` | write | workspace | ask |
| `spawn_subagent` | meta | none | ask |
| `web_search` | network | read-only | ask |
| `run_verification_ladder` | meta | none | allow |
| `cryptographic_bind` | write | workspace | ask |

### 3.3 Verification Ladder

6-rung sequential pipeline. Each rung must pass before the next executes.

| Rung | Check | Implementation | Cost |
|------|-------|---------------|------|
| L0 | Schema validity | JSON Schema validation on all tool I/O | ~0ms |
| L1 | Static analysis | Type-level invariant checking (Rust types + LTL) | ~1ms |
| L2 | Deterministic linter | Citation format, reference existence, cross-source link validity | ~5ms |
| L3 | Compilation check | Merkle hash computation + comparison | ~10ms |
| L4 | Unit test | IntegrityVerifier 5-check suite (node exists, hash, Merkle proof, citation key, claim evidence) | ~50ms |
| L5 | LLM audit | Independent-context LLM reviews output against original spec | ~2000ms (async) |

**Integration with agent loop**: After every ACT→VERIFY transition, the ladder runs. L0-L4 are synchronous. L5 is async if the action has irreversible consequences (e.g., publishing, committing to argument graph).

**New contract**: `I8_verification_ladder_contract.md` — specifies which rungs are required for which action classes.

### 3.4 Memory Architecture

**Current**: JSONL per thread + Tantivy search.

**Target**: 4-tier memory system:

```
┌─────────────────────────────────────────────┐
│  Tier 1: Working Memory (in-context)        │
│  - Current session conversation history      │
│  - Active query plan + evidence items        │
│  - Context budget: zone-based allocation     │
│  - Auto-compaction when over limit           │
├─────────────────────────────────────────────┤
│  Tier 2: Episodic Memory (per-session)      │
│  - Structured interaction trajectories       │
│  - Actions taken + outcomes achieved         │
│  - Reflective feedback (ACE Reflector)       │
│  - Stored as JSONL with Merkle DAG           │
├─────────────────────────────────────────────┤
│  Tier 3: Long-Term Memory (cross-session)  │
│  - Consolidated knowledge from sessions     │
│  - Active extraction (MemReader-style)       │
│  - CRUD operations as tool-based actions    │
│  - Store / retrieve / summarize / discard    │
│  - Policy-guided retrieval (GRPO-trained)   │
│  - Tantivy + SQLite + graph store            │
├─────────────────────────────────────────────┤
│  Tier 4: Corpus Memory (permanent)          │
│  - Full document corpus + indexes           │
│  - CSL-JSON registry + Merkle roots          │
│  - Argument graph + contradiction map       │
│  - Immutable, append-only                    │
└─────────────────────────────────────────────┘
```

**Memory operations are tool-based actions** (AgeMem pattern):
- `memory_store(key, value, tier, metadata)`
- `memory_retrieve(query, tier, policy)`
- `memory_consolidate(tier2→tier3)`
- `memory_summarize(entries)`
- `memory_discard(key, reason)`

**New contract**: `I9_memory_architecture_contract.md` — specifies tier boundaries, consolidation triggers, retrieval policies, and Merkle integrity for memory DAG.

### 3.5 Context Assembly & Budgeting

**Current**: I5 Context Budget Zones defined in contracts, not fully implemented.

**Target**:
```
┌─────────────────────────────────────────────────┐
│ System Prompt (stable prefix, cacheable)         │
│  - Environment block (pwd, OS, date, git)        │
│  - Tool guidance (which tools to prefer)          │
│  - Tone & style directives                        │
│  - Academic rigor rules                            │
│  - Verification ladder state                       │
├─────────────────────────────────────────────────┤
│ Skill Context (lazy-loaded, cacheable)            │
│  - Loaded only when skill is invoked              │
│  - Academic domain skills on-demand               │
├─────────────────────────────────────────────────┤
│ Agent Context (dynamic, per-turn)                  │
│  - Conversation history (compacted if needed)      │
│  - Working memory items                            │
│  - Verification ladder results                    │
│  - Trace spans for current frame                  │
├─────────────────────────────────────────────────┤
│ Source Context (retrieved, budgeted)              │
│  - BM25-ranked evidence nodes (budget zone)        │
│  - CSL citation records                           │
│  - Merkle proofs (lazy, on verification request)   │
├─────────────────────────────────────────────────┤
│ Output Budget (reserved)                           │
│  - Guaranteed space for answer + evidence chain    │
└─────────────────────────────────────────────────┘
```

**Auto-compaction**: When total context exceeds `auto_compact_limit`:
1. Stable prefix preserved (prompt cache)
2. Conversation history summarized (compaction agent)
3. Source context evicted by LRU + score
4. Verification state preserved (never compacted)

### 3.6 Hook System

**Lifecycle hooks** (deterministic, model-independent):

| Hook | Trigger | Purpose |
|------|---------|---------|
| `PreToolUse` | Before tool dispatch | Permission check, input sanitization, sandbox setup |
| `PostToolUse` | After tool returns | Output validation, Merkle hash check, trace emission |
| `PreVerification` | Before ladder run | Select which rungs to execute |
| `PostVerification` | After ladder completes | Audit trail, escalation decision |
| `PreSubagent` | Before spawning subagent | Context isolation check, budget allocation |
| `PostSubagent` | After subagent completes | Result validation, context merge |
| `Notification` | On user-facing events | TUI updates, progress bars |
| `Stop` | On session termination | Memory consolidation, trace finalization |
| `SessionStart` | On session init | Environment setup, contract loading |
| `SessionCompact` | On context overflow | Compaction strategy execution |

**Implementation**: Extend `trace.rs` with hook dispatch. Hooks are Rust functions registered in `HookRegistry`. Python hooks via NDJSON bridge.

### 3.7 SafeHarness 4-Layer Security

Wraps the entire agent loop:

**Layer 1: Inform** (Input Sanitization)
- All external content (PDFs, URLs, API responses) sanitized before entering reasoning chain
- Provenance tracking: every piece of information tagged with source ID + trust level
- Prompt injection detection (pattern-based + secondary LLM scan for high-risk sources)

**Layer 2: Verify** (Tiered Verification Cascade)
- Tier 0: Rule-based checks (schema, format, existence)
- Tier 1: Deterministic validators (Merkle, hash, citation key)
- Tier 2: Causal diagnostics (only for high-impact actions)
- Escalation: Tier 0 fail → block. Tier 1 fail → retry with stronger model. Tier 2 fail → HITL.

**Layer 3: Constrain** (Least-Privilege Tool Control)
- Risk-tier classification: Read (no risk) → Workspace (low risk) → Network (medium risk) → System (high risk)
- Capability tokens (Ed25519-signed): each tool call gets a token encoding granted capabilities
- Dynamic privilege ceiling: anomalous behavior → tighten ceiling

**Layer 4: Correct** (Rollback & Degradation)
- State checkpoints before every write action
- Adaptive degradation: sustained anomalies → progressive tool restriction → forced rollback
- Merkle-verified rollback: verify corpus integrity after rollback

**New contract**: `I10_safeharness_contract.md` — specifies cross-layer escalation protocol.

### 3.8 Cryptographic Binding & Provenance

Adopt arXiv:2603.14332's three governance requirements:

**G1: Capability Integrity**
- Every tool definition gets an Ed25519 signature from the harness
- Tool definitions loaded at session start, any runtime modification requires re-signing
- Agent cannot invoke a tool whose signature doesn't match the registry

**G2: Behavioral Verifiability**
- Every agent action produces a signed execution receipt
- Receipt includes: tool name, input hash, output hash, capability token, Merkle proof (if applicable)
- Receipts form an interaction audit trail with cryptographic provenance

**G3: Interaction Auditability**
- Multi-agent interactions get a shared audit context
- Every subagent spawn gets a parent-signed delegation token
- Chain Verifiability Theorem: one unverifiable interior agent breaks end-to-end verification for all downstream nodes
- Implementation: every NDJSON message between Rust↔Python gets a SHA-256 hash chain

**New contract**: `I11_cryptographic_binding_contract.md`

### 3.9 Subagent Architecture

**Current**: 3 long-lived NDJSON daemon agents (Coordinator, Librarian, Ingest).

**Target**: Dynamic subagent spawning within the agent loop:

```rust
// Conceptual API
SubagentHandle spawn_subagent(
    agent_type: AgentType,      // Explore, Fix, Verify, Research, Review
    context: IsolatedContext,    // Fresh context, no parent baggage
    tools: ToolSubset,           // Restricted tool access
    skill_pack: SkillPack,      // Domain skills
    budget: TokenBudget,        // Bound token usage
    parent_delegation: SignedToken,  // Cryptographic delegation
) -> SubagentHandle;

// Lifecycle
handle.send_input(msg);
handle.wait(timeout);
handle.cancel();
handle.close();   // Returns result + audit trail
```

**Subagent types for academic domain**:

| Agent | Tool Access | Purpose |
|-------|------------|---------|
| `Explore` | Read-only (search_bm25, tree_traverse, read_corpus, cite_render) | Quick corpus exploration |
| `Research` | Read + memory (all read tools + memory_retrieve) | Multi-step research tasks |
| `Verify` | Read + verify (all read tools + merkle_verify, run_verification_ladder) | Independent verification audit (L5) |
| `Ingest` | Write scoped (ingest_document, index_document) | Document ingestion with isolation |
| `Review` | Read-only (search_claims, ag_query_claims, ag_query_contradictions) | Argument analysis |
| `Compact` | Internal only (memory_summarize, memory_consolidate) | Context compaction |

**Key rule**: Each subagent runs in isolated context. Prompt cache reuse keeps cost < 10% of full call. Depth limit = 1 (no subagent spawning subagent).

---

## 4. Contracts (New & Extended)

| ID | Name | Type | Status |
|----|------|------|--------|
| I1 | Tool Dispatcher | Existing | Extend with ToolRegistry + ToolSearch |
| I2 | Agent Runtime | Existing | Extend with subagent lifecycle |
| I3 | Pre-Grounded Gate | Existing | Keep |
| I4 | Score Fusion | Existing | Keep |
| I5 | Context Budget | Existing | Implement fully |
| I6 | Not assigned | — | — |
| I7 | Weak Signal Escalation | Existing | Keep |
| **I8** | **Verification Ladder** | **New** | 6-rung pipeline contract |
| **I9** | **Memory Architecture** | **New** | 4-tier memory contract |
| **I10** | **SafeHarness Security** | **New** | 4-layer security contract |
| **I11** | **Cryptographic Binding** | **New** | G1/G2/G3 governance contract |
| **I12** | **Hook System** | **New** | Lifecycle hook contract |
| **I13** | **Subagent Protocol** | **New** | Spawn/wait/cancel/close contract |
| **I14** | **Agent Loop Contract** | **New** | Async generator loop invariant |
| **S11** | **MAT Trace Schema** | **New** | Message-Action Trace with step/trace contracts |
| **S12** | **Interaction Audit Trail** | **New** | Signed provenance schema |
| **A2** | **WebSocket App-Server API** | **New** | Remote session protocol |

---

## 5. Implementation Phases

### Phase 1: Foundation (4-6 weeks)
*Harden the kernel, implement the agent loop, add verification ladder*

1. **Implement Context Assembly & Budgeting** (I5 full implementation)
   - Modular system prompt construction (env block + tool guidance + academic rules)
   - Zone-based token budget with deterministic eviction
   - Auto-compaction trigger

2. **Implement Agent Loop** (I14)
   - Replace fixed pipeline with async generator loop in Rust kernel
   - Streaming, cancellable LLM calls
   - Backpressure on token rate

3. **Implement Verification Ladder** (I8)
   - L0-L4 deterministic rungs
   - Integration with DKEE VERIFY→COMMIT transition
   - L5 async LLM audit (independent context)

4. **Implement Hook System** (I12)
   - Core lifecycle hooks (PreToolUse, PostToolUse, SessionStart, Stop)
   - HookRegistry in Rust kernel
   - Python hook bridge via NDJSON

5. **Extend Trace System** (S11)
   - Message-Action Trace format with step/trace contracts
   - LTL invariant checker on traces
   - MAT → JSONL persistence

### Phase 2: Safety & Memory (4-6 weeks)
*SafeHarness, cryptographic binding, 4-tier memory*

6. **Implement SafeHarness 4-Layer Security** (I10)
   - Inform layer: input sanitization + provenance tracking
   - Verify layer: tiered cascade
   - Constrain layer: risk-tier classification + capability tokens (Ed25519)
   - Correct layer: checkpoint + rollback + degradation

7. **Implement Cryptographic Binding** (I11)
   - G1: Signed tool definitions
   - G2: Signed execution receipts
   - G3: Interaction audit trail with delegation tokens
   - SHA-256 hash chain on all NDJSON messages

8. **Implement 4-Tier Memory Architecture** (I9)
   - Tier 2: Episodic memory (structured trajectories with Merkle DAG)
   - Tier 3: Long-term memory (CRUD tools, active consolidation)
   - Memory tools: store/retrieve/consolidate/summarize/discard
   - Integration with Tantivy + SQLite + graph store

### Phase 3: Subagents & Tool Registry (4-6 weeks)
*Dynamic subagent spawning, tool search, parallel execution*

9. **Implement Subagent Architecture** (I13)
   - SubagentHandle API in Rust kernel
   - Isolated context management
   - Prompt cache reuse for subagent spawning
   - Depth limit enforcement
   - Signed delegation tokens

10. **Implement Tool Registry & Router** (I1 extension)
    - Self-describing tools with JSON Schema
    - Permission levels + concurrency safety flags
    - Parallel batch execution for read-only tools
    - ToolSearch: BM25 over available tools
    - ToolGenesis: 7-stage governance pipeline for new tools

11. **Convert Pipeline Agents to Subagents**
    - CorpusLoader → Explore subagent
    - Ingestion pipeline → Ingest subagent
    - IntegrityVerifier → Verify subagent
    - Coordinator → absorbed into main agent loop

### Phase 4: Academic Domain Skills (3-4 weeks)
*Skill packs become first-class*

12. **Academic Skill Pack v2**
    - Citation skill: CSL rendering, Chicago/APA/MLA formatting
    - Research skill: multi-step corpus exploration with evidence chains
    - Integrity skill: Merkle verification, hash checking, proof generation
    - Literature review skill: systematic search + comparison + gap identification
    - Argument analysis skill: claim extraction, contradiction detection, edge writing
    - Ingestion skill: PDF/URL/media ingestion with Merkle tree generation

13. **Skill Hot-Loading & Versioning**
    - Runtime skill discovery from `~/.citeindex/skills/`
    - Lazy skill context loading (inject only when invoked)
    - Skill versioning with signed manifests

### Phase 5: Evaluation & Polish (3-4 weeks)
*Benchmarking, TUI upgrades, remote access*

14. **Evaluation Pipeline**
    - Academic Integrity Benchmark: synthetic corpus + adversarial queries
    - Citation Accuracy Benchmark: ground-truth CSL vs agent output
    - Merkle Proof Validity Benchmark: 100% proof validity on all evidence
    - Terminal-Bench integration for coding agent evaluation
    - Regression test suite with CI

15. **TUI v2.0**
    - Subagent progress panels
    - Verification ladder visualization
    - Memory inspector panel
    - Hook management UI

16. **Remote API & Multi-Session** (A2)
    - WebSocket app-server for remote TUI
    - Multi-session support (multiple agent loops in parallel)
    - Session serialization + share links

---

## 6. What Is Preserved (Not Rewritten)

These components carry forward with extensions only:

| Component | Action |
|-----------|--------|
| DKEE State Machine | Keep. Add LTL monitor as Session Governor |
| Merkle Engine | Keep. Add to verification ladder L3 |
| Tantivy indexes | Keep. Add to tool registry |
| SQLite Argument Graph | Keep. Add to tool registry |
| 18 Kernel Tools | Keep. Convert to self-describing registry entries |
| NDJSON IPC Bridge | Keep. Add SHA-256 hash chain + signed receipts |
| Trace System | Keep. Extend to MAT format + LTL checker |
| Skill Pack System | Keep. Add hot-loading + lazy context |
| Recovery Chain (R1-R6) | Keep. Integrate with SafeHarness Correct layer |
| ACE Scholar Adaptation | Keep. Integrate with Tier 3 memory consolidation |
| Ingestion Pipelines | Keep as Ingest subagent skill |
| CSL/citeproc | Keep as Citation skill |

---

## 7. New Dependencies

| Category | Dependency | Purpose |
|----------|-----------|---------|
| **Cryptography** | `ed25519-dalek` (Rust) | Ed25519 signing for capability tokens |
| | `sha2` (Rust) | Already used; extend for hash chains |
| **Formal Methods** | LTL checker (custom) | Runtime invariant monitoring |
| **Sandboxing** | `bubblewrap` / `landlock` (Linux) | OS-native sandbox for tool execution |
| | `seatbelt` (macOS) | Platform-native sandbox |
| **LLM** | `async-stream` / `tokio` | Async generator agent loop |
| | `tiktoken-rs` | Token counting for context budget |
| **Memory** | `sqlx` (Rust) | Async SQLite for tier 3 memory |
| | `petgraph` (Rust) | Graph memory for tier 4 |
| **Web** | `reqwest` + `scraper` | Web search/research tool |
| **API** | `axum` + `tokio-tungstenite` | WebSocket app-server |

---

## 8. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Merkle proof validity on all evidence | 100% | Verification ladder L3 + L4 |
| Citation accuracy (CSL match to ground truth) | >95% | Citation benchmark |
| Reproducibility (same query → same evidence chain) | 100% | Deterministic BM25 + hash-anchored retrieval |
| Verification ladder pass rate (all rungs on normal operation) | >99% | L0-L5 success rate |
| Subagent cost overhead vs single agent | <15% | Token count comparison |
| Context compaction recovery (answer quality preserved) | >90% | Pre/post compaction QA score |
| LTL invariant violation detection | 100% of injected violations | Fault injection tests |
| SafeHarness attack success rate reduction | >90% vs unprotected baseline | ASB + InjecAgent benchmarks |
| Tool execution sandbox escape rate | 0% | Sandbox verification tests |
| End-to-end cryptographic provenance verification | <0.02% overhead | Performance benchmark |

---

## 9. Risk Assessment

| Risk | Mitigation |
|------|-----------|
| LTL checker too slow for runtime | O(1) per-event monitor; deep analysis is post-hoc |
| Subagent context isolation adds complexity | Depth limit = 1; prompt cache reuse reduces cost |
| Memory consolidation produces stale knowledge | Merkle integrity on memory DAG; discard policy |
| Formal verification overkill for academic domain | Academic rigor IS the differentiator; start with critical invariants only |
| Rust↔Python IPC signed receipts add latency | SHA-256 hash chain is ~1μs per message; Ed25519 verify is ~97μs |
| Phased delivery stretches timeline | Each phase delivers independently usable value |

---

*Design document for CiteIndex Harness-Native Upgrade v2.0*
*Author: harness engineer analysis*
*Date: 2026-04-27*