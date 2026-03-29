"""
utils/ollama_client.py — Repo2Product AI
Interfaces with local Ollama server for repo explanation and adaptive assistance.
Provides streaming and non-streaming modes, with graceful fallback.
"""

import json
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Generator, List
import logging

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2"
FALLBACK_MODELS = ["llama3.2", "llama3", "llama2", "mistral", "phi3", "gemma2:2b", "qwen2.5:3b"]


class OllamaClient:
    """
    Client for local Ollama LLM server.
    Used for repo explanation, setup guidance, and adaptive suggestions.
    Designed for CPU-only, low-RAM environments.
    """

    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = DEFAULT_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._available: Optional[bool] = None
        self._available_models: List[str] = []

    # ------------------------------------------------------------------ #
    #  Server availability                                                 #
    # ------------------------------------------------------------------ #

    def is_available(self) -> bool:
        """Check if Ollama server is running."""
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

    def get_available_models(self) -> List[str]:
        """Return list of pulled models."""
        if not self.is_available():
            return []
        return self._available_models

    def get_best_model(self) -> Optional[str]:
        """Return the best available model from fallback list."""
        available = self.get_available_models()
        if not available:
            return None
        # Try preferred models in order
        for model in FALLBACK_MODELS:
            if model in available or any(m.startswith(model) for m in available):
                return model
        return available[0] if available else None

    def auto_select_model(self) -> bool:
        """Auto-select best available model. Returns True if model found."""
        best = self.get_best_model()
        if best:
            self.model = best
            return True
        return False

    # ------------------------------------------------------------------ #
    #  Core LLM calls                                                      #
    # ------------------------------------------------------------------ #

    def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1024,
        stream: bool = False,
    ) -> str:
        """
        Send a generate request to Ollama.
        Returns full response text.
        """
        if not self.is_available():
            return ""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 2048,  # Keep context small for CPU
            },
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                if stream:
                    return self._collect_stream(resp)
                else:
                    result = json.loads(resp.read().decode())
                    return result.get("response", "")
        except (urllib.error.URLError, TimeoutError) as e:
            logger.warning(f"Ollama request failed: {e}")
            return ""
        except Exception as e:
            logger.warning(f"Ollama unexpected error: {e}")
            return ""

    def _collect_stream(self, resp) -> str:
        """Collect streaming response into a single string."""
        parts = []
        for line in resp:
            try:
                chunk = json.loads(line.decode("utf-8"))
                parts.append(chunk.get("response", ""))
                if chunk.get("done"):
                    break
            except Exception:
                continue
        return "".join(parts)

    def stream_generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> Generator[str, None, None]:
        """Stream tokens as they are generated."""
        if not self.is_available():
            yield ""
            return

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 2048,
            },
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                for line in resp:
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                        token = chunk.get("response", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            break
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"Ollama stream failed: {e}")
            yield ""

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        """Chat API endpoint."""
        if not self.is_available():
            return ""

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 2048,
            },
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/chat",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode())
                return result.get("message", {}).get("content", "")
        except (urllib.error.URLError, TimeoutError) as e:
            logger.warning(f"Ollama chat failed: {e}")
            return ""
        except Exception as e:
            logger.warning(f"Ollama unexpected error: {e}")
            return ""

    # ------------------------------------------------------------------ #
    #  High-level repo analysis tasks                                      #
    # ------------------------------------------------------------------ #

    SYSTEM_PROMPT = """You are an expert software engineer and developer tools specialist.
Analyze repositories and provide clear, concise, actionable insights.
Be specific, technical, and practical. Avoid fluff. Keep responses focused."""

    def explain_repo(self, structure: Dict[str, Any], metadata: Dict[str, Any]) -> str:
        """Generate a plain-English explanation of what the repo does."""
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

    def suggest_cpu_optimizations(
        self,
        frameworks: List[str],
        heavy_deps: List[str],
        ram_gb: int,
    ) -> str:
        """Suggest CPU-specific optimizations."""
        if not self.is_available():
            return self._fallback_cpu_tips(frameworks, ram_gb)

        prompt = f"""Suggest CPU-only optimizations for a Python project:

System: Intel 7th Gen CPU, {ram_gb}GB RAM, no GPU
Frameworks: {', '.join(frameworks) or 'None'}
Heavy packages: {', '.join(heavy_deps) or 'None'}

Give 5 specific, actionable optimizations. Focus on:
- Memory efficiency
- CPU thread usage
- Model/batch size reduction
- Inference speed on CPU
Format as numbered list."""

        response = self.generate(prompt, system=self.SYSTEM_PROMPT, max_tokens=400)
        return response or self._fallback_cpu_tips(frameworks, ram_gb)

    def generate_run_command(self, structure: Dict[str, Any], adaptation: Dict[str, Any]) -> str:
        """Generate the optimal run command based on project analysis."""
        if not self.is_available():
            return ""

        frameworks = [fw["name"] for fw in structure.get("frameworks", [])]
        entry_points = [ep["path"] for ep in structure.get("entry_points", [])]
        project_type = structure.get("project_type", "")

        prompt = f"""Generate the correct command to run this project:

Project Type: {project_type}
Frameworks: {', '.join(frameworks)}
Entry Points: {', '.join(entry_points)}
Adaptations: {len(adaptation.get('package_replacements', []))} packages replaced

Respond with ONLY the run command(s), one per line. No explanation."""

        return self.generate(prompt, system=self.SYSTEM_PROMPT, max_tokens=100, temperature=0.1)

    def answer_question(self, question: str, context: str) -> str:
        """Answer a developer's question about the repo."""
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": f"Context about the repository:\n{context}\n\nQuestion: {question}"},
        ]
        return self.chat(messages, max_tokens=600)

    # ------------------------------------------------------------------ #
    #  Fallbacks (when Ollama unavailable)                                 #
    # ------------------------------------------------------------------ #

    def _fallback_explanation(self, structure: Dict, metadata: Dict) -> str:
        desc = metadata.get("description", "No description available")
        lang = metadata.get("language", "")
        frameworks = [fw["name"] for fw in structure.get("frameworks", [])]
        project_type = structure.get("project_type", "unknown")

        type_descriptions = {
            "web-api-python": "a Python REST API backend",
            "web-fullstack-python": "a Python full-stack web application",
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
            f"1. Set OMP_NUM_THREADS=4 to optimize CPU thread usage",
            f"2. Close other applications to free RAM (you have {ram_gb}GB total)",
            "3. Use smaller model variants when available",
            "4. Enable result caching to avoid repeated computation",
            "5. Monitor with: watch -n2 'free -h && top -bn1 | head -5'",
        ]
        if "PyTorch" in frameworks:
            tips.append("6. Use torch.compile() for PyTorch 2.0+ CPU speedup")
        if "HuggingFace" in frameworks:
            tips.append("6. Use pipeline(..., device='cpu', batch_size=1) for memory efficiency")
        return "\n".join(tips)


class OllamaStatus:
    """Helper to check and display Ollama status."""

    @staticmethod
    def get_status(base_url: str = OLLAMA_BASE_URL) -> Dict[str, Any]:
        client = OllamaClient(base_url)
        is_running = client.is_available()
        models = client.get_available_models() if is_running else []
        best_model = client.get_best_model() if is_running else None

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
