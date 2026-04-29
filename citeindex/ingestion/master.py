import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from .deterministic import hash_payload
from .models import IngestionConfig, IngestionFailure, IngestionLogEntry, PipelineResult
from .pipelines import digital_pdf, media, scanned_pdf, url_article
from .markdown_export import write_library_markdown
from .storage import append_jsonl, csl_folder_name, ensure_dir, store_corpus_artifacts, write_json

logger = logging.getLogger(__name__)

# Extensions supported for conversion (merged from legacy utils.py)
_OFFICE_EXTENSIONS = {".docx", ".doc", ".rtf", ".odt", ".pptx", ".ppt", ".odp"}
_DJVU_EXTENSIONS = {".djvu"}
_MEDIA_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".mkv", ".webm"}


class CiteIndexIngestionOrchestrator:
    def __init__(self, corpus_root: str = "corpus", schema_version: str = "1.0.0"):
        self.corpus_root = os.path.abspath(corpus_root)
        self.schema_version = schema_version
        ensure_dir(self.corpus_root)

    def ingest(
        self,
        input_ref: str,
        config: Optional[IngestionConfig] = None,
    ) -> Dict[str, Any]:
        cfg = config or IngestionConfig()
        try:
            resource_type, normalized = self.detect_resource_type(input_ref)
            if resource_type == "unsupported":
                return self._failure(
                    stage="detect_resource_type",
                    source_id="unknown",
                    error_code="unsupported_input",
                    error_message=f"Unsupported input: {input_ref}",
                    next_action="Provide PDF, URL, or media file",
                )

            # Phase 1: Office/DJVU → convert to PDF before routing
            temp_pdf = None
            if resource_type == "office_document":
                temp_pdf = self._convert_office_to_pdf(normalized, cfg)
                if not temp_pdf:
                    return self._failure(
                        stage="office_conversion",
                        source_id="unknown",
                        error_code="conversion_failed",
                        error_message=f"Failed to convert Office document: {input_ref}",
                        next_action="Ensure LibreOffice is installed",
                    )
                resource_type = self._pdf_kind(temp_pdf)
                normalized = temp_pdf

            elif resource_type == "djvu_document":
                temp_pdf = self._convert_djvu_to_pdf(normalized, cfg)
                if not temp_pdf:
                    return self._failure(
                        stage="djvu_conversion",
                        source_id="unknown",
                        error_code="conversion_failed",
                        error_message=f"Failed to convert DJVU document: {input_ref}",
                        next_action="Ensure djvulibre-bin is installed",
                    )
                resource_type = self._pdf_kind(temp_pdf)
                normalized = temp_pdf

            try:
                sub_result = self.route_to_pipeline(resource_type, normalized, cfg)
            finally:
                # Clean up temp PDF from Office/DJVU conversion
                if temp_pdf and os.path.exists(temp_pdf):
                    os.remove(temp_pdf)
                    logger.info("Removed temporary conversion file: %s", temp_pdf)

            standardized_csl = self.standardize_csl_json(
                sub_result.csl_json,
                sub_result.merkle_tree or {},
                resource_type,
            )

            artifacts = sub_result.to_dict()
            artifacts["csl_json"] = standardized_csl

            folder_name = csl_folder_name(standardized_csl)
            document_path = store_corpus_artifacts(self.corpus_root, folder_name, artifacts)
            log_entry = self.log_ingestion(input_ref, resource_type, standardized_csl, sub_result)

            output = {
                "schema_version": self.schema_version,
                "status": "ok",
                "document_path": document_path,
                "standardized_csl_json": standardized_csl,
                "sub_pipeline_outputs": sub_result.to_dict(),
                "ingestion_log_entry": log_entry,
            }

            # Phase 1.5: Schema validation (best-effort)
            try:
                from .schema_validator import validate_ingestion_output

                errors = validate_ingestion_output(output)
                if errors:
                    logger.warning("Schema validation warnings: %s", errors)
                    output["schema_validation_warnings"] = errors
            except Exception:
                pass

            write_json(os.path.join(document_path, "ingestion_output.json"), output)

            # Generate human-readable library markdown
            try:
                library_md_path = write_library_markdown(
                    corpus_root=self.corpus_root,
                    csl_json=standardized_csl,
                    document_json=sub_result.document_json,
                    transcript_json=sub_result.transcript_json,
                    resource_type=resource_type,
                )
                output["library_md_path"] = library_md_path
            except Exception:
                logger.warning("Library markdown generation failed", exc_info=True)

            return output
        except Exception as e:
            return self._failure(
                stage="master_ingestion",
                source_id="unknown",
                error_code="ingestion_exception",
                error_message=str(e),
                next_action="Inspect stack trace and input file health",
            )

    def detect_resource_type(self, input_ref: str) -> tuple[str, str]:
        parsed = urlparse(input_ref)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            host = parsed.netloc.lower()
            if any(token in host for token in ["youtube", "youtu.be", "vimeo", "podcast", "soundcloud"]):
                return "media", input_ref
            return "url_article", input_ref

        if not os.path.exists(input_ref):
            return "unsupported", input_ref

        ext = os.path.splitext(input_ref.lower())[1]
        if ext == ".pdf":
            return self._pdf_kind(input_ref), os.path.abspath(input_ref)
        if ext in _OFFICE_EXTENSIONS:
            return "office_document", os.path.abspath(input_ref)
        if ext in _DJVU_EXTENSIONS:
            return "djvu_document", os.path.abspath(input_ref)
        if ext in _MEDIA_EXTENSIONS:
            return "media", os.path.abspath(input_ref)
        return "unsupported", input_ref

    def _pdf_kind(self, pdf_path: str) -> str:
        import fitz

        doc = fitz.open(pdf_path)
        text_present = False
        for i in range(min(3, doc.page_count)):
            if doc[i].get_text().strip():
                text_present = True
                break
        doc.close()
        return "digital_pdf" if text_present else "scanned_pdf"

    def _convert_office_to_pdf(self, doc_path: str, config: IngestionConfig) -> Optional[str]:
        """Convert Office document to PDF using legacy file_converter."""
        from ..file_converter import convert_to_pdf
        return convert_to_pdf(doc_path)

    def _convert_djvu_to_pdf(self, doc_path: str, config: IngestionConfig) -> Optional[str]:
        """Convert DJVU document to PDF using legacy file_converter."""
        from ..file_converter import convert_to_pdf
        return convert_to_pdf(doc_path)

    def route_to_pipeline(
        self,
        resource_type: str,
        normalized_input: str,
        config: IngestionConfig,
    ) -> PipelineResult:
        if resource_type == "digital_pdf":
            return digital_pdf.run(normalized_input, source_type="digital_pdf", config=config)
        if resource_type == "scanned_pdf":
            return scanned_pdf.run(normalized_input, config=config)
        if resource_type == "url_article":
            return url_article.run(normalized_input, config=config)
        if resource_type == "media":
            return media.run(normalized_input)
        raise ValueError(f"No route for resource type: {resource_type}")

    def standardize_csl_json(
        self,
        csl_json: Dict[str, Any],
        merkle_tree: Dict[str, Any],
        source_type: str,
    ) -> Dict[str, Any]:
        standardized = dict(csl_json)
        content_hash = hash_payload(csl_json)
        merkle_root = merkle_tree.get("root")

        standardized["id"] = content_hash[:16]
        standardized["content_hash"] = content_hash
        standardized["merkle_root"] = merkle_root
        standardized["source_type"] = source_type
        standardized["ingestion_timestamp"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return standardized

    def log_ingestion(
        self,
        input_ref: str,
        resource_type: str,
        standardized_csl: Dict[str, Any],
        result: PipelineResult,
    ) -> Dict[str, Any]:
        entry = IngestionLogEntry(
            input_ref=input_ref,
            resource_type=resource_type,
            csl_id=standardized_csl.get("id", ""),
            merkle_root=(result.merkle_tree or {}).get("root", ""),
            ingestion_timestamp=standardized_csl.get("ingestion_timestamp", ""),
        ).to_dict()
        append_jsonl(os.path.join(self.corpus_root, "ingestion_log.jsonl"), entry)
        return entry

    # ------------------------------------------------------------------
    # Batch URL article ingestion (--all-url-article / --update-url-article)
    # ------------------------------------------------------------------

    _CONTENT_HASHES_FILE = "_url_content_hashes.json"

    def _load_content_hashes(self) -> Dict[str, str]:
        """Load URL → content-hash mapping from corpus root."""
        path = os.path.join(self.corpus_root, self._CONTENT_HASHES_FILE)
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_content_hashes(self, hashes: Dict[str, str]) -> None:
        """Persist URL → content-hash mapping to corpus root."""
        write_json(os.path.join(self.corpus_root, self._CONTENT_HASHES_FILE), hashes)

    def ingest_all_urls(
        self,
        root_url: str,
        config: Optional[IngestionConfig] = None,
        update: bool = False,
        max_depth: int = 2,
        max_pages: int = 100,
    ) -> Dict[str, Any]:
        """Crawl *root_url*, discover article links, and ingest each one.

        Parameters
        ----------
        root_url : str
            Starting page for the crawl (e.g. a site index or homepage).
        config : IngestionConfig, optional
            Shared ingestion config forwarded to each URL pipeline run.
        update : bool
            When True, fetch each page and compare its content hash with
            the stored hash.  Skip if unchanged; re-ingest if changed or
            new.  When False, ingest every discovered URL unconditionally.
        max_depth : int
            BFS crawl depth (default 2).
        max_pages : int
            Maximum pages the crawler will visit (default 100).

        Returns
        -------
        dict  Summary with ``discovered``, ``ingested``, ``skipped``,
              ``updated``, ``failed`` counts and per-URL results.
        """
        from .url_crawler import discover_article_urls, fetch_content_hash

        logger.info("Discovering article URLs from %s (depth=%d, max_pages=%d)",
                     root_url, max_depth, max_pages)
        discovered = discover_article_urls(root_url, max_depth=max_depth, max_pages=max_pages)

        stored_hashes: Dict[str, str] = {}
        if update:
            stored_hashes = self._load_content_hashes()
            logger.info("Update mode: %d stored content hashes", len(stored_hashes))

        results: List[Dict[str, Any]] = []
        ingested_count = 0
        updated_count = 0
        skipped_count = 0
        failed_count = 0

        for idx, url in enumerate(discovered, start=1):
            # ── Update mode: compare content hash before ingesting ──
            if update:
                new_hash = fetch_content_hash(url)
                old_hash = stored_hashes.get(url)

                if new_hash and old_hash and new_hash == old_hash:
                    logger.info("[%d/%d] SKIP (unchanged): %s", idx, len(discovered), url)
                    skipped_count += 1
                    results.append({"url": url, "status": "unchanged"})
                    continue

                is_update = old_hash is not None
            else:
                new_hash = None
                is_update = False

            logger.info("[%d/%d] %s: %s", idx, len(discovered),
                        "Updating" if is_update else "Ingesting", url)
            try:
                output = self.ingest(url, config=config)
                status = output.get("status", "unknown")
                if status == "ok":
                    if is_update:
                        updated_count += 1
                        results.append({"url": url, "status": "updated"})
                    else:
                        ingested_count += 1
                        results.append({"url": url, "status": status})

                    # Store content hash (compute now if not in update mode)
                    if new_hash is None:
                        new_hash = fetch_content_hash(url)
                    if new_hash:
                        stored_hashes[url] = new_hash
                else:
                    failed_count += 1
                    results.append({"url": url, "status": status})
            except Exception as exc:
                logger.error("Failed to ingest %s: %s", url, exc, exc_info=True)
                results.append({"url": url, "status": "error", "error": str(exc)})
                failed_count += 1

        # Persist content hashes after batch
        self._save_content_hashes(stored_hashes)

        summary = {
            "status": "ok",
            "root_url": root_url,
            "discovered": len(discovered),
            "ingested": ingested_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "results": results,
        }
        logger.info(
            "Batch complete: discovered=%d ingested=%d updated=%d skipped=%d failed=%d",
            len(discovered), ingested_count, updated_count, skipped_count, failed_count,
        )
        return summary

    # ------------------------------------------------------------------

    def _failure(
        self,
        stage: str,
        source_id: str,
        error_code: str,
        error_message: str,
        next_action: str,
    ) -> Dict[str, Any]:
        return IngestionFailure(
            status="blocked",
            stage=stage,
            source_id=source_id,
            error_code=error_code,
            error_message=error_message,
            next_action=next_action,
        ).to_dict()
