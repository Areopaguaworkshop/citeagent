import { Client } from "@modelcontextprotocol/sdk/client/index.js"
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js"
import path from "path"
import os from "os"
import { execSync } from "child_process"

/**
 * CiteAgentBridge — plugin-owned subprocess that talks to the Python backend.
 *
 * Unlike the old CiteAgentMcpBridge (which relied on OpenCode's MCP client
 * to spawn the server), this bridge spawns `citeindex.mcp_server` itself,
 * sets the correct environment, and owns the full connection lifecycle.
 * This eliminates the -32000 Connection Closed errors caused by OpenCode's
 * MCP client managing the stdio lifecycle.
 */
export class CiteAgentBridge {
  private client: Client | null = null
  private transport: StdioClientTransport | null = null
  private connected = false
  private projectDir: string
  private pythonCmd: string
  private reconnectAttempts = 0
  private maxReconnects = 3
  private shuttingDown = false

  constructor(projectDir: string) {
    this.projectDir = projectDir
    this.pythonCmd =
      process.env.CITEAGENT_PYTHON ||
      CiteAgentBridge.findPython(projectDir)
  }

  /**
   * Auto-detect a Python interpreter that can import citeindex.
   * Priority: CITEAGENT_PYTHON env → project .venv → rye → uv → system python3.
   */
  static findPython(projectDir: string): string {
    const candidates = [
      path.join(projectDir, ".venv", "bin", "python3"),
      path.join(os.homedir(), ".rye", "py", "cpython@3.12.8", "bin", "python3.12"),
      path.join(os.homedir(), ".local", "share", "uv", "python", "bin", "python3"),
      "python3",
    ]
    for (const cmd of candidates) {
      try {
        execSync(`${cmd} -c "import citeindex"`, {
          stdio: "pipe",
          timeout: 5000,
        })
        return cmd
      } catch {
        continue
      }
    }
    // Last resort — will produce a clear error at connect() time
    return "python3"
  }

  async connect(): Promise<void> {
    if (this.connected && this.client) return

    this.transport = new StdioClientTransport({
      command: this.pythonCmd,
      args: ["-m", "citeindex.mcp_server"],
      env: {
        ...process.env,
        PYTHONPATH: this.projectDir,
        CITEAGENT_CORPUS_ROOT: path.join(this.projectDir, "corpus"),
      } as Record<string, string>,
      stderr: "pipe",
    })

    // Log stderr from Python process
    this.transport.stderr?.on("data", (chunk: Buffer) => {
      const msg = chunk.toString().trim()
      if (msg) console.debug("[CiteAgent kernel]", msg)
    })

    this.client = new Client({
      name: "opencode-citeagent",
      version: "0.2.0",
    })

    try {
      await this.client.connect(this.transport)
      this.connected = true
      this.reconnectAttempts = 0
    } catch (error) {
      this.connected = false
      throw new Error(
        `CiteAgent: failed to connect to Python backend: ${error}`,
      )
    }
  }

  async callTool(
    name: string,
    args: Record<string, unknown>,
  ): Promise<string> {
    if (!this.connected || !this.client) {
      await this.reconnect()
    }
    try {
      const result = await this.client!.callTool({ name, arguments: args })
      return this.extractText(result)
    } catch (error) {
      if (this.shouldReconnect(error)) {
        await this.reconnect()
        const result = await this.client!.callTool({ name, arguments: args })
        return this.extractText(result)
      }
      throw error
    }
  }

  async disconnect(): Promise<void> {
    this.shuttingDown = true
    if (this.client && this.connected) {
      try {
        await this.client.close()
      } catch {
        // ignore close errors
      }
    }
    this.connected = false
    this.client = null
    this.transport = null
  }

  /** Extract text content from MCP CallToolResult */
  private extractText(result: unknown): string {
    if (
      result &&
      typeof result === "object" &&
      "content" in result &&
      Array.isArray((result as any).content)
    ) {
      const content = (result as any).content
      const textItem = content.find((c: any) => c.type === "text")
      if (textItem?.text) return textItem.text
    }
    return JSON.stringify(result, null, 2)
  }

  private shouldReconnect(error: unknown): boolean {
    if (this.shuttingDown) return false
    if (error instanceof Error) {
      const msg = error.message.toLowerCase()
      return (
        msg.includes("connection") ||
        msg.includes("closed") ||
        msg.includes("-32000")
      )
    }
    return false
  }

  private async reconnect(): Promise<void> {
    if (this.reconnectAttempts >= this.maxReconnects) {
      throw new Error("CiteAgent: max reconnection attempts reached")
    }
    this.reconnectAttempts++
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 10000)
    await new Promise<void>((r) => setTimeout(r, delay))
    await this.disconnect()
    this.shuttingDown = false // reset for reconnect
    await this.connect()
  }
}

// ── Singleton ──────────────────────────────────────────────────────────

let _bridge: CiteAgentBridge | null = null

export function getBridge(projectDir: string): CiteAgentBridge {
  if (!_bridge) {
    _bridge = new CiteAgentBridge(projectDir)
  }
  return _bridge
}

export function resetBridge(): void {
  _bridge = null
}
