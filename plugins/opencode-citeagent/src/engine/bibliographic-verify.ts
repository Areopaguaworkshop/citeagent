import type { CslRecord } from "./types.js";

export type BibliographicStatus =
  | "verified"
  | "not_found"
  | "unresolvable"
  | "unavailable";

export interface BibliographicVerification {
  citation_key: string;
  status: BibliographicStatus;
  method?: "doi" | "title";
  query?: string;
  matched_doi?: string;
  matched_title?: string;
  reason?: string;
}

type Fetcher = (
  input: string | URL | Request,
  init?: RequestInit,
) => Promise<Response>;

function field(record: CslRecord, ...names: string[]): string {
  for (const name of names) {
    const value = record[name];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function normalizeDoi(value: string): string {
  return value
    .replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "")
    .replace(/^doi:\s*/i, "")
    .trim()
    .toLowerCase();
}

function normalizeTitle(value: string): string {
  return (value.toLowerCase().match(/[\p{L}\p{N}]+/gu) || []).join(" ");
}

export async function verifyBibliographicRecord(
  record: CslRecord | undefined,
  citationKey: string,
  fetcher: Fetcher = fetch,
): Promise<BibliographicVerification> {
  if (!record) {
    return {
      citation_key: citationKey,
      status: "unresolvable",
      reason: "citation key is not present in the local CSL registry",
    };
  }

  const doi = normalizeDoi(field(record, "DOI", "doi"));
  const title = field(record, "title");
  if (!doi && !normalizeTitle(title)) {
    return {
      citation_key: citationKey,
      status: "unresolvable",
      reason: "CSL record has neither a DOI nor a title",
    };
  }

  const method = doi ? "doi" : "title";
  const query = doi || title;
  const url = doi
    ? `https://api.crossref.org/works/${encodeURIComponent(doi)}`
    : `https://api.crossref.org/works?query.title=${encodeURIComponent(title)}&rows=1`;

  try {
    const response = await fetcher(url, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(10_000),
    });
    if (response.status === 404) {
      return { citation_key: citationKey, status: "not_found", method, query };
    }
    if (!response.ok) {
      return {
        citation_key: citationKey,
        status: "unavailable",
        method,
        query,
        reason: `Crossref returned HTTP ${response.status}`,
      };
    }

    const payload = (await response.json()) as {
      message?: {
        DOI?: string;
        title?: string[];
        items?: Array<{ DOI?: string; title?: string[] }>;
      };
    };
    const match = doi ? payload.message : payload.message?.items?.[0];
    const matchedDoi = normalizeDoi(match?.DOI || "");
    const matchedTitle = match?.title?.[0] || "";
    // ponytail: exact normalized titles avoid false verification; add fuzzy matching only if measured misses justify it.
    const verified = doi
      ? matchedDoi === doi
      : normalizeTitle(matchedTitle) === normalizeTitle(title);

    return {
      citation_key: citationKey,
      status: verified ? "verified" : "not_found",
      method,
      query,
      matched_doi: matchedDoi || undefined,
      matched_title: matchedTitle || undefined,
    };
  } catch (error) {
    return {
      citation_key: citationKey,
      status: "unavailable",
      method,
      query,
      reason: error instanceof Error ? error.message : String(error),
    };
  }
}
