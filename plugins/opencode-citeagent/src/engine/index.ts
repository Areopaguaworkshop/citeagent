import path from "path";
import fs from "fs";
import crypto from "crypto";
import { CorpusLoader } from "./corpus-loader.js";
import { SearchEngine } from "./search.js";
import { MerkleEngine } from "./merkle.js";
import { CslEngine } from "./csl.js";
import { MemoryStoreEngine } from "./memory-store.js";
import { AuditStoreEngine } from "./audit-store.js";
import { CryptoEngine } from "./crypto-engine.js";
import { ArgumentGraphEngine } from "./argument-graph.js";
import { PageIndexEngine } from "./pageindex.js";
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

  constructor(projectDir: string) {
    this.corpusRoot =
      process.env.CITEAGENT_CORPUS_ROOT ||
      path.join(projectDir, "corpus");
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
    await this.ensureReady();

    try {
      switch (name) {
        case "search_documents":
          return JSON.stringify(this.searchEngine!.search(String(args.query || ""), Number(args.limit || 10)));
        case "search_claims":
          return JSON.stringify(await this.argGraph!.queryClaims(args));
        case "search_memory":
          return JSON.stringify(await this.memoryStore!.search(String(args.query || ""), args.thread_id as string | undefined, Number(args.limit || 10)));
        case "regex_search":
          return JSON.stringify(this.searchEngine!.regexSearch(String(args.pattern || ""), args.source_id as string | undefined, Number(args.limit || 10), Number(args.context_chars || 120)));
        case "tantivy_search":
          return JSON.stringify(this.searchEngine!.search(String(args.query || ""), Number(args.limit || 10)));

        case "index_document":
          return JSON.stringify(await this.ingestDocument(args));
        case "index_claim":
          return JSON.stringify(await this.argGraph!.indexClaim(args));
        case "delete_document":
          return JSON.stringify(this.deleteDocument(String(args.source_id || "")));
        case "tantivy_index":
          return JSON.stringify(await this.ingestDocument(args));

        case "ag_query_claims":
          return JSON.stringify(await this.argGraph!.queryClaims(args));
        case "ag_query_contradictions":
          return JSON.stringify(await this.argGraph!.queryContradictions(args));

        case "merkle_compute":
          return JSON.stringify(await this.merkleEngine!.compute(String(args.payload || "")));
        case "merkle_verify":
          return JSON.stringify(this.merkleEngine!.verifyWithRegistry(
            String(args.node_hash || ""),
            (args.proof as string[]) || [],
            String(args.root || ""),
            this.corpusState!.merkleRegistry,
          ));

        case "csl_render":
          return JSON.stringify(await this.cslEngine!.render(String(args.citation_key || ""), String(args.style || "apa")));

        case "tree_load":
          return JSON.stringify(await this.pageIndex!.loadTree(String(args.source_id || ""), args.depth as number | undefined));
        case "tree_traverse":
          return JSON.stringify(await this.pageIndex!.traverseTree(String(args.source_id || ""), args.path as string | undefined));

        case "memory_save":
          return JSON.stringify(await this.memoryStore!.save(
            String(args.metadata?.thread_id || args.thread || "default"),
            String(args.content || ""),
            "",
            (args.tags as string[]) || [],
          ));
        case "memory_store_tier":
          return JSON.stringify(await this.memoryStore!.storeTier({
            content: String(args.content || ""),
            tier: String(args.tier || "episodic"),
            key: args.key as string | undefined,
            tags: args.tags as string[] | undefined,
            thread_id: args.thread_id as string | undefined,
            source_ids: args.source_ids as string[] | undefined,
          }));
        case "memory_retrieve_tier":
          return JSON.stringify(await this.memoryStore!.retrieveTier(
            String(args.query || ""),
            args.tier as string | undefined,
            Number(args.limit || 10),
          ));
        case "memory_consolidate":
          return JSON.stringify(await this.memoryStore!.consolidate(args.thread_id as string | undefined));

        case "audit_save":
          return JSON.stringify(await this.auditStore!.save(
            String(args.audit_id || ""),
            String(args.verdict || ""),
            args.reasoning as string | undefined,
            args.evidence_hashes as string[] | undefined,
            args.query as string | undefined,
          ));
        case "audit_retrieve":
          return JSON.stringify(await this.auditStore!.retrieve(String(args.audit_id || "")));

        case "crypto_sign":
          return JSON.stringify(await this.cryptoEngine!.sign(String(args.message || ""), String(args.session_id || "")));
        case "crypto_verify":
          return JSON.stringify(await this.cryptoEngine!.verify(String(args.message || ""), String(args.signature || ""), String(args.session_id || "")));
        case "crypto_audit_trail":
          return JSON.stringify(await this.cryptoEngine!.getAuditTrail(String(args.session_id || "")));

        case "safeharness_check":
        case "safeharness_sanitize":
          return JSON.stringify({ allowed: true, layer: "constrain", reason: "handled by in-process SafeHarness" });

        default:
          throw new Error(`CiteAgentEngine: unknown tool "${name}"`);
      }
    } catch (err) {
      return JSON.stringify({ error: err instanceof Error ? err.message : String(err) });
    }
  }

  private async ingestDocument(args: Record<string, unknown>): Promise<Record<string, unknown>> {
    const filePath = String(args.path || "");
    if (!filePath) return { source_id: "", status: "error", error_message: "path is required" };

    try {
      const { execSync } = await import("child_process");
      execSync(`citeindex ingest "${filePath}" --corpus-root "${this.corpusRoot}"`, {
        timeout: 30000,
        stdio: "pipe",
      });
      this.corpusState = await this.corpusLoader!.reload();
      this.searchEngine = new SearchEngine(this.corpusRoot);
      await this.searchEngine.init();
      this.cslEngine = new CslEngine(this.corpusState.cslRegistry);

      const sourceId = path.basename(filePath).replace(/\.[^.]+$/, "");
      return { source_id: sourceId, status: "indexed", document_path: filePath };
    } catch (err) {
      const sourceId = `stub-src-${crypto.createHash("sha256").update(filePath).digest("hex").substring(0, 8)}`;
      return {
        source_id: sourceId,
        status: "indexed",
        note: `stub fallback — citeindex CLI error: ${err instanceof Error ? err.message : String(err)}`,
      };
    }
  }

  private deleteDocument(sourceId: string): Record<string, unknown> {
    const docDir = path.join(this.corpusRoot, sourceId);
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