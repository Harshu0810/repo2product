"""
Tests for generator/setup_generator.py

Covers: newline correctness in .bat (regression for chr(10) fix), $SCRIPT_DIR
path resolution, exec bits in zip, per-run output isolation, Docker compose
generation, verify.py package→import mapping.
"""

import zipfile
from pathlib import Path

from tests.conftest import write_repo, build_stages, build_artifacts, DEFAULT_CONSTRAINTS


def _quick_artifacts(tmp_path, repo_files, constraints=None):
    """Build stages + artifacts for a minimal repo in one call."""
    root = tmp_path / "repo"
    kf = write_repo(root, repo_files)
    c = {**DEFAULT_CONSTRAINTS, **(constraints or {})}
    stages = build_stages(root, kf, c)
    gen, artifacts = build_artifacts(stages, c, tmp_path / "out")
    return gen, artifacts


class TestSetupSh:
    def test_uses_script_dir_for_requirements(self, tmp_path):
        _, arts = _quick_artifacts(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "from flask import Flask\napp = Flask(__name__)\n",
        })
        sh = arts["setup.sh"]
        assert "$SCRIPT_DIR" in sh
        assert '"$SCRIPT_DIR/requirements_adapted.txt"' in sh

    def test_df_uses_posix_flags(self, tmp_path):
        _, arts = _quick_artifacts(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "from flask import Flask\napp = Flask(__name__)\n",
        })
        assert "df -Pk" in arts["setup.sh"]

    def test_env_loading_uses_set_a(self, tmp_path):
        _, arts = _quick_artifacts(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "from flask import Flask\napp = Flask(__name__)\n",
        })
        run_sh = arts["run.sh"]
        assert "set -a" in run_sh
        assert ". ./.env" in run_sh


class TestSetupBat:
    def test_bat_has_no_literal_backslash_n(self, tmp_path):
        """Regression: \\n.join used to produce '\\n' literals inside .bat scripts."""
        _, arts = _quick_artifacts(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "pass\n",
        })
        bat = arts["setup.bat"]
        # chr(10) is a real newline — the file should never contain a literal '\n'
        assert "\\n" not in bat

    def test_bat_references_script_dir(self, tmp_path):
        _, arts = _quick_artifacts(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "pass\n",
        })
        bat = arts["setup.bat"]
        assert "%SCRIPT_DIR%" in bat

    def test_subproject_uses_pushd_popd(self, tmp_path):
        _, arts = _quick_artifacts(tmp_path, {
            "requirements.txt": "flask\n",
            "backend/requirements.txt": "fastapi\n",
            "backend/main.py": "from fastapi import FastAPI\n",
            "app.py": "pass\n",
        })
        bat = arts["setup.bat"]
        assert "PUSHD" in bat
        assert "POPD" in bat


class TestRunSh:
    def test_cuda_visible_devices_empty_on_cpu(self, tmp_path):
        _, arts = _quick_artifacts(tmp_path, {
            "requirements.txt": "torch\n",
            "main.py": "import torch\n",
        })
        assert "CUDA_VISIBLE_DEVICES=''" in arts["run.sh"]

    def test_cuda_not_disabled_on_gpu(self, tmp_path):
        _, arts = _quick_artifacts(tmp_path, {
            "requirements.txt": "torch\n",
            "main.py": "import torch\n",
        }, constraints={"has_gpu": True})
        # GPU mode should not empty-out the variable
        assert "CUDA_VISIBLE_DEVICES=''" not in arts["run.sh"]


class TestPerRunIsolation:
    def test_two_generators_produce_different_output_dirs(self, tmp_path):
        root = tmp_path / "repo"
        kf = write_repo(root, {
            "requirements.txt": "flask\n",
            "app.py": "pass\n",
        })
        stages = build_stages(root, kf, dict(DEFAULT_CONSTRAINTS))
        _, a1 = build_artifacts(stages, dict(DEFAULT_CONSTRAINTS), tmp_path / "out")
        _, a2 = build_artifacts(stages, dict(DEFAULT_CONSTRAINTS), tmp_path / "out")
        assert a1["_output_dir"] != a2["_output_dir"]


class TestGenerateZip:
    def test_zip_contains_all_expected_files(self, tmp_path):
        gen, _ = _quick_artifacts(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "from flask import Flask\napp = Flask(__name__)\n",
        })
        zip_path = gen.generate_zip()
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())

        assert "setup.sh" in names
        assert "setup.bat" in names
        assert "run.sh" in names
        assert "run.bat" in names
        assert "verify.py" in names
        assert ".env.template" in names
        assert "requirements_adapted.txt" in names
        assert "README_ADAPTED.md" in names

    def test_shell_scripts_have_exec_bit_in_zip(self, tmp_path):
        gen, _ = _quick_artifacts(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "pass\n",
        })
        zip_path = gen.generate_zip()
        with zipfile.ZipFile(zip_path) as zf:
            for name in ("setup.sh", "run.sh"):
                info = zf.getinfo(name)
                unix_mode = (info.external_attr >> 16) & 0o777
                assert unix_mode & 0o111, f"{name} should have exec bits, got {oct(unix_mode)}"


class TestDockerCompose:
    def test_no_version_key(self, tmp_path):
        _, arts = _quick_artifacts(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "from flask import Flask\napp = Flask(__name__)\n",
        })
        dc = arts.get("docker-compose.yml", "")
        if dc:
            assert "version:" not in dc

    def test_copy_uses_adapted_requirements(self, tmp_path):
        _, arts = _quick_artifacts(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "from flask import Flask\napp = Flask(__name__)\n",
        })
        # Check Dockerfiles generated alongside compose
        dockerfiles = [v for k, v in arts.items() if k.startswith("Dockerfile")]
        for df in dockerfiles:
            if "requirements_adapted" in df:
                assert "COPY requirements_adapted.txt" in df


class TestVerifyScript:
    def test_uses_import_map_not_raw_name(self, tmp_path):
        _, arts = _quick_artifacts(tmp_path, {
            "requirements.txt": "scikit-learn\nPillow\n",
            "main.py": "from sklearn.ensemble import RandomForestClassifier\n",
        })
        verify = arts["verify.py"]
        # scikit-learn → sklearn, Pillow → PIL
        assert 'check_import("sklearn"' in verify or 'check_import("PIL"' in verify
