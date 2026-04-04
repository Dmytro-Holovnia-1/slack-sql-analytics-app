from typing import Literal

from loguru import logger

from app.graph.messages import latest_message_text, to_langchain_history
from app.graph.state import GraphState

from .prompts import FEW_SHOT_EXAMPLES, SYSTEM
from .schemas import IntentRouterOutput

_INTENT_MAP = {
    "query_database_for_new_analytics_data": "sql_expert_node",
    "retrieve_sql_code_from_previous_conversation_turn": "artifact_retrieval_node",
    "export_previous_query_results_to_csv_file": "artifact_retrieval_node",
    "explain_sql_or_database_schema_without_querying": "meta_analyst_node",
    "decline_off_topic_request_unrelated_to_analytics": "response_node",
}


async def intent_router_node(state: GraphState, llm_client) -> dict:
    messages = state.get("messages", [])
    user_text = latest_message_text(messages, "user") or ""
    history = to_langchain_history(messages[:-1])
    logger.debug(f"Intent classification request: '{user_text[:200]}'")

    result: IntentRouterOutput = await llm_client.generate_structured_output(
        system_prompt=SYSTEM,
        user_prompt=user_text,
        history=history,
        few_shot_examples=FEW_SHOT_EXAMPLES,
        response_model=IntentRouterOutput,
    )

    logger.info(f"Intent classified as: {result.intent}")

    return {
        "intent": result.intent,
        "sql_title": None,
        "row_count": 0,
        "direct_response": None,
        "artifact_format": None,
        "artifact_content": None,
        "artifact_title": None,
        "formatted_response": None,
    }


def route_intent(
    state: GraphState,
) -> Literal[
    "sql_expert_node",
    "artifact_retrieval_node",
    "meta_analyst_node",
    "response_node",
]:
    intent = state.get("intent", "decline_off_topic_request_unrelated_to_analytics")
    target = _INTENT_MAP.get(intent, "response_node")
    logger.debug(f"Routing intent '{intent}' to {target}")
    return target
