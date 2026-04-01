from functools import partial
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from loguru import logger

from app.graph.artifact_retrieval.node import artifact_retrieval_node
from app.graph.intent_router.node import intent_router_node, route_intent
from app.graph.meta_analysis.node import meta_analyst_node
from app.graph.responder.formatter_node import result_formatter_node
from app.graph.responder.response_node import response_node
from app.graph.sql_generation.executor_node import route_sql_executor, sql_executor_node
from app.graph.sql_generation.expert_node import route_sql_expert, sql_expert_node
from app.graph.sql_generation.repair_node import sql_repair_node
from app.graph.state import GraphState


def build_graph(
    llm_client: Any,
    query_service: Any,
    checkpointer: Any | None = None,
) -> Any:
    """
    Build and compile the LangGraph workflow.

    Uses a factory pattern to avoid mutable wrapper anti-patterns and fragile closures. The fetch_history function is
    created after compilation to ensure it captures a valid, fully-initialized graph reference.
    """
    logger.info("Building LangGraph workflow")
    builder = StateGraph(GraphState)

    # Add all nodes and edges first (before compilation)
    builder.add_node("intent_router_node", partial(intent_router_node, llm_client=llm_client))
    builder.add_node("sql_expert_node", partial(sql_expert_node, llm_client=llm_client))
    builder.add_node("sql_executor_node", partial(sql_executor_node, query_service=query_service))
    builder.add_node("sql_repair_node", partial(sql_repair_node, llm_client=llm_client))
    builder.add_node("result_formatter_node", partial(result_formatter_node, llm_client=llm_client))
    builder.add_node("response_node", response_node)
    # Add stub for artifact_retrieval_node (will be replaced after compilation with proper fetch_history)
    builder.add_node("artifact_retrieval_node", lambda state: state)
    builder.add_node("meta_analyst_node", partial(meta_analyst_node, llm_client=llm_client))
    builder.add_edge(START, "intent_router_node")
    builder.add_conditional_edges(
        "intent_router_node",
        route_intent,
        {
            "sql_expert_node": "sql_expert_node",
            "artifact_retrieval_node": "artifact_retrieval_node",
            "meta_analyst_node": "meta_analyst_node",
            "response_node": "response_node",
        },
    )
    builder.add_conditional_edges(
        "sql_expert_node",
        route_sql_expert,
        {
            "response_node": "response_node",
            "sql_executor_node": "sql_executor_node",
        },
    )
    builder.add_conditional_edges(
        "sql_executor_node",
        route_sql_executor,
        {
            "sql_repair_node": "sql_repair_node",
            "result_formatter_node": "result_formatter_node",
        },
    )
    builder.add_edge("sql_repair_node", "sql_executor_node")
    builder.add_edge("result_formatter_node", END)
    builder.add_edge("artifact_retrieval_node", END)
    builder.add_edge("meta_analyst_node", END)
    builder.add_edge("response_node", END)

    # Compile the graph first
    compiled_app = builder.compile(checkpointer=checkpointer)

    # Now create fetch_history with a valid closure over the compiled graph
    async def fetch_history(config):
        """Fetch state history from the compiled graph."""
        async for snapshot in compiled_app.aget_state_history(config):
            yield snapshot

    # Replace artifact_retrieval_node with proper implementation
    compiled_app.add_node(
        "artifact_retrieval_node",
        partial(artifact_retrieval_node, fetch_history=fetch_history, llm_client=llm_client),
        clobber=True,
    )

    logger.info(f"LangGraph workflow compiled successfully with nodes: {list(compiled_app.nodes.keys())}")
    return compiled_app


def create_graph() -> Any:
    """
    Factory function for LangGraph Studio. Creates graph with dependencies from environment variables.

    Returns:
        CompiledStateGraph instance
    """
    logger.info("Creating graph for LangGraph Studio")

    # Lazy imports to avoid circular dependencies
    from app.config import load_settings
    from app.llm.gemini_client import GeminiClient
    from app.services.query_service import DatabaseQueryService

    # Load settings from environment
    settings = load_settings()

    # Create dependencies
    llm_client = GeminiClient(settings)
    query_service = DatabaseQueryService.from_settings(settings)
    checkpointer = MemorySaver()  # Use memory checkpointer for Studio

    # Build and return graph
    return build_graph(llm_client, query_service, checkpointer)
