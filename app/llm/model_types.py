"""LLM model type definitions."""

from enum import StrEnum


class ModelType(StrEnum):
    """Model type enumeration for LLM selection."""

    STANDARD = "standard"
    LOW_COST = "low_cost"
