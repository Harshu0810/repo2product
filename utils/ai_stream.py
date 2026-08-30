"""
utils/ai_stream.py — Repo2Product AI
Shared streaming backend for the Chat AI and README AI features.

Both features need the same thing: pick a backend (Hugging Face cloud or local
Ollama), stream tokens, and surface failures. They used to each carry their own
copy of that routing, which is how they drifted apart from utils/llm_client.py.
This is the single implementation.

Errors are yielded with ERROR_PREFIX so the caller can tell a failed API call
apart from something the model actually said — previously an HTTP error rendered
as if it were the assistant's answer.
"""

import os
import logging
from typing import Dict, Generator, List

from utils.runtime import CLOUD_MODE  # noqa: F401  (re-exported for callers)

logger = logging.getLogger(__name__)

# Every cloud path in the app uses this model. Keep it here so the UI copy,
# the AI-explanation stage and the streaming features can never disagree.
HF_DEFAULT_MODEL = "meta-llama/Meta-Llama-3-8B-Instruct"

ERROR_PREFIX = "⛔ AI_ERROR:"


def error_chunk(message: str) -> str:
    """Tag a message so callers can render it as an error, not as model output."""
    return f"{ERROR_PREFIX} {message}"


def is_error(text: str) -> bool:
    return text.lstrip().startswith(ERROR_PREFIX)


def error_message(text: str) -> str:
    """Strip the marker for display."""
    return text.lstrip()[len(ERROR_PREFIX):].strip() if is_error(text) else text


def stream_completion(
    messages: List[Dict[str, str]],
    use_hf: bool = False,
    hf_token: str = "",
    use_ollama: bool = False,
    ollama_model: str = "llama3.2",
    ollama_url: str = "http://localhost:11434",
    max_tokens: int = 1000,
    no_engine_hint: str = "this feature",
) -> Generator[str, None, None]:
    """
    Stream a chat completion from whichever backend is configured.

    Resolution order: explicit Hugging Face → cloud default → explicit Ollama →
    an error explaining that nothing is configured.
    """
    # ── HuggingFace Cloud ──────────────────────────────────────────────
    if use_hf:
        try:
            from huggingface_hub import InferenceClient
        except ImportError:
            yield error_chunk("`huggingface_hub` is not installed. Run: `pip install huggingface_hub`")
            return

        token = hf_token or os.environ.get("HF_TOKEN", "")
        try:
            client = InferenceClient(HF_DEFAULT_MODEL, token=token)
            for message in client.chat_completion(messages=messages, stream=True, max_tokens=max_tokens):
                yield message.choices[0].delta.content or ""
        except Exception as e:
            logger.warning(f"HF streaming failed: {e}")
            yield error_chunk(
                f"Hugging Face API call failed: {e}. "
                "Ensure HF_TOKEN is set in your Space Settings → Secrets, or paste a token in the sidebar."
            )
        return

    # ── Local / Remote Ollama ──────────────────────────────────────────
    if use_ollama:
        try:
            import ollama as ollama_lib
        except ImportError:
            yield error_chunk("`ollama` package not installed. Run: `pip install ollama`")
            return

        try:
            # Honour a non-default host instead of silently using localhost.
            if ollama_url and ollama_url.rstrip("/") != "http://localhost:11434":
                client = ollama_lib.Client(host=ollama_url)
                response = client.chat(model=ollama_model, messages=messages, stream=True)
            else:
                response = ollama_lib.chat(model=ollama_model, messages=messages, stream=True)
            for chunk in response:
                yield chunk["message"]["content"]
        except Exception as e:
            logger.warning(f"Ollama streaming failed: {e}")
            if "connection" in str(e).lower():
                yield error_chunk(f"Could not connect to Ollama at {ollama_url}. Ensure it is running (`ollama serve`).")
            else:
                yield error_chunk(f"Ollama call failed: {e}")
        return

    # ── No AI engine selected ──────────────────────────────────────────
    yield error_chunk(
        f"No AI engine configured. Enable **Hugging Face (Cloud)** or **Ollama (Local)** "
        f"in the sidebar to use {no_engine_hint}."
    )
