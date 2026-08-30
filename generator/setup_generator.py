"""
generator/setup_generator.py — Repo2Product AI
Generates ready-to-run setup scripts (Linux/Mac and Windows),
.env templates, and a minimal working project structure.
"""

import zipfile
import json
import re
import stat
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

from utils.package_imports import to_import_name

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

    # Entries that must keep their exec bit when extracted from the zip.
    EXECUTABLE_FILES = ("setup.sh", "run.sh")

    # Fixed zip mtime: the artifact content is deterministic for a given
    # analysis, so the archive should be too (and zip has no notion of "now"
    # once you build ZipInfo entries by hand).
    _zip_timestamp = (1980, 1, 1, 0, 0, 0)

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

        # One output directory per generator instance. The hosted app serves many
        # users from a single process and a shared /tmp, so two people analysing
        # the same repository at once must not write over each other.
        self.run_id = uuid.uuid4().hex[:8]
        self.slug = f"{self.owner}__{self.repo}"
        self.project_output = self.output_dir / f"{self.slug}_{self.run_id}"

        # generate_all() is idempotent but not free; generate_zip() reuses this.
        self._artifacts: Optional[Dict[str, str]] = None

    # ------------------------------------------------------------------ #
    #  Main generation entry point                                         #
    # ------------------------------------------------------------------ #

    def generate_all(self) -> Dict[str, str]:
        """Generate all artifacts and return {filename: content} dict."""
        if self._artifacts is not None:
            return dict(self._artifacts)

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
        project_output = self.project_output
        project_output.mkdir(parents=True, exist_ok=True)

        for filename, content in artifacts.items():
            filepath = project_output / filename
            # Sub-project Dockerfiles are nested (e.g. "frontend/Dockerfile"),
            # so the parent directory may not exist yet.
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)

        # Make shell scripts executable (on Unix)
        for sh_file in self.EXECUTABLE_FILES:
            fp = project_output / sh_file
            try:
                fp.chmod(fp.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            except OSError as e:  # no-op on Windows / read-only mounts
                logger.debug(f"Could not set exec bit on {fp}: {e}")

        self._artifacts = dict(artifacts)
        artifacts["_output_dir"] = str(project_output)
        return artifacts

    def generate_zip(self) -> str:
        """Package all artifacts into a downloadable zip."""
        artifacts = self.generate_all()
        artifacts.pop("_output_dir", None)

        zip_path = self.output_dir / f"{self.slug}_{self.run_id}_setup.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, content in artifacts.items():
                # zipfile has no notion of "executable" via writestr(), so build
                # the entry by hand: without this the extracted setup.sh/run.sh
                # arrive mode 0600 and `bash setup.sh` is the only way to run them.
                info = zipfile.ZipInfo(filename, date_time=self._zip_timestamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                executable = filename in self.EXECUTABLE_FILES
                info.external_attr = (0o755 if executable else 0o644) << 16
                zf.writestr(info, content)

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

        # requirements_adapted.txt ships inside this package, not inside the
        # cloned repository, and setup.sh runs from within the clone — so every
        # reference to it has to be resolved against $SCRIPT_DIR.
        adapted = '"$SCRIPT_DIR/requirements_adapted.txt"'

        py_projects = self.deps.get("python", {}).get("projects", {})
        sub_projects = [d for d in py_projects if d not in (".", "")]
        has_root_project = (not py_projects) or any(d in (".", "") for d in py_projects)

        if has_root_project:
            if torch_rep and torch_rep.get("install_cmd"):
                install_cmds.append(f"pip install {torch_rep['install_cmd']}")
                install_cmds.append("# --no-deps first so the adapted requirements cannot pull GPU torch back in")
                install_cmds.append(f"pip install -r {adapted} --no-deps || pip install -r {adapted}")
            else:
                install_cmds.append(f"pip install -r {adapted}")

        for d in sub_projects:
            # Each install runs in a subshell so the cd is scoped: a plain
            # `cd a` / `cd b` sequence compounds into a/b and then fails.
            install_cmds.append(
                f'( cd "{d}" && pip install -r requirements.txt )  '
                f'# sub-project requirements are used as-is (not CPU-adapted)'
            )

        node_projects = self.deps.get("node", {}).get("projects", {})
        for d in node_projects:
            d_clean = d if d not in (".", "") else ""
            if d_clean:
                install_cmds.append(f'( cd "{d_clean}" && npm install )')
            else:
                install_cmds.append("npm install")

        title = f"{self.owner}/{self.repo}"
        needed_mb = int(self.deps.get("summary", {}).get("resource_estimate", {}).get("estimated_disk_mb", 2000))

        next_steps = [f"cd $REPO_NAME", "source venv/bin/activate"]
        if env_vars:
            next_steps.append("Edit .env with your configuration")
        next_steps.append('bash "$SCRIPT_DIR/run.sh"')
        next_steps_block = chr(10).join(
            f'echo "  {i}. {step}"' for i, step in enumerate(next_steps, 1)
        )

        django_block = (
            "# ── Django setup ─────────────────────────────────────────────\n"
            "python manage.py migrate --run-syncdb 2>/dev/null && success 'Database initialized' || true"
            if "Django" in self.frameworks else "# No framework-specific setup needed"
        )

        return f"""#!/usr/bin/env bash
# ============================================================
#  setup.sh — Generated by Repo2Product AI
#  Project: {self.owner}/{self.repo}
#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
#  Target: Linux/macOS, {"GPU-enabled" if self.has_gpu else "CPU-only"}, {self.ram_gb}GB RAM
# ============================================================

set -e  # Exit on any error

# Absolute path to this package, so the generated files can be found after we
# cd into the cloned repository.
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"

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
echo "=============================================="
echo "  Repo2Product AI — Setup Script"
echo "  {title}"
echo "=============================================="
echo ""

# ── Prerequisites check ──────────────────────────────────────
info "Checking prerequisites..."

command -v git >/dev/null 2>&1 || error "git is not installed. Install: sudo apt install git"
command -v "$PYTHON" >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1 || \\
    error "Python not found. Install Python {self.python_ver}+"

PYTHON_CMD=$(command -v "$PYTHON" 2>/dev/null || command -v python3)
PY_VER=$("$PYTHON_CMD" --version 2>&1 | cut -d' ' -f2)
info "Using Python $PY_VER at $PYTHON_CMD"

# Check disk space (need roughly {int(needed_mb * 1.5 / 1024) + 1}GB).
# -P forces POSIX single-line output and -k fixes the unit; bare `df` wraps long
# device names onto two lines and varies its block size between platforms.
AVAILABLE_KB=$(df -Pk . | awk 'NR==2 {{print $4}}')
NEEDED_KB={int(needed_mb * 1.5) * 1024}
if [ -n "$AVAILABLE_KB" ] && [ "$AVAILABLE_KB" -lt "$NEEDED_KB" ]; then
    warn "Low disk space. Available: $((AVAILABLE_KB/1024))MB, Recommended: $((NEEDED_KB/1024))MB"
fi
success "Prerequisites OK"

# ── Clone repository ─────────────────────────────────────────
cd "$SCRIPT_DIR"
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
    "$PYTHON_CMD" -m venv venv || error "Failed to create venv. Try: pip install virtualenv"
    success "Virtual environment created"
else
    info "Virtual environment already exists"
fi

# shellcheck disable=SC1091
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
    elif [ -f "$SCRIPT_DIR/.env.template" ]; then
        cp "$SCRIPT_DIR/.env.template" .env
        warn ".env created from template — please edit with your values"
    else
        warn "No .env template found — create .env manually if needed"
    fi
else
    info ".env already exists"
fi

{django_block}

# ── Verify installation ───────────────────────────────────────
info "Running verification..."
python "$SCRIPT_DIR/verify.py" && success "Verification passed" || \\
    warn "Verification had warnings — check above output"

# ── Done ──────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo "  Setup Complete!"
echo "=============================================="
echo ""
echo "  Next steps:"
{next_steps_block}
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
        sub_projects = [d for d in py_projects if d not in (".", "")]
        has_root_project = (not py_projects) or any(d in (".", "") for d in py_projects)

        bat_installs = ["pip install --upgrade pip wheel setuptools"]
        if has_root_project:
            # Same story as setup.sh: the adapted requirements live beside this
            # script (%SCRIPT_DIR%), not inside the freshly cloned repository.
            bat_installs.append('pip install -r "%SCRIPT_DIR%requirements_adapted.txt"')
            bat_installs.append("IF ERRORLEVEL 1 ( echo [WARN] Some packages failed )")

        for d in sub_projects:
            # PUSHD/POPD keeps each directory change scoped, so consecutive
            # sub-projects don't stack up into a nested path that doesn't exist.
            win_dir = d.replace("/", "\\")
            bat_installs.append(f'PUSHD "{win_dir}"')
            bat_installs.append("REM sub-project requirements are used as-is (not CPU-adapted)")
            bat_installs.append("pip install -r requirements.txt")
            bat_installs.append("IF ERRORLEVEL 1 ( echo [WARN] Some packages failed in " + win_dir + " )")
            bat_installs.append("POPD")

        node_projects = self.deps.get("node", {}).get("projects", {})
        for d in node_projects:
            d_clean = d if d not in (".", "") else ""
            if d_clean:
                win_dir = d_clean.replace("/", "\\")
                bat_installs.append(f'PUSHD "{win_dir}"')
                bat_installs.append("call npm install")
                bat_installs.append("POPD")
            else:
                bat_installs.append("call npm install")

        bat_install_block = chr(10).join(bat_installs)

        next_steps = ["cd %REPO_NAME%", "venv\\Scripts\\activate"]
        if self.structure.get("env_variables", {}):
            next_steps.append("Edit .env with your configuration")
        next_steps.append('call "%SCRIPT_DIR%run.bat"')
        next_steps_block = chr(10).join(
            f"echo   {i}. {step}" for i, step in enumerate(next_steps, 1)
        )

        return f"""@echo off
REM ============================================================
REM  setup.bat — Generated by Repo2Product AI
REM  Project: {self.owner}/{self.repo}
REM  Target: Windows, {"GPU-enabled" if self.has_gpu else "CPU-only"}, {self.ram_gb}GB RAM
REM ============================================================

SETLOCAL EnableDelayedExpansion
REM Directory containing this script (with trailing backslash).
SET SCRIPT_DIR=%~dp0
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
CD /D "%SCRIPT_DIR%"
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
    IF ERRORLEVEL 1 (echo [ERROR] Could not create venv & pause & exit /b 1)
)
CALL venv\\Scripts\\activate.bat
echo [OK] Virtual environment activated

REM Install dependencies
echo [INFO] Installing dependencies...
{bat_install_block}

REM Environment
IF NOT EXIST .env (
    IF EXIST .env.example (
        COPY .env.example .env >nul
        echo [WARN] .env created from .env.example -- please edit with your values
    ) ELSE (
        IF EXIST "%SCRIPT_DIR%.env.template" (
            COPY "%SCRIPT_DIR%.env.template" .env >nul
            echo [WARN] .env created from template -- please edit with your values
        )
    )
)

REM Verify installation
echo [INFO] Running verification...
%PYTHON% "%SCRIPT_DIR%verify.py"

echo.
echo  ============================================
echo   Setup Complete!
echo  ============================================
echo.
echo   Next steps:
{next_steps_block}
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
            extra_services.append("BG_PIDS+=($!)")

        pre_checks = []
        if "Django" in self.frameworks:
            pre_checks.append("python manage.py migrate --check 2>/dev/null || python manage.py migrate")

        env_export = []
        omp_threads = max(2, min(8, self.ram_gb // 2))
        if not self.constraints.get("has_gpu", False):
            env_export.append("export CUDA_VISIBLE_DEVICES=''  # Disable CUDA on CPU-only system")
        env_export += [
            f"export OMP_NUM_THREADS={omp_threads}         # Optimize OpenMP thread count",
            "export TOKENIZERS_PARALLELISM=false  # Avoid HuggingFace warnings",
        ]

        run_cmds_sh = []
        for i, run in enumerate(runs):
            run_cmd_line = run["command"]
            run_cmds_sh.append(f"echo \"[run.sh] Starting {run['label']}...\"")
            if i < len(runs) - 1:
                run_cmds_sh.append(f"{run_cmd_line} &")
                run_cmds_sh.append("BG_PIDS+=($!)")
                run_cmds_sh.append("")
            else:
                run_cmds_sh.append(f"{run_cmd_line}")

        runs_block = "\n".join(run_cmds_sh) if run_cmds_sh else "echo '[run.sh] No run command was detected — see README_ADAPTED.md'"

        return f"""#!/usr/bin/env bash
# ============================================================
#  run.sh — Generated by Repo2Product AI
#  Project: {self.owner}/{self.repo}
#  Run type: {self.project_type}
# ============================================================

set -e

# This script sits in the generated package; setup.sh clones the repository
# beside it. Run from inside the clone so relative paths and venv/ resolve.
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
cd "$SCRIPT_DIR"
if [ -d "{self.repo}" ]; then
    cd "{self.repo}"
fi

# Background services started below are killed when this script exits, so
# Ctrl-C doesn't leave orphaned workers behind.
BG_PIDS=()
cleanup() {{
    for pid in "${{BG_PIDS[@]}}"; do
        kill "$pid" 2>/dev/null || true
    done
}}
trap cleanup EXIT

# ── Activate virtual environment ──────────────────────────────
if [ -f "venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
elif [ -f "../venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source ../venv/bin/activate
fi

# ── Environment ───────────────────────────────────────────────
# `set -a` exports everything the file defines. The previous
# `xargs -d '\\n'` form is a GNU extension and fails outright on macOS.
if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
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

        runs_block = "\n".join(run_cmds_bat) if run_cmds_bat else "echo [run.bat] No run command was detected -- see README_ADAPTED.md"

        return f"""@echo off
REM run.bat — Generated by Repo2Product AI
SETLOCAL

REM setup.bat clones the repository next to this script; run from inside it.
CD /D "%~dp0"
IF EXIST "{self.repo}" CD /D "{self.repo}"

IF EXIST venv\\Scripts\\activate.bat (
    CALL venv\\Scripts\\activate.bat
)

IF EXIST .env (
    FOR /F "usebackq tokens=1,* delims== eol=#" %%A IN (".env") DO (
        SET "%%A=%%B"
    )
)

{"REM GPU enabled -- CUDA left as configured" if self.has_gpu else "SET CUDA_VISIBLE_DEVICES="}
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
                    val = "" if val is None else str(val)
                    if not val or val == "<required>":
                        lines.append(f"{var}=  # Required — fill this in")
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

        # Filter first, then take 10. Slicing before filtering meant a repo whose
        # first entries were all GPU-only produced a verifier that checked nothing.
        imports_to_check = []
        for dep in python_deps:
            if dep.get("gpu_required"):
                continue
            name = dep["name"]
            # A package's distribution name is often not its import name
            # (scikit-learn → sklearn, beautifulsoup4 → bs4, pillow → PIL).
            import_name = to_import_name(name)
            if not import_name:
                continue
            imports_to_check.append((name, import_name))
            if len(imports_to_check) >= 10:
                break

        checks = []
        for pkg_name, import_name in imports_to_check:
            checks.append(f'check_import("{import_name}", "{pkg_name}")')

        # Entry point checks
        entry_checks = []
        for ep in self.entry_points[:3]:
            entry_checks.append(f'check_file("{ep["path"]}")')

        # Only probe Ollama when something in the project actually wants a local LLM.
        wants_ollama = bool(self.deps.get("summary", {}).get("local_llm_deps"))
        services_block = "check_ollama()" if wants_ollama else 'print("  (no local services required)")'

        return f'''#!/usr/bin/env python3
"""verify.py — Repo2Product AI Installation Verifier"""
import sys
import os

PASS = "OK"; FAIL = "FAIL"; WARN = "WARN"
errors = 0; warnings = 0

def check_import(module, package_name=""):
    global errors
    try:
        __import__(module)
        print(f"  [{{PASS}}] {{package_name or module}}")
    except ImportError as e:
        print(f"  [{{FAIL}}] {{package_name or module}}: {{e}}")
        errors += 1
    except Exception as e:
        # Importing succeeded but the module blew up on load (missing system
        # library, bad config). Worth reporting, but not an install failure.
        print(f"  [{{WARN}}] {{package_name or module}} imported with errors: {{e}}")
        warnings += 1

def check_file(path):
    global warnings
    if os.path.exists(path):
        print(f"  [{{PASS}}] {{path}}")
    else:
        print(f"  [{{WARN}}] {{path}} not found")
        warnings += 1

def check_python_version():
    global errors
    required = ({self._required_python_tuple()})
    if sys.version_info[:2] < required:
        print(f"  [{{FAIL}}] Python {{sys.version_info.major}}.{{sys.version_info.minor}} < {{required[0]}}.{{required[1]}}")
        errors += 1
    else:
        print(f"  [{{PASS}}] Python {{sys.version_info.major}}.{{sys.version_info.minor}}.{{sys.version_info.micro}}")

def check_ollama():
    global warnings
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        print(f"  [{{PASS}}] Ollama server running")
    except Exception:
        print(f"  [{{WARN}}] Ollama not running (needed for this project's local LLM features)")
        warnings += 1

print()
print("=" * 50)
print("  Repo2Product AI - Installation Verifier")
print("  {self.owner}/{self.repo}")
print("=" * 50)

print("\\n[ Python Version ]")
check_python_version()

print("\\n[ Required Packages ]")
{chr(10).join(checks) if checks else 'print("  (no packages to verify)")'}

print("\\n[ Project Files ]")
{chr(10).join(entry_checks) if entry_checks else 'print("  (no entry points to verify)")'}

print("\\n[ Services ]")
{services_block}

print()
print("=" * 50)
if errors == 0 and warnings == 0:
    print(f"  [{{PASS}}] All checks passed!")
elif errors == 0:
    print(f"  [{{WARN}}] {{warnings}} warning(s) - project may still run")
else:
    print(f"  [{{FAIL}}] {{errors}} error(s) - fix before running")
print("=" * 50)
print()

sys.exit(errors)
'''

    def _required_python_tuple(self) -> str:
        """Render the target Python version as a literal tuple for verify.py."""
        parts = str(self.python_ver or "3.8").split(".")
        try:
            major, minor = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        except ValueError:
            major, minor = 3, 8
        return f"{major}, {minor}"

    # ------------------------------------------------------------------ #
    #  Docker Compose                                                      #
    # ------------------------------------------------------------------ #

    def _generate_docker_compose(self) -> Dict[str, str]:
        """Generate CPU-only docker-compose.yml and associated Dockerfiles.

        Every service builds from this package directory as its context and
        clones the repository inside the image. That is what makes the compose
        file usable straight out of the extracted zip: the previous version set
        the context to the source tree, which does not contain
        requirements_adapted.txt, so `docker compose build` failed on COPY.
        """
        files: Dict[str, str] = {}
        services: List[str] = []

        py_projects = self.deps.get("python", {}).get("projects", {})
        node_projects = self.deps.get("node", {}).get("projects", {})

        if not py_projects and not node_projects:
            return {}

        repo_url = f"https://github.com/{self.owner}/{self.repo}.git"
        omp_threads = max(2, min(8, self.ram_gb // 2))
        used_ports = set()

        # ── Python Services ────────────────────────────────────────
        for d in py_projects:
            d_clean = d if d not in (".", "") else ""
            is_root = not d_clean
            svc_name = "backend" if is_root else f"backend-{self._safe_name(d_clean)}"

            port = self._pick_port(self._default_python_port(), used_ports)
            cmd = self._docker_command(d_clean)

            workdir = "/app" if is_root else f"/app/{d_clean}"
            # Root projects install the CPU-adapted requirements shipped in this
            # package; sub-projects fall back to their own requirements.txt.
            if is_root:
                install = (
                    "COPY requirements_adapted.txt /tmp/requirements_adapted.txt\n"
                    "RUN pip install --no-cache-dir -r /tmp/requirements_adapted.txt"
                )
            else:
                install = (
                    "# Sub-project requirements are used as-is (not CPU-adapted)\n"
                    f'RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi'
                )

            df = f"""# Generated by Repo2Product AI — CPU-only image for {svc_name}
FROM python:{self.python_ver}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    OMP_NUM_THREADS={omp_threads} \\
    TOKENIZERS_PARALLELISM=false \\
    CUDA_VISIBLE_DEVICES=

RUN apt-get update \\
 && apt-get install -y --no-install-recommends git \\
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN git clone --depth=1 {repo_url} /app
WORKDIR {workdir}

{install}

EXPOSE {port}
CMD {cmd}
"""
            df_path = "Dockerfile" if is_root else f"Dockerfile.{self._safe_name(d_clean)}"
            files[df_path] = df

            services.append(f"""  {svc_name}:
    build:
      context: .
      dockerfile: {df_path}
    ports:
      - "{port}:{port}"
    environment:
      OMP_NUM_THREADS: "{omp_threads}"
      TOKENIZERS_PARALLELISM: "false"
      CUDA_VISIBLE_DEVICES: ""
    restart: unless-stopped""")

        # ── Node Services ──────────────────────────────────────────
        for d, pkg in node_projects.items():
            d_clean = d if d not in (".", "") else ""
            svc_name = "frontend" if not d_clean else f"frontend-{self._safe_name(d_clean)}"

            # Vite defaults to 5173, create-react-app to 3000.
            default_node_port = 5173 if "vite" in json.dumps(pkg).lower() else 3000
            port = self._pick_port(default_node_port, used_ports)

            workdir = "/app" if not d_clean else f"/app/{d_clean}"
            df = f"""# Generated by Repo2Product AI — image for {svc_name}
FROM node:18-alpine

RUN apk add --no-cache git
WORKDIR /app
RUN git clone --depth=1 {repo_url} /app
WORKDIR {workdir}

RUN npm install

ENV NODE_ENV=development
EXPOSE {port}
CMD ["npm", "run", "dev"]
"""
            df_path = f"Dockerfile.{svc_name}"
            files[df_path] = df

            services.append(f"""  {svc_name}:
    build:
      context: .
      dockerfile: {df_path}
    ports:
      - "{port}:{port}"
    environment:
      NODE_ENV: "development"
    restart: unless-stopped""")

        if not services:
            return {}

        # No `version:` key — it has been obsolete since Compose v2 and current
        # versions print a warning for it.
        compose_yml = f"""# docker-compose.yml — Generated by Repo2Product AI
# Build context is this directory; each image clones
# {repo_url} at build time.
services:
{chr(10).join(services)}
"""
        files["docker-compose.yml"] = compose_yml
        return files

    @staticmethod
    def _safe_name(path: str) -> str:
        """Turn a sub-directory path into a service/file-name-safe token."""
        token = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")
        return token or "app"

    @staticmethod
    def _pick_port(preferred: int, used: set) -> int:
        """Give each service its own host port instead of colliding on one."""
        port = preferred
        while port in used:
            port += 1
        used.add(port)
        return port

    def _default_python_port(self) -> int:
        if "FastAPI" in self.frameworks or "Django" in self.frameworks:
            return 8000
        if "Flask" in self.frameworks:
            return 5000
        if "Streamlit" in self.frameworks:
            return 8501
        if "Gradio" in self.frameworks:
            return 7860
        return 8000

    @staticmethod
    def _unwrap_subshell(command: str) -> tuple:
        """Split `( cd "web" && npm start )` into ("npm start", "web")."""
        m = re.match(r'^\(\s*cd\s+"?([^"&]+?)"?\s*&&\s*(.+?)\s*\)$', command.strip())
        if m:
            return m.group(2).strip(), m.group(1).strip()
        # Legacy/plain form: `cd web && npm start`
        m = re.match(r'^cd\s+"?([^"&]+?)"?\s*&&\s*(.+)$', command.strip())
        if m:
            return m.group(2).strip(), m.group(1).strip()
        return command.strip(), ""

    def _docker_command(self, sub_dir: str) -> str:
        """JSON-array CMD for a service, preferring the planned run command."""
        markers = ("runserver", "uvicorn", "flask run", "streamlit", "gunicorn", "python ")
        for r in self.plan.get("run_commands", []):
            inner, cmd_dir = self._unwrap_subshell(r.get("command", ""))
            # Only adopt a run command that belongs to this sub-project.
            if cmd_dir.strip("./") != sub_dir.strip("./"):
                continue
            if any(m in inner for m in markers):
                # Inline `VAR=value cmd` needs a shell, so keep it in shell form.
                if re.match(r"^[A-Z_][A-Z0-9_]*=", inner):
                    return json.dumps(["sh", "-c", inner])
                return json.dumps(inner.split())
        return json.dumps(["python", self.main_entry if not sub_dir else "main.py"])

    # ------------------------------------------------------------------ #
    #  README_ADAPTED.md                                                   #
    # ------------------------------------------------------------------ #

    def _generate_readme(self) -> str:
        compat = self.adaptation.get("compatibility_score", 0)
        compat_label = self.adaptation.get("compatibility_label", "")
        run_cmd = self._get_primary_run_command()
        meta = self.fetch.get("metadata", {})
        has_compose = bool(self.deps.get("python", {}).get("projects")) or bool(self.deps.get("node", {}).get("projects"))
        compose_row = "| `docker-compose.yml` | Containerized environment config |\n" if has_compose else ""
        compose_section = f"""
### Docker

```bash
docker compose up --build
```

Each image clones `{self.owner}/{self.repo}` at build time, so this works
directly from the extracted package — no separate clone needed.
""" if has_compose else ""

        return f"""# {self.owner}/{self.repo} — Adapted Setup Guide

> **Generated by Repo2Product AI** on {datetime.now().strftime('%Y-%m-%d')}

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
{compose_row}| `verify.py` | Post-install verification |
| `README_ADAPTED.md` | This file |

> Keep these files together. `setup.sh` clones the repository into
> `{self.repo}/` **next to them** and installs from `requirements_adapted.txt`
> in this directory, so moving individual files will break those paths.

## 🚀 Quick Start

### Linux / macOS
```bash
bash setup.sh      # One-time setup: clones the repo, builds a venv, installs
bash run.sh        # Run the project
```

### Windows
```batch
setup.bat          REM One-time setup
run.bat            REM Run the project
```

### Manual
```bash
# from this directory
git clone --depth=1 https://github.com/{self.owner}/{self.repo}.git
cd {self.repo}
python3 -m venv venv && source venv/bin/activate
pip install -r ../requirements_adapted.txt
cp ../.env.template .env   # then edit with your values
cd .. && bash run.sh
```
{compose_section}
## 🔄 CPU Adaptations

{self._render_adaptations_table()}

## ▶️ Primary Run Command

```bash
{run_cmd}
```

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
        # Same merge as .env.template, so the README and the template agree.
        env_setup = self.plan.get("environment_setup", {})
        variables = {**self.structure.get("env_variables", {}), **env_setup.get("variables", {})}
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
