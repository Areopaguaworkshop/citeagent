import crypto from "crypto";
import type { MerkleVerifyResult } from "./types.js";

export class MerkleEngine {
  private walkProof(nodeHash: string, proof: string[]): string {
    let current = nodeHash;
    for (const step of proof) {
      const left = step.startsWith("left:");
      const sibling = step.replace(/^(left|right):/, "");
      current = crypto
        .createHash("sha256")
        .update(left ? sibling + current : current + sibling, "utf-8")
        .digest("hex");
    }
    return current;
  }

  async hashPayload(data: string): Promise<string> {
    return crypto.createHash("sha256").update(data, "utf-8").digest("hex");
  }

  async hashPair(left: string, right: string): Promise<string> {
    const combined = left + right;
    return crypto.createHash("sha256").update(combined, "utf-8").digest("hex");
  }

  async compute(payload: string): Promise<{ hash: string; merkle_root: string; leaf_count: number }> {
    const hash = await this.hashPayload(payload);
    return {
      hash,
      merkle_root: hash,
      leaf_count: 1,
    };
  }

  async verify(
    nodeHash: string,
    proof: string[],
    root: string,
  ): Promise<MerkleVerifyResult> {
    const current = this.walkProof(nodeHash, proof);

    const valid = current === root;
    return {
      valid,
      computed_hash: current,
      expected_hash: root,
    };
  }

  verifyWithRegistry(
    nodeHash: string,
    proof: string[],
    root: string,
    merkleRegistry: Map<string, { root: string }>,
  ): MerkleVerifyResult {
    const current = this.walkProof(nodeHash, proof);

    const basicValid = current === root;

    const verifiedSources: string[] = [];
    let registryVerified = false;
    for (const [sourceId, merkle] of merkleRegistry) {
      if (merkle.root === root) {
        verifiedSources.push(sourceId);
        registryVerified = true;
      }
    }

    return {
      valid: basicValid && registryVerified,
      computed_hash: current,
      expected_hash: root,
      verified_sources: verifiedSources,
      registry_verified: registryVerified,
    };
  }
}
