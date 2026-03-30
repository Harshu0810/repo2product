"""
utils/chat_interface.py — Repo2Product AI
Maintains an AI-driven chat streaming session context for analyzing repositories.
Combines logic from `devbrain_ai/chat/interface.py` with Repo2Product architecture contexts.
"""

import os
import logging
from typing import Generator

logger = logging.getLogger(__name__)

CLOUD_MODE = bool(os.environ.get("SPACE_ID") or os.environ.get("R2P_CLOUD"))

def chat_stream(
    user_query: str,
    context: str,
    use_hf: bool = False,
    hf_token: str = "",
    use_ollama: bool = False,
    ollama_model: str = "llama3.2",
    ollama_url: str = "http://localhost:11434"
) -> Generator[str, None, None]:
    """
    Stream a localized AI response analyzing the selected software repository framework/setup.
    """
    prompt = f"""You are Repo2Product AI, an expert software architecture assistant analyzing a GitHub repository designed to be packaged and run.
Here are the explicit technical details and constraints of the analyzed project setup:
{context}

Respond directly to the user's question, referencing the provided context (such as their specific dependencies, compatibility score, estimated resource requirements, or setup plan) when relevant to give a highly personalized answer. If they ask about specific languages or heavy dependencies, name them.

User: {user_query}
Assistant:"""

    messages = [{"role": "user", "content": prompt}]

    # ── HuggingFace Cloud ──────────────────────────────────────────────
    if use_hf or (CLOUD_MODE and not use_ollama):
        try:
            from huggingface_hub import InferenceClient
            token = hf_token or os.environ.get("HF_TOKEN", "")
            client = InferenceClient("meta-llama/Meta-Llama-3-8B-Instruct", token=token)
            for message in client.chat_completion(messages=messages, stream=True, max_tokens=1000):
                yield message.choices[0].delta.content or ""
        except ImportError:
            yield "Error: `huggingface_hub` is not installed. Run: `pip install huggingface_hub`"
        except Exception as e:
            yield f"Error calling Hugging Face API: {e}. Ensure HF_TOKEN is set in your Space Settings → Secrets."
        return

    # ── Local Ollama ───────────────────────────────────────────────────
    if use_ollama:
        try:
            import ollama as ollama_lib
            response = ollama_lib.chat(model=ollama_model, messages=messages, stream=True)
            for chunk in response:
                yield chunk['message']['content']
        except ImportError:
            yield "Error: `ollama` package not installed. Run: `pip install ollama`"
        except Exception as e:
            if "connection" in str(e).lower():
                yield "Error: Could not connect to Ollama. Ensure it is running (`ollama serve`)."
            else:
                yield f"Error calling Ollama: {e}"
        return

    # ── No AI engine selected ──────────────────────────────────────────
    yield "⚠️ No AI engine configured. Enable **Hugging Face (Cloud)** or **Ollama (Local)** in the sidebar to use Chat AI."
