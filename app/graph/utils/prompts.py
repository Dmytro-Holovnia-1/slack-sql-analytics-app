"""Shared prompt utilities."""

import json
from typing import Any


def json_output(payload: dict[str, Any]) -> str:
    """Serialize a payload to JSON string for few-shot examples."""
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)
