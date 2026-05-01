import { describe, test, expect, beforeAll, afterAll } from "bun:test";
import fs from "fs";
import path from "path";
import os from "os";
import { AuditStoreEngine } from "./audit-store.js";

let tmpDir: string;

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "citeagent-audit-"));
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("AuditStoreEngine", () => {
  test("save writes audit record", async () => {
    const store = new AuditStoreEngine(tmpDir);
    const result = await store.save("audit-1", "pass", "looks good", ["hash1"], "test query");
    expect(result.audit_id).toBe("audit-1");
    expect(result.status).toBe("saved");
  });

  test("retrieve reads audit record", async () => {
    const store = new AuditStoreEngine(tmpDir);
    await store.save("audit-2", "fail", "bad data", [], "query");
    const result = await store.retrieve("audit-2");
    if ("error" in result) throw new Error("Should not have error");
    expect(result.audit_id).toBe("audit-2");
    expect(result.verdict).toBe("fail");
  });

  test("retrieve returns error for missing audit", async () => {
    const store = new AuditStoreEngine(tmpDir);
    const result = await store.retrieve("nonexistent");
    expect(result).toHaveProperty("error");
  });
});