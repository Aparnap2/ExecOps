"""LangFuse observability integration for tracing and monitoring.

This module provides integration with LangFuse for tracing LLM calls,
agent decisions, and performance metrics.
"""

import logging
from contextlib import contextmanager
from typing import Any

from langfuse.langchain import LangfuseCallbackHandler
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


class LangfuseObserver:
    """LangFuse observer for tracing and monitoring.

    This class manages LangFuse integration for observability
    across the Sentinel agent and LLM calls.
    """

    def __init__(
        self,
        public_key: str,
        secret_key: str,
        host: str = "http://localhost:3000",
    ) -> None:
        """Initialize the LangFuse observer.

        Args:
            public_key: LangFuse public key
            secret_key: LangFuse secret key
            host: LangFuse server URL
        """
        self._public_key = public_key
        self._secret_key = secret_key
        self._host = host
        self._handler: LangfuseCallbackHandler | None = None

        logger.info(f"LangfuseObserver initialized with host: {host}")

    def get_handler(self) -> LangfuseCallbackHandler | None:
        """Get the LangFuse callback handler.

        Returns:
            LangfuseCallbackHandler or None if not configured
        """
        if not self._public_key or not self._secret_key:
            logger.warning("LangFuse keys not configured")
            return None

        if self._handler is None:
            self._handler = LangfuseCallbackHandler(
                public_key=self._public_key,
                secret_key=self._secret_key,
                host=self._host,
            )

        return self._handler

    def create_llm(self, model: str = "gpt-4o", **kwargs: Any) -> ChatOpenAI | None:
        """Create an LLM with LangFuse tracing.

        Args:
            model: Model name
            **kwargs: Additional ChatOpenAI kwargs

        Returns:
            ChatOpenAI with LangFuse callbacks or None
        """
        handler = self.get_handler()
        if not handler:
            return None

        callbacks = kwargs.pop("callbacks", []) + [handler]

        return ChatOpenAI(
            model=model,
            callbacks=callbacks,
            **kwargs,
        )

    @contextmanager
    def trace(self, name: str, **metadata: Any):
        """Context manager for creating traces.

        Args:
            name: Trace name
            **metadata: Additional metadata
        """
        from langfuse import Langfuse

        langfuse = Langfuse(
            public_key=self._public_key,
            secret_key=self._secret_key,
            host=self._host,
        )

        generation = langfuse.generation(
            name=name,
            metadata=metadata,
        )

        try:
            yield generation
        except Exception as e:
            generation.update(
                output=str(e),
                status="error",
            )
            raise
        finally:
            generation.end()

    def flush(self) -> None:
        """Flush pending traces to LangFuse."""
        handler = self.get_handler()
        if handler:
            handler.langfuse.flush()


def create_langfuse_handler(
    public_key: str | None = None,
    secret_key: str | None = None,
    host: str | None = None,
) -> LangfuseCallbackHandler | None:
    """Create a LangFuse callback handler.

    Args:
        public_key: LangFuse public key (from env if None)
        secret_key: LangFuse secret key (from env if None)
        host: LangFuse server URL (from env if None)

    Returns:
        LangfuseCallbackHandler or None
    """
    import os

    key = public_key or os.getenv("LANGFUSE_PUBLIC_KEY")
    secret = secret_key or os.getenv("LANGFUSE_SECRET_KEY")
    langfuse_host = host or os.getenv("LANGFUSE_HOST", "http://localhost:3000")

    if not key or not secret:
        logger.warning("LangFuse not configured - tracing disabled")
        return None

    return LangfuseCallbackHandler(
        public_key=key,
        secret_key=secret,
        host=langfuse_host,
    )


def create_observer(
    public_key: str | None = None,
    secret_key: str | None = None,
    host: str | None = None,
) -> LangfuseObserver:
    """Create a LangFuse observer.

    Args:
        public_key: LangFuse public key (from env if None)
        secret_key: LangFuse secret key (from env if None)
        host: LangFuse server URL (from env if None)

    Returns:
        LangfuseObserver instance
    """
    import os

    key = public_key or os.getenv("LANGFUSE_PUBLIC_KEY")
    secret = secret_key or os.getenv("LANGFUSE_SECRET_KEY")
    langfuse_host = host or os.getenv("LANGFUSE_HOST", "http://localhost:3000")

    return LangfuseObserver(
        public_key=key or "",
        secret_key=secret or "",
        host=langfuse_host,
    )
