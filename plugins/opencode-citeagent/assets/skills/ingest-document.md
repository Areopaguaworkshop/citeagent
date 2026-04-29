---
description: Ingest a document (PDF, URL, media) into the academic corpus with Merkle verification
---

# Ingest Document Skill

## When to Use
- User provides a PDF, URL, or media file to add to the corpus
- User asks to index, import, or process a document
- User wants to make a source searchable via `cite_search`

## Steps

1. **Detect type**: Identify the resource type from the URL or file extension
   - Digital PDF (`.pdf`): GROBID metadata extraction
   - Scanned PDF: OCR pipeline (OCRmyPDF → Tesseract)
   - URL Article (`http(s)://`): Playwright/trafilatura fetch
   - Media (`.mp3`, `.mp4`, `.wav`, `.mkv`): yt-dlp → WhisperX transcription
   - Office (`.docx`, `.pptx`, `.xlsx`): LibreOffice conversion → PDF pipeline
   - DJVU (`.djvu`): ddjvu conversion → PDF pipeline

2. **Ingest via tool**: Call `cite_ingest` with the source path/URL
   ```
   cite_ingest(source="https://arxiv.org/pdf/2401.12345", force=false)
   ```

3. **Verify ingestion**: Check the returned document ID and Merkle root hash
   - If ingestion fails, check error message and retry with `force=true`
   - If partial ingestion, note which sections were processed

4. **Validate Merkle tree**: Call `cite_verify` on the document root
   ```
   cite_verify(node_hash=<root_hash>, proof=[], root=<root_hash>)
   ```

5. **Confirm index**: Call `cite_search` with a query from the document title to confirm it's indexed

6. **Report**: Return document ID, Merkle root, section count, and indexing status

## Output Format
```
INGESTION REPORT
================
Document ID: <source_id>
Merkle Root: <root_hash>
Sections: <count>
Pages: <count>
Index Status: INDEXED / PARTIAL / FAILED
Evidence Chain: Valid / Invalid
```

## Error Handling
- If URL is unreachable, suggest alternative sources
- If PDF is encrypted, ask user for passphrase or suggest OCR fallback
- If media transcription fails, report language detection issues
- Never skip Merkle verification — an unverified document cannot be cited
