import json
import shutil
from pathlib import Path

from analyzer.dependency_detector import DependencyDetector
from analyzer.structure_parser import RepoStructureParser
from planner.adaptive_planner import AdaptivePlanner
from generator.setup_generator import SetupGenerator

# Create dummy repo structure
base = Path("/tmp/dummy_fullstack")
if base.exists():
    shutil.rmtree(base)
base.mkdir(parents=True)

# Frontend
(base / "frontend").mkdir()
with open(base / "frontend" / "package.json", "w") as f:
    json.dump({
        "name": "my-react-app",
        "dependencies": {"react": "^18.0.0", "next": "latest"},
        "scripts": {"dev": "next dev"}
    }, f)

# Backend
(base / "backend").mkdir()
with open(base / "backend" / "requirements.txt", "w") as f:
    f.write("fastapi\nuvicorn\n")
with open(base / "backend" / "main.py", "w") as f:
    f.write("from fastapi import FastAPI\napp = FastAPI()")

# System state
key_files = {
    str(base / "frontend" / "package.json"): open(base / "frontend" / "package.json").read(),
    str(base / "backend" / "requirements.txt"): open(base / "backend" / "requirements.txt").read()
}

# 1. Parse Structure
parser = RepoStructureParser(str(base))
structure = parser.analyze()
print("Project Type:", structure["project_type"])

# 2. Dependency Detect
detector = DependencyDetector(str(base), key_files)
deps = detector.analyze()
print("Deps:", deps["summary"])

# 3. Plan
planner = AdaptivePlanner(
    fetch_result={"owner": "dummy", "repo": "fullstack"},
    structure=structure,
    dependency_analysis=deps,
    resource_estimate={"ram": {"minimum_gb": 4}, "disk": {"install_gb": 1}},
    adaptation={},
    user_constraints={"os": "linux", "ram_gb": 8, "has_gpu": False}
)
plan = planner.generate_plan()

# 4. Generate
gen = SetupGenerator(
    fetch_result={"owner": "dummy", "repo": "fullstack"},
    structure=structure,
    dependency_analysis=deps,
    adaptation={},
    plan=plan,
    user_constraints={"os": "linux", "ram_gb": 8, "has_gpu": False},
    output_dir="/tmp/output"
)
artifacts = gen.generate_all()

print("RUN COMMANDS SH:\n", artifacts["run.sh"])
print("SETUP COMMANDS SH:\n", artifacts["setup.sh"])
