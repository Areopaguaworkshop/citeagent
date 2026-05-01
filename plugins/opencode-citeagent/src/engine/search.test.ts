import { describe, test, expect, beforeAll, afterAll } from "bun:test";
import fs from "fs";
import path from "path";
import os from "os";
import { SearchEngine } from "./search.js";

let tmpDir: string;

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "citeagent-search-"));
  const docDir = path.join(tmpDir, "search-doc");
  fs.mkdirSync(docDir, { recursive: true });
  fs.writeFileSync(
    path.join(docDir, "csl.json"),
    JSON.stringify({ id: "search2024", type: "article", title: "Search Test", merkle_root: "toproot" }),
  );
  fs.writeFileSync(
    path.join(docDir, "document.json"),
    JSON.stringify({
      nodes: [
        { node_id: "s1", source_id: "search2024", text: "Quantum entanglement in superconducting circuits", sha256: "h1", page: 1, paragraph: 1, section_path: "/Intro" },
        { node_id: "s2", source_id: "search2024", text: "Machine learning for protein folding prediction", sha256: "h2", page: 2, paragraph: 1, section_path: "/Methods" },
        { node_id: "s3", source_id: "search2024", text: "Classical quantum algorithms and their applications", sha256: "h3", page: 3, paragraph: 1, section_path: "/Discussion" },
      ],
    }),
  );
  fs.writeFileSync(
    path.join(docDir, "merkle.json"),
    JSON.stringify({ algorithm: "sha256", leaf_count: 3, levels: [["h1","h2","h3"],["root1","root2"],["toproot"]], root: "toproot" }),
  );
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("SearchEngine", () => {
  test("finds documents by keyword", async () => {
    const engine = new SearchEngine(tmpDir);
    await engine.init();
    const results = engine.search("quantum", 10);
    expect(results.total).toBeGreaterThanOrEqual(2);
  });

  test("returns empty for no matches", async () => {
    const engine = new SearchEngine(tmpDir);
    await engine.init();
    const results = engine.search("xyzzynonexistent", 10);
    expect(results.total).toBe(0);
  });

  test("respects limit", async () => {
    const engine = new SearchEngine(tmpDir);
    await engine.init();
    const results = engine.search("quantum", 1);
    expect(results.results.length).toBeLessThanOrEqual(1);
  });

  test("regex search finds pattern matches", async () => {
    const engine = new SearchEngine(tmpDir);
    await engine.init();
    const results = engine.regexSearch("quantum.*circuits", undefined, 10, 120);
    expect(results.total).toBeGreaterThanOrEqual(1);
  });

  test("regex search returns empty for invalid regex", async () => {
    const engine = new SearchEngine(tmpDir);
    await engine.init();
    const results = engine.regexSearch("[invalid", undefined, 10);
    expect(results.total).toBe(0);
    expect(results.note).toContain("Invalid regex");
  });
});