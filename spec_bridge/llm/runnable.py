"""The provider adapter as an LCEL Runnable (W4-R R4, D-043 decision 2).

LangChain composes the RAG chain; the model call still goes through our JsonProvider, so
the audit log, the offline guard and the fixed options (temperature 0, seed) stay in force.
"""

from typing import Any

from langchain_core.runnables import Runnable, RunnableLambda

from spec_bridge.llm.provider import JsonProvider


def as_runnable(
    provider: JsonProvider, *, system: str, schema: dict[str, Any] | None, task: str
) -> Runnable[str, dict[str, Any]]:
    """user prompt -> JSON object; an LlmError propagates to the caller."""

    def call(user: str) -> dict[str, Any]:
        return provider.complete_json(system=system, user=user, schema=schema, task=task)

    return RunnableLambda(call)
