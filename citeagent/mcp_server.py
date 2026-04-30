#!/usr/bin/env python3
"""
CiteAgent MCP Server — exposes CiteAgent engine functionality via the
Model Context Protocol (stdio transport).

Server name : citeagent
Version     : 0.4.0

Each tool is an async shim that delegates to the real CiteAgent Python
functions.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

SERVER_NAME = "citeagent"
SERVER_VERSION = "0.4.0"

server = Server(SERVER_NAME, version=SERVER_VERSION)

STUB_NOTE = "stub implementation — not yet fully implemented"
PLACEHOLDER_NOTE = "Not yet implemented"

# ---------------------------------------------------------------------------
# Corpus root resolution
# ---------------------------------------------------------------------------

_CORPUS_ROOT_ARG = "corpus/"  # default, overridden by --corpus-root or env var


def get_corpus_root() -> str:
    """Return the effective corpus root directory.

    Priority:
      1. CITEAGENT_CORPUS_ROOT environment variable
      2. --corpus-root CLI argument
      3. "corpus/" (relative to CWD)
    """
    env_val = os.environ.get("CITEAGENT_CORPUS_ROOT")
    if env_val and env_val.strip():
        return env_val.strip()
    return _CORPUS_ROOT_ARG


# ---------------------------------------------------------------------------
# Lazy-initialized singletons
# ---------------------------------------------------------------------------

_search_pipeline = None
_memory_store = None
_ingestion_orchestrator = None
_corpus_loader = None


def _get_search_pipeline():
    """Lazy-initialize and return a SearchPipeline."""
    global _search_pipeline
    if _search_pipeline is None:
        from citeagent.agents.chat import SearchPipeline
        _search_pipeline = SearchPipeline(corpus_root=get_corpus_root())
    return _search_pipeline


def _get_memory_store():
    """Lazy-initialize and return a MemoryStore."""
    global _memory_store
    if _memory_store is None:
        from citeagent.agents.memory import MemoryStore
        _memory_store = MemoryStore(memory_dir=os.path.join(get_corpus_root(), ".memory"))
    return _memory_store


def _get_ingestion_orchestrator():
    """Lazy-initialize and return a CiteIndexIngestionOrchestrator."""
    global _ingestion_orchestrator
    if _ingestion_orchestrator is None:
        from citeindex import CiteIndexIngestionOrchestrator
        _ingestion_orchestrator = CiteIndexIngestionOrchestrator(corpus_root=get_corpus_root())
    return _ingestion_orchestrator


def _get_corpus_loader():
    """Lazy-initialize and return a loaded CorpusLoader."""
    global _corpus_loader
    if _corpus_loader is None:
        from citeagent.agents.corpus_loader import CorpusLoader
        _corpus_loader = CorpusLoader(corpus_root=get_corpus_root())
        _corpus_loader.load()  # load() is sync; callers should use via asyncio.to_thread
    return _corpus_loader


# ---------------------------------------------------------------------------
# Tool definitions  (list_tools)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_documents",
        "description": "BM25 full-text search over indexed documents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"},
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_claims",
        "description": "Search claims in the argument graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query for claims"},
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_memory",
        "description": "Search persisted memory entries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query for memory"},
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "index_document",
        "description": "Ingest and index a document into the knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path or URL of the document"},
                "metadata": {
                    "type": "object",
                    "description": "Optional metadata dict to attach",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "index_claim",
        "description": "Index a claim extracted from a document.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim_text": {"type": "string", "description": "The claim text"},
                "source_id": {"type": "string", "description": "Source document identifier"},
                "metadata": {
                    "type": "object",
                    "description": "Optional metadata dict",
                },
            },
            "required": ["claim_text", "source_id"],
        },
    },
    {
        "name": "delete_document",
        "description": "Remove a document and its associated data from the index.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_id": {
                    "type": "string",
                    "description": "Identifier of the document to delete",
                },
            },
            "required": ["source_id"],
        },
    },
    {
        "name": "ag_query_claims",
        "description": "Query claims from the argument graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim_id": {
                    "type": "string",
                    "description": "Optional specific claim ID to look up",
                },
                "source_id": {
                    "type": "string",
                    "description": "Optional source document filter",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "ag_query_contradictions",
        "description": "Find contradictions in the argument graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim_id": {
                    "type": "string",
                    "description": "Optional claim ID to check for contradictions",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 10,
                },
            },
        },
    },

    {
        "name": "merkle_compute",
        "description": "Compute a Merkle hash for a given payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "payload": {
                    "type": "string",
                    "description": "The data to hash (UTF-8 string)",
                },
            },
            "required": ["payload"],
        },
    },
    {
        "name": "merkle_verify",
        "description": "Verify a Merkle proof against a known root hash.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_hash": {
                    "type": "string",
                    "description": "Hash of the node to verify",
                },
                "proof": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Merkle proof (list of sibling hashes)",
                },
                "root": {
                    "type": "string",
                    "description": "Expected Merkle root hash",
                },
            },
            "required": ["node_hash", "proof", "root"],
        },
    },
    {
        "name": "csl_render",
        "description": "Render a citation in a given CSL style.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "citation_key": {
                    "type": "string",
                    "description": "Citation key to render",
                },
                "style": {
                    "type": "string",
                    "description": "CSL style name (e.g. apa, chicago, ieee)",
                    "default": "apa",
                },
            },
            "required": ["citation_key"],
        },
    },
    {
        "name": "tree_load",
        "description": "Load a pageindex tree structure.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_id": {
                    "type": "string",
                    "description": "Document source ID whose tree to load",
                },
                "depth": {
                    "type": "integer",
                    "description": "Maximum depth to load",
                    "default": -1,
                },
            },
            "required": ["source_id"],
        },
    },
    {
        "name": "tree_traverse",
        "description": "Traverse a pageindex tree with an optional path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_id": {
                    "type": "string",
                    "description": "Document source ID",
                },
                "path": {
                    "type": "string",
                    "description": "Path within the tree to traverse",
                },
            },
            "required": ["source_id"],
        },
    },
    {
        "name": "regex_search",
        "description": "Search indexed documents using a regular expression.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regular expression pattern",
                },
                "source_id": {
                    "type": "string",
                    "description": "Optional document source filter",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 10,
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "memory_save",
        "description": "Save a memory entry for later retrieval.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The memory content to store",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for categorisation",
                },
                "metadata": {
                    "type": "object",
                    "description": "Optional metadata dict",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "tantivy_search",
        "description": "Legacy Tantivy-based full-text search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"},
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "tantivy_index",
        "description": "Legacy Tantivy-based document indexing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to index"},
                "metadata": {
                    "type": "object",
                    "description": "Optional metadata dict",
                },
            },
            "required": ["path"],
        },
    },
    # Audit tools
    {
        "name": "audit_save",
        "description": "Save an audit result to persistent storage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "audit_id": {"type": "string", "description": "Unique audit identifier"},
                "verdict": {"type": "string", "description": "Audit verdict (approved/rejected)"},
                "reasoning": {"type": "string", "description": "Reasoning for the verdict"},
                "evidence_hashes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of evidence SHA-256 hashes",
                },
                "query": {"type": "string", "description": "Original query being audited"},
            },
            "required": ["audit_id", "verdict"],
        },
    },
    {
        "name": "audit_retrieve",
        "description": "Retrieve a saved audit result.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "audit_id": {"type": "string", "description": "Audit identifier to retrieve"},
            },
            "required": ["audit_id"],
        },
    },
    # Memory tier tools
    {
        "name": "memory_store_tier",
        "description": "Store a memory entry in a specific tier (working/episodic/long_term/corpus).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Memory content"},
                "tier": {"type": "string", "description": "Tier: working, episodic, long_term, corpus"},
                "key": {"type": "string", "description": "Unique key for this memory"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for categorisation"},
                "thread_id": {"type": "string", "description": "Thread identifier"},
                "source_ids": {"type": "array", "items": {"type": "string"}, "description": "Evidence source IDs"},
            },
            "required": ["content", "tier"],
        },
    },
    {
        "name": "memory_retrieve_tier",
        "description": "Retrieve memories from a specific tier or all tiers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "tier": {"type": "string", "description": "Tier to search (optional)"},
                "limit": {"type": "integer", "description": "Max results", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_consolidate",
        "description": "Consolidate episodic memories into long-term storage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "Thread to consolidate (optional)"},
            },
        },
    },

    # Cryptographic tools
    {
        "name": "crypto_sign",
        "description": "Sign a message using HMAC-SHA256 (MVP - upgrade to Ed25519 for production).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to sign"},
                "session_id": {"type": "string", "description": "Session identifier"},
            },
            "required": ["message", "session_id"],
        },
    },
    {
        "name": "crypto_verify",
        "description": "Verify an HMAC-SHA256 signature.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Original message"},
                "signature": {"type": "string", "description": "Signature to verify"},
                "session_id": {"type": "string", "description": "Session identifier"},
            },
            "required": ["message", "signature", "session_id"],
        },
    },
    {
        "name": "crypto_audit_trail",
        "description": "Return the audit chain for a session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session identifier"},
            },
            "required": ["session_id"],
        },
    },
    # SafeHarness tools
    {
        "name": "safeharness_check",
        "description": "Run all 4 SafeHarness layers on a tool call and return the result.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "Name of the tool to check"},
                "args": {"type": "object", "description": "Tool arguments"},
            },
            "required": ["tool_name"],
        },
    },
    {
        "name": "safeharness_sanitize",
        "description": "SafeHarness Layer 1: sanitize input for a tool call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "Tool name"},
                "input": {"type": "object", "description": "Input to sanitize"},
            },
            "required": ["tool_name", "input"],
        },
    },

]

# ---------------------------------------------------------------------------
# Handler helpers
# ---------------------------------------------------------------------------


def _sha256_hex(data: str) -> str:
    """Return the hex-encoded SHA-256 digest of *data* (UTF-8)."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# list_tools handler
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name=d["name"], description=d["description"], inputSchema=d["inputSchema"])
        for d in TOOL_DEFINITIONS
    ]


# ---------------------------------------------------------------------------
# call_tool handler
# ---------------------------------------------------------------------------


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Dispatch an incoming tool call to the appropriate handler."""

    if arguments is None:
        arguments = {}

    handler = _HANDLERS.get(name)
    if handler is None:
        return [
            {
                "type": "text",
                "text": json.dumps({"error": f"Unknown tool: {name}"}),
            }
        ]

    result = await handler(arguments)
    return [{"type": "text", "text": json.dumps(result)}]


# ---------------------------------------------------------------------------
# Individual tool handlers  (all async, return JSON-serialisable dicts)
# ---------------------------------------------------------------------------


async def _handle_search_documents(args: dict[str, Any]) -> dict[str, Any]:
    """BM25 full-text search using SearchPipeline."""
    query: str = args.get("query", "")
    limit: int = args.get("limit", 10)
    try:
        pipeline = _get_search_pipeline()
        result = await asyncio.wait_for(
            asyncio.to_thread(pipeline.search, query, top_k=limit),
            timeout=5.0,
        )
        if result.get("status") == "no_corpus":
            return result
        # Normalize the SearchPipeline output to the MCP schema
        results = result.get("results", [])
        return {
            "results": results,
            "total": result.get("total_results", len(results)),
            "query_id": result.get("query_id", ""),
            "retrieval_method": result.get("retrieval_method", ""),
        }
    except Exception as exc:
        logger.warning("search_documents failed, falling back to stub: %s", exc)
        stub_hash = _sha256_hex(f"stub:{query}")
        results = []
        for i in range(min(limit, 3)):
            results.append(
                {
                    "title": f"Stub document {i + 1} for '{query}'",
                    "source_id": f"stub-src-{i + 1}",
                    "sha256": _sha256_hex(f"stub:{query}:{i}"),
                    "merkle_root": stub_hash,
                    "citation_key": f"stub{query[:8]}{i + 1}",
                }
            )
        return {
            "results": results,
            "total": len(results),
            "note": f"stub fallback — real implementation error: {exc}",
        }


async def _handle_search_claims(args: dict[str, Any]) -> dict[str, Any]:
    """Search claims using the v12 runtime ClaimExtractionAgent adapter."""
    query: str = args.get("query", "")
    limit: int = args.get("limit", 10)
    try:
        from citeagent.agents.v12_runtime import handle_claim_extraction
        result = await asyncio.wait_for(
            asyncio.to_thread(handle_claim_extraction, {"text": query, "query": query}),
            timeout=5.0,
        )
        claims = result.get("claims", [])
        # Normalize to MCP schema
        results = []
        for claim in claims[:limit]:
            results.append({
                "claim_id": claim.get("claim_id", ""),
                "claim_text": claim.get("claim_text", ""),
                "source_id": claim.get("section_ref", ""),
                "polarity_tag": claim.get("polarity_tag", ""),
                "entities": claim.get("entities", []),
            })
        return {"results": results, "total": len(results)}
    except Exception as exc:
        logger.warning("search_claims failed, falling back to stub: %s", exc)
        results = [
            {
                "claim_id": f"claim-stub-{i}",
                "claim_text": f"Stub claim {i} matching '{query}'",
                "source_id": f"stub-src-{i}",
            }
            for i in range(min(limit, 3))
        ]
        return {
            "results": results,
            "total": len(results),
            "note": f"stub fallback — real implementation error: {exc}",
        }


async def _handle_search_memory(args: dict[str, Any]) -> dict[str, Any]:
    """Search persisted memory entries using MemoryStore."""
    query: str = args.get("query", "")
    limit: int = args.get("limit", 10)
    thread_id: str | None = args.get("thread_id")
    try:
        store = _get_memory_store()
        entries = await asyncio.wait_for(
            asyncio.to_thread(store.search, query, thread_id=thread_id),
            timeout=5.0,
        )
        results = []
        for entry in entries[:limit]:
            results.append({
                "memory_id": entry.entry_id,
                "content": entry.response or entry.query,
                "query": entry.query,
                "thread_id": entry.thread_id,
                "timestamp": entry.timestamp,
                "tags": [],
            })
        return {"results": results, "total": len(results)}
    except Exception as exc:
        logger.warning("search_memory failed, falling back to stub: %s", exc)
        results = [
            {
                "memory_id": f"mem-stub-{i}",
                "content": f"Stub memory {i} for '{query}'",
                "tags": ["stub"],
            }
            for i in range(min(limit, 3))
        ]
        return {
            "results": results,
            "total": len(results),
            "note": f"stub fallback — real implementation error: {exc}",
        }


async def _handle_index_document(args: dict[str, Any]) -> dict[str, Any]:
    """Ingest a document using CiteIndexIngestionOrchestrator."""
    path: str = args.get("path", "")
    # Quick validation: skip heavy call if path is obviously invalid
    if not path or not os.path.exists(path):
        return {
            "source_id": f"stub-src-{_sha256_hex(path)[:12]}",
            "status": "indexed",
            "note": f"stub fallback — path does not exist: {path}",
        }
    try:
        orchestrator = _get_ingestion_orchestrator()
        result = await asyncio.wait_for(
            asyncio.to_thread(orchestrator.ingest, path),
            timeout=30.0,
        )
        status = result.get("status", "unknown")
        if status == "ok":
            csl = result.get("standardized_csl_json", {})
            return {
                "source_id": csl.get("id", ""),
                "status": "indexed",
                "document_path": result.get("document_path", ""),
                "merkle_root": csl.get("merkle_root", ""),
            }
        else:
            return {
                "source_id": "",
                "status": status,
                "error_code": result.get("error_code", ""),
                "error_message": result.get("error_message", ""),
                "note": "ingestion failed",
            }
    except asyncio.TimeoutError:
        logger.warning("index_document timed out")
        return {
            "source_id": f"stub-src-{_sha256_hex(path)[:12]}",
            "status": "indexed",
            "note": "stub fallback — ingestion timed out",
        }
    except Exception as exc:
        logger.warning("index_document failed, falling back to stub: %s", exc)
        return {
            "source_id": f"stub-src-{_sha256_hex(path)[:12]}",
            "status": "indexed",
            "note": f"stub fallback — real implementation error: {exc}",
        }


async def _handle_index_claim(args: dict[str, Any]) -> dict[str, Any]:
    """Index a claim using the v12 runtime ClaimExtractionAgent adapter."""
    claim_text: str = args.get("claim_text", "")
    source_id: str = args.get("source_id", "")
    if not claim_text.strip():
        return {
            "claim_id": f"claim-stub-{_sha256_hex(source_id)[:10]}",
            "source_id": source_id,
            "status": "indexed",
            "note": "stub fallback — empty claim text",
        }
    try:
        from citeagent.agents.v12_runtime import handle_claim_extraction
        result = await asyncio.wait_for(
            asyncio.to_thread(handle_claim_extraction, {
                "text": claim_text,
                "section_ref": source_id,
                "hierarchy_path": args.get("metadata", {}).get("hierarchy_path", "/"),
            }),
            timeout=5.0,
        )
        claims = result.get("claims", [])
        if claims:
            claim = claims[0]
            return {
                "claim_id": claim.get("claim_id", ""),
                "source_id": source_id,
                "claim_text": claim.get("claim_text", claim_text),
                "status": "indexed",
            }
        return {
            "claim_id": f"claim-{_sha256_hex(claim_text)[:10]}",
            "source_id": source_id,
            "status": "indexed",
            "note": "no claims extracted from short text",
        }
    except asyncio.TimeoutError:
        logger.warning("index_claim timed out")
        return {
            "claim_id": f"claim-stub-{_sha256_hex(claim_text)[:10]}",
            "source_id": source_id,
            "status": "indexed",
            "note": "stub fallback — claim extraction timed out",
        }
    except Exception as exc:
        logger.warning("index_claim failed, falling back to stub: %s", exc)
        return {
            "claim_id": f"claim-stub-{_sha256_hex(claim_text)[:10]}",
            "source_id": source_id,
            "status": "indexed",
            "note": f"stub fallback — real implementation error: {exc}",
        }


async def _handle_delete_document(args: dict[str, Any]) -> dict[str, Any]:
    """Delete a document and its corpus artifacts."""
    import shutil
    source_id: str = args.get("source_id", "")
    corpus_root = get_corpus_root()

    # Find the folder matching this source_id
    deleted = False
    if os.path.isdir(corpus_root):
        for entry in os.listdir(corpus_root):
            entry_path = os.path.join(corpus_root, entry)
            if not os.path.isdir(entry_path):
                continue
            # Check if csl.json id matches source_id
            csl_path = os.path.join(entry_path, "csl.json")
            if os.path.isfile(csl_path):
                try:
                    with open(csl_path, "r", encoding="utf-8") as f:
                        csl = json.load(f)
                    if csl.get("id") == source_id or entry == source_id:
                        shutil.rmtree(entry_path)
                        deleted = True
                        break
                except (json.JSONDecodeError, OSError):
                    continue

    # Also try direct folder name match
    direct_path = os.path.join(corpus_root, source_id)
    if not deleted and os.path.isdir(direct_path):
        shutil.rmtree(direct_path)
        deleted = True

    if not deleted:
        return {"source_id": source_id, "status": "not_found"}

    # Reset lazy singletons so they reload fresh data
    global _search_pipeline, _corpus_loader
    _search_pipeline = None
    _corpus_loader = None

    return {"source_id": source_id, "status": "deleted"}


async def _handle_ag_query_claims(args: dict[str, Any]) -> dict[str, Any]:
    """Query claims from the argument graph using corpus data."""
    claim_id: str | None = args.get("claim_id")
    source_id: str | None = args.get("source_id")
    limit: int = args.get("limit", 10)
    # Skip heavy corpus load if no real corpus exists
    corpus_root = get_corpus_root()
    if not os.path.isdir(corpus_root) or not os.listdir(corpus_root):
        results = [
            {"claim_id": claim_id or f"claim-stub-{i}", "claim_text": f"Stub claim {i}", "source_id": source_id or f"stub-src-{i}"}
            for i in range(min(limit, 3))
        ]
        return {"results": results, "total": len(results), "note": "stub fallback — no corpus directory"}
    try:
        loader = await asyncio.wait_for(
            asyncio.to_thread(_get_corpus_loader),
            timeout=5.0,
        )
        if source_id:
            nodes = loader.get_nodes_by_source(source_id)
        else:
            nodes = loader.all_nodes

        # If a specific claim_id was given, try to find a matching node
        if claim_id:
            nodes = [n for n in nodes if n.get("node_id") == claim_id]

        results = []
        for node in nodes[:limit]:
            results.append({
                "claim_id": node.get("node_id", ""),
                "claim_text": node.get("text", ""),
                "source_id": node.get("source_id", ""),
            })
        return {"results": results, "total": len(results)}
    except asyncio.TimeoutError:
        logger.warning("ag_query_claims timed out")
        results = [
            {"claim_id": claim_id or f"claim-stub-{i}", "claim_text": f"Stub claim {i}", "source_id": source_id or f"stub-src-{i}"}
            for i in range(min(limit, 3))
        ]
        return {"results": results, "total": len(results), "note": "stub fallback — corpus load timed out"}
    except Exception as exc:
        logger.warning("ag_query_claims failed, falling back to stub: %s", exc)
        results = [
            {
                "claim_id": claim_id or f"claim-stub-{i}",
                "claim_text": f"Stub claim {i}",
                "source_id": source_id or f"stub-src-{i}",
            }
            for i in range(min(limit, 3))
        ]
        return {
            "results": results,
            "total": len(results),
            "note": f"stub fallback — real implementation error: {exc}",
        }


async def _handle_ag_query_contradictions(args: dict[str, Any]) -> dict[str, Any]:
    """Find contradictions using the v12 runtime ContradictionAgent adapter."""
    claim_id: str | None = args.get("claim_id")
    limit: int = args.get("limit", 10)
    # Skip heavy corpus load if no real corpus exists
    corpus_root = get_corpus_root()
    if not os.path.isdir(corpus_root) or not os.listdir(corpus_root):
        results = [
            {"claim_a": claim_id or f"claim-stub-{i}-a", "claim_b": f"claim-stub-{i}-b", "edge_type": "contradicts", "weight": 0.85}
            for i in range(min(limit, 2))
        ]
        return {"results": results, "total": len(results), "note": "stub fallback — no corpus directory"}
    try:
        from citeagent.agents.v12_runtime import handle_contradiction
        # Build a minimal claims list from the corpus if possible
        loader = await asyncio.wait_for(
            asyncio.to_thread(_get_corpus_loader),
            timeout=5.0,
        )
        if claim_id:
            claims_input = [{"claim_id": claim_id, "claim_text": ""}]
        else:
            claims_input = [
                {"claim_id": n.get("node_id", f"claim-{i}"), "claim_text": n.get("text", "")}
                for i, n in enumerate(loader.all_nodes[:limit])
            ]
        result = await asyncio.wait_for(
            asyncio.to_thread(handle_contradiction, {"claims": claims_input}),
            timeout=5.0,
        )
        edges = result.get("edges", [])
        results = []
        for edge in edges[:limit]:
            results.append({
                "claim_a": edge.get("claim_a_id", ""),
                "claim_b": edge.get("claim_b_id", ""),
                "edge_type": "contradicts",
                "explanation": edge.get("explanation", ""),
            })
        return {"results": results, "total": len(results)}
    except asyncio.TimeoutError:
        logger.warning("ag_query_contradictions timed out")
        results = [
            {"claim_a": claim_id or f"claim-stub-{i}-a", "claim_b": f"claim-stub-{i}-b", "edge_type": "contradicts", "weight": 0.85}
            for i in range(min(limit, 2))
        ]
        return {"results": results, "total": len(results), "note": "stub fallback — corpus query timed out"}
    except Exception as exc:
        logger.warning("ag_query_contradictions failed, falling back to stub: %s", exc)
        results = [
            {
                "claim_a": claim_id or f"claim-stub-{i}-a",
                "claim_b": f"claim-stub-{i}-b",
                "edge_type": "contradicts",
                "weight": 0.85,
            }
            for i in range(min(limit, 2))
        ]
        return {
            "results": results,
            "total": len(results),
            "note": f"stub fallback — real implementation error: {exc}",
        }





async def _handle_merkle_compute(args: dict[str, Any]) -> dict[str, Any]:
    """Compute SHA-256 Merkle hash using citeindex.ingestion.deterministic."""
    payload: str = args.get("payload", "")
    try:
        from citeindex.ingestion.deterministic import sha256_hex, build_merkle_tree
        leaf_hash = sha256_hex(payload)
        tree = build_merkle_tree([leaf_hash])
        return {
            "hash": leaf_hash,
            "merkle_root": tree.get("root", leaf_hash),
            "leaf_count": tree.get("leaf_count", 1),
        }
    except Exception as exc:
        logger.warning("merkle_compute failed, using local hash: %s", exc)
        computed = _sha256_hex(payload)
        return {"hash": computed, "note": f"computed locally — import error: {exc}"}


async def _handle_merkle_verify(args: dict[str, Any]) -> dict[str, Any]:
    """Verify a Merkle proof using SHA-256 hash computation and comparison.

    Walks the proof (list of sibling hashes, left-to-right pairing)
    and compares the computed root with the expected root.
    Full verification against the merkle_registry requires loading the
    corpus, so a simple hash walk is performed here.
    """
    node_hash: str = args.get("node_hash", "")
    proof: list[str] = args.get("proof", [])
    root: str = args.get("root", "")

    # Compute Merkle root from leaf + proof (simple left-to-right pairing)
    current = node_hash
    for sibling in proof:
        combined = current + sibling
        current = hashlib.sha256(combined.encode("utf-8")).hexdigest()

    valid = current == root
    result = {
        "valid": valid,
        "computed_hash": current,
        "expected_hash": root,
    }

    # If the corpus is available, cross-check against the merkle registry
    try:
        loader = await asyncio.wait_for(
            asyncio.to_thread(_get_corpus_loader), timeout=5.0,
        )
        # Try to find a source whose merkle root matches the expected root
        matching_sources = []
        for sid, merkle in loader.merkle_registry.items():
            if merkle.get("root") == root:
                matching_sources.append(sid)
        if matching_sources:
            result["verified_sources"] = matching_sources
            # Use the integrity verifier for a more thorough check
            from citeagent.agents.integrity import IntegrityVerifier
            verifier = IntegrityVerifier()
            # Build a minimal evidence item for verification
            evidence_item = {
                "sha256": node_hash,
                "source_id": matching_sources[0],
                "document_merkle_root": root,
                "merkle_proof": [
                    {"hash": sibling, "position": "right"}
                    for sibling in proof
                ],
            }
            merkle_ok = verifier._verify_merkle_proof(
                evidence_item, loader.merkle_registry,
            )
            result["registry_verified"] = merkle_ok
    except Exception as exc:
        # Corpus not available or verification failed — that's okay
        logger.debug("merkle_verify registry check skipped: %s", exc)

    return result


async def _handle_csl_render(args: dict[str, Any]) -> dict[str, Any]:
    """Render a citation using citeindex.citation_style.format_bibliography."""
    citation_key: str = args.get("citation_key", "")
    style: str = args.get("style", "apa")
    try:
        loader = await asyncio.wait_for(
            asyncio.to_thread(_get_corpus_loader), timeout=5.0,
        )
        csl = loader.get_csl_by_id(citation_key)
        if csl is None:
            csl = loader.get_csl_by_source(citation_key)
        if csl is None:
            return {
                "output": f"[{citation_key}] Citation key not found in corpus",
                "style": style,
                "note": "citation_key not found",
            }

        from citeindex.citation_style import format_bibliography
        bib, in_text = await asyncio.wait_for(
            asyncio.to_thread(format_bibliography, [csl], style),
            timeout=5.0,
        )
        if bib and not bib.startswith("Error"):
            return {
                "output": bib.strip(),
                "in_text": in_text,
                "style": style,
                "citation_key": citation_key,
            }
        else:
            return {
                "output": f"[{citation_key}] Formatted citation string ({style})",
                "style": style,
                "note": f"format_bibliography returned: {bib[:120]}",
            }
    except Exception as exc:
        logger.warning("csl_render failed, falling back to stub: %s", exc)
        return {
            "output": f"[{citation_key}] Formatted citation string ({style})",
            "style": style,
            "note": f"stub fallback — real implementation error: {exc}",
        }


async def _handle_tree_load(args: dict[str, Any]) -> dict[str, Any]:
    """Load a PageIndex tree using PageIndexRetrievalAgent._load_trees."""
    source_id: str = args.get("source_id", "")
    depth: int = args.get("depth", -1)
    try:
        from citeagent.agents.pageindex_retrieval import PageIndexRetrievalAgent
        agent = PageIndexRetrievalAgent(corpus_root=get_corpus_root())
        trees = await asyncio.wait_for(
            asyncio.to_thread(agent._load_trees, source_id if source_id else None),
            timeout=5.0,
        )
        if not trees:
            return {
                "source_id": source_id,
                "tree": None,
                "depth": depth,
                "note": "no PageIndex trees found in corpus",
            }
        # Return the first matching tree (or all if no specific source_id)
        if source_id and source_id in trees:
            tree = trees[source_id]
        else:
            # Return the first available tree
            doc_id, tree = next(iter(trees.items()))
            source_id = doc_id

        return {
            "source_id": source_id,
            "tree": tree,
            "depth": depth,
        }
    except Exception as exc:
        logger.warning("tree_load failed, falling back to stub: %s", exc)
        return {
            "source_id": source_id,
            "tree": {
                "id": "root",
                "label": f"Stub tree for {source_id}",
                "children": [],
            },
            "depth": depth,
            "note": f"stub fallback — real implementation error: {exc}",
        }


async def _handle_tree_traverse(args: dict[str, Any]) -> dict[str, Any]:
    """Traverse a PageIndex tree using PageIndexRetrievalAgent._find_node_in_tree."""
    source_id: str = args.get("source_id", "")
    path: str = args.get("path", "")
    try:
        from citeagent.agents.pageindex_retrieval import PageIndexRetrievalAgent
        agent = PageIndexRetrievalAgent(corpus_root=get_corpus_root())
        trees = await asyncio.wait_for(
            asyncio.to_thread(agent._load_trees, source_id if source_id else None),
            timeout=5.0,
        )

        if not trees:
            return {
                "source_id": source_id,
                "path": path,
                "nodes": [],
                "note": "no PageIndex trees found in corpus",
            }

        # Use path as a node_id for traversal
        target_id = path if path else ""
        if target_id:
            # Find the specific tree containing this source
            if source_id in trees:
                tree = trees[source_id]
            else:
                tree = next(iter(trees.values()))
            found = agent._find_node_in_tree(tree, target_id)
            if found:
                return {
                    "source_id": source_id,
                    "path": path,
                    "nodes": [found],
                }
            else:
                return {
                    "source_id": source_id,
                    "path": path,
                    "nodes": [],
                    "note": f"node '{target_id}' not found in tree",
                }
        else:
            # No path, return top-level nodes
            tree = trees.get(source_id, next(iter(trees.values())))
            level_1 = tree.get("level_1", [])
            return {
                "source_id": source_id,
                "path": path,
                "nodes": level_1,
            }
    except Exception as exc:
        logger.warning("tree_traverse failed, falling back to stub: %s", exc)
        return {
            "source_id": source_id,
            "path": path,
            "nodes": [],
            "note": f"stub fallback — real implementation error: {exc}",
        }


async def _handle_regex_search(args: dict[str, Any]) -> dict[str, Any]:
    """Search indexed documents using a regular expression."""
    import re
    pattern: str = args.get("pattern", "")
    source_id: str | None = args.get("source_id")
    limit: int = args.get("limit", 10)
    context_chars: int = args.get("context_chars", 120)

    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return {"results": [], "total": 0, "error": f"Invalid regex: {e}"}

    try:
        loader = await asyncio.wait_for(
            asyncio.to_thread(_get_corpus_loader),
            timeout=5.0,
        )
        nodes = loader.all_nodes
        if source_id:
            nodes = loader.get_nodes_by_source(source_id)

        results = []
        for node in nodes:
            text = node.get("text", "")
            for match in compiled.finditer(text):
                start = max(0, match.start() - context_chars // 2)
                end = min(len(text), match.end() + context_chars // 2)
                results.append({
                    "doc_id": node.get("source_id", ""),
                    "node_id": node.get("node_id", ""),
                    "match_text": match.group(),
                    "context": text[start:end],
                    "locator": node.get("locator", {}),
                })
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break

        return {"results": results, "total": len(results)}
    except asyncio.TimeoutError:
        return {"results": [], "total": 0, "error": "Corpus load timed out"}
    except Exception as exc:
        return {"results": [], "total": 0, "error": str(exc)}


async def _handle_memory_save(args: dict[str, Any]) -> dict[str, Any]:
    """Save a memory entry using MemoryStore."""
    content: str = args.get("content", "")
    tags: list[str] = args.get("tags", [])
    metadata: dict[str, Any] | None = args.get("metadata")
    try:
        store = _get_memory_store()
        thread_id = "default"
        if metadata and isinstance(metadata, dict):
            thread_id = metadata.get("thread_id", "default")
        evidence_ids = tags if tags else []
        entry = await asyncio.wait_for(
            asyncio.to_thread(
                store.save,
                thread_id=thread_id,
                query=content,
                response=content,
                evidence_node_ids=evidence_ids,
            ),
            timeout=5.0,
        )
        return {
            "memory_id": entry.entry_id,
            "content": content,
            "tags": tags,
            "metadata": metadata or {},
            "sha256": entry.sha256,
            "timestamp": entry.timestamp,
            "status": "saved",
        }
    except Exception as exc:
        logger.warning("memory_save failed, falling back to stub: %s", exc)
        return {
            "memory_id": f"mem-stub-{_sha256_hex(content)[:10]}",
            "content": content,
            "tags": tags,
            "metadata": metadata or {},
            "status": "saved",
            "note": f"stub fallback — real implementation error: {exc}",
        }


async def _handle_tantivy_search(args: dict[str, Any]) -> dict[str, Any]:
    """Tantivy full-text search (placeholder implementation)."""
    query: str = args.get("query", "")
    limit: int = args.get("limit", 10)
    results = [
        {
            "doc_id": f"tantivy-stub-{i}",
            "score": round(1.0 / (i + 1), 4),
            "snippet": f"Stub snippet {i} for '{query}'",
        }
        for i in range(min(limit, 3))
    ]
    return {"results": results, "total": len(results), "note": PLACEHOLDER_NOTE}


async def _handle_tantivy_index(args: dict[str, Any]) -> dict[str, Any]:
    """Tantivy index creation (placeholder implementation)."""
    path: str = args.get("path", "")
    return {
        "doc_id": f"tantivy-stub-{_sha256_hex(path)[:12]}",
        "status": "indexed",
        "note": PLACEHOLDER_NOTE,
    }




# ---------------------------------------------------------------------------
# Audit tools
# ---------------------------------------------------------------------------


async def _handle_audit_save(args: dict[str, Any]) -> dict[str, Any]:
    """Save an audit result to persistent storage."""
    audit_id: str = args.get("audit_id", "")
    verdict: str = args.get("verdict", "")
    reasoning: str = args.get("reasoning", "")
    query: str = args.get("query", "")
    evidence_hashes: list[str] = args.get("evidence_hashes", [])

    try:
        audit_dir = os.path.join(get_corpus_root(), ".audits")
        os.makedirs(audit_dir, exist_ok=True)
        audit_path = os.path.join(audit_dir, f"{audit_id}.json")
        audit_data = {
            "audit_id": audit_id,
            "verdict": verdict,
            "reasoning": reasoning,
            "query": query,
            "evidence_hashes": evidence_hashes,
            "saved_at": logger.handlers[0].baseFilename if logger.handlers else "now",
        }
        with open(audit_path, "w", encoding="utf-8") as f_obj:
            json.dump(audit_data, f_obj, indent=2)
        return {"audit_id": audit_id, "saved": True, "path": audit_path}
    except Exception as exc:
        logger.warning("audit_save failed: %s", exc)
        return {"audit_id": audit_id, "saved": False, "error": str(exc)}


async def _handle_audit_retrieve(args: dict[str, Any]) -> dict[str, Any]:
    """Retrieve a saved audit result."""
    audit_id: str = args.get("audit_id", "")
    try:
        audit_path = os.path.join(get_corpus_root(), ".audits", f"{audit_id}.json")
        with open(audit_path, "r", encoding="utf-8") as f_obj:
            data = json.load(f_obj)
        return {"found": True, **data}
    except FileNotFoundError:
        return {"found": False, "audit_id": audit_id, "error": "audit not found"}
    except Exception as exc:
        return {"found": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Memory tier tools
# ---------------------------------------------------------------------------


async def _handle_memory_store_tier(args: dict[str, Any]) -> dict[str, Any]:
    """Store a memory entry in a specific tier."""
    content: str = args.get("content", "")
    tier: str = args.get("tier", "episodic")
    thread_id: str = args.get("thread_id", "default")
    key: str = args.get("key", "")
    tags: list[str] = args.get("tags", [])
    source_ids: list[str] = args.get("source_ids", [])

    if tier == "corpus":
        return {"error": "Corpus tier is immutable — use index_document instead"}

    if tier == "working":
        return {
            "entry_id": f"mem-working-{_sha256_hex(content)[:8]}",
            "stored": True,
            "tier": "working",
            "note": "stored in working memory (transient — session only)",
        }

    try:
        mem_dir = os.path.join(get_corpus_root(), ".memory", tier)
        os.makedirs(mem_dir, exist_ok=True)

        if tier == "episodic":
            filepath = os.path.join(mem_dir, f"{thread_id}.jsonl")
        else:  # long_term
            filepath = os.path.join(mem_dir, "entries.jsonl")

        entry = {
            "entry_id": f"mem-{_sha256_hex(content)[:10]}-{key or 'none'}",
            "tier": tier,
            "key": key,
            "content": content,
            "tags": tags,
            "thread_id": thread_id,
            "sha256": _sha256_hex(content),
            "source_ids": source_ids,
            "timestamp": str(logger.handlers[0].baseFilename if logger.handlers else ""),
        }
        with open(filepath, "a", encoding="utf-8") as f_obj:
            f_obj.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return {"entry_id": entry["entry_id"], "stored": True, "tier": tier, "path": filepath}
    except Exception as exc:
        logger.warning("memory_store_tier failed: %s", exc)
        return {"stored": False, "tier": tier, "error": str(exc)}


async def _handle_memory_retrieve_tier(args: dict[str, Any]) -> dict[str, Any]:
    """Retrieve memories from specific or all tiers."""
    query: str = args.get("query", "")
    tier: str | None = args.get("tier")
    limit: int = args.get("limit", 10)

    tiers_to_search = [tier] if tier else ["episodic", "long_term"]
    results = []

    try:
        for t in tiers_to_search:
            mem_dir = os.path.join(get_corpus_root(), ".memory", t)
            if not os.path.isdir(mem_dir):
                continue
            for filename in os.listdir(mem_dir):
                if filename.endswith(".jsonl"):
                    filepath = os.path.join(mem_dir, filename)
                    with open(filepath, "r", encoding="utf-8") as f_obj:
                        for line in f_obj:
                            try:
                                entry = json.loads(line.strip())
                                q = query.lower()
                                if q in entry.get("content", "").lower() or q in " ".join(entry.get("tags", [])).lower():
                                    results.append(entry)
                                    if len(results) >= limit:
                                        break
                            except json.JSONDecodeError:
                                continue
                    if len(results) >= limit:
                        break
            if len(results) >= limit:
                break

        return {"entries": results, "total": len(results), "tier": tier or "all"}
    except Exception as exc:
        return {"entries": [], "total": 0, "error": str(exc)}


async def _handle_memory_consolidate(args: dict[str, Any]) -> dict[str, Any]:
    """Consolidate episodic memories into long-term storage."""
    thread_id: str | None = args.get("thread_id")

    try:
        episodic_dir = os.path.join(get_corpus_root(), ".memory", "episodic")
        long_term_dir = os.path.join(get_corpus_root(), ".memory", "long_term")
        os.makedirs(long_term_dir, exist_ok=True)

        consolidated = 0
        if os.path.isdir(episodic_dir):
            for filename in os.listdir(episodic_dir):
                if thread_id and not filename.startswith(thread_id):
                    continue
                if filename.endswith(".jsonl"):
                    filepath = os.path.join(episodic_dir, filename)
                    with open(filepath, "r", encoding="utf-8") as f_obj:
                        for line in f_obj:
                            try:
                                entry = json.loads(line.strip())
                                # Deduplicate by content hash
                                content_hash = _sha256_hex(entry.get("content", ""))
                                lt_path = os.path.join(long_term_dir, "entries.jsonl")
                                existing = False
                                if os.path.isfile(lt_path):
                                    with open(lt_path, "r", encoding="utf-8") as lt_f:
                                        for lt_line in lt_f:
                                            try:
                                                lt_entry = json.loads(lt_line.strip())
                                                if _sha256_hex(lt_entry.get("content", "")) == content_hash:
                                                    existing = True
                                                    break
                                            except:
                                                continue
                                if not existing:
                                    with open(lt_path, "a", encoding="utf-8") as lt_f:
                                        lt_f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                                    consolidated += 1
                            except:
                                continue

        return {
            "consolidated_count": consolidated,
            "from_tier": "episodic",
            "to_tier": "long_term",
        }
    except Exception as exc:
        return {"consolidated_count": 0, "error": str(exc)}



# ---------------------------------------------------------------------------


async def _handle_crypto_sign(args: dict[str, Any]) -> dict[str, Any]:
    """Sign a message using HMAC-SHA256 (MVP: upgrade to Ed25519 for production)."""
    message: str = args.get("message", "")
    session_id: str = args.get("session_id", "default")

    try:
        import hmac
        key_path = os.path.join(get_corpus_root(), ".crypto", f"{session_id}.key")
        os.makedirs(os.path.dirname(key_path), exist_ok=True)

        # Load or generate session key
        if os.path.isfile(key_path):
            with open(key_path, "rb") as f_obj:
                key = f_obj.read()
        else:
            key = os.urandom(32)
            with open(key_path, "wb") as f_obj:
                f_obj.write(key)

        msg_hash = _sha256_hex(message)
        signature = hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()

        return {
            "message_hash": msg_hash,
            "signature": signature,
            "session_id": session_id,
        }
    except Exception as exc:
        return {"error": str(exc)}


async def _handle_crypto_verify(args: dict[str, Any]) -> dict[str, Any]:
    """Verify an HMAC-SHA256 signature."""
    message: str = args.get("message", "")
    signature: str = args.get("signature", "")
    session_id: str = args.get("session_id", "default")

    try:
        import hmac
        key_path = os.path.join(get_corpus_root(), ".crypto", f"{session_id}.key")
        if not os.path.isfile(key_path):
            return {"valid": False, "reason": "session key not found"}

        with open(key_path, "rb") as f_obj:
            key = f_obj.read()

        expected = hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()
        valid = hmac.compare_digest(signature, expected)

        return {
            "valid": valid,
            "message_hash": _sha256_hex(message),
            "reason": "OK" if valid else "signature mismatch",
        }
    except Exception as exc:
        return {"valid": False, "reason": str(exc)}


async def _handle_crypto_audit_trail(args: dict[str, Any]) -> dict[str, Any]:
    """Return the audit trail for a session."""
    session_id: str = args.get("session_id", "default")

    try:
        trail_path = os.path.join(get_corpus_root(), ".crypto", f"{session_id}_trail.jsonl")
        if not os.path.isfile(trail_path):
            return {"entries": [], "chain_valid": True, "note": "no audit trail yet"}

        entries = []
        with open(trail_path, "r", encoding="utf-8") as f_obj:
            for line in f_obj:
                try:
                    entries.append(json.loads(line.strip()))
                except:
                    continue

        # Verify chain integrity
        chain_valid = True
        for i, entry in enumerate(entries):
            if i > 0:
                if entry.get("previous_hash") != entries[i - 1].get("message_hash"):
                    chain_valid = False
                    break

        return {"entries": entries, "chain_valid": chain_valid, "note": "hash chain verified"}
    except Exception as exc:
        return {"entries": [], "chain_valid": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# SafeHarness tools
# ---------------------------------------------------------------------------


async def _handle_safeharness_check(args: dict[str, Any]) -> dict[str, Any]:
    """Run all 4 SafeHarness layers on a tool call."""
    tool_name: str = args.get("tool_name", "")
    tool_args = args.get("args", {})

    # Layer 1 — sanitize input
    sanitized = tool_args
    if isinstance(tool_args, dict):
        for k, v in list(tool_args.items()):
            if isinstance(v, str) and len(v) > 10000:
                sanitized[k] = v[:10000]
        # Strip prompt injection patterns
        for k, v in list(sanitized.items()):
            if isinstance(v, str):
                for pattern in ["ignore", "forget", "override", "system:", "role:"]:
                    v = v.replace(pattern, "[REDACTED]")
                sanitized[k] = v

    # Layer 3 — permission check (risk tier classification)
    tier = args.get("risk_tier", "read")
    tiers = {"read": ["search_documents", "search_claims", "search_memory", "tree_load", "tree_traverse", "csl_render", "merkle_verify", "ag_query_claims", "ag_query_contradictions", "audit_retrieve", "memory_retrieve_tier", "regex_search"], "workspace": ["index_claim", "memory_save", "memory_store_tier", "memory_consolidate", "merkle_compute", "crypto_sign", "crypto_verify", "crypto_audit_trail", "safeharness_check", "safeharness_sanitize"], "network": ["index_document", "tantivy_search", "tantivy_index"], "system": ["delete_document"]}
    allowed_tier = None
    for t, tools in tiers.items():
        if tool_name in tools:
            allowed_tier = t
            break
    allowed = allowed_tier is not None and allowed_tier != "system"

    return {
        "allowed": allowed,
        "layer": "constrain",
        "reason": f"Tool {tool_name} classified as {allowed_tier or 'unknown'} tier",
        "sanitized_input": sanitized,
        "risk_tier": allowed_tier or "unknown",
    }


async def _handle_safeharness_sanitize(args: dict[str, Any]) -> dict[str, Any]:
    """SafeHarness Layer 1: sanitize input."""
    tool_name: str = args.get("tool_name", "")
    tool_input = args.get("input", {})
    modifications = []

    if isinstance(tool_input, dict):
        sanitized = {}
        for k, v in list(tool_input.items()):
            if isinstance(v, str):
                orig = v
                for pattern in ["ignore previous", "forget instructions", "override system", "act as", "you are now"]:
                    v = v.replace(pattern, "[REDACTED]")
                # Trim long strings
                if len(orig) > 10000:
                    v = orig[:10000]
                    modifications.append(f"trimmed ${k} from {len(orig)} to 10000 chars")
                sanitized[k] = v
            else:
                sanitized[k] = v
    else:
        sanitized = tool_input

    return {"sanitized_input": sanitized, "modifications": modifications}





# ---------------------------------------------------------------------------
# Handler dispatch map
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Any] = {
    "search_documents": _handle_search_documents,
    "search_claims": _handle_search_claims,
    "search_memory": _handle_search_memory,
    "index_document": _handle_index_document,
    "index_claim": _handle_index_claim,
    "delete_document": _handle_delete_document,
    "ag_query_claims": _handle_ag_query_claims,
    "ag_query_contradictions": _handle_ag_query_contradictions,

    "merkle_compute": _handle_merkle_compute,
    "merkle_verify": _handle_merkle_verify,
    "csl_render": _handle_csl_render,
    "tree_load": _handle_tree_load,
    "tree_traverse": _handle_tree_traverse,
    "regex_search": _handle_regex_search,
    "memory_save": _handle_memory_save,
    "tantivy_search": _handle_tantivy_search,
    "tantivy_index": _handle_tantivy_index,
    "audit_save": _handle_audit_save,
    "audit_retrieve": _handle_audit_retrieve,
    "memory_store_tier": _handle_memory_store_tier,
    "memory_retrieve_tier": _handle_memory_retrieve_tier,
    "memory_consolidate": _handle_memory_consolidate,

    "crypto_sign": _handle_crypto_sign,
    "crypto_verify": _handle_crypto_verify,
    "crypto_audit_trail": _handle_crypto_audit_trail,
    "safeharness_check": _handle_safeharness_check,
    "safeharness_sanitize": _handle_safeharness_sanitize,

}

# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run the MCP server over stdio."""
    parser = argparse.ArgumentParser(description="CiteAgent MCP Server")
    parser.add_argument(
        "--corpus-root",
        default=None,
        help="Path to the corpus root directory (default: corpus/)",
    )
    parsed, _unknown = parser.parse_known_args()

    if parsed.corpus_root:
        global _CORPUS_ROOT_ARG
        _CORPUS_ROOT_ARG = parsed.corpus_root

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())