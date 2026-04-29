# Phase 3: Advanced Safety & Architecture Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement 5 advanced subsystems for CiteAgent's academic integrity harness: L5 LLM Audit, LTL Runtime Monitor, 4-tier Memory, SafeHarness Security, and Cryptographic Binding.

**Architecture:** All features are implemented across the TypeScript plugin layer (`plugins/opencode-citeagent/src/`) and the Python MCP server (`citeindex/mcp_server.py`). TypeScript handles orchestration, verification, and hook integration; Python handles data persistence and computation. The MCP bridge connects them.

**Tech Stack:** TypeScript/Bun (plugin SDK), Python/asyncio (MCP server), Zod (schemas), Ed25519 (PyNaCl), SHA-256 (hashlib)

---

## Task 1: L5 LLM Audit (Independent-context audit)

**Files:**
- Modify: `plugins/opencode-citeagent/src/verification.ts` (add L5 rung)
- Modify: `plugins/opencode-citeagent/src/types.ts` (add L5 types)
- Modify: `plugins/opencode-citeagent/src/hooks/index.ts` (async L5 trigger)
- Add MCP tools to `citeindex/mcp_server.py` for audit storage

**What:** After L0-L4 pass, an independent LLM context (separate from the agent loop) reviews the evidence against the original user query. This prevents the agent from self-approving fabricated evidence.

**Implementation:**
1. Add `L5AuditResult` type to types.ts
2. Add `l5LlmAudit()` method to VerificationLadder class — calls Ollama with a fresh context containing ONLY the original query + evidence items (no conversation history)
3. Parse the audit LLM's verdict (approved/rejected + reasoning)
4. Make L5 async: the verification ladder returns "pending_audit" if L0-L4 pass, then L5 completes asynchronously
5. Store audit results via MCP tool `audit_save`

## Task 2: LTL Runtime Monitor (Session Governor)

**Files:**
- Create: `plugins/opencode-citeagent/src/ltl-monitor.ts`
- Modify: `plugins/opencode-citeagent/src/hooks/index.ts` (integrate monitor)
- Modify: `plugins/opencode-citeagent/src/types.ts` (LTL types)

**What:** O(1) per-event monitor that checks state transitions against temporal invariants. Invariants: "VERIFY must precede COMMIT", "no tool call outside granted capability set", "every evidence citation must have valid Merkle proof before output".

**Implementation:**
1. Define LTL invariants as predicates on (previousState, event, currentState)
2. Implement state machine: IDLE → PLAN → ACT → VERIFY → COMMIT → DONE (with error transitions)
3. Each hook event (`tool.execute.before`/`after`) feeds through the monitor
4. Violation → emit warning or force session termination
5. Post-hoc trace analysis method (Büchi automaton on collected traces)

## Task 3: 4-Tier Memory Architecture

**Files:**
- Create: `plugins/opencode-citeagent/src/memory.ts`
- Modify: `citeindex/mcp_server.py` (add memory tier tools)
- Modify: `plugins/opencode-citeagent/src/tools/index.ts` (add memory tools)
- Modify: `plugins/opencode-citeagent/src/types.ts` (memory types)

**What:** Replace flat MemoryStore with 4 tiers: Working (in-context), Episodic (per-session JSONL), Long-Term (cross-session consolidated), Corpus (immutable). Memory operations are tool-based actions.

**Implementation:**
1. Define MemoryTier enum and MemoryEntry types
2. Add MCP tools: `memory_store`, `memory_retrieve`, `memory_consolidate`, `memory_summarize`, `memory_discard`
3. Python backend: tier-based storage on disk (working=transient, episodic=JSONL, ltm=SQLite, corpus=existing)
4. Consolidation: episodic→ltm triggers on session end
5. Plugin tools: `cite_memory_store`, `cite_memory_retrieve`, `cite_memory_consolidate`

## Task 4: SafeHarness 4-Layer Security

**Files:**
- Create: `plugins/opencode-citeagent/src/safeharness.ts`
- Modify: `plugins/opencode-citeagent/src/hooks/index.ts` (integrate layers)
- Modify: `plugins/opencode-citeagent/src/types.ts` (security types)

**What:** Wrap the agent loop with 4 security layers: Inform (sanitize input), Verify (tiered cascade), Constrain (least-privilege tools), Correct (rollback).

**Implementation:**
1. Layer 1 (Inform): sanitize all tool inputs — strip prompt injection patterns, tag with provenance
2. Layer 2 (Verify): tiered verification cascade — Tier 0 (rule) → Tier 1 (deterministic) → Tier 2 (causal/HITL)
3. Layer 3 (Constrain): risk-tier classification per tool (Read/Workspace/Network/System) + dynamic privilege ceiling
4. Layer 4 (Correct): state checkpointing before writes, adaptive degradation on anomalies

## Task 5: Cryptographic Binding (Ed25519)

**Files:**
- Create: `plugins/opencode-citeagent/src/crypto.ts`
- Modify: `citeindex/mcp_server.py` (add signing/verification tools)
- Modify: `plugins/opencode-citeagent/src/types.ts` (crypto types)
- Modify: `plugins/opencode-citeagent/src/hooks/index.ts` (sign receipts)

**What:** G1 (capability integrity): Ed25519-signed tool definitions. G2 (behavioral verifiability): signed execution receipts. G3 (interaction auditability): SHA-256 hash chain on NDJSON messages.

**Implementation:**
1. Generate Ed25519 keypair on session start (PyNaCl in Python, tweetnacl in TS)
2. Sign tool definitions at registration → `ToolSignature` type
3. Sign execution receipts after each tool call → `ExecutionReceipt` type
4. SHA-256 hash chain on all MCP messages → `AuditTrail` type
5. MCP tools: `crypto_sign`, `crypto_verify`, `crypto_audit_trail`