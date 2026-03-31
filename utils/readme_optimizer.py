"""
utils/readme_optimizer.py — Repo2Product AI
AI-powered README optimizer. Streams improved README via HuggingFace Cloud or local Ollama.
Adapted from DevBrain AI's readme_optimizer module.
"""

import os
import logging
from typing import Generator

logger = logging.getLogger(__name__)

CLOUD_MODE = bool(os.environ.get("SPACE_ID") or os.environ.get("R2P_CLOUD"))


def improve_readme_stream(
    readme_text: str,
    repo_context: str = "",
    use_hf: bool = False,
    hf_token: str = "",
    use_ollama: bool = False,
    ollama_model: str = "llama3.2",
    ollama_url: str = "http://localhost:11434",
) -> Generator[str, None, None]:
    """
    Stream an AI-improved or generated version of the given README text.
    Picks the right backend based on flags (HuggingFace cloud or local Ollama).
    """
    safe_text = str(readme_text)[:2000] if readme_text else ""

    if len(safe_text.strip()) < 50:
        # Generate from scratch primarily using context if README is empty or very short
        prompt = f"""You are an expert technical writer. Create a professional, well-structured, and developer-friendly README for the following repository.
Use the provided repository context to generate the content. Include standard sections (Overview, Features, Installation, Usage).
Output ONLY the generated README in markdown.

Repository Context:
{repo_context}

---
Generated README:
"""
    else:
        # Improve existing README
        prompt = f"""You are an expert technical writer. Improve the following README to make it professional, well-structured, and developer-friendly.
Add clear standard sections (Overview, Features, Installation, Usage, Contributing, License) if missing.
Incorporate any useful details from the repository context below.
Preserve all factual content. Do not complain about truncated text. Output ONLY the improved README in markdown.

Repository Context:
{repo_context}

Original README:
{safe_text}

---
Improved README:
"""
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
    yield "⚠️ No AI engine configured. Enable **Hugging Face (Cloud)** or **Ollama (Local)** in the sidebar to use README optimization."
