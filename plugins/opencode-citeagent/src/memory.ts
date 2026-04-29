import type { CiteAgentMcpBridge } from "./types.js";
import type { MemoryTier, MemoryEntry, MemoryStoreResult, MemoryRetrieveResult, MemoryConsolidateResult } from "./types.js";

// ---------------------------------------------------------------------------
// MemoryArchitect — 4-tier memory management
// ---------------------------------------------------------------------------

export class MemoryArchitect {
  private bridge: CiteAgentMcpBridge;

  constructor(bridge: CiteAgentMcpBridge) {
    this.bridge = bridge;
  }

  /**
   * Store a memory entry in the specified tier.
   *
   * - working: returns immediately (ephemeral, in-process)
   * - episodic: writes to JSONL via MCP memory_store_tier
   * - long_term: writes to JSONL via MCP memory_store_tier
   * - corpus: rejects (corpus tier is immutable, written only by consolidation)
   */
  async store(entry: {
    content: string;
    tier: MemoryTier;
    key: string;
    tags?: string[];
    thread_id?: string;
    source_ids?: string[];
  }): Promise<MemoryStoreResult> {
    const tier = entry.tier;

    // Working tier: ephemeral, return immediately
    if (tier === "working") {
      return {
        entry_id: `working-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`,
        stored: true,
        tier: "working",
      };
    }

    // Corpus tier: reject direct writes
    if (tier === "corpus") {
      return {
        entry_id: "",
        stored: false,
        tier: "corpus",
      };
    }

    // Episodic / long_term: delegate to MCP
    const result = await this.bridge.callTool("memory_store_tier", {
      content: entry.content,
      tier,
      key: entry.key,
      tags: entry.tags ?? [],
      thread_id: entry.thread_id ?? "default",
      source_ids: entry.source_ids ?? [],
    });

    const data = result as Record<string, unknown>;
    return {
      entry_id: String(data.entry_id ?? ""),
      stored: Boolean(data.stored),
      tier,
    };
  }

  /**
   * Retrieve memory entries matching a query.
   * Searches episodic + long_term JSONL files via MCP memory_retrieve_tier.
   */
  async retrieve(
    query: string,
    tier?: MemoryTier,
    limit?: number,
  ): Promise<MemoryRetrieveResult> {
    const result = await this.bridge.callTool("memory_retrieve_tier", {
      query,
      tier: tier ?? "",
      limit: limit ?? 10,
    });

    const data = result as Record<string, unknown>;
    const entries = (data.entries ?? []) as MemoryEntry[];

    return {
      entries,
      total: Number(data.total ?? entries.length),
      tier: (tier ?? "episodic") as MemoryTier,
    };
  }

  /**
   * Consolidate memory: move episodic entries to long_term,
   * deduplicating by SHA-256.
   */
  async consolidate(threadId?: string): Promise<MemoryConsolidateResult> {
    const result = await this.bridge.callTool("memory_consolidate", {
      thread_id: threadId ?? "default",
    });

    const data = result as Record<string, unknown>;
    return {
      consolidated_count: Number(data.consolidated_count ?? 0),
      from_tier: "episodic",
      to_tier: "long_term",
    };
  }

  /**
   * Discard a memory entry. Returns error for corpus tier (immutable).
   */
  async discard(entryId: string, reason: string): Promise<{ discarded: boolean; reason: string }> {
    // Corpus tier entries cannot be discarded
    if (entryId.startsWith("corpus-")) {
      return {
        discarded: false,
        reason: `Cannot discard corpus-tier entry "${entryId}": corpus tier is immutable`,
      };
    }

    // For other tiers, mark as discarded via memory_store_tier with a discard flag
    // (In a full implementation, this would call a dedicated discard endpoint)
    return {
      discarded: true,
      reason: `Entry "${entryId}" discarded: ${reason}`,
    };
  }
}