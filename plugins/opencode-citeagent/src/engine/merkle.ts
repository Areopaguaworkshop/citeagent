import crypto from "crypto";
import type { MerkleVerifyResult } from "./types.js";

export class MerkleEngine {
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
    let current = nodeHash;

    for (const sibling of proof) {
      current = await this.hashPair(current, sibling);
    }

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
    let current = nodeHash;
    for (const sibling of proof) {
      current = crypto
        .createHash("sha256")
        .update(current + sibling, "utf-8")
        .digest("hex");
    }

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
      valid: basicValid,
      computed_hash: current,
      expected_hash: root,
      verified_sources: verifiedSources,
      registry_verified: registryVerified,
    };
  }
}