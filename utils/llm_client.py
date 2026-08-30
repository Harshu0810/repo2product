"""
utils/llm_client.py — Repo2Product AI
Unified client for localized Ollama and Hugging Face Cloud Inference API.
"""

import json
import os
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List
import logging

# Canonical cloud model, shared with the streaming features so the UI copy, the
# AI-explanation stage, Chat AI and README AI can never disagree about the model.
from utils.ai_stream import HF_DEFAULT_MODEL  # noqa: F401  (re-exported for callers)
from utils.runtime import CLOUD_MODE

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"


class LLMClient:
    """
    Client for LLM generation (Ollama and Hugging Face).
    Used for repo explanation, setup guidance, and adaptive suggestions.
    """

    SYSTEM_PROMPT = """You are an expert software engineer and developer tools specialist.
Analyze repositories and provide clear, concise, actionable insights.
Be specific, technical, and practical. Avoid fluff. Keep responses focused."""

    def __init__(self, provider: str = "ollama", base_url: str = OLLAMA_BASE_URL, model: str = "llama3.2", api_key: str = ""):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self._available: Optional[bool] = None
        self._available_models: List[str] = []

    # ------------------------------------------------------------------ #
    #  Server availability                                                 #
    # ------------------------------------------------------------------ #

    def resolved_model(self) -> str:
        """Human-readable name of the model this client will actually call."""
        if self.provider == "huggingface":
            return self.model if "/" in self.model else HF_DEFAULT_MODEL
        return self.model

    def _hf_token(self) -> str:
        """Explicit key wins; otherwise fall back to the Space/host secret."""
        return self.api_key or os.environ.get("HF_TOKEN", "")

    def is_available(self) -> bool:
        if self.provider == "huggingface":
            return bool(self._hf_token())

        if self._available is not None:
            return bool(self._available)
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                self._available_models = [m["name"].split(":")[0] for m in data.get("models", [])]
                self._available = True
                return True
        except Exception:
            self._available = False
            return False


    def auto_select_model(self) -> bool:
        if self.provider == "huggingface":
            return True
        if not self.is_available(): return False
        models = self._available_models
        for m in ["llama3.2", "llama3", "llama2", "mistral", "phi3", "gemma2", "qwen2.5"]:
            if m in models or any(x.startswith(m) for x in models):
                self.model = m
                return True
        if models:
            self.model = models[0]
            return True
        return False

    # ------------------------------------------------------------------ #
    #  Core LLM calls                                                      #
    # ------------------------------------------------------------------ #

    def generate(self, prompt: str, system: str = "", temperature: float = 0.3, max_tokens: int = 1024) -> str:
        if not self.is_available():
            return ""

        if self.provider == "huggingface":
            return self._generate_hf(prompt, system, temperature, max_tokens)
        else:
            return self._generate_ollama(prompt, system, temperature, max_tokens)

    def _generate_hf(self, prompt: str, system: str, temperature: float, max_tokens: int) -> str:
        """
        Chat-completion call through huggingface_hub, matching the streaming paths in
        chat_interface.py / readme_optimizer.py. Using the chat API means the model's
        own prompt template is applied server-side — no hand-rolled instruction tags.
        """
        try:
            from huggingface_hub import InferenceClient
        except ImportError:
            logger.warning("huggingface_hub is not installed; cannot use the HF provider")
            return ""

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            client = InferenceClient(self.resolved_model(), token=self._hf_token())
            completion = client.chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return (completion.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning(f"HF request failed: {e}")
            return ""

    def _generate_ollama(self, prompt: str, system: str, temperature: float, max_tokens: int) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 2048},
        }
        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode())
                return result.get("response", "")
        except Exception as e:
            logger.warning(f"Ollama request failed: {e}")
            return ""

    # ------------------------------------------------------------------ #
    #  High-level repo analysis tasks                                      #
    # ------------------------------------------------------------------ #

    def explain_repo(self, structure: Dict[str, Any], metadata: Dict[str, Any]) -> str:
        desc = metadata.get("description", "")
        lang = metadata.get("language", "")
        frameworks = [fw["name"] for fw in structure.get("frameworks", [])]
        project_type = structure.get("project_type", "")
        entry_points = [ep["path"] for ep in structure.get("entry_points", [])]
        file_count = structure.get("file_count", 0)

        prompt = f"""Analyze this GitHub repository and explain what it does:

Repository Info:
- Description: {desc or 'No description'}
- Language: {lang}
- Project Type: {project_type}
- Frameworks: {', '.join(frameworks) or 'None'}
- Entry Points: {', '.join(entry_points) or 'None'}
- Files: {file_count}

Provide:
1. What this project does (2-3 sentences)
2. Who it's for (target user)
3. Key features (3-5 bullet points)
4. How components connect (brief architecture)

Be concise and technical."""
        response = self.generate(prompt, system=self.SYSTEM_PROMPT, max_tokens=600)
        return response or self._fallback_explanation(structure, metadata)

    def suggest_cpu_optimizations(self, frameworks: List[str], heavy_deps: List[str], ram_gb: int) -> str:
        if not self.is_available():
            return self._fallback_cpu_tips(frameworks, ram_gb)

        prompt = f"""Suggest CPU-only optimizations for a project:

System: {ram_gb}GB RAM, CPU-only (no GPU)
Frameworks: {', '.join(frameworks) or 'None'}
Heavy packages: {', '.join(heavy_deps) or 'None'}

Give 5 specific, actionable optimizations. Focus on:
- Memory efficiency
- CPU thread usage
- Inference speed on CPU
Format as numbered list."""

        response = self.generate(prompt, system=self.SYSTEM_PROMPT, max_tokens=400)
        return response or self._fallback_cpu_tips(frameworks, ram_gb)

    def _fallback_explanation(self, structure: Dict, metadata: Dict) -> str:
        desc = metadata.get("description", "No description available")
        lang = metadata.get("language", "")
        frameworks = [fw["name"] for fw in structure.get("frameworks", [])]
        project_type = structure.get("project_type", "unknown")

        type_descriptions = {
            "web-api-python": "a Python REST API backend",
            "web-fullstack-python": "a Python full-stack web application",
            "fullstack": "a Full-Stack application",
            "data-app-streamlit": "an interactive data application built with Streamlit",
            "ml-training": "a machine learning model training pipeline",
            "nlp-huggingface": "an NLP application using HuggingFace models",
            "llm-application": "an application powered by large language models",
            "python-script": "a Python utility/script",
        }

        type_desc = type_descriptions.get(project_type, "a software project")
        fw_str = f" using {', '.join(frameworks)}" if frameworks else ""

        return (
            f"This is {type_desc}{fw_str} written in {lang}. "
            f"{desc}. "
            f"The project has been analyzed and adapted for CPU-only execution."
        )

    def _fallback_cpu_tips(self, frameworks: List[str], ram_gb: int) -> str:
        tips = [
            f"Set OMP_NUM_THREADS={max(2, min(8, ram_gb // 2))} to optimize CPU thread usage",
            f"Close other applications to free RAM (you have {ram_gb}GB total)",
            "Use smaller model variants when available",
            "Enable result caching to avoid repeated computation",
            "Monitor with: watch -n2 'free -h && top -bn1 | head -5'",
        ]
        if "PyTorch" in frameworks:
            tips.append("Use torch.compile() for PyTorch 2.0+ CPU speedup")
        if "HuggingFace" in frameworks:
            tips.append("Use pipeline(..., device='cpu', batch_size=1) for memory efficiency")
        # Number at render time so conditional tips can't collide.
        return "\n".join(f"{i}. {tip}" for i, tip in enumerate(tips, 1))

class OllamaStatus:
    """Helper to check and display Ollama status."""

    @staticmethod
    def get_status(base_url: str = OLLAMA_BASE_URL) -> Dict[str, Any]:
        if CLOUD_MODE:
            # There is no Ollama inside the Space container, and probing
            # localhost there just adds latency to every run.
            return {
                "running": False,
                "url": base_url,
                "models": [],
                "best_model": "",
                "model_count": 0,
                "status_text": "Unavailable in cloud mode — Ollama is a local-only backend",
            }

        client = LLMClient(provider="ollama", base_url=base_url)
        is_running = client.is_available()
        models = client._available_models if is_running else []
        best_model = ""
        if is_running:
            client.auto_select_model()
            best_model = client.model

        return {
            "running": is_running,
            "url": base_url,
            "models": models,
            "best_model": best_model,
            "model_count": len(models),
            "status_text": (
                f"✅ Running — {len(models)} model(s) available" if is_running
                else "❌ Not running — start with: ollama serve"
            ),
        }
