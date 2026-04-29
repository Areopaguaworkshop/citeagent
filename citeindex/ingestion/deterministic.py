import hashlib
import json
from typing import Any, Dict, List


def canonicalize_text(text: str) -> str:
    """Normalize text for deterministic hashing."""
    if text is None:
        return ""
    if not isinstance(text, str):
        return str(text) if text else ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "\n".join(lines).strip()


def canonical_json_dumps(data: Any) -> str:
    """Stable JSON serialization for hashing and artifact persistence."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def hash_payload(payload: Any) -> str:
    if isinstance(payload, str):
        normalized = canonicalize_text(payload)
    else:
        normalized = canonical_json_dumps(payload)
    return sha256_hex(normalized)


def build_merkle_tree(leaf_hashes: List[str]) -> Dict[str, Any]:
    """
    Build a deterministic Merkle tree.
    Odd nodes are duplicated at each level for deterministic pairing.
    """
    if not leaf_hashes:
        leaf_hashes = [sha256_hex("")]

    levels: List[List[str]] = [leaf_hashes[:]]
    while len(levels[-1]) > 1:
        current = levels[-1]
        nxt: List[str] = []
        for i in range(0, len(current), 2):
            left = current[i]
            right = current[i + 1] if i + 1 < len(current) else current[i]
            nxt.append(sha256_hex(left + right))
        levels.append(nxt)

    return {
        "algorithm": "sha256",
        "leaf_count": len(leaf_hashes),
        "levels": levels,
        "root": levels[-1][0],
    }


def build_hierarchical_merkle_tree(
    document_structure: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a hierarchical Merkle tree from document structure.

    Hierarchy: line → paragraph → column → page → document
    Per the YAML spec:
      paragraph = hash(lines)
      column = hash(paragraphs)
      page = hash(columns + footnotes)
      document = hash(pages)
    """
    proof_tree: Dict[str, Any] = {"pages": []}
    page_hashes: List[str] = []

    for page in document_structure.get("pages", []):
        page_number = page.get("page_number", 0)
        page_proof: Dict[str, Any] = {"page_number": page_number, "columns": [], "footnotes": []}
        column_hashes: List[str] = []

        columns = page.get("columns", [])
        if not columns:
            # Fall back to paragraphs directly (non-layout structure)
            paragraphs = page.get("paragraphs", [])
            if paragraphs:
                columns = [{"paragraphs": paragraphs}]

        for column in columns:
            col_proof: Dict[str, Any] = {"paragraphs": []}
            paragraph_hashes: List[str] = []

            for para in column.get("paragraphs", []):
                text = para.get("text", "")
                lines = para.get("lines", [])

                if lines:
                    line_hashes: List[str] = []
                    line_proofs: List[Dict[str, str]] = []
                    for line in lines:
                        canon = canonicalize_text(line)
                        lh = sha256_hex(canon)
                        line_hashes.append(lh)
                        line_proofs.append({"text": line, "hash": lh})
                    para_hash = sha256_hex("".join(line_hashes))
                    col_proof["paragraphs"].append({
                        "hash": para_hash,
                        "lines": line_proofs,
                    })
                else:
                    canon = canonicalize_text(text)
                    para_hash = sha256_hex(canon)
                    col_proof["paragraphs"].append({
                        "hash": para_hash,
                        "text": text,
                    })

                paragraph_hashes.append(para_hash)

            col_hash = sha256_hex("".join(paragraph_hashes)) if paragraph_hashes else sha256_hex("")
            col_proof["hash"] = col_hash
            column_hashes.append(col_hash)
            page_proof["columns"].append(col_proof)

        footnote_hashes: List[str] = []
        for fn in page.get("footnotes", []):
            fn_text = fn.get("text", "") if isinstance(fn, dict) else str(fn)
            canon = canonicalize_text(fn_text)
            fn_hash = sha256_hex(canon)
            footnote_hashes.append(fn_hash)
            page_proof["footnotes"].append({"text": fn_text, "hash": fn_hash})

        all_page_child_hashes = column_hashes + footnote_hashes
        pg_hash = sha256_hex("".join(all_page_child_hashes)) if all_page_child_hashes else sha256_hex("")
        page_proof["hash"] = pg_hash
        page_hashes.append(pg_hash)
        proof_tree["pages"].append(page_proof)

    doc_hash = sha256_hex("".join(page_hashes)) if page_hashes else sha256_hex("")

    return {
        "algorithm": "sha256",
        "root": doc_hash,
        "page_hashes": page_hashes,
        "proof_tree": proof_tree,
    }


def build_merkle_proof(tree: Dict[str, Any], leaf_index: int) -> List[Dict[str, str]]:
    levels = tree.get("levels", [])
    if not levels or leaf_index < 0 or leaf_index >= len(levels[0]):
        return []

    proof: List[Dict[str, str]] = []
    idx = leaf_index
    for level in levels[:-1]:
        sibling_idx = idx ^ 1
        if sibling_idx >= len(level):
            sibling_idx = idx
        position = "right" if sibling_idx > idx else "left"
        proof.append({"position": position, "hash": level[sibling_idx]})
        idx //= 2
    return proof
