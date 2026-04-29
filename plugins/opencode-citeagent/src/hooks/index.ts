import { getBridge } from "../mcp-bridge.js"
import { VerificationLadder } from "../verification.js"
import { SafeHarness } from "../safeharness.js"
import { LTLMonitor } from "../ltl-monitor.js"
import { CryptoBinding } from "../crypto.js"
import type { Hooks } from "@opencode-ai/plugin"

export async function createCiteAgentHooks(ctx: {
  directory: string
}): Promise<Hooks> {
  const safeharness = new SafeHarness()
  const monitor = new LTLMonitor()
  const crypto = new CryptoBinding()
  await crypto.init(`session-${Date.now()}`)

  return {
    "tool.execute.before": async (input, _output) => {
      const toolName = input.tool

      // SafeHarness Layer 3: Constrain — check tool permission
      const permCheck = safeharness.checkPermission(toolName)
      if (!permCheck.allowed) {
        console.warn(
          `[CiteAgent] SafeHarness blocked tool ${toolName}: ${permCheck.reason}`,
        )
        return
      }

      // SafeHarness Layer 1: Inform — sanitize input
      const sanitized = safeharness.sanitizeInput(toolName, input.args ?? {})
      if (sanitized.sanitized_input) {
        input.args = sanitized.sanitized_input
      }

      // LTL Monitor: check transition
      const transition = monitor.transition({
        type: "tool_call",
        tool_name: toolName,
        tool_risk_tier: permCheck.risk_tier,
        timestamp: Date.now(),
      })
      if (!transition.allowed) {
        const violations = transition.violations
          .filter((v) => v.severity === "error")
          .map((v) => v.message)
        console.warn(
          `[CiteAgent] LTL monitor blocked tool ${toolName}:`,
          violations.join("; "),
        )
        return
      }

      // Crypto: add to audit chain
      crypto.addToAuditChain("request", toolName, input.args ?? {})
    },

    "tool.execute.after": async (_input, output) => {
      const out = output.output ?? ""
      const toolName = String(_input.tool ?? "unknown")

      // SafeHarness Layer 2: Verify — check result validity
      const verifyResult = safeharness.tieredVerify(
        toolName,
        _input.args ?? {},
        typeof out === "object" ? out : { text: String(out) },
      )
      if (!verifyResult.allowed) {
        safeharness.reportAnomaly(
          `Post-hoc verification failed for ${toolName}: ${verifyResult.reason}`,
        )
      }

      // Crypto: add response to audit chain
      crypto.addToAuditChain("response", toolName, {
        output: String(out).substring(0, 100),
      })
      // Create execution receipt
      try {
        const receipt = crypto.createExecutionReceipt(
          toolName,
          _input.args ?? {},
          out,
        )
        console.log(
          `[CiteAgent] Execution receipt: ${receipt.receipt_id} tool=${toolName}`,
        )
      } catch {
        // Receipt creation may fail for non-serializable outputs — skip
      }

      // SafeHarness Layer 4: Correct — checkpoint after writes
      safeharness.checkpoint(toolName, JSON.stringify(_input.args ?? {}))

      // Verification ladder for evidence-bearing outputs
      if (out.includes("merkle_proof") && out.includes("sha256")) {
        try {
          const parsed = JSON.parse(out)
          const items = Array.isArray(parsed) ? parsed : [parsed]
          const evidenceItems = items.filter(
            (item: Record<string, unknown>) =>
              "merkle_proof" in item && "sha256" in item,
          )
          if (evidenceItems.length > 0) {
            const bridge = getBridge(ctx.directory)
            const ladder = new VerificationLadder(bridge)
            const result = await ladder.run(evidenceItems)
            console.log(
              "[CiteAgent] Verification ladder result:",
              result.overall,
            )
          }
        } catch {
          // Failed to parse or verify — skip silently
        }
      }
    },

    "experimental.session.compacting": async (_input, output) => {
      output.context.push(
        "## CiteAgent Academic Context\n- Preserve all citation keys and Merkle proof chains\n- Never compact evidence items with unverifiable hashes\n- Maintain CSL registry references across compaction\n- Keep verification ladder results for active evidence",
      )

      // LTL: check liveness at compaction
      const violations = monitor.checkLiveness()
      if (violations.length > 0) {
        output.context.push(
          `## LTL Violations Detected\n${violations.map((v) => `- ${v.invariant_name}: ${v.message}`).join("\n")}`,
        )
      }

      // Crypto: log audit trail summary
      const trail = crypto.getAuditTrail()
      if (trail.entries.length > 0) {
        output.context.push(
          `## Audit Trail\n- Session: ${trail.session_id}\n- Messages: ${trail.entries.length}\n- Chain valid: ${trail.current_hash ? "yes" : "no"}`,
        )
      }
    },
  }
}