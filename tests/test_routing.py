from app.graph.intent_router.node import route_intent
from app.graph.sql_generation.executor_node import route_sql_executor
from app.graph.sql_generation.expert_node import route_sql_expert


def test_route_intent():
    assert route_intent({"intent": "query_database_for_new_analytics_data"}) == "sql_expert_node"
    assert route_intent({"intent": "retrieve_sql_code_from_previous_conversation_turn"}) == "artifact_retrieval_node"
    assert route_intent({"intent": "export_previous_query_results_to_csv_file"}) == "artifact_retrieval_node"
    assert route_intent({"intent": "explain_sql_or_database_schema_without_querying"}) == "meta_analyst_node"
    assert route_intent({"intent": "decline_off_topic_request_unrelated_to_analytics"}) == "response_node"


def test_route_sql_expert():
    assert route_sql_expert({"direct_response": "Clarification needed"}) == "response_node"
    assert route_sql_expert({"direct_response": None}) == "sql_executor_node"


def test_route_sql_executor():
    # No error -> go to formatter
    assert route_sql_executor({"sql_error": None, "repair_count": 0}) == "result_formatter_node"

    # Has error, attempts < 2 -> go to repair
    assert route_sql_executor({"sql_error": "Syntax error", "repair_count": 0}) == "sql_repair_node"
    assert route_sql_executor({"sql_error": "Syntax error", "repair_count": 1}) == "sql_repair_node"

    # Has error, attempts exhausted -> give up, go to formatter
    assert route_sql_executor({"sql_error": "Syntax error", "repair_count": 3}) == "result_formatter_node"
