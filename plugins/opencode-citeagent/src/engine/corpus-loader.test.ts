import { describe, test, expect, beforeAll, afterAll } from "bun:test";
import fs from "fs";
import path from "path";
import os from "os";
import { CorpusLoader } from "./corpus-loader.js";

let tmpDir: string;

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "citeagent-test-"));
  const docDir = path.join(tmpDir, "test-doc");
  fs.mkdirSync(docDir, { recursive: true });

  fs.writeFileSync(
    path.join(docDir, "csl.json"),
    JSON.stringify({
      id: "test2024",
      type: "article",
      title: "Test Document",
      author: [{ family: "Smith", given: "John" }],
      issued: { "date-parts": [[2024]] },
      merkle_root: "abc123",
      source_type: "pdf",
    }),
  );

  fs.writeFileSync(
    path.join(docDir, "document.json"),
    JSON.stringify({
      metadata: { title: "Test Document" },
      nodes: [
        {
          node_id: "test2024:p1:1:abcd",
          source_id: "test2024",
          text: "This is a test paragraph about quantum computing.",
          sha256: "sha256_aaaa",
          page: 1,
          paragraph: 1,
          section_path: "/Introduction",
        },
        {
          node_id: "test2024:p2:2:efgh",
          source_id: "test2024",
          text: "Another paragraph about machine learning.",
          sha256: "sha256_bbbb",
          page: 2,
          paragraph: 2,
          section_path: "/Methods",
        },
      ],
    }),
  );

  fs.writeFileSync(
    path.join(docDir, "merkle.json"),
    JSON.stringify({
      algorithm: "sha256",
      leaf_count: 2,
      levels: [["sha256_aaaa", "sha256_bbbb"], ["abc123"]],
      root: "abc123",
    }),
  );
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("CorpusLoader", () => {
  test("loads corpus from directory", async () => {
    const loader = new CorpusLoader(tmpDir);
    const state = await loader.load();

    expect(state.cslRegistry.size).toBe(1);
    expect(state.cslRegistry.get("test2024")?.title).toBe("Test Document");
    expect(state.nodes.length).toBe(2);
    expect(state.nodes[0].text).toContain("quantum computing");
    expect(state.merkleRegistry.size).toBe(1);
    expect(state.merkleRegistry.get("test2024")?.root).toBe("abc123");
    expect(state.sourceIds.has("test2024")).toBe(true);
  });

  test("returns empty state for nonexistent directory", async () => {
    const loader = new CorpusLoader("/nonexistent/path");
    const state = await loader.load();
    expect(state.cslRegistry.size).toBe(0);
    expect(state.nodes.length).toBe(0);
  });

  test("reload refreshes state", async () => {
    const loader = new CorpusLoader(tmpDir);
    const state1 = await loader.load();
    const state2 = await loader.reload();
    expect(state2.loadedAt).toBeGreaterThanOrEqual(state1.loadedAt);
  });
});