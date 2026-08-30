"""
Tests for analyzer/structure_parser.py

Covers: framework detection, entry point detection, language breakdown,
key_files parameter (cloud-mode), project type classification.
"""

from tests.conftest import write_repo, build_stages, DEFAULT_CONSTRAINTS
from analyzer.structure_parser import RepoStructureParser


class TestLanguageDetection:
    def test_counts_files_by_extension(self, tmp_path):
        root = tmp_path / "proj"
        write_repo(root, {
            "main.py": "print('hello')\n",
            "util.py": "pass\n",
            "index.js": "console.log('hi')\n",
            "README.md": "# Hello\n",
        })
        files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        result = RepoStructureParser(local_path=str(root), file_list=files).analyze()

        assert result["languages"]["Python"] == 2
        assert result["languages"]["JavaScript"] == 1
        assert result["primary_language"] == "Python"


class TestEntryPoints:
    def test_detects_common_names(self, tmp_path):
        root = tmp_path / "proj"
        write_repo(root, {
            "app.py": "from flask import Flask\napp = Flask(__name__)\n",
            "utils.py": "pass\n",
        })
        files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        result = RepoStructureParser(local_path=str(root), file_list=files).analyze()

        paths = [ep["path"] for ep in result["entry_points"]]
        assert "app.py" in paths

    def test_manage_py_is_entry_point(self, tmp_path):
        root = tmp_path / "dj"
        write_repo(root, {
            "manage.py": "import django\ndjango.setup()\n",
            "myapp/__init__.py": "",
        })
        files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        result = RepoStructureParser(local_path=str(root), file_list=files).analyze()

        paths = [ep["path"] for ep in result["entry_points"]]
        assert "manage.py" in paths


class TestFrameworkDetection:
    def test_detects_fastapi_from_imports(self, tmp_path):
        root = tmp_path / "api"
        kf = write_repo(root, {
            "main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
            "requirements.txt": "fastapi\nuvicorn\n",
        })
        files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        result = RepoStructureParser(local_path=str(root), file_list=files, key_files=kf).analyze()

        fw_names = [fw["name"] for fw in result["frameworks"]]
        assert "FastAPI" in fw_names

    def test_detects_streamlit(self, tmp_path):
        root = tmp_path / "stapp"
        kf = write_repo(root, {
            "app.py": "import streamlit as st\nst.title('Hello')\n",
        })
        files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        result = RepoStructureParser(local_path=str(root), file_list=files, key_files=kf).analyze()

        fw_names = [fw["name"] for fw in result["frameworks"]]
        assert "Streamlit" in fw_names

    def test_detects_pytorch_from_key_files_only(self, tmp_path):
        """Cloud mode: no local path, framework detected from key_files content."""
        key_files = {
            "train.py": "import torch\ndevice = torch.device('cuda')\n",
            "requirements.txt": "torch\nnumpy\n",
        }
        # file_list simulates the API tree listing
        file_list = ["train.py", "requirements.txt", "README.md"]
        result = RepoStructureParser(
            local_path=None, file_list=file_list, key_files=key_files,
        ).analyze()

        fw_names = [fw["name"] for fw in result["frameworks"]]
        assert "PyTorch" in fw_names


class TestProjectType:
    def test_fastapi_classified_as_web_api(self, tmp_path):
        root = tmp_path / "api"
        kf = write_repo(root, {
            "main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
            "requirements.txt": "fastapi\nuvicorn\n",
        })
        files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        result = RepoStructureParser(local_path=str(root), file_list=files, key_files=kf).analyze()

        assert "web" in result["project_type"] or "api" in result["project_type"]

    def test_plain_script_classified(self, tmp_path):
        root = tmp_path / "script"
        kf = write_repo(root, {"main.py": "print('hello world')\n"})
        files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        result = RepoStructureParser(local_path=str(root), file_list=files, key_files=kf).analyze()

        assert "python" in result["project_type"].lower() or "script" in result["project_type"].lower()


class TestBooleanFlags:
    def test_has_tests_when_test_directory_exists(self, tmp_path):
        root = tmp_path / "proj"
        write_repo(root, {
            "main.py": "pass\n",
            "tests/test_main.py": "def test_ok(): assert True\n",
        })
        files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        result = RepoStructureParser(local_path=str(root), file_list=files).analyze()

        assert result["has_tests"] is True

    def test_has_docker_when_dockerfile_present(self, tmp_path):
        root = tmp_path / "proj"
        write_repo(root, {
            "main.py": "pass\n",
            "Dockerfile": "FROM python:3.10\nCOPY . .\n",
        })
        files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        result = RepoStructureParser(local_path=str(root), file_list=files).analyze()

        assert result["has_docker"] is True
