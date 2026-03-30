"""
planner/adaptive_planner.py — Repo2Product AI
Generates comprehensive, constraint-aware step-by-step setup and execution plans.
"""

from typing import Dict, List, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class AdaptivePlanner:
    """
    Takes analysis results and user constraints to produce a complete,
    actionable setup plan with steps, commands, environment config,
    and execution guide.
    """

    def __init__(
        self,
        fetch_result: Dict[str, Any],
        structure: Dict[str, Any],
        dependency_analysis: Dict[str, Any],
        resource_estimate: Dict[str, Any],
        adaptation: Dict[str, Any],
        user_constraints: Dict[str, Any],
    ):
        self.fetch = fetch_result
        self.structure = structure
        self.deps = dependency_analysis
        self.resources = resource_estimate
        self.adaptation = adaptation
        self.constraints = user_constraints

        self.os = user_constraints.get("os", "linux")
        self.ram_gb = user_constraints.get("ram_gb", 8)
        self.has_gpu = user_constraints.get("has_gpu", False)
        self.python_version = user_constraints.get("python_version", "3.10")
        self.project_type = structure.get("project_type", "python-script")
        self.primary_language = structure.get("primary_language", "Python")
        self.frameworks = [fw["name"] for fw in structure.get("frameworks", [])]
        self.entry_points = structure.get("entry_points", [])

    # ------------------------------------------------------------------ #
    #  Main plan generation                                                #
    # ------------------------------------------------------------------ #

    def generate_plan(self) -> Dict[str, Any]:
        """Generate the complete setup and run plan."""
        return {
            "overview": self._generate_overview(),
            "prerequisites": self._generate_prerequisites(),
            "setup_steps": self._generate_setup_steps(),
            "environment_setup": self._generate_env_setup(),
            "run_commands": self._generate_run_commands(),
            "troubleshooting": self._generate_troubleshooting(),
            "expected_output": self._generate_expected_output(),
            "optimization_tips": self._generate_optimization_tips(),
            "full_plan_text": "",  # filled at end
        }

    def generate_full_plan(self) -> str:
        """Render a complete human-readable setup guide."""
        plan = self.generate_plan()
        lines = []

        owner = self.fetch.get("owner", "")
        repo = self.fetch.get("repo", "")
        compat = self.adaptation.get("compatibility_score", 0)
        compat_label = self.adaptation.get("compatibility_label", "")

        lines += [
            f"# 🚀 Setup Guide: {owner}/{repo}",
            f"**Project Type:** {self.project_type}",
            f"**Primary Language:** {self.primary_language}",
            f"**Frameworks:** {', '.join(self.frameworks) or 'None detected'}",
            f"**Compatibility Score:** {compat}/100 — {compat_label}",
            "",
        ]

        # Overview
        lines += ["## 📋 Project Overview", plan["overview"], ""]

        # Prerequisites
        lines += ["## ✅ Prerequisites"]
        for prereq in plan["prerequisites"]:
            lines.append(f"- {prereq}")
        lines.append("")

        # Setup steps
        lines += ["## 🔧 Setup Steps"]
        for i, step in enumerate(plan["setup_steps"], 1):
            lines.append(f"\n### Step {i}: {step['title']}")
            lines.append(step["description"])
            if step.get("commands"):
                lines.append("```bash")
                lines.extend(step["commands"])
                lines.append("```")
            if step.get("notes"):
                for note in step["notes"]:
                    lines.append(f"> ⚠️ {note}")
        lines.append("")

        # Environment setup
        env_section = plan["environment_setup"]
        if env_section.get("variables"):
            lines += ["## 🔐 Environment Variables"]
            lines.append("Create a `.env` file with the following variables:")
            lines.append("```env")
            for var, default in env_section["variables"].items():
                lines.append(f"{var}={default}")
            lines.append("```")
            lines.append("")

        # Run commands
        lines += ["## ▶️ Running the Project"]
        for run in plan["run_commands"]:
            lines.append(f"\n**{run['label']}:**")
            lines.append("```bash")
            lines.append(run["command"])
            lines.append("```")
            if run.get("note"):
                lines.append(f"> {run['note']}")
        lines.append("")

        # Adaptations made
        if self.adaptation.get("package_replacements") or self.adaptation.get("removed_packages"):
            lines += ["## 🔄 CPU Adaptations Made"]
            for rep in self.adaptation.get("package_replacements", []):
                lines.append(f"- **{rep['original']}** → **{rep['replacement']}**: {rep.get('note', rep.get('reason', ''))}")
            for rem in self.adaptation.get("removed_packages", []):
                lines.append(f"- ~~{rem['package']}~~ — removed: {rem.get('impact', rem.get('reason', ''))}")
            lines.append("")

        # Troubleshooting
        lines += ["## 🛠️ Troubleshooting"]
        for tip in plan["troubleshooting"]:
            lines.append(f"\n**{tip['issue']}:**")
            lines.append(f"→ {tip['fix']}")
        lines.append("")

        # Optimization tips
        if plan["optimization_tips"]:
            lines += ["## ⚡ Performance Tips for Your System"]
            for tip in plan["optimization_tips"]:
                lines.append(f"- {tip}")

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Section generators                                                  #
    # ------------------------------------------------------------------ #

    def _generate_overview(self) -> str:
        meta = self.fetch.get("metadata", {})
        desc = meta.get("description", "No description available")
        lang = meta.get("language", self.primary_language)
        stars = meta.get("stars", 0)
        license_ = meta.get("license", "Unknown")
        issues = self.adaptation.get("summary", {})

        parts = [
            f"{desc}",
            f"\nOriginal language: **{lang}** | Stars: ⭐ {stars} | License: {license_}",
        ]

        if issues.get("packages_replaced", 0) > 0:
            parts.append(
                f"\n🔄 **{issues['packages_replaced']} packages** adapted for CPU-only operation."
            )
        if issues.get("packages_removed", 0) > 0:
            parts.append(
                f"\n❌ **{issues['packages_removed']} GPU-only packages** removed — "
                f"{issues.get('features_disabled', 0)} features disabled."
            )

        return " ".join(parts)

    def _generate_prerequisites(self) -> List[str]:
        prereqs = []
        py_ver = self.constraints.get("python_version", "3.10")
        prereqs.append(f"Python {py_ver}+ installed (`python --version`)")
        prereqs.append("pip installed and updated (`pip install --upgrade pip`)")
        prereqs.append("git installed (`git --version`)")
        prereqs.append(f"At least {self.resources['ram']['minimum_gb']}GB free RAM")
        prereqs.append(f"At least {self.resources['disk']['install_gb']}GB free disk space")

        if "Django" in self.frameworks:
            prereqs.append("Database (SQLite for development, PostgreSQL for production)")
        if "Celery" in self.frameworks:
            prereqs.append("Redis or RabbitMQ (for Celery task queue)")

        node_deps = self.deps.get("node", {})
        if node_deps:
            prereqs.append("Node.js 18+ and npm installed (`node --version`)")

        docker_deps = self.deps.get("docker", {})
        if docker_deps.get("base_image"):
            prereqs.append("Docker installed (optional — native run instructions provided below)")

        env_vars = self.structure.get("env_variables", {})
        api_keys = self.adaptation.get("package_replacements", [])
        api_key_originals = [r["original"] for r in api_keys if "api" in r.get("reason", "").lower()]
        if env_vars or api_key_originals:
            prereqs.append("Required API keys (see Environment Variables section)")

        if self.constraints.get("use_ollama") or "Ollama" in self.frameworks:
            prereqs.append("Ollama installed and running (`ollama serve`)")

        return prereqs

    def _generate_setup_steps(self) -> List[Dict[str, Any]]:
        steps = []
        owner = self.fetch.get("owner", "")
        repo = self.fetch.get("repo", "")
        local_path = self.fetch.get("local_path", f"./{owner}__{repo}")

        # Step 1: Clone
        steps.append({
            "title": "Clone the Repository",
            "description": "Clone the project to your local machine.",
            "commands": [
                f"git clone --depth=1 https://github.com/{owner}/{repo}.git",
                f"cd {repo}",
            ],
            "notes": [],
        })

        # Step 2: Python environment
        if self.primary_language == "Python":
            venv_cmd = "python3 -m venv venv" if self.os != "windows" else "python -m venv venv"
            activate = "source venv/bin/activate" if self.os != "windows" else r"venv\Scripts\activate"
            steps.append({
                "title": "Create Virtual Environment",
                "description": "Isolate project dependencies in a virtual environment.",
                "commands": [venv_cmd, activate],
                "notes": ["Always activate the venv before running commands in this project"],
            })

        # Step 3: Install dependencies
        install_notes = []
        install_cmds = []

        # Check for torch CPU install
        torch_rep = next((r for r in self.adaptation.get("package_replacements", []) if r["original"] == "torch"), None)
        if torch_rep and torch_rep.get("install_cmd"):
            install_cmds.append(f"pip install {torch_rep['install_cmd']}")
            install_notes.append("PyTorch installed as CPU-only version (saves ~1.5GB)")

        # Check for tensorflow-cpu
        tf_rep = next((r for r in self.adaptation.get("package_replacements", []) if r["original"] in ("tensorflow", "tensorflow-gpu")), None)
        if tf_rep:
            install_cmds.append("pip install tensorflow-cpu")
            install_notes.append("TensorFlow installed as CPU-only version")

        py_projects = self.deps.get("python", {}).get("projects", {})
        if py_projects:
            if "pip install --upgrade pip" not in install_cmds:
                install_cmds.insert(0, "pip install --upgrade pip")
            for d in py_projects.keys():
                d_clean = d if d not in (".", "") else ""
                prefix = f"cd {d_clean} && " if d_clean else ""
                install_cmds.append(f"{prefix}pip install -r requirements.txt")

        # Node deps
        node_projects = self.deps.get("node", {}).get("projects", {})
        if node_projects:
            for d in node_projects.keys():
                d_clean = d if d not in (".", "") else ""
                prefix = f"cd {d_clean} && " if d_clean else ""
                install_cmds.append(f"{prefix}npm install")

        install_desc = "Install all required packages (adapted for CPU-only operation)." if not self.has_gpu else "Install all required packages."
        steps.append({
            "title": "Install Dependencies",
            "description": install_desc,
            "commands": install_cmds,
            "notes": install_notes,
        })

        # Step 4: Environment configuration
        env_vars = self.structure.get("env_variables", {})
        if env_vars:
            steps.append({
                "title": "Configure Environment Variables",
                "description": "Set up your `.env` file with required configuration.",
                "commands": [
                    "cp .env.example .env  # Copy template" if ".env.example" in " ".join(self.fetch.get("file_list", [])) else "touch .env",
                    "# Edit .env with your values:",
                    "nano .env  # or use your preferred editor",
                ],
                "notes": [f"Required: {', '.join(list(env_vars.keys())[:5])}"],
            })

        # Step 5: Database setup (Django / SQLAlchemy)
        if "Django" in self.frameworks:
            steps.append({
                "title": "Database Setup",
                "description": "Initialize Django database.",
                "commands": [
                    "python manage.py migrate",
                    "python manage.py createsuperuser  # Optional",
                ],
                "notes": ["SQLite will be used by default — suitable for development"],
            })

        # Step 6: Ollama setup (if needed)
        if self.constraints.get("use_ollama") or any("openai" in r.get("original", "") for r in self.adaptation.get("package_replacements", [])):
            ollama_model = self.constraints.get("ollama_model", "llama3.2")
            steps.append({
                "title": "Set Up Local LLM with Ollama",
                "description": f"Pull and run the local LLM model via Ollama.",
                "commands": [
                    "ollama serve  # Start Ollama server (in separate terminal)",
                    f"ollama pull {ollama_model}",
                    f"ollama run {ollama_model}  # Test the model",
                ],
                "notes": [
                    f"Model download: {ollama_model} requires ~2-4GB disk space",
                    "Ollama uses CPU inference — responses may take 5-30 seconds",
                ],
            })

        # Step 7: Verification
        steps.append({
            "title": "Verify Installation",
            "description": "Quick sanity check that everything is installed correctly.",
            "commands": self._generate_verify_commands(),
            "notes": [],
        })

        return steps

    def _generate_verify_commands(self) -> List[str]:
        cmds = ["python -c \"import sys; print(f'Python {sys.version}')\""]
        for dep in self.deps.get("python", {}).get("all", [])[:5]:
            name = dep["name"].replace("-", "_").split(".")[0]
            cmds.append(f"python -c \"import {name}; print('{dep['name']} OK')\"")
        return cmds[:6]

    def _generate_env_setup(self) -> Dict[str, Any]:
        env_vars = self.structure.get("env_variables", {})
        if not env_vars:
            return {"variables": {}, "notes": []}

        # Build default values
        defaults = {}
        for var, val in env_vars.items():
            if val and val not in ("<required>", ""):
                defaults[var] = val
            elif "KEY" in var or "SECRET" in var or "TOKEN" in var:
                defaults[var] = f"your_{var.lower()}_here"
            elif "URL" in var or "HOST" in var:
                defaults[var] = "http://localhost:8000"
            elif "PORT" in var:
                defaults[var] = "8000"
            elif "DEBUG" in var:
                defaults[var] = "true"
            else:
                defaults[var] = f"<set_{var.lower()}>"

        # Check if ollama replacing openai
        for rep in self.adaptation.get("package_replacements", []):
            if rep.get("replacement") == "ollama (local)":
                defaults["OPENAI_API_BASE"] = "http://localhost:11434/v1"
                defaults["OPENAI_API_KEY"] = "ollama"

        return {
            "variables": defaults,
            "notes": [
                "Never commit .env to version control",
                "Add .env to your .gitignore",
            ],
        }

    def _generate_run_commands(self) -> List[Dict[str, str]]:
        runs = []
        project_type = self.project_type

        # Detect entry points
        entry_names = [ep["name"] for ep in self.entry_points]
        main_entry = next((ep["path"] for ep in self.entry_points), None)

        if "Django" in self.frameworks:
            runs.append({
                "label": "Development Server",
                "command": "python manage.py runserver 0.0.0.0:8000",
                "note": "Access at http://localhost:8000",
            })
        elif "FastAPI" in self.frameworks:
            entry = main_entry or "main.py"
            module = Path(entry).stem
            runs.append({
                "label": "FastAPI Server (Development)",
                "command": f"uvicorn {module}:app --host 0.0.0.0 --port 8000 --reload",
                "note": "API docs at http://localhost:8000/docs",
            })
            workers = max(1, min(4, self.ram_gb // 4))
            runs.append({
                "label": "FastAPI Server (Production)",
                "command": f"gunicorn {module}:app -w {workers} -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000",
                "note": f"Using {workers} workers for {self.ram_gb}GB RAM system",
            })
        elif "Flask" in self.frameworks:
            entry = main_entry or "app.py"
            module = Path(entry).stem
            runs.append({
                "label": "Flask Dev Server",
                "command": f"flask run --host=0.0.0.0 --port=5000",
                "note": "Set FLASK_APP=app.py if needed",
            })
        elif "Streamlit" in self.frameworks:
            entry = main_entry or "app.py"
            runs.append({
                "label": "Streamlit App",
                "command": f"streamlit run {entry} --server.port 8501",
                "note": "Opens at http://localhost:8501",
            })
        elif "Gradio" in self.frameworks:
            entry = main_entry or "app.py"
            runs.append({
                "label": "Gradio App",
                "command": f"python {entry}",
                "note": "Opens at http://localhost:7860",
            })

        node_projects = self.deps.get("node", {}).get("projects", {})
        if node_projects and ("node-app" in project_type or "fullstack" in project_type or "React" in self.frameworks or "Next.js" in self.frameworks or "Vue" in self.frameworks):
            for d, proj in node_projects.items():
                scripts = proj.get("scripts", {})
                d_clean = d if d not in (".", "") else ""
                prefix = f"cd {d_clean} && " if d_clean else ""
                if "start" in scripts:
                    runs.append({"label": f"Start App ({d_clean or 'root'})", "command": f"{prefix}npm start", "note": ""})
                elif "dev" in scripts:
                    runs.append({"label": f"Development Mode ({d_clean or 'root'})", "command": f"{prefix}npm run dev", "note": ""})
                elif not scripts:
                    runs.append({"label": f"Start App ({d_clean or 'root'})", "command": f"{prefix}node index.js", "note": ""})

        if not runs and main_entry:
            runs.append({
                "label": "Run Application",
                "command": f"python {main_entry}",
                "note": "Main application entry point",
            })

        # Celery worker
        if "Celery" in self.frameworks:
            runs.append({
                "label": "Celery Worker",
                "command": "celery -A app worker --loglevel=info --concurrency=2",
                "note": "Run in a separate terminal. Uses 2 workers for CPU efficiency",
            })

        return runs or [{"label": "Run", "command": "python main.py", "note": "Adjust to your main file"}]

    def _generate_troubleshooting(self) -> List[Dict[str, str]]:
        tips = [
            {
                "issue": "ModuleNotFoundError after installing requirements",
                "fix": "Ensure virtual environment is activated: `source venv/bin/activate` (Linux/Mac) or `venv\\Scripts\\activate` (Windows)",
            },
            {
                "issue": "pip install fails with compilation errors",
                "fix": "Install build tools: `sudo apt install build-essential python3-dev` (Linux) or install Visual C++ Build Tools (Windows)",
            },
            {
                "issue": "Out of memory error (MemoryError / killed)",
                "fix": f"Your system has {self.ram_gb}GB RAM. Reduce batch size, use streaming, or close other applications",
            },
            {
                "issue": "Port already in use",
                "fix": "Kill the process: `lsof -i :8000 | awk 'NR>1 {print $2}' | xargs kill` or change the port",
            },
            {
                "issue": "CUDA / GPU error on CPU system",
                "fix": "Set CUDA_VISIBLE_DEVICES='' and ensure torch is installed as CPU-only version",
            },
            {
                "issue": "Slow inference (ML models)",
                "fix": f"Expected on CPU. Optimize: reduce input size, use smaller models, enable torch.compile() for PyTorch 2.0+",
            },
        ]

        # Project-specific tips
        if "Django" in self.frameworks:
            tips.append({
                "issue": "Django migration errors",
                "fix": "Run `python manage.py makemigrations && python manage.py migrate`",
            })
        if "FastAPI" in self.frameworks:
            tips.append({
                "issue": "uvicorn: command not found",
                "fix": "Install: `pip install uvicorn[standard]`",
            })
        if "Ollama" in self.frameworks or self.constraints.get("use_ollama"):
            tips.append({
                "issue": "Ollama connection refused",
                "fix": "Start Ollama server: `ollama serve` in a separate terminal",
            })

        flagged = self.deps.get("summary", {}).get("flagged_issues", [])
        for issue in flagged:
            if issue.get("severity") == "error":
                tips.append({
                    "issue": f"Package '{issue['package']}' fails to import",
                    "fix": issue.get("fix", "See adaptations section"),
                })

        return tips

    def _generate_expected_output(self) -> Dict[str, Any]:
        project_type = self.project_type
        output_map = {
            "web-api-python": {
                "type": "HTTP API Server",
                "expected": "Server starts on http://localhost:8000",
                "verify": "curl http://localhost:8000/health → {\"status\": \"ok\"}",
            },
            "web-fullstack-python": {
                "type": "Web Application",
                "expected": "Web app accessible at http://localhost:8000",
                "verify": "Open browser → http://localhost:8000",
            },
            "data-app-streamlit": {
                "type": "Streamlit Dashboard",
                "expected": "Browser opens with interactive dashboard",
                "verify": "Open browser → http://localhost:8501",
            },
            "ml-demo-gradio": {
                "type": "Gradio ML Interface",
                "expected": "Browser opens with ML demo interface",
                "verify": "Open browser → http://localhost:7860",
            },
            "ml-training": {
                "type": "ML Training Script",
                "expected": "Training progress printed to console with loss/accuracy metrics",
                "verify": "Check for decreasing loss values in output",
            },
            "python-script": {
                "type": "Python Script",
                "expected": "Script executes and prints output or generates files",
                "verify": "Check console output and output/ directory",
            },
        }
        return output_map.get(project_type, {
            "type": "Application",
            "expected": "Application starts successfully",
            "verify": "Check console output for startup messages",
        })

    def _generate_optimization_tips(self) -> List[str]:
        tips = []
        dep_names = {d["name"] for d in self.deps.get("python", {}).get("all", [])}

        gpu_status = "GPU available" if self.has_gpu else "CPU-only"
        os_label = {"linux": "Linux", "macos": "macOS", "windows": "Windows"}.get(self.os, self.os)
        tips.append(f"Your system: {self.ram_gb}GB RAM, {gpu_status}, {os_label}")

        if "torch" in dep_names:
            tips.append("Enable PyTorch CPU optimizations: `torch.set_num_threads(4)` at startup")
            tips.append("Use torch.compile() for 10-30% speedup on CPU (PyTorch 2.0+)")

        if "transformers" in dep_names:
            tips.append("Use smaller quantized models (GGUF format via llama-cpp-python) for 4-8x speedup")
            tips.append("Enable model caching with TRANSFORMERS_CACHE env variable")

        if "pandas" in dep_names:
            tips.append("Use chunked reading for large files: `pd.read_csv(file, chunksize=1000)`")

        omp_threads = max(2, min(8, self.ram_gb // 2))
        tips.append(f"Set `OMP_NUM_THREADS={omp_threads}` for optimal OpenMP performance on your CPU")
        workers = max(1, min(4, self.ram_gb // 4))
        tips.append(f"Use `gunicorn --workers={workers}` for web servers (recommended for {self.ram_gb}GB RAM)")
        tips.append("Monitor memory: `watch -n1 free -h` to detect memory pressure")

        return tips
