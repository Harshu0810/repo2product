"""
utils/chat_interface.py — Repo2Product AI
Maintains an AI-driven chat streaming session context for analyzing repositories.
Backend routing lives in utils/ai_stream.py so Chat AI, README AI and the
AI-explanation stage all talk to the same model through the same API.
"""

import logging
from typing import Generator

from utils.ai_stream import CLOUD_MODE, stream_completion  # noqa: F401  (CLOUD_MODE re-exported)

logger = logging.getLogger(__name__)


def chat_stream(
    user_query: str,
    context: str,
    use_hf: bool = False,
    hf_token: str = "",
    use_ollama: bool = False,
    ollama_model: str = "llama3.2",
    ollama_url: str = "http://localhost:11434",
) -> Generator[str, None, None]:
    """
    Stream an AI response analyzing the selected software repository framework/setup.

    Failures are yielded with utils.ai_stream.ERROR_PREFIX; use `is_error()` on the
    accumulated text to render them as errors rather than as assistant output.
    """
    prompt = f"""You are Repo2Product AI, an expert software architecture assistant analyzing a GitHub repository designed to be packaged and run.
Here are the explicit technical details and constraints of the analyzed project setup:
{context}

Respond directly to the user's question, referencing the provided context (such as their specific dependencies, compatibility score, estimated resource requirements, or setup plan) when relevant to give a highly personalized answer. If they ask about specific languages or heavy dependencies, name them.

User: {user_query}
Assistant:"""

    yield from stream_completion(
        messages=[{"role": "user", "content": prompt}],
        use_hf=use_hf,
        hf_token=hf_token,
        use_ollama=use_ollama,
        ollama_model=ollama_model,
        ollama_url=ollama_url,
        max_tokens=1000,
        no_engine_hint="Chat AI",
    )
