export interface EvidenceItem {
  node_id: string;
  source_id: string;
  sha256: string;
  merkle_proof: string[];
  citation_key: string;
  citation_rendered: string;
}

export interface VerificationResult {
  passed: boolean;
  level: number;
  message: string;
  details?: string;
}

export interface L5AuditResult {
  verdict: "approved" | "rejected" | "pending";
  reasoning: string;
  audited_evidence: EvidenceItem[];
  original_query: string;
  timestamp: string;
  model_id: string;
}

export type VerificationLadderOverall = "approved" | "rejected" | "pending_audit";

export interface VerificationLadderResult {
  overall: VerificationLadderOverall;
  rungs: VerificationResult[];
  evidence: EvidenceItem[];
}

export type MemoryTier = "working" | "episodic" | "long_term" | "corpus";

export interface MemoryEntry {
  entry_id: string;
  tier: MemoryTier;
  key: string;
  content: string;
  metadata: Record<string, unknown>;
  tags: string[];
  thread_id: string;
  sha256: string;
  timestamp: string;
  source_ids?: string[];
}

export interface MemoryStoreResult {
  entry_id: string;
  stored: boolean;
  tier: MemoryTier;
}

export interface MemoryRetrieveResult {
  entries: MemoryEntry[];
  total: number;
  tier: MemoryTier;
}

export interface MemoryConsolidateResult {
  consolidated_count: number;
  from_tier: MemoryTier;
  to_tier: MemoryTier;
}

export interface CiteAgentMcpBridge {
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  callTool(name: string, args: Record<string, unknown>): Promise<unknown>;
  listTools(): Promise<Array<{ name: string; description?: string }>>;
}

// ---------------------------------------------------------------------------
// Cryptographic Binding types (arXiv:2603.14332 — G1/G2/G3 guarantees)
// ---------------------------------------------------------------------------

export interface Ed25519KeyPair {
  public_key: string;   // base64 encoded
  private_key: string;  // base64 encoded
  created_at: string;
  session_id: string;
}

export interface ToolSignature {
  tool_name: string;
  tool_hash: string;      // SHA-256 of tool definition JSON
  signature: string;       // Ed25519 signature, base64
  public_key: string;     // signer's public key, base64
  timestamp: string;
}

export interface ExecutionReceipt {
  receipt_id: string;
  tool_name: string;
  input_hash: string;     // SHA-256 of input args JSON
  output_hash: string;    // SHA-256 of output JSON
  signature: string;       // Ed25519 signature of (tool_name + input_hash + output_hash)
  public_key: string;
  capability_token?: string;
  merkle_proof?: string;   // if applicable
  timestamp: string;
}

export interface AuditChainEntry {
  sequence_number: number;
  message_hash: string;    // SHA-256 of this message
  previous_hash: string;    // SHA-256 of previous message (chain)
  direction: "request" | "response";
  tool_name: string;
  timestamp: string;
}

export interface AuditTrail {
  session_id: string;
  entries: AuditChainEntry[];
  start_hash: string;      // SHA-256 of session init
  current_hash: string;     // latest chain hash
}

export type RiskTier = "read" | "workspace" | "network" | "system";

export interface ToolPermission {
  tool_name: string;
  risk_tier: RiskTier;
  requires_approval: boolean;
  sandbox_required: boolean;
  max_calls_per_session?: number;
}

export interface ProvenanceTag {
  source_id: string;
  trust_level: "verified" | "unverified" | "external" | "user";
  sanitized: boolean;
  timestamp: string;
}

export interface SecurityCheckResult {
  allowed: boolean;
  layer: "inform" | "verify" | "constrain" | "correct";
  reason: string;
  sanitized_input?: Record<string, unknown>;
  risk_tier?: RiskTier;
}

export interface StateCheckpoint {
  checkpoint_id: string;
  timestamp: string;
  tool_name: string;
  input_hash: string;
  rollback_available: boolean;
}

// ── LTL Monitor Types ──────────────────────────────────────────────────

/** Agent session states in the CiteAgent harness loop. */
export type AgentState = "idle" | "plan" | "act" | "verify" | "commit" | "done" | "error";

/** Events that trigger state transitions. */
export interface AgentEvent {
  type: "tool_call" | "tool_result" | "user_message" | "subagent_spawn" | "commit" | "error";
  tool_name?: string;
  tool_risk_tier?: "read" | "workspace" | "network" | "system";
  payload?: Record<string, unknown>;
  timestamp: number;
}

/** LTL invariant: predicate on (previousState, event, currentState). */
export interface LTLInvariant {
  id: string;
  name: string;
  description: string;
  check: (prev: AgentState, event: AgentEvent, next: AgentState) => boolean;
  severity: "error" | "warning"; // error = force termination, warning = log
}

/** Violation record produced when an invariant fails. */
export interface LTLViolation {
  invariant_id: string;
  invariant_name: string;
  previous_state: AgentState;
  event: AgentEvent;
  attempted_state: AgentState;
  severity: "error" | "warning";
  timestamp: number;
  message: string;
}

/** Trace entry for post-hoc analysis. */
export interface TraceEntry {
  from: AgentState;
  event: AgentEvent;
  to: AgentState;
  timestamp: number;
  violations: LTLViolation[];
}

// ---------------------------------------------------------------------------
// Re-exports from safeharness.ts and crypto.ts for unified type access
// ---------------------------------------------------------------------------

export type { RiskTier as SafeHarnessRiskTier, ToolPermission as SafeHarnessToolPermission, SecurityCheckResult as SafeHarnessSecurityCheckResult, StateCheckpoint as SafeHarnessStateCheckpoint } from "./safeharness.js";

export type { Ed25519KeyPair, ToolSignature, ExecutionReceipt, AuditChainEntry, AuditTrail } from "./crypto.js";