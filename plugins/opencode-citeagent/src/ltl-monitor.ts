import type { AgentState, AgentEvent, LTLInvariant, LTLViolation, TraceEntry } from "./types.js";

// Set of read-only tool names allowed in VERIFY / COMMIT states
const READ_ONLY_TOOLS = new Set([
  "cite_search",
  "cite_verify",
  "cite_render",
  "cite_node_lookup",
  "cite_tree",
  "cite_argument_query",
  "cite_memory_save",
  "audit_retrieve",
  "search_memory",
  "tree_load",
  "tree_traverse",
  "csl_render",
  "node_lookup",
]);

// Evidence-producing tool names (require verification before COMMIT)
const EVIDENCE_TOOLS = new Set(["search_documents", "search_claims", "cite_search", "cite_search_claims"]);

// ── Built-in invariants ────────────────────────────────────────────────

const VERIFY_BEFORE_COMMIT: LTLInvariant = {
  id: "verify_before_commit",
  name: "VERIFY_BEFORE_COMMIT",
  description: "COMMIT state can only be entered from VERIFY state",
  check: (prev, _event, next) => {
    if (next === "commit" && prev !== "verify") return false;
    return true;
  },
  severity: "error",
};

const PLAN_BEFORE_ACT: LTLInvariant = {
  id: "plan_before_act",
  name: "PLAN_BEFORE_ACT",
  description: "ACT state can only be entered from PLAN or ACT state",
  check: (prev, _event, next) => {
    if (next === "act" && prev !== "plan" && prev !== "act") return false;
    return true;
  },
  severity: "error",
};

const NO_UNGRANTED_TOOL: LTLInvariant = {
  id: "no_ungranted_tool",
  name: "NO_UNGRANTED_TOOL",
  description: "In VERIFY/COMMIT state, only read-only tools may be called",
  check: (_prev, event, nextState) => {
    // This invariant applies when a tool_call event occurs and the
    // resulting state is verify or commit. We also check when the
    // current state *is* verify/commit and a tool_call arrives.
    if (event.type !== "tool_call") return true;
    const toolName = event.tool_name ?? "";
    if (nextState === "verify" || nextState === "commit") {
      return READ_ONLY_TOOLS.has(toolName);
    }
    return true;
  },
  severity: "error",
};

const MERKLE_BEFORE_OUTPUT: LTLInvariant = {
  id: "merkle_before_output",
  name: "MERKLE_BEFORE_OUTPUT",
  description: "Evidence-producing tools must have corresponding verification before COMMIT",
  check: (_prev, event, next) => {
    // Lightweight per-event check: flag warning if an evidence tool is
    // called and the transition leads to commit without a prior
    // verification step. A more thorough post-hoc analysis happens in
    // checkLiveness().
    if (event.type === "tool_call" && EVIDENCE_TOOLS.has(event.tool_name ?? "") && next === "commit") {
      return false;
    }
    return true;
  },
  severity: "warning",
};

const LIVENESS_PLAN_TO_DONE: LTLInvariant = {
  id: "liveness_plan_to_done",
  name: "LIVENESS_PLAN_TO_DONE",
  description: "Every PLAN must eventually reach DONE (post-hoc check)",
  // Always passes per-event; real check is in checkLiveness()
  check: () => true,
  severity: "warning",
};

const DEFAULT_INVARIANTS: LTLInvariant[] = [
  VERIFY_BEFORE_COMMIT,
  PLAN_BEFORE_ACT,
  NO_UNGRANTED_TOOL,
  MERKLE_BEFORE_OUTPUT,
  LIVENESS_PLAN_TO_DONE,
];

// ── State transition table (deterministic, O(1)) ───────────────────────

function resolveNextState(current: AgentState, event: AgentEvent): AgentState {
  switch (event.type) {
    case "user_message":
      if (current === "idle" || current === "done" || current === "error") return "plan";
      return current;
    case "tool_call":
      if (current === "plan") return "act";
      if (current === "act") return "act";
      if (current === "verify") return "verify";
      if (current === "commit") return "commit";
      return current;
    case "tool_result":
      if (current === "act") return "verify";
      if (current === "verify") return "verify";
      if (current === "commit") return "commit";
      return current;
    case "commit":
      if (current === "verify" || current === "commit") return "commit";
      return current;
    case "error":
      return "error";
    case "subagent_spawn":
      if (current === "plan" || current === "act") return "act";
      return current;
    default:
      return current;
  }
}

// ── LTLMonitor ─────────────────────────────────────────────────────────

export class LTLMonitor {
  private state: AgentState = "idle";
  private trace: TraceEntry[] = [];
  private invariants: LTLInvariant[];
  // Track whether verification occurred since last evidence-producing call
  private evidenceSeen = false;
  private verifiedSinceEvidence = false;

  constructor(invariants?: LTLInvariant[]) {
    this.invariants = invariants ?? DEFAULT_INVARIANTS;
  }

  /** O(1) state transition check. Rejects if any error-severity invariant fails. */
  transition(event: AgentEvent): { allowed: boolean; newState: AgentState; violations: LTLViolation[] } {
    const prevState = this.state;
    const nextState = resolveNextState(prevState, event);

    // Track evidence / verification relationship for MERKLE_BEFORE_OUTPUT
    if (event.type === "tool_call" && EVIDENCE_TOOLS.has(event.tool_name ?? "")) {
      this.evidenceSeen = true;
      this.verifiedSinceEvidence = false;
    }
    if (event.type === "tool_call" && (event.tool_name === "cite_verify" || event.tool_name === "merkle_verify")) {
      this.verifiedSinceEvidence = true;
    }

    // Evaluate all invariants — O(k) where k is constant (5 invariants)
    const violations: LTLViolation[] = [];

    for (const inv of this.invariants) {
      if (!inv.check(prevState, event, nextState)) {
        violations.push({
          invariant_id: inv.id,
          invariant_name: inv.name,
          previous_state: prevState,
          event,
          attempted_state: nextState,
          severity: inv.severity,
          timestamp: event.timestamp,
          message: `Invariant "${inv.name}" violated: ${inv.description} (transition ${prevState} → ${nextState})`,
        });
      }
    }

    const hasError = violations.some((v) => v.severity === "error");

    // Only commit state change if allowed
    if (!hasError) {
      this.state = nextState;
    }

    const entry: TraceEntry = {
      from: prevState,
      event,
      to: hasError ? prevState : nextState,
      timestamp: event.timestamp,
      violations,
    };
    this.trace.push(entry);

    return {
      allowed: !hasError,
      newState: hasError ? prevState : nextState,
      violations,
    };
  }

  /** Returns the current agent state. */
  getState(): AgentState {
    return this.state;
  }

  /** Returns the full trace for post-hoc analysis. */
  getTrace(): TraceEntry[] {
    return this.trace;
  }

  /**
   * Post-hoc Büchi-style liveness check: every PLAN entry must eventually
   * reach DONE in the trace. Returns violations for any PLAN that did not.
   */
  checkLiveness(): LTLViolation[] {
    const violations: LTLViolation[] = [];

    // Check LIVENESS_PLAN_TO_DONE: every PLAN must reach DONE
    let planEntryIndex = -1;
    for (let i = 0; i < this.trace.length; i++) {
      if (this.trace[i].to === "plan") {
        planEntryIndex = i;
      }
      if (planEntryIndex !== -1 && this.trace[i].to === "done") {
        planEntryIndex = -1; // satisfied
      }
    }

    if (planEntryIndex !== -1) {
      violations.push({
        invariant_id: "liveness_plan_to_done",
        invariant_name: "LIVENESS_PLAN_TO_DONE",
        previous_state: this.trace[planEntryIndex].from,
        event: this.trace[planEntryIndex].event,
        attempted_state: "plan",
        severity: "warning",
        timestamp: Date.now(),
        message: "Liveness violation: PLAN state reached but never transitioned to DONE",
      });
    }

    // Check MERKLE_BEFORE_OUTPUT post-hoc: evidence produced but no
    // verification before reaching COMMIT or DONE
    let evidenceSeen = false;
    let verifiedAfterEvidence = false;
    for (const entry of this.trace) {
      if (
        entry.event.type === "tool_call" &&
        EVIDENCE_TOOLS.has(entry.event.tool_name ?? "")
      ) {
        evidenceSeen = true;
        verifiedAfterEvidence = false;
      }
      if (
        entry.event.type === "tool_call" &&
        (entry.event.tool_name === "cite_verify" || entry.event.tool_name === "merkle_verify")
      ) {
        verifiedAfterEvidence = true;
      }
      if ((entry.to === "commit" || entry.to === "done") && evidenceSeen && !verifiedAfterEvidence) {
        violations.push({
          invariant_id: "merkle_before_output",
          invariant_name: "MERKLE_BEFORE_OUTPUT",
          previous_state: entry.from,
          event: entry.event,
          attempted_state: entry.to,
          severity: "warning",
          timestamp: entry.timestamp,
          message: "Evidence-producing tool was called without subsequent verification before COMMIT/DONE",
        });
        evidenceSeen = false; // report once per evidence→commit chain
      }
      if (entry.to === "commit" || entry.to === "done") {
        evidenceSeen = false;
        verifiedAfterEvidence = false;
      }
    }

    return violations;
  }

  /** Reset monitor to idle state. */
  reset(): void {
    this.state = "idle";
    this.trace = [];
    this.evidenceSeen = false;
    this.verifiedSinceEvidence = false;
  }
}
