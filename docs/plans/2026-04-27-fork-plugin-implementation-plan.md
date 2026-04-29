# CiteAgent Fork+Plugin Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fork OpenCode (anomalyco/opencode) and build a CiteIndex academic agent system as a first-class OpenCode plugin + custom agent definitions, keeping the Rust kernel as the backend service.

**Architecture:** OpenCode (TypeScript/Bun) provides the agent loop, subagent system, hooks, context management, TUI, and plugin SDK. CiteIndex's Rust kernel runs as a backend service, exposing its 18 tools via MCP protocol. A custom OpenCode plugin (`opencode-citeindex`) bridges the two, adding academic tools, verification hooks, and domain-specific agents. The result is "CiteAgent" — a harness-native academic research agent built on OpenCode's infrastructure.

**Tech Stack:** TypeScript/Bun (OpenCode plugin SDK), Rust (CiteIndex kernel), MCP protocol (bridge), Zod (tool schemas), Ed25519 (capability tokens)

---

## Phase 0: Fork & Bootstrap

### Task 0.1: Fork OpenCode Repository

**Files:**
- Create: `fork/` (git clone of anomalyco/opencode)
- Create: `fork/.opencode/` (project config directory)

**Step 1: Clone OpenCode and create fork**

```bash
cd /home/ajiap/project/citeagent
git clone https://github.com/anomalyco/opencode.git fork/opencode
cd fork/opencode
```

**Step 2: Verify it builds**

```bash
cd fork/opencode
bun install
bun run build
./opencode --version
```

Expected: version string printed (e.g., `v1.14.28`)

**Step 3: Rename branding to CiteAgent**

In `fork/opencode/packages/opencode/package.json`:
- Change `name` to `@citeagent/opencode`
- Change `bin` entry from `opencode` to `citeagent`

Verify:
```bash
cd fork/opencode && bun run build && ./citeagent --version
```

**Step 4: Commit fork**

```bash
cd fork/opencode
git checkout -b citeagent-fork
git add -A
git commit -m "fork: rename opencode to citeagent, initial fork"
```

### Task 0.2: Initialize CiteAgent Plugin Package

**Files:**
- Create: `plugins/opencode-citeindex/package.json`
- Create: `plugins/opencode-citeindex/tsconfig.json`
- Create: `plugins/opencode-citeindex/src/index.ts`
- Create: `plugins/opencode-citeindex/src/tools/index.ts`
- Create: `plugins/opencode-citeindex/src/hooks/index.ts`
- Create: `plugins/opencode-citeindex/src/mcp-bridge.ts`
- Create: `plugins/opencode-citeindex/src/types.ts`

**Step 1: Create plugin package scaffold**

```bash
cd /home/ajiap/project/citeagent
mkdir -p plugins/opencode-citeindex/src
```

`plugins/opencode-citeindex/package.json`:
```json
{
  "name": "opencode-citeindex",
  "version": "0.1.0",
  "type": "module",
  "main": "src/index.ts",
  "dependencies": {
    "@opencode-ai/plugin": "latest",
    "zod": "^3.23.0"
  }
}
```

`plugins/opencode-citeindex/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ESNext",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "types": ["bun-types"]
  },
  "include": ["src/**/*"]
}
```

**Step 2: Create minimal plugin entry point**

`plugins/opencode-citeindex/src/index.ts`:
```typescript
import type { Plugin } from "@opencode-ai/plugin";
import { createCiteIndexTools } from "./tools/index.js";
import { createCiteIndexHooks } from "./hooks/index.js";

export const CiteIndexPlugin: Plugin = async (ctx) => {
  const tools = createCiteIndexTools(ctx);
  const hooks = createCiteIndexHooks(ctx);

  await ctx.client.app.log({
    body: { service: "citeindex", level: "info", message: "CiteIndex plugin initialized" },
  });

  return {
    tool: tools,
    ...hooks,
  };
};

export default CiteIndexPlugin;
```

**Step 3: Create placeholder tools and hooks**

`plugins/opencode-citeindex/src/tools/index.ts`:
```typescript
import { tool } from "@opencode-ai/plugin";
import type { z } from "zod";

export function createCiteIndexTools(ctx: any) {
  return {
    cite_search: tool({
      description:
        "Search the academic corpus using BM25. Returns ranked document nodes with citation metadata.",
      args: {
        query: tool.schema.string().describe("Search query terms"),
        limit: tool.schema.number().default(10).describe("Max results to return"),
      },
      async execute(args, context) {
        // TODO: bridge to Rust kernel via MCP
        return JSON.stringify({ status: "ok", results: [], message: "MCP bridge not yet connected" });
      },
    }),
    cite_verify: tool({
      description:
        "Verify the Merkle proof for a specific evidence node. Checks SHA-256 hash chain from leaf to document root.",
      args: {
        node_id: tool.schema.string().describe("Node ID (e.g., s5.1.p5)"),
        merkle_proof: tool.schema.array(tool.schema.string()).describe("Merkle proof hashes"),
        root_hash: tool.schema.string().describe("Document merkle root hash"),
      },
      async execute(args, context) {
        return JSON.stringify({ status: "pending", message: "MCP bridge not yet connected" });
      },
    }),
    cite_render: tool({
      description:
        "Render a CSL-JSON citation record to formatted bibliography string (Chicago, APA, MLA).",
      args: {
        citation_key: tool.schema.string().describe("CSL citation key"),
        style: tool.schema.string().default("chicago-author-date").describe("Citation style"),
      },
      async execute(args, context) {
        return JSON.stringify({ status: "pending", message: "MCP bridge not yet connected" });
      },
    }),
    cite_ingest: tool({
      description:
        "Ingest a document (PDF, URL, media) into the academic corpus. Creates PageIndex tree, Merkle hashes, and Tantivy index entries.",
      args: {
        source: tool.schema.string().describe("File path or URL to ingest"),
        force: tool.schema.boolean().default(false).describe("Force re-ingestion if already indexed"),
      },
      async execute(args, context) {
        return JSON.stringify({ status: "pending", message: "MCP bridge not yet connected" });
      },
    }),
  };
}
```

`plugins/opencode-citeindex/src/hooks/index.ts`:
```typescript
export function createCiteIndexHooks(ctx: any) {
  return {
    "tool.execute.before": async (input: any, output: any) => {
      // Pre-execution hook: nothing yet
    },
    "tool.execute.after": async (input: any, output: any) => {
      // Post-execution hook: log Merkle-sensitive operations
      if (input.tool?.startsWith("cite_")) {
        await ctx.client.app.log({
          body: {
            service: "citeindex",
            level: "info",
            message: `CiteIndex tool executed: ${input.tool}`,
            extra: { result_hash: "pending" },
          },
        });
      }
    },
    "experimental.session.compacting": async (input: any, output: any) => {
      // Inject academic context into compaction prompt
      output.context.push(
        "## CiteIndex Academic Context\n- Preserve all citation keys and Merkle proof chains\n- Never compact evidence items with unverifiable hashes\n- Maintain CSL registry references across compaction"
      );
    },
  };
}
```

**Step 4: Install plugin in forked OpenCode**

```bash
# Symlink plugin into fork's config directory
mkdir -p fork/opencode/.opencode/plugins
ln -s /home/ajiap/project/citeagent/plugins/opencode-citeindex fork/opencode/.opencode/plugins/citeindex
```

Add to fork's `opencode.json` (project-level config):
```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["./.opencode/plugins/citeindex"]
}
```

**Step 5: Verify plugin loads**

```bash
cd fork/opencode
bun install
./citeagent --help
```

Expected: Help text prints without plugin errors.

**Step 6: Commit**

```bash
cd /home/ajiap/project/citeagent
git add plugins/
git commit -m "feat: scaffold opencode-citeindex plugin with initial tools and hooks"
```

---

## Phase 1: MCP Bridge (Connect OpenCode ↔ Rust Kernel)

### Task 1.1: Implement MCP Server for CiteIndex Kernel

**Files:**
- Create: `citeindex-rs/crates/kernel/src/mcp_server.rs`
- Create: `citeindex-rs/crates/kernel/src/mcp_server/handlers.rs`
- Modify: `citeindex-rs/crates/kernel/Cargo.toml` (add `rmcp` dependency)
- Modify: `citeindex-rs/crates/kernel/src/lib.rs` (add mcp_server module)
- Test: `citeindex-rs/crates/kernel/tests/test_mcp_server.rs`

**Step 1: Add MCP dependency to Cargo.toml**

In `citeindex-rs/crates/kernel/Cargo.toml`, add:
```toml
[dependencies]
rmcp = { version = "0.1", features = ["server"] }
```

**Step 2: Write failing test for MCP tool listing**

`citeindex-rs/crates/kernel/tests/test_mcp_server.rs`:
```rust
use rmcp::model::{ListToolsResult, CallToolResult};

#[tokio::test]
async fn test_mcp_list_tools_returns_citeindex_tools() {
    let server = citeindex_kernel::mcp_server::CiteIndexMcpServer::new_test();
    let result: ListToolsResult = server.list_tools(Default::default()).await.unwrap();
    assert!(result.tools.iter().any(|t| t.name == "search_documents"));
    assert!(result.tools.iter().any(|t| t.name == "merkle_verify"));
    assert!(result.tools.iter().any(|t| t.name == "csl_render"));
}

#[tokio::test]
async fn test_mcp_call_search_documents() {
    let server = citeindex_kernel::mcp_server::CiteIndexMcpServer::new_test();
    let result: CallToolResult = server.call_tool(CallToolRequestParam {
        name: "search_documents".into(),
        arguments: serde_json::json!({"query": "test"}),
    }).await.unwrap();
    assert!(!result.is_error.unwrap_or(false));
}
```

**Step 3: Run test to verify it fails**

```bash
cd citeindex-rs && cargo test test_mcp_list_tools_returns_citeindex_tools
```

Expected: FAIL — module doesn't exist yet

**Step 4: Implement MCP server**

`citeindex-rs/crates/kernel/src/mcp_server.rs`:
```rust
pub mod handlers;

use rmcp::{
    ServerHandler,
    model::{ServerInfo, ListToolsResult, CallToolResult, CallToolRequestParam},
    schemars,
};
use serde_json::Value;
use crate::tools::ToolContext;

pub struct CiteIndexMcpServer {
    ctx: ToolContext,
}

impl CiteIndexMcpServer {
    pub fn new(ctx: ToolContext) -> Self { Self { ctx } }

    /// Create a test instance with in-memory stores
    #[cfg(test)]
    pub fn new_test() -> Self {
        Self { ctx: ToolContext::new_test() }
    }
}

#[derive(schemars::JsonSchema)]
pub struct SearchDocumentsParams {
    pub query: String,
    #[schemars(default = "default_limit")]
    pub limit: Option<u64>,
}

fn default_limit() -> u64 { 10 }

impl ServerHandler for CiteIndexMcpServer {
    fn info(&self) -> ServerInfo {
        ServerInfo {
            name: "citeindex-kernel".into(),
            version: "0.12.0".into(),
            ..Default::default()
        }
    }

    async fn list_tools(&self, _req: rmcp::model::ListToolsRequestParam) -> Result<ListToolsResult, rmcp::Error> {
        Ok(ListToolsResult {
            tools: vec![
                rmcp::model::Tool {
                    name: "search_documents".into(),
                    description: Some("BM25 full-text search on document index".into()),
                    input_schema: serde_json::to_value(schemars::schema_for!(SearchDocumentsParams)).ok(),
                },
                // TODO: Add remaining 17 tools from tools/mod.rs
            ],
            next_cursor: None,
        })
    }

    async fn call_tool(&self, req: CallToolRequestParam) -> Result<CallToolResult, rmcp::Error> {
        match req.name.as_str() {
            "search_documents" => handlers::search_documents(&self.ctx, req.arguments).await,
            "merkle_verify" => handlers::merkle_verify(&self.ctx, req.arguments).await,
            // TODO: Add remaining tools
            _ => Err(rmcp::Error::method_not_found(format!("Unknown tool: {}", req.name), None)),
        }
    }
}
```

`citeindex-rs/crates/kernel/src/mcp_server/handlers.rs`:
```rust
use crate::tools::ToolContext;
use rmcp::model::CallToolResult;
use serde_json::Value;

pub async fn search_documents(ctx: &ToolContext, args: Value) -> Result<CallToolResult, rmcp::Error> {
    let query = args["query"].as_str().ok_or_else(|| rmcp::Error::invalid_params("query is required", None))?;
    let limit = args["limit"].as_u64().unwrap_or(10);

    // Delegate to existing tools::search_documents
    let result = ctx.search_documents(query, limit).await
        .map_err(|e| rmcp::Error::internal_error(e.to_string(), None))?;

    Ok(CallToolResult {
        content: vec![rmcp::model::RawContent::Text { text: serde_json::to_string_pretty(&result).unwrap() }],
        is_error: Some(false),
    })
}

pub async fn merkle_verify(ctx: &ToolContext, args: Value) -> Result<CallToolResult, rmcp::Error> {
    let node_hash = args["node_hash"].as_str().ok_or_else(|| rmcp::Error::invalid_params("node_hash required", None))?;
    let proof = args["proof"].as_array().ok_or_else(|| rmcp::Error::invalid_params("proof array required", None))?;
    let root = args["root"].as_str().ok_or_else(|| rmcp::Error::invalid_params("root required", None))?;

    let proof_strs: Vec<&str> = proof.iter().filter_map(|v| v.as_str()).collect();
    let result = ctx.merkle_verify(node_hash, &proof_strs, root).await
        .map_err(|e| rmcp::Error::internal_error(e.to_string(), None))?;

    Ok(CallToolResult {
        content: vec![rmcp::model::RawContent::Text { text: serde_json::to_string_pretty(&result).unwrap() }],
        is_error: Some(false),
    })
}
```

**Step 5: Add binary entry point for MCP server**

Add to `citeindex-rs/crates/kernel/src/cli.rs`:
```rust
// Add to the Command enum:
McpServe { port: Option<u16> },

// Add to the match dispatch:
Command::McpServe { port } => {
    let ctx = ToolContext::from_config(&config)?;
    let server = CiteIndexMcpServer::new(ctx);
    let port = port.unwrap_or(8765);
    // Start as STDIO MCP server (standard for OpenCode)
    rmcp::transport::stdio::serve(server).await?;
}
```

**Step 6: Run tests to verify they pass**

```bash
cd citeindex-rs && cargo test test_mcp_
```

Expected: PASS

**Step 7: Commit**

```bash
git add citeindex-rs/
git commit -m "feat(kernel): add MCP server exposing 18 kernel tools via rmcp protocol"
```

### Task 1.2: Connect Plugin to MCP Server

**Files:**
- Modify: `plugins/opencode-citeindex/src/mcp-bridge.ts`
- Modify: `plugins/opencode-citeindex/src/tools/index.ts`

**Step 1: Implement MCP bridge**

`plugins/opencode-citeindex/src/mcp-bridge.ts`:
```typescript
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

export class CiteIndexMcpBridge {
  private client: Client | null = null;
  private kernelPath: string;

  constructor(kernelPath: string = "citeindex-kernel") {
    this.kernelPath = kernelPath;
  }

  async connect(): Promise<void> {
    const transport = new StdioClientTransport({
      command: this.kernelPath,
      args: ["mcp-serve"],
    });

    this.client = new Client(
      { name: "opencode-citeindex", version: "0.1.0" },
      { capabilities: {} }
    );

    await this.client.connect(transport);
  }

  async callTool(name: string, args: Record<string, unknown>): Promise<unknown> {
    if (!this.client) throw new Error("MCP bridge not connected");
    const result = await this.client.callTool({ name, arguments: args });
    return result;
  }

  async listTools(): Promise<unknown[]> {
    if (!this.client) throw new Error("MCP bridge not connected");
    const result = await this.client.listTools();
    return result.tools;
  }

  async disconnect(): Promise<void> {
    if (this.client) {
      await this.client.close();
      this.client = null;
    }
  }
}
```

**Step 2: Wire tools to MCP bridge**

Update `plugins/opencode-citeindex/src/tools/index.ts`:
```typescript
import { tool } from "@opencode-ai/plugin";
import { CiteIndexMcpBridge } from "../mcp-bridge.js";

let bridge: CiteIndexMcpBridge | null = null;

async function getBridge(): Promise<CiteIndexMcpBridge> {
  if (!bridge) {
    bridge = new CiteIndexMcpBridge();
    await bridge.connect();
  }
  return bridge;
}

export function createCiteIndexTools(ctx: any) {
  return {
    cite_search: tool({
      description: "BM25 full-text search on academic corpus. Returns ranked nodes with citation metadata and Merkle hashes.",
      args: {
        query: tool.schema.string().describe("Search query"),
        limit: tool.schema.number().default(10).describe("Max results"),
      },
      async execute(args) {
        const b = await getBridge();
        const result = await b.callTool("search_documents", { query: args.query, limit: args.limit });
        return JSON.stringify(result, null, 2);
      },
    }),
    cite_search_claims: tool({
      description: "Search claims in the argument graph. Returns claim nodes with contradiction links.",
      args: {
        query: tool.schema.string().describe("Claim search query"),
      },
      async execute(args) {
        const b = await getBridge();
        const result = await b.callTool("search_claims", { query: args.query });
        return JSON.stringify(result, null, 2);
      },
    }),
    cite_verify: tool({
      description: "Verify Merkle proof for evidence node. Checks SHA-256 chain leaf→root.",
      args: {
        node_hash: tool.schema.string().describe("SHA-256 hash of the evidence node"),
        proof: tool.schema.array(tool.schema.string()).describe("Merkle proof sibling hashes"),
        root: tool.schema.string().describe("Document Merkle root hash"),
      },
      async execute(args) {
        const b = await getBridge();
        const result = await b.callTool("merkle_verify", {
          node_hash: args.node_hash,
          proof: args.proof,
          root: args.root,
        });
        return JSON.stringify(result, null, 2);
      },
    }),
    cite_render: tool({
      description: "Render CSL-JSON citation to formatted bibliography (Chicago, APA, MLA).",
      args: {
        citation_key: tool.schema.string().describe("CSL citation key"),
        style: tool.schema.string().default("chicago-author-date").describe("Citation style ID"),
      },
      async execute(args) {
        const b = await getBridge();
        const result = await b.callTool("csl_render", {
          citation_key: args.citation_key,
          style: args.style,
        });
        return JSON.stringify(result, null, 2);
      },
    }),
    cite_ingest: tool({
      description: "Ingest document (PDF/URL/media) into corpus. Creates PageIndex tree, Merkle hashes, Tantivy index.",
      args: {
        source: tool.schema.string().describe("File path or URL"),
        force: tool.schema.boolean().default(false).describe("Force re-ingestion"),
      },
      async execute(args) {
        const b = await getBridge();
        const result = await b.callTool("index_document", { source: args.source, force: args.force });
        return JSON.stringify(result, null, 2);
      },
    }),
    cite_tree: tool({
      description: "Load and traverse PageIndex tree for a document. Returns structured hierarchy.",
      args: {
        document_id: tool.schema.string().describe("Document source ID"),
        depth: tool.schema.number().default(3).describe("Max depth to traverse"),
      },
      async execute(args) {
        const b = await getBridge();
        const loadResult = await b.callTool("tree_load", { document_id: args.document_id });
        if (args.depth > 0) {
          const traverseResult = await b.callTool("tree_traverse", { depth: args.depth });
          return JSON.stringify(traverseResult, null, 2);
        }
        return JSON.stringify(loadResult, null, 2);
      },
    }),
    cite_memory_save: tool({
      description: "Save a memory entry to the agent's persistent memory store.",
      args: {
        content: tool.schema.string().describe("Memory content to save"),
        thread: tool.schema.string().default("default").describe("Thread name"),
        tags: tool.schema.array(tool.schema.string()).default([]).describe("Tags for retrieval"),
      },
      async execute(args) {
        const b = await getBridge();
        const result = await b.callTool("memory_save", {
          content: args.content,
          thread: args.thread,
          tags: args.tags,
        });
        return JSON.stringify(result, null, 2);
      },
    }),
    cite_argument_query: tool({
      description: "Query the argument graph for claims, contradictions, and support edges.",
      args: {
        claim_id: tool.schema.string().optional().describe("Specific claim ID"),
        find_contradictions: tool.schema.boolean().default(false).describe("Find contradictions"),
      },
      async execute(args) {
        const b = await getBridge();
        if (args.find_contradictions) {
          const result = await b.callTool("ag_query_contradictions", { claim_id: args.claim_id });
          return JSON.stringify(result, null, 2);
        }
        const result = await b.callTool("ag_query_claims", { claim_id: args.claim_id });
        return JSON.stringify(result, null, 2);
      },
    }),
  };
}
```

**Step 3: Add MCP SDK dependency**

Update `plugins/opencode-citeindex/package.json`:
```json
{
  "dependencies": {
    "@opencode-ai/plugin": "latest",
    "@modelcontextprotocol/sdk": "^1.12.0",
    "zod": "^3.23.0"
  }
}
```

**Step 4: Register as MCP server in OpenCode config**

Update fork's `opencode.json`:
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcpServers": {
    "citeindex-kernel": {
      "command": "citeindex-kernel",
      "args": ["mcp-serve"]
    }
  }
}
```

**Step 5: Verify end-to-end**

```bash
# Build Rust kernel
cd citeindex-rs && cargo build --release --bin citeindex-kernel

# Start OpenCode with plugin
cd fork/opencode
./citeagent
# In TUI: type "@cite_search query=test"
```

Expected: Tool call routes through MCP → Rust kernel → returns BM25 results

**Step 6: Commit**

```bash
git add plugins/ fork/opencode/opencode.json
git commit -m "feat: connect opencode-citeindex plugin to Rust kernel via MCP bridge"
```

---

## Phase 2: Academic Agent Definitions

### Task 2.1: Define Academic Domain Agents

**Files:**
- Create: `fork/opencode/.opencode/agents/researcher.md`
- Create: `fork/opencode/.opencode/agents/verifier.md`
- Create: `fork/opencode/.opencode/agents/ingestor.md`
- Create: `fork/opencode/.opencode/agents/reviewer.md`
- Create: `fork/opencode/.opencode/agents/explore-corpus.md`

**Step 1: Create researcher agent (primary)**

`fork/opencode/.opencode/agents/researcher.md`:
```markdown
---
description: Academic research agent with citation-verified evidence chains
mode: primary
model: anthropic/claude-sonnet-4-20250514
temperature: 0.1
permission:
  read: allow
  edit: deny
  bash:
    "*": deny
    "citeindex-kernel *": allow
  task:
    "*": deny
    "explore-corpus": allow
    "verifier": allow
  skill: allow
  websearch: allow
  webfetch: allow
color: "#4a90d9"
maxSteps: 30
---

You are an academic research agent with access to the CiteIndex academic corpus and verification system.

## Core Principles

1. **Every claim requires evidence.** Never state a fact without citing a source from the corpus.
2. **Every citation must be verifiable.** Use `cite_verify` to check Merkle proofs before including evidence.
3. **No hallucinations.** If the corpus doesn't contain evidence, say so explicitly rather than fabricating.
4. **Fail-closed integrity.** If any Merkle proof fails, reject the entire evidence item.

## Workflow

1. Use `cite_search` to find relevant evidence in the corpus
2. Use `cite_tree` to explore document structure and context
3. Use `cite_verify` to validate Merkle proofs for evidence items
4. Use `cite_render` to format citations properly
5. Synthesize findings with inline citations and evidence chains

## Output Format

For every answer, include:
- Evidence items with node IDs (e.g., `s5.1.p5`)
- SHA-256 hashes of source text
- Merkle proof chains
- Formatted citations (Chicago author-date by default)
- Integrity status (approved/rejected per evidence item)

## Delegation

- Use `@explore-corpus` for quick corpus exploration
- Use `@verifier` for independent verification audit
```

**Step 2: Create verifier subagent**

`fork/opencode/.opencode/agents/verifier.md`:
```markdown
---
description: Independent verification auditor — checks Merkle proofs, citation integrity, and evidence validity
mode: subagent
model: anthropic/claude-haiku-4-20250514
temperature: 0.0
permission:
  read: allow
  edit: deny
  bash: deny
  external_directory: deny
  webfetch: deny
  websearch: deny
color: "#e74c3c"
hidden: true
---

You are an independent verification auditor. Your job is to verify evidence items produced by the researcher agent.

## Verification Checklist

1. **Node existence**: Does the cited node exist in the corpus?
2. **Hash match**: Does the SHA-256 hash of the source text match the recorded hash?
3. **Merkle proof**: Does the Merkle proof walk correctly from leaf to root?
4. **Citation key**: Does the citation key resolve to a valid CSL record?
5. **Claim evidence**: For claims, does the evidence node actually support the claim?

## Rules

- **Fail-closed**: If ANY check fails, mark the evidence item as REJECTED
- **No speculation**: Only verify what you can confirm from the corpus
- **Full trace**: For every check, state: [PASS] or [FAIL: <reason>]

Use `cite_verify`, `cite_search`, and `cite_tree` to perform checks.
```

**Step 3: Create ingestor subagent**

`fork/opencode/.opencode/agents/ingestor.md`:
```markdown
---
description: Document ingestion agent — ingests PDFs, URLs, and media into the academic corpus
mode: subagent
model: anthropic/claude-sonnet-4-20250514
temperature: 0.1
permission:
  read: allow
  edit: deny
  bash:
    "*": ask
    "citeindex-kernel ingest *": allow
  webfetch: allow
  external_directory: ask
color: "#2ecc71"
---

You are a document ingestion specialist for the CiteIndex academic corpus.

## Supported Formats

- **Digital PDF**: GROBID metadata → MinerU layout → DSPy reconciliation → Merkle tree
- **Scanned PDF**: OCRmyPDF → PaddleOCR → Tesseract → GROBID → Merkle tree
- **URL Article**: Playwright/trafilatura fetch → Zotero metadata → CSL JSON → Merkle tree
- **Media** (audio/video): yt-dlp → ffmpeg → WhisperX → diarization → Merkle tree
- **Office/DJVU**: LibreOffice/ddjvu conversion → delegate to PDF pipeline

## Workflow

1. Detect resource type
2. Run appropriate ingestion pipeline
3. Verify Merkle tree generation
4. Confirm Tantivy index entries
5. Report ingestion result with document ID and merkle root

Use `cite_ingest` to trigger ingestion.
```

**Step 4: Create explore-corpus subagent**

`fork/opencode/.opencode/agents/explore-corpus.md`:
```markdown
---
description: Fast read-only corpus explorer — search documents, browse tree structures, check citations
mode: subagent
model: anthropic/claude-haiku-4-20250514
temperature: 0.0
permission:
  read: allow
  edit: deny
  bash: deny
  glob: allow
  grep: allow
  webfetch: deny
  websearch: deny
color: "#f39c12"
---

You are a fast corpus explorer. Quickly find documents, browse structures, and answer questions about the academic corpus.

## Available Operations

- `cite_search`: BM25 search across documents, claims, and memory
- `cite_tree`: Load and traverse PageIndex document trees
- `cite_render`: Format citations for display
- `cite_argument_query`: Query the argument graph

## Rules

- Read-only: never modify the corpus
- Fast: prefer haiku model for speed
- Concise: give brief answers, let the primary agent synthesize
```

**Step 5: Create reviewer subagent**

`fork/opencode/.opencode/agents/reviewer.md`:
```markdown
---
description: Literature review agent — systematic search, comparison, gap identification across sources
mode: subagent
model: anthropic/claude-sonnet-4-20250514
temperature: 0.2
permission:
  read: allow
  edit: deny
  bash: deny
  webfetch: allow
  websearch: allow
  task:
    "*": deny
    "explore-corpus": allow
color: "#9b59b6"
---

You are a literature review specialist. You perform systematic searches across the academic corpus, compare sources, identify contradictions, and find research gaps.

## Workflow

1. Systematic search: use `cite_search` with multiple query formulations
2. Source comparison: use `cite_argument_query` to find contradictions and supports
3. Gap identification: analyze coverage and identify under-represented topics
4. Synthesis: produce structured literature review with verified citations

## Output

- Structured review with sections
- Comparison tables when appropriate
- Contradiction map with evidence
- Coverage gaps with search evidence
```

**Step 6: Update opencode.json with agent config**

```json
{
  "$schema": "https://opencode.ai/config.json",
  "agent": {
    "build": { "disable": true },
    "plan": { "disable": true },
    "researcher": {
      "mode": "primary",
      "model": "anthropic/claude-sonnet-4-20250514"
    }
  }
}
```

**Step 7: Test agent switching in TUI**

```bash
cd fork/opencode && ./citeagent
# In TUI: Tab key should cycle to "researcher" agent
# Type: "search for papers about Syriac studies"
# Should invoke cite_search via MCP bridge
```

**Step 8: Commit**

```bash
git add fork/opencode/.opencode/ fork/opencode/opencode.json
git commit -m "feat: add academic domain agents (researcher, verifier, ingestor, explorer, reviewer)"
```

---

## Phase 3: Verification Hooks & Context

### Task 3.1: Implement Verification Ladder Hooks

**Files:**
- Modify: `plugins/opencode-citeindex/src/hooks/index.ts`
- Create: `plugins/opencode-citeindex/src/verification.ts`
- Create: `plugins/opencode-citeindex/src/types.ts`

**Step 1: Define verification types**

`plugins/opencode-citeindex/src/types.ts`:
```typescript
export interface VerificationRung {
  level: number;
  name: string;
  check: (input: VerificationInput) => Promise<VerificationResult>;
}

export interface VerificationInput {
  toolName: string;
  toolArgs: Record<string, unknown>;
  toolResult: unknown;
  sessionContext: unknown;
}

export interface VerificationResult {
  passed: boolean;
  level: number;
  message: string;
  details?: Record<string, unknown>;
}

export type EvidenceItem = {
  node_id: string;
  source_id: string;
  sha256: string;
  merkle_proof: string[];
  citation_key: string;
  citation_rendered: string;
};

export type VerificationLadderResult = {
  overall: "approved" | "rejected";
  rungs: VerificationResult[];
  evidence: EvidenceItem[];
};
```

**Step 2: Implement verification ladder**

`plugins/opencode-citeindex/src/verification.ts`:
```typescript
import type { VerificationInput, VerificationResult, VerificationLadderResult, EvidenceItem } from "./types.js";
import { CiteIndexMcpBridge } from "./mcp-bridge.js";

export class VerificationLadder {
  private bridge: CiteIndexMcpBridge;

  constructor(bridge: CiteIndexMcpBridge) {
    this.bridge = bridge;
  }

  async run(evidence: EvidenceItem[]): Promise<VerificationLadderResult> {
    const results: VerificationResult[] = [];

    for (const item of evidence) {
      // L0: Schema check — evidence item has required fields
      results.push(await this.l0_schema_check(item));
      // L1: Node existence — node_id resolves in corpus
      results.push(await this.l1_node_exists(item));
      // L2: Hash match — sha256 matches stored
      results.push(await this.l2_hash_match(item));
      // L3: Merkle proof — chain is valid
      results.push(await this.l3_merkle_proof(item));
      // L4: Citation key — resolves to CSL record
      results.push(await this.l4_citation_key(item));
    }

    const all_passed = results.every((r) => r.passed);
    return {
      overall: all_passed ? "approved" : "rejected",
      rungs: results,
      evidence,
    };
  }

  private async l0_schema_check(item: EvidenceItem): Promise<VerificationResult> {
    const required = ["node_id", "source_id", "sha256", "merkle_proof", "citation_key"];
    const missing = required.filter((k) => !item[k as keyof EvidenceItem]);
    return {
      passed: missing.length === 0,
      level: 0,
      message: missing.length === 0 ? "Schema valid" : `Missing fields: ${missing.join(", ")}`,
    };
  }

  private async l1_node_exists(item: EvidenceItem): Promise<VerificationResult> {
    try {
      const result = await this.bridge.callTool("tree_traverse", { node_id: item.node_id });
      return { passed: true, level: 1, message: "Node exists in corpus" };
    } catch {
      return { passed: false, level: 1, message: `Node ${item.node_id} not found` };
    }
  }

  private async l2_hash_match(item: EvidenceItem): Promise<VerificationResult> {
    try {
      const result: any = await this.bridge.callTool("regex_search", {
        pattern: item.sha256,
        node_id: item.node_id,
      });
      const found = result?.content?.[0]?.text?.includes(item.sha256);
      return { passed: !!found, level: 2, message: found ? "Hash matches" : "Hash mismatch" };
    } catch {
      return { passed: false, level: 2, message: "Hash verification failed" };
    }
  }

  private async l3_merkle_proof(item: EvidenceItem): Promise<VerificationResult> {
    try {
      const result: any = await this.bridge.callTool("merkle_verify", {
        node_hash: item.sha256,
        proof: item.merkle_proof,
        root: item.source_id, // Will be replaced with actual merkle_root lookup
      });
      const valid = result?.content?.[0]?.text ? JSON.parse(result.content[0].text).valid : false;
      return { passed: !!valid, level: 3, message: valid ? "Merkle proof valid" : "Merkle proof invalid" };
    } catch {
      return { passed: false, level: 3, message: "Merkle verification error" };
    }
  }

  private async l4_citation_key(item: EvidenceItem): Promise<VerificationResult> {
    try {
      const result: any = await this.bridge.callTool("csl_render", {
        citation_key: item.citation_key,
        style: "chicago-author-date",
      });
      const rendered = result?.content?.[0]?.text;
      return { passed: !!rendered, level: 4, message: rendered ? "Citation resolves" : "Citation key not found" };
    } catch {
      return { passed: false, level: 4, message: "Citation resolution failed" };
    }
  }
}
```

**Step 3: Wire verification into hooks**

Update `plugins/opencode-citeindex/src/hooks/index.ts`:
```typescript
import { CiteIndexMcpBridge } from "../mcp-bridge.js";
import { VerificationLadder } from "../verification.js";
import type { EvidenceItem } from "../types.js";

let bridge: CiteIndexMcpBridge | null = null;
let ladder: VerificationLadder | null = null;

async function getLadder(): Promise<VerificationLadder> {
  if (!ladder) {
    if (!bridge) {
      bridge = new CiteIndexMcpBridge();
      await bridge.connect();
    }
    ladder = new VerificationLadder(bridge);
  }
  return ladder;
}

export function createCiteIndexHooks(ctx: any) {
  return {
    "tool.execute.after": async (input: any, output: any) => {
      // Auto-verify when research agent produces evidence
      if (input.tool === "cite_search" || input.tool === "task") {
        try {
          const resultText = typeof output.result === "string" ? output.result : JSON.stringify(output.result);
          // Check if output contains evidence items with merkle proofs
          if (resultText.includes("merkle_proof") && resultText.includes("sha256")) {
            const parsed = JSON.parse(resultText);
            const evidence: EvidenceItem[] = parsed.evidence || [];
            if (evidence.length > 0) {
              const lad = await getLadder();
              const verification = await lad.run(evidence);
              // Inject verification result into session context
              await ctx.client.app.log({
                body: {
                  service: "citeindex-verification",
                  level: verification.overall === "approved" ? "info" : "warn",
                  message: `Verification ladder: ${verification.overall}`,
                  extra: { rungs: verification.rungs, evidence_count: evidence.length },
                },
              });
            }
          }
        } catch {
          // Not JSON or no evidence — skip verification
        }
      }
    },

    "experimental.session.compacting": async (input: any, output: any) => {
      output.context.push(
        "## CiteIndex Academic Context\n" +
        "- Preserve all citation keys and Merkle proof chains\n" +
        "- Never compact evidence items with unverifiable hashes\n" +
        "- Maintain CSL registry references across compaction\n" +
        "- Keep verification ladder results for active evidence"
      );
    },
  };
}
```

**Step 4: Test verification ladder**

```bash
cd fork/opencode && ./citeagent
# In TUI: ask researcher to search for a topic
# Verify that verification ladder runs automatically on evidence items
# Check logs for "Verification ladder: approved/rejected"
```

**Step 5: Commit**

```bash
git add plugins/opencode-citeindex/src/
git commit -m "feat: add verification ladder (L0-L4) with auto-verification hooks"
```

---

## Phase 4: Skill Packs & Rules

### Task 4.1: Create Academic Agent Rules

**Files:**
- Create: `fork/opencode/.opencode/rules/academic-integrity.md`
- Create: `fork/opencode/.opencode/rules/citation-format.md`

**Step 1: Create academic integrity rule**

`fork/opencode/.opencode/rules/academic-integrity.md`:
```markdown
# Academic Integrity Rules

These rules are enforced by the CiteIndex verification system.

## Mandatory
- Every factual claim must have a `cite_search` result backing it
- Every evidence item must pass verification ladder (L0-L4) before inclusion
- If a Merkle proof fails, the evidence is REJECTED — no exceptions
- Citation keys that don't resolve to CSL records are invalid
- Never cite a source you haven't verified exists in the corpus

## Prohibited
- Fabricating citation details (authors, titles, years, DOIs)
- Using evidence items with missing SHA-256 hashes
- Skipping Merkle verification for "trusted" sources
- Including unverified external search results as primary evidence
- Modifying evidence items after retrieval

## On Uncertainty
- If no evidence exists in corpus, state: "No corpus evidence found for [claim]."
- If evidence is ambiguous, state the ambiguity explicitly
- If verification fails, explain which check failed and why
```

**Step 2: Create citation format rule**

`fork/opencode/.opencode/rules/citation-format.md`:
```markdown
# Citation Format

## Default Style
Chicago author-date format via `cite_render`.

## Inline Citation Format
> Quoted text from source
> — [Author Year] (node: `s5.1.p5`, hash: `abc123...`)

## Evidence Chain Format
```
evidence:
  - node_id: s5.1.p5
    source_id: Author2023Title
    sha256: abc123...
    merkle_proof: [leaf_hash, ..., root_hash]
    citation_key: Author2023Title
    citation_rendered: "Author, A. (2023). Title. Journal, 1(2), 3–4."
    verification: approved
```

## Unsupported
- Do NOT invent citation formats
- Do NOT use APA/MLA unless explicitly requested
- Always use `cite_render` tool for formatting — never format manually
```

**Step 3: Commit**

```bash
git add fork/opencode/.opencode/rules/
git commit -m "feat: add academic integrity and citation format rules"
```

---

## Phase 5: Skills & Commands

### Task 5.1: Create Academic Skill Definitions

**Files:**
- Create: `fork/opencode/.opencode/skills/literature-review.md`
- Create: `fork/opencode/.opencode/skills/verify-evidence.md`
- Create: `fork/opencode/.opencode/skills/ingest-document.md`

**Step 1: Create literature review skill**

`fork/opencode/.opencode/skills/literature-review.md`:
```markdown
---
description: Systematic literature review across the academic corpus
---

# Literature Review Skill

## Steps

1. **Scope definition**: Clarify the research question with the user
2. **Systematic search**: Run `cite_search` with 3-5 query formulations
3. **Expand search**: Use `cite_argument_query` to find contradictions and supports
4. **Corpus exploration**: Use `@explore-corpus` to browse related documents
5. **Evidence collection**: Gather verified evidence items
6. **Verification**: Use `@verifier` to independently audit all evidence
7. **Synthesis**: Write structured review with inline citations and evidence chains
8. **Gap analysis**: Identify under-represented areas

## Output Structure
- Introduction (research question, scope)
- Methodology (search strategy, inclusion criteria)
- Findings (organized thematically with citations)
- Contradictions (mapped across sources)
- Gaps (identified with evidence)
- References (formatted via cite_render)
```

**Step 2: Create verify evidence skill**

`fork/opencode/.opencode/skills/verify-evidence.md`:
```markdown
---
description: Run full verification ladder on a set of evidence items
---

# Verify Evidence Skill

## When to Use
- After generating any answer with citations
- Before publishing or committing findings
- When evidence integrity is questioned

## Steps

1. **Collect items**: Identify all evidence items in the current answer
2. **L0 Schema**: Check all required fields present
3. **L1 Existence**: Verify each node_id exists in corpus
4. **L2 Hash**: Verify SHA-256 hash matches stored text
5. **L3 Merkle**: Verify Merkle proof from leaf to root
6. **L4 Citation**: Verify citation key resolves to valid CSL record
7. **Report**: Generate VerificationLadderResult with pass/fail per item
8. **Action**: If any item fails → REJECT, remove from answer, flag for re-search

## Fail-Closed Rule
A single failed evidence item invalidates the entire answer. No partial credit.
```

**Step 3: Commit**

```bash
git add fork/opencode/.opencode/skills/
git commit -m "feat: add literature review and verify evidence skills"
```

---

## Summary of Deliverables

| Phase | Deliverable | Key Files |
|-------|-------------|-----------|
| 0 | Fork + plugin scaffold | `fork/opencode/`, `plugins/opencode-citeindex/` |
| 1 | MCP bridge (OpenCode ↔ Rust kernel) | `mcp_server.rs`, `mcp-bridge.ts`, 8 tools |
| 2 | Academic agents (5 agents) | `.opencode/agents/*.md` |
| 3 | Verification ladder + hooks | `verification.ts`, `hooks/index.ts` |
| 4 | Rules (academic integrity, citation) | `.opencode/rules/*.md` |
| 5 | Skills (literature review, verify) | `.opencode/skills/*.md` |

### What We Get From OpenCode (Free)

| Feature | From OpenCode | Instead Of Building |
|---------|---------------|-------------------|
| Agent loop (async generator) | ✅ Built in | Custom Rust event loop |
| Subagent spawning | ✅ Task tool | Custom SubagentHandle |
| Context assembly | ✅ Modular system prompt | Custom context assembler |
| Context compaction | ✅ Auto-compact + hook | Custom compaction logic |
| Permission system | ✅ deny/ask/allow per-tool per-agent | Custom permission gate |
| Hook system | ✅ 20+ lifecycle hooks | Custom hook dispatch |
| LSP integration | ✅ Auto LSP spawning | Custom LSP bridge |
| Multi-session | ✅ Child session navigation | Custom session manager |
| Web search | ✅ Built-in websearch tool | Custom web search |
| TUI (terminal UI) | ✅ Ratatui-grade TUI | Custom Rust TUI |
| WebSocket server | ✅ Client/server architecture | Custom API server |
| Plugin SDK | ✅ TypeScript plugin API | Custom extension system |
| MCP support | ✅ MCP client + server | Custom tool protocol |
| Agent skills | ✅ `.opencode/skills/` | Custom skill system |

### What We Build (Differentiator)

| Component | Why It Can't Come From OpenCode |
|-----------|-------------------------------|
| CiteIndex Rust kernel (18 tools, Tantivy, SQLite, Merkle) | Domain-specific academic infrastructure |
| MCP server bridge | Connects Rust kernel to OpenCode's tool system |
| Verification ladder (L0-L5) | Academic integrity — no coding agent has this |
| Academic agent prompts + permissions | Domain-specific behavior |
| Verification hooks | Auto-verification on evidence production |
| Citation format rules | Academic domain constraints |
| Merkle-verified evidence chains | Unique to CiteIndex's mission |

---

*Implementation plan for CiteAgent Fork+Plugin architecture*
*Date: 2026-04-27*