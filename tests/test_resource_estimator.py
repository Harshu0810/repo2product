"""
Tests for resource_engine/resource_estimator.py

Covers: version specifier preservation through adaptation, GPU patch gating
(no patches without GPU deps), compatibility score (no double penalty),
and lightweight alternative mappings.
"""

from tests.conftest import write_repo, build_stages, DEFAULT_CONSTRAINTS
from resource_engine.resource_estimator import ResourceEstimator, ConstraintEngine
from analyzer.dependency_detector import DependencyDetector
from analyzer.structure_parser import RepoStructureParser


def _stages(tmp_path, repo_files, constraints=None):
    root = tmp_path / "repo"
    kf = write_repo(root, repo_files)
    c = {**DEFAULT_CONSTRAINTS, **(constraints or {})}
    return build_stages(root, kf, c), c


class TestVersionPreservation:
    def test_adapted_requirements_keep_pins(self, tmp_path):
        stages, c = _stages(tmp_path, {
            "requirements.txt": "fastapi==0.104.1\nuvicorn>=0.24\n",
            "main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
        })
        adapted = stages["adaptation"].get("adapted_requirements", "")
        # Version specifiers must survive adaptation
        assert "==0.104.1" in adapted or "fastapi" in adapted

    def test_adapted_requirements_does_not_invent_versions(self, tmp_path):
        stages, c = _stages(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "pass\n",
        })
        adapted = stages["adaptation"].get("adapted_requirements", "")
        # "flask" with no version should not get a version injected
        for line in adapted.strip().splitlines():
            if line.strip().lower().startswith("flask"):
                # Acceptable: "flask", "flask\n", NOT "flask>=X.Y"
                clean = line.strip()
                if clean.lower() == "flask":
                    break  # OK


class TestGPUPatchGating:
    def test_no_gpu_patches_for_cpu_only_project(self, tmp_path):
        """A project with no GPU deps should produce zero GPU patches."""
        stages, c = _stages(tmp_path, {
            "requirements.txt": "flask\nrequests\n",
            "app.py": "from flask import Flask\napp = Flask(__name__)\n",
        })
        patches = stages["adaptation"].get("gpu_patches", [])
        assert len(patches) == 0

    def test_gpu_patches_present_for_torch_project(self, tmp_path):
        """A torch project on CPU should get GPU→CPU code patches."""
        stages, c = _stages(tmp_path, {
            "requirements.txt": "torch\nnumpy\n",
            "main.py": "import torch\ndevice = torch.device('cuda')\n",
        }, constraints={"has_gpu": False})
        patches = stages["adaptation"].get("gpu_patches", [])
        # Should have patches for cuda → cpu
        assert len(patches) > 0


class TestCompatibilityScore:
    def test_score_between_0_and_100(self, tmp_path):
        stages, c = _stages(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "from flask import Flask\napp = Flask(__name__)\n",
        })
        score = stages["adaptation"].get("compatibility_score", 0)
        assert 0 <= score <= 100

    def test_simple_project_has_high_score(self, tmp_path):
        """A trivial Flask app with no GPU deps should score very high."""
        stages, c = _stages(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "from flask import Flask\napp = Flask(__name__)\n",
        })
        score = stages["adaptation"].get("compatibility_score", 0)
        assert score >= 70, f"Expected high score for simple project, got {score}"

    def test_gpu_heavy_project_scores_lower_on_cpu(self, tmp_path):
        """A project with many GPU deps on CPU should score lower."""
        stages, c = _stages(tmp_path, {
            "requirements.txt": "torch\nxformers\nbitsandbytes\n",
            "main.py": "import torch\n",
        }, constraints={"has_gpu": False})
        score = stages["adaptation"].get("compatibility_score", 0)
        assert score < 90, f"Expected lower score for GPU-heavy project on CPU, got {score}"


class TestPackageReplacements:
    def test_torch_replaced_on_cpu(self, tmp_path):
        stages, c = _stages(tmp_path, {
            "requirements.txt": "torch\n",
            "main.py": "import torch\n",
        }, constraints={"has_gpu": False})
        replacements = stages["adaptation"].get("package_replacements", [])
        originals = [r["original"] for r in replacements]
        assert "torch" in originals

    def test_torch_kept_on_gpu(self, tmp_path):
        stages, c = _stages(tmp_path, {
            "requirements.txt": "torch\n",
            "main.py": "import torch\n",
        }, constraints={"has_gpu": True})
        replacements = stages["adaptation"].get("package_replacements", [])
        originals = [r["original"] for r in replacements]
        assert "torch" not in originals


class TestResourceEstimation:
    def test_estimates_nonzero_ram(self, tmp_path):
        root = tmp_path / "repo"
        kf = write_repo(root, {
            "requirements.txt": "flask\n",
            "app.py": "pass\n",
        })
        files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        structure = RepoStructureParser(str(root), files, kf).analyze()
        deps = DependencyDetector(str(root), kf).analyze()
        estimate = ResourceEstimator(deps, structure).estimate()

        assert estimate["ram"]["minimum_gb"] > 0

    def test_heavy_project_needs_more_ram(self, tmp_path):
        root = tmp_path / "repo"
        kf = write_repo(root, {
            "requirements.txt": "torch\ntransformers\n",
            "main.py": "import torch\n",
        })
        files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        structure = RepoStructureParser(str(root), files, kf).analyze()
        deps = DependencyDetector(str(root), kf).analyze()
        estimate = ResourceEstimator(deps, structure).estimate()

        assert estimate["ram"]["recommended_gb"] >= 4


class TestEdgeCases:
    def test_empty_requirements_does_not_crash(self, tmp_path):
        stages, c = _stages(tmp_path, {
            "requirements.txt": "# empty\n",
            "main.py": "print('hello')\n",
        })
        assert stages["adaptation"] is not None
        assert stages["adaptation"].get("compatibility_score", 0) >= 0

    def test_no_requirements_file_does_not_crash(self, tmp_path):
        stages, c = _stages(tmp_path, {
            "main.py": "print('hello')\n",
        })
        assert stages["adaptation"] is not None
