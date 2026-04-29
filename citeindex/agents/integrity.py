"""Integrity Verifier Agent — cryptographic and citation integrity checks.

Matches ``.agent/agent/integrity.md`` and skill ``integrity-verifier.yaml``.

Fail-closed: default to rejection if verification state is unknown.
"""

import logging
from typing import Any, Dict, List, Optional

from .models import IntegrityCheck, IntegrityReport, SCHEMA_VERSION

logger = logging.getLogger(__name__)


class IntegrityVerifier:
    """Verify hashes, Merkle proofs, and citation references."""

    def __init__(self, schema_version: str = SCHEMA_VERSION) -> None:
        self.schema_version = schema_version

    def verify(
        self,
        answer_machine: Dict[str, Any],
        nodes: List[Dict[str, Any]],
        merkle_registry: Dict[str, Dict[str, Any]],
        csl_registry: List[Dict[str, Any]],
    ) -> IntegrityReport:
        checks: List[Dict[str, Any]] = []
        violations: List[str] = []

        # Build lookups
        node_map: Dict[str, Dict[str, Any]] = {n["node_id"]: n for n in nodes}
        csl_keys: set = set()
        for csl in csl_registry:
            csl_keys.add(csl.get("id", ""))
            csl_keys.add(csl.get("_source_id", ""))

        evidence = answer_machine.get("evidence", [])

        if not evidence:
            return IntegrityReport(
                schema_version=self.schema_version,
                status="rejected",
                checks=checks,
                violations=["No evidence items in answer"],
            )

        for item in evidence:
            node_id = item.get("node_id", "")

            # Check 1: Node exists
            node = node_map.get(node_id)
            node_exists = node is not None
            checks.append(IntegrityCheck(
                check_type="node_exists",
                node_id=node_id,
                passed=node_exists,
                detail="Node found in corpus" if node_exists else "Node not found",
            ).to_dict())
            if not node_exists:
                violations.append(f"Node {node_id} not found in corpus")
                continue

            # Check 2: Hash verification
            hash_ok = self._verify_hash(node, item)
            checks.append(IntegrityCheck(
                check_type="hash_match",
                node_id=node_id,
                passed=hash_ok,
                detail="SHA256 matches" if hash_ok else "SHA256 mismatch",
            ).to_dict())
            if not hash_ok:
                violations.append(f"Hash mismatch for node {node_id}")

            # Check 3: Merkle proof verification
            merkle_ok = self._verify_merkle_proof(item, merkle_registry)
            checks.append(IntegrityCheck(
                check_type="merkle_proof",
                node_id=node_id,
                passed=merkle_ok,
                detail="Merkle proof valid" if merkle_ok else "Merkle proof invalid or missing",
            ).to_dict())
            if not merkle_ok:
                violations.append(f"Merkle proof failed for node {node_id}")

            # Check 4: Citation key resolves
            citation_key = item.get("citation_key", "")
            source_id = item.get("source_id", "")
            csl_ok = (
                citation_key != ""
                and (source_id in csl_keys or citation_key in csl_keys or
                     any(c.get("_source_id") == source_id for c in csl_registry))
            )
            checks.append(IntegrityCheck(
                check_type="citation_resolved",
                node_id=node_id,
                passed=csl_ok,
                detail="Citation key resolves" if csl_ok else "Citation key not found in CSL registry",
            ).to_dict())
            if not csl_ok:
                violations.append(f"Citation key '{citation_key}' not resolved for node {node_id}")

        # Check 5: Every claim has evidence (answer is non-empty implies evidence exists)
        answer = answer_machine.get("answer", "")
        if answer and not evidence:
            violations.append("Answer contains text but no evidence items")

        # Determine status
        if violations:
            status = "rejected"
        else:
            status = "approved"

        approved_ref = ""
        if status == "approved":
            from ..ingestion.deterministic import hash_payload
            approved_ref = hash_payload(answer_machine)

        return IntegrityReport(
            schema_version=self.schema_version,
            status=status,
            checks=checks,
            violations=violations,
            approved_answer_ref=approved_ref,
        )

    # ------------------------------------------------------------------
    # Verification helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _verify_hash(node: Dict[str, Any], evidence_item: Dict[str, Any]) -> bool:
        """Recompute node hash and compare with evidence."""
        from ..ingestion.deterministic import hash_payload

        text = node.get("text", "")
        if not text:
            return False

        recomputed = hash_payload(text)
        evidence_hash = evidence_item.get("sha256", "")
        node_hash = node.get("sha256", "")

        return recomputed == evidence_hash and recomputed == node_hash

    @staticmethod
    def _verify_merkle_proof(
        evidence_item: Dict[str, Any],
        merkle_registry: Dict[str, Dict[str, Any]],
    ) -> bool:
        """Verify the Merkle proof leads to the claimed document root."""
        from ..ingestion.deterministic import sha256_hex

        source_id = evidence_item.get("source_id", "")
        merkle = merkle_registry.get(source_id, {})
        claimed_root = evidence_item.get("document_merkle_root", "")
        proof = evidence_item.get("merkle_proof", [])
        leaf_hash = evidence_item.get("sha256", "")

        if not claimed_root or not merkle:
            return False

        actual_root = merkle.get("root", "")
        if claimed_root != actual_root:
            return False

        if not proof:
            # No proof path — check if leaf is directly in the tree
            levels = merkle.get("levels", [])
            if levels and leaf_hash in levels[0]:
                # Single-leaf or leaf is present; acceptable if tree has only 1 level
                if len(levels) == 1:
                    return leaf_hash == actual_root
                # Otherwise, we need a proof
                return False
            return False

        # Walk the proof
        current = leaf_hash
        for step in proof:
            sibling = step.get("hash", "")
            position = step.get("position", "")
            if position == "left":
                current = sha256_hex(sibling + current)
            else:
                current = sha256_hex(current + sibling)

        return current == claimed_root
