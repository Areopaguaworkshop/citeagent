import type { RiskTier, ToolPermission, SecurityCheckResult, StateCheckpoint, ProvenanceTag } from "./types.js";

// ---------------------------------------------------------------------------
// Default tool permissions
// ---------------------------------------------------------------------------

const DEFAULT_TOOL_PERMISSIONS: ToolPermission[] = [
  // read tier (auto-approve) — both engine names and cite_ prefixed names
  { tool_name: "search_documents", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_search", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "search_claims", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_search_claims", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "search_memory", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_search_memory", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "tree_load", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_tree", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "tree_traverse", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_tree_traverse", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "csl_render", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_render", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "node_lookup", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_node_lookup", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "merkle_verify", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_verify", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "ag_query_claims", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_argument_query", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "ag_query_contradictions", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "audit_retrieve", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_audit_retrieve", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "memory_retrieve_tier", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_memory_retrieve_tier", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "crypto_audit_trail", risk_tier: "read", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_crypto_audit_trail", risk_tier: "read", requires_approval: false, sandbox_required: false },

  // workspace tier (auto-approve)
  { tool_name: "index_claim", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_index_claim", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "memory_save", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_memory_save", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "memory_store_tier", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_memory_store_tier", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "memory_consolidate", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_memory_consolidate", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "memory_summarize", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "merkle_compute", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_merkle_compute", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "audit_save", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_audit_save", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "crypto_sign", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_crypto_sign", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "crypto_verify", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_crypto_verify", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "safeharness_check", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_safeharness_check", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "safeharness_sanitize", risk_tier: "workspace", requires_approval: false, sandbox_required: false },
  { tool_name: "cite_safeharness_sanitize", risk_tier: "workspace", requires_approval: false, sandbox_required: false },

  // network tier (needs approval)
  { tool_name: "bibliographic_verify", risk_tier: "network", requires_approval: true, sandbox_required: false },
  { tool_name: "cite_bibliographic_verify", risk_tier: "network", requires_approval: true, sandbox_required: false },
  { tool_name: "index_document", risk_tier: "network", requires_approval: true, sandbox_required: false },
  { tool_name: "cite_ingest", risk_tier: "network", requires_approval: true, sandbox_required: false },
  { tool_name: "tantivy_search", risk_tier: "network", requires_approval: true, sandbox_required: false },
  { tool_name: "cite_tantivy_search", risk_tier: "network", requires_approval: true, sandbox_required: false },

  // system tier (always needs approval)
  { tool_name: "delete_document", risk_tier: "system", requires_approval: true, sandbox_required: true },
  { tool_name: "cite_delete_document", risk_tier: "system", requires_approval: true, sandbox_required: true },
  { tool_name: "ag_write_edge", risk_tier: "system", requires_approval: true, sandbox_required: true },
  { tool_name: "tantivy_index", risk_tier: "system", requires_approval: true, sandbox_required: true },
  { tool_name: "cite_tantivy_index", risk_tier: "system", requires_approval: true, sandbox_required: true },
  { tool_name: "regex_search", risk_tier: "system", requires_approval: true, sandbox_required: true },
  { tool_name: "cite_regex_search", risk_tier: "system", requires_approval: true, sandbox_required: true },
];

// ---------------------------------------------------------------------------
// Prompt injection patterns (Layer 1: Inform)
// ---------------------------------------------------------------------------

const INJECTION_PATTERNS: RegExp[] = [
  /ignore\s+(all\s+)?previous\s+instructions?/gi,
  /system\s*:\s*/gi,
  /you\s+are\s+now\s+/gi,
  /forget\s+(all\s+)?(your\s+)?instructions?/gi,
  /pretend\s+you\s+are/gi,
  /override\s+(safety|security)/gi,
  /disregard\s+(all\s+)?(previous|above)/gi,
  /new\s+instructions?\s*:/gi,
  /\<\/?system\>/gi,
  /INJECT\s*:/gi,
];

// ---------------------------------------------------------------------------
// Risk tier ordering for privilege ceiling checks
// ---------------------------------------------------------------------------

const RISK_TIER_ORDER: Record<RiskTier, number> = {
  read: 0,
  workspace: 1,
  network: 2,
  system: 3,
};

const RISK_TIERS: RiskTier[] = ["read", "workspace", "network", "system"];

// ---------------------------------------------------------------------------
// SafeHarness
// ---------------------------------------------------------------------------

export class SafeHarness {
  private permissions: Map<string, ToolPermission> = new Map();
  private callCounts: Map<string, number> = new Map();
  private anomalyCount: number = 0;
  private privilegeCeiling: RiskTier = "system"; // starts at maximum; degrades on anomalies
  private checkpoints: Map<string, StateCheckpoint> = new Map();
  private checkpointCounter: number = 0;
  private maxInputLength: number = 10000;

  constructor(permissions?: ToolPermission[]) {
    const perms = permissions ?? DEFAULT_TOOL_PERMISSIONS;
    for (const perm of perms) {
      this.permissions.set(perm.tool_name, perm);
    }
  }

  // -----------------------------------------------------------------------
  // Layer 1: Inform — sanitize input
  // -----------------------------------------------------------------------

  /**
   * Strip prompt injection patterns from string arguments, trim values to
   * 10000 chars, and tag each with a provenance marker.
   */
  sanitizeInput(
    toolName: string,
    args: Record<string, unknown>,
  ): { sanitized: Record<string, unknown>; modifications: string[] } {
    const modifications: string[] = [];
    const sanitized: Record<string, unknown> = {};

    for (const [key, value] of Object.entries(args)) {
      if (typeof value === "string") {
        let cleaned = value;

        // Strip injection patterns
        for (const pattern of INJECTION_PATTERNS) {
          if (pattern.test(cleaned)) {
            modifications.push(`Stripped injection pattern in arg "${key}"`);
            cleaned = cleaned.replace(pattern, "[FILTERED]");
          }
          // Reset regex lastIndex since we used /g flags
          pattern.lastIndex = 0;
        }

        // Trim to max length
        if (cleaned.length > this.maxInputLength) {
          modifications.push(`Truncated arg "${key}" from ${cleaned.length} to ${this.maxInputLength} chars`);
          cleaned = cleaned.substring(0, this.maxInputLength);
        }

        // Add provenance tag
        const provenance: ProvenanceTag = {
          source_id: toolName,
          trust_level: "unverified",
          sanitized: modifications.length > 0,
          timestamp: new Date().toISOString(),
        };

        sanitized[key] = cleaned;
        (sanitized as Record<string, unknown>)[`_${key}_provenance`] = provenance;
      } else if (typeof value === "object" && value !== null && !Array.isArray(value)) {
        // Recurse into nested objects
        const nested = this.sanitizeInput(toolName, value as Record<string, unknown>);
        sanitized[key] = nested.sanitized;
        for (const mod of nested.modifications) {
          modifications.push(mod);
        }
      } else {
        sanitized[key] = value;
      }
    }

    return { sanitized, modifications };
  }

  // -----------------------------------------------------------------------
  // Layer 2: Verify — tiered verification of tool results
  // -----------------------------------------------------------------------

  /**
   * Rule-based verification of tool results.
   * - merkle_verify must have boolean `valid`
   * - csl_render must have string `output`
   * - search results must have array `results`
   *
   * Returns a SecurityCheckResult indicating whether verification passed.
   */
  tieredVerify(
    toolName: string,
    _args: Record<string, unknown>,
    result: Record<string, unknown>,
  ): SecurityCheckResult {
    // merkle_verify must return a boolean `valid` field
    if (toolName === "merkle_verify") {
      if (!("valid" in result)) {
        return {
          allowed: false,
          layer: "verify",
          reason: "merkle_verify result missing 'valid' boolean field",
        };
      }
      if (typeof result.valid !== "boolean") {
        return {
          allowed: false,
          layer: "verify",
          reason: `merkle_verify 'valid' must be boolean, got ${typeof result.valid}`,
        };
      }
    }

    // csl_render must return a string `output` field
    if (toolName === "csl_render") {
      if (!("output" in result)) {
        return {
          allowed: false,
          layer: "verify",
          reason: "csl_render result missing 'output' string field",
        };
      }
      if (typeof result.output !== "string") {
        return {
          allowed: false,
          layer: "verify",
          reason: `csl_render 'output' must be string, got ${typeof result.output}`,
        };
      }
    }

    // search tools must return array `results`
    if (
      toolName.startsWith("search_") ||
      toolName === "ag_query_claims" ||
      toolName === "ag_query_contradictions"
    ) {
      if (!("results" in result) || !Array.isArray(result.results)) {
        return {
          allowed: false,
          layer: "verify",
          reason: `${toolName} result missing 'results' array field`,
        };
      }
    }

    return {
      allowed: true,
      layer: "verify",
      reason: "Verification passed",
    };
  }

  // -----------------------------------------------------------------------
  // Layer 3: Constrain — permission and call-count checks
  // -----------------------------------------------------------------------

  /**
   * Check whether a tool is permitted to execute based on:
   * - Tool's risk tier vs current privilege ceiling
   * - Whether the tool requires approval
   * - Per-session call count limits
   */
  checkPermission(toolName: string): SecurityCheckResult {
    const perm = this.permissions.get(toolName);

    // Unknown tools: default to system tier requiring approval
    if (!perm) {
      return {
        allowed: false,
        layer: "constrain",
        reason: `Unknown tool "${toolName}" — no permission defined, defaulting to system tier`,
        risk_tier: "system",
      };
    }

    // Check privilege ceiling
    const ceilingIdx = RISK_TIER_ORDER[this.privilegeCeiling];
    const toolIdx = RISK_TIER_ORDER[perm.risk_tier];
    if (toolIdx > ceilingIdx) {
      return {
        allowed: false,
        layer: "constrain",
        reason: `Tool "${toolName}" risk tier "${perm.risk_tier}" exceeds privilege ceiling "${this.privilegeCeiling}"`,
        risk_tier: perm.risk_tier,
      };
    }

    // Check approval requirement
    if (perm.requires_approval) {
      return {
        allowed: false,
        layer: "constrain",
        reason: `Tool "${toolName}" requires approval (risk tier: ${perm.risk_tier})`,
        risk_tier: perm.risk_tier,
      };
    }

    // Check call count limit
    if (perm.max_calls_per_session !== undefined) {
      const current = this.callCounts.get(toolName) ?? 0;
      if (current >= perm.max_calls_per_session) {
        return {
          allowed: false,
          layer: "constrain",
          reason: `Tool "${toolName}" exceeded max calls per session (${perm.max_calls_per_session})`,
          risk_tier: perm.risk_tier,
        };
      }
    }

    // Increment call count
    this.callCounts.set(toolName, (this.callCounts.get(toolName) ?? 0) + 1);

    return {
      allowed: true,
      layer: "constrain",
      reason: "Permission check passed",
      risk_tier: perm.risk_tier,
    };
  }

  // -----------------------------------------------------------------------
  // Layer 4: Correct — state checkpoints and anomaly tracking
  // -----------------------------------------------------------------------

  /**
   * Create a state checkpoint before a write operation.
   * Returns a StateCheckpoint that can be used for rollback.
   */
  checkpoint(toolName: string, inputHash: string): StateCheckpoint {
    this.checkpointCounter += 1;
    const checkpointId = `ckpt-${this.checkpointCounter}-${Date.now()}`;

    const cp: StateCheckpoint = {
      checkpoint_id: checkpointId,
      timestamp: new Date().toISOString(),
      tool_name: toolName,
      input_hash: inputHash,
      rollback_available: true,
    };

    this.checkpoints.set(checkpointId, cp);
    return cp;
  }

  /**
   * Record an anomaly and potentially degrade the privilege ceiling.
   * After 3 anomalies, the ceiling drops one tier.
   */
  reportAnomaly(): void {
    this.anomalyCount += 1;

    // Degrade privilege ceiling after every 3 anomalies
    const degradations = Math.floor(this.anomalyCount / 3);
    if (degradations > 0) {
      const currentIdx = RISK_TIER_ORDER[this.privilegeCeiling];
      const newIdx = Math.max(0, currentIdx - degradations);
      const newCeiling = RISK_TIERS[newIdx];
      if (newCeiling !== this.privilegeCeiling) {
        this.privilegeCeiling = newCeiling;
        console.warn(
          `[SafeHarness] Privilege ceiling degraded to "${this.privilegeCeiling}" after ${this.anomalyCount} anomalies`,
        );
      }
    }
  }

  // -----------------------------------------------------------------------
  // Combined pre/post check
  // -----------------------------------------------------------------------

  /**
   * Run all 4 security layers before a tool call.
   * Returns the combined SecurityCheckResult from the first failing layer,
   * or the last layer checked if all pass.
   */
  preCheck(
    toolName: string,
    args: Record<string, unknown>,
  ): SecurityCheckResult {
    // Layer 3: Constrain — check permission first (cheapest check)
    const permResult = this.checkPermission(toolName);
    if (!permResult.allowed) {
      return permResult;
    }

    // Layer 1: Inform — sanitize input
    const { sanitized, modifications } = this.sanitizeInput(toolName, args);
    if (modifications.length > 0) {
      this.reportAnomaly();
    }

    return {
      allowed: true,
      layer: "inform",
      reason: modifications.length > 0
        ? `Input sanitized: ${modifications.join("; ")}`
        : "Pre-check passed",
      sanitized_input: sanitized,
      risk_tier: permResult.risk_tier,
    };
  }

  /**
   * Run Layer 2 (Verify) on tool result after execution.
   */
  postCheck(
    toolName: string,
    args: Record<string, unknown>,
    result: Record<string, unknown>,
  ): SecurityCheckResult {
    const verifyResult = this.tieredVerify(toolName, args, result);
    if (!verifyResult.allowed) {
      this.reportAnomaly();
    }
    return verifyResult;
  }

  // -----------------------------------------------------------------------
  // Accessors
  // -----------------------------------------------------------------------

  /** Return the current privilege ceiling tier. */
  getPrivilegeCeiling(): RiskTier {
    return this.privilegeCeiling;
  }

  /** Return current anomaly count. */
  getAnomalyCount(): number {
    return this.anomalyCount;
  }

  /** Return checkpoint count. */
  getCheckpointCount(): number {
    return this.checkpoints.size;
  }

  /** Get a specific checkpoint by ID. */
  getCheckpoint(checkpointId: string): StateCheckpoint | undefined {
    return this.checkpoints.get(checkpointId);
  }

  /** Get all registered tool permissions. */
  getPermissions(): ToolPermission[] {
    return Array.from(this.permissions.values());
  }

  /** Reset harness state (for testing). */
  reset(): void {
    this.callCounts.clear();
    this.anomalyCount = 0;
    this.privilegeCeiling = "system";
    this.checkpoints.clear();
    this.checkpointCounter = 0;
  }
}
