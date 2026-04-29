"""Validate pipeline I/O against .agent/schema/ YAML contracts.

Loads JSON Schema definitions from the .agent/schema/stage/ directory
and validates pipeline outputs at stage boundaries.
"""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SCHEMA_CACHE: Dict[str, Dict[str, Any]] = {}


def _find_schema_dir() -> Optional[str]:
    """Locate the .agent/schema/stage/ directory relative to project root."""
    # Walk up from this file to find the project root containing .agent/
    current = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        candidate = os.path.join(current, ".agent", "schema", "stage")
        if os.path.isdir(candidate):
            return candidate
        current = os.path.dirname(current)
    return None


def _load_yaml_schema(schema_name: str) -> Optional[Dict[str, Any]]:
    """Load a YAML schema file by name (without extension)."""
    if schema_name in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[schema_name]

    schema_dir = _find_schema_dir()
    if not schema_dir:
        return None

    path = os.path.join(schema_dir, f"{schema_name}.yaml")
    if not os.path.exists(path):
        return None

    try:
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        _SCHEMA_CACHE[schema_name] = schema
        return schema
    except Exception:
        logger.warning("Failed to load schema %s", schema_name, exc_info=True)
        return None


def validate_output(schema_name: str, data: Dict[str, Any]) -> List[str]:
    """Validate data against a named schema. Returns list of error strings.

    If jsonschema or pyyaml is not installed, or the schema file is missing,
    returns an empty list (validation is best-effort).
    """
    schema = _load_yaml_schema(schema_name)
    if schema is None:
        return []

    try:
        import jsonschema

        validator = jsonschema.Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
        return [f"{'.'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors]
    except ImportError:
        logger.info("jsonschema not installed, skipping validation")
        return []
    except Exception:
        logger.warning("Schema validation failed unexpectedly", exc_info=True)
        return []


def validate_ingestion_output(data: Dict[str, Any]) -> List[str]:
    """Validate a complete ingestion output against the ingestion_output schema."""
    return validate_output("ingestion_output", data)


def validate_retrieval_output(data: Dict[str, Any]) -> List[str]:
    """Validate retrieval output against the retrieval_output schema."""
    return validate_output("retrieval_output", data)
