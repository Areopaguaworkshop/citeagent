import fs from "fs";
import path from "path";
import crypto from "crypto";
import type { MemoryEntry } from "./types.js";

export class MemoryStoreEngine {
  private corpusRoot: string;

  constructor(corpusRoot: string) {
    this.corpusRoot = corpusRoot;
  }

  async save(
    threadId: string,
    query: string,
    response: string,
    evidenceNodeIds: string[],
    tags?: string[],
  ): Promise<MemoryEntry & { status: string }> {
    const dir = path.join(this.corpusRoot, ".memory");
    fs.mkdirSync(dir, { recursive: true });

    const timestamp = new Date().toISOString();
    const entryId = `mem-${crypto.randomBytes(8).toString("hex")}`;
    const sha256 = crypto
      .createHash("sha256")
      .update(`${timestamp}|${query}|${response}`)
      .digest("hex");

    const entry: MemoryEntry = {
      entry_id: entryId,
      timestamp,
      thread_id: threadId,
      query,
      response,
      evidence_node_ids: evidenceNodeIds,
      sha256,
      tags: tags || [],
    };

    const filePath = path.join(dir, `${threadId}.jsonl`);
    fs.appendFileSync(filePath, JSON.stringify(entry) + "\n");

    return { ...entry, status: "saved" };
  }

  async search(
    query: string,
    threadId?: string,
    limit: number = 10,
  ): Promise<{ results: MemoryEntry[]; total: number }> {
    const dir = path.join(this.corpusRoot, ".memory");
    if (!fs.existsSync(dir)) return { results: [], total: 0 };

    const files = threadId
      ? [`${threadId}.jsonl`]
      : fs.readdirSync(dir).filter((f) => f.endsWith(".jsonl"));

    const allEntries: Array<MemoryEntry & { _score: number }> = [];
    const queryLower = query.toLowerCase();
    const queryTokens = queryLower.split(/\s+/);

    for (const file of files) {
      const filePath = path.join(dir, file);
      if (!fs.existsSync(filePath)) continue;
      const lines = fs.readFileSync(filePath, "utf-8").split("\n").filter(Boolean);
      for (const line of lines) {
        try {
          const entry = JSON.parse(line) as MemoryEntry;
          const text = `${entry.query} ${entry.response} ${(entry.tags || []).join(" ")}`.toLowerCase();
          const score = queryTokens.filter((t) => text.includes(t)).length;
          if (score > 0) {
            allEntries.push({ ...entry, _score: score });
          }
        } catch {}
      }
    }

    allEntries.sort((a, b) => b._score - a._score);
    const results = allEntries.slice(0, limit).map(({ _score, ...rest }) => rest as MemoryEntry);

    return { results, total: allEntries.length };
  }

  async storeTier(args: {
    content: string;
    tier: string;
    key?: string;
    tags?: string[];
    thread_id?: string;
    source_ids?: string[];
  }): Promise<{ entry_id: string; stored: boolean; tier: string; error?: string; path?: string }> {
    if (args.tier === "corpus") {
      return { entry_id: "", stored: false, tier: "corpus", error: "Corpus tier is immutable — use index_document instead" };
    }

    if (args.tier === "working") {
      const entryId = `mem-working-${crypto.randomBytes(4).toString("hex")}`;
      return { entry_id: entryId, stored: true, tier: "working" };
    }

    const tierDir = path.join(this.corpusRoot, ".memory", args.tier);
    fs.mkdirSync(tierDir, { recursive: true });

    const threadId = args.thread_id || "default";
    const filePath = path.join(tierDir, `${threadId}.jsonl`);
    const entryId = `mem-${args.tier}-${crypto.randomBytes(4).toString("hex")}`;
    const timestamp = new Date().toISOString();
    const sha256 = crypto.createHash("sha256").update(args.content).digest("hex");

    const entry = {
      entry_id: entryId,
      timestamp,
      tier: args.tier,
      key: args.key || entryId,
      content: args.content,
      tags: args.tags || [],
      thread_id: threadId,
      source_ids: args.source_ids || [],
      sha256,
    };

    fs.appendFileSync(filePath, JSON.stringify(entry) + "\n");

    return { entry_id: entryId, stored: true, tier: args.tier, path: filePath };
  }

  async retrieveTier(
    query: string,
    tier?: string,
    limit: number = 10,
  ): Promise<{ entries: Record<string, unknown>[]; total: number; tier: string }> {
    const tiersToSearch = tier ? [tier] : ["episodic", "long_term"];
    const allEntries: Record<string, unknown>[] = [];
    const queryLower = query.toLowerCase();

    for (const t of tiersToSearch) {
      const tierDir = path.join(this.corpusRoot, ".memory", t);
      if (!fs.existsSync(tierDir)) continue;

      const files = fs.readdirSync(tierDir).filter((f) => f.endsWith(".jsonl"));
      for (const file of files) {
        const filePath = path.join(tierDir, file);
        const lines = fs.readFileSync(filePath, "utf-8").split("\n").filter(Boolean);
        for (const line of lines) {
          try {
            const entry = JSON.parse(line);
            const text = (entry.content || "").toLowerCase();
            if (text.includes(queryLower) || queryLower.split(/\s+/).some((t) => text.includes(t))) {
              allEntries.push(entry);
            }
          } catch {}
        }
      }
    }

    return {
      entries: allEntries.slice(0, limit),
      total: allEntries.length,
      tier: tier || "all",
    };
  }

  async consolidate(
    threadId: string = "default",
  ): Promise<{ consolidated_count: number; from_tier: string; to_tier: string }> {
    const epiDir = path.join(this.corpusRoot, ".memory", "episodic");
    const ltDir = path.join(this.corpusRoot, ".memory", "long_term");
    if (!fs.existsSync(epiDir)) return { consolidated_count: 0, from_tier: "episodic", to_tier: "long_term" };

    fs.mkdirSync(ltDir, { recursive: true });

    const epiFile = path.join(epiDir, `${threadId}.jsonl`);
    const ltFile = path.join(ltDir, `${threadId}.jsonl`);
    if (!fs.existsSync(epiFile)) return { consolidated_count: 0, from_tier: "episodic", to_tier: "long_term" };

    const entries = fs.readFileSync(epiFile, "utf-8").split("\n").filter(Boolean);
    const seenHashes = new Set<string>();

    const ltExisting = fs.existsSync(ltFile)
      ? fs.readFileSync(ltFile, "utf-8").split("\n").filter(Boolean)
      : [];
    for (const line of ltExisting) {
      try {
        const entry = JSON.parse(line);
        seenHashes.add(entry.sha256);
      } catch {}
    }

    let consolidated = 0;
    for (const line of entries) {
      try {
        const entry = JSON.parse(line);
        if (!seenHashes.has(entry.sha256)) {
          fs.appendFileSync(ltFile, JSON.stringify(entry) + "\n");
          seenHashes.add(entry.sha256);
          consolidated++;
        }
      } catch {}
    }

    return { consolidated_count: consolidated, from_tier: "episodic", to_tier: "long_term" };
  }
}