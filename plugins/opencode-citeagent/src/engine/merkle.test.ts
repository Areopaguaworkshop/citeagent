import { describe, test, expect } from "bun:test";
import { MerkleEngine } from "./merkle.js";

describe("MerkleEngine", () => {
  test("compute returns hash and root for payload", async () => {
    const engine = new MerkleEngine();
    const result = await engine.compute("hello world");
    expect(result.hash).toMatch(/^[a-f0-9]{64}$/);
    expect(result.leaf_count).toBeGreaterThanOrEqual(1);
  });

  test("verify returns true for valid proof", async () => {
    const engine = new MerkleEngine();
    const computed = await engine.compute("test data");
    const result = await engine.verify(computed.hash, [], computed.merkle_root);
    expect(result.valid).toBe(true);
  });

  test("verify returns false for invalid proof", async () => {
    const engine = new MerkleEngine();
    const result = await engine.verify("badhash", ["fakesibling"], "fakeroot");
    expect(result.valid).toBe(false);
  });

  test("verify walks multi-level proof correctly", async () => {
    const engine = new MerkleEngine();
    const leftHash = await engine.hashPayload("left");
    const rightHash = await engine.hashPayload("right");
    const root = await engine.hashPair(leftHash, rightHash);
    const result = await engine.verify(leftHash, [rightHash], root);
    expect(result.valid).toBe(true);
  });

  test("verifyWithRegistry checks registry roots", () => {
    const engine = new MerkleEngine();
    const merkleRegistry = new Map<string, { root: string }>();
    merkleRegistry.set("doc1", { root: "testroot" });
    const result = engine.verifyWithRegistry("testroot", [], "testroot", merkleRegistry);
    expect(result.valid).toBe(true);
    expect(result.registry_verified).toBe(true);
    expect(result.verified_sources).toContain("doc1");
  });
});