"""File-based JSONL memory persistence for chat threads.

Stores query + response pairs as JSONL.  Each entry is hashed into a
Merkle DAG per Summary.md.  PostgreSQL migration deferred to Tier 3.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .models import MemoryEntry, SCHEMA_VERSION

logger = logging.getLogger(__name__)


class MemoryStore:
    """JSONL-backed memory store with per-thread files."""

    def __init__(self, memory_dir: str = "corpus/.memory") -> None:
        self.memory_dir = os.path.abspath(memory_dir)
        os.makedirs(self.memory_dir, exist_ok=True)

    def save(
        self,
        thread_id: str,
        query: str,
        response: str,
        evidence_node_ids: Optional[List[str]] = None,
    ) -> MemoryEntry:
        from ..ingestion.deterministic import hash_payload

        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        payload = f"{timestamp}|{query}|{response}"
        entry_hash = hash_payload(payload)

        entry = MemoryEntry(
            entry_id=entry_hash[:16],
            timestamp=timestamp,
            thread_id=thread_id,
            query=query,
            response=response,
            evidence_node_ids=evidence_node_ids or [],
            sha256=entry_hash,
        )

        path = self._thread_path(thread_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False, sort_keys=True))
            f.write("\n")

        logger.info("Memory saved: entry_id=%s thread=%s", entry.entry_id, thread_id)
        return entry

    def load_thread(self, thread_id: str) -> List[MemoryEntry]:
        path = self._thread_path(thread_id)
        if not os.path.exists(path):
            return []

        entries: List[MemoryEntry] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entries.append(MemoryEntry(**data))
                except Exception:
                    logger.warning("Skipping malformed memory entry", exc_info=True)
        return entries

    def search(self, query: str, thread_id: Optional[str] = None) -> List[MemoryEntry]:
        """Simple keyword search across memory entries."""
        from .indexing import tokenize

        query_tokens = set(tokenize(query))
        if not query_tokens:
            return []

        results: List[tuple] = []

        if thread_id:
            threads = [thread_id]
        else:
            threads = self._list_threads()

        for tid in threads:
            entries = self.load_thread(tid)
            for entry in entries:
                entry_tokens = set(tokenize(entry.query + " " + entry.response))
                overlap = len(query_tokens & entry_tokens)
                if overlap > 0:
                    results.append((overlap, entry))

        results.sort(key=lambda x: -x[0])
        return [entry for _, entry in results]

    def build_merkle_dag(self, thread_id: str) -> Dict[str, Any]:
        """Build a Merkle DAG for a thread's memory entries."""
        from ..ingestion.deterministic import build_merkle_tree

        entries = self.load_thread(thread_id)
        leaf_hashes = [e.sha256 for e in entries if e.sha256]
        if not leaf_hashes:
            return {"root": "", "leaf_count": 0}
        return build_merkle_tree(leaf_hashes)

    def _thread_path(self, thread_id: str) -> str:
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in thread_id)
        return os.path.join(self.memory_dir, f"{safe_id}.jsonl")

    def _list_threads(self) -> List[str]:
        threads: List[str] = []
        if not os.path.isdir(self.memory_dir):
            return threads
        for fname in sorted(os.listdir(self.memory_dir)):
            if fname.endswith(".jsonl"):
                threads.append(fname[:-6])
        return threads
