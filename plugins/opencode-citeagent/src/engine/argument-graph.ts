import fs from "fs";
import path from "path";
import crypto from "crypto";
import { safePath } from "./safe-path.js";
import type { CorpusState } from "./types.js";

export class ArgumentGraphEngine {
  private corpusRoot: string;
  private corpusState: CorpusState;

  constructor(corpusRoot: string, corpusState: CorpusState) {
    this.corpusRoot = corpusRoot;
    this.corpusState = corpusState;
  }

  async queryClaims(
    args: Record<string, unknown>,
  ): Promise<{ claims: Record<string, unknown>[]; total: number }> {
    const claimId = args.claim_id as string | undefined;
    const sourceId = args.source_id as string | undefined;
    const limit = Number(args.limit || 10);

    const claimsPath = sourceId
      ? safePath(
          safePath(this.corpusRoot, sourceId),
          `${sourceId}_claims.jsonl`,
        )
      : null;

    const claims: Record<string, unknown>[] = [];

    if (claimsPath && fs.existsSync(claimsPath)) {
      const lines = fs
        .readFileSync(claimsPath, "utf-8")
        .split("\n")
        .filter(Boolean);
      for (const line of lines) {
        try {
          const entry = JSON.parse(line);
          if (claimId && entry.claim_id !== claimId) continue;
          claims.push(entry);
          if (claims.length >= limit) break;
        } catch {}
      }
    }

    return { claims, total: claims.length };
  }

  async queryContradictions(
    args: Record<string, unknown>,
  ): Promise<{ contradictions: Record<string, unknown>[]; note: string }> {
    return {
      contradictions: [],
      note: "Contradiction detection is a stub — requires LLM-based analysis",
    };
  }

  async indexClaim(
    args: Record<string, unknown>,
  ): Promise<{ claim_id: string; status: string }> {
    const claimText = String(args.claim_text || "");
    const sourceId = String(args.source_id || "default");
    const metadata = args.metadata as Record<string, unknown> | undefined;

    const claimId = `claim-${crypto.randomBytes(4).toString("hex")}`;
    const entry = {
      claim_id: claimId,
      claim_text: claimText,
      source_id: sourceId,
      polarity_tag: (metadata as any)?.polarity_tag || null,
      entities: (metadata as any)?.entities || [],
      timestamp: new Date().toISOString(),
    };

    const docDir = safePath(this.corpusRoot, sourceId);
    fs.mkdirSync(docDir, { recursive: true });
    const claimsPath = safePath(docDir, `${sourceId}_claims.jsonl`);
    fs.appendFileSync(claimsPath, JSON.stringify(entry) + "\n");

    return { claim_id: claimId, status: "indexed" };
  }
}
