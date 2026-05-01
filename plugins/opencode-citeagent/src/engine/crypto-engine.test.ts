import { describe, test, expect, beforeAll, afterAll } from "bun:test";
import fs from "fs";
import path from "path";
import os from "os";
import { CryptoEngine } from "./crypto-engine.js";

let tmpDir: string;

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "citeagent-crypto-"));
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("CryptoEngine", () => {
  test("sign returns signature", async () => {
    const engine = new CryptoEngine(tmpDir);
    const result = await engine.sign("hello", "session-1");
    expect(result.signature).toMatch(/^[a-f0-9]{64}$/);
    expect(result.session_id).toBe("session-1");
  });

  test("verify validates correct signature", async () => {
    const engine = new CryptoEngine(tmpDir);
    const { signature } = await engine.sign("hello", "session-2");
    const result = await engine.verify("hello", signature, "session-2");
    expect(result.valid).toBe(true);
  });

  test("verify rejects wrong message", async () => {
    const engine = new CryptoEngine(tmpDir);
    const { signature } = await engine.sign("hello", "session-3");
    const result = await engine.verify("wrong", signature, "session-3");
    expect(result.valid).toBe(false);
  });

  test("getAuditTrail returns entries", async () => {
    const engine = new CryptoEngine(tmpDir);
    await engine.sign("hello", "session-4");
    const trail = await engine.getAuditTrail("session-4");
    expect(trail.entries.length).toBeGreaterThanOrEqual(1);
  });
});