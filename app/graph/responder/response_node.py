from loguru import logger

from app.config import OFF_TOPIC_RESPONSE
from app.graph.messages import assistant_message
from app.graph.state import GraphState


async def response_node(state: GraphState) -> dict:
    """Generic response node for direct answers and decline messages."""
    response = state.get("direct_response") or OFF_TOPIC_RESPONSE
    logger.info(f"Response: {response[:100]}...")
    return {"formatted_response": response, "messages": [assistant_message(response)]}
