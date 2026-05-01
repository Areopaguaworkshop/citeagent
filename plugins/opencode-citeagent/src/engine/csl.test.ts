import { describe, test, expect } from "bun:test";
import { CslEngine } from "./csl.js";
import type { CslRecord } from "./types.js";

describe("CslEngine", () => {
  const records = new Map<string, CslRecord>();
  records.set("smith2024", {
    id: "smith2024",
    type: "article-journal",
    title: "Quantum Entanglement in Practice",
    author: [{ family: "Smith", given: "John" }],
    issued: { "date-parts": [[2024]] },
    "container-title": "Journal of Physics",
  });

  test("renders citation for known key", async () => {
    const engine = new CslEngine(records);
    const result = await engine.render("smith2024", "apa");
    expect(result.citation_key).toBe("smith2024");
    expect(result.output.length).toBeGreaterThan(0);
  });

  test("returns note for unknown key", async () => {
    const engine = new CslEngine(records);
    const result = await engine.render("nonexistent", "apa");
    expect(result.note).toContain("not found");
  });

  test("renders APA style", async () => {
    const engine = new CslEngine(records);
    const result = await engine.render("smith2024", "apa");
    expect(result.output).toContain("Smith");
    expect(result.output).toContain("2024");
    expect(result.in_text).toBe("(Smith, 2024)");
  });

  test("renders IEEE style", async () => {
    const engine = new CslEngine(records);
    const result = await engine.render("smith2024", "ieee");
    expect(result.in_text).toBe("[smith2024]");
  });
});