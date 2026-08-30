import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js";
import path from "path";
import os from "os";
import fs from "fs";
import { CiteAgentEngine } from "./engine/index.js";

export interface BuiltinMcpDef {
  key: string;
  name: string;
  url: string;
  requiredEnvVars?: string[];
  optionalEnvVars?: string[];
  headers?: () => Record<string, string>;
}

export const BUILTIN_MCPS: ReadonlyArray<BuiltinMcpDef> = [
  {
    key: "websearch",
    name: "Exa Web Search",
    url: "https://mcp.exa.ai/mcp?tools=web_search_exa",
    requiredEnvVars: ["EXA_API_KEY", "TAVILY_API_KEY"],
    headers: () => {
      const key = process.env.EXA_API_KEY || process.env.TAVILY_API_KEY || "";
      return key ? { "x-api-key": key } : ({} as Record<string, string>);
    },
  },
  {
    key: "context7",
    name: "Context7 Docs",
    url: "https://mcp.context7.com/mcp",
    optionalEnvVars: ["CONTEXT7_API_KEY"],
    headers: () => {
      const key = process.env.CONTEXT7_API_KEY || "";
      return key
        ? { Authorization: `Bearer ${key}` }
        : ({} as Record<string, string>);
    },
  },
  {
    key: "grep_app",
    name: "Grep.app Code Search",
    url: "https://mcp.grep.app",
  },
] as const;

interface CiteAgentConfig {
  disabled_mcps?: string[];
}

function loadConfig(): CiteAgentConfig {
  const configPath = path.join(
    os.homedir(),
    ".config",
    "opencode",
    "citeagent.json",
  );
  try {
    if (fs.existsSync(configPath)) {
      const raw = fs.readFileSync(configPath, "utf-8");
      return JSON.parse(raw) as CiteAgentConfig;
    }
  } catch (err) {
    console.warn("[CiteAgent] Failed to load config from", configPath, err);
  }
  return {};
}

interface ConnectedMcp {
  def: BuiltinMcpDef;
  client: Client;
  transport: SSEClientTransport;
}

export class CiteAgentMcpManager {
  private engine: CiteAgentEngine;
  readonly disabledMcps: Set<string>;
  private builtinConnections: Map<string, ConnectedMcp> = new Map();

  constructor(projectDir: string) {
    this.engine = new CiteAgentEngine(projectDir);
    const config = loadConfig();
    this.disabledMcps = new Set(config.disabled_mcps ?? []);
  }

  async connectAll(projectDir: string): Promise<void> {
    await this.engine.ensureReady();

    for (const def of BUILTIN_MCPS) {
      if (this.disabledMcps.has(def.key)) {
        console.debug(`[CiteAgent] Skipping disabled MCP: ${def.key}`);
        continue;
      }
      await this.connectBuiltin(def);
    }
  }

  private async connectBuiltin(def: BuiltinMcpDef): Promise<void> {
    if (def.requiredEnvVars?.length) {
      const hasRequired = def.requiredEnvVars.some(
        (envVar) => process.env[envVar],
      );
      if (!hasRequired) {
        console.warn(
          `[CiteAgent] Skipping ${def.key} (${def.name}): missing required env var(s) ` +
            def.requiredEnvVars.join(" or "),
        );
        return;
      }
    }

    try {
      const headers = def.headers?.() ?? {};
      const transport = new SSEClientTransport(new URL(def.url), {
        requestInit: Object.keys(headers).length > 0 ? { headers } : undefined,
      });

      const client = new Client({
        name: "opencode-citeagent",
        version: "0.3.8",
      });

      await client.connect(transport);
      this.builtinConnections.set(def.key, { def, client, transport });
      console.debug(
        `[CiteAgent] Connected built-in MCP: ${def.key} (${def.name})`,
      );
    } catch (err) {
      console.warn(
        `[CiteAgent] Failed to connect built-in MCP ${def.key} (${def.name}):`,
        err instanceof Error ? err.message : err,
      );
    }
  }

  async disconnectAll(): Promise<void> {
    for (const [, conn] of this.builtinConnections) {
      try {
        await conn.client.close();
      } catch {}
    }
    this.builtinConnections.clear();
  }

  async callTool(name: string, args: Record<string, unknown>): Promise<string> {
    if (name.startsWith("cite_")) {
      const engineName = name.replace(/^cite_/, "");
      return this.engine.callTool(engineName, args);
    }

    for (const [, conn] of this.builtinConnections) {
      try {
        const result = await conn.client.callTool({ name, arguments: args });
        return extractMcpText(result);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        if (
          msg.includes("not found") ||
          msg.includes("unknown tool") ||
          msg.includes("Method not found")
        ) {
          continue;
        }
        throw err;
      }
    }

    throw new Error(
      `CiteAgent: no MCP server recognized tool "${name}". ` +
        `Connected: engine + [${[...this.builtinConnections.keys()].join(", ")}]`,
    );
  }

  getEngine(): CiteAgentEngine {
    return this.engine;
  }
}

function extractMcpText(result: unknown): string {
  if (
    result &&
    typeof result === "object" &&
    "content" in result &&
    Array.isArray((result as any).content)
  ) {
    const content = (result as any).content;
    const textItem = content.find((c: any) => c.type === "text");
    if (textItem?.text) return textItem.text;
  }
  return JSON.stringify(result, null, 2);
}

let _manager: CiteAgentMcpManager | null = null;

export function getMcpManager(projectDir: string): CiteAgentMcpManager {
  if (!_manager) {
    _manager = new CiteAgentMcpManager(projectDir);
  }
  return _manager;
}

export function resetAll(): void {
  _manager = null;
}
