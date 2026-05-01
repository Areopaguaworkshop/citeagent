export interface CorpusNode {
  node_id: string;
  source_id: string;
  text: string;
  sha256: string;
  page: number | null;
  paragraph: number | null;
  section_path: string;
}

export interface CslRecord {
  id: string;
  type: string;
  title?: string;
  author?: Array<{ family?: string; given?: string }>;
  issued?: { "date-parts"?: number[][] };
  URL?: string;
  merkle_root?: string;
  content_hash?: string;
  ingestion_timestamp?: string;
  source_type?: string;
  [key: string]: unknown;
}

export interface MerkleTree {
  algorithm: string;
  leaf_count: number;
  levels: string[][];
  root: string;
}

export interface CorpusState {
  cslRegistry: Map<string, CslRecord>;
  nodes: CorpusNode[];
  merkleRegistry: Map<string, MerkleTree>;
  sourceIds: Set<string>;
  loadedAt: number;
}

export interface SearchDoc {
  id: string;
  source_id: string;
  text: string;
  sha256: string;
  title: string;
  citation_key: string;
  merkle_root: string;
  section_path: string;
  page: number | null;
}

export interface MemoryEntry {
  entry_id: string;
  timestamp: string;
  thread_id: string;
  query: string;
  response: string;
  evidence_node_ids: string[];
  sha256: string;
  tags?: string[];
  content?: string;
  tier?: string;
}

export interface AuditRecord {
  audit_id: string;
  verdict: string;
  reasoning: string;
  evidence_hashes: string[];
  query: string;
  saved_at: string;
}

export interface ClaimRecord {
  claim_id: string;
  claim_text: string;
  source_id: string;
  polarity_tag?: string;
  entities?: string[];
  hierarchy_path?: string;
}

export interface PageIndexNode {
  id: string;
  label?: string;
  heading?: string;
  node_id?: string;
  page_range?: string;
  page_number?: number;
  summary?: string;
  text_blocks?: string[];
  children?: PageIndexNode[];
}

export interface PageIndexTree {
  source_id: string;
  levels: Record<string, PageIndexNode[]>;
  root?: PageIndexNode;
}

export interface SearchResult {
  results: Array<Record<string, unknown>>;
  total: number;
  note?: string;
}

export interface MerkleVerifyResult {
  valid: boolean;
  computed_hash: string;
  expected_hash: string;
  verified_sources?: string[];
  registry_verified?: boolean;
}

export interface CslRenderResult {
  output: string;
  in_text?: string;
  style: string;
  citation_key: string;
  note?: string;
}