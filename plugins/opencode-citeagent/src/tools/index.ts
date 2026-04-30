import { tool } from "@opencode-ai/plugin"
import { getBridge } from "../mcp-bridge.js"

const z = tool.schema

export async function createCiteAgentTools(ctx: { directory: string }) {
  const bridge = getBridge(ctx.directory)
  await bridge.connect()

  // Helper: call Python backend and return text
  const call = (name: string, args: Record<string, unknown>) =>
    bridge.callTool(name, args)

  return {
    // ── Academic Core ──────────────────────────────────

    cite_search: tool({
      description:
        "BM25 full-text search on the academic corpus. Returns ranked document nodes with citation metadata and Merkle hashes.",
      args: {
        query: z.string().describe("Search query terms"),
        limit: z.number().default(10).describe("Maximum results to return"),
      },
      async execute({ query, limit }) {
        return call("search_documents", { query, limit })
      },
    }),

    cite_search_claims: tool({
      description:
        "Search claims in the argument graph. Returns claim nodes with contradiction and support links.",
      args: { query: z.string().describe("Claim search query") },
      async execute({ query }) {
        return call("search_claims", { query })
      },
    }),

    cite_verify: tool({
      description:
        "Verify Merkle proof for an evidence node. Checks SHA-256 hash chain from leaf to document root.",
      args: {
        node_hash: z
          .string()
          .describe("SHA-256 hash of the evidence node"),
        proof: z
          .array(z.string())
          .describe("Merkle proof sibling hashes"),
        root: z.string().describe("Document Merkle root hash"),
      },
      async execute({ node_hash, proof, root }) {
        return call("merkle_verify", { node_hash, proof, root })
      },
    }),

    cite_render: tool({
      description:
        "Render a CSL-JSON citation record to formatted bibliography string (Chicago, APA, MLA, etc.).",
      args: {
        citation_key: z.string().describe("CSL citation key"),
        style: z
          .string()
          .default("chicago-author-date")
          .describe("Citation style ID"),
      },
      async execute({ citation_key, style }) {
        return call("csl_render", { citation_key, style })
      },
    }),

    cite_ingest: tool({
      description:
        "Ingest a document (PDF, URL, media) into the academic corpus. Creates PageIndex tree, Merkle hashes, and Tantivy index entries.",
      args: {
        path: z.string().describe("File path or URL to ingest"),
        force: z
          .boolean()
          .default(false)
          .describe("Force re-ingestion if already indexed"),
      },
      async execute({ path, force }) {
        return call("index_document", { path, force })
      },
    }),

    cite_tree: tool({
      description:
        "Load PageIndex tree for a document. Returns the root node and metadata.",
      args: {
        source_id: z.string().describe("Document source ID"),
      },
      async execute({ source_id }) {
        return call("tree_load", { source_id })
      },
    }),

    cite_tree_traverse: tool({
      description:
        "Traverse PageIndex tree for a document to a given depth. Returns structured hierarchy of sections, paragraphs, and text blocks.",
      args: {
        source_id: z.string().describe("Document source ID"),
      },
      async execute({ source_id }) {
        return call("tree_traverse", { source_id })
      },
    }),

    cite_memory_save: tool({
      description:
        "Save a memory entry to the agent's persistent memory store (JSONL + Tantivy index).",
      args: {
        content: z.string().describe("Memory content to save"),
        thread: z.string().default("default").describe("Thread name"),
        tags: z
          .array(z.string())
          .default([])
          .describe("Tags for retrieval"),
      },
      async execute({ content, thread, tags }) {
        return call("memory_save", { content, thread, tags })
      },
    }),

    cite_search_memory: tool({
      description:
        "Search the agent's persistent memory store. Returns matching entries with metadata.",
      args: {
        query: z.string().describe("Search query"),
      },
      async execute({ query }) {
        return call("search_memory", { query })
      },
    }),

    cite_argument_query: tool({
      description:
        "Query the argument graph for claims, contradictions, and support edges.",
      args: {
        claim_id: z
          .string()
          .optional()
          .describe("Specific claim ID to look up"),
        find_contradictions: z
          .boolean()
          .default(false)
          .describe("Find contradictions instead of claims"),
      },
      async execute({ claim_id, find_contradictions }) {
        if (find_contradictions)
          return call("ag_query_contradictions", { claim_id })
        return call("ag_query_claims", { claim_id })
      },
    }),

    // ── Extended Academic ──────────────────────────────

    cite_regex_search: tool({
      description:
        "Regex-based search on document nodes. Returns matching text with node IDs.",
      args: {
        pattern: z.string().describe("Regex pattern to search"),
        node_id: z
          .string()
          .optional()
          .describe("Limit search to this node"),
      },
      async execute({ pattern, node_id }) {
        return call("regex_search", { pattern, node_id })
      },
    }),

    cite_index_claim: tool({
      description:
        "Index a new claim in the argument graph, linked to a source document.",
      args: {
          claim_text: z.string().describe("Text of the claim"),
          source_id: z.string().describe("Source document ID"),
        },
      async execute({ claim_text, source_id }) {
        return call("index_claim", { claim_text, source_id })
      },
    }),

    cite_delete_document: tool({
      description:
        "Delete a document and all its associated data from the corpus.",
      args: {
        source_id: z.string().describe("Document source ID to delete"),
      },
      async execute({ source_id }) {
        return call("delete_document", { source_id })
      },
    }),

    cite_merkle_compute: tool({
      description:
        "Compute Merkle tree hashes for a payload (JSON string or text). Returns root hash and proof data.",
      args: {
        payload: z.string().describe("Payload to hash (JSON string or text)"),
      },
      async execute({ payload }) {
        return call("merkle_compute", { payload })
      },
    }),

    cite_tantivy_index: tool({
      description:
        "Add a file to the Tantivy full-text search index (low-level, prefer cite_ingest for full pipeline).",
      args: {
        path: z.string().describe("File path to index"),
      },
      async execute({ path }) {
        return call("tantivy_index", { path })
      },
    }),

    cite_tantivy_search: tool({
      description:
        "Low-level Tantivy search. Prefer cite_search for most queries.",
      args: {
        query: z.string().describe("Tantivy search query"),
      },
      async execute({ query }) {
        return call("tantivy_search", { query })
      },
    }),

    // ── Audit ──────────────────────────────────────────

    cite_audit_save: tool({
      description:
        "Save an audit result to persistent storage with verdict, reasoning, and evidence hashes.",
      args: {
        audit_id: z.string().describe("Unique audit identifier"),
        verdict: z
          .string()
          .describe("Audit verdict (approved/rejected)"),
        reasoning: z
          .string()
          .optional()
          .describe("Reasoning for the verdict"),
        evidence_hashes: z
          .array(z.string())
          .optional()
          .describe("List of evidence SHA-256 hashes"),
        query: z
          .string()
          .optional()
          .describe("Original query being audited"),
      },
      async execute({ audit_id, verdict, reasoning, evidence_hashes, query }) {
        return call("audit_save", {
          audit_id,
          verdict,
          reasoning,
          evidence_hashes,
          query,
        })
      },
    }),

    cite_audit_retrieve: tool({
      description: "Retrieve a saved audit result by ID.",
      args: {
        audit_id: z.string().describe("Audit identifier to retrieve"),
      },
      async execute({ audit_id }) {
        return call("audit_retrieve", { audit_id })
      },
    }),

    // ── Memory Tiers ───────────────────────────────────

    cite_memory_store_tier: tool({
      description:
        "Store a memory entry in a specific tier (working/episodic/long_term/corpus).",
      args: {
        content: z.string().describe("Memory content"),
        tier: z
          .string()
          .describe("Tier: working, episodic, long_term, corpus"),
        key: z.string().optional().describe("Unique key for this memory"),
        tags: z
          .array(z.string())
          .optional()
          .describe("Tags for categorisation"),
        thread_id: z
          .string()
          .optional()
          .describe("Thread identifier"),
        source_ids: z
          .array(z.string())
          .optional()
          .describe("Evidence source IDs"),
      },
      async execute({ content, tier, key, tags, thread_id, source_ids }) {
        return call("memory_store_tier", {
          content,
          tier,
          key,
          tags,
          thread_id,
          source_ids,
        })
      },
    }),

    cite_memory_retrieve_tier: tool({
      description:
        "Retrieve memories from a specific tier or all tiers.",
      args: {
        query: z.string().describe("Search query"),
        tier: z.string().optional().describe("Tier to search (optional)"),
        limit: z.number().default(10).describe("Max results"),
      },
      async execute({ query, tier, limit }) {
        return call("memory_retrieve_tier", { query, tier, limit })
      },
    }),

    cite_memory_consolidate: tool({
      description:
        "Consolidate episodic memories into long-term storage.",
      args: {
        thread_id: z
          .string()
          .optional()
          .describe("Thread to consolidate"),
      },
      async execute({ thread_id }) {
        return call("memory_consolidate", { thread_id })
      },
    }),

    // ── Cryptographic ──────────────────────────────────

    cite_crypto_sign: tool({
      description:
        "Sign a message using HMAC-SHA256 (MVP — upgrade to Ed25519 for production).",
      args: {
        message: z.string().describe("Message to sign"),
        session_id: z.string().describe("Session identifier"),
      },
      async execute({ message, session_id }) {
        return call("crypto_sign", { message, session_id })
      },
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
      args: {
        session_id: z.string().describe("Session identifier"),
      },
      async execute({ session_id }) {
        return call("crypto_audit_trail", { session_id })
      },
    }),

    // ── SafeHarness ─────────────────────────────────────

    cite_safeharness_check: tool({
      description:
        "Run all 4 SafeHarness layers on a tool call and return the result.",
      args: {
        tool_name: z.string().describe("Name of the tool to check"),
        args: z
          .record(z.unknown())
          .optional()
          .describe("Tool arguments"),
      },
      async execute({ tool_name, args }) {
        return call("safeharness_check", {
          tool_name,
          args: args ?? {},
        })
      },
    }),

    cite_safeharness_sanitize: tool({
      description:
        "SafeHarness Layer 1: sanitize input for a tool call.",
      args: {
        tool_name: z.string().describe("Tool name"),
        input: z.record(z.unknown()).describe("Input to sanitize"),
      },
      async execute({ tool_name, input }) {
        return call("safeharness_sanitize", { tool_name, input })
      },
    }),


  }
}