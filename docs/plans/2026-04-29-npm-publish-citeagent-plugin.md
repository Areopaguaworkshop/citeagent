# Publish @areopaguaworkshop/citeagent to npm — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Publish the CiteAgent OpenCode plugin to npm as `@areopaguaworkshop/citeagent` so users can install it globally with `bunx @areopaguaworkshop/citeagent@latest install`.

**Architecture:** Restructure the existing `plugins/opencode-citeagent/` into a standalone npm-publishable package. Add an install CLI (`bin/install.ts`) that deploys skills, agents, rules, and agent config to `~/.config/opencode/`, and registers the plugin in the global `opencode.json`. Fix the hardcoded Python path to auto-detect. Bundle all OpenCode assets into the npm package.

**Tech Stack:** TypeScript, Bun, npm registry, @opencode-ai/plugin SDK

---

## Design Decisions (pre-approved)

| Decision | Choice |
|----------|-------|
| npm package name | `@areopaguaworkshop/citeagent` (unscoped `citeagent` is taken by citeagentai) |
| Python detection | Auto-detect: `CITEAGENT_PYTHON` env → `.venv/bin/python3` → system `python3`. Fail with clear error if `citeindex` module not importable |
| Python prerequisite | Check + instruct. If `citeindex` not importable, print `pip install citeindex` and exit |
| Install UX | `bunx @areopaguaworkshop/citeagent@latest install` (matches oh-my-opencode-slim pattern) |
| Asset deployment | Skills/agents/rules copied to `~/.config/opencode/{skills,agents,rules}/` with `citeagent-` prefix |
| Agent config | Generated at `~/.config/opencode/citeagent.json` |

---

### Task 1: Fix hardcoded Python path in mcp-bridge.ts

**Files:**
- Modify: `plugins/opencode-citeagent/src/mcp-bridge.ts:28-29`

**Step 1: Replace hardcoded path with auto-detect logic**

Replace the constructor body:

```typescript
// OLD:
this.pythonCmd =
  process.env.CITEAGENT_PYTHON ||
  "/home/ajiap/.rye/py/cpython@3.12.8/bin/python3.12"

// NEW:
this.pythonCmd =
  process.env.CITEAGENT_PYTHON ||
  CiteAgentBridge.findPython(projectDir)
```

**Step 2: Add the static findPython method to the class**

Add this static method before the `connect()` method:

```typescript
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
```

**Step 3: Add missing imports**

Add `os` and `execSync` to the imports at top of file:

```typescript
import os from "os"
import { execSync } from "child_process"
```

**Step 4: Build and verify**

Run: `cd plugins/opencode-citeagent && bun run build`
Expected: Build succeeds with no errors

**Step 5: Commit**

```bash
git add plugins/opencode-citeagent/src/mcp-bridge.ts
git commit -m "fix: replace hardcoded Python path with auto-detect logic"
```

---

### Task 2: Rename package and update package.json

**Files:**
- Modify: `plugins/opencode-citeagent/package.json`

**Step 1: Update package.json**

Change the package name, add `bin`, `files`, `keywords`, `repository`, and update version:

```json
{
  "name": "@areopaguaworkshop/citeagent",
  "version": "0.3.0",
  "type": "module",
  "main": "dist/index.js",
  "bin": {
    "citeagent-install": "dist/bin/install.js"
  },
  "files": [
    "dist/",
    "assets/"
  ],
  "scripts": {
    "build": "bun build src/index.ts --outdir=dist --target=bun --format=esm",
    "build:bin": "bun build bin/install.ts --outfile=dist/bin/install.js --target=bun --format=esm",
    "build:all": "bun run build && bun run build:bin",
    "prepublishOnly": "bun run build:all"
  },
  "dependencies": {
    "@opencode-ai/plugin": "1.14.28",
    "@modelcontextprotocol/sdk": "^1.12.0",
    "zod": "^3.23.0"
  },
  "keywords": [
    "opencode",
    "opencode-plugin",
    "academic",
    "citation",
    "merkle",
    "research",
    "citeagent",
    "ai",
    "agents"
  ],
  "repository": {
    "type": "git",
    "url": "git+https://github.com/areopaguaworkshop/citation.git",
    "directory": "plugins/opencode-citeagent"
  },
  "license": "MIT",
  "description": "OpenCode plugin for CiteAgent — AI research knowledge infrastructure with Merkle-verified retrieval and citation-indexed search"
}
```

**Step 2: Verify build works**

Run: `cd plugins/opencode-citeagent && bun run build`
Expected: Build succeeds

**Step 3: Commit**

```bash
git add plugins/opencode-citeagent/package.json
git commit -m "chore: rename package to @areopaguaworkshop/citeagent for npm publish"
```

---

### Task 3: Bundle OpenCode assets into the plugin

**Files:**
- Create: `plugins/opencode-citeagent/assets/skills/ingest-document.md`
- Create: `plugins/opencode-citeagent/assets/skills/verify-evidence.md`
- Create: `plugins/opencode-citeagent/assets/skills/literature-review.md`
- Create: `plugins/opencode-citeagent/assets/agents/researcher.md`
- Create: `plugins/opencode-citeagent/assets/agents/verifier.md`
- Create: `plugins/opencode-citeagent/assets/agents/explore-corpus.md`
- Create: `plugins/opencode-citeagent/assets/agents/ingestor.md`
- Create: `plugins/opencode-citeagent/assets/agents/reviewer.md`
- Create: `plugins/opencode-citeagent/assets/rules/academic-integrity.md`
- Create: `plugins/opencode-citeagent/assets/rules/citation-format.md`

**Step 1: Create assets directory and copy files**

```bash
cd plugins/opencode-citeagent
mkdir -p assets/skills assets/agents assets/rules
```

**Step 2: Copy skills from .opencode/skills/ to assets/skills/**

Copy each file from the project `.opencode/skills/` to `assets/skills/`:
- `ingest-document.md` — content from `.opencode/skills/ingest-document.md`
- `verify-evidence.md` — content from `.opencode/skills/verify-evidence.md`
- `literature-review.md` — content from `.opencode/skills/literature-review.md`

**Step 3: Copy agents from .opencode/agents/ to assets/agents/**

Copy each file from `.opencode/agents/` to `assets/agents/`:
- `researcher.md`
- `verifier.md`
- `explore-corpus.md`
- `ingestor.md`
- `reviewer.md`

**Step 4: Copy rules from .opencode/rules/ to assets/rules/**

- `academic-integrity.md`
- `citation-format.md`

**Step 5: Commit**

```bash
git add plugins/opencode-citeagent/assets/
git commit -m "feat: bundle OpenCode skills, agents, and rules as npm package assets"
```

---

### Task 4: Create the install CLI script

**Files:**
- Create: `plugins/opencode-citeagent/bin/install.ts`

**Step 1: Write the install script**

```typescript
#!/usr/bin/env bun
/**
 * CiteAgent OpenCode Plugin — Installer
 *
 * Usage:
 *   bunx @areopaguaworkshop/citeagent@latest install
 *   bunx @areopaguaworkshop/citeagent@latest install --reset
 *   bunx @areopaguaworkshop/citeagent@latest install --dry-run
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync, cpSync, readdirSync } from "fs"
import { join } from "path"
import { homedir } from "os"
import { execSync } from "child_process"

// ── Config ──────────────────────────────────────────────────────────────────

const OPENCODE_DIR = join(homedir(), ".config", "opencode")
const PLUGIN_NAME = "@areopaguaworkshop/citeagent"
const CONFIG_FILENAME = "citeagent.json"
const ASSET_PREFIX = "citeagent-"

// ── Flags ───────────────────────────────────────────────────────────────────

const args = process.argv.slice(2)
const dryRun = args.includes("--dry-run")
const reset = args.includes("--reset")
const command = args.find((a) => !a.startsWith("--"))

if (command !== "install") {
  console.log("Usage: bunx @areopaguaworkshop/citeagent@latest install [--reset] [--dry-run]")
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

  // Check citeindex module
  try {
    execSync('python3 -c "import citeindex"', { stdio: "pipe", timeout: 10000 })
    console.log("✅ Python citeindex package found")
  } catch {
    console.error("❌ citeindex not importable. Install with: pip install citeindex")
    ok = false
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
    // Strip comments for JSON parsing (simple // comment removal)
    const jsonStr = content
      .split("\n")
      .map((line) => line.replace(/\/\/.*$/, ""))
      .join("\n")

    try {
      const config = JSON.parse(jsonStr)
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
  const assetDir = join(import.meta.dir, "..", "assets", subdir)

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
  console.log("  1. Ensure Python citeindex is installed: pip install citeindex")
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
```

**Step 2: Verify the script parses without errors**

Run: `cd plugins/opencode-citeagent && bun run build:bin`
Expected: Build succeeds, producing `dist/bin/install.js`

**Step 3: Commit**

```bash
git add plugins/opencode-citeagent/bin/
git commit -m "feat: add install CLI for global deployment via bunx"
```

---

### Task 5: Add .npmignore to exclude unnecessary files from npm package

**Files:**
- Create: `plugins/opencode-citeagent/.npmignore`

**Step 1: Create .npmignore**

```
src/
bin/
node_modules/
bun.lock
tsconfig.json
.gitignore
```

We want to ship `dist/` (built plugin) and `assets/` (bundled configs), but not the source, the bin source, or lock files.

**Step 2: Commit**

```bash
git add plugins/opencode-citeagent/.npmignore
git commit -m "chore: add .npmignore for clean npm package"
```

---

### Task 6: Add README.md for the npm package

**Files:**
- Create: `plugins/opencode-citeagent/README.md`

**Step 1: Write the README**

```markdown
# @areopaguaworkshop/citeagent

OpenCode plugin for CiteAgent — AI research knowledge infrastructure with Merkle-verified retrieval, citation-indexed search, and trace-bound chat.

## Install

```bash
bunx @areopaguaworkshop/citeagent@latest install
```

The installer automatically:
- Adds the plugin to `~/.config/opencode/opencode.jsonc`
- Deploys skills to `~/.config/opencode/skills/`
- Deploys agent configs to `~/.config/opencode/agents/`
- Deploys rules to `~/.config/opencode/rules/`
- Generates agent model mappings in `~/.config/opencode/citeagent.json`

### Options

| Flag | Description |
|------|-------------|
| `--reset` | Overwrite existing configuration |
| `--dry-run` | Simulate install without writing files |

## Prerequisites

```bash
# Required: Python + citeindex
pip install citeindex

# Optional: OCR support
sudo apt install tesseract-ocr

# Optional: LLM backend (for chat/generation)
# https://ollama.ai
```

## Uninstall

1. Remove `"@areopaguaworkshop/citeagent"` from `~/.config/opencode/opencode.jsonc` `plugin` array
2. Remove config: `rm ~/.config/opencode/citeagent.json`
3. Remove assets: `rm ~/.config/opencode/skills/citeagent-*.md ~/.config/opencode/agents/citeagent-*.md ~/.config/opencode/rules/citeagent-*.md`

## Agents

| Agent | Mode | Description |
|-------|------|-------------|
| `citeagent-researcher` | primary | Academic research with citation-verified evidence |
| `citeagent-verifier` | subagent (hidden) | Independent Merkle proof audit |
| `citeagent-explore-corpus` | subagent | Fast corpus search and browsing |
| `citeagent-ingestor` | subagent | Document ingestion (PDF, URL, media) |
| `citeagent-reviewer` | subagent | Systematic literature review |

## Tools

The plugin provides 25+ tools via MCP bridge to the Python backend:

- `cite_search` — BM25 full-text search
- `cite_verify` — Merkle proof verification
- `cite_render` — CSL citation rendering (Chicago, APA, MLA...)
- `cite_ingest` — Document ingestion with Merkle hashing
- `cite_tree` / `cite_tree_traverse` — PageIndex document tree
- `cite_argument_query` — Argument graph (claims, contradictions)
- `cite_memory_*` — 4-tier persistent memory (working → episodic → long_term → corpus)
- And more (see source)

## Architecture

```
User question
     │
     ▼
citeagent-researcher (OpenCode agent)
     │
     ├── cite_search ──→ Retrieval agent (Python/MCP)
     ├── cite_verify ──→ Integrity agent (Python/MCP)
     ├── cite_ingest ──→ Ingestion agent (Python/MCP)
     │
     ├── @citeagent-explore-corpus (OpenCode subagent)
     └── @citeagent-verifier (OpenCode subagent)
```

The plugin spawns `python3 -m citeindex.mcp_server` as a subprocess and communicates via MCP over stdio.

## License

MIT
```

**Step 2: Commit**

```bash
git add plugins/opencode-citeagent/README.md
git commit -m "docs: add README for npm package"
```

---

### Task 7: Update project opencode.jsonc to use npm package name

**Files:**
- Modify: `.opencode/opencode.jsonc`

**Step 1: Switch plugin reference from local path to npm name**

```jsonc
// OLD:
"plugin": ["./plugins/opencode-citeagent"],

// NEW:
"plugin": ["@areopaguaworkshop/citeagent"],
```

**Step 2: Commit**

```bash
git add .opencode/opencode.jsonc
git commit -m "chore: switch plugin reference to npm package @areopaguaworkshop/citeagent"
```

---

### Task 8: Build and dry-run publish

**Step 1: Install dependencies and build**

```bash
cd plugins/opencode-citeagent
bun install
bun run build:all
```

Expected: `dist/index.js` and `dist/bin/install.js` created with no errors

**Step 2: Verify package contents**

```bash
npm publish --dry-run
```

Expected: Output shows `dist/`, `assets/`, `README.md`, `package.json` in the tarball. No `src/`, `node_modules/`, or `bin/` source files.

**Step 3: Commit (if any fixes needed from dry-run)**

Only if changes were needed to fix the dry-run.

---

### Task 9: Publish to npm

**Step 1: Login to npm (if not already)**

```bash
npm login
```

**Important:** The user must be a member of the `areopaguaworkshop` org on npm, or the org must be created first.

**Step 2: Create the org on npm (if not already)**

If `areopaguaworkshop` doesn't exist on npm:
```bash
npm org create areopaguaworkshop
```

**Step 3: Publish**

```bash
cd plugins/opencode-citeagent
npm publish --access public
```

Expected: Package appears at `https://www.npmjs.com/package/@areopaguaworkshop/citeagent`

**Step 4: Verify install works**

On a fresh machine (or after clearing cache):

```bash
bunx @areopaguaworkshop/citeagent@latest install --dry-run
```

Expected: Dry-run shows all deployment steps without writing files.

---

### Task 10: Tag release and update project docs

**Step 1: Tag the release**

```bash
git tag -a @areopaguaworkshop/citeagent@0.3.0 -m "Publish @areopaguaworkshop/citeagent v0.3.0 to npm"
git push origin @areopaguaworkshop/citeagent@0.3.0
```

**Step 2: Update project README.md**

Add installation section mentioning the npm package. In the **Quick Start** section, add:

```markdown
### OpenCode Plugin (Global)

```bash
# Install the OpenCode plugin globally
bunx @areopaguaworkshop/citeagent@latest install

# Prerequisites
pip install citeindex
```
```

**Step 3: Commit and push**

```bash
git add README.md
git commit -m "docs: add npm install instructions for @areopaguaworkshop/citeagent"
git push origin main
```

---

## Task Summary

| # | Task | Type | Complexity |
|---|------|------|-----------|
| 1 | Fix hardcoded Python path | Bug fix | Small |
| 2 | Rename package + update package.json | Config | Small |
| 3 | Bundle assets into plugin | File copy | Medium |
| 4 | Create install CLI | New code | Large |
| 5 | Add .npmignore | Config | Trivial |
| 6 | Add README.md | Docs | Medium |
| 7 | Update opencode.jsonc | Config | Trivial |
| 8 | Build + dry-run publish | Verification | Small |
| 9 | Publish to npm | Deploy | Small (manual) |
| 10 | Tag release + update docs | Release | Small |

**Critical path:** Tasks 1→2→3→4→5→6→7 must be done sequentially before Task 8.
Task 9 requires npm login/org setup (manual step).