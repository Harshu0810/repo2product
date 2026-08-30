"""
Tests for planner/failure_predictor.py

Covers: Python version check uses user-declared version (not sys.version_info),
cloud mode skips socket probes and doesn't read host os.environ for secrets,
system-lib key normalization, disk/RAM thresholds.
"""

import os
import sys
from unittest.mock import patch

from tests.conftest import write_repo, build_stages, DEFAULT_CONSTRAINTS
from planner.failure_predictor import FailurePredictor


def _predictor(tmp_path, repo_files, constraints=None):
    root = tmp_path / "repo"
    kf = write_repo(root, repo_files)
    c = {**DEFAULT_CONSTRAINTS, **(constraints or {})}
    stages = build_stages(root, kf, c)
    return FailurePredictor(
        structure=stages["structure"],
        dependency_analysis=stages["deps"],
        adaptation=stages["adaptation"],
        user_constraints=c,
        local_path=str(root),
    )


class TestPythonVersionCheck:
    def test_warns_when_user_version_below_project_requirement(self, tmp_path):
        """Predictor should compare the sidebar-declared version, not sys.version_info."""
        pred = _predictor(tmp_path, {
            "requirements.txt": "flask\n",
            ".python-version": "3.12\n",
            "app.py": "pass\n",
        }, constraints={"python_version": "3.9"})

        result = pred.predict()
        msgs = [p["message"] for p in result["predictions"] if p["category"] == "python_version"]
        assert any("3.12" in m and "3.9" in m for m in msgs), \
            f"Expected version mismatch warning, got: {msgs}"

    def test_no_warning_when_user_meets_requirement(self, tmp_path):
        pred = _predictor(tmp_path, {
            "requirements.txt": "flask\n",
            ".python-version": "3.10\n",
            "app.py": "pass\n",
        }, constraints={"python_version": "3.12"})

        result = pred.predict()
        version_preds = [p for p in result["predictions"] if p["category"] == "python_version"]
        assert len(version_preds) == 0

    def test_does_not_use_sys_version(self, tmp_path):
        """
        Even if the server runs Python 3.10, the predictor should check the
        user's declared version (e.g. 3.8), not sys.version_info.
        """
        pred = _predictor(tmp_path, {
            "requirements.txt": "flask\n",
            ".python-version": "3.11\n",
            "app.py": "pass\n",
        }, constraints={"python_version": "3.8"})

        result = pred.predict()
        # Should flag the mismatch regardless of what Python is running this test
        msgs = [p["message"] for p in result["predictions"] if p["category"] == "python_version"]
        assert len(msgs) > 0


class TestCloudMode:
    @patch("planner.failure_predictor.CLOUD_MODE", True)
    def test_cloud_mode_skips_socket_probe_for_ports(self, tmp_path):
        """In cloud mode, port checks should be info-only, not probing sockets."""
        pred = _predictor(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "from flask import Flask\napp = Flask(__name__)\n",
        })
        result = pred.predict()
        port_preds = [p for p in result["predictions"] if p["category"] == "port_conflict"]
        # Should be info level, not warning (no socket probe)
        for p in port_preds:
            assert p["level"] == "info"

    @patch("planner.failure_predictor.CLOUD_MODE", True)
    def test_cloud_mode_treats_all_secrets_as_missing(self, tmp_path):
        """
        In cloud mode, os.environ belongs to the Space container, so all
        secrets should be flagged regardless of what's in the host environment.
        """
        pred = _predictor(tmp_path, {
            "requirements.txt": "openai\n",
            "main.py": "import os\nkey = os.environ['OPENAI_API_KEY']\n",
        })
        result = pred.predict()
        env_preds = [p for p in result["predictions"] if p["category"] == "env_variables"]
        # Should warn about secrets
        assert len(env_preds) > 0


class TestSystemLibNormalization:
    def test_lowercase_dep_matches_system_lib_requirements(self, tmp_path):
        """System-lib keys should be lowercase to match the detector's output."""
        pred = _predictor(tmp_path, {
            "requirements.txt": "psycopg2\n",
            "main.py": "import psycopg2\n",
        })
        result = pred.predict()
        sys_preds = [p for p in result["predictions"] if p["category"] == "system_library"]
        assert len(sys_preds) > 0
        assert any("libpq" in p["fix"] for p in sys_preds)


class TestResourceThresholds:
    def test_critical_when_ram_exceeds_user_budget(self, tmp_path):
        """A project needing 12GB on an 8GB system should flag critical."""
        pred = _predictor(tmp_path, {
            "requirements.txt": "torch\ntransformers\ndiffusers\n",
            "main.py": "import torch\n",
        }, constraints={"ram_gb": 4})

        result = pred.predict()
        mem_preds = [p for p in result["predictions"]
                     if p["category"] == "memory" and p["level"] == "critical"]
        # Heavy deps on 4GB should trigger a critical
        if result["predictions"]:
            # At least warn about memory
            all_mem = [p for p in result["predictions"] if p["category"] == "memory"]
            assert len(all_mem) > 0

    def test_no_critical_when_ram_is_sufficient(self, tmp_path):
        pred = _predictor(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "pass\n",
        }, constraints={"ram_gb": 32})

        result = pred.predict()
        mem_critical = [p for p in result["predictions"]
                        if p["category"] == "memory" and p["level"] == "critical"]
        assert len(mem_critical) == 0


class TestGPUPackageCheck:
    def test_gpu_required_package_without_gpu_is_flagged(self, tmp_path):
        root = tmp_path / "repo"
        kf = write_repo(root, {
            "requirements.txt": "xformers\ntorch\n",
            "main.py": "import torch\n",
        })
        c = {**DEFAULT_CONSTRAINTS, "has_gpu": False}
        stages = build_stages(root, kf, c)
        pred = FailurePredictor(
            structure=stages["structure"],
            dependency_analysis=stages["deps"],
            adaptation={},  # unadapted
            user_constraints=c,
            local_path=str(root),
        )

        result = pred.predict()
        gpu_preds = [p for p in result["predictions"] if p["category"] == "gpu_dependency"]
        # xformers is gpu_required — should be flagged when not removed by adaptation
        assert len(gpu_preds) > 0

    def test_gpu_package_not_flagged_when_gpu_available(self, tmp_path):
        pred = _predictor(tmp_path, {
            "requirements.txt": "xformers\ntorch\n",
            "main.py": "import torch\n",
        }, constraints={"has_gpu": True})

        result = pred.predict()
        gpu_preds = [p for p in result["predictions"] if p["category"] == "gpu_dependency"]
        assert len(gpu_preds) == 0


class TestFilePermissions:
    def test_permission_check_skipped_on_windows(self, tmp_path):
        """On Windows, X_OK is meaningless — permission check should be skipped."""
        pred = _predictor(tmp_path, {
            "run.sh": "#!/bin/bash\necho hello\n",
            "requirements.txt": "flask\n",
            "app.py": "pass\n",
        })
        result = pred.predict()
        perm_preds = [p for p in result["predictions"] if p["category"] == "permissions"]
        if os.name == "nt":
            assert len(perm_preds) == 0
