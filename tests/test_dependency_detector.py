"""
Regression tests for dependency parsing.

Each test here pins behaviour that was previously wrong: version specifiers were
silently replaced with "any", editable installs invented a package named "-e",
and unprofiled packages were charged zero RAM and zero disk.
"""

from analyzer.dependency_detector import (
    DependencyDetector,
    UNKNOWN_PACKAGE_RAM_MB,
    UNKNOWN_PACKAGE_DISK_MB,
)


def _deps_by_name(result):
    return {d["name"]: d for d in result["python"]["all"]}


class TestRequirementsTxt:
    def test_preserves_version_specifiers(self, tmp_path):
        key_files = {"requirements.txt": "fastapi==0.104.1\nuvicorn>=0.24\nflask~=3.0\n"}
        deps = _deps_by_name(DependencyDetector(None, key_files).analyze())

        assert deps["fastapi"]["version"] == "==0.104.1"
        assert deps["uvicorn"]["version"] == ">=0.24"
        assert deps["flask"]["version"] == "~=3.0"

    def test_skips_editable_and_vcs_installs(self, tmp_path):
        key_files = {"requirements.txt": "requests\n-e .\ngit+https://github.com/a/b.git\n"}
        deps = _deps_by_name(DependencyDetector(None, key_files).analyze())

        assert set(deps) == {"requests"}

    def test_strips_inline_comments_and_markers(self):
        key_files = {
            "requirements.txt": (
                "numpy  # pinned for reproducibility\n"
                'pywin32; sys_platform == "win32"\n'
            )
        }
        deps = _deps_by_name(DependencyDetector(None, key_files).analyze())

        assert "numpy" in deps
        assert "pywin32" in deps
        assert "#" not in deps["numpy"]["version"]
        assert ";" not in deps["pywin32"]["name"]

    def test_ignores_blank_lines_and_options(self):
        key_files = {"requirements.txt": "\n\n--index-url https://example.invalid\nrich\n"}
        deps = _deps_by_name(DependencyDetector(None, key_files).analyze())

        assert "rich" in deps
        assert not any(n.startswith("-") for n in deps)


class TestPyproject:
    def test_pep621_dependencies_keep_specifiers(self):
        content = (
            "[project]\n"
            'name = "demo"\n'
            'requires-python = ">=3.11"\n'
            "dependencies = [\n"
            '    "fastapi>=0.100",\n'
            '    "pydantic==2.5.0",\n'
            "]\n"
        )
        result = DependencyDetector(None, {"pyproject.toml": content}).analyze()
        deps = _deps_by_name(result)

        assert deps["fastapi"]["version"] == ">=0.100"
        assert deps["pydantic"]["version"] == "==2.5.0"
        assert result["python_requirement"]["minimum"] == "3.11"

    def test_poetry_caret_becomes_a_range(self):
        content = (
            "[tool.poetry.dependencies]\n"
            'python = "^3.10"\n'
            'requests = "^2.31.0"\n'
            'httpx = "~0.25"\n'
            'rich = "*"\n'
        )
        result = DependencyDetector(None, {"pyproject.toml": content}).analyze()
        deps = _deps_by_name(result)

        assert deps["requests"]["version"] == ">=2.31.0,<3.0.0"
        assert deps["httpx"]["version"] == "~=0.25"
        assert deps["rich"]["version"] == "any"
        # `python` is a requirement, not a dependency to pip install.
        assert "python" not in deps
        assert result["python_requirement"]["minimum"] == "3.10"

    def test_poetry_table_form_version(self):
        content = (
            "[tool.poetry.dependencies]\n"
            'torch = { version = "2.1.0", source = "pytorch" }\n'
        )
        deps = _deps_by_name(DependencyDetector(None, {"pyproject.toml": content}).analyze())

        assert deps["torch"]["version"] == "==2.1.0"


class TestPythonRequirement:
    def test_python_version_file_wins_when_present(self):
        result = DependencyDetector(None, {".python-version": "3.12.1\n"}).analyze()
        req = result["python_requirement"]

        assert req["minimum"] == "3.12"
        assert req["source"] == ".python-version"

    def test_runtime_txt_is_understood(self):
        result = DependencyDetector(None, {"runtime.txt": "python-3.9.18\n"}).analyze()

        assert result["python_requirement"]["minimum"] == "3.9"

    def test_absent_requirement_is_empty_not_guessed(self):
        result = DependencyDetector(None, {"requirements.txt": "flask\n"}).analyze()

        assert result["python_requirement"]["minimum"] == ""


class TestResourceAccounting:
    def test_unprofiled_package_is_not_free(self):
        # "some-internal-lib" has no entry in DEPENDENCY_PROFILES.
        key_files = {"requirements.txt": "some-internal-lib\n"}
        result = DependencyDetector(None, key_files).analyze()
        dep = _deps_by_name(result)["some-internal-lib"]

        assert dep["estimated"] is True
        assert dep["ram_mb"] == UNKNOWN_PACKAGE_RAM_MB
        assert dep["disk_mb"] == UNKNOWN_PACKAGE_DISK_MB
        assert dep["note"]

    def test_profiled_package_keeps_its_profile(self):
        result = DependencyDetector(None, {"requirements.txt": "torch\n"}).analyze()
        dep = _deps_by_name(result)["torch"]

        assert dep["estimated"] is False
        assert dep["ram_mb"] > UNKNOWN_PACKAGE_RAM_MB
        assert dep["weight"] == "heavy"

    def test_estimate_reports_profile_coverage(self):
        key_files = {"requirements.txt": "torch\nsome-internal-lib\n"}
        est = DependencyDetector(None, key_files).analyze()["summary"]["resource_estimate"]

        assert est["profiled_packages"] == 1
        assert est["unprofiled_packages"] == 1


class TestPipfile:
    def test_star_version_maps_to_any(self):
        content = '[packages]\nflask = "*"\nrequests = "==2.31.0"\n'
        deps = _deps_by_name(DependencyDetector(None, {"Pipfile": content}).analyze())

        assert deps["flask"]["version"] == "any"
        assert deps["requests"]["version"] == "==2.31.0"


class TestPerProjectGrouping:
    def test_sub_project_requirements_are_grouped_by_directory(self, fullstack_repo):
        root, key_files = fullstack_repo
        result = DependencyDetector(str(root), key_files).analyze()

        assert "backend" in result["python"]["projects"]
        names = {d["name"] for d in result["python"]["projects"]["backend"]}
        assert {"fastapi", "uvicorn"} <= names
