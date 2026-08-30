"""
planner/failure_predictor.py — Repo2Product AI
Pre-flight failure prediction engine. Checks for common setup issues
before the user attempts to run the project.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import logging

from utils.runtime import CLOUD_MODE

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
    #  Target-environment helpers                                          #
    # ------------------------------------------------------------------ #

    def _target_python(self) -> Optional[Tuple[int, int]]:
        """
        The Python version the *user* will run the project on, as declared in
        the sidebar. Never `sys.version_info` — that is the version of the
        server rendering this app, which tells us nothing about the user's box.
        """
        declared = str(self.constraints.get("python_version", "") or "")
        return self._parse_version(declared)

    @staticmethod
    def _parse_version(value: str) -> Optional[Tuple[int, int]]:
        parts = re.findall(r"\d+", value or "")
        if not parts:
            return None
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        return (major, minor)

    def _required_python(self) -> Optional[Tuple[int, int]]:
        """Minimum Python the project itself declares, if any."""
        req = self.deps.get("python_requirement", {}) or {}
        return self._parse_version(req.get("minimum", ""))

    # ------------------------------------------------------------------ #
    #  Individual checks                                                   #
    # ------------------------------------------------------------------ #

    def _check_python_version(self):
        target = self._target_python()
        required = self._required_python()
        if not target or not required:
            return

        req = self.deps.get("python_requirement", {}) or {}
        declared = req.get("declared", ".".join(str(p) for p in required))
        source = req.get("source", "the project manifest")
        target_str = ".".join(str(p) for p in target)

        if target < required:
            self.predictions.append(FailurePrediction(
                level="critical",
                category="python_version",
                message=(
                    f"Project requires Python {declared} (from {source}) "
                    f"but you selected {target_str}"
                ),
                fix=(
                    f"Install a newer Python: `pyenv install {declared.lstrip('>=~^ ')}` "
                    f"or download it from python.org, then recreate the venv"
                ),
            ))

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
            return

        for ep in entries:
            if ep["path"] in file_list:
                continue
            # Not in the listing. With a local clone we can confirm on disk;
            # in API-only mode the tree listing *is* the source of truth.
            if self.local_path and (self.local_path / ep["path"]).exists():
                continue
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

        secretish = [v for v in env_vars
                     if "KEY" in v or "SECRET" in v or "TOKEN" in v or "PASSWORD" in v]
        if not secretish:
            return

        if CLOUD_MODE:
            # We are running on a shared server. os.environ here belongs to the
            # Space container, not to the person downloading the package, so
            # every secret is "missing" as far as they are concerned.
            missing = secretish
        else:
            missing = [v for v in secretish if not os.environ.get(v)]

        if missing:
            shown = ", ".join(missing[:5])
            extra = f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""
            self.predictions.append(FailurePrediction(
                level="warning",
                category="env_variables",
                message=f"Secrets referenced by the code must be provided: {shown}{extra}",
                fix="Copy .env.template to .env and fill in these values before running",
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
        python_deps = {d["name"] for d in self.deps.get("python", {}).get("all", [])}

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
        disk_budget = self.constraints.get("disk_gb")
        if disk_budget:
            if disk_gb > disk_budget * 0.9:
                self.predictions.append(FailurePrediction(
                    level="critical",
                    category="disk",
                    message=f"Installation needs ~{disk_gb}GB but only {disk_budget}GB is free",
                    fix="Free up disk space, or install to a separate drive with `pip install --target`",
                ))
            elif disk_gb > disk_budget * 0.7:
                self.predictions.append(FailurePrediction(
                    level="warning",
                    category="disk",
                    message=f"Installation needs ~{disk_gb}GB of your {disk_budget}GB free space",
                    fix="Clear the pip cache first: `pip cache purge`",
                ))
        elif disk_gb > 10:
            self.predictions.append(FailurePrediction(
                level="warning",
                category="disk",
                message=f"Installation requires ~{disk_gb}GB disk space",
                fix="Check free space with `df -h .` before installing",
            ))

    def _check_missing_system_deps(self):
        python_deps = {d["name"].lower() for d in self.deps.get("python", {}).get("all", [])}

        # Packages that build from C sources when no wheel matches the host.
        # Keys are already in the detector's normalized (lower-case) form.
        SYSTEM_LIB_REQUIREMENTS = {
            "psycopg2": ("libpq-dev", "PostgreSQL client library"),
            "mysqlclient": ("default-libmysqlclient-dev", "MySQL client library"),
            "pillow": ("libjpeg-dev zlib1g-dev", "JPEG/PNG codecs"),
            "lxml": ("libxml2-dev libxslt-dev", "XML processing libraries"),
            "cryptography": ("libssl-dev libffi-dev", "OpenSSL and libffi"),
            "pyaudio": ("portaudio19-dev", "PortAudio headers"),
            "opencv-python": ("libgl1 libglib2.0-0", "OpenGL/GLib runtime for cv2"),
        }

        for dep, (sys_pkg, desc) in SYSTEM_LIB_REQUIREMENTS.items():
            if dep in python_deps:
                self.predictions.append(FailurePrediction(
                    level="info",
                    category="system_library",
                    message=f"'{dep}' needs {desc} if pip has to build it from source",
                    fix=f"On Debian/Ubuntu: sudo apt install {sys_pkg}",
                ))

    def _check_port_conflicts(self):
        """Check whether the ports this project wants are already taken."""
        frameworks = self.structure.get("frameworks", [])
        fw_names = {fw["name"] for fw in frameworks}

        PORT_MAP = {
            "FastAPI": 8000,
            "Flask": 5000,
            "Django": 8000,
            "Streamlit": 8501,
            "Gradio": 7860,
        }

        wanted = sorted({port for fw, port in PORT_MAP.items() if fw in fw_names})
        if not wanted:
            return

        if CLOUD_MODE:
            # A socket probe here would test the Space container, not the
            # machine that will actually run the project. Advise instead.
            ports = ", ".join(str(p) for p in wanted)
            self.predictions.append(FailurePrediction(
                level="info",
                category="port_conflict",
                message=f"This project binds port(s) {ports} — make sure they are free locally",
                fix=f"Check with: `lsof -i :{wanted[0]}` (macOS/Linux) or "
                    f"`netstat -ano | findstr :{wanted[0]}` (Windows)",
            ))
            return

        for port in wanted:
            if self._is_port_in_use(port):
                self.predictions.append(FailurePrediction(
                    level="warning",
                    category="port_conflict",
                    message=f"Port {port} is already in use on this machine",
                    fix=f"Kill the process: `lsof -ti :{port} | xargs kill` "
                        f"or run the app on a different port",
                ))

    def _is_port_in_use(self, port: int) -> bool:
        if CLOUD_MODE:
            return False
        try:
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.25)
                return s.connect_ex(("127.0.0.1", port)) == 0
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
        # The exec bit only exists on POSIX filesystems. On Windows
        # os.access(path, X_OK) is true for every readable file, so the check
        # would report nothing and mean nothing.
        if not self.local_path or os.name == "nt":
            return
        for script in self.structure.get("script_files", []):
            full = self.local_path / script
            if full.suffix != ".sh" or not full.is_file():
                continue
            if not full.stat().st_mode & 0o111:
                self.predictions.append(FailurePrediction(
                    level="warning",
                    category="permissions",
                    message=f"Script '{script}' is not executable",
                    fix=f"Run: chmod +x {script}",
                    auto_fixable=True,
                ))

    def _check_ollama_availability(self):
        """Flag Ollama as a prerequisite when the plan depends on it."""
        fw_names = {fw["name"] for fw in self.structure.get("frameworks", [])}
        use_ollama = self.constraints.get("use_ollama", False)
        has_ollama_replacement = any(
            r.get("replacement") == "ollama (local)"
            for r in self.adaptation.get("package_replacements", [])
        )
        if not (fw_names & {"Ollama"} or use_ollama or has_ollama_replacement):
            return

        if CLOUD_MODE:
            # Probing 127.0.0.1:11434 from the Space would describe the
            # container, never the user's laptop.
            self.predictions.append(FailurePrediction(
                level="info",
                category="ollama",
                message="This project uses Ollama for local inference",
                fix="Install it from ollama.com, then run `ollama serve` "
                    "and pull a model (e.g. `ollama pull llama3`)",
            ))
        elif self._ollama_running():
            self.predictions.append(FailurePrediction(
                level="info",
                category="ollama",
                message="Ollama server is running (OK)",
                fix="",
            ))
        else:
            self.predictions.append(FailurePrediction(
                level="warning",
                category="ollama",
                message="Ollama server not running",
                fix="Start Ollama: `ollama serve` in a separate terminal",
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
        python_deps = {d["name"] for d in self.deps.get("python", {}).get("all", [])}
        target = self._target_python()
        if not target:
            return
        target_str = ".".join(str(p) for p in target)

        PYTHON_INCOMPATIBILITIES = [
            ("torch", (3, 13), "PyTorch wheels for 3.13+ lag behind releases"),
            ("tensorflow", (3, 13), "TensorFlow has no 3.13 wheels on all platforms yet"),
        ]

        for pkg, min_broken, msg in PYTHON_INCOMPATIBILITIES:
            if pkg in python_deps and target >= min_broken:
                self.predictions.append(FailurePrediction(
                    level="warning",
                    category="version_compat",
                    message=f"Python {target_str} may not have prebuilt '{pkg}' wheels",
                    fix=f"{msg}. Consider Python 3.11 or 3.12 for this project",
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
