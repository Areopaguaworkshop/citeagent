import type { Plugin } from "@opencode-ai/plugin"
import { createCiteAgentTools } from "./tools/index.js"
import { createCiteAgentHooks } from "./hooks/index.js"
import { getMcpManager } from "./mcp-bridge.js"

export const CiteAgentPlugin: Plugin = async (ctx) => {
  // Connect the Python backend + built-in MCP servers (websearch, context7, grep_app)
  const manager = getMcpManager(ctx.directory)
  await manager.connectAll(ctx.directory)

  const tools = await createCiteAgentTools(ctx)
  const hooks = await createCiteAgentHooks(ctx)

  return {
    tool: tools,
    ...hooks,
  }
}

export default { server: CiteAgentPlugin }