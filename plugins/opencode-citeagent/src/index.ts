import type { Plugin } from "@opencode-ai/plugin"
import { createCiteAgentTools } from "./tools/index.js"
import { createCiteAgentHooks } from "./hooks/index.js"
import { getBridge } from "./mcp-bridge.js"

export const CiteAgentPlugin: Plugin = async (ctx) => {
  // Connect to the Python backend (spawn + stdio)
  const bridge = getBridge(ctx.directory)
  await bridge.connect()

  const tools = await createCiteAgentTools(ctx)
  const hooks = await createCiteAgentHooks(ctx)

  return {
    tool: tools,
    ...hooks,
  }
}

export default { server: CiteAgentPlugin }