import { mkdir, readFile, rename, writeFile } from "fs/promises";
import path from "path";
import type { SearchResult } from "./types.js";

export type SourceRole = "primary" | "secondary" | "unknown";

export interface PaperSource {
  source_id: string;
  role: SourceRole;
}

export interface PaperWorkspace {
  schema_version: 1;
  paper_id: string;
  title: string;
  question: string;
  sources: PaperSource[];
  created_at: string;
  updated_at: string;
}

const paperId = (value: string) => /^[a-z0-9][a-z0-9_-]{0,63}$/.test(value);
const now = () => new Date().toISOString();

/** Public metadata only. Corpus contents never live in this store. */
export class WorkspaceStore {
  private readonly paperDir: string;
  private readonly activePath: string;
  private writes: Promise<void> = Promise.resolve();

  constructor(stateRoot: string) {
    this.paperDir = path.join(stateRoot, "papers");
    this.activePath = path.join(stateRoot, "active-paper.json");
  }

  async create(paper_id: string, title: string, question: string): Promise<PaperWorkspace> {
    return this.serial(async () => {
      if (!paperId(paper_id)) throw new Error("paper_id must be a lowercase slug");
      if (!title.trim() || !question.trim()) throw new Error("title and question are required");
      const timestamp = now();
      const paper: PaperWorkspace = { schema_version: 1, paper_id, title: title.trim(), question: question.trim(), sources: [], created_at: timestamp, updated_at: timestamp };
      await this.write(this.paperPath(paper_id), paper);
      return paper;
    });
  }

  async addSource(paper_id: string, source_id: string, role: SourceRole = "unknown") {
    return this.serial(async () => {
      if (!source_id.trim()) throw new Error("source_id is required");
      if (!(["primary", "secondary", "unknown"] as string[]).includes(role)) throw new Error("role must be primary, secondary, or unknown");
      const paper = await this.load(paper_id);
      const existing = paper.sources.find((source) => source.source_id === source_id);
      if (existing) existing.role = role;
      else paper.sources.push({ source_id, role });
      paper.updated_at = now();
      await this.write(this.paperPath(paper_id), paper);
      return paper;
    });
  }

  async use(paper_id: string): Promise<PaperWorkspace> {
    return this.serial(async () => {
      const paper = await this.load(paper_id);
      await this.write(this.activePath, { paper_id });
      return paper;
    });
  }

  async get(paper_id: string): Promise<PaperWorkspace> {
    return this.load(paper_id);
  }

  async active(): Promise<PaperWorkspace | null> {
    try {
      const active = JSON.parse(await readFile(this.activePath, "utf8")) as { paper_id?: string };
      return active.paper_id ? await this.load(active.paper_id) : null;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
      throw error;
    }
  }

  async status() {
    const active = await this.active();
    return { active_paper: active };
  }

  async audit(paper_id?: string) {
    const paper = paper_id ? await this.load(paper_id) : await this.active();
    if (!paper) return { status: "no_active_paper", source_count: 0, missing_source_ids: [] };
    return {
      status: paper.sources.length ? "ok" : "incomplete",
      paper_id: paper.paper_id,
      source_count: paper.sources.length,
      primary_source_count: paper.sources.filter((source) => source.role === "primary").length,
      missing_source_ids: paper.sources.length ? [] : ["Add at least one approved source before drafting."],
    };
  }

  async filterSearchResults(result: SearchResult): Promise<SearchResult> {
    const active = await this.active();
    if (!active) return result;
    const allowed = new Set(active.sources.map((source) => source.source_id));
    const results = result.results.filter((item) => allowed.has(String(item.source_id ?? item.doc_id ?? "")));
    return { ...result, results, total: results.length };
  }

  async assertSourceAllowed(sourceId: string) {
    const active = await this.active();
    if (!active || active.sources.some((source) => source.source_id === sourceId)) return;
    throw new Error(`Source ${sourceId} is not approved for active paper ${active.paper_id}`);
  }

  private paperPath(id: string) {
    if (!paperId(id)) throw new Error("paper_id must be a lowercase slug");
    return path.join(this.paperDir, `${id}.json`);
  }

  private async load(id: string): Promise<PaperWorkspace> {
    try {
      return JSON.parse(await readFile(this.paperPath(id), "utf8")) as PaperWorkspace;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") throw new Error(`Paper ${id} not found`);
      throw error;
    }
  }

  private async write(file: string, value: unknown) {
    await mkdir(path.dirname(file), { recursive: true });
    const temporary = `${file}.tmp`;
    await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, "utf8");
    await rename(temporary, file);
  }

  private serial<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.writes.then(operation);
    this.writes = result.then(() => undefined, () => undefined);
    return result;
  }
}
