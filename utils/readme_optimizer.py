"""
utils/readme_optimizer.py — Repo2Product AI
AI-powered README optimizer. Streams an improved README via HuggingFace Cloud or local Ollama.
Backend routing lives in utils/ai_stream.py.
"""

import logging
from typing import Generator

from utils.ai_stream import CLOUD_MODE, stream_completion  # noqa: F401  (CLOUD_MODE re-exported)

logger = logging.getLogger(__name__)

# Long enough for a real project README; short enough to stay inside the model's
# context alongside the repo context block and the generated output.
MAX_README_CHARS = 12000


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

    Failures are yielded with utils.ai_stream.ERROR_PREFIX so the caller can tell
    them apart from generated markdown.
    """
    original = str(readme_text) if readme_text else ""
    safe_text = original[:MAX_README_CHARS]
    truncated = len(original) > MAX_README_CHARS
    if truncated:
        logger.info(f"README truncated for prompting: {len(original)} → {MAX_README_CHARS} chars")

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
        truncation_note = (
            "\nNote: the original README was truncated for length. Improve what is shown and do "
            "not invent content for the omitted part.\n" if truncated else ""
        )
        # Improve existing README
        prompt = f"""You are an expert technical writer. Improve the following README to make it professional, well-structured, and developer-friendly.
Add clear standard sections (Overview, Features, Installation, Usage, Contributing, License) if missing.
Incorporate any useful details from the repository context below.
Preserve all factual content. Do not complain about truncated text. Output ONLY the improved README in markdown.
{truncation_note}
Repository Context:
{repo_context}

Original README:
{safe_text}

---
Improved README:
"""

    yield from stream_completion(
        messages=[{"role": "user", "content": prompt}],
        use_hf=use_hf,
        hf_token=hf_token,
        use_ollama=use_ollama,
        ollama_model=ollama_model,
        ollama_url=ollama_url,
        max_tokens=2000,
        no_engine_hint="README optimization",
    )
