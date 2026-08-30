import path from "path";
import fs from "fs";
import { CorpusLoader } from "./corpus-loader.js";
import { SearchEngine } from "./search.js";
import { MerkleEngine } from "./merkle.js";
import { CslEngine } from "./csl.js";
import { MemoryStoreEngine } from "./memory-store.js";
import { AuditStoreEngine } from "./audit-store.js";
import { CryptoEngine } from "./crypto-engine.js";
import { ArgumentGraphEngine } from "./argument-graph.js";
import { PageIndexEngine } from "./pageindex.js";
import { safePath } from "./safe-path.js";
import { verifyBibliographicRecord } from "./bibliographic-verify.js";
import { ResearchState } from "./research-state.js";
import { ResearchWorkflow } from "./workflow.js";
import { WorkspaceStore, type SourceRole } from "./workspaces.js";
import { SafeHarness } from "../safeharness.js";
import type { CorpusState } from "./types.js";

export class CiteAgentEngine {
  private corpusRoot: string;
  private corpusState: CorpusState | null = null;
  private initPromise: Promise<void> | null = null;
  private corpusLoader: CorpusLoader | null = null;
  private searchEngine: SearchEngine | null = null;
  private merkleEngine: MerkleEngine | null = null;
  private cslEngine: CslEngine | null = null;
  private memoryStore: MemoryStoreEngine | null = null;
  private auditStore: AuditStoreEngine | null = null;
  private cryptoEngine: CryptoEngine | null = null;
  private argGraph: ArgumentGraphEngine | null = null;
  private pageIndex: PageIndexEngine | null = null;
  private safeHarness = new SafeHarness();
  private readonly stateRoot: string;
  private readonly researchState: ResearchState;
  private readonly workflow: ResearchWorkflow;
  private readonly workspaces: WorkspaceStore;

  constructor(projectDir: string) {
    this.corpusRoot =
      process.env.CITEAGENT_CORPUS_ROOT || path.join(projectDir, "corpus");
    this.stateRoot =
      process.env.CITEAGENT_STATE_ROOT || path.join(projectDir, ".citeagent");
    this.researchState = new ResearchState(this.stateRoot);
    this.workflow = new ResearchWorkflow(this.stateRoot);
    this.workspaces = new WorkspaceStore(this.stateRoot);
  }

  async ensureReady(): Promise<void> {
    if (this.corpusState) return;
    if (this.initPromise) return this.initPromise;
    this.initPromise = this.initialize();
    await this.initPromise;
  }

  private async initialize(): Promise<void> {
    this.corpusLoader = new CorpusLoader(this.corpusRoot);
    this.corpusState = await this.corpusLoader.load();
    this.searchEngine = new SearchEngine(this.corpusRoot);
    await this.searchEngine.init();
    this.merkleEngine = new MerkleEngine();
    this.cslEngine = new CslEngine(this.corpusState.cslRegistry);
    this.memoryStore = new MemoryStoreEngine(this.corpusRoot);
    this.auditStore = new AuditStoreEngine(this.corpusRoot);
    this.cryptoEngine = new CryptoEngine(this.corpusRoot);
    this.argGraph = new ArgumentGraphEngine(this.corpusRoot, this.corpusState);
    this.pageIndex = new PageIndexEngine(this.corpusRoot);
  }

  async callTool(name: string, args: Record<string, unknown>): Promise<string> {
    try {
      if (name !== "status" && name !== "doctor") await this.ensureReady();
      switch (name) {
        case "search_documents":
          return JSON.stringify(await this.workspaces.filterSearchResults(
            this.searchEngine!.search(
              String(args.query || ""),
              Number(args.limit || 10),
            ),
          ));
        case "search_claims":
          return JSON.stringify(await this.filterScopedRecords(await this.argGraph!.queryClaims(args)));
        case "search_memory":
          return JSON.stringify(
            await this.memoryStore!.search(
              String(args.query || ""),
              args.thread_id as string | undefined,
              Number(args.limit || 10),
            ),
          );
        case "regex_search":
          return JSON.stringify(
            await this.workspaces.filterSearchResults(this.searchEngine!.regexSearch(
              String(args.pattern || ""),
              args.source_id as string | undefined,
              Number(args.limit || 10),
              Number(args.context_chars || 120),
            )),
          );
        case "tantivy_search":
          return JSON.stringify(await this.workspaces.filterSearchResults(
            this.searchEngine!.search(
              String(args.query || ""),
              Number(args.limit || 10),
            ),
          ));

        case "index_document":
          return JSON.stringify(await this.ingestDocument(args));
        case "index_claim":
          return JSON.stringify(await this.argGraph!.indexClaim(args));
        case "delete_document":
          await this.workspaces.assertSourceAllowed(String(args.source_id || ""));
          return JSON.stringify(
            this.deleteDocument(String(args.source_id || "")),
          );
        case "tantivy_index":
          return JSON.stringify(await this.ingestDocument(args));

        case "ag_query_claims":
          return JSON.stringify(await this.filterScopedRecords(await this.argGraph!.queryClaims(args)));
        case "ag_query_contradictions":
          return JSON.stringify(await this.filterScopedRecords(await this.argGraph!.queryContradictions(args)));

        case "merkle_compute":
          return JSON.stringify(
            await this.merkleEngine!.compute(String(args.payload || "")),
          );
        case "merkle_verify": {
          const node = args.node_id
            ? this.corpusState!.nodes.find(
                (candidate) => candidate.node_id === args.node_id,
              )
            : undefined;
          if (args.node_id && !node) {
            return JSON.stringify({
              valid: false,
              error: `Node ${args.node_id} not found`,
            });
          }
          const root = node
            ? this.corpusState!.merkleRegistry.get(node.source_id)?.root || ""
            : String(args.root || "");
          return JSON.stringify(
            this.merkleEngine!.verifyWithRegistry(
              node?.sha256 || String(args.node_hash || ""),
              (args.proof as string[]) || [],
              root,
              this.corpusState!.merkleRegistry,
            ),
          );
        }
        case "node_lookup": {
          const node = this.corpusState!.nodes.find((candidate) => candidate.node_id === String(args.node_id || ""));
          if (node) await this.workspaces.assertSourceAllowed(node.source_id);
          return JSON.stringify(node || null);
        }

        case "csl_render":
          return JSON.stringify(
            await this.cslEngine!.render(
              String(args.citation_key || ""),
              String(args.style || "apa"),
            ),
          );
        case "bibliographic_verify": {
          const citationKey = String(args.citation_key || "");
          return JSON.stringify(
            await verifyBibliographicRecord(
              this.corpusState!.cslRegistry.get(citationKey),
              citationKey,
            ),
          );
        }

        case "tree_load":
          await this.workspaces.assertSourceAllowed(String(args.source_id || ""));
          return JSON.stringify(
            await this.pageIndex!.loadTree(
              String(args.source_id || ""),
              args.depth as number | undefined,
            ),
          );
        case "tree_traverse":
          await this.workspaces.assertSourceAllowed(String(args.source_id || ""));
          return JSON.stringify(
            await this.pageIndex!.traverseTree(
              String(args.source_id || ""),
              args.path as string | undefined,
            ),
          );

        case "memory_save":
          return JSON.stringify(
            await this.memoryStore!.save(
              String(
                (args.metadata as Record<string, unknown> | undefined)
                  ?.thread_id ||
                  args.thread ||
                  "default",
              ),
              String(args.content || ""),
              "",
              (args.tags as string[]) || [],
            ),
          );
        case "memory_store_tier":
          return JSON.stringify(
            await this.memoryStore!.storeTier({
              content: String(args.content || ""),
              tier: String(args.tier || "episodic"),
              key: args.key as string | undefined,
              tags: args.tags as string[] | undefined,
              thread_id: args.thread_id as string | undefined,
              source_ids: args.source_ids as string[] | undefined,
            }),
          );
        case "memory_retrieve_tier":
          return JSON.stringify(
            await this.memoryStore!.retrieveTier(
              String(args.query || ""),
              args.tier as string | undefined,
              Number(args.limit || 10),
            ),
          );
        case "memory_consolidate":
          return JSON.stringify(
            await this.memoryStore!.consolidate(
              args.thread_id as string | undefined,
            ),
          );

        case "audit_save":
          return JSON.stringify(
            await this.auditStore!.save(
              String(args.audit_id || ""),
              String(args.verdict || ""),
              args.reasoning as string | undefined,
              args.evidence_hashes as string[] | undefined,
              args.query as string | undefined,
            ),
          );
        case "audit_retrieve":
          return JSON.stringify(
            await this.auditStore!.retrieve(String(args.audit_id || "")),
          );

        case "crypto_sign":
          return JSON.stringify(
            await this.cryptoEngine!.sign(
              String(args.message || ""),
              String(args.session_id || ""),
            ),
          );
        case "crypto_verify":
          return JSON.stringify(
            await this.cryptoEngine!.verify(
              String(args.message || ""),
              String(args.signature || ""),
              String(args.session_id || ""),
            ),
          );
        case "crypto_audit_trail":
          return JSON.stringify(
            await this.cryptoEngine!.getAuditTrail(
              String(args.session_id || ""),
            ),
          );

        case "safeharness_check":
          return JSON.stringify(
            this.safeHarness.preCheck(
              String(args.tool_name || ""),
              (args.args as Record<string, unknown>) || {},
            ),
          );
        case "safeharness_sanitize":
          return JSON.stringify(
            this.safeHarness.sanitizeInput(
              String(args.tool_name || ""),
              (args.input as Record<string, unknown>) || {},
            ),
          );

        case "status":
          {
            const corpusRootExists = fs.existsSync(this.corpusRoot);
          return JSON.stringify({
            status: this.corpusState ? "ok" : corpusRootExists ? "not_initialized" : "degraded",
            next_action: this.corpusState
              ? "Ready for research."
              : corpusRootExists
              ? "Corpus is configured; run a corpus tool to initialize it."
              : "Set CITEAGENT_CORPUS_ROOT to an indexed corpus, then retry.",
            corpus: {
              ready: Boolean(this.corpusState),
              document_count: this.corpusState?.sourceIds.size ?? 0,
              node_count: this.corpusState?.nodes.length ?? 0,
              merkle_root_count: this.corpusState?.merkleRegistry.size ?? 0,
            },
            workspace: await this.workspaces.status(),
            research_state: await this.researchState.snapshot(),
            workflow: await this.workflow.status(),
          });
          }
        case "doctor":
          {
            const corpusRootExists = fs.existsSync(this.corpusRoot);
          return JSON.stringify({
            status: corpusRootExists ? "ok" : "degraded",
            checks: {
              corpus_root_exists: corpusRootExists,
              citeindex_available: Boolean(Bun.which("citeindex")),
              local_state_configured: Boolean(process.env.CITEAGENT_STATE_ROOT),
            },
            next_action: !corpusRootExists
              ? "Set CITEAGENT_CORPUS_ROOT to an indexed corpus."
              : Bun.which("citeindex")
              ? "Ready for research and ingestion."
              : "Install citeindex to enable document ingestion.",
          });
          }

        case "paper_create":
          return JSON.stringify(await this.workspaces.create(
            String(args.paper_id || ""),
            String(args.title || ""),
            String(args.question || ""),
          ));
        case "paper_add_source":
          if (!this.corpusState!.sourceIds.has(String(args.source_id || ""))) {
            return JSON.stringify(this.errorResponse(
              "SOURCE_NOT_FOUND",
              `Source ${String(args.source_id || "")} is not in this corpus.`,
              "Ingest the source before approving it for a paper.",
            ));
          }
          return JSON.stringify(await this.workspaces.addSource(
            String(args.paper_id || ""),
            String(args.source_id || ""),
            String(args.role || "unknown") as SourceRole,
          ));
        case "paper_use":
          return JSON.stringify(await this.workspaces.use(String(args.paper_id || "")));
        case "paper_status":
          return JSON.stringify(await this.workspaces.status());
        case "paper_audit": {
          const audit = await this.workspaces.audit(args.paper_id as string | undefined);
          const paper = args.paper_id
            ? await this.workspaces.get(String(args.paper_id))
            : await this.workspaces.active();
          const missing_source_ids = paper?.sources
            .filter((source) => !this.corpusState!.sourceIds.has(source.source_id))
            .map((source) => source.source_id) ?? [];
          return JSON.stringify({
            ...audit,
            status: missing_source_ids.length ? "incomplete" : audit.status,
            missing_source_ids,
          });
        }

        case "state_wake_up":
          return JSON.stringify(await this.researchState.wakeUp(Number(args.limit || 3)));
        case "state_snapshot":
          return JSON.stringify(await this.researchState.snapshot());
        case "state_record_session":
          return JSON.stringify(await this.researchState.record(
            String(args.session_id || ""),
            (args.topics as string[]) || [],
            (args.source_ids as string[]) || [],
            (args.open_questions as string[]) || [],
          ));

        case "workflow_start": {
          const active = await this.workspaces.active();
          if (!active) {
            return JSON.stringify(this.errorResponse(
              "PAPER_SCOPE_REQUIRED",
              "Activate a paper workspace before starting a workflow.",
              "Create a paper, approve its sources, then activate it.",
            ));
          }
          const missing = active.sources.filter((source) => !this.corpusState!.sourceIds.has(source.source_id));
          if (!active.sources.length || missing.length) {
            return JSON.stringify(this.errorResponse(
              "PAPER_AUDIT_FAILED",
              "The active paper has no usable approved sources.",
              "Approve at least one corpus source before starting a workflow.",
            ));
          }
          const evidence = await this.workspaces.filterSearchResults(
            this.searchEngine!.search(String(args.topic || ""), Number(args.limit || 20)),
          );
          const verified = [];
          for (const item of evidence.results) {
            const node = this.corpusState!.nodes.find((candidate) => candidate.node_id === String(item.node_id));
            if (node && await this.verifyNode(node)) verified.push(item);
          }
          return JSON.stringify(await this.workflow.start(String(args.topic || ""), verified.length));
        }
        case "workflow_resume":
          return JSON.stringify(await this.workflow.resume(
            String(args.workflow_id || ""),
            String(args.choice || "proceed") as "proceed" | "refine" | "abort",
          ));

        default:
          throw new Error(`CiteAgentEngine: unknown tool "${name}"`);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return JSON.stringify(this.errorResponse("TOOL_FAILED", message, "Check the tool arguments and current CiteAgent status."));
    }
  }

  private errorResponse(error_code: string, message: string, next_action: string) {
    return { status: "error", error_code, message, next_action, error: message };
  }

  private async filterScopedRecords(value: unknown): Promise<unknown> {
    if (!Array.isArray(value)) return value;
    const active = await this.workspaces.active();
    if (!active) return value;
    const allowed = new Set(active.sources.map((source) => source.source_id));
    return value.filter((item) => typeof item === "object" && item !== null && allowed.has(String((item as Record<string, unknown>).source_id ?? "")));
  }

  private async verifyNode(node: CorpusState["nodes"][number]) {
    const tree = this.corpusState!.merkleRegistry.get(node.source_id);
    if (!tree?.levels?.length || !tree.root) return false;
    if (node.sha256 !== await this.merkleEngine!.hashPayload(node.text)) return false;
    let index = tree.levels[0]?.indexOf(node.sha256) ?? -1;
    if (index < 0) return false;
    const proof: string[] = [];
    for (let levelIndex = 0; levelIndex < tree.levels.length - 1; levelIndex += 1) {
      const level = tree.levels[levelIndex];
      const siblingIndex = index % 2 === 0 ? index + 1 : index - 1;
      const sibling = level[siblingIndex] ?? level[index];
      if (!sibling) return false;
      proof.push(index % 2 === 0 ? sibling : `left:${sibling}`);
      index = Math.floor(index / 2);
    }
    return this.merkleEngine!.verifyWithRegistry(node.sha256, proof, tree.root, this.corpusState!.merkleRegistry).valid;
  }

  private async ingestDocument(
    args: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    const filePath = String(args.path || "");
    if (!filePath)
      return {
        source_id: "",
        status: "error",
        error_message: "path is required",
      };

    try {
      const { execFileSync } = await import("child_process");
      execFileSync(
        "citeindex",
        ["ingest", filePath, "--corpus-root", this.corpusRoot],
        {
          timeout: 30000,
          stdio: "pipe",
        },
      );
      this.corpusState = await this.corpusLoader!.reload();
      this.searchEngine = new SearchEngine(this.corpusRoot);
      await this.searchEngine.init();
      this.cslEngine = new CslEngine(this.corpusState.cslRegistry);

      const sourceId = path.basename(filePath).replace(/\.[^.]+$/, "");
      return {
        source_id: sourceId,
        status: "indexed",
        document_path: filePath,
      };
    } catch (err) {
      return {
        source_id: "",
        status: "error",
        error_message: err instanceof Error ? err.message : String(err),
      };
    }
  }

  private deleteDocument(sourceId: string): Record<string, unknown> {
    const docDir = safePath(this.corpusRoot, sourceId);
    if (!fs.existsSync(docDir)) {
      return { source_id: sourceId, status: "not_found" };
    }
    try {
      fs.rmSync(docDir, { recursive: true, force: true });
      this.corpusState = null;
      this.initPromise = null;
      return { source_id: sourceId, status: "deleted" };
    } catch (err) {
      return { source_id: sourceId, status: "error", error: String(err) };
    }
  }
}
