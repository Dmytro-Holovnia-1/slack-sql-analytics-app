"""
Intent Router vertical slice.

Routes user messages to the appropriate handler based on intent.
"""

from .node import intent_router_node, route_intent
from .schemas import IntentRouterOutput

__all__ = [
    "intent_router_node",
    "route_intent",
    "IntentRouterOutput",
]
