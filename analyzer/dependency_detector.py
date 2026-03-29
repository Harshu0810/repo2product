"""
dependency_detector.py — Repo2Product AI
Extracts, parses, and categorizes dependencies from all known manifest formats.
Provides version parsing, conflict detection, and weight classification.
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Dependency Weight / Resource Database
# ─────────────────────────────────────────────────────────────────────────────

DEPENDENCY_PROFILES: Dict[str, Dict[str, Any]] = {
    # ── Heavy ML/AI libraries ──────────────────────────────────────────────
    "torch": {
        "weight": "heavy", "ram_mb": 2500, "disk_mb": 2000,
        "gpu_optional": True, "cpu_install_mb": 800,
        "alternatives": ["onnxruntime", "tflite"],
        "note": "PyTorch — install CPU-only version: pip install torch --index-url https://download.pytorch.org/whl/cpu",
    },
    "tensorflow": {
        "weight": "heavy", "ram_mb": 2000, "disk_mb": 1500,
        "gpu_optional": True, "cpu_install_mb": 700,
        "alternatives": ["tensorflow-cpu", "tflite-runtime"],
        "note": "Use tensorflow-cpu for CPU-only systems",
    },
    "tensorflow-gpu": {
        "weight": "heavy", "ram_mb": 2500, "disk_mb": 1800,
        "gpu_required": True, "alternatives": ["tensorflow-cpu"],
    },
    "transformers": {
        "weight": "heavy", "ram_mb": 1500, "disk_mb": 500,
        "gpu_optional": True,
        "alternatives": ["llama-cpp-python", "ctransformers"],
        "note": "HuggingFace Transformers — models download separately and can be large",
    },
    "diffusers": {
        "weight": "heavy", "ram_mb": 3000, "disk_mb": 1000,
        "gpu_optional": True, "alternatives": [],
    },
    "xformers": {
        "weight": "heavy", "ram_mb": 500, "disk_mb": 2000,
        "gpu_required": True, "alternatives": [],
    },
    "bitsandbytes": {
        "weight": "heavy", "ram_mb": 300, "disk_mb": 200,
        "gpu_required": True, "alternatives": [],
        "note": "bitsandbytes requires GPU — not compatible with CPU-only",
    },
    "flash-attn": {
        "weight": "heavy", "ram_mb": 500, "disk_mb": 500,
        "gpu_required": True, "alternatives": [],
    },
    "auto-gptq": {
        "weight": "heavy", "ram_mb": 500, "disk_mb": 200,
        "gpu_required": True, "alternatives": ["llama-cpp-python"],
    },
    # ── Medium ML libraries ────────────────────────────────────────────────
    "scikit-learn": {
        "weight": "medium", "ram_mb": 300, "disk_mb": 50,
        "alternatives": [],
    },
    "scipy": {"weight": "medium", "ram_mb": 200, "disk_mb": 100, "alternatives": []},
    "opencv-python": {
        "weight": "medium", "ram_mb": 400, "disk_mb": 200,
        "alternatives": ["opencv-python-headless", "Pillow"],
        "note": "Use opencv-python-headless for server environments",
    },
    "opencv-python-headless": {"weight": "medium", "ram_mb": 300, "disk_mb": 150, "alternatives": []},
    "sentence-transformers": {
        "weight": "heavy", "ram_mb": 1000, "disk_mb": 400,
        "gpu_optional": True, "alternatives": ["gensim"],
    },
    "spacy": {
        "weight": "medium", "ram_mb": 500, "disk_mb": 200,
        "alternatives": ["nltk"],
    },
    "nltk": {"weight": "light", "ram_mb": 100, "disk_mb": 50, "alternatives": []},
    "gensim": {"weight": "medium", "ram_mb": 400, "disk_mb": 100, "alternatives": []},
    "lightgbm": {"weight": "medium", "ram_mb": 200, "disk_mb": 50, "alternatives": []},
    "xgboost": {"weight": "medium", "ram_mb": 200, "disk_mb": 50, "alternatives": []},
    "catboost": {"weight": "medium", "ram_mb": 300, "disk_mb": 100, "alternatives": ["lightgbm"]},
    "faiss-cpu": {"weight": "medium", "ram_mb": 400, "disk_mb": 100, "alternatives": []},
    "faiss-gpu": {
        "weight": "heavy", "ram_mb": 500, "disk_mb": 200,
        "gpu_required": True, "alternatives": ["faiss-cpu"],
    },
    # ── Data libraries ─────────────────────────────────────────────────────
    "pandas": {"weight": "medium", "ram_mb": 200, "disk_mb": 40, "alternatives": ["polars"]},
    "polars": {"weight": "light", "ram_mb": 100, "disk_mb": 30, "alternatives": []},
    "numpy": {"weight": "light", "ram_mb": 100, "disk_mb": 30, "alternatives": []},
    "pyarrow": {"weight": "medium", "ram_mb": 200, "disk_mb": 80, "alternatives": []},
    "dask": {
        "weight": "medium", "ram_mb": 300, "disk_mb": 50,
        "note": "Dask — use distributed=False for single-machine CPU",
    },
    "ray": {
        "weight": "heavy", "ram_mb": 500, "disk_mb": 200,
        "note": "Ray — resource-intensive on CPU, consider disabling",
    },
    # ── Web frameworks ─────────────────────────────────────────────────────
    "fastapi": {"weight": "light", "ram_mb": 50, "disk_mb": 10, "alternatives": []},
    "uvicorn": {"weight": "light", "ram_mb": 30, "disk_mb": 5, "alternatives": []},
    "flask": {"weight": "light", "ram_mb": 40, "disk_mb": 10, "alternatives": []},
    "django": {"weight": "medium", "ram_mb": 100, "disk_mb": 30, "alternatives": ["flask", "fastapi"]},
    "streamlit": {"weight": "medium", "ram_mb": 200, "disk_mb": 50, "alternatives": []},
    "gradio": {"weight": "medium", "ram_mb": 300, "disk_mb": 80, "alternatives": ["streamlit"]},
    "gunicorn": {"weight": "light", "ram_mb": 50, "disk_mb": 5, "alternatives": []},
    "aiohttp": {"weight": "light", "ram_mb": 50, "disk_mb": 10, "alternatives": []},
    # ── Database ───────────────────────────────────────────────────────────
    "sqlalchemy": {"weight": "light", "ram_mb": 80, "disk_mb": 20, "alternatives": []},
    "psycopg2": {"weight": "light", "ram_mb": 30, "disk_mb": 10, "alternatives": ["psycopg2-binary"]},
    "pymongo": {"weight": "light", "ram_mb": 50, "disk_mb": 15, "alternatives": []},
    "redis": {"weight": "light", "ram_mb": 20, "disk_mb": 5, "alternatives": []},
    "elasticsearch": {"weight": "medium", "ram_mb": 100, "disk_mb": 20, "alternatives": []},
    "chromadb": {"weight": "medium", "ram_mb": 300, "disk_mb": 100, "alternatives": ["sqlite-vec"]},
    "pinecone-client": {"weight": "light", "ram_mb": 50, "disk_mb": 10, "requires_api_key": True},
    "weaviate-client": {"weight": "light", "ram_mb": 50, "disk_mb": 10},
    # ── LLM / AI APIs ──────────────────────────────────────────────────────
    "openai": {"weight": "light", "ram_mb": 30, "disk_mb": 5, "requires_api_key": True},
    "anthropic": {"weight": "light", "ram_mb": 30, "disk_mb": 5, "requires_api_key": True},
    "langchain": {"weight": "medium", "ram_mb": 200, "disk_mb": 50},
    "langchain-openai": {"weight": "light", "ram_mb": 50, "disk_mb": 10, "requires_api_key": True},
    "langchain-community": {"weight": "medium", "ram_mb": 200, "disk_mb": 50},
    "ollama": {"weight": "light", "ram_mb": 50, "disk_mb": 10, "local_llm": True},
    "llama-cpp-python": {
        "weight": "medium", "ram_mb": 200, "disk_mb": 100,
        "local_llm": True,
        "note": "llama-cpp-python — CPU-compatible local LLM inference",
    },
    # ── Utilities ──────────────────────────────────────────────────────────
    "requests": {"weight": "light", "ram_mb": 20, "disk_mb": 3},
    "httpx": {"weight": "light", "ram_mb": 25, "disk_mb": 5},
    "pydantic": {"weight": "light", "ram_mb": 50, "disk_mb": 10},
    "pydantic-settings": {"weight": "light", "ram_mb": 30, "disk_mb": 5},
    "python-dotenv": {"weight": "light", "ram_mb": 10, "disk_mb": 2},
    "click": {"weight": "light", "ram_mb": 15, "disk_mb": 3},
    "typer": {"weight": "light", "ram_mb": 20, "disk_mb": 5},
    "rich": {"weight": "light", "ram_mb": 30, "disk_mb": 8},
    "loguru": {"weight": "light", "ram_mb": 15, "disk_mb": 3},
    "celery": {"weight": "medium", "ram_mb": 150, "disk_mb": 20},
    "boto3": {"weight": "medium", "ram_mb": 100, "disk_mb": 50, "requires_api_key": True},
    "pillow": {"weight": "light", "ram_mb": 80, "disk_mb": 30},
    "matplotlib": {"weight": "medium", "ram_mb": 200, "disk_mb": 80},
    "seaborn": {"weight": "light", "ram_mb": 100, "disk_mb": 20},
    "plotly": {"weight": "medium", "ram_mb": 200, "disk_mb": 80},
    "tqdm": {"weight": "light", "ram_mb": 10, "disk_mb": 2},
    "pytest": {"weight": "light", "ram_mb": 50, "disk_mb": 10},
    "tiktoken": {"weight": "light", "ram_mb": 50, "disk_mb": 20},
    "tokenizers": {"weight": "medium", "ram_mb": 200, "disk_mb": 50},
    "accelerate": {
        "weight": "medium", "ram_mb": 200, "disk_mb": 50,
        "gpu_optional": True,
    },
    "peft": {"weight": "medium", "ram_mb": 300, "disk_mb": 50, "gpu_optional": True},
}


# ─────────────────────────────────────────────────────────────────────────────
# DependencyDetector
# ─────────────────────────────────────────────────────────────────────────────

class DependencyDetector:
    """
    Extracts and analyzes dependencies from Python, Node, Go, Rust, and
    other project manifests. Classifies weight, detects GPU requirements,
    and identifies API key dependencies.
    """

    def __init__(self, local_path: Optional[str], key_files: Dict[str, str]):
        self.local_path = Path(local_path) if local_path else None
        self.key_files = key_files  # {relative_path: content}

    # ------------------------------------------------------------------ #
    #  Main analysis entry point                                           #
    # ------------------------------------------------------------------ #

    def analyze(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "python": self._parse_python_deps(),
            "node": self._parse_node_deps(),
            "system": self._parse_system_deps(),
            "docker": self._parse_docker_deps(),
            "summary": {},
        }

        # Build summary
        all_python = result["python"].get("all", [])
        result["summary"] = {
            "total_python_deps": len(all_python),
            "heavy_deps": self._classify_by_weight(all_python, "heavy"),
            "medium_deps": self._classify_by_weight(all_python, "medium"),
            "light_deps": self._classify_by_weight(all_python, "light"),
            "gpu_required": self._check_gpu_required(all_python),
            "gpu_optional": self._check_gpu_optional(all_python),
            "api_key_required": self._check_api_keys(all_python),
            "local_llm_deps": self._check_local_llm(all_python),
            "flagged_issues": self._flag_issues(all_python),
            "resource_estimate": self._estimate_resources(all_python),
        }

        return result

    # ------------------------------------------------------------------ #
    #  Python dependency parsing                                           #
    # ------------------------------------------------------------------ #

    def _parse_python_deps(self) -> Dict[str, Any]:
        deps: Dict[str, Any] = {
            "requirements_txt": [],
            "pipfile": [],
            "pyproject": [],
            "setup_py": [],
            "all": [],
            "projects": {},  # Tracks python dependencies per directory
        }

        # requirements.txt variants
        for path, content in self.key_files.items():
            fname = Path(path).name
            d = str(Path(path).parent)
            if fname.startswith("requirements") and fname.endswith(".txt"):
                parsed = self._parse_requirements_txt(content, source="requirements.txt")
                deps["requirements_txt"].extend(parsed)
                deps["projects"].setdefault(d, []).extend(parsed)
            # Pipfile
            elif fname == "Pipfile":
                parsed = self._parse_pipfile(content)
                deps["pipfile"].extend(parsed)
                deps["projects"].setdefault(d, []).extend(parsed)
            # pyproject.toml
            elif fname == "pyproject.toml":
                parsed = self._parse_pyproject(content)
                deps["pyproject"].extend(parsed)
                deps["projects"].setdefault(d, []).extend(parsed)
            # setup.py
            elif fname == "setup.py":
                parsed = self._parse_setup_py(content)
                deps["setup_py"].extend(parsed)
                deps["projects"].setdefault(d, []).extend(parsed)

        # Merge all, deduplicate by name
        seen = {}
        for source in ("requirements_txt", "pipfile", "pyproject", "setup_py"):
            for dep in deps[source]:
                name = dep["name"].lower()
                if name not in seen:
                    seen[name] = dep
                    deps["all"].append(dep)

        # Enrich with profiles
        for dep in deps["all"]:
            profile = DEPENDENCY_PROFILES.get(dep["name"].lower(), {})
            dep.update({
                "weight": profile.get("weight", "unknown"),
                "ram_mb": profile.get("ram_mb", 0),
                "disk_mb": profile.get("disk_mb", 0),
                "gpu_required": profile.get("gpu_required", False),
                "gpu_optional": profile.get("gpu_optional", False),
                "requires_api_key": profile.get("requires_api_key", False),
                "local_llm": profile.get("local_llm", False),
                "alternatives": profile.get("alternatives", []),
                "note": profile.get("note", ""),
            })

        return deps

    def _parse_requirements_txt(self, content: str, source: str = "requirements.txt") -> List[Dict[str, str]]:
        """Parse requirements.txt format."""
        deps = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-r") or line.startswith("--"):
                continue
            # Handle -e git+... editable installs
            if line.startswith("-e "):
                deps.append({"name": "editable-install", "version": line[3:], "source": source})
                continue
            # Parse: package==1.0, package>=1.0, package[extra], etc.
            match = re.match(r"^([a-zA-Z0-9_\-\.]+)(?:\[.*?\])?\s*([><=!~^].+)?$", line)
            if match:
                deps.append({
                    "name": match.group(1).lower(),
                    "version": match.group(2) or "any",
                    "source": source,
                })
        return deps

    def _parse_pipfile(self, content: str) -> List[Dict[str, str]]:
        """Parse Pipfile TOML-like format."""
        deps = []
        in_packages = False
        for line in content.splitlines():
            line = line.strip()
            if line in ("[packages]", "[dev-packages]"):
                in_packages = True
            elif line.startswith("["):
                in_packages = False
            elif in_packages and "=" in line:
                key, _, val = line.partition("=")
                name = key.strip().strip('"').strip("'").lower()
                version = val.strip().strip('"').strip("'")
                if name:
                    deps.append({"name": name, "version": version, "source": "Pipfile"})
        return deps

    def _parse_pyproject(self, content: str) -> List[Dict[str, str]]:
        """Parse pyproject.toml dependencies section."""
        deps = []
        # Match [tool.poetry.dependencies] or [project] dependencies
        dep_pattern = re.compile(
            r'^([a-zA-Z0-9_\-\.]+)\s*=\s*["\'^~>=<{]', re.MULTILINE
        )
        inline_pattern = re.compile(
            r'"([a-zA-Z0-9_\-\.]+)\s*[><=!~^]'
        )

        # Search for dependencies array (PEP 621)
        deps_section = re.search(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if deps_section:
            for match in inline_pattern.finditer(deps_section.group(1)):
                deps.append({"name": match.group(1).lower(), "version": "any", "source": "pyproject.toml"})

        # Poetry style
        in_deps = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped in ('[tool.poetry.dependencies]', '[tool.poetry.dev-dependencies]'):
                in_deps = True
            elif stripped.startswith('['):
                in_deps = False
            elif in_deps and '=' in stripped and not stripped.startswith('#'):
                m = dep_pattern.match(stripped)
                if m:
                    name = m.group(1).lower()
                    if name not in ('python',):
                        deps.append({"name": name, "version": "any", "source": "pyproject.toml"})

        return deps

    def _parse_setup_py(self, content: str) -> List[Dict[str, str]]:
        """Extract install_requires from setup.py."""
        deps = []
        pattern = re.compile(
            r'install_requires\s*=\s*\[(.*?)\]', re.DOTALL
        )
        match = pattern.search(content)
        if match:
            items = re.findall(r'["\']([^"\']+)["\']', match.group(1))
            for item in items:
                m = re.match(r'^([a-zA-Z0-9_\-\.]+)', item)
                if m:
                    deps.append({"name": m.group(1).lower(), "version": "any", "source": "setup.py"})
        return deps

    # ------------------------------------------------------------------ #
    #  Node.js dependency parsing                                          #
    # ------------------------------------------------------------------ #

    def _parse_node_deps(self) -> Dict[str, Any]:
        projects = {}
        for path, content in self.key_files.items():
            if Path(path).name == "package.json":
                try:
                    pkg = json.loads(content)
                    def flatten(dep_dict: Dict) -> List[Dict]:
                        return [
                            {"name": name, "version": version}
                            for name, version in dep_dict.items()
                        ] if dep_dict else []
                    
                    projects[str(Path(path).parent)] = {
                        "dependencies": flatten(pkg.get("dependencies", {})),
                        "devDependencies": flatten(pkg.get("devDependencies", {})),
                        "scripts": pkg.get("scripts", {}),
                        "engines": pkg.get("engines", {}),
                        "name": pkg.get("name", ""),
                        "main": pkg.get("main", ""),
                    }
                except json.JSONDecodeError:
                    pass

        if not projects:
            return {}
            
        # Select root project or first available as default for backward compatibility
        root_key = next((k for k in projects if k in (".", "")), list(projects.keys())[0])
        result = dict(projects[root_key])
        result["projects"] = projects
        
        return result

    # ------------------------------------------------------------------ #
    #  System / Docker dependency parsing                                  #
    # ------------------------------------------------------------------ #

    def _parse_system_deps(self) -> List[str]:
        """Extract apt/yum packages from shell scripts and Dockerfiles."""
        system_pkgs = []
        patterns = [
            re.compile(r'apt-get install[^&\n]+', re.IGNORECASE),
            re.compile(r'apt install[^&\n]+', re.IGNORECASE),
            re.compile(r'yum install[^&\n]+', re.IGNORECASE),
            re.compile(r'apk add[^&\n]+', re.IGNORECASE),
        ]
        for content in self.key_files.values():
            for pat in patterns:
                for match in pat.finditer(content):
                    system_pkgs.append(match.group(0).strip())
        return list(set(system_pkgs))[:20]

    def _parse_docker_deps(self) -> Dict[str, Any]:
        """Parse Dockerfile for base image and exposed ports."""
        for path in ("Dockerfile", "dockerfile"):
            content = self.key_files.get(path, "")
            if content:
                break
        else:
            return {}

        result = {"base_image": "", "exposed_ports": [], "env_vars": [], "run_commands": []}
        for line in content.splitlines():
            line = line.strip()
            if line.upper().startswith("FROM "):
                result["base_image"] = line[5:].strip()
            elif line.upper().startswith("EXPOSE "):
                ports = re.findall(r'\d+', line)
                result["exposed_ports"].extend(ports)
            elif line.upper().startswith("ENV "):
                result["env_vars"].append(line[4:].strip())
            elif line.upper().startswith("RUN "):
                result["run_commands"].append(line[4:].strip()[:100])
        return result

    # ------------------------------------------------------------------ #
    #  Classification helpers                                              #
    # ------------------------------------------------------------------ #

    def _classify_by_weight(self, deps: List[Dict], weight: str) -> List[str]:
        return [d["name"] for d in deps if d.get("weight") == weight]

    def _check_gpu_required(self, deps: List[Dict]) -> List[str]:
        return [d["name"] for d in deps if d.get("gpu_required")]

    def _check_gpu_optional(self, deps: List[Dict]) -> List[str]:
        return [d["name"] for d in deps if d.get("gpu_optional")]

    def _check_api_keys(self, deps: List[Dict]) -> List[str]:
        return [d["name"] for d in deps if d.get("requires_api_key")]

    def _check_local_llm(self, deps: List[Dict]) -> List[str]:
        return [d["name"] for d in deps if d.get("local_llm")]

    def _flag_issues(self, deps: List[Dict]) -> List[Dict[str, str]]:
        issues = []
        for dep in deps:
            if dep.get("gpu_required"):
                issues.append({
                    "severity": "error",
                    "package": dep["name"],
                    "issue": f"'{dep['name']}' REQUIRES GPU — will not run on CPU-only systems",
                    "fix": f"Alternatives: {', '.join(dep['alternatives']) or 'None known'}",
                })
            elif dep.get("requires_api_key"):
                issues.append({
                    "severity": "warning",
                    "package": dep["name"],
                    "issue": f"'{dep['name']}' requires an API key (paid service)",
                    "fix": "Set the API key in .env or consider local alternatives",
                })
            elif dep.get("weight") == "heavy" and dep.get("gpu_optional"):
                issues.append({
                    "severity": "info",
                    "package": dep["name"],
                    "issue": f"'{dep['name']}' is GPU-accelerated — will run on CPU but slowly",
                    "fix": dep.get("note", "Consider CPU-optimized version"),
                })
        return issues

    def _estimate_resources(self, deps: List[Dict]) -> Dict[str, Any]:
        """Estimate total RAM and disk requirements."""
        total_ram = 200  # base OS overhead
        total_disk = 500  # base Python install

        for dep in deps:
            total_ram += dep.get("ram_mb", 0)
            total_disk += dep.get("disk_mb", 0)

        return {
            "estimated_ram_mb": total_ram,
            "estimated_ram_gb": round(total_ram / 1024, 1),
            "estimated_disk_mb": total_disk,
            "estimated_disk_gb": round(total_disk / 1024, 1),
            "ram_warning": total_ram > 6144,
            "disk_warning": total_disk > 10000,
        }
