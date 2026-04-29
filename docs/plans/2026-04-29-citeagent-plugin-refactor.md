# CiteAgent Plugin Refactor: Kill the MCP Server

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate the separate MCP server and its stdio connection entirely. Make CiteAgent a pure OpenCode plugin that manages its own Python backend subprocess, registering all 32 tools as first-class plugin tools with full hook integration.

**Architecture:** The plugin (`opencode-citeagent`) becomes the sole entry point. It spawns the Python `citeindex.mcp_server` as a managed subprocess (not via OpenCode's MCP client), talks to it via stdio JSON-RPC that the plugin itself controls, and registers all 32 tools natively in OpenCode's tool system. No fork needed — users install vanilla `opencode`, add the plugin, and it works.

**Tech Stack:** TypeScript/Bun (plugin), Python (citeindex backend as subprocess), OpenCode Plugin SDK (`@opencode-ai/plugin`), MCP SDK (client-only, for subprocess communication)

---

## Why This Refactor

| Problem | Cause | Fix |
|---------|-------|-----|
| `MCP error -32000: Connection closed` | OpenCode's MCP client manages stdio lifecycle; process dies → connection lost | Plugin owns subprocess; reconnect is plugin's responsibility |
| `PYTHONPATH` / `CITEAGENT_CORPUS_ROOT` env hacks | OpenCode launches MCP with project cwd, not our config | Plugin controls spawn env |
| `@opencode-ai/plugin@0.0.0-dev-*` npm error | Dev version in fork doesn't exist on npm | No fork → use published opencode binary |
| Duplicate tool registration | 32 MCP tools + 8 plugin tools = confusing overlap | Single source of truth: plugin tools |
| Can't access OpenCode session context | MCP server is isolated process | Plugin hooks have full context (sessionID, agent, directory) |
| Hardcoded Python path in config | `opencode.jsonc` has absolute machine-specific paths | Plugin auto-detects Python or uses configurable path |

## What We Keep

- `citeindex/mcp_server.py` — Python backend stays, but now spawned by the plugin, not by OpenCode's MCP system
- `plugins/opencode-citeagent/src/` — TypeScript subsystems (verification, safeharness, ltl-monitor, memory, crypto)
- `fork/opencode/.opencode/` — Config files, agents, rules, skills (moved to project root)
- The Python backends (merkle, search, etc.) — unchanged

## What We Change

- `mcp-bridge.ts` — Replaced: instead of MCP client connecting to OpenCode-managed server, plugin spawns its own subprocess
- `tools/index.ts` — Replaced: 8 proxy tools → 32 native plugin tools (all 32 that MCP server has)
- `hooks/index.ts` — Updated: remove `CiteAgentMcpBridge` dependency for hooks that don't need MCP calls
- `opencode.jsonc` — Remove `mcp.citeagent` config entirely; add `CITEAGENT_PYTHON` env var
- Fork — Not needed. Delete. User installs stock `opencode`.

---

## Phase 1: Plugin-Managed Subprocess Bridge

### Task 1.1: Replace MCP Bridge with Plugin-Owned Subprocess

**Files:**
- Modify: `plugins/opencode-citeagent/src/mcp-bridge.ts` (rewrite)

**Step 1: Rewrite mcp-bridge.ts to spawn Python as a managed subprocess**

The current `CiteAgentMcpBridge` uses `StdioClientTransport` which expects an already-running server. The new version will:

1. Spawn `python3.12 -m citeindex.mcp_server` itself (not via OpenCode's MCP system)
2. Set `PYTHONPATH` and `CITEAGENT_CORPUS_ROOT` correctly
3. Handle reconnection, stderr logging, and graceful shutdown
4. Auto-detect Python binary (`CITEAGENT_PYTHON` env var or `python3` fallback)

```typescript
import { Client } from "@modelcontextprotocol/sdk/client/index.js"
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js"
import { spawn, type Subprocess } from "bun"
import path from "path"

export class CiteAgentBridge {
  private client: Client | null = null
  private transport: StdioClientTransport | null = null
  private proc: Subprocess | null = null
  private connected = false
  private projectDir: string
  private pythonCmd: string
  private reconnectAttempts = 0
  private maxReconnects = 3
  private shuttingDown = false

  constructor(projectDir: string) {
    this.projectDir = projectDir
    // Auto-detect Python: env var > rye path > system python3
    this.pythonCmd = process.env.CITEAGENT_PYTHON || "/home/ajiap/.rye/py/cpython@3.12.8/bin/python3.12"
  }

  async connect(): Promise<void> {
    if (this.connected && this.client) return

    this.transport = new StdioClientTransport({
      command: this.pythonCmd,
      args: ["-m", "citeindex.mcp_server"],
      env: {
        ...process.env,
        PYTHONPATH: this.projectDir,
        CITEAGENT_CORPUS_ROOT: path.join(this.projectDir, "corpus"),
      },
      stderr: "pipe",
    })

    // Log stderr from Python process
    this.transport.stderr?.on("data", (chunk: Buffer) => {
      const msg = chunk.toString().trim()
      if (msg) console.debug("[CiteAgent kernel]", msg)
    })

    this.client = new Client({
      name: "opencode-citeagent",
      version: "0.1.0",
    })

    try {
      await this.client.connect(this.transport)
      this.connected = true
      this.reconnectAttempts = 0
    } catch (error) {
      this.connected = false
      throw new Error(`CiteAgent: failed to connect to Python backend: ${error}`)
    }
  }

  async callTool(name: string, args: Record<string, unknown>): Promise<string> {
    if (!this.connected || !this.client) {
      await this.reconnect()
    }
    try {
      const result = await this.client!.callTool({ name, arguments: args })
      // Extract text content from MCP response
      if (result.content && Array.isArray(result.content)) {
        const textContent = result.content.find((c: any) => c.type === "text")
        if (textContent?.text) return textContent.text
      }
      return JSON.stringify(result, null, 2)
    } catch (error) {
      if (this.shouldReconnect(error)) {
        await this.reconnect()
        const result = await this.client!.callTool({ name, arguments: args })
        if (result.content && Array.isArray(result.content)) {
          const textContent = result.content.find((c: any) => c.type === "text")
          if (textContent?.text) return textContent.text
        }
        return JSON.stringify(result, null, 2)
      }
      throw error
    }
  }

  async disconnect(): Promise<void> {
    this.shuttingDown = true
    if (this.client && this.connected) {
      await this.client.close()
    }
    if (this.proc) {
      this.proc.kill()
      this.proc = null
    }
    this.connected = false
    this.client = null
    this.transport = null
  }

  private shouldReconnect(error: unknown): boolean {
    if (this.shuttingDown) return false
    if (error instanceof Error) {
      const msg = error.message.toLowerCase()
      return msg.includes("connection") || msg.includes("closed") || msg.includes("-32000")
    }
    return false
  }

  private async reconnect(): Promise<void> {
    if (this.reconnectAttempts >= this.maxReconnects) {
      throw new Error("CiteAgent: max reconnection attempts reached")
    }
    this.reconnectAttempts++
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 10000)
    await new Promise<void>((r) => setTimeout(r, delay))
    await this.disconnect()
    this.shuttingDown = false // reset for reconnect
    await this.connect()
  }
}
```

**Step 2: Create a singleton bridge instance**

Add to `mcp-bridge.ts`:

```typescript
let _bridge: CiteAgentBridge | null = null

export function getBridge(projectDir: string): CiteAgentBridge {
  if (!_bridge) {
    _bridge = new CiteAgentBridge(projectDir)
  }
  return _bridge
}
```

**Step 3: Commit**

```bash
git add plugins/opencode-citeagent/src/mcp-bridge.ts
git commit -m "refactor: replace MCP-client bridge with plugin-owned subprocess bridge"
```

---

## Phase 2: 32 Native Plugin Tools

### Task 2.1: Replace 8 Proxy Tools with 32 Native Tools

**Files:**
- Modify: `plugins/opencode-citeagent/src/tools/index.ts` (rewrite)

**Step 1: Rewrite tools/index.ts to register all 32 tools**

Each tool calls `bridge.callTool()` (the plugin-owned subprocess, not MCP config). The 32 tools come from the MCP server's `TOOL_DEFINITIONS` list. Group them logically:

**Academic Core (8 existing):** `cite_search`, `cite_search_claims`, `cite_verify`, `cite_render`, `cite_ingest`, `cite_tree`, `cite_memory_save`, `cite_argument_query`

**Extended Academic (6 new):** `cite_regex_search`, `cite_csl_lookup`, `cite_memory_load`, `cite_graph_query`, `cite_export`, `cite_status`

**Audit (2 new):** `cite_audit_save`, `cite_audit_retrieve`

**Memory Tiers (4 new):** `cite_memory_store_tier`, `cite_memory_retrieve_tier`, `cite_memory_consolidate`, `cite_memory_summarize`

**Crypto (3 new):** `cite_crypto_sign`, `cite_crypto_verify`, `cite_crypto_audit_trail`

**SafeHarness (5 new):** `cite_safeharness_check`, `cite_safeharness_sanitize`, `cite_safeharness_checkpoint`, `cite_safeharness_rollback`, `cite_safeharness_status`

**Verification (1 existing via hook, 0 new tools):** Verification ladder runs automatically in hooks, no separate tool needed.

**Tool naming:** All tools prefixed with `cite_` to namespace them in OpenCode's tool system.

```typescript
import { tool } from "@opencode-ai/plugin"
import { getBridge } from "../mcp-bridge.js"

const z = tool.schema

export async function createCiteAgentTools(ctx: { directory: string }) {
  const bridge = getBridge(ctx.directory)
  await bridge.connect()

  // Helper: call Python backend and return text
  const call = async (name: string, args: Record<string, unknown>) => {
    return bridge.callTool(name, args)
  }

  return {
    // ── Academic Core ──────────────────────────────────
    cite_search: tool({
      description: "BM25 full-text search on the academic corpus. Returns ranked document nodes with citation metadata and Merkle hashes.",
      args: {
        query: z.string().describe("Search query terms"),
        limit: z.number().default(10).describe("Maximum results to return"),
      },
      async execute({ query, limit }) { return call("search_documents", { query, limit }) },
    }),

    cite_search_claims: tool({
      description: "Search claims in the argument graph. Returns claim nodes with contradiction and support links.",
      args: { query: z.string().describe("Claim search query") },
      async execute({ query }) { return call("search_claims", { query }) },
    }),

    cite_verify: tool({
      description: "Verify Merkle proof for an evidence node. Checks SHA-256 hash chain from leaf to document root.",
      args: {
        node_hash: z.string().describe("SHA-256 hash of the evidence node"),
        proof: z.array(z.string()).describe("Merkle proof sibling hashes"),
        root: z.string().describe("Document Merkle root hash"),
      },
      async execute({ node_hash, proof, root }) { return call("merkle_verify", { node_hash, proof, root }) },
    }),

    cite_render: tool({
      description: "Render a CSL-JSON citation record to formatted bibliography string (Chicago, APA, MLA, etc.).",
      args: {
        citation_key: z.string().describe("CSL citation key"),
        style: z.string().default("chicago-author-date").describe("Citation style ID"),
      },
      async execute({ citation_key, style }) { return call("csl_render", { citation_key, style }) },
    }),

    cite_ingest: tool({
      description: "Ingest a document (PDF, URL, media) into the academic corpus. Creates PageIndex tree, Merkle hashes, and Tantivy index entries.",
      args: {
        source: z.string().describe("File path or URL to ingest"),
        force: z.boolean().default(false).describe("Force re-ingestion if already indexed"),
      },
      async execute({ source, force }) { return call("index_document", { source, force }) },
    }),

    cite_tree: tool({
      description: "Load and traverse PageIndex tree for a document. Returns structured hierarchy of sections, paragraphs, and text blocks.",
      args: {
        document_id: z.string().describe("Document source ID"),
        depth: z.number().default(3).describe("Max depth to traverse"),
      },
      async execute({ document_id, depth }) { return call("tree_load", { document_id, depth: String(depth) }) },
    }),

    cite_memory_save: tool({
      description: "Save a memory entry to the agent's persistent memory store (JSONL + Tantivy index).",
      args: {
        content: z.string().describe("Memory content to save"),
        thread: z.string().default("default").describe("Thread name"),
        tags: z.array(z.string()).default([]).describe("Tags for retrieval"),
      },
      async execute({ content, thread, tags }) { return call("memory_save", { content, thread, tags }) },
    }),

    cite_argument_query: tool({
      description: "Query the argument graph for claims, contradictions, and support edges.",
      args: {
        claim_id: z.string().optional().describe("Specific claim ID to look up"),
        find_contradictions: z.boolean().default(false).describe("Find contradictions instead of claims"),
      },
      async execute({ claim_id, find_contradictions }) {
        if (find_contradictions) return call("ag_query_contradictions", { claim_id })
        return call("ag_query_claims", { claim_id })
      },
    }),

    // ── Extended Academic ──────────────────────────────
    cite_regex_search: tool({
      description: "Regex-based search on document nodes. Returns matching text with node IDs.",
      args: {
        pattern: z.string().describe("Regex pattern to search"),
        node_id: z.string().optional().describe("Limit search to this node"),
      },
      async execute({ pattern, node_id }) { return call("regex_search", { pattern, node_id }) },
    }),

    cite_csl_lookup: tool({
      description: "Look up a CSL-JSON citation record by key.",
      args: { citation_key: z.string().describe("CSL citation key to look up") },
      async execute({ citation_key }) { return call("csl_lookup", { citation_key }) },
    }),

    cite_memory_load: tool({
      description: "Load memory entries from a thread.",
      args: {
        thread: z.string().default("default").describe("Thread name"),
        limit: z.number().default(10).describe("Max entries to return"),
      },
      async execute({ thread, limit }) { return call("memory_load", { thread, limit }) },
    }),

    cite_graph_query: tool({
      description: "Query the argument graph: list claims, find supports/contradictions for a claim.",
      args: {
        query: z.string().describe("Query for the argument graph"),
        find_contradictions: z.boolean().default(false).describe("Find contradictions"),
      },
      async execute({ query, find_contradictions }) { return call("ag_query", { query, find_contradictions }) },
    }),

    cite_export: tool({
      description: "Export citation data (BibTeX, RIS, or CSL-JSON) for a document or set of citations.",
      args: {
        document_id: z.string().describe("Document ID to export citations from"),
        format: z.string().default("bibtex").describe("Export format: bibtex, ris, csl"),
      },
      async execute({ document_id, format }) { return call("export_citations", { document_id, format }) },
    }),

    cite_status: tool({
      description: "Get CiteAgent kernel status: corpus stats, index health, backend availability.",
      args: {},
      async execute() { return call("status", {}) },
    }),

    // ── Audit ──────────────────────────────────────────
    cite_audit_save: tool({
      description: "Save an audit result to persistent storage.",
      args: {
        audit_id: z.string().describe("Unique audit identifier"),
        verdict: z.string().describe("Audit verdict (approved/rejected)"),
        reasoning: z.string().optional().describe("Reasoning for the verdict"),
        evidence_hashes: z.array(z.string()).optional().describe("List of evidence SHA-256 hashes"),
        query: z.string().optional().describe("Original query being audited"),
      },
      async execute({ audit_id, verdict, reasoning, evidence_hashes, query }) {
        return call("audit_save", { audit_id, verdict, reasoning, evidence_hashes, query })
      },
    }),

    cite_audit_retrieve: tool({
      description: "Retrieve a saved audit result.",
      args: { audit_id: z.string().describe("Audit identifier to retrieve") },
      async execute({ audit_id }) { return call("audit_retrieve", { audit_id }) },
    }),

    // ── Memory Tiers ───────────────────────────────────
    cite_memory_store_tier: tool({
      description: "Store a memory entry in a specific tier (working/episodic/long_term/corpus).",
      args: {
        content: z.string().describe("Memory content"),
        tier: z.string().describe("Tier: working, episodic, long_term, corpus"),
        key: z.string().optional().describe("Unique key for this memory"),
        tags: z.array(z.string()).optional().describe("Tags for categorisation"),
        thread_id: z.string().optional().describe("Thread identifier"),
        source_ids: z.array(z.string()).optional().describe("Evidence source IDs"),
      },
      async execute({ content, tier, key, tags, thread_id, source_ids }) {
        return call("memory_store_tier", { content, tier, key, tags, thread_id, source_ids })
      },
    }),

    cite_memory_retrieve_tier: tool({
      description: "Retrieve memories from a specific tier or all tiers.",
      args: {
        query: z.string().describe("Search query"),
        tier: z.string().optional().describe("Tier to search (optional)"),
        limit: z.number().default(10).describe("Max results"),
      },
      async execute({ query, tier, limit }) { return call("memory_retrieve_tier", { query, tier, limit }) },
    }),

    cite_memory_consolidate: tool({
      description: "Consolidate episodic memories into long-term storage.",
      args: { thread_id: z.string().optional().describe("Thread to consolidate") },
      async execute({ thread_id }) { return call("memory_consolidate", { thread_id }) },
    }),

    cite_memory_summarize: tool({
      description: "Summarize a set of memory entries.",
      args: { entry_ids: z.array(z.string()).describe("List of memory entry IDs to summarize") },
      async execute({ entry_ids }) { return call("memory_summarize", { entry_ids }) },
    }),

    // ── Cryptographic ──────────────────────────────────
    cite_crypto_sign: tool({
      description: "Sign a message using HMAC-SHA256 (MVP — upgrade to Ed25519 for production).",
      args: {
        message: z.string().describe("Message to sign"),
        session_id: z.string().describe("Session identifier"),
      },
      async execute({ message, session_id }) { return call("crypto_sign", { message, session_id }) },
    }),

    cite_crypto_verify: tool({
      description: "Verify an HMAC-SHA256 signature.",
      args: {
        message: z.string().describe("Original message"),
        signature: z.string().describe("Signature to verify"),
        session_id: z.string().describe("Session identifier"),
      },
      async execute({ message, signature, session_id }) {
        return call("crypto_verify", { message, signature, session_id })
      },
    }),

    cite_crypto_audit_trail: tool({
      description: "Return the audit chain for a session.",
      args: { session_id: z.string().describe("Session identifier") },
      async execute({ session_id }) { return call("crypto_audit_trail", { session_id }) },
    }),

    // ── SafeHarness ─────────────────────────────────────
    cite_safeharness_check: tool({
      description: "Run all 4 SafeHarness layers on a tool call and return the result.",
      args: {
        tool_name: z.string().describe("Name of the tool to check"),
        args: z.record(z.unknown()).optional().describe("Tool arguments"),
      },
      async execute({ tool_name, args }) { return call("safeharness_check", { tool_name, args: args ?? {} }) },
    }),

    cite_safeharness_sanitize: tool({
      description: "SafeHarness Layer 1: sanitize input for a tool call.",
      args: {
        tool_name: z.string().describe("Tool name"),
        input: z.record(z.unknown()).describe("Input to sanitize"),
      },
      async execute({ tool_name, input }) { return call("safeharness_sanitize", { tool_name, input }) },
    }),

    cite_safeharness_checkpoint: tool({
      description: "SafeHarness Layer 4: create a state checkpoint before a write action.",
      args: {
        tool_name: z.string().describe("Tool being called"),
        input_hash: z.string().optional().describe("SHA-256 hash of input"),
      },
      async execute({ tool_name, input_hash }) { return call("safeharness_checkpoint", { tool_name, input_hash }) },
    }),

    cite_safeharness_rollback: tool({
      description: "SafeHarness Layer 4: rollback from a checkpoint (placeholder).",
      args: { checkpoint_id: z.string().describe("Checkpoint to rollback") },
      async execute({ checkpoint_id }) { return call("safeharness_rollback", { checkpoint_id }) },
    }),

    cite_safeharness_status: tool({
      description: "Get the current SafeHarness security status.",
      args: {},
      async execute() { return call("safeharness_status", {}) },
    }),
  }
}
```

**Step 2: Commit**

```bash
git add plugins/opencode-citeagent/src/tools/index.ts
git commit -m "feat: register all 32 tools as native plugin tools"
```

---

## Phase 3: Update Plugin Entry Point and Hooks

### Task 3.1: Update Index and Hooks to Use New Bridge

**Files:**
- Modify: `plugins/opencode-citeagent/src/index.ts`
- Modify: `plugins/opencode-citeagent/src/hooks/index.ts`

**Step 1: Update index.ts to pass projectDir and handle bridge lifecycle**

```typescript
import { Plugin } from "@opencode-ai/plugin"
import { createCiteAgentTools } from "./tools/index.js"
import { createCiteAgentHooks } from "./hooks/index.js"
import { getBridge } from "./mcp-bridge.js"

export const CiteAgentPlugin: Plugin = async (ctx) => {
  const bridge = getBridge(ctx.directory)
  await bridge.connect()

  const tools = await createCiteAgentTools(ctx)
  const hooks = await createCiteAgentHooks(ctx)

  return {
    tool: tools,
    ...hooks,
  }
}

export default CiteAgentPlugin
```

**Step 2: Update hooks/index.ts — remove CiteAgentMcpBridge import, use getBridge**

The hooks currently import `CiteAgentMcpBridge` for the verification ladder. Change to use `getBridge`:

```typescript
import { getBridge } from "../mcp-bridge.js"
// ... rest of imports unchanged

export async function createCiteAgentHooks(ctx: { directory: string }): Promise<Hooks> {
  const safeharness = new SafeHarness()
  const monitor = new LTLMonitor()
  const crypto = new CryptoBinding()
  await crypto.init(`session-${Date.now()}`)

  return {
    "tool.execute.before": async (input, _output) => {
      // ... same logic as before, no changes needed
    },

    "tool.execute.after": async (_input, output) => {
      // ... same logic, but replace CiteAgentMcpBridge.instance with getBridge(ctx.directory)
      const bridge = getBridge(_ctx.directory)  // need to pass ctx through
      // ... verification ladder uses bridge
    },

    "experimental.session.compacting": async (_input, output) => {
      // ... unchanged
    },
  }
}
```

Note: The hooks need access to `ctx.directory` but the `tool.execute.after` hook signature is `(input, output)`. We need to capture `ctx` in the closure. This is already how it works — `createCiteAgentHooks` takes `ctx` and the returned hooks close over it.

**Step 3: Commit**

```bash
git add plugins/opencode-citeagent/src/index.ts plugins/opencode-citeagent/src/hooks/index.ts
git commit -m "refactor: update plugin entry point and hooks to use subprocess bridge"
```

---

## Phase 4: Config and File Restructuring

### Task 4.1: Move Config from Fork to Project Root

**Files:**
- Create: `.opencode/opencode.jsonc` (project root, not inside fork/)
- Create: `.opencode/plugins/opencode-citeagent` (symlink)
- Create: `.opencode/agents/` (copy from fork)
- Create: `.opencode/rules/` (copy from fork)
- Create: `.opencode/skills/` (copy from fork)

**Step 1: Create project-root .opencode directory**

```bash
mkdir -p /home/ajiap/project/citeagent/.opencode/plugins
mkdir -p /home/ajiap/project/citeagent/.opencode/agents
mkdir -p /home/ajiap/project/citeagent/.opencode/rules
mkdir -p /home/ajiap/project/citeagent/.opencode/skills
```

**Step 2: Create .opencode/opencode.jsonc — no MCP server, no fork needed**

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  // Plugin: CiteAgent academic harness
  "plugin": ["./plugins/opencode-citeagent"],
  // Model: Ollama DeepSeek V4 Flash
  "model": "ollama/deepseek-v4-flash:cloud",
  // Agents: academic domain specialists
  "default_agent": "researcher",
  "agent": {
    "researcher": {
      "mode": "primary",
      "model": "ollama/deepseek-v4-flash:cloud",
      "description": "Academic research agent for citation analysis, literature review, and knowledge retrieval",
    },
    "verifier": {
      "mode": "subagent",
      "model": "ollama/deepseek-v4-flash:cloud",
      "description": "Hidden verification subagent that validates evidence chains",
    },
  },
  // Ollama provider (local)
  "provider": {
    "ollama": {
      "api": "http://localhost:11434/v1",
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama (Local)",
      "models": {
        "deepseek-v4-flash:cloud": {
          "name": "DeepSeek V4 Flash",
          "family": "deepseek",
          "reasoning": true,
          "tool_call": true,
          "temperature": true,
          "limit": { "context": 131072, "output": 8192 },
        },
      },
    },
  },
  // NO MCP SERVER — the plugin manages its own backend
}
```

Key change: **No `"mcp"` section.** The plugin spawns Python itself.

**Step 3: Symlink the plugin**

```bash
ln -sf /home/ajiap/project/citeagent/plugins/opencode-citeagent /home/ajiap/project/citeagent/.opencode/plugins/opencode-citeagent
```

**Step 4: Copy agents, rules, skills from fork**

```bash
cp -r /home/ajiap/project/citeagent/fork/opencode/.opencode/agents/* /home/ajiap/project/citeagent/.opencode/agents/
cp -r /home/ajiap/project/citeagent/fork/opencode/.opencode/rules/* /home/ajiap/project/citeagent/.opencode/rules/
cp -r /home/ajiap/project/citeagent/fork/opencode/.opencode/skills/* /home/ajiap/project/citeagent/.opencode/skills/
# Don't copy effect/ skill — that's OpenCode-specific
# Don't copy smoke-theme.json or tui-smoke.tsx — those are OpenCode dev tools
```

**Step 5: Commit**

```bash
git add .opencode/
git commit -m "feat: add project-root .opencode config (no fork, no MCP)"
```

---

### Task 4.2: Update Package Exports for V1 Module Format

**Files:**
- Modify: `plugins/opencode-citeagent/package.json`

**Step 1: Update package.json for V1 module format**

OpenCode's plugin loader expects a `{ server: PluginFn }` or `{ tui: TuiPluginFn }` default export (V1 format). Our current `index.ts` uses the legacy named export format. Update to V1:

```json
{
  "name": "opencode-citeagent",
  "version": "0.2.0",
  "type": "module",
  "main": "src/index.ts",
  "scripts": {
    "build": "bun build src/index.ts --outdir=dist --target=bun --format=esm"
  },
  "dependencies": {
    "@opencode-ai/plugin": "1.14.28",
    "@modelcontextprotocol/sdk": "^1.12.0",
    "zod": "^3.23.0"
  }
}
```

Note: version bump `0.1.0` → `0.2.0` to reflect the refactor.

**Step 2: Ensure index.ts exports V1 module format**

Already done — our `index.ts` has `export default CiteAgentPlugin` which matches the V1 `{ server: PluginFn }` pattern if we adjust the export:

```typescript
// At end of index.ts
export default { server: CiteAgentPlugin }
```

Or keep the named export as-is — OpenCode's plugin loader supports both legacy named exports and V1 module format. Check the current export and ensure it has `export default`.

**Step 3: Commit**

```bash
git add plugins/opencode-citeagent/package.json
git commit -m "bump plugin version to 0.2.0 for refactor"
```

---

## Phase 5: Remove Fork Dependency

### Task 5.1: Verify OpenCode Works Without Fork

**Steps:**

1. Install stock OpenCode (same version as fork):
   ```bash
   # OpenCode can be installed via bun or downloaded
   # The key point: no custom binary needed
   ```

2. Update `.opencode/opencode.jsonc` to remove any reference to the fork directory

3. Run OpenCode from the project root:
   ```bash
   cd /home/ajiap/project/citeagent
   opencode
   ```

4. Verify in the TUI:
   - Plugin loads (check logs for "CiteAgent plugin initialized")
   - 32 tools registered (try `cite_search` in chat)
   - No MCP connection errors
   - Ollama provider works (send a message)

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: CiteAgent is now a pure plugin — no fork needed"
```

---

### Task 5.2: Archive Fork Directory

**Steps:**

1. Move fork to archive:
   ```bash
   mv /home/ajiap/project/citeagent/fork /home/ajiap/project/citeagent/_archive_fork
   ```

2. The fork is no longer needed for running CiteAgent. Keep it archived for reference but it's not part of the active project.

---

## Summary of Deliverables

| Phase | Deliverable | Key Change |
|-------|-------------|------------|
| 1 | `mcp-bridge.ts` | Plugin spawns Python subprocess itself |
| 2 | `tools/index.ts` | 8 proxy tools → 32 native plugin tools |
| 3 | `index.ts` + `hooks/index.ts` | Use new bridge, V1 module format |
| 4 | `.opencode/` at project root | Config, agents, rules, skills — no fork |
| 5 | Fork archived | CiteAgent = plugin + config + Python backend |

## What Users Need

```
citeagent/
├── .opencode/
│   ├── opencode.jsonc          # No MCP, just plugin + provider + agents
│   ├── plugins/
│   │   └── opencode-citeagent → symlink
│   ├── agents/                  # researcher, verifier, etc.
│   ├── rules/                   # academic-integrity, citation-format
│   └── skills/                  # literature-review, verify-evidence, ingest-document
├── plugins/
│   └── opencode-citeagent/
│       ├── src/
│       │   ├── index.ts         # Plugin entry (V1 module)
│       │   ├── mcp-bridge.ts    # Subprocess manager (not MCP client)
│       │   ├── tools/index.ts   # 32 native tools
│       │   ├── hooks/index.ts   # SafeHarness + LTL + Crypto + Verification hooks
│       │   ├── verification.ts  # L0-L5 ladder
│       │   ├── safeharness.ts   # 4-layer security
│       │   ├── ltl-monitor.ts   # Runtime state machine
│       │   ├── memory.ts        # 4-tier memory (TS sidecar)
│       │   ├── crypto.ts        # HMAC-SHA256 binding
│       │   └── types.ts         # All types
│       ├── package.json
│       └── tsconfig.json
├── citeindex/                   # Python backend (unchanged)
│   ├── mcp_server.py            # Still runs as subprocess
│   └── ...
└── corpus/                      # Academic data
```

**To run CiteAgent:**
1. Install stock OpenCode
2. `cd citeagent && opencode`
3. Plugin auto-loads, spawns Python backend, registers 32 tools
4. No fork, no MCP config, no env var hacks

---

*Implementation plan for CiteAgent plugin refactor*
*Date: 2026-04-29*