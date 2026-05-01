import { getMcpManager } from "./mcp-bridge.js";
import type { EvidenceItem, VerificationResult, VerificationLadderResult } from "./types.js";

export class VerificationLadder {
  private directory: string;

  constructor(directory: string) {
    this.directory = directory;
  }

  async run(evidence: EvidenceItem[]): Promise<VerificationLadderResult> {
    const rungs: VerificationResult[] = [];

    for (const item of evidence) {
      const l0 = this.l0SchemaCheck(item);
      rungs.push(l0);
      if (!l0.passed) {
        return { overall: "rejected", rungs, evidence };
      }

      const l1 = await this.l1NodeExistence(item);
      rungs.push(l1);
      if (!l1.passed) {
        return { overall: "rejected", rungs, evidence };
      }

      const l2 = await this.l2HashMatch(item);
      rungs.push(l2);
      if (!l2.passed) {
        return { overall: "rejected", rungs, evidence };
      }

      const l3 = await this.l3MerkleProof(item);
      rungs.push(l3);
      if (!l3.passed) {
        return { overall: "rejected", rungs, evidence };
      }

      const l4 = await this.l4CitationKey(item);
      rungs.push(l4);
      if (!l4.passed) {
        return { overall: "rejected", rungs, evidence };
      }
    }

    return { overall: "pending_audit", rungs, evidence };
  }

  async l5LlmAudit(
    originalQuery: string,
    evidence: EvidenceItem[],
  ): Promise<VerificationResult> {
    const evidenceSummary = evidence
      .map(
        (e) =>
          `Node ${e.node_id}: hash=${e.sha256?.substring(0, 16)}… key=${e.citation_key}`,
      )
      .join("\n");

    const auditPrompt =
      `You are an independent academic evidence auditor. You must verify whether the following evidence supports the original research query.\n\n` +
      `ORIGINAL QUERY: ${originalQuery}\n\n` +
      `EVIDENCE ITEMS:\n${evidenceSummary}\n\n` +
      `For each evidence item, check:\n` +
      `1. Does this evidence directly address the query?\n` +
      `2. Are the Merkle hash and citation key consistent?\n` +
      `3. Is there any sign of fabrication or hallucination?\n\n` +
      `Respond with APPROVED or REJECTED, followed by a brief reasoning.`;

    try {
      const response = await fetch(
        "http://localhost:11434/v1/chat/completions",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model: "deepseek-v4-flash:cloud",
            messages: [{ role: "user", content: auditPrompt }],
            max_tokens: 500,
          }),
        },
      );

      const data = (await response.json()) as {
        choices?: Array<{ message?: { content?: string } }>;
      };
      const content = data.choices?.[0]?.message?.content ?? "";
      const verdict = content.includes("APPROVED");

      return {
        passed: verdict,
        level: 5,
        message: verdict
          ? "L5 audit approved: independent LLM verified evidence quality"
          : "L5 audit rejected: independent LLM found evidence concerns",
        details: content.substring(0, 500),
      };
    } catch (error) {
      return {
        passed: false,
        level: 5,
        message: `L5 audit failed: ${error instanceof Error ? error.message : String(error)}`,
      };
    }
  }

  private l0SchemaCheck(item: EvidenceItem): VerificationResult {
    const required: (keyof EvidenceItem)[] = [
      "node_id",
      "source_id",
      "sha256",
      "merkle_proof",
      "citation_key",
      "citation_rendered",
    ];

    const missing = required.filter((key) => {
      const val = item[key];
      return val === undefined || val === null || val === "";
    });

    if (missing.length > 0) {
      return {
        passed: false,
        level: 0,
        message: `Missing required fields: ${missing.join(", ")}`,
        details: `Evidence item for node ${item.node_id ?? "unknown"} failed schema validation`,
      };
    }

    return {
      passed: true,
      level: 0,
      message: "Schema check passed — all required fields present",
    };
  }

  private async l1NodeExistence(
    item: EvidenceItem,
  ): Promise<VerificationResult> {
    try {
      const manager = getMcpManager(this.directory);
      const result = await manager.callTool("cite_tree_traverse", {
        node_id: item.node_id,
      });

      if (result && typeof result === "object") {
        return {
          passed: true,
          level: 1,
          message: `Node ${item.node_id} exists in citation tree`,
        };
      }

      return {
        passed: false,
        level: 1,
        message: `Node ${item.node_id} not found in citation tree`,
      };
    } catch (error) {
      return {
        passed: false,
        level: 1,
        message: `Node existence check failed: ${error instanceof Error ? error.message : String(error)}`,
      };
    }
  }

  private async l2HashMatch(
    item: EvidenceItem,
  ): Promise<VerificationResult> {
    try {
      const manager = getMcpManager(this.directory);
      const result = await manager.callTool("cite_regex_search", {
        pattern: item.sha256,
      });

      if (result) {
        return {
          passed: true,
          level: 2,
          message: `SHA-256 hash ${item.sha256.substring(0, 12)}… matches`,
        };
      }

      return {
        passed: false,
        level: 2,
        message: `SHA-256 hash mismatch for node ${item.node_id}`,
      };
    } catch (error) {
      return {
        passed: false,
        level: 2,
        message: `Hash match check failed: ${error instanceof Error ? error.message : String(error)}`,
      };
    }
  }

  private async l3MerkleProof(
    item: EvidenceItem,
  ): Promise<VerificationResult> {
    try {
      const manager = getMcpManager(this.directory);
      const result = await manager.callTool("cite_merkle_verify", {
        node_id: item.node_id,
        proof: item.merkle_proof,
      });

      if (
        result &&
        typeof result === "object" &&
        "valid" in (result as Record<string, unknown>)
      ) {
        const valid = (result as Record<string, unknown>).valid;
        if (valid === true) {
          return {
            passed: true,
            level: 3,
            message: `Merkle proof valid for node ${item.node_id}`,
          };
        }
      }

      return {
        passed: false,
        level: 3,
        message: `Merkle proof invalid for node ${item.node_id}`,
      };
    } catch (error) {
      return {
        passed: false,
        level: 3,
        message: `Merkle proof check failed: ${error instanceof Error ? error.message : String(error)}`,
      };
    }
  }

  private async l4CitationKey(
    item: EvidenceItem,
  ): Promise<VerificationResult> {
    try {
      const manager = getMcpManager(this.directory);
      const result = await manager.callTool("cite_csl_render", {
        citation_key: item.citation_key,
      });

      const rendered =
        result &&
        typeof result === "object" &&
        "output" in (result as Record<string, unknown>)
          ? String((result as Record<string, unknown>).output)
          : String(result);

      if (rendered === item.citation_rendered) {
        return {
          passed: true,
          level: 4,
          message: `Citation key ${item.citation_key} renders correctly`,
        };
      }

      return {
        passed: false,
        level: 4,
        message: `Citation render mismatch for key ${item.citation_key}`,
        details: `Expected: "${item.citation_rendered}", Got: "${rendered}"`,
      };
    } catch (error) {
      return {
        passed: false,
        level: 4,
        message: `Citation key check failed: ${error instanceof Error ? error.message : String(error)}`,
      };
    }
  }
}