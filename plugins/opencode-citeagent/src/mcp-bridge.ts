import { Client } from "@modelcontextprotocol/sdk/client/index.js"
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js"
import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js"
import path from "path"
import os from "os"
import fs from "fs"
import { execSync } from "child_process"

// ── Built-in MCP server definitions ──────────────────────────────────────

/** Descriptor for a built-in remote MCP server (SSE/HTTP-based). */
export interface BuiltinMcpDef {
  /** Unique key used in config and routing (e.g. "websearch"). */
  key: string
  /** Display name for log messages. */
  name: string
  /** Remote SSE endpoint URL. */
  url: string
  /** Environment variable names that provide API keys (checked in order). */
  requiredEnvVars?: string[]
  /** Optional environment variable names — no warning if missing. */
  optionalEnvVars?: string[]
  /** Custom headers to send with every request (e.g. x-api-key). */
  headers?: () => Record<string, string>
}

/**
 * Built-in MCP servers available alongside the Python backend.
 * Each entry describes how to connect and what auth is needed.
 */
export const BUILTIN_MCPS: ReadonlyArray<BuiltinMcpDef> = [
  {
    key: "websearch",
    name: "Exa Web Search",
    url: "https://mcp.exa.ai/mcp?tools=web_search_exa",
    requiredEnvVars: ["EXA_API_KEY", "TAVILY_API_KEY"],
    headers: () => {
      const key = process.env.EXA_API_KEY || process.env.TAVILY_API_KEY || ""
      return key ? { "x-api-key": key } : {}
    },
  },
  {
    key: "context7",
    name: "Context7 Docs",
    url: "https://mcp.context7.com/mcp",
    optionalEnvVars: ["CONTEXT7_API_KEY"],
    headers: () => {
      const key = process.env.CONTEXT7_API_KEY || ""
      return key ? { Authorization: `Bearer ${key}` } : {}
    },
  },
  {
    key: "grep_app",
    name: "Grep.app Code Search",
    url: "https://mcp.grep.app",
  },
] as const

// ── Config loading ───────────────────────────────────────────────────────

interface CiteAgentConfig {
  disabled_mcps?: string[]
}

/**
 * Read ~/.config/opencode/citeagent.json and return the parsed config.
 * Returns an empty config (all MCPs enabled) if the file doesn't exist.
 */
function loadConfig(): CiteAgentConfig {
  const configPath = path.join(
    os.homedir(),
    ".config",
    "opencode",
    "citeagent.json",
  )
  try {
    if (fs.existsSync(configPath)) {
      const raw = fs.readFileSync(configPath, "utf-8")
      return JSON.parse(raw) as CiteAgentConfig
    }
  } catch (err) {
    console.warn("[CiteAgent] Failed to load config from", configPath, err)
  }
  return {}
}

// ── CiteAgentBridge (Python backend, unchanged) ──────────────────────────

/**
 * CiteAgentBridge — plugin-owned subprocess that talks to the Python backend.
 *
 * Unlike the old CiteAgentMcpBridge (which relied on OpenCode's MCP client
 * to spawn the server), this bridge spawns `citeagent.mcp_server` itself,
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
   * Auto-detect a Python interpreter that can import citeagent.
   * Priority: CITEAGENT_PYTHON env → project .venv → uv tool → rye → system python3.
   */
  static findPython(projectDir: string): string {
    const candidates = [
      path.join(projectDir, ".venv", "bin", "python3"),
      path.join(os.homedir(), ".local", "share", "uv", "tools", "citeagent", "bin", "python"),
      path.join(os.homedir(), ".local", "share", "uv", "tools", "citeagent", "bin", "python3"),
      path.join(os.homedir(), ".rye", "py", "cpython@3.12.8", "bin", "python3.12"),
      path.join(os.homedir(), ".local", "share", "uv", "python", "bin", "python3"),
      "python3",
    ]
    for (const cmd of candidates) {
      try {
        execSync(`${cmd} -c "import citeagent"`, {
          stdio: "pipe",
          timeout: 5000,
        })
        return cmd
      } catch {
        continue
      }
    }
    // If no python found but citeagent CLI exists, try to resolve its python
    // (uv tool install creates a wrapper script that points at a venv)
    try {
      const citeagentPath = execSync("which citeagent", { stdio: "pipe", timeout: 3000 })
        .toString()
        .trim()
      if (citeagentPath) {
        // The citeagent binary is a shim; we can try to find the real python from its shebang
        const shebang = execSync(`head -1 "${citeagentPath}"`, { stdio: "pipe" })
          .toString()
          .trim()
        if (shebang.startsWith("#!/")) {
          const binPath = shebang.slice(2).replace(/\s.*/, "")
          try {
            // Verify this python can import citeagent
            execSync(`${path.dirname(binPath)}/python3 -c "import citeagent"`, {
              stdio: "pipe",
              timeout: 5000,
            })
            return `${path.dirname(binPath)}/python3`
          } catch {
            // shebang wasn't the python — skip
          }
        }
        // Fallback: citeagent is on PATH and works, use system python3
        // (uv tool creates a wrapper; the real import might need uv run)
        try {
          execSync("python3 -c \"import citeagent\"", { stdio: "pipe", timeout: 5000 })
        } catch {
          // python3 can't import citeagent but citeagent binary exists
          // This likely means citeagent is in a PATH dir but python3 is system
          // Warn will be shown at connect time
        }
      }
    } catch {
      // citeagent not on PATH either
    }
    // Last resort
    return "python3"
  }

  async connect(): Promise<void> {
    if (this.connected && this.client) return

    this.transport = new StdioClientTransport({
      command: this.pythonCmd,
      args: ["-m", "citeagent.mcp_server"],
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
      version: "0.3.2",
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

// ── CiteAgentMcpManager ──────────────────────────────────────────────────

/** A connected built-in MCP client keyed by its definition key. */
interface ConnectedMcp {
  def: BuiltinMcpDef
  client: Client
  transport: SSEClientTransport
}

/**
 * CiteAgentMcpManager — manages the Python bridge connection plus
 * built-in remote MCP servers (websearch, context7, grep_app).
 *
 * Routing rules for callTool():
 *   - Tool names starting with "cite_" → Python bridge
 *   - Otherwise, route to the MCP whose definition matches the tool.
 *     Since we don't know exact tool names for remote MCPs ahead of time,
 *     we try each enabled built-in MCP in order and return the first
 *     successful result.
 */
export class CiteAgentMcpManager {
  /** The Python backend bridge. */
  private bridge: CiteAgentBridge

  /** Set of MCP keys to skip (loaded from config). */
  readonly disabledMcps: Set<string>

  /** Connected built-in MCP clients. */
  private builtinConnections: Map<string, ConnectedMcp> = new Map()

  constructor(projectDir: string) {
    this.bridge = new CiteAgentBridge(projectDir)
    const config = loadConfig()
    this.disabledMcps = new Set(config.disabled_mcps ?? [])
  }

  /** Connect the Python bridge and all enabled built-in MCP servers. */
  async connectAll(projectDir: string): Promise<void> {
    // 1. Connect the Python backend (must succeed)
    await this.bridge.connect()

    // 2. Connect each enabled built-in MCP
    for (const def of BUILTIN_MCPS) {
      if (this.disabledMcps.has(def.key)) {
        console.debug(`[CiteAgent] Skipping disabled MCP: ${def.key}`)
        continue
      }
      await this.connectBuiltin(def)
    }
  }

  /**
   * Connect a single built-in MCP server.
   * Logs a warning and continues on failure (non-fatal).
   */
  private async connectBuiltin(def: BuiltinMcpDef): Promise<void> {
    // Check required environment variables
    if (def.requiredEnvVars?.length) {
      const hasRequired = def.requiredEnvVars.some(
        (envVar) => process.env[envVar],
      )
      if (!hasRequired) {
        console.warn(
          `[CiteAgent] Skipping ${def.key} (${def.name}): missing required env var(s) ` +
            def.requiredEnvVars.join(" or "),
        )
        return
      }
    }

    try {
      // Build transport with optional custom headers
      const headers = def.headers?.() ?? {}
      const transport = new SSEClientTransport(new URL(def.url), {
        requestInit: Object.keys(headers).length > 0 ? { headers } : undefined,
      })

      const client = new Client({
        name: "opencode-citeagent",
        version: "0.3.2",
      })

      await client.connect(transport)
      this.builtinConnections.set(def.key, { def, client, transport })
      console.debug(`[CiteAgent] Connected built-in MCP: ${def.key} (${def.name})`)
    } catch (err) {
      console.warn(
        `[CiteAgent] Failed to connect built-in MCP ${def.key} (${def.name}):`,
        err instanceof Error ? err.message : err,
      )
    }
  }

  /** Disconnect all MCP connections (Python bridge + built-ins). */
  async disconnectAll(): Promise<void> {
    // Disconnect built-in MCPs
    for (const [key, conn] of this.builtinConnections) {
      try {
        await conn.client.close()
      } catch {
        // ignore close errors
      }
    }
    this.builtinConnections.clear()

    // Disconnect Python bridge
    await this.bridge.disconnect()
  }

  /**
   * Call a tool on the appropriate MCP server.
   *
   * Routing:
   *  - "cite_*" → Python bridge
   *  - Otherwise → try each connected built-in MCP until one succeeds
   *    (remote MCPs expose unique tool names, so only one will recognise it).
   */
  async callTool(
    name: string,
    args: Record<string, unknown>,
  ): Promise<string> {
    // Route cite_* tools to the Python bridge
    if (name.startsWith("cite_")) {
      return this.bridge.callTool(name, args)
    }

    // Try each connected built-in MCP
    for (const [key, conn] of this.builtinConnections) {
      try {
        const result = await conn.client.callTool({ name, arguments: args })
        return extractMcpText(result)
      } catch (err) {
        // If the server doesn't know this tool, try the next one
        const msg = err instanceof Error ? err.message : String(err)
        if (
          msg.includes("not found") ||
          msg.includes("unknown tool") ||
          msg.includes("Method not found")
        ) {
          continue
        }
        // Auth/network errors — don't try further
        throw err
      }
    }

    throw new Error(
      `CiteAgent: no MCP server recognized tool "${name}". ` +
        `Connected: bridge + [${[...this.builtinConnections.keys()].join(", ")}]`,
    )
  }

  /** Access the underlying Python bridge (for backward compat). */
  getBridge(): CiteAgentBridge {
    return this.bridge
  }
}

// ── Helper: extract text from MCP CallToolResult ─────────────────────────

function extractMcpText(result: unknown): string {
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

// ── Singleton ────────────────────────────────────────────────────────────

let _manager: CiteAgentMcpManager | null = null

/** Get (or create) the global MCP manager singleton. */
export function getMcpManager(projectDir: string): CiteAgentMcpManager {
  if (!_manager) {
    _manager = new CiteAgentMcpManager(projectDir)
  }
  return _manager
}

/**
 * Convenience: get the Python bridge from the global manager.
 * Backward-compatible with code that only used getBridge().
 */
export function getBridge(projectDir: string): CiteAgentBridge {
  return getMcpManager(projectDir).getBridge()
}

/** Reset the global manager and all connections. */
export function resetAll(): void {
  _manager = null
}

/**
 * @deprecated Use resetAll() instead. Only resets the Python bridge,
 * not the built-in MCP connections.
 */
export function resetBridge(): void {
  _manager = null
}