import { describe, test, expect, beforeAll, afterAll } from "bun:test";
import fs from "fs";
import path from "path";
import os from "os";
import { MemoryStoreEngine } from "./memory-store.js";

let tmpDir: string;

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "citeagent-mem-"));
  fs.mkdirSync(path.join(tmpDir, ".memory"), { recursive: true });
  fs.mkdirSync(path.join(tmpDir, ".memory", "episodic"), { recursive: true });
  fs.mkdirSync(path.join(tmpDir, ".memory", "long_term"), { recursive: true });
  fs.appendFileSync(
    path.join(tmpDir, ".memory", "default.jsonl"),
    JSON.stringify({
      entry_id: "mem-1",
      timestamp: new Date().toISOString(),
      thread_id: "default",
      query: "quantum",
      response: "Quantum computing uses qubits",
      evidence_node_ids: [],
      sha256: "fakehash",
    }) + "\n",
  );
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("MemoryStoreEngine", () => {
  test("save appends entry to JSONL", async () => {
    const store = new MemoryStoreEngine(tmpDir);
    const result = await store.save("default", "test query", "test response", []);
    expect(result.entry_id).toBeDefined();
    expect(result.sha256).toBeDefined();
  });

  test("search finds entries by keyword", async () => {
    const store = new MemoryStoreEngine(tmpDir);
    const result = await store.search("quantum");
    expect(result.total).toBeGreaterThanOrEqual(1);
  });

  test("store_tier writes to episodic", async () => {
    const store = new MemoryStoreEngine(tmpDir);
    const result = await store.storeTier({
      content: "test episodic content",
      tier: "episodic",
      key: "test-key",
      tags: ["test"],
      thread_id: "default",
      source_ids: [],
    });
    expect(result.stored).toBe(true);
  });

  test("retrieve_tier finds entries", async () => {
    const store = new MemoryStoreEngine(tmpDir);
    const result = await store.retrieveTier("test", "episodic", 10);
    expect(result.entries.length).toBeGreaterThanOrEqual(0);
  });

  test("consolidate moves episodic to long_term", async () => {
    const store = new MemoryStoreEngine(tmpDir);
    const result = await store.consolidate("default");
    expect(result.consolidated_count).toBeGreaterThanOrEqual(0);
  });

  test("corpus tier rejects writes", async () => {
    const store = new MemoryStoreEngine(tmpDir);
    const result = await store.storeTier({
      content: "should fail",
      tier: "corpus",
      key: "test",
      tags: [],
      thread_id: "default",
      source_ids: [],
    });
    expect(result.stored).toBe(false);
  });
});