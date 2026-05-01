#!/usr/bin/env bun
/**
 * CiteAgent OpenCode Plugin — Installer
 *
 * Usage:
 *   bunx @ephremyuan/citeagent@latest install
 *   bunx @ephremyuan/citeagent@latest install --reset
 *   bunx @ephremyuan/citeagent@latest install --dry-run
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync, cpSync, readdirSync } from "fs"
import { join } from "path"
import { homedir } from "os"
import { execSync } from "child_process"

// ── Config ──────────────────────────────────────────────────────────────────

const OPENCODE_DIR = join(homedir(), ".config", "opencode")
const PLUGIN_NAME = "@ephremyuan/citeagent"
const CONFIG_FILENAME = "citeagent.json"
const ASSET_PREFIX = "citeagent-"

// ── Flags ───────────────────────────────────────────────────────────────────

const args = process.argv.slice(2)
const dryRun = args.includes("--dry-run")
const reset = args.includes("--reset")
const command = args.find((a) => !a.startsWith("--"))

if (command !== "install") {
  console.log("Usage: bunx @ephremyuan/citeagent@latest install [--reset] [--dry-run]")
  process.exit(1)
}

function log(msg: string) {
  if (dryRun) {
    console.log(`[DRY RUN] ${msg}`)
  } else {
    console.log(msg)
  }
}

// ── Step 1: Check prerequisites ─────────────────────────────────────────────

function checkPrerequisites(): boolean {
  let ok = true

  // Check Python3
  try {
    execSync("python3 --version", { stdio: "pipe" })
    console.log("✅ Python3 found")
  } catch {
    console.error("❌ Python3 not found. Install Python 3.12+ first.")
    ok = false
  }

  // Check citeagent module (the research agent runtime)
  let citeagentFound = false
  try {
    execSync('python3 -c "import citeagent"', { stdio: "pipe", timeout: 10000 })
    console.log("✅ Python citeagent package found")
    citeagentFound = true
  } catch {
    try {
      const venvPython = join(process.cwd(), ".venv", "bin", "python3")
      execSync(`"${venvPython}" -c "import citeagent"`, { stdio: "pipe", timeout: 10000 })
      console.log("✅ Python citeagent package found (project .venv)")
      citeagentFound = true
    } catch {
      // not found
    }
  }
  if (!citeagentFound) {
    console.error("❌ citeagent not found. Install with:")
    console.error("     uv tool install citeagent   (recommended, isolated global CLI)")
    ok = false
  }

  // Check citeindex module (the ingestion engine, required for cite ingest)
  let citeindexFound = false
  try {
    execSync("command -v citeindex", { stdio: "pipe", timeout: 10000, shell: "/bin/sh" })
    console.log("✅ Python citeindex package found (CLI on PATH)")
    citeindexFound = true
  } catch {
    try {
      execSync('python3 -c "import citeindex"', { stdio: "pipe", timeout: 10000 })
      console.log("✅ Python citeindex package found (system python)")
      citeindexFound = true
    } catch {
      try {
        const venvPython2 = join(process.cwd(), ".venv", "bin", "python3")
        execSync(`"${venvPython2}" -c "import citeindex"`, { stdio: "pipe", timeout: 10000 })
        console.log("✅ Python citeindex package found (project .venv)")
        citeindexFound = true
      } catch {
        // not found
      }
    }
  }
  if (!citeindexFound) {
    console.warn("⚠️  citeindex not found (needed for document ingestion). Install with:")
    console.warn("     uv tool install citeindex   (recommended, isolated global CLI)")
  }

  // Check tesseract (optional)
  try {
    execSync("tesseract --version", { stdio: "pipe" })
    console.log("✅ Tesseract OCR found (optional)")
  } catch {
    console.warn("⚠️  Tesseract not found (optional, needed for OCR): sudo apt install tesseract-ocr")
  }

  // Check ollama (optional)
  try {
    execSync("ollama --version", { stdio: "pipe" })
    console.log("✅ Ollama found (for LLM features)")
  } catch {
    console.warn("⚠️  Ollama not found (optional, for chat/generation): https://ollama.ai")
  }

  return ok
}

// ── Step 2: Add plugin to global opencode.json ──────────────────────────────

function addPluginToConfig(): void {
  const configPath = join(OPENCODE_DIR, "opencode.jsonc")

  let content = ""
  if (existsSync(configPath)) {
    content = readFileSync(configPath, "utf-8")

    // Strip JSONC comments while respecting strings, so that "//" inside a
    // string literal (e.g. "https://...") is not mistaken for a line comment.
    const stripJsonc = (src: string): string => {
      let out = ""
      let i = 0
      let inString = false
      let stringQuote = ""
      while (i < src.length) {
        const ch = src[i]
        const next = src[i + 1]
        if (inString) {
          out += ch
          if (ch === "\\" && i + 1 < src.length) {
            out += src[i + 1]
            i += 2
            continue
          }
          if (ch === stringQuote) {
            inString = false
          }
          i += 1
          continue
        }
        if (ch === '"' || ch === "'") {
          inString = true
          stringQuote = ch
          out += ch
          i += 1
          continue
        }
        if (ch === "/" && next === "/") {
          while (i < src.length && src[i] !== "\n") i += 1
          continue
        }
        if (ch === "/" && next === "*") {
          i += 2
          while (i < src.length && !(src[i] === "*" && src[i + 1] === "/")) i += 1
          i += 2
          continue
        }
        out += ch
        i += 1
      }
      return out
    }

    // Try strict JSON first; fall back to JSONC stripping.
    let parsed: any
    try {
      parsed = JSON.parse(content)
    } catch {
      try {
        parsed = JSON.parse(stripJsonc(content))
      } catch {
        console.warn(`⚠️  Could not parse ${configPath}. Add "${PLUGIN_NAME}" to the "plugin" array manually.`)
        return
      }
    }

    try {
      const config = parsed
      const plugins = (config.plugin ?? []) as string[]
      if (plugins.includes(PLUGIN_NAME)) {
        console.log(`ℹ️  Plugin "${PLUGIN_NAME}" already in ${configPath}`)
        return
      }
      plugins.push(PLUGIN_NAME)
      config.plugin = plugins
      if (!dryRun) {
        mkdirSync(OPENCODE_DIR, { recursive: true })
        writeFileSync(configPath, JSON.stringify(config, null, 2))
      }
      log(`✅ Added "${PLUGIN_NAME}" to ${configPath}`)
    } catch {
      console.warn(`⚠️  Could not parse ${configPath}. Add "${PLUGIN_NAME}" to the "plugin" array manually.`)
    }
  } else {
    // Create new config
    const config = {
      $schema: "https://opencode.ai/config.json",
      plugin: [PLUGIN_NAME],
    }
    if (!dryRun) {
      mkdirSync(OPENCODE_DIR, { recursive: true })
      writeFileSync(configPath, JSON.stringify(config, null, 2))
    }
    log(`✅ Created ${configPath} with plugin "${PLUGIN_NAME}"`)
  }
}

// ── Step 3: Deploy assets to global directories ────────────────────────────

function deployAssets(subdir: string, label: string): void {
  const globalDir = join(OPENCODE_DIR, subdir)
  // When built, this file lives at dist/bin/install.js, so assets/ is two levels up.
  // When run directly from bin/install.ts, it's one level up. Try both.
  let assetDir = join(import.meta.dir, "..", "..", "assets", subdir)
  if (!existsSync(assetDir)) {
    assetDir = join(import.meta.dir, "..", "assets", subdir)
  }

  if (!existsSync(assetDir)) {
    console.warn(`⚠️  No bundled assets found at ${assetDir}`)
    return
  }

  const files = readdirSync(assetDir).filter((f) => f.endsWith(".md"))

  if (!dryRun) {
    mkdirSync(globalDir, { recursive: true })
  }

  for (const file of files) {
    const src = join(assetDir, file)
    const dest = join(globalDir, `${ASSET_PREFIX}${file}`)
    if (!dryRun) {
      cpSync(src, dest)
    }
    log(`✅ Deployed ${label}: ${ASSET_PREFIX}${file}`)
  }
}

// ── Step 4: Generate agent config ───────────────────────────────────────────

function generateAgentConfig(): void {
  const configPath = join(OPENCODE_DIR, CONFIG_FILENAME)

  if (existsSync(configPath) && !reset) {
    console.log(`ℹ️  Agent config exists at ${configPath} (use --reset to overwrite)`)
    return
  }

  const config = {
    default_agent: "citeagent-researcher",
    agents: {
      "citeagent-researcher": {
        mode: "primary",
        description: "Academic research agent with citation-verified evidence chains and Merkle integrity",
        color: "#4a90d9",
        steps: 30,
      },
      "citeagent-verifier": {
        mode: "subagent",
        description: "Independent verification auditor — checks Merkle proofs, citation integrity, evidence validity",
        color: "#e74c3c",
        hidden: true,
      },
      "citeagent-explore-corpus": {
        mode: "subagent",
        description: "Fast read-only corpus explorer — search documents, browse trees, check citations",
        color: "#f39c12",
      },
      "citeagent-ingestor": {
        mode: "subagent",
        description: "Document ingestion agent — PDFs, URLs, media into the corpus with Merkle verification",
        color: "#2ecc71",
      },
      "citeagent-reviewer": {
        mode: "subagent",
        description: "Literature review agent — systematic search, gap identification, contradiction mapping",
        color: "#9b59b6",
      },
    },
    // Built-in MCP servers: websearch (Exa/Tavily), context7, grep_app.
    // Add entries to this array to disable specific MCP servers globally.
    // Example: ["websearch"] disables Exa/Tavily web search.
    disabled_mcps: [],
  }

  if (!dryRun) {
    writeFileSync(configPath, JSON.stringify(config, null, 2))
  }
  log(`✅ Generated agent config at ${configPath}`)
}

// ── Step 5: Print next steps ────────────────────────────────────────────────

function printNextSteps(): void {
  console.log("\n───────────────────────────────────────────────────")
  console.log("🔬 CiteAgent for OpenCode — Installation Complete")
  console.log("───────────────────────────────────────────────────")
  console.log("\nNext steps:")
  console.log("  1. Ensure Python citeindex is installed: uv tool install citeindex")
  console.log("  2. (Optional) Install OCR: sudo apt install tesseract-ocr")
  console.log("  3. (Optional) Install LLM backend: https://ollama.ai")
  console.log("  4. Restart OpenCode to activate the plugin")
  console.log("\nUninstall:")
  console.log("  - Remove plugin from ~/.config/opencode/opencode.jsonc")
  console.log(`  - rm ~/.config/opencode/${CONFIG_FILENAME}`)
  console.log("  - rm ~/.config/opencode/skills/citeagent-*.md")
  console.log("  - rm ~/.config/opencode/agents/citeagent-*.md")
  console.log("  - rm ~/.config/opencode/rules/citeagent-*.md")
  console.log("")
}

// ── Run ─────────────────────────────────────────────────────────────────────

console.log("\n🔬 CiteAgent OpenCode Plugin — Installer\n")

if (!checkPrerequisites()) {
  console.error("\n❌ Prerequisites not met. Fix the issues above and re-run.")
  process.exit(1)
}

console.log("")
addPluginToConfig()
deployAssets("skills", "skill")
deployAssets("agents", "agent")
deployAssets("rules", "rule")
generateAgentConfig()
printNextSteps()
