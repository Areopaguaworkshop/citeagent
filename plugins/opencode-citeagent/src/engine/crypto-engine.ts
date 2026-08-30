import crypto from "crypto";
import fs from "fs";
import path from "path";
import { safePath } from "./safe-path.js";

export class CryptoEngine {
  private corpusRoot: string;
  private sessionKeys: Map<string, string> = new Map();

  constructor(corpusRoot: string) {
    this.corpusRoot = corpusRoot;
  }

  private getSessionKey(sessionId: string): string {
    if (!this.sessionKeys.has(sessionId)) {
      this.sessionKeys.set(sessionId, crypto.randomBytes(32).toString("hex"));
    }
    return this.sessionKeys.get(sessionId)!;
  }

  async sign(
    message: string,
    sessionId: string,
  ): Promise<{ signature: string; session_id: string }> {
    const key = this.getSessionKey(sessionId);
    const signature = crypto
      .createHmac("sha256", key)
      .update(message)
      .digest("hex");

    const dir = path.join(this.corpusRoot, ".crypto");
    fs.mkdirSync(dir, { recursive: true });
    const trailPath = safePath(dir, `${sessionId}_trail.jsonl`);
    fs.appendFileSync(
      trailPath,
      JSON.stringify({
        action: "sign",
        message_hash: crypto.createHash("sha256").update(message).digest("hex"),
        signature,
        timestamp: new Date().toISOString(),
      }) + "\n",
    );

    return { signature, session_id: sessionId };
  }

  async verify(
    message: string,
    signature: string,
    sessionId: string,
  ): Promise<{ valid: boolean; session_id: string }> {
    const key = this.getSessionKey(sessionId);
    const expected = crypto
      .createHmac("sha256", key)
      .update(message)
      .digest("hex");
    return { valid: expected === signature, session_id: sessionId };
  }

  async getAuditTrail(
    sessionId: string,
  ): Promise<{ entries: Record<string, unknown>[]; session_id: string }> {
    const trailPath = safePath(
      path.join(this.corpusRoot, ".crypto"),
      `${sessionId}_trail.jsonl`,
    );
    if (!fs.existsSync(trailPath)) {
      return { entries: [], session_id: sessionId };
    }

    const lines = fs
      .readFileSync(trailPath, "utf-8")
      .split("\n")
      .filter(Boolean);
    const entries: Record<string, unknown>[] = [];
    for (const line of lines) {
      try {
        entries.push(JSON.parse(line));
      } catch {}
    }

    return { entries, session_id: sessionId };
  }
}
