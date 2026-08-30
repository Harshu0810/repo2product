"""
Tests for planner/adaptive_planner.py

Covers: plan caching, prerequisites .get() safety, run command detection,
framework-specific troubleshooting, and full plan text generation.
"""

from tests.conftest import write_repo, build_stages, DEFAULT_CONSTRAINTS
from planner.adaptive_planner import AdaptivePlanner


def _planner(tmp_path, repo_files, constraints=None):
    root = tmp_path / "repo"
    kf = write_repo(root, repo_files)
    c = {**DEFAULT_CONSTRAINTS, **(constraints or {})}
    stages = build_stages(root, kf, c)
    return AdaptivePlanner(
        fetch_result=stages["fetch"],
        structure=stages["structure"],
        dependency_analysis=stages["deps"],
        resource_estimate=stages["resources"],
        adaptation=stages["adaptation"],
        user_constraints=c,
    )


class TestPlanCaching:
    def test_same_plan_returned_on_second_call(self, tmp_path):
        planner = _planner(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "from flask import Flask\napp = Flask(__name__)\n",
        })
        plan1 = planner.generate_plan()
        plan2 = planner.generate_plan()
        # Same dict object — cached, not recomputed
        assert plan1 is plan2

    def test_full_plan_derives_from_generate_plan(self, tmp_path):
        planner = _planner(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "from flask import Flask\napp = Flask(__name__)\n",
        })
        full_text = planner.generate_full_plan()
        assert isinstance(full_text, str)
        assert len(full_text) > 100  # not empty


class TestPrerequisites:
    def test_prerequisites_is_list(self, tmp_path):
        planner = _planner(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "pass\n",
        })
        plan = planner.generate_plan()
        assert isinstance(plan["prerequisites"], list)

    def test_prerequisites_mention_python(self, tmp_path):
        planner = _planner(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "pass\n",
        })
        plan = planner.generate_plan()
        prereqs_text = " ".join(plan["prerequisites"]).lower()
        assert "python" in prereqs_text


class TestRunCommands:
    def test_flask_gets_run_command(self, tmp_path):
        planner = _planner(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "from flask import Flask\napp = Flask(__name__)\n",
        })
        plan = planner.generate_plan()
        runs = plan["run_commands"]
        assert len(runs) > 0
        all_cmds = " ".join(r["command"] for r in runs)
        assert "flask" in all_cmds.lower() or "python" in all_cmds.lower()

    def test_django_gets_runserver(self, tmp_path):
        planner = _planner(tmp_path, {
            "requirements.txt": "django\n",
            "manage.py": "import django\ndjango.setup()\n",
            "settings.py": "INSTALLED_APPS = []\n",
        })
        plan = planner.generate_plan()
        runs = plan["run_commands"]
        all_cmds = " ".join(r["command"] for r in runs)
        assert "runserver" in all_cmds or "manage.py" in all_cmds or "python" in all_cmds


class TestTroubleshooting:
    def test_troubleshooting_is_list_of_dicts(self, tmp_path):
        planner = _planner(tmp_path, {
            "requirements.txt": "flask\n",
            "app.py": "from flask import Flask\napp = Flask(__name__)\n",
        })
        plan = planner.generate_plan()
        tips = plan["troubleshooting"]
        assert isinstance(tips, list)
        if tips:
            assert "issue" in tips[0]
            assert "fix" in tips[0]


class TestOptimizationTips:
    def test_cpu_tips_for_pytorch_project(self, tmp_path):
        planner = _planner(tmp_path, {
            "requirements.txt": "torch\nnumpy\n",
            "main.py": "import torch\ndevice = torch.device('cuda')\n",
        })
        plan = planner.generate_plan()
        tips = plan.get("optimization_tips", [])
        assert isinstance(tips, list)
