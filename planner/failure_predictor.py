"""
planner/failure_predictor.py — Repo2Product AI
Pre-flight failure prediction engine. Checks for common setup issues
before the user attempts to run the project.
"""

import re
import os
import sys
import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class FailurePrediction:
    def __init__(self, level: str, category: str, message: str,
                 fix: str, auto_fixable: bool = False):
        self.level = level  # critical / warning / info
        self.category = category
        self.message = message
        self.fix = fix
        self.auto_fixable = auto_fixable

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "category": self.category,
            "message": self.message,
            "fix": self.fix,
            "auto_fixable": self.auto_fixable,
        }


class FailurePredictor:
    """
    Analyzes a project before execution and predicts likely failure points.
    Produces actionable fixes for each predicted failure.
    """

    def __init__(
        self,
        structure: Dict[str, Any],
        dependency_analysis: Dict[str, Any],
        adaptation: Dict[str, Any],
        user_constraints: Dict[str, Any],
        local_path: Optional[str] = None,
    ):
        self.structure = structure
        self.deps = dependency_analysis
        self.adaptation = adaptation
        self.constraints = user_constraints
        self.local_path = Path(local_path) if local_path else None
        self.predictions: List[FailurePrediction] = []

    # ------------------------------------------------------------------ #
    #  Main prediction entry point                                         #
    # ------------------------------------------------------------------ #

    def predict(self) -> Dict[str, Any]:
        """Run all checks and return prediction report."""
        self.predictions = []

        self._check_python_version()
        self._check_missing_entry_points()
        self._check_gpu_only_packages()
        self._check_missing_env_variables()
        self._check_api_keys_without_alternatives()
        self._check_conflicting_dependencies()
        self._check_system_resources()
        self._check_missing_system_deps()
        self._check_port_conflicts()
        self._check_database_requirements()
        self._check_file_permissions()
        self._check_ollama_availability()
        self._check_internet_requirements()
        self._check_version_incompatibilities()

        preds = [p.to_dict() for p in self.predictions]

        criticals = [p for p in preds if p["level"] == "critical"]
        warnings = [p for p in preds if p["level"] == "warning"]
        infos = [p for p in preds if p["level"] == "info"]

        overall_risk = (
            "HIGH" if criticals else
            "MEDIUM" if warnings else
            "LOW"
        )

        return {
            "overall_risk": overall_risk,
            "can_proceed": len(criticals) == 0,
            "predictions": preds,
            "criticals": criticals,
            "warnings": warnings,
            "infos": infos,
            "summary": {
                "total": len(preds),
                "critical": len(criticals),
                "warning": len(warnings),
                "info": len(infos),
            },
            "pre_run_checklist": self._generate_checklist(preds),
        }

    # ------------------------------------------------------------------ #
    #  Individual checks                                                   #
    # ------------------------------------------------------------------ #

    def _check_python_version(self):
        current = f"{sys.version_info.major}.{sys.version_info.minor}"
        required = self.constraints.get("python_version", "3.8")
        try:
            req_major, req_minor = map(int, required.split(".")[:2])
            if sys.version_info < (req_major, req_minor):
                self.predictions.append(FailurePrediction(
                    level="critical",
                    category="python_version",
                    message=f"Python {current} detected but {required}+ required",
                    fix=f"Install Python {required}: pyenv install {required} or download from python.org",
                ))
        except Exception:
            pass

    def _check_missing_entry_points(self):
        entries = self.structure.get("entry_points", [])
        file_list = self.structure.get("file_list", [])

        if not entries:
            self.predictions.append(FailurePrediction(
                level="warning",
                category="entry_point",
                message="No standard entry point detected (main.py, app.py, etc.)",
                fix="Review the README to find the correct startup command",
            ))
        else:
            for ep in entries:
                if ep["path"] not in file_list and self.local_path:
                    full = self.local_path / ep["path"]
                    if not full.exists():
                        self.predictions.append(FailurePrediction(
                            level="critical",
                            category="entry_point",
                            message=f"Entry point '{ep['path']}' not found in repo",
                            fix="Check the repository — file may have been moved or renamed",
                        ))

    def _check_gpu_only_packages(self):
        gpu_required = self.deps.get("summary", {}).get("gpu_required", [])
        if gpu_required and not self.constraints.get("has_gpu", False):
            for pkg in gpu_required:
                removed = [r["package"] for r in self.adaptation.get("removed_packages", [])]
                if pkg not in removed:
                    self.predictions.append(FailurePrediction(
                        level="critical",
                        category="gpu_dependency",
                        message=f"'{pkg}' requires GPU but no GPU available",
                        fix=f"Use adapted requirements.txt (remove '{pkg}') or find CPU alternative",
                        auto_fixable=True,
                    ))

    def _check_missing_env_variables(self):
        env_vars = self.structure.get("env_variables", {})
        if not env_vars:
            return

        missing = []
        for var, default in env_vars.items():
            # Check if it's a required API key
            if "KEY" in var or "SECRET" in var or "TOKEN" in var:
                env_val = os.environ.get(var, "")
                if not env_val:
                    missing.append(var)

        if missing:
            self.predictions.append(FailurePrediction(
                level="warning",
                category="env_variables",
                message=f"Missing environment variables: {', '.join(missing[:5])}",
                fix="Add these to your .env file before running",
            ))

    def _check_api_keys_without_alternatives(self):
        api_deps = self.deps.get("summary", {}).get("api_key_required", [])
        replacements = {r["original"] for r in self.adaptation.get("package_replacements", [])}

        for dep in api_deps:
            if dep not in replacements:
                self.predictions.append(FailurePrediction(
                    level="warning",
                    category="api_key",
                    message=f"'{dep}' requires a paid API key — no local alternative configured",
                    fix=f"Either set {dep.upper()}_API_KEY in .env or replace with Ollama (local)",
                ))

    def _check_conflicting_dependencies(self):
        """Detect known version conflicts."""
        python_deps = {d["name"]: d.get("version", "any") for d in self.deps.get("python", {}).get("all", [])}

        KNOWN_CONFLICTS = [
            ("torch", "tensorflow", "PyTorch and TensorFlow may conflict — install in separate venvs"),
            ("langchain", "openai", "LangChain and openai versions must be compatible"),
        ]

        for dep1, dep2, msg in KNOWN_CONFLICTS:
            if dep1 in python_deps and dep2 in python_deps:
                self.predictions.append(FailurePrediction(
                    level="info",
                    category="version_conflict",
                    message=f"Potential conflict: {dep1} + {dep2}",
                    fix=msg,
                ))

        # Heavy deps that together might OOM
        heavy_deps = self.deps.get("summary", {}).get("heavy_deps", [])
        if len(heavy_deps) > 3:
            ram_gb = self.constraints.get("ram_gb", 8)
            self.predictions.append(FailurePrediction(
                level="warning",
                category="memory",
                message=f"{len(heavy_deps)} heavy packages detected — may exceed {ram_gb}GB RAM",
                fix="Only import what you need, use lazy loading, or use streaming inference",
            ))

    def _check_system_resources(self):
        ram_gb = self.constraints.get("ram_gb", 8)
        est = self.deps.get("summary", {}).get("resource_estimate", {})
        est_gb = est.get("estimated_ram_gb", 0)

        if est_gb > ram_gb * 0.9:
            self.predictions.append(FailurePrediction(
                level="critical",
                category="memory",
                message=f"Estimated RAM ({est_gb}GB) exceeds available RAM ({ram_gb}GB)",
                fix="Reduce batch sizes, use model quantization, or close other applications",
            ))
        elif est_gb > ram_gb * 0.7:
            self.predictions.append(FailurePrediction(
                level="warning",
                category="memory",
                message=f"High memory usage expected ({est_gb}GB of {ram_gb}GB available)",
                fix="Close Chrome, IDEs, and other apps before running",
            ))

        disk_gb = est.get("estimated_disk_gb", 0)
        if disk_gb > 30:  # User has 40GB disk
            self.predictions.append(FailurePrediction(
                level="warning",
                category="disk",
                message=f"Installation requires ~{disk_gb}GB disk space",
                fix="Free up disk space or install to a separate drive",
            ))

    def _check_missing_system_deps(self):
        system_deps = self.deps.get("system", [])
        python_deps = {d["name"] for d in self.deps.get("python", {}).get("all", [])}

        # Check for packages needing system libs
        SYSTEM_LIB_REQUIREMENTS = {
            "psycopg2": ("libpq-dev", "PostgreSQL dev library"),
            "Pillow": ("libjpeg-dev zlib1g-dev", "Image processing libraries"),
            "lxml": ("libxml2-dev libxslt-dev", "XML processing libraries"),
            "cryptography": ("libssl-dev libffi-dev", "Crypto libraries"),
        }

        for dep, (sys_pkg, desc) in SYSTEM_LIB_REQUIREMENTS.items():
            if dep.lower() in python_deps:
                self.predictions.append(FailurePrediction(
                    level="info",
                    category="system_library",
                    message=f"'{dep}' may need system library: {sys_pkg}",
                    fix=f"sudo apt install {sys_pkg}  # {desc}",
                ))

    def _check_port_conflicts(self):
        """Check if common ports are already in use."""
        frameworks = self.structure.get("frameworks", [])
        fw_names = {fw["name"] for fw in frameworks}

        PORT_MAP = {
            "FastAPI": 8000,
            "Flask": 5000,
            "Django": 8000,
            "Streamlit": 8501,
            "Gradio": 7860,
        }

        for fw, port in PORT_MAP.items():
            if fw in fw_names:
                if self._is_port_in_use(port):
                    self.predictions.append(FailurePrediction(
                        level="warning",
                        category="port_conflict",
                        message=f"Port {port} ({fw}) may already be in use",
                        fix=f"Kill the process: `lsof -i :{port} | awk 'NR>1 {{print $2}}' | xargs kill`",
                    ))

    def _is_port_in_use(self, port: int) -> bool:
        try:
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex(("localhost", port)) == 0
        except Exception:
            return False

    def _check_database_requirements(self):
        frameworks = {fw["name"] for fw in self.structure.get("frameworks", [])}
        file_list = self.structure.get("file_list", [])

        if "Django" in frameworks:
            # Check for migrations
            has_migrations = any("migrations" in f for f in file_list)
            if not has_migrations:
                self.predictions.append(FailurePrediction(
                    level="info",
                    category="database",
                    message="Django project with no migrations directory",
                    fix="Run: python manage.py makemigrations && python manage.py migrate",
                ))

        dep_names = {d["name"] for d in self.deps.get("python", {}).get("all", [])}
        if "psycopg2" in dep_names or "psycopg2-binary" in dep_names:
            self.predictions.append(FailurePrediction(
                level="info",
                category="database",
                message="PostgreSQL dependency detected — requires PostgreSQL server",
                fix="Install PostgreSQL: sudo apt install postgresql OR use SQLite for development",
            ))

    def _check_file_permissions(self):
        if not self.local_path:
            return
        scripts = self.structure.get("script_files", [])
        for script in scripts:
            full = self.local_path / script
            if full.suffix in (".sh",) and full.exists():
                if not os.access(full, os.X_OK):
                    self.predictions.append(FailurePrediction(
                        level="warning",
                        category="permissions",
                        message=f"Script '{script}' not executable",
                        fix=f"Run: chmod +x {script}",
                        auto_fixable=True,
                    ))

    def _check_ollama_availability(self):
        """Check if Ollama is needed and available."""
        fw_names = {fw["name"] for fw in self.structure.get("frameworks", [])}
        use_ollama = self.constraints.get("use_ollama", False)
        has_ollama_replacement = any(
            r.get("replacement") == "ollama (local)"
            for r in self.adaptation.get("package_replacements", [])
        )

        if ("Ollama" in fw_names or use_ollama or has_ollama_replacement):
            # Try to connect to Ollama
            if not self._ollama_running():
                self.predictions.append(FailurePrediction(
                    level="warning",
                    category="ollama",
                    message="Ollama server not running",
                    fix="Start Ollama: `ollama serve` in a separate terminal",
                ))
            else:
                self.predictions.append(FailurePrediction(
                    level="info",
                    category="ollama",
                    message="Ollama server is running ✓",
                    fix="",
                ))

    def _ollama_running(self) -> bool:
        return self._is_port_in_use(11434)

    def _check_internet_requirements(self):
        """Warn about features needing internet on first run."""
        dep_names = {d["name"] for d in self.deps.get("python", {}).get("all", [])}
        if "transformers" in dep_names:
            self.predictions.append(FailurePrediction(
                level="info",
                category="network",
                message="HuggingFace transformers will download models on first run",
                fix="Ensure internet connection for first run. Set HF_HUB_OFFLINE=1 for offline mode after download",
            ))
        if "sentence-transformers" in dep_names:
            self.predictions.append(FailurePrediction(
                level="info",
                category="network",
                message="sentence-transformers downloads embedding models on first run",
                fix="Pre-download models: `python -c \"from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')\"`",
            ))

    def _check_version_incompatibilities(self):
        python_deps = {d["name"]: d.get("version", "any") for d in self.deps.get("python", {}).get("all", [])}
        py_ver = sys.version_info

        PYTHON_INCOMPATIBILITIES = [
            ("torch", (3, 12), "PyTorch support for Python 3.12 is limited in older versions"),
            ("tensorflow", (3, 12), "TensorFlow may have issues with Python 3.12"),
        ]

        for pkg, max_py, msg in PYTHON_INCOMPATIBILITIES:
            if pkg in python_deps and py_ver >= max_py:
                self.predictions.append(FailurePrediction(
                    level="warning",
                    category="version_compat",
                    message=f"Python {py_ver.major}.{py_ver.minor} may have compatibility issues with '{pkg}'",
                    fix=f"{msg}. Consider using Python 3.10 or 3.11",
                ))

    # ------------------------------------------------------------------ #
    #  Checklist generation                                                #
    # ------------------------------------------------------------------ #

    def _generate_checklist(self, predictions: List[Dict]) -> List[Dict[str, Any]]:
        checklist = [
            {"item": "Virtual environment activated", "required": True, "category": "setup"},
            {"item": "requirements.txt installed (adapted version)", "required": True, "category": "setup"},
            {"item": ".env file created with all required variables", "required": True, "category": "config"},
            {"item": "Database initialized (if applicable)", "required": False, "category": "database"},
            {"item": "Ollama running (if using local LLM)", "required": False, "category": "llm"},
            {"item": "Sufficient free disk space (check with: df -h)", "required": True, "category": "system"},
            {"item": "Other memory-heavy apps closed", "required": True, "category": "system"},
        ]

        # Add items from critical predictions
        for pred in predictions:
            if pred["level"] == "critical":
                checklist.append({
                    "item": f"RESOLVED: {pred['message'][:60]}",
                    "required": True,
                    "category": pred["category"],
                    "fix": pred["fix"],
                })

        return checklist
