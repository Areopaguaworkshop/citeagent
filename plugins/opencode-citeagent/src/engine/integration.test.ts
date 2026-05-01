import { describe, test, expect, beforeAll, afterAll } from "bun:test";
import fs from "fs";
import path from "path";
import os from "os";
import { CiteAgentEngine } from "./index.js";

let tmpDir: string;
let engine: CiteAgentEngine;

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "citeagent-integ-"));
  const docDir = path.join(tmpDir, "integ-doc");
  fs.mkdirSync(docDir, { recursive: true });

  fs.writeFileSync(
    path.join(docDir, "csl.json"),
    JSON.stringify({
      id: "integ2024",
      type: "article-journal",
      title: "Integration Test Document",
      author: [{ family: "Doe", given: "Jane" }],
      issued: { "date-parts": [[2024]] },
      "container-title": "Test Journal",
      merkle_root: "integroot",
    }),
  );

  fs.writeFileSync(
    path.join(docDir, "document.json"),
    JSON.stringify({
      nodes: [
        { node_id: "integ2024:n1", source_id: "integ2024", text: "Quantum entanglement enables secure communication", sha256: "h1", page: 1, paragraph: 1, section_path: "/Intro" },
        { node_id: "integ2024:n2", source_id: "integ2024", text: "Machine learning models require large datasets", sha256: "h2", page: 2, paragraph: 1, section_path: "/Methods" },
      ],
    }),
  );

  fs.writeFileSync(
    path.join(docDir, "merkle.json"),
    JSON.stringify({ algorithm: "sha256", leaf_count: 2, levels: [["h1", "h2"], ["integroot"]], root: "integroot" }),
  );

  process.env.CITEAGENT_CORPUS_ROOT = tmpDir;
  engine = new CiteAgentEngine(tmpDir);
});

afterAll(() => {
  delete process.env.CITEAGENT_CORPUS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("CiteAgentEngine integration", () => {
  test("engine initializes without Python", async () => {
    await engine.ensureReady();
  });

  test("search_documents returns results", async () => {
    const result = JSON.parse(await engine.callTool("search_documents", { query: "quantum", limit: 5 }));
    expect(result.total).toBeGreaterThanOrEqual(1);
  });

  test("csl_render returns formatted citation", async () => {
    const result = JSON.parse(await engine.callTool("csl_render", { citation_key: "integ2024", style: "apa" }));
    expect(result).toHaveProperty("output");
    expect(result.output).toContain("Doe");
  });

  test("merkle_compute returns hash", async () => {
    const result = JSON.parse(await engine.callTool("merkle_compute", { payload: "test" }));
    expect(result.hash).toMatch(/^[a-f0-9]{64}$/);
  });

  test("memory save and search cycle", async () => {
    await engine.callTool("memory_save", { content: "integration test memory", thread: "test", tags: ["test"] });
    const result = JSON.parse(await engine.callTool("search_memory", { query: "integration" }));
    expect(result.total).toBeGreaterThanOrEqual(1);
  });

  test("regex_search finds patterns", async () => {
    const result = JSON.parse(await engine.callTool("regex_search", { pattern: "quantum.*communication" }));
    expect(result.total).toBeGreaterThanOrEqual(1);
  });

  test("audit save and retrieve", async () => {
    await engine.callTool("audit_save", { audit_id: "integ-audit-1", verdict: "pass", reasoning: "test" });
    const result = JSON.parse(await engine.callTool("audit_retrieve", { audit_id: "integ-audit-1" }));
    expect(result.audit_id).toBe("integ-audit-1");
  });

  test("crypto sign and verify cycle", async () => {
    const signResult = JSON.parse(await engine.callTool("crypto_sign", { message: "hello", session_id: "integ-session" }));
    const verifyResult = JSON.parse(await engine.callTool("crypto_verify", { message: "hello", signature: signResult.signature, session_id: "integ-session" }));
    expect(verifyResult.valid).toBe(true);
  });

  test("unknown tool returns error", async () => {
    const result = JSON.parse(await engine.callTool("nonexistent_tool", {}));
    expect(result).toHaveProperty("error");
  });
});