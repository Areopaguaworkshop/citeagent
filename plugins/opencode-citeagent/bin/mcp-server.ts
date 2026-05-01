#!/usr/bin/env bun
/**
 * CiteAgent Standalone MCP Server
 *
 * Runs CiteAgentEngine natively in TypeScript via the Model Context Protocol
 * (stdio transport). No Python required.
 *
 * Usage:
 *   bunx @ephremyuan/citeagent mcp-server
 *   bunx @ephremyuan/citeagent mcp-server --corpus-root /path/to/corpus
 *
 * This serves the same 25 tools as the Python `citeagent.mcp_server`,
 * but runs entirely in-process — no subprocess, no Python dependency.
 * Only `cite_ingest`/`cite_tantivy_index` shells out to the `citeindex` CLI
 * as an optional sidecar.
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js"
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js"
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js"
import { CiteAgentEngine } from "../src/engine/index.js"

// ---------------------------------------------------------------------------
// Tool definitions — mirrors the Python MCP server's TOOL_DEFINITIONS
// ---------------------------------------------------------------------------

const TOOL_DEFINITIONS = [
  {
    name: "search_documents",
    description: "BM25 full-text search over indexed documents.",
    inputSchema: {
      type: "object" as const,
      properties: {
        query: { type: "string", description: "Search query string" },
        limit: { type: "integer", description: "Maximum number of results", default: 10 },
      },
      required: ["query"],
    },
  },
  {
    name: "search_claims",
    description: "Search claims in the argument graph.",
    inputSchema: {
      type: "object" as const,
      properties: {
        query: { type: "string", description: "Search query for claims" },
        limit: { type: "integer", description: "Maximum number of results", default: 10 },
      },
      required: ["query"],
    },
  },
  {
    name: "search_memory",
    description: "Search persisted memory entries.",
    inputSchema: {
      type: "object" as const,
      properties: {
        query: { type: "string", description: "Search query for memory" },
        thread_id: { type: "string", description: "Thread to search" },
        limit: { type: "integer", description: "Maximum number of results", default: 10 },
      },
      required: ["query"],
    },
  },
  {
    name: "index_document",
    description: "Ingest and index a document into the knowledge base. Requires citeindex CLI for full pipeline.",
    inputSchema: {
      type: "object" as const,
      properties: {
        path: { type: "string", description: "File path or URL of the document" },
        metadata: { type: "object", description: "Optional metadata dict to attach" },
      },
      required: ["path"],
    },
  },
  {
    name: "index_claim",
    description: "Index a claim extracted from a document.",
    inputSchema: {
      type: "object" as const,
      properties: {
        claim_text: { type: "string", description: "The claim text" },
        source_id: { type: "string", description: "Source document identifier" },
        metadata: { type: "object", description: "Optional metadata dict" },
      },
      required: ["claim_text", "source_id"],
    },
  },
  {
    name: "delete_document",
    description: "Remove a document and its associated data from the index.",
    inputSchema: {
      type: "object" as const,
      properties: {
        source_id: { type: "string", description: "Identifier of the document to delete" },
      },
      required: ["source_id"],
    },
  },
  {
    name: "ag_query_claims",
    description: "Query claims from the argument graph.",
    inputSchema: {
      type: "object" as const,
      properties: {
        claim_id: { type: "string", description: "Optional specific claim ID" },
        source_id: { type: "string", description: "Optional source document filter" },
        limit: { type: "integer", description: "Maximum results", default: 10 },
      },
    },
  },
  {
    name: "ag_query_contradictions",
    description: "Find contradictions in the argument graph.",
    inputSchema: {
      type: "object" as const,
      properties: {
        claim_id: { type: "string", description: "Optional claim ID to check" },
        limit: { type: "integer", description: "Maximum results", default: 10 },
      },
    },
  },
  {
    name: "merkle_compute",
    description: "Compute a Merkle hash for a given payload.",
    inputSchema: {
      type: "object" as const,
      properties: {
        payload: { type: "string", description: "The data to hash (UTF-8 string)" },
      },
      required: ["payload"],
    },
  },
  {
    name: "merkle_verify",
    description: "Verify a Merkle proof against a known root hash.",
    inputSchema: {
      type: "object" as const,
      properties: {
        node_hash: { type: "string", description: "Hash of the node to verify" },
        proof: { type: "array", items: { type: "string" }, description: "Merkle proof (sibling hashes)" },
        root: { type: "string", description: "Expected Merkle root hash" },
      },
      required: ["node_hash", "proof", "root"],
    },
  },
  {
    name: "csl_render",
    description: "Render a citation in a given CSL style.",
    inputSchema: {
      type: "object" as const,
      properties: {
        citation_key: { type: "string", description: "Citation key to render" },
        style: { type: "string", description: "CSL style (apa, chicago-author-date, ieee, mla)", default: "apa" },
      },
      required: ["citation_key"],
    },
  },
  {
    name: "tree_load",
    description: "Load a PageIndex tree structure.",
    inputSchema: {
      type: "object" as const,
      properties: {
        source_id: { type: "string", description: "Document source ID" },
        depth: { type: "integer", description: "Maximum depth to load", default: -1 },
      },
      required: ["source_id"],
    },
  },
  {
    name: "tree_traverse",
    description: "Traverse a PageIndex tree with an optional path.",
    inputSchema: {
      type: "object" as const,
      properties: {
        source_id: { type: "string", description: "Document source ID" },
        path: { type: "string", description: "Path within the tree to traverse" },
      },
      required: ["source_id"],
    },
  },
  {
    name: "regex_search",
    description: "Search indexed documents using a regular expression.",
    inputSchema: {
      type: "object" as const,
      properties: {
        pattern: { type: "string", description: "Regular expression pattern" },
        source_id: { type: "string", description: "Optional document source filter" },
        limit: { type: "integer", description: "Maximum number of results", default: 10 },
        context_chars: { type: "integer", description: "Context characters around match", default: 120 },
      },
      required: ["pattern"],
    },
  },
  {
    name: "memory_save",
    description: "Save a memory entry for later retrieval.",
    inputSchema: {
      type: "object" as const,
      properties: {
        content: { type: "string", description: "The memory content to store" },
        tags: { type: "array", items: { type: "string" }, description: "Optional tags" },
        metadata: { type: "object", description: "Optional metadata dict" },
      },
      required: ["content"],
    },
  },
  {
    name: "tantivy_search",
    description: "Full-text search (uses BM25 engine internally).",
    inputSchema: {
      type: "object" as const,
      properties: {
        query: { type: "string", description: "Search query string" },
        limit: { type: "integer", description: "Maximum results", default: 10 },
      },
      required: ["query"],
    },
  },
  {
    name: "tantivy_index",
    description: "Index a document (delegates to citeindex CLI for full pipeline).",
    inputSchema: {
      type: "object" as const,
      properties: {
        path: { type: "string", description: "File path to index" },
        metadata: { type: "object", description: "Optional metadata dict" },
      },
      required: ["path"],
    },
  },
  {
    name: "audit_save",
    description: "Save an audit result (verdict + evidence hashes).",
    inputSchema: {
      type: "object" as const,
      properties: {
        audit_id: { type: "string", description: "Unique audit identifier" },
        verdict: { type: "string", description: "Audit verdict (approved/rejected)" },
        reasoning: { type: "string", description: "Reasoning for the verdict" },
        evidence_hashes: { type: "array", items: { type: "string" }, description: "Evidence SHA-256 hashes" },
        query: { type: "string", description: "Original query being audited" },
      },
      required: ["audit_id", "verdict"],
    },
  },
  {
    name: "audit_retrieve",
    description: "Retrieve a saved audit result.",
    inputSchema: {
      type: "object" as const,
      properties: {
        audit_id: { type: "string", description: "Audit identifier to retrieve" },
      },
      required: ["audit_id"],
    },
  },
  {
    name: "memory_store_tier",
    description: "Store a memory entry in a specific tier (working/episodic/long_term/corpus).",
    inputSchema: {
      type: "object" as const,
      properties: {
        content: { type: "string", description: "Memory content" },
        tier: { type: "string", description: "Tier: working, episodic, long_term, corpus" },
        key: { type: "string", description: "Unique key for this memory" },
        tags: { type: "array", items: { type: "string" }, description: "Tags" },
        thread_id: { type: "string", description: "Thread identifier" },
        source_ids: { type: "array", items: { type: "string" }, description: "Evidence source IDs" },
      },
      required: ["content", "tier"],
    },
  },
  {
    name: "memory_retrieve_tier",
    description: "Retrieve memories from a specific tier or all tiers.",
    inputSchema: {
      type: "object" as const,
      properties: {
        query: { type: "string", description: "Search query" },
        tier: { type: "string", description: "Tier to search (optional)" },
        limit: { type: "integer", description: "Max results", default: 10 },
      },
      required: ["query"],
    },
  },
  {
    name: "memory_consolidate",
    description: "Consolidate episodic memories into long-term storage.",
    inputSchema: {
      type: "object" as const,
      properties: {
        thread_id: { type: "string", description: "Thread to consolidate (optional)" },
      },
    },
  },
  {
    name: "crypto_sign",
    description: "Sign a message using HMAC-SHA256.",
    inputSchema: {
      type: "object" as const,
      properties: {
        message: { type: "string", description: "Message to sign" },
        session_id: { type: "string", description: "Session identifier" },
      },
      required: ["message", "session_id"],
    },
  },
  {
    name: "crypto_verify",
    description: "Verify an HMAC-SHA256 signature.",
    inputSchema: {
      type: "object" as const,
      properties: {
        message: { type: "string", description: "Original message" },
        signature: { type: "string", description: "Signature to verify" },
        session_id: { type: "string", description: "Session identifier" },
      },
      required: ["message", "signature", "session_id"],
    },
  },
  {
    name: "crypto_audit_trail",
    description: "Return the audit chain for a session.",
    inputSchema: {
      type: "object" as const,
      properties: {
        session_id: { type: "string", description: "Session identifier" },
      },
      required: ["session_id"],
    },
  },
  {
    name: "safeharness_check",
    description: "Run SafeHarness security layers on a tool call.",
    inputSchema: {
      type: "object" as const,
      properties: {
        tool_name: { type: "string", description: "Name of the tool to check" },
        args: { type: "object", description: "Tool arguments" },
      },
      required: ["tool_name"],
    },
  },
  {
    name: "safeharness_sanitize",
    description: "SafeHarness Layer 1: sanitize input for a tool call.",
    inputSchema: {
      type: "object" as const,
      properties: {
        tool_name: { type: "string", description: "Tool name" },
        input: { type: "object", description: "Input to sanitize" },
      },
      required: ["tool_name", "input"],
    },
  },
]

// ---------------------------------------------------------------------------
// Server setup
// ---------------------------------------------------------------------------

const SERVER_NAME = "citeagent"
const SERVER_VERSION = "0.4.0"

const server = new Server({ name: SERVER_NAME, version: SERVER_VERSION }, {
  capabilities: { tools: {} },
})

let engine: CiteAgentEngine | null = null

function getEngine(): CiteAgentEngine {
  if (!engine) {
    const projectDir = process.cwd()
    engine = new CiteAgentEngine(projectDir)
  }
  return engine
}

// ---------------------------------------------------------------------------
// list_tools handler
// ---------------------------------------------------------------------------

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: TOOL_DEFINITIONS.map((d) => ({
      name: d.name,
      description: d.description,
      inputSchema: d.inputSchema,
    })),
  }
})

// ---------------------------------------------------------------------------
// call_tool handler
// ---------------------------------------------------------------------------

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params
  const eng = getEngine()

  // Ensure engine is initialized
  await eng.ensureReady()

  const result = await eng.callTool(name, args || {})
  return {
    content: [{ type: "text", text: result }],
  }
})

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const transport = new StdioServerTransport()
  await server.connect(transport)
  console.error(`[CiteAgent MCP Server] Running on stdio (v${SERVER_VERSION}, TS-native, no Python required)`)
}

main().catch((err) => {
  console.error("[CiteAgent MCP Server] Fatal error:", err)
  process.exit(1)
})