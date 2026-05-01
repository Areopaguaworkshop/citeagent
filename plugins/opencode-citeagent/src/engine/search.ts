import MiniSearch from "minisearch";
import { CorpusLoader } from "./corpus-loader.js";
import type { CorpusState, SearchDoc, SearchResult } from "./types.js";

export class SearchEngine {
  private corpusRoot: string;
  private loader: CorpusLoader;
  private index: MiniSearch<SearchDoc> | null = null;
  private state: CorpusState | null = null;

  constructor(corpusRoot: string) {
    this.corpusRoot = corpusRoot;
    this.loader = new CorpusLoader(corpusRoot);
  }

  async init(): Promise<void> {
    this.state = await this.loader.load();
    this.index = this.buildIndex(this.state);
  }

  search(query: string, limit: number = 10): SearchResult {
    if (!this.index || !this.state) {
      return { results: [], total: 0, note: "engine not initialized" };
    }

    try {
      const hits = this.index.search(query, { fuzzy: 0.2, prefix: true });
      const results = hits.slice(0, limit).map((hit) => {
        const doc = hit as unknown as SearchDoc;
        return {
          node_id: doc.id,
          source_id: doc.source_id,
          title: doc.title,
          citation_key: doc.citation_key,
          sha256: doc.sha256,
          merkle_root: doc.merkle_root,
          section_path: doc.section_path,
          score: hit.score,
        };
      });

      return { results, total: results.length };
    } catch {
      return { results: [], total: 0, note: "search error" };
    }
  }

  regexSearch(
    pattern: string,
    sourceId?: string,
    limit: number = 10,
    contextChars: number = 120,
  ): SearchResult {
    if (!this.state) return { results: [], total: 0, note: "engine not initialized" };

    let re: RegExp;
    try {
      re = new RegExp(pattern, "gi");
    } catch (err) {
      return { results: [], total: 0, note: `Invalid regex: ${err}` };
    }

    const results: Array<Record<string, unknown>> = [];
    const nodes = sourceId
      ? this.state.nodes.filter((n) => n.source_id === sourceId)
      : this.state.nodes;

    for (const node of nodes) {
      re.lastIndex = 0;
      const match = re.exec(node.text);
      if (match) {
        const start = Math.max(0, match.index - contextChars / 2);
        const end = Math.min(node.text.length, match.index + match[0].length + contextChars / 2);
        results.push({
          doc_id: node.source_id,
          node_id: node.node_id,
          match_text: match[0],
          context: node.text.substring(start, end),
          section_path: node.section_path,
        });
        if (results.length >= limit) break;
      }
    }

    return { results, total: results.length };
  }

  private buildIndex(state: CorpusState): MiniSearch<SearchDoc> {
    const ms = new MiniSearch<SearchDoc>({
      fields: ["text", "title", "section_path"],
      storeFields: ["source_id", "sha256", "merkle_root", "citation_key", "title", "section_path", "page"],
      idField: "id",
    });

    const docs: SearchDoc[] = state.nodes.map((node) => {
      const csl = state.cslRegistry.get(node.source_id);
      return {
        id: node.node_id,
        source_id: node.source_id,
        text: node.text,
        sha256: node.sha256,
        title: csl?.title || node.source_id,
        citation_key: csl?.id || node.source_id,
        merkle_root: csl?.merkle_root || "",
        section_path: node.section_path,
        page: node.page,
      };
    });

    if (docs.length > 0) {
      ms.addAll(docs);
    }

    return ms;
  }
}