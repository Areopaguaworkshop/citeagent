# @ephremyuan/citeagent

**A local, evidence-first academic agent layer for Codex and OpenCode.**

CiteAgent v0.5.0 is not a general-purpose OpenCode plugin. It gives coding-agent hosts an academic-paper workspace: approved-source retrieval, exact-passage citation checks, Merkle integrity verification, and explicit research checkpoints. It plays the academic role that an agent-layer distribution plays for software work.

The scholar remains responsible for the research question, source approval, interpretation, authorship, and publication decisions. CiteAgent never treats a search result or model memory as paper evidence.

## Install

### OpenCode

```bash
bunx @ephremyuan/citeagent@latest install
```

The installer adds the OpenCode integration, academic agents, skills, rules, and SafeHarness hooks. It does not upload or copy your corpus.

### Codex and other MCP clients

Run the local MCP server:

```bash
bunx @ephremyuan/citeagent mcp-server
```

For Codex, add this to `~/.codex/config.toml`:

```toml
[mcp_servers.citeagent]
command = "bunx"
args = ["@ephremyuan/citeagent", "mcp-server"]
env = { CITEAGENT_CORPUS_ROOT = "./corpus" }
enabled = true
```

## Academic workflow

1. Create a paper workspace and record its question.
2. Approve the local corpus source IDs the paper may use.
3. Search and retrieve only within that approved scope.
4. Check exact passages, hashes, Merkle proofs, and bibliography fields.
5. Advance `research → outline → draft → review` through explicit `proceed`, `refine`, or `abort` checkpoints.

The workflow is a local checkpoint/state machine, not an autonomous paper writer. Codex or OpenCode may prepare prose after the scholar approves a checkpoint; CiteAgent does not claim authorship or publication authority. Workspace and session data are metadata-only local files; source text remains in the corpus.

```text
paper_create    paper_id="my-paper" title="…" question="…"
paper_add_source paper_id="my-paper" source_id="local-source-id" role="primary"
paper_use       paper_id="my-paper"
workflow_start  topic="…"
workflow_resume workflow_id="…" choice="proceed"
```

`workflow_start` requires an active paper, an approved source that still exists
in the corpus, and at least one scoped result with a verified text hash and
Merkle proof. The workflow begins at `research`; each `proceed` advances one
stage, `refine` repeats the current checkpoint, and `abort` deletes it. Records
expire after one hour. Use `paper_status`, `paper_audit`, `state_wake_up`,
`state_snapshot`, `status`, and `doctor` for local operational metadata.

## What is included

- **41 MCP tools**: paper scope, BM25/regex retrieval, exact passage lookup, Merkle and bibliographic checks, CSL rendering, ingestion, memory, audit, state, workflow, `status`, and `doctor`.
- **OpenCode academic agents**: researcher, verifier, corpus explorer, ingestor, and reviewer.
- **Local-first controls**: approved-source scoping, fail-closed workflow gates, structured errors, and diagnostics that do not return corpus text.

All tools except the two optional `citeindex` ingestion integrations run natively in TypeScript. Install `citeindex` only if you need to ingest PDFs, URLs, or media:

```bash
uv tool install citeindex
```

## Privacy and release boundary

The npm package contains code and public agent assets only. It excludes corpora, paper artifacts, local session/workflow metadata, logs, models, credentials, and private paths. See the repository's [privacy policy](https://github.com/Areopaguaworkshop/citeagent/blob/master/PRIVACY.md).

## License

MIT
