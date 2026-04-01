from langsmith.run_helpers import tracing_context

PHASE_2_TRACE_TAGS = ["phase:2", "surface:slack"]


def slack_tracing_context(*, intent: str, thread_id: str):
    return tracing_context(
        tags=[*PHASE_2_TRACE_TAGS, f"intent:{intent}"],
        metadata={"thread_id": thread_id, "intent": intent},
    )
