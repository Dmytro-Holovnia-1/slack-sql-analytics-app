"""
Responder vertical slice.

Handles response formatting, direct responses, and decline messages.
"""

from .formatter_node import is_complex_result, result_formatter_node
from .prompts import FEW_SHOT_EXAMPLES, SYSTEM
from .response_node import response_node
from .schemas import InterpreterOutput

__all__ = [
    "response_node",
    "result_formatter_node",
    "is_complex_result",
    "FEW_SHOT_EXAMPLES",
    "SYSTEM",
    "InterpreterOutput",
]
