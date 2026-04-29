"""Output formatting utilities for human-readable and JSON modes."""
from __future__ import annotations

import json
from enum import Enum
from typing import Any


class OutputFormat(Enum):
    """Output format modes."""
    HUMAN = "human"
    JSON = "json"


def format_output(data: Any, json_mode: bool = False) -> str:
    """Format output data for display.

    Args:
        data: Dict, list, or string to format.
        json_mode: If True, output as JSON. Otherwise human-readable.

    Returns:
        Formatted string.
    """
    if json_mode:
        if isinstance(data, (dict, list)):
            return json.dumps(data, ensure_ascii=False, indent=2)
        return json.dumps({"result": str(data)}, ensure_ascii=False, indent=2)

    if isinstance(data, dict):
        if data.get("success") is False:
            error = data.get("error", "Unknown error")
            return f"Error: {error}"
        return _format_dict_human(data)
    if isinstance(data, list):
        return "\n".join(str(item) for item in data)
    return str(data)


def _format_dict_human(data: dict[str, Any], indent: int = 0) -> str:
    """Format a dictionary as human-readable key: value pairs."""
    lines = []
    prefix = "  " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            lines.append(_format_dict_human(value, indent + 1))
        elif isinstance(value, list):
            if value and isinstance(value[0], dict):
                lines.append(f"{prefix}{key}: ({len(value)} items)")
            else:
                lines.append(f"{prefix}{key}: {value}")
        else:
            lines.append(f"{prefix}{key}: {value}")
    return "\n".join(lines)
