"""
langfuse_setup.py — Langfuse callback handler for LangChain RAG tracing.

langfuse >= 3.x dropped langfuse.callback in favour of langfuse.langchain.
This wrapper handles both versions gracefully.
"""

from config import settings


def get_langfuse_handler(session_id: str | None = None,
                         user_id: str | None = None):
    """
    Returns a Langfuse callback handler per request, compatible with
    langfuse v2 (langfuse.callback.CallbackHandler) and
    langfuse v3 (langfuse.langchain.CallbackHandler).
    Falls back to a no-op handler if Langfuse keys are not configured.
    """
    # Guard: skip if keys are missing (local dev without Langfuse)
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        return _NoOpHandler()

    try:
        # langfuse >= 3.x
        from langfuse.langchain import CallbackHandler
    except ImportError:
        try:
            # langfuse 2.x
            from langfuse.callback import CallbackHandler  # type: ignore[no-redef]
        except ImportError:
            return _NoOpHandler()

    try:
        return CallbackHandler(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
            session_id=session_id,
            user_id=user_id,
        )
    except Exception:
        return _NoOpHandler()


class _NoOpHandler:
    """
    Minimal stub so rag_chain.py works even without Langfuse.
    Must satisfy the LangChain callback manager's attribute checks:
    - ignore_chain, ignore_agent, ignore_llm, ignore_chat_model,
      ignore_retry, ignore_retriever, ignore_custom_event
    - raise_error
    Uses __getattr__ to return False/None for any attribute access.
    """
    # LangChain checks these boolean flags via getattr()
    raise_error: bool = False
    ignore_llm: bool = True
    ignore_chain: bool = True
    ignore_agent: bool = True
    ignore_retriever: bool = True
    ignore_chat_model: bool = True
    ignore_retry: bool = True
    ignore_custom_event: bool = True
    run_inline: bool = False

    def __getattr__(self, name: str):
        # Return a no-op callable for any method LangChain tries to call
        return lambda *args, **kwargs: None

    def __repr__(self) -> str:
        return "<LangfuseNoOpHandler>"
