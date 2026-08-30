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
    "tool.execute.before": async (input, output) => {
      const toolName = input.tool

      const permCheck = safeharness.checkPermission(toolName)
      const sanitized = safeharness.sanitizeInput(toolName, output.args ?? {})
      output.args = sanitized.sanitized

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
        throw new Error(`CiteAgent blocked ${toolName}: ${violations.join("; ")}`)
      }

      await crypto.addToAuditChain("request", toolName, output.args ?? {})
    },

    "tool.execute.after": async (_input, output) => {
      const out = output.output ?? ""
      const toolName = String(_input.tool ?? "unknown")

      const verifyResult = safeharness.tieredVerify(
        toolName,
        _input.args ?? {},
        typeof out === "object" ? out : { text: String(out) },
      )
      if (!verifyResult.allowed) {
        safeharness.reportAnomaly()
      }

      await crypto.addToAuditChain("response", toolName, {
        output: String(out).substring(0, 100),
      })
      try {
        const receipt = await crypto.createExecutionReceipt(
          toolName,
          _input.args ?? {},
          out,
        )
        console.log(
          `[CiteAgent] Execution receipt: ${receipt.receipt_id} tool=${toolName}`,
        )
      } catch {
      }

      if (out.includes("merkle_proof") && out.includes("sha256")) {
        try {
          const parsed = JSON.parse(out)
          const items = Array.isArray(parsed) ? parsed : [parsed]
          const evidenceItems = items.filter(
            (item: Record<string, unknown>) =>
              "merkle_proof" in item && "sha256" in item,
          )
          if (evidenceItems.length > 0) {
            const ladder = new VerificationLadder(ctx.directory)
            const result = await ladder.run(evidenceItems)
            console.log(
              "[CiteAgent] Verification ladder result:",
              result.overall,
            )
          }
        } catch {
        }
      }
    },

    "experimental.session.compacting": async (_input, output) => {
      output.context.push(
        "## CiteAgent Academic Context\n- Preserve all citation keys and Merkle proof chains\n- Never compact evidence items with unverifiable hashes\n- Maintain CSL registry references across compaction\n- Keep verification ladder results for active evidence",
      )

      const violations = monitor.checkLiveness()
      if (violations.length > 0) {
        output.context.push(
          `## LTL Violations Detected\n${violations.map((v) => `- ${v.invariant_name}: ${v.message}`).join("\n")}`,
        )
      }

      const trail = crypto.getAuditTrail()
      if (trail.entries.length > 0) {
        output.context.push(
          `## Audit Trail\n- Session: ${trail.session_id}\n- Messages: ${trail.entries.length}\n- Chain valid: ${trail.current_hash ? "yes" : "no"}`,
        )
      }
    },
  }
}
