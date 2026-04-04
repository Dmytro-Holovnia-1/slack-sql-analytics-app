from langchain_core.messages import AIMessage
from loguru import logger

from app.config import get_settings
from app.graph.state import GraphState


async def response_node(state: GraphState) -> dict:
    """Generic response node for direct answers and decline messages."""
    response = state.get("direct_response") or get_settings().off_topic_response
    logger.info(f"Response: {response[:100]}...")
    return {"formatted_response": response, "messages": [AIMessage(content=response)]}
