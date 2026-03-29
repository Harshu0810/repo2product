"""
utils/orchestrator.py — Repo2Product AI
Central pipeline that coordinates all modules end-to-end.
Returns a unified analysis result used by the Streamlit UI.
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional, Callable

from analyzer.repo_fetcher import RepoFetcher, RepoFetchError
from analyzer.structure_parser import RepoStructureParser
from analyzer.dependency_detector import DependencyDetector
from resource_engine.resource_estimator import ResourceEstimator, ConstraintEngine
from planner.adaptive_planner import AdaptivePlanner
from planner.failure_predictor import FailurePredictor
from generator.setup_generator import SetupGenerator
from utils.llm_client import LLMClient, OllamaStatus

logger = logging.getLogger(__name__)

CLOUD_MODE = bool(os.environ.get("SPACE_ID") or os.environ.get("R2P_CLOUD"))

DEFAULT_CONSTRAINTS = {
    "ram_gb": 8,
    "os": "linux",
    "has_gpu": False,
    "python_version": "3.10",
    "use_ollama": False,
    "use_hf": False,
    "ollama_model": "llama3.2",
    "hf_token": "",
}


class Repo2ProductPipeline:
    """
    End-to-end pipeline: URL → Analysis → Adaptation → Plan → Artifacts
    """

    def __init__(
        self,
        output_dir: Optional[str] = None,
        github_token: Optional[str] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ):
        if output_dir is None:
            output_dir = "/tmp/repo2product_output" if CLOUD_MODE else "./output"
            
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.github_token = github_token
        self.progress = progress_callback or (lambda msg, pct: None)

    def run(self, url: str, user_constraints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Full pipeline run. Returns comprehensive result dict.
        """
        constraints = {**DEFAULT_CONSTRAINTS, **(user_constraints or {})}
        result: Dict[str, Any] = {
            "url": url,
            "constraints": constraints,
            "stages": {},
            "errors": [],
            "warnings": [],
            "success": False,
        }

        start_time = time.time()

        try:
            # ── Stage 1: Fetch ──────────────────────────────────────────
            self.progress("🔍 Fetching repository...", 5)
            fetcher = RepoFetcher(
                output_dir=str(self.output_dir),
                github_token=self.github_token,
                api_only=CLOUD_MODE,
            )
            fetch_result = fetcher.fetch(url)
            result["stages"]["fetch"] = fetch_result

            if not fetch_result.get("clone_success") and not fetch_result.get("api_success"):
                raise RepoFetchError("Could not fetch repository via clone or API")

            self.progress("✅ Repository fetched", 15)

            # ── Stage 2: Structure Analysis ────────────────────────────
            self.progress("🔬 Analyzing repository structure...", 20)
            parser = RepoStructureParser(
                local_path=fetch_result.get("local_path"),
                file_list=fetch_result.get("file_list", []),
            )
            structure = parser.analyze()
            result["stages"]["structure"] = structure
            self.progress("✅ Structure analyzed", 35)

            # ── Stage 3: Dependency Detection ──────────────────────────
            self.progress("📦 Detecting dependencies...", 38)
            dep_detector = DependencyDetector(
                local_path=fetch_result.get("local_path"),
                key_files=fetch_result.get("key_files", {}),
            )
            dependency_analysis = dep_detector.analyze()
            result["stages"]["dependencies"] = dependency_analysis
            self.progress("✅ Dependencies analyzed", 50)

            # ── Stage 4: Resource Estimation ───────────────────────────
            self.progress("💾 Estimating resource requirements...", 52)
            estimator = ResourceEstimator(dependency_analysis, structure)
            resource_estimate = estimator.estimate()
            result["stages"]["resources"] = resource_estimate
            self.progress("✅ Resources estimated", 60)

            # ── Stage 5: Constraint Adaptation ─────────────────────────
            self.progress("⚙️ Adapting to your system constraints...", 62)
            constraint_engine = ConstraintEngine(dependency_analysis, constraints)
            adaptation = constraint_engine.adapt()
            result["stages"]["adaptation"] = adaptation
            self.progress("✅ Adaptations generated", 70)

            # ── Stage 6: Adaptive Plan ─────────────────────────────────
            self.progress("📋 Generating setup plan...", 72)
            planner = AdaptivePlanner(
                fetch_result=fetch_result,
                structure=structure,
                dependency_analysis=dependency_analysis,
                resource_estimate=resource_estimate,
                adaptation=adaptation,
                user_constraints=constraints,
            )
            plan = planner.generate_plan()
            plan_text = planner.generate_full_plan()
            plan["full_plan_text"] = plan_text
            result["stages"]["plan"] = plan
            self.progress("✅ Setup plan generated", 80)

            # ── Stage 7: Failure Prediction ────────────────────────────
            self.progress("🔮 Predicting potential issues...", 82)
            predictor = FailurePredictor(
                structure=structure,
                dependency_analysis=dependency_analysis,
                adaptation=adaptation,
                user_constraints=constraints,
                local_path=fetch_result.get("local_path"),
            )
            predictions = predictor.predict()
            result["stages"]["predictions"] = predictions
            self.progress("✅ Issues predicted", 88)

            # ── Stage 8: Artifact Generation ──────────────────────────
            self.progress("⚡ Generating setup scripts and artifacts...", 90)
            generator = SetupGenerator(
                fetch_result=fetch_result,
                structure=structure,
                dependency_analysis=dependency_analysis,
                adaptation=adaptation,
                plan=plan,
                user_constraints=constraints,
                output_dir=str(self.output_dir),
            )
            artifacts = generator.generate_all()
            zip_path = generator.generate_zip()
            result["stages"]["artifacts"] = {
                "files": {k: v for k, v in artifacts.items() if k != "_output_dir"},
                "output_dir": artifacts.get("_output_dir", ""),
                "zip_path": zip_path,
            }
            self.progress("✅ Artifacts generated", 95)

            # ── Stage 9: AI Explanation (optional) ─────────────────
            ollama_status = OllamaStatus.get_status()
            result["ollama_status"] = ollama_status
            
            use_ollama = constraints.get("use_ollama") and ollama_status["running"]
            use_hf = constraints.get("use_hf")
            
            if use_ollama or use_hf:
                self.progress("🤖 Generating AI explanation...", 96)
                
                if use_hf:
                    hf_token = constraints.get("hf_token", "")
                    llm = LLMClient(provider="huggingface", api_key=hf_token)
                else:
                    llm = LLMClient(provider="ollama", model=ollama_status.get("best_model", "llama3.2"))
                    llm.auto_select_model()

                explanation = llm.explain_repo(structure, fetch_result.get("metadata", {}))
                cpu_tips = llm.suggest_cpu_optimizations(
                    frameworks=[fw["name"] for fw in structure.get("frameworks", [])],
                    heavy_deps=dependency_analysis.get("summary", {}).get("heavy_deps", []),
                    ram_gb=constraints.get("ram_gb", 8),
                )
                result["stages"]["ai_explanation"] = {
                    "repo_explanation": explanation,
                    "cpu_optimizations": cpu_tips,
                    "model_used": llm.model if use_ollama else "Mistral-7B-Instruct (Cloud)",
                }

            # ── Finalize ───────────────────────────────────────────────
            elapsed = time.time() - start_time
            result["elapsed_seconds"] = round(elapsed, 1)
            result["success"] = True
            result["summary"] = self._build_summary(result)
            self.progress("🎉 Analysis complete!", 100)

        except RepoFetchError as e:
            result["errors"].append({"stage": "fetch", "error": str(e)})
            logger.error(f"Fetch error: {e}")
            self.progress(f"❌ Error: {e}", 0)
        except Exception as e:
            result["errors"].append({"stage": "unknown", "error": str(e)})
            logger.exception(f"Pipeline error: {e}")
            self.progress(f"❌ Error: {e}", 0)

        return result

    def _build_summary(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Build a quick-access summary from all pipeline stages."""
        fetch = result["stages"].get("fetch", {})
        structure = result["stages"].get("structure", {})
        deps = result["stages"].get("dependencies", {})
        resources = result["stages"].get("resources", {})
        adaptation = result["stages"].get("adaptation", {})
        predictions = result["stages"].get("predictions", {})
        artifacts = result["stages"].get("artifacts", {})
        meta = fetch.get("metadata", {})

        return {
            # Repo info
            "repo_name": f"{fetch.get('owner', '')}/{fetch.get('repo', '')}",
            "description": meta.get("description", ""),
            "language": meta.get("language", structure.get("primary_language", "")),
            "stars": meta.get("stars", 0),
            "license": meta.get("license", ""),
            "project_type": structure.get("project_type", "unknown"),
            "frameworks": [fw["name"] for fw in structure.get("frameworks", [])],
            "file_count": structure.get("file_count", 0),
            "has_tests": structure.get("has_tests", False),
            "has_docker": structure.get("has_docker", False),
            "has_ci": structure.get("has_ci", False),
            # Dependencies
            "total_deps": deps.get("summary", {}).get("total_python_deps", 0),
            "heavy_deps": deps.get("summary", {}).get("heavy_deps", []),
            "gpu_required": deps.get("summary", {}).get("gpu_required", []),
            "api_key_required": deps.get("summary", {}).get("api_key_required", []),
            "flagged_issues": deps.get("summary", {}).get("flagged_issues", []),
            # Resources
            "ram_minimum_gb": resources.get("ram", {}).get("minimum_gb", 0),
            "ram_recommended_gb": resources.get("ram", {}).get("recommended_gb", 0),
            "disk_gb": resources.get("disk", {}).get("install_gb", 0),
            "gpu_required_flag": resources.get("gpu", {}).get("required", False),
            "resource_warnings": resources.get("warnings", []),
            # Adaptation
            "compatibility_score": adaptation.get("compatibility_score", 0),
            "compatibility_label": adaptation.get("compatibility_label", ""),
            "packages_replaced": adaptation.get("summary", {}).get("packages_replaced", 0),
            "packages_removed": adaptation.get("summary", {}).get("packages_removed", 0),
            "features_disabled": adaptation.get("summary", {}).get("features_disabled", 0),
            # Predictions
            "risk_level": predictions.get("overall_risk", "LOW"),
            "can_proceed": predictions.get("can_proceed", True),
            "critical_issues": len(predictions.get("criticals", [])),
            "warnings_count": len(predictions.get("warnings", [])),
            # Artifacts
            "zip_path": artifacts.get("zip_path", ""),
            "output_dir": artifacts.get("output_dir", ""),
        }
