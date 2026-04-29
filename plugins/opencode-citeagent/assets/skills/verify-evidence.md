---
description: Run full verification ladder on a set of evidence items to ensure Merkle integrity
---

# Verify Evidence Skill

## When to Use
- After generating any answer with citations
- Before publishing or committing findings
- When evidence integrity is questioned
- As a quality gate before final output

## Steps

1. **Collect items**: Identify all evidence items in the current answer
2. **L0 Schema**: Check all required fields present (node_id, source_id, sha256, merkle_proof, citation_key, citation_rendered)
3. **L1 Existence**: Verify each node_id exists in corpus via `cite_tree`
4. **L2 Hash**: Verify SHA-256 hash matches stored text via `cite_verify`
5. **L3 Merkle**: Verify Merkle proof from leaf to root via `cite_verify`
6. **L4 Citation**: Verify citation key resolves to valid CSL record via `cite_render`
7. **Report**: Generate verification result with pass/fail per item per rung
8. **Action**: If any item fails any rung → REJECT that item, remove from answer, flag for re-search

## Fail-Closed Rule
A single failed evidence item does NOT invalidate other items. Each item is independently verified. However, the overall answer integrity is marked as "degraded" if any item is rejected.

## Verification Output Format
```
VERIFICATION REPORT
==================
Overall: APPROVED / DEGRADED / REJECTED

Item 1: node s5.1.p5
  L0 Schema:     [PASS]
  L1 Existence:  [PASS]
  L2 Hash:       [PASS]
  L3 Merkle:     [PASS]
  L4 Citation:   [PASS]
  Status: APPROVED

Item 2: node s3.2.p1
  L0 Schema:     [PASS]
  L1 Existence:  [PASS]
  L2 Hash:       [FAIL: hash mismatch]
  L3 Merkle:     [SKIP: upstream failure]
  L4 Citation:   [SKIP: upstream failure]
  Status: REJECTED — removed from answer
```
