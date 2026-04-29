from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class IngestionFailure:
    status: str
    stage: str
    source_id: str
    error_code: str
    error_message: str
    next_action: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IngestionLogEntry:
    input_ref: str
    resource_type: str
    csl_id: str
    merkle_root: str
    ingestion_timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IngestionConfig:
    """Configuration parameters passed through the ingestion pipeline."""
    llm_model: str = "ollama/qwen3"
    text_direction: str = "horizontal"
    vertical_lang: str = "ch"
    lang: str = "auto"
    page_range: str = "1-5, -3"
    citation_style: str = "chicago-author-date"
    doc_type_override: Optional[str] = None
    use_layout_analysis: bool = True
    is_primary: bool = False
    use_pageindex: bool = True
    pageindex_model: str = "ollama/qwen3.5:cloud"


@dataclass
class PipelineResult:
    status: str
    source_id: str
    resource_type: str
    csl_json: Dict[str, Any]
    document_json: Optional[Dict[str, Any]] = None
    transcript_json: Optional[Dict[str, Any]] = None
    merkle_tree: Optional[Dict[str, Any]] = None
    media_metadata: Optional[Dict[str, Any]] = None
    retrieval_index: Optional[Dict[str, Any]] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload.update(payload.pop("extra", {}))
        return payload


def validate_ingestion_input(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if "schema_version" not in payload:
        errors.append("missing schema_version")
    if "source_manifest" not in payload:
        errors.append("missing source_manifest")
        return errors

    if not isinstance(payload["source_manifest"], list) or not payload["source_manifest"]:
        errors.append("source_manifest must be a non-empty array")
        return errors

    for item in payload["source_manifest"]:
        if "source_id" not in item:
            errors.append("source item missing source_id")
        if "source_path" not in item:
            errors.append("source item missing source_path")
    return errors
