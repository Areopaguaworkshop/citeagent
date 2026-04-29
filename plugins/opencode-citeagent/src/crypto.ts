// MVP: HMAC-SHA256 signing — upgrade to Ed25519 (PyNaCl/tweetnacl) for production
//
// This module implements the Cryptographic Binding layer for CiteAgent per
// arXiv:2603.14332.  Three guarantees:
//   G1 — Capability Integrity:        Ed25519 (MVP: HMAC-SHA256) signed tool definitions
//   G2 — Behavioral Verifiability:    Signed execution receipts
//   G3 — Interaction Auditability:    SHA-256 hash-chained audit trail on every message

import type {
  Ed25519KeyPair,
  ToolSignature,
  ExecutionReceipt,
  AuditChainEntry,
  AuditTrail,
} from "./types.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Return a hex-encoded SHA-256 digest of a UTF-8 string. */
async function sha256Hex(data: string): Promise<string> {
  const encoded = new TextEncoder().encode(data);
  const hashBuffer = await crypto.subtle.digest("SHA-256", encoded);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * HMAC-SHA256 signature (MVP substitute for Ed25519).
 *
 * Uses the Web Crypto API `crypto.subtle.sign` with HMAC-SHA256.
 * The *privateKey* is used as the HMAC key material.
 */
async function hmacSign(keyMaterial: string, message: string): Promise<string> {
  const encoder = new TextEncoder();

  // Import the key material as a raw HMAC key
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(keyMaterial),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );

  const signature = await crypto.subtle.sign(
    "HMAC",
    key,
    encoder.encode(message),
  );

  // Return base64-encoded signature
  return btoa(String.fromCharCode(...new Uint8Array(signature)));
}

/**
 * Verify an HMAC-SHA256 signature (MVP substitute for Ed25519 verify).
 *
 * Recomputes the HMAC over *message* using *publicKey* as key material
 * and compares against the provided *signature*.
 *
 * NOTE: In the MVP the public key IS the private key (symmetric HMAC).
 *       Upgrade to Ed25519 to get proper asymmetric verification.
 */
async function hmacVerify(
  keyMaterial: string,
  message: string,
  signature: string,
): Promise<boolean> {
  try {
    const expected = await hmacSign(keyMaterial, message);
    return expected === signature;
  } catch {
    return false;
  }
}

/** Generate a v4-like random UUID (no crypto.randomUUID dependency). */
function generateId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  // Set version (4) and variant bits per RFC 4122 §4.4
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

// ---------------------------------------------------------------------------
// CryptoBinding class
// ---------------------------------------------------------------------------

export class CryptoBinding {
  private keyPair: Ed25519KeyPair | null = null;
  private auditTrail: AuditChainEntry[] = [];
  private sequenceNumber: number = 0;
  private previousHash: string = "";
  private startHash: string = "";

  // -----------------------------------------------------------------------
  // Initialization
  // -----------------------------------------------------------------------

  /** Generate a session keypair and initialise the audit chain. */
  async init(sessionId: string): Promise<void> {
    // MVP: generate a random 32-byte key, base64-encode for storage.
    // Production: use Ed25519.generateKeyPair() instead.
    const rawKey = new Uint8Array(32);
    crypto.getRandomValues(rawKey);
    const pubB64 = btoa(String.fromCharCode(...rawKey));
    const privB64 = btoa(String.fromCharCode(...rawKey)); // MVP: same key for HMAC symmetry

    this.keyPair = {
      public_key: pubB64,
      private_key: privB64,
      created_at: new Date().toISOString(),
      session_id: sessionId,
    };

    // Genesis hash = SHA-256(session_id + timestamp)
    this.startHash = await sha256Hex(
      `${sessionId}:${this.keyPair.created_at}`,
    );
    this.previousHash = this.startHash;
    this.sequenceNumber = 0;
    this.auditTrail = [];
  }

  // -----------------------------------------------------------------------
  // G1: Capability Integrity — sign & verify tool definitions
  // -----------------------------------------------------------------------

  /** Sign a tool definition (G1 — Capability Integrity). */
  async signToolDefinition(
    toolName: string,
    toolDefJson: string,
  ): Promise<ToolSignature> {
    if (!this.keyPair) throw new Error("CryptoBinding not initialised");

    const toolHash = await sha256Hex(toolDefJson);
    const message = `${toolName}:${toolHash}`;
    const signature = await hmacSign(this.keyPair.private_key, message);

    return {
      tool_name: toolName,
      tool_hash: toolHash,
      signature,
      public_key: this.keyPair.public_key,
      timestamp: new Date().toISOString(),
    };
  }

  /** Verify a tool definition signature (G1 — Capability Integrity). */
  async verifyToolSignature(sig: ToolSignature): Promise<boolean> {
    const message = `${sig.tool_name}:${sig.tool_hash}`;
    return hmacVerify(sig.public_key, message, sig.signature);
  }

  // -----------------------------------------------------------------------
  // G2: Behavioral Verifiability — execution receipts
  // -----------------------------------------------------------------------

  /** Create an execution receipt (G2 — Behavioral Verifiability). */
  async createExecutionReceipt(
    toolName: string,
    inputArgs: Record<string, unknown>,
    output: unknown,
  ): Promise<ExecutionReceipt> {
    if (!this.keyPair) throw new Error("CryptoBinding not initialised");

    const inputJson = JSON.stringify(inputArgs);
    const outputJson = JSON.stringify(output);
    const inputHash = await sha256Hex(inputJson);
    const outputHash = await sha256Hex(outputJson);

    const message = `${toolName}:${inputHash}:${outputHash}`;
    const signature = await hmacSign(this.keyPair.private_key, message);

    return {
      receipt_id: generateId(),
      tool_name: toolName,
      input_hash: inputHash,
      output_hash: outputHash,
      signature,
      public_key: this.keyPair.public_key,
      timestamp: new Date().toISOString(),
    };
  }

  /** Verify an execution receipt (G2 — Behavioral Verifiability). */
  async verifyExecutionReceipt(receipt: ExecutionReceipt): Promise<boolean> {
    const message = `${receipt.tool_name}:${receipt.input_hash}:${receipt.output_hash}`;
    return hmacVerify(receipt.public_key, message, receipt.signature);
  }

  // -----------------------------------------------------------------------
  // G3: Interaction Auditability — hash-chained audit trail
  // -----------------------------------------------------------------------

  /** Add a message to the audit chain (G3 — Interaction Auditability). */
  async addToAuditChain(
    direction: "request" | "response",
    toolName: string,
    message: unknown,
  ): Promise<AuditChainEntry> {
    const messageJson = JSON.stringify(message);
    const messageHash = await sha256Hex(messageJson);

    this.sequenceNumber += 1;
    const entry: AuditChainEntry = {
      sequence_number: this.sequenceNumber,
      message_hash: messageHash,
      previous_hash: this.previousHash,
      direction,
      tool_name: toolName,
      timestamp: new Date().toISOString(),
    };

    this.auditTrail.push(entry);
    // The next entry will chain to this one
    this.previousHash = await sha256Hex(
      `${messageHash}:${this.previousHash}`,
    );

    return entry;
  }

  /** Verify the entire audit chain is intact (G3 — Interaction Auditability). */
  async verifyAuditChain(): Promise<{ valid: boolean; broken_at?: number }> {
    // The first entry should chain back to the startHash
    let expectedPrev = this.startHash;

    for (let i = 0; i < this.auditTrail.length; i++) {
      const entry = this.auditTrail[i];

      if (entry.previous_hash !== expectedPrev) {
        return { valid: false, broken_at: entry.sequence_number };
      }

      // Recompute the chain hash for the next entry
      expectedPrev = await sha256Hash(
        `${entry.message_hash}:${expectedPrev}`,
      );
    }

    return { valid: true };
  }

  /** Get the current audit trail. */
  getAuditTrail(): AuditTrail {
    const lastEntry =
      this.auditTrail.length > 0
        ? this.auditTrail[this.auditTrail.length - 1]
        : null;

    return {
      session_id: this.keyPair?.session_id ?? "",
      entries: [...this.auditTrail],
      start_hash: this.startHash,
      current_hash: lastEntry?.message_hash ?? this.startHash,
    };
  }

  /** Get the current keypair. */
  getKeyPair(): Ed25519KeyPair | null {
    return this.keyPair;
  }
}

// ---------------------------------------------------------------------------
// Standalone utility — sync SHA-256 helper for verifyAuditChain
// ---------------------------------------------------------------------------

/**
 * Simple async SHA-256 helper (avoids re-declaring `sha256Hex` inside the
 * class verification loop which would otherwise shadow it).
 */
async function sha256Hash(data: string): Promise<string> {
  const encoded = new TextEncoder().encode(data);
  const hashBuffer = await crypto.subtle.digest("SHA-256", encoded);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}