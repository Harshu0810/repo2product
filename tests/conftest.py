"""
Shared fixtures for the Repo2Product AI test suite.

The helpers here build *synthetic* repositories on disk under pytest's
`tmp_path`, so the tests run identically on Windows, macOS and Linux and never
touch the network or a hardcoded /tmp path.

`key_files` is always keyed by repo-relative POSIX path, matching what
RepoFetcher._fetch_key_files produces in production. Keying it by absolute path
(as the old smoke script did) exercises code paths that never run for real.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


DEFAULT_CONSTRAINTS = {
    "ram_gb": 8,
    "disk_gb": 40,
    "os": "linux",
    "has_gpu": False,
    "python_version": "3.10",
    "use_ollama": False,
    "use_hf": False,
}


def write_repo(root: Path, files: dict) -> dict:
    """
    Write `files` (repo-relative path -> content) under `root`.

    Returns the key_files mapping the pipeline would receive: relative POSIX
    paths to content.
    """
    key_files = {}
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        key_files[Path(rel).as_posix()] = content
    return key_files


@pytest.fixture
def constraints():
    return dict(DEFAULT_CONSTRAINTS)


@pytest.fixture
def gpu_constraints():
    return {**DEFAULT_CONSTRAINTS, "has_gpu": True}


@pytest.fixture
def fullstack_repo(tmp_path):
    """
    A monorepo with a Next.js frontend and a FastAPI backend — the shape that
    exercised the nested-Dockerfile and sub-project-install code paths.
    """
    root = tmp_path / "fullstack"
    key_files = write_repo(root, {
        "frontend/package.json": (
            '{"name": "my-react-app",'
            ' "dependencies": {"react": "^18.0.0", "next": "14.0.0"},'
            ' "scripts": {"dev": "next dev", "start": "next start"}}'
        ),
        "backend/requirements.txt": "fastapi==0.104.1\nuvicorn>=0.24\n",
        "backend/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
        "README.md": "# Fullstack\n\nA test project.\n",
    })
    return root, key_files


@pytest.fixture
def ml_repo(tmp_path):
    """A GPU-flavoured ML repo: heavy deps, pinned versions, an entry point."""
    root = tmp_path / "mlproj"
    key_files = write_repo(root, {
        "requirements.txt": (
            "torch==2.1.0\n"
            "transformers>=4.35.0\n"
            "openai~=1.3\n"
            "numpy\n"
            "# a comment line\n"
            "-e .\n"
            "git+https://github.com/some/pkg.git\n"
        ),
        "main.py": (
            "import os\n"
            "import torch\n"
            "API_KEY = os.environ.get('OPENAI_API_KEY')\n"
            "device = torch.device('cuda')\n"
            "model = model.cuda()\n"
        ),
        ".python-version": "3.11\n",
    })
    return root, key_files


def build_stages(root: Path, key_files: dict, user_constraints: dict) -> dict:
    """
    Run the analysis stages the way the orchestrator does, and return every
    intermediate so tests can assert on any of them.
    """
    from analyzer.structure_parser import RepoStructureParser
    from analyzer.dependency_detector import DependencyDetector
    from resource_engine.resource_estimator import ResourceEstimator, ConstraintEngine
    from planner.adaptive_planner import AdaptivePlanner
    from planner.failure_predictor import FailurePredictor

    file_list = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*") if p.is_file()
    )

    structure = RepoStructureParser(
        local_path=str(root), file_list=file_list, key_files=key_files,
    ).analyze()

    deps = DependencyDetector(str(root), key_files).analyze()
    resources = ResourceEstimator(deps, structure).estimate()
    adaptation = ConstraintEngine(deps, user_constraints).adapt()

    fetch_result = {
        "owner": "octocat",
        "repo": root.name,
        "url": f"https://github.com/octocat/{root.name}",
        "default_branch": "main",
        "local_path": str(root),
        "file_list": file_list,
        "key_files": key_files,
        "metadata": {"description": "test repo", "stars": 0, "license": "MIT"},
    }

    plan = AdaptivePlanner(
        fetch_result=fetch_result,
        structure=structure,
        dependency_analysis=deps,
        resource_estimate=resources,
        adaptation=adaptation,
        user_constraints=user_constraints,
    ).generate_plan()

    predictions = FailurePredictor(
        structure=structure,
        dependency_analysis=deps,
        adaptation=adaptation,
        user_constraints=user_constraints,
        local_path=str(root),
    ).predict()

    return {
        "fetch": fetch_result,
        "structure": structure,
        "deps": deps,
        "resources": resources,
        "adaptation": adaptation,
        "plan": plan,
        "predictions": predictions,
    }


def build_artifacts(stages: dict, user_constraints: dict, output_dir: Path):
    from generator.setup_generator import SetupGenerator

    gen = SetupGenerator(
        fetch_result=stages["fetch"],
        structure=stages["structure"],
        dependency_analysis=stages["deps"],
        adaptation=stages["adaptation"],
        plan=stages["plan"],
        user_constraints=user_constraints,
        output_dir=str(output_dir),
    )
    return gen, gen.generate_all()
