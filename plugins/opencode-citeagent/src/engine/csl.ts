import type { CslRecord, CslRenderResult } from "./types.js";

export class CslEngine {
  private registry: Map<string, CslRecord>;

  constructor(registry: Map<string, CslRecord>) {
    this.registry = registry;
  }

  async render(citationKey: string, style: string = "apa"): Promise<CslRenderResult> {
    const record = this.registry.get(citationKey);
    if (!record) {
      return {
        output: `[${citationKey}] Citation key not found in corpus`,
        style,
        citation_key: citationKey,
        note: "citation_key not found",
      };
    }

    const formatted = this.formatCslRecord(record, style);
    const inText = this.formatInText(record, style);

    return {
      output: formatted,
      in_text: inText,
      style,
      citation_key: citationKey,
    };
  }

  private formatCslRecord(record: CslRecord, style: string): string {
    const authors = (record.author || [])
      .map((a) => `${a.family || ""}${a.given ? `, ${a.given}` : ""}`)
      .join(", ");

    const year = record.issued?.["date-parts"]?.[0]?.[0] || "n.d.";
    const title = record.title || "Untitled";
    const container = (record as Record<string, unknown>)["container-title"] as string || "";

    switch (style) {
      case "apa":
        return `${authors} (${year}). ${title}. ${container}`.replace(/\. $/, ".");
      case "chicago-author-date":
        return `${authors}. ${year}. "${title}." ${container}`.replace(/" $/, '" ');
      case "ieee":
        return `${authors}, "${title}," ${container}, ${year}.`;
      case "mla":
        return `${authors}. "${title}." ${container}, ${year}.`;
      default:
        return `${authors} (${year}). ${title}. ${container}`.replace(/\. $/, ".");
    }
  }

  private formatInText(record: CslRecord, style: string): string {
    const firstAuthor = record.author?.[0];
    const family = firstAuthor?.family || "Unknown";
    const year = record.issued?.["date-parts"]?.[0]?.[0] || "n.d.";

    switch (style) {
      case "apa":
        return `(${family}, ${year})`;
      case "chicago-author-date":
        return `(${family} ${year})`;
      case "ieee":
        return `[${record.id}]`;
      case "mla":
        return `(${family} ${year})`;
      default:
        return `(${family}, ${year})`;
    }
  }
}