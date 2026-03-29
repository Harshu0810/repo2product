"""
structure_parser.py — Repo2Product AI
Deep analysis of repository structure: folder layout, language detection,
framework detection, entry points, and AST-based Python analysis.
"""

import ast
import json
import re
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from collections import defaultdict, Counter
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Framework & Technology Signatures
# ─────────────────────────────────────────────────────────────────────────────

FRAMEWORK_SIGNATURES: Dict[str, Dict[str, Any]] = {
    # Python Web
    "FastAPI": {
        "files": [], "imports": ["fastapi", "FastAPI"],
        "patterns": [r"from fastapi import", r"app = FastAPI\("],
        "category": "web-api", "language": "python",
    },
    "Flask": {
        "files": [], "imports": ["flask", "Flask"],
        "patterns": [r"from flask import", r"app = Flask\("],
        "category": "web-api", "language": "python",
    },
    "Django": {
        "files": ["manage.py", "settings.py"],
        "imports": ["django"],
        "patterns": [r"django\.setup\(\)", r"INSTALLED_APPS"],
        "category": "web-fullstack", "language": "python",
    },
    "Streamlit": {
        "files": [], "imports": ["streamlit"],
        "patterns": [r"import streamlit as st", r"st\.title\("],
        "category": "data-app", "language": "python",
    },
    "Gradio": {
        "files": [], "imports": ["gradio"],
        "patterns": [r"import gradio as gr", r"gr\.Interface"],
        "category": "ml-ui", "language": "python",
    },
    "Celery": {
        "files": [], "imports": ["celery"],
        "patterns": [r"from celery import", r"Celery\("],
        "category": "task-queue", "language": "python",
    },
    "SQLAlchemy": {
        "files": [], "imports": ["sqlalchemy"],
        "patterns": [r"from sqlalchemy import", r"create_engine\("],
        "category": "orm", "language": "python",
    },
    "Pydantic": {
        "files": [], "imports": ["pydantic"],
        "patterns": [r"from pydantic import", r"BaseModel"],
        "category": "validation", "language": "python",
    },
    # ML / AI
    "PyTorch": {
        "files": [], "imports": ["torch"],
        "patterns": [r"import torch", r"torch\.cuda"],
        "category": "ml-framework", "language": "python", "gpu_likely": True,
    },
    "TensorFlow": {
        "files": [], "imports": ["tensorflow", "tf"],
        "patterns": [r"import tensorflow", r"tf\.keras"],
        "category": "ml-framework", "language": "python", "gpu_likely": True,
    },
    "HuggingFace": {
        "files": [], "imports": ["transformers", "datasets", "huggingface_hub"],
        "patterns": [r"from transformers import", r"AutoModel"],
        "category": "nlp", "language": "python", "gpu_likely": True, "heavy": True,
    },
    "LangChain": {
        "files": [], "imports": ["langchain"],
        "patterns": [r"from langchain import", r"LLMChain"],
        "category": "llm-framework", "language": "python",
    },
    "Ollama": {
        "files": [], "imports": ["ollama"],
        "patterns": [r"import ollama", r"ollama\.chat"],
        "category": "llm-local", "language": "python",
    },
    "OpenAI": {
        "files": [], "imports": ["openai"],
        "patterns": [r"import openai", r"openai\.ChatCompletion"],
        "category": "llm-api", "language": "python", "requires_api_key": True,
    },
    "Anthropic": {
        "files": [], "imports": ["anthropic"],
        "patterns": [r"import anthropic"],
        "category": "llm-api", "language": "python", "requires_api_key": True,
    },
    "scikit-learn": {
        "files": [], "imports": ["sklearn"],
        "patterns": [r"from sklearn import", r"import sklearn"],
        "category": "ml-classic", "language": "python",
    },
    "Pandas": {
        "files": [], "imports": ["pandas"],
        "patterns": [r"import pandas as pd"],
        "category": "data", "language": "python",
    },
    "NumPy": {
        "files": [], "imports": ["numpy"],
        "patterns": [r"import numpy as np"],
        "category": "data", "language": "python",
    },
    # JavaScript/Node
    "React": {
        "files": [], "imports": ["react"],
        "patterns": [r"from 'react'", r"from \"react\"", r"React\.createElement"],
        "category": "web-frontend", "language": "javascript",
    },
    "Next.js": {
        "files": ["next.config.js", "next.config.ts"],
        "imports": ["next"],
        "patterns": [r"from 'next'", r"NextApiRequest"],
        "category": "web-fullstack", "language": "javascript",
    },
    "Express": {
        "files": [], "imports": ["express"],
        "patterns": [r"require\('express'\)", r"from 'express'"],
        "category": "web-api", "language": "javascript",
    },
    "Vue": {
        "files": [], "imports": ["vue"],
        "patterns": [r"from 'vue'", r"createApp\("],
        "category": "web-frontend", "language": "javascript",
    },
}

LANGUAGE_EXTENSIONS: Dict[str, str] = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".jsx": "JavaScript", ".tsx": "TypeScript",
    ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin",
    ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".cpp": "C++",
    ".c": "C", ".sh": "Shell", ".yaml": "YAML", ".yml": "YAML",
    ".json": "JSON", ".toml": "TOML", ".md": "Markdown",
    ".html": "HTML", ".css": "CSS", ".scss": "CSS",
    ".sql": "SQL", ".r": "R", ".R": "R",
}

ENTRY_POINT_NAMES = {
    "main.py", "app.py", "run.py", "server.py", "index.py",
    "cli.py", "manage.py", "__main__.py", "start.py", "wsgi.py",
    "asgi.py", "index.js", "server.js", "app.js", "main.js",
    "index.ts", "main.go", "main.rs",
}


# ─────────────────────────────────────────────────────────────────────────────
# RepoStructureParser
# ─────────────────────────────────────────────────────────────────────────────

class RepoStructureParser:
    """
    Parses a cloned (or API-listed) repository and extracts structural,
    linguistic, framework, and entry-point information.
    """

    def __init__(self, local_path: Optional[str] = None, file_list: Optional[list] = None):
        self.local_path = Path(local_path) if local_path else None
        self.file_list: List[str] = file_list or []
        self._analysis_cache: Dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    #  Main analysis entry point                                           #
    # ------------------------------------------------------------------ #

    def analyze(self) -> Dict[str, Any]:
        """Run full structural analysis and return comprehensive report."""
        if self._analysis_cache:
            return self._analysis_cache

        files = self.file_list
        if self.local_path and self.local_path.exists():
            files = self._scan_files()

        result = {
            "file_count": len(files),
            "file_list": files,
            "languages": self._detect_languages(files),
            "primary_language": "",
            "folder_structure": self._build_folder_tree(files),
            "entry_points": self._detect_entry_points(files),
            "frameworks": [],
            "project_type": "",
            "has_tests": self._has_tests(files),
            "has_ci": self._has_ci(files),
            "has_docker": self._has_docker(files),
            "has_docs": self._has_docs(files),
            "config_files": self._find_config_files(files),
            "script_files": self._find_scripts(files),
            "database_files": self._find_database_files(files),
            "api_definitions": self._find_api_definitions(files),
            "env_variables": {},
            "ast_insights": {},
        }

        # Primary language
        if result["languages"]:
            result["primary_language"] = max(
                result["languages"], key=result["languages"].get
            )

        # Framework detection needs file content
        if self.local_path:
            result["frameworks"] = self._detect_frameworks(files)
            result["env_variables"] = self._extract_env_variables(files)
            result["ast_insights"] = self._python_ast_analysis(files)

        result["project_type"] = self._determine_project_type(result)

        self._analysis_cache = result
        return result

    # ------------------------------------------------------------------ #
    #  Language detection                                                  #
    # ------------------------------------------------------------------ #

    def _detect_languages(self, files: List[str]) -> Dict[str, int]:
        counts: Counter = Counter()
        skip_dirs = {"node_modules", ".git", "__pycache__", "venv", ".venv", "dist", "build"}
        for f in files:
            parts = Path(f).parts
            if any(p in skip_dirs for p in parts):
                continue
            ext = Path(f).suffix.lower()
            lang = LANGUAGE_EXTENSIONS.get(ext)
            if lang and lang not in ("YAML", "JSON", "TOML", "Markdown"):
                counts[lang] += 1
        return dict(counts)

    # ------------------------------------------------------------------ #
    #  Folder tree                                                         #
    # ------------------------------------------------------------------ #

    def _build_folder_tree(self, files: List[str], max_depth: int = 3) -> Dict:
        tree: Dict = {}
        for f in files:
            parts = Path(f).parts
            if len(parts) > max_depth + 1:
                parts = parts[:max_depth] + ("...",)
            node = tree
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            leaf = parts[-1] if parts else f
            node[leaf] = None  # leaf node
        return tree

    def _tree_to_string(self, tree: Dict, prefix: str = "", depth: int = 0) -> str:
        if depth > 4:
            return ""
        lines = []
        items = sorted(tree.items(), key=lambda x: (x[1] is None, x[0]))
        for i, (name, subtree) in enumerate(items):
            connector = "└── " if i == len(items) - 1 else "├── "
            lines.append(f"{prefix}{connector}{name}")
            if subtree is not None:
                extension = "    " if i == len(items) - 1 else "│   "
                lines.append(self._tree_to_string(subtree, prefix + extension, depth + 1))
        return "\n".join(filter(None, lines))

    def get_tree_string(self) -> str:
        result = self.analyze()
        return self._tree_to_string(result["folder_structure"])

    # ------------------------------------------------------------------ #
    #  Entry point detection                                              #
    # ------------------------------------------------------------------ #

    def _detect_entry_points(self, files: List[str]) -> List[Dict[str, str]]:
        entries = []
        for f in files:
            fname = Path(f).name
            if fname in ENTRY_POINT_NAMES:
                entries.append({
                    "path": f,
                    "name": fname,
                    "type": self._classify_entry_point(f),
                })
        return entries

    def _classify_entry_point(self, path: str) -> str:
        name = Path(path).name
        mapping = {
            "manage.py": "django-management",
            "wsgi.py": "wsgi-server",
            "asgi.py": "asgi-server",
            "cli.py": "cli",
            "__main__.py": "module-main",
        }
        return mapping.get(name, "main-entry")

    # ------------------------------------------------------------------ #
    #  Framework detection                                                 #
    # ------------------------------------------------------------------ #

    def _detect_frameworks(self, files: List[str]) -> List[Dict[str, Any]]:
        detected = []
        file_names = {Path(f).name for f in files}

        # Content to search (sample Python and JS files)
        content_samples = self._sample_source_content(files, max_files=40)

        for fw_name, sig in FRAMEWORK_SIGNATURES.items():
            confidence = 0
            evidence = []

            # File existence check
            for req_file in sig.get("files", []):
                if req_file in file_names:
                    confidence += 40
                    evidence.append(f"Found file: {req_file}")

            # Pattern matching in source
            for pattern in sig.get("patterns", []):
                for content in content_samples.values():
                    if re.search(pattern, content):
                        confidence += 30
                        evidence.append(f"Pattern matched: {pattern[:50]}")
                        break

            if confidence >= 30:
                fw_info = {
                    "name": fw_name,
                    "confidence": min(confidence, 100),
                    "category": sig.get("category", "unknown"),
                    "language": sig.get("language", "unknown"),
                    "evidence": evidence[:3],
                }
                for flag in ("gpu_likely", "heavy", "requires_api_key"):
                    if sig.get(flag):
                        fw_info[flag] = True
                detected.append(fw_info)

        # Sort by confidence
        detected.sort(key=lambda x: x["confidence"], reverse=True)
        return detected

    def _sample_source_content(self, files: List[str], max_files: int = 40) -> Dict[str, str]:
        """Read a sample of source files for pattern matching."""
        if not self.local_path:
            return {}
        content = {}
        exts = {".py", ".js", ".ts", ".jsx", ".tsx"}
        count = 0
        for f in files:
            if count >= max_files:
                break
            if Path(f).suffix in exts:
                full = self.local_path / f
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as fh:
                        content[f] = fh.read(10_000)
                    count += 1
                except Exception:
                    pass
        return content

    # ------------------------------------------------------------------ #
    #  Env variable extraction                                             #
    # ------------------------------------------------------------------ #

    def _extract_env_variables(self, files: List[str]) -> Dict[str, str]:
        """Extract required env variables from .env.example and source."""
        env_vars: Dict[str, str] = {}

        # From .env.example
        for f in files:
            fname = Path(f).name
            if fname in (".env.example", ".env.sample", ".env.template"):
                full = self.local_path / f
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as fh:
                        for line in fh:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                key, _, val = line.partition("=")
                                env_vars[key.strip()] = val.strip()
                except Exception:
                    pass

        # Scan source for os.environ / os.getenv patterns
        pattern = re.compile(r'os\.(?:environ\.get|getenv)\(["\']([A-Z_][A-Z0-9_]*)["\']')
        for f in files:
            if Path(f).suffix == ".py":
                full = self.local_path / f
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as fh:
                        for match in pattern.finditer(fh.read(20_000)):
                            key = match.group(1)
                            if key not in env_vars:
                                env_vars[key] = "<required>"
                except Exception:
                    pass

        return env_vars

    # ------------------------------------------------------------------ #
    #  Python AST Analysis                                                 #
    # ------------------------------------------------------------------ #

    def _python_ast_analysis(self, files: List[str]) -> Dict[str, Any]:
        """Deep AST analysis of Python files."""
        insights: Dict[str, Any] = {
            "total_functions": 0,
            "total_classes": 0,
            "imports": Counter(),
            "main_patterns": [],
            "async_code": False,
            "type_hints": False,
            "decorators": Counter(),
        }

        py_files = [f for f in files if Path(f).suffix == ".py"][:50]

        for f in py_files:
            if not self.local_path:
                continue
            full = self.local_path / f
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    source = fh.read(100_000)
                tree = ast.parse(source, filename=str(full))
                self._walk_ast(tree, insights, f)
            except SyntaxError:
                pass
            except Exception as e:
                logger.debug(f"AST parse error {f}: {e}")

        insights["top_imports"] = dict(insights["imports"].most_common(20))
        insights["top_decorators"] = dict(insights["decorators"].most_common(10))
        del insights["imports"]
        del insights["decorators"]
        return insights

    def _walk_ast(self, tree: ast.AST, insights: Dict, filepath: str):
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                insights["total_functions"] += 1
                if isinstance(node, ast.AsyncFunctionDef):
                    insights["async_code"] = True
                # Check decorators
                for dec in node.decorator_list:
                    dec_name = self._get_decorator_name(dec)
                    if dec_name:
                        insights["decorators"][dec_name] += 1
                # Check return annotations
                if node.returns:
                    insights["type_hints"] = True

            elif isinstance(node, ast.ClassDef):
                insights["total_classes"] += 1

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    insights["imports"][alias.name.split(".")[0]] += 1

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    insights["imports"][node.module.split(".")[0]] += 1

            elif isinstance(node, ast.If):
                # Detect if __name__ == '__main__' pattern
                test = node.test
                if (
                    isinstance(test, ast.Compare)
                    and isinstance(test.left, ast.Name)
                    and test.left.id == "__name__"
                ):
                    insights["main_patterns"].append(filepath)

    def _get_decorator_name(self, node: ast.expr) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._get_decorator_name(node.value)}.{node.attr}"
        if isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return None

    # ------------------------------------------------------------------ #
    #  Metadata checks                                                     #
    # ------------------------------------------------------------------ #

    def _has_tests(self, files: List[str]) -> bool:
        test_patterns = {"test_", "_test", "tests/", "test/", "spec/", "__tests__/"}
        return any(any(p in f for p in test_patterns) for f in files)

    def _has_ci(self, files: List[str]) -> bool:
        ci_paths = {".github/workflows", ".travis.yml", ".circleci", "Jenkinsfile", ".gitlab-ci.yml"}
        return any(any(ci in f for ci in ci_paths) for f in files)

    def _has_docker(self, files: List[str]) -> bool:
        docker_files = {"Dockerfile", "docker-compose.yml", "docker-compose.yaml"}
        return any(Path(f).name in docker_files for f in files)

    def _has_docs(self, files: List[str]) -> bool:
        doc_dirs = {"docs/", "documentation/", "doc/", "wiki/"}
        return any(any(d in f for d in doc_dirs) for f in files)

    def _find_config_files(self, files: List[str]) -> List[str]:
        config_names = {
            "config.py", "config.yaml", "config.yml", "config.json",
            "settings.py", "settings.yaml", "settings.yml",
            "pyproject.toml", "setup.cfg", ".flake8", ".pylintrc",
        }
        return [f for f in files if Path(f).name in config_names]

    def _find_scripts(self, files: List[str]) -> List[str]:
        return [f for f in files if Path(f).suffix in (".sh", ".bat", ".ps1")
                or Path(f).name in ("Makefile", "makefile", "Taskfile.yml")]

    def _find_database_files(self, files: List[str]) -> List[str]:
        db_exts = {".sql", ".db", ".sqlite", ".sqlite3"}
        db_names = {"migrations/", "alembic/", "schema.sql", "schema.py"}
        return [
            f for f in files
            if Path(f).suffix in db_exts or any(d in f for d in db_names)
        ]

    def _find_api_definitions(self, files: List[str]) -> List[str]:
        api_names = {"openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json", "api.yaml"}
        return [f for f in files if Path(f).name in api_names]

    # ------------------------------------------------------------------ #
    #  Project type classification                                         #
    # ------------------------------------------------------------------ #

    def _determine_project_type(self, analysis: Dict) -> str:
        frameworks = {fw["name"] for fw in analysis.get("frameworks", [])}
        primary_lang = analysis.get("primary_language", "")

        backend_fws = {"FastAPI", "Flask", "Django", "Express"}
        frontend_fws = {"React", "Vue", "Next.js"}
        
        has_backend = any(fw in backend_fws for fw in frameworks)
        has_frontend = any(fw in frontend_fws for fw in frameworks)
        
        if has_backend and has_frontend:
            return "fullstack"

        type_matrix = [
            ({"Django"}, "web-fullstack-python"),
            ({"FastAPI"}, "web-api-python"),
            ({"Flask"}, "web-api-python"),
            ({"Next.js"}, "web-fullstack-node"),
            ({"React", "Vue"}, "web-frontend"),
            ({"Streamlit"}, "data-app-streamlit"),
            ({"Gradio"}, "ml-demo-gradio"),
            ({"PyTorch", "TensorFlow"}, "ml-training"),
            ({"HuggingFace"}, "nlp-huggingface"),
            ({"LangChain", "OpenAI", "Anthropic"}, "llm-application"),
            ({"Celery"}, "task-queue"),
        ]

        for fw_set, proj_type in type_matrix:
            if fw_set & frameworks:
                return proj_type

        # Fallback by language
        lang_fallback = {
            "Python": "python-script",
            "JavaScript": "node-app",
            "TypeScript": "node-app",
            "Go": "go-app",
            "Rust": "rust-app",
            "Java": "java-app",
        }
        return lang_fallback.get(primary_lang, "unknown")

    # ------------------------------------------------------------------ #
    #  Local file scanning                                                 #
    # ------------------------------------------------------------------ #

    def _scan_files(self, max_files: int = 2000) -> List[str]:
        if not self.local_path or not self.local_path.exists():
            return []
        skip_dirs = {".git", "__pycache__", "node_modules", ".tox", "venv",
                     ".venv", "dist", "build", ".mypy_cache", ".pytest_cache"}
        files = []
        for p in self.local_path.rglob("*"):
            if p.is_file():
                rel = p.relative_to(self.local_path)
                if not any(part in skip_dirs for part in rel.parts):
                    files.append(str(rel))
                    if len(files) >= max_files:
                        break
        return files
