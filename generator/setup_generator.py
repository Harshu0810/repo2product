"""
generator/setup_generator.py — Repo2Product AI
Generates ready-to-run setup scripts (Linux/Mac and Windows),
.env templates, and a minimal working project structure.
"""

import zipfile
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SetupGenerator:
    """
    Generates all runnable artifacts:
    - setup.sh  (Linux/Mac)
    - setup.bat (Windows)
    - .env.template
    - run.sh / run.bat
    - README_ADAPTED.md
    - requirements_adapted.txt
    """

    def __init__(
        self,
        fetch_result: Dict[str, Any],
        structure: Dict[str, Any],
        dependency_analysis: Dict[str, Any],
        adaptation: Dict[str, Any],
        plan: Dict[str, Any],
        user_constraints: Dict[str, Any],
        output_dir: str = "./output",
    ):
        self.fetch = fetch_result
        self.structure = structure
        self.deps = dependency_analysis
        self.adaptation = adaptation
        self.plan = plan
        self.constraints = user_constraints
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.owner = fetch_result.get("owner", "unknown")
        self.repo = fetch_result.get("repo", "project")
        self.os = user_constraints.get("os", "linux")
        self.ram_gb = user_constraints.get("ram_gb", 8)
        self.has_gpu = user_constraints.get("has_gpu", False)
        self.python_ver = user_constraints.get("python_version", "3.10")
        self.frameworks = [fw["name"] for fw in structure.get("frameworks", [])]
        self.project_type = structure.get("project_type", "python-script")
        self.primary_lang = structure.get("primary_language", "Python")
        self.entry_points = structure.get("entry_points", [])
        self.main_entry = self.entry_points[0]["path"] if self.entry_points else "main.py"

    # ------------------------------------------------------------------ #
    #  Main generation entry point                                         #
    # ------------------------------------------------------------------ #

    def generate_all(self) -> Dict[str, str]:
        """Generate all artifacts and return {filename: content} dict."""
        artifacts = {}

        artifacts["setup.sh"] = self._generate_setup_sh()
        artifacts["setup.bat"] = self._generate_setup_bat()
        artifacts["run.sh"] = self._generate_run_sh()
        artifacts["run.bat"] = self._generate_run_bat()
        artifacts[".env.template"] = self._generate_env_template()
        artifacts["requirements_adapted.txt"] = self.adaptation.get("adapted_requirements", "# No Python dependencies")
        artifacts["README_ADAPTED.md"] = self._generate_readme()
        artifacts["verify.py"] = self._generate_verify_script()

        # ── Docker Compose ──────────────────────────────────────────
        docker_artifacts = self._generate_docker_compose()
        artifacts.update(docker_artifacts)

        # Save all to output dir
        project_output = self.output_dir / f"{self.owner}__{self.repo}"
        project_output.mkdir(parents=True, exist_ok=True)

        for filename, content in artifacts.items():
            filepath = project_output / filename
            with open(filepath, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)

        # Make shell scripts executable (on Unix)
        try:
            import stat
            for sh_file in ["setup.sh", "run.sh"]:
                fp = project_output / sh_file
                fp.chmod(fp.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        except Exception:
            pass

        artifacts["_output_dir"] = str(project_output)
        return artifacts

    def generate_zip(self) -> str:
        """Package all artifacts into a downloadable zip."""
        artifacts = self.generate_all()
        output_dir = Path(artifacts.pop("_output_dir", str(self.output_dir)))

        zip_path = self.output_dir / f"{self.owner}__{self.repo}_setup.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, content in artifacts.items():
                zf.writestr(filename, content)

        return str(zip_path)

    # ------------------------------------------------------------------ #
    #  setup.sh                                                            #
    # ------------------------------------------------------------------ #

    def _generate_setup_sh(self) -> str:
        repo_url = f"https://github.com/{self.owner}/{self.repo}.git"
        env_vars = self.structure.get("env_variables", {})

        # Build install commands
        torch_rep = next((r for r in self.adaptation.get("package_replacements", []) if r["original"] == "torch"), None)
        install_cmds = ["pip install --upgrade pip wheel setuptools"]

        py_projects = self.deps.get("python", {}).get("projects", {})
        if py_projects:
            for d in py_projects.keys():
                d_clean = d if d not in (".", "") else ""
                prefix = f"cd {d_clean} && " if d_clean else ""
                req_file = "requirements_adapted.txt" if not d_clean else "requirements.txt"
                
                if torch_rep and torch_rep.get("install_cmd") and not d_clean:
                    install_cmds.append(f"{prefix}pip install {torch_rep['install_cmd']}")
                    install_cmds.append(f"{prefix}# Note: remaining packages installed from adapted requirements")
                    install_cmds.append(f"{prefix}pip install -r {req_file} --no-deps 2>/dev/null || {prefix}pip install -r {req_file}")
                else:
                    install_cmds.append(f"{prefix}pip install -r {req_file}")
                if d_clean:
                    install_cmds.append("cd ..")
        else:
            if torch_rep and torch_rep.get("install_cmd"):
                install_cmds.append(f"pip install {torch_rep['install_cmd']}")
                install_cmds.append(f"pip install -r requirements_adapted.txt --no-deps 2>/dev/null || pip install -r requirements_adapted.txt")
            else:
                install_cmds.append("pip install -r requirements_adapted.txt")

        node_projects = self.deps.get("node", {}).get("projects", {})
        if node_projects:
            for d in node_projects.keys():
                d_clean = d if d not in (".", "") else ""
                prefix = f"cd {d_clean} && " if d_clean else ""
                install_cmds.append(f"{prefix}npm install")
                if d_clean:
                    install_cmds.append("cd ..")

        return f"""#!/usr/bin/env bash
# ============================================================
#  setup.sh — Generated by Repo2Product AI
#  Project: {self.owner}/{self.repo}
#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
#  Target: Linux/macOS, {"GPU-enabled" if self.has_gpu else "CPU-only"}, {self.ram_gb}GB RAM
# ============================================================

set -e  # Exit on any error
REPO_URL="{repo_url}"
REPO_NAME="{self.repo}"
PYTHON="{f"python{self.python_ver}" if self.python_ver else "python3"}"

# ── Colors ──────────────────────────────────────────────────
RED='\\033[0;31m'; GREEN='\\033[0;32m'; YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'; NC='\\033[0m'

info()    {{ echo -e "${{BLUE}}[INFO]${{NC}} $1"; }}
success() {{ echo -e "${{GREEN}}[OK]${{NC}} $1"; }}
warn()    {{ echo -e "${{YELLOW}}[WARN]${{NC}} $1"; }}
error()   {{ echo -e "${{RED}}[ERROR]${{NC}} $1"; exit 1; }}

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Repo2Product AI — Setup Script             ║"
echo "║   {self.owner}/{self.repo:<35}║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Prerequisites check ──────────────────────────────────────
info "Checking prerequisites..."

command -v git &>/dev/null || error "git is not installed. Install: sudo apt install git"
command -v $PYTHON &>/dev/null || command -v python3 &>/dev/null || \\
    error "Python not found. Install Python {self.python_ver}+"

PYTHON_CMD=$(command -v $PYTHON 2>/dev/null || command -v python3)
PY_VER=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
info "Using Python $PY_VER at $PYTHON_CMD"

# Check disk space (need at least {int(self.deps.get('summary', {}).get('resource_estimate', {}).get('estimated_disk_mb', 2000) / 1024) + 2}GB)
AVAILABLE_KB=$(df . | tail -1 | awk '{{print $4}}')
NEEDED_KB={int(self.deps.get('summary', {}).get('resource_estimate', {}).get('estimated_disk_mb', 2000) * 1.5) * 1024}
if [ "$AVAILABLE_KB" -lt "$NEEDED_KB" ]; then
    warn "Low disk space. Available: $((AVAILABLE_KB/1024/1024))GB, Recommended: $((NEEDED_KB/1024/1024))GB"
fi
success "Prerequisites OK"

# ── Clone repository ─────────────────────────────────────────
if [ -d "$REPO_NAME" ]; then
    info "Directory $REPO_NAME exists — skipping clone"
    info "To re-clone: rm -rf $REPO_NAME && bash setup.sh"
else
    info "Cloning $REPO_URL ..."
    git clone --depth=1 "$REPO_URL" "$REPO_NAME" || error "Failed to clone repository"
    success "Repository cloned"
fi

cd "$REPO_NAME"

# ── Virtual environment ───────────────────────────────────────
if [ ! -d "venv" ]; then
    info "Creating virtual environment..."
    $PYTHON_CMD -m venv venv || error "Failed to create venv. Try: pip install virtualenv"
    success "Virtual environment created"
else
    info "Virtual environment already exists"
fi

source venv/bin/activate
success "Virtual environment activated"

# ── Install dependencies ──────────────────────────────────────
info "Installing dependencies (CPU-optimized)..."
{chr(10).join(install_cmds)}

success "Dependencies installed"

# ── Environment configuration ─────────────────────────────────
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        warn ".env created from .env.example — please edit with your values"
    elif [ -f ".env.template" ]; then
        cp .env.template .env
        warn ".env created from template — please edit with your values"
    else
        warn "No .env template found — create .env manually if needed"
    fi
else
    info ".env already exists"
fi

{"# ── Django setup ─────────────────────────────────────────────" if "Django" in self.frameworks else ""}
{"python manage.py migrate --run-syncdb 2>/dev/null && success 'Database initialized'" if "Django" in self.frameworks else ""}

# ── Verify installation ───────────────────────────────────────
info "Running verification..."
python verify.py 2>/dev/null && success "Verification passed" || \\
    warn "Verification had warnings — check above output"

# ── Done ──────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   ✅  Setup Complete!                        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "  Next steps:"
echo "  1. cd $REPO_NAME"
echo "  2. source venv/bin/activate"
{"  3. Edit .env with your configuration" if env_vars else ""}
echo "  4. bash ../run.sh"
echo ""
echo "  For issues, see README_ADAPTED.md"
echo ""
"""

    # ------------------------------------------------------------------ #
    #  setup.bat (Windows)                                                 #
    # ------------------------------------------------------------------ #

    def _generate_setup_bat(self) -> str:
        repo_url = f"https://github.com/{self.owner}/{self.repo}.git"

        py_projects = self.deps.get("python", {}).get("projects", {})
        bat_installs = ["pip install --upgrade pip wheel setuptools"]
        if py_projects:
            for d in py_projects.keys():
                d_clean = d if d not in (".", "") else ""
                req_file = "requirements_adapted.txt" if not d_clean else "requirements.txt"
                if d_clean:
                    bat_installs.append(f"cd {d_clean}")
                bat_installs.append(f"pip install -r {req_file}")
                if d_clean:
                    bat_installs.append(f"cd ..")
        else:
            bat_installs.append("pip install -r requirements_adapted.txt")
        bat_installs.append("IF ERRORLEVEL 1 ( echo [WARN] Some packages failed )")

        node_projects = self.deps.get("node", {}).get("projects", {})
        if node_projects:
            for d in node_projects.keys():
                d_clean = d if d not in (".", "") else ""
                if d_clean:
                    bat_installs.append(f"cd {d_clean}")
                bat_installs.append("npm install")
                if d_clean:
                    bat_installs.append(f"cd ..")

        bat_install_block = "\\n".join(bat_installs)

        return f"""@echo off
REM ============================================================
REM  setup.bat — Generated by Repo2Product AI
REM  Project: {self.owner}/{self.repo}
REM  Target: Windows, {"GPU-enabled" if self.has_gpu else "CPU-only"}, {self.ram_gb}GB RAM
REM ============================================================

SETLOCAL EnableDelayedExpansion
SET REPO_URL={repo_url}
SET REPO_NAME={self.repo}
SET PYTHON=python

echo.
echo  ============================================
echo   Repo2Product AI -- Setup Script (Windows)
echo   {self.owner}/{self.repo}
echo  ============================================
echo.

REM Check prerequisites
where git >nul 2>nul
IF ERRORLEVEL 1 (
    echo [ERROR] git not found. Install from: https://git-scm.com/download/win
    pause & exit /b 1
)

where %PYTHON% >nul 2>nul
IF ERRORLEVEL 1 (
    echo [ERROR] Python not found. Install from: https://python.org
    pause & exit /b 1
)

echo [INFO] Checking Python version...
%PYTHON% --version

REM Clone repository
IF EXIST %REPO_NAME% (
    echo [INFO] Directory %REPO_NAME% exists -- skipping clone
) ELSE (
    echo [INFO] Cloning repository...
    git clone --depth=1 %REPO_URL% %REPO_NAME%
    IF ERRORLEVEL 1 (echo [ERROR] Clone failed & pause & exit /b 1)
)
cd %REPO_NAME%

REM Virtual environment
IF NOT EXIST venv (
    echo [INFO] Creating virtual environment...
    %PYTHON% -m venv venv
)
CALL venv\\Scripts\\activate.bat
echo [OK] Virtual environment activated

REM Install dependencies
echo [INFO] Installing dependencies...
{bat_install_block}

REM Environment
IF NOT EXIST .env (
    IF EXIST .env.example (
        COPY .env.example .env
        echo [WARN] .env created -- please edit with your values
    )
)

echo.
echo  ============================================
echo   Setup Complete!
echo  ============================================
echo.
echo   Next steps:
echo   1. cd %REPO_NAME%
echo   2. venv\\Scripts\\activate
echo   3. Edit .env with your configuration
echo   4. run.bat
echo.
pause
"""

    # ------------------------------------------------------------------ #
    #  run.sh                                                              #
    # ------------------------------------------------------------------ #

    def _generate_run_sh(self) -> str:
        runs = self.plan.get("run_commands", [])

        extra_services = []
        if "Celery" in self.frameworks:
            extra_services.append("# Start Celery worker in background")
            extra_services.append("celery -A app worker --loglevel=info --concurrency=2 &")

        pre_checks = []
        if "Django" in self.frameworks:
            pre_checks.append("python manage.py migrate --check 2>/dev/null || python manage.py migrate")

        env_export = []
        omp_threads = max(2, min(8, self.ram_gb // 2))
        if not self.constraints.get("has_gpu", False):
            env_export += [
                "export CUDA_VISIBLE_DEVICES=''  # Disable CUDA on CPU-only system",
                f"export OMP_NUM_THREADS={omp_threads}         # Optimize OpenMP thread count",
                "export TOKENIZERS_PARALLELISM=false  # Avoid HuggingFace warnings",
            ]
        else:
            env_export += [
                f"export OMP_NUM_THREADS={omp_threads}         # Optimize OpenMP thread count",
                "export TOKENIZERS_PARALLELISM=false  # Avoid HuggingFace warnings",
            ]
            
        run_cmds_sh = []
        for i, run in enumerate(runs):
            run_cmd_line = run["command"]
            if i < len(runs) - 1:
                run_cmds_sh.append(f"echo \"[run.sh] Starting {run['label']}...\"")
                run_cmds_sh.append(f"{run_cmd_line} &")
                run_cmds_sh.append(f"PID_{i}=$!")
                run_cmds_sh.append("")
            else:
                run_cmds_sh.append(f"echo \"[run.sh] Starting {run['label']}...\"")
                run_cmds_sh.append(f"{run_cmd_line}")
                
        runs_block = "\n".join(run_cmds_sh)

        return f"""#!/usr/bin/env bash
# ============================================================
#  run.sh — Generated by Repo2Product AI
#  Project: {self.owner}/{self.repo}
#  Run type: {self.project_type}
# ============================================================

set -e
cd "$(dirname "$0")"

# ── Activate virtual environment ──────────────────────────────
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "../venv/bin/activate" ]; then
    source ../venv/bin/activate
fi

# ── Environment ───────────────────────────────────────────────
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs -d '\\n' 2>/dev/null || true)
fi

# CPU Optimizations
{chr(10).join(env_export)}

# ── Pre-run checks ────────────────────────────────────────────
{chr(10).join(pre_checks) if pre_checks else "# No pre-run checks needed"}

# ── Extra services ─────────────────────────────────────────────
{chr(10).join(extra_services) if extra_services else "# No extra services"}

# ── Run the application ───────────────────────────────────────
{runs_block}
"""

    def _generate_run_bat(self) -> str:
        runs = self.plan.get("run_commands", [])
        run_cmds_bat = []
        for i, run in enumerate(runs):
            if i < len(runs) - 1:
                run_cmds_bat.append(f"echo [run.bat] Starting {run['label']} in new window...")
                run_cmds_bat.append(f"start \"{run['label']}\" cmd /k \"{run['command']}\"")
                run_cmds_bat.append("")
            else:
                run_cmds_bat.append(f"echo [run.bat] Starting {run['label']}...")
                run_cmds_bat.append(f"{run['command']}")
                
        runs_block = "\n".join(run_cmds_bat)
        
        return f"""@echo off
REM run.bat — Generated by Repo2Product AI
SETLOCAL

cd /d "%~dp0"

IF EXIST venv\\Scripts\\activate.bat (
    CALL venv\\Scripts\\activate.bat
)

IF EXIST .env (
    FOR /F "tokens=1,2 delims== eol=#" %%A IN (.env) DO (
        SET %%A=%%B
    )
)

{"" if self.has_gpu else "SET CUDA_VISIBLE_DEVICES="}
SET OMP_NUM_THREADS={max(2, min(8, self.ram_gb // 2))}
SET TOKENIZERS_PARALLELISM=false

{runs_block}
"""

    # ------------------------------------------------------------------ #
    #  .env template                                                       #
    # ------------------------------------------------------------------ #

    def _generate_env_template(self) -> str:
        env_vars = self.structure.get("env_variables", {})
        env_setup = self.plan.get("environment_setup", {})
        merged = {**env_vars, **env_setup.get("variables", {})}

        lines = [
            f"# .env.template — Generated by Repo2Product AI",
            f"# Project: {self.owner}/{self.repo}",
            f"# Generated: {datetime.now().strftime('%Y-%m-%d')}",
            "# ─────────────────────────────────────────────────────────",
            "# Copy this file to .env and fill in your values",
            "# NEVER commit .env to version control!",
            "",
        ]

        # Group by category
        app_vars = {}
        db_vars = {}
        api_vars = {}
        other_vars = {}

        for var, val in merged.items():
            if any(x in var for x in ("DB_", "DATABASE_", "POSTGRES_", "MONGO_", "REDIS_")):
                db_vars[var] = val
            elif any(x in var for x in ("API_KEY", "TOKEN", "SECRET", "PASSWORD")):
                api_vars[var] = val
            elif any(x in var for x in ("HOST", "PORT", "URL", "DEBUG", "ENV", "APP_")):
                app_vars[var] = val
            else:
                other_vars[var] = val

        sections = [
            ("# ── Application ──────────────────────────────────", app_vars),
            ("# ── Database ─────────────────────────────────────", db_vars),
            ("# ── API Keys & Secrets ───────────────────────────", api_vars),
            ("# ── Other ────────────────────────────────────────", other_vars),
        ]

        for header, section in sections:
            if section:
                lines.append(header)
                for var, val in section.items():
                    if not val or val == "<required>":
                        lines.append(f"{var}=  # Required — fill this in")
                    elif val.startswith("your_") or val.startswith("<"):
                        lines.append(f"{var}={val}")
                    else:
                        lines.append(f"{var}={val}")
                lines.append("")

        # Add performance vars
        omp_threads = max(2, min(8, self.ram_gb // 2))
        perf_lines = [
            "# ── Performance (auto-set in run.sh) ──────────────",
        ]
        if not self.has_gpu:
            perf_lines.append("CUDA_VISIBLE_DEVICES=  # Empty = disable GPU")
        perf_lines += [
            f"OMP_NUM_THREADS={omp_threads}",
            "TOKENIZERS_PARALLELISM=false",
        ]
        lines += perf_lines

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Verification script                                                 #
    # ------------------------------------------------------------------ #

    def _generate_verify_script(self) -> str:
        python_deps = self.deps.get("python", {}).get("all", [])
        imports_to_check = []
        for dep in python_deps[:15]:
            name = dep["name"]
            import_name = name.replace("-", "_").split(".")[0]
            # Skip GPU-only
            if not dep.get("gpu_required"):
                imports_to_check.append((name, import_name))

        checks = []
        for pkg_name, import_name in imports_to_check[:10]:
            checks.append(f'    check_import("{import_name}", "{pkg_name}")')

        # Entry point checks
        entry_checks = []
        for ep in self.entry_points[:3]:
            entry_checks.append(f'    check_file("{ep["path"]}")')

        return f'''#!/usr/bin/env python3
"""verify.py — Repo2Product AI Installation Verifier"""
import sys
import os

PASS = "✓"; FAIL = "✗"; WARN = "⚠"
errors = 0; warnings = 0

def check_import(module, package_name=""):
    global errors
    try:
        __import__(module)
        print(f"  {{PASS}} {{package_name or module}}")
    except ImportError as e:
        print(f"  {{FAIL}} {{package_name or module}}: {{e}}")
        errors += 1

def check_file(path):
    global warnings
    if os.path.exists(path):
        print(f"  {{PASS}} {{path}}")
    else:
        print(f"  {{WARN}} {{path}} not found")
        warnings += 1

def check_python_version():
    global errors
    required = (3, 8)
    if sys.version_info < required:
        print(f"  {{FAIL}} Python {{sys.version_info.major}}.{{sys.version_info.minor}} < {{required[0]}}.{{required[1]}}")
        errors += 1
    else:
        print(f"  {{PASS}} Python {{sys.version_info.major}}.{{sys.version_info.minor}}.{{sys.version_info.micro}}")

def check_ollama():
    global warnings
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        print(f"  {{PASS}} Ollama server running")
    except Exception:
        print(f"  {{WARN}} Ollama not running (only needed if project uses local LLM)")
        warnings += 1

print()
print("=" * 50)
print("  Repo2Product AI — Installation Verifier")
print("  {self.owner}/{self.repo}")
print("=" * 50)

print("\\n[ Python Version ]")
check_python_version()

print("\\n[ Required Packages ]")
{chr(10).join(checks) if checks else '    print("  (no packages to verify)")'}

print("\\n[ Project Files ]")
{chr(10).join(entry_checks) if entry_checks else '    print("  (no entry points to verify)")'}

print("\\n[ Services ]")
check_ollama()

print()
print("=" * 50)
if errors == 0 and warnings == 0:
    print(f"  {{PASS}} All checks passed!")
elif errors == 0:
    print(f"  {{WARN}} {{warnings}} warning(s) — project may still run")
else:
    print(f"  {{FAIL}} {{errors}} error(s) — fix before running")
print("=" * 50)
print()

sys.exit(errors)
'''

    # ------------------------------------------------------------------ #
    #  Docker Compose                                                      #
    # ------------------------------------------------------------------ #

    def _generate_docker_compose(self) -> Dict[str, str]:
        """Generate CPU-only docker-compose.yml and associated Dockerfiles."""
        files = {}
        services = []
        
        py_projects = self.deps.get("python", {}).get("projects", {})
        node_projects = self.deps.get("node", {}).get("projects", {})
        
        if not py_projects and not node_projects:
            return {}

        service_idx = 1
        
        # Python Services
        for d, reqs in py_projects.items():
            d_clean = d if d not in (".", "") else "."
            svc_name = f"backend-{service_idx}" if d_clean != "." else "backend"
            port = "8000" if "FastAPI" in self.frameworks or "Django" in self.frameworks else ("5000" if "Flask" in self.frameworks else "8501")
            
            # Find run command for this
            cmd = '["python", "main.py"]'
            runs = self.plan.get("run_commands", [])
            for r in runs:
                if "runserver" in r["command"] or "uvicorn" in r["command"] or "flask run" in r["command"] or "streamlit" in r["command"]:
                    cmd_parts = r["command"].replace(f"cd {d_clean} && ", "").split()
                    cmd = json.dumps(cmd_parts)
                    break

            df = f"""FROM python:{self.python_ver}-slim
WORKDIR /app
COPY requirements_adapted.txt .
RUN pip install --no-cache-dir -r requirements_adapted.txt
COPY . .
ENV OMP_NUM_THREADS=4
ENV CUDA_VISIBLE_DEVICES=""
CMD {cmd}
"""
            df_path = "Dockerfile" if d_clean == "." else f"{d_clean}/Dockerfile"
            files[df_path] = df
            
            services.append(f"""  {svc_name}:
    build:
      context: {d_clean}
      dockerfile: Dockerfile
    ports:
      - "{port}:{port}"
    environment:
      - OMP_NUM_THREADS=4
      - CUDA_VISIBLE_DEVICES=""
    restart: unless-stopped
""")
            service_idx += 1
            
        # Node Services
        for d, pkg in node_projects.items():
            d_clean = d if d not in (".", "") else "."
            svc_name = f"frontend-{service_idx}" if d_clean != "." else "frontend"
            
            # Extract port (Vite uses 5173, React uses 3000)
            port = "5173" if "vite" in json.dumps(pkg) else "3000"
            
            df = f"""FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
CMD ["npm", "run", "dev"]
"""
            df_path = "Dockerfile" if d_clean == "." else f"{d_clean}/Dockerfile"
            if df_path in files: # Conflict fallback
                df_path = "Dockerfile.node" if d_clean == "." else f"{d_clean}/Dockerfile.node"
                
            files[df_path] = df
            
            services.append(f"""  {svc_name}:
    build:
      context: {d_clean}
      dockerfile: {Path(df_path).name}
    ports:
      - "{port}:{port}"
    environment:
      - NODE_ENV=development
    restart: unless-stopped
""")
            service_idx += 1

        if not services:
            return {}

        compose_yml = f"""version: '3.8'
services:
{chr(10).join(services)}
"""
        files["docker-compose.yml"] = compose_yml
        return files

    # ------------------------------------------------------------------ #
    #  README_ADAPTED.md                                                   #
    # ------------------------------------------------------------------ #

    def _generate_readme(self) -> str:
        compat = self.adaptation.get("compatibility_score", 0)
        compat_label = self.adaptation.get("compatibility_label", "")
        run_cmd = self._get_primary_run_command()
        meta = self.fetch.get("metadata", {})

        return f"""# {self.owner}/{self.repo} — Adapted Setup Guide

> **Generated by [Repo2Product AI](https://github.com)** on {datetime.now().strftime('%Y-%m-%d')}

## 🎯 Project Summary

**Original Description:** {meta.get('description', 'See original README')}

| Property | Value |
|----------|-------|
| Language | {self.primary_lang} |
| Type | {self.project_type} |
| Frameworks | {', '.join(self.frameworks) or 'None detected'} |
| Compatibility Score | {compat}/100 — {compat_label} |
| Target System | {"GPU-enabled" if self.has_gpu else "CPU-only"}, {self.ram_gb}GB RAM, {self.os} |

## 📋 Files in This Package

| File | Purpose |
|------|---------|
| `setup.sh` | Linux/Mac automated setup script |
| `setup.bat` | Windows automated setup script |
| `run.sh` | Linux/Mac run script |
| `run.bat` | Windows run script |
| `.env.template` | Environment variable template |
| `requirements_adapted.txt` | CPU-adapted Python dependencies |
| `docker-compose.yml` | Containerized environment config |
| `verify.py` | Post-install verification |
| `README_ADAPTED.md` | This file |

## 🚀 Quick Start

### Linux / macOS
```bash
bash setup.sh      # One-time setup
bash run.sh        # Run the project
```

### Windows
```batch
setup.bat          REM One-time setup
run.bat            REM Run the project
```

### Manual
```bash
git clone --depth=1 https://github.com/{self.owner}/{self.repo}.git
cd {self.repo}
python3 -m venv venv && source venv/bin/activate
pip install -r requirements_adapted.txt
cp .env.template .env  # Edit with your values
bash run.sh
```

## 🔄 CPU Adaptations

{self._render_adaptations_table()}

## 🔐 Required Environment Variables

```env
{self._render_env_vars_section()}
```

## ⚠️ Known Issues & Fixes

{self._render_known_issues()}

## ⚡ Performance Notes

- **CPU**: {"GPU available — hardware acceleration enabled" if self.has_gpu else "CPU-only — expect slower ML inference vs GPU"}
- **RAM**: {self.ram_gb}GB — monitor with `watch -n2 free -h`
- **Thread count**: Set `OMP_NUM_THREADS={max(2, min(8, self.ram_gb // 2))}` for optimal performance on {self.ram_gb}GB RAM system
- **Ollama**: For LLM tasks, `ollama serve` must be running

## 📖 Original Repository

- URL: https://github.com/{self.owner}/{self.repo}
- Stars: ⭐ {meta.get('stars', 0)}
- License: {meta.get('license', 'Unknown')}
"""

    def _render_adaptations_table(self) -> str:
        replacements = self.adaptation.get("package_replacements", [])
        removed = self.adaptation.get("removed_packages", [])

        if not replacements and not removed:
            return "✅ No adaptations needed — project runs natively on CPU."

        lines = ["| Change | Original | Replacement | Reason |",
                 "|--------|----------|-------------|--------|"]
        for rep in replacements:
            lines.append(f"| Replace | `{rep['original']}` | `{rep.get('replacement', 'N/A')}` | {rep.get('reason', '')} |")
        for rem in removed:
            lines.append(f"| Remove | `{rem['package']}` | — | {rem.get('reason', 'GPU-only')} |")
        return "\n".join(lines)

    def _render_env_vars_section(self) -> str:
        env_setup = self.plan.get("environment_setup", {})
        variables = env_setup.get("variables", {})
        if not variables:
            return "# No environment variables required"
        return "\n".join(f"{k}={v}" for k, v in list(variables.items())[:10])

    def _render_known_issues(self) -> str:
        tips = self.plan.get("troubleshooting", [])
        if not tips:
            return "No known issues identified."
        lines = []
        for tip in tips[:6]:
            lines.append(f"**{tip['issue']}**")
            lines.append(f"→ {tip['fix']}\n")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Utility                                                             #
    # ------------------------------------------------------------------ #

    def _get_primary_run_command(self) -> str:
        runs = self.plan.get("run_commands", [])
        if runs:
            return runs[0]["command"]

        # Fallback detection
        if "Django" in self.frameworks:
            return "python manage.py runserver 0.0.0.0:8000"
        if "FastAPI" in self.frameworks:
            entry = Path(self.main_entry).stem
            return f"uvicorn {entry}:app --host 0.0.0.0 --port 8000 --reload"
        if "Flask" in self.frameworks:
            return "flask run --host=0.0.0.0 --port=5000"
        if "Streamlit" in self.frameworks:
            return f"streamlit run {self.main_entry}"
        if "Gradio" in self.frameworks:
            return f"python {self.main_entry}"
        if "node-app" in self.project_type:
            scripts = self.deps.get("node", {}).get("scripts", {})
            return "npm start" if "start" in scripts else "node index.js"
        return f"python {self.main_entry}"
