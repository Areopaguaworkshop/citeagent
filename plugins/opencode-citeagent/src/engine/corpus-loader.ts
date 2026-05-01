import fs from "fs";
import path from "path";
import type {
  CorpusState,
  CorpusNode,
  CslRecord,
  MerkleTree,
} from "./types.js";

export class CorpusLoader {
  private corpusRoot: string;
  private state: CorpusState | null = null;

  constructor(corpusRoot: string) {
    this.corpusRoot = corpusRoot;
  }

  async load(): Promise<CorpusState> {
    if (this.state) return this.state;
    return this.reloadData();
  }

  async reload(): Promise<CorpusState> {
    return this.reloadData();
  }

  private async reloadData(): Promise<CorpusState> {
    const cslRegistry = new Map<string, CslRecord>();
    const nodes: CorpusNode[] = [];
    const merkleRegistry = new Map<string, MerkleTree>();
    const sourceIds = new Set<string>();

    if (!fs.existsSync(this.corpusRoot)) {
      return { cslRegistry, nodes, merkleRegistry, sourceIds, loadedAt: Date.now() };
    }

    const entries = this.safeReaddir(this.corpusRoot);
    for (const entry of entries) {
      const dirPath = path.join(this.corpusRoot, entry);
      if (!fs.statSync(dirPath).isDirectory()) continue;

      const cslPath = path.join(dirPath, "csl.json");
      if (!fs.existsSync(cslPath)) continue;

      try {
        const csl = JSON.parse(fs.readFileSync(cslPath, "utf-8")) as CslRecord;
        const sourceId = csl.id || entry;
        cslRegistry.set(sourceId, csl);
        sourceIds.add(sourceId);

        const docPath = path.join(dirPath, "document.json");
        if (fs.existsSync(docPath)) {
          const doc = JSON.parse(fs.readFileSync(docPath, "utf-8"));
          const docNodes: CorpusNode[] = doc.nodes || [];
          for (const node of docNodes) {
            nodes.push(node);
          }
        }

        const merklePath = path.join(dirPath, "merkle.json");
        if (fs.existsSync(merklePath)) {
          const merkle = JSON.parse(
            fs.readFileSync(merklePath, "utf-8"),
          ) as MerkleTree;
          merkleRegistry.set(sourceId, merkle);
        }
      } catch (err) {
        console.warn(`[CorpusLoader] Skipping ${entry}: ${err}`);
      }
    }

    this.state = { cslRegistry, nodes, merkleRegistry, sourceIds, loadedAt: Date.now() };
    return this.state;
  }

  private safeReaddir(dir: string): string[] {
    try {
      return fs
        .readdirSync(dir)
        .filter((e) => !e.startsWith(".") && e !== "_url_content_hashes.json" && e !== "ingestion_log.jsonl");
    } catch {
      return [];
    }
  }
}