import fs from "fs";
import path from "path";
import { safePath } from "./safe-path.js";
import type { AuditRecord } from "./types.js";

export class AuditStoreEngine {
  private corpusRoot: string;

  constructor(corpusRoot: string) {
    this.corpusRoot = corpusRoot;
  }

  async save(
    auditId: string,
    verdict: string,
    reasoning?: string,
    evidenceHashes?: string[],
    query?: string,
  ): Promise<AuditRecord & { status: string }> {
    const dir = path.join(this.corpusRoot, ".audits");
    fs.mkdirSync(dir, { recursive: true });

    const record: AuditRecord = {
      audit_id: auditId,
      verdict,
      reasoning: reasoning || "",
      evidence_hashes: evidenceHashes || [],
      query: query || "",
      saved_at: new Date().toISOString(),
    };

    const filePath = safePath(dir, `${auditId}.json`);
    fs.writeFileSync(filePath, JSON.stringify(record, null, 2));

    return { ...record, status: "saved" };
  }

  async retrieve(auditId: string): Promise<AuditRecord | { error: string }> {
    const filePath = safePath(
      path.join(this.corpusRoot, ".audits"),
      `${auditId}.json`,
    );
    if (!fs.existsSync(filePath)) {
      return { error: `Audit ${auditId} not found` };
    }

    try {
      return JSON.parse(fs.readFileSync(filePath, "utf-8")) as AuditRecord;
    } catch {
      return { error: `Failed to parse audit ${auditId}` };
    }
  }
}
