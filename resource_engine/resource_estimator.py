"""
resource_engine/resource_estimator.py — Repo2Product AI
Estimates resource requirements and adapts project to user constraints.
"""

from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Lightweight alternative mappings
# ─────────────────────────────────────────────────────────────────────────────

LIGHTWEIGHT_ALTERNATIVES: Dict[str, Dict[str, Any]] = {
    "torch": {
        "cpu_install": "torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu",
        "note": "Install CPU-only PyTorch (saves ~1.5GB vs CUDA version)",
        "ram_saved_mb": 500,
    },
    "tensorflow": {
        "replacement": "tensorflow-cpu",
        "note": "Replace tensorflow with tensorflow-cpu",
        "ram_saved_mb": 400,
    },
    "tensorflow-gpu": {
        "replacement": "tensorflow-cpu",
        "note": "Replace tensorflow-gpu with tensorflow-cpu for CPU systems",
        "code_change": "No code changes needed — same API",
    },
    "faiss-gpu": {
        "replacement": "faiss-cpu",
        "note": "Replace faiss-gpu with faiss-cpu",
        "code_change": "No code changes needed — same API",
    },
    "opencv-python": {
        "replacement": "opencv-python-headless",
        "note": "Use headless OpenCV for servers (no GUI dependencies)",
        "ram_saved_mb": 100,
    },
    "xformers": {
        "replacement": None,
        "note": "xformers requires GPU — disable flash attention in model config",
        "code_change": "Set attn_implementation='eager' instead of 'flash_attention_2'",
    },
    "bitsandbytes": {
        "replacement": None,
        "note": "bitsandbytes is GPU-only — remove quantization or use llama-cpp-python for GGUF quantized models",
        "code_change": "Remove load_in_4bit/load_in_8bit parameters from model loading",
    },
    "auto-gptq": {
        "replacement": "llama-cpp-python",
        "note": "Replace GPTQ quantization with GGUF format via llama-cpp-python",
    },
    "flash-attn": {
        "replacement": None,
        "note": "flash-attn is GPU-only — remove it. Models will use standard attention",
        "code_change": "Remove flash_attn import and use_flash_attention_2=True flags",
    },
    "cupy": {
        "replacement": "numpy",
        "note": "Replace CuPy (GPU arrays) with NumPy for CPU computation",
        "code_change": "Replace 'import cupy as cp' with 'import numpy as cp'",
    },
    "ray": {
        "replacement": "multiprocessing",
        "note": "Replace Ray with Python multiprocessing for CPU parallelism",
    },
    "transformers": {
        "cpu_note": "transformers works on CPU — set device='cpu' in model loading",
        "code_change": "model.to('cpu') and device='cpu' in pipeline()",
        "performance_note": "Inference will be slow on CPU for large models — use smaller models",
    },
    "diffusers": {
        "cpu_note": "diffusers can run on CPU but very slowly — reduce inference steps",
        "code_change": "pipe = pipe.to('cpu'), num_inference_steps=20 (reduce from 50)",
    },
    "accelerate": {
        "cpu_note": "accelerate works on CPU — no device_map='auto' needed",
        "code_change": "Remove device_map='auto', use device='cpu'",
    },
    "peft": {
        "cpu_note": "peft works on CPU for inference — training will be very slow",
    },
    "openai": {
        "replacement": "ollama",
        "note": "Replace OpenAI API with local Ollama for zero-cost LLM",
        "code_change": "Use ollama.chat() or compatible OpenAI client pointing to localhost:11434",
    },
    "anthropic": {
        "replacement": "ollama",
        "note": "Replace Anthropic API with local Ollama for zero-cost LLM",
    },
    "sentence-transformers": {
        "replacement": "ollama",
        "note": "Use Ollama embedding models for zero-cost embeddings",
        "code_change": "Replace SentenceTransformer with Ollama embeddings API",
    },
}

# GPU code patterns and their CPU replacements
GPU_CODE_PATTERNS = [
    {
        "pattern": r"\.to\(['\"]cuda['\"]\)",
        "replacement": ".to('cpu')",
        "description": "Move model to CPU",
    },
    {
        "pattern": r"device\s*=\s*['\"]cuda['\"]",
        "replacement": "device = 'cpu'",
        "description": "Set device to CPU",
    },
    {
        "pattern": r"torch\.cuda\.is_available\(\)",
        "replacement": "False  # CPU-only mode",
        "description": "Disable GPU availability check",
    },
    {
        "pattern": r"device_map\s*=\s*['\"]auto['\"]",
        "replacement": "device_map='cpu'",
        "description": "Force CPU device map",
    },
    {
        "pattern": r"load_in_4bit\s*=\s*True",
        "replacement": "# load_in_4bit=True  # Disabled: requires GPU",
        "description": "Disable 4-bit quantization (GPU-only)",
    },
    {
        "pattern": r"load_in_8bit\s*=\s*True",
        "replacement": "# load_in_8bit=True  # Disabled: requires GPU",
        "description": "Disable 8-bit quantization (GPU-only)",
    },
    {
        "pattern": r"use_flash_attention_2\s*=\s*True",
        "replacement": "# use_flash_attention_2=True  # Disabled: requires GPU",
        "description": "Disable flash attention (GPU-only)",
    },
    {
        "pattern": r"attn_implementation\s*=\s*['\"]flash_attention_2['\"]",
        "replacement": "attn_implementation='eager'",
        "description": "Use standard attention on CPU",
    },
    {
        "pattern": r"torch\.float16",
        "replacement": "torch.float32",
        "description": "Use float32 (more stable on CPU)",
    },
    {
        "pattern": r"torch\.bfloat16",
        "replacement": "torch.float32",
        "description": "Use float32 on CPU",
    },
    {
        "pattern": r"\.half\(\)",
        "replacement": ".float()  # CPU doesn't support half precision well",
        "description": "Use full precision on CPU",
    },
]


class ResourceEstimator:
    """
    Analyzes dependency profiles to estimate total system resource requirements
    and produces a clear resource report.
    """

    def __init__(self, dependency_analysis: Dict[str, Any], structure_analysis: Dict[str, Any]):
        self.deps = dependency_analysis
        self.structure = structure_analysis

    def estimate(self) -> Dict[str, Any]:
        python_deps = self.deps.get("python", {}).get("all", [])
        frameworks = self.structure.get("frameworks", [])

        base_ram = self._base_ram_estimate()
        dep_ram = sum(d.get("ram_mb", 0) for d in python_deps)
        runtime_ram = base_ram + dep_ram

        base_disk = 500  # Python + pip
        dep_disk = sum(d.get("disk_mb", 0) for d in python_deps)
        total_disk = base_disk + dep_disk

        gpu_required = bool(self.deps.get("summary", {}).get("gpu_required"))
        gpu_optional = bool(self.deps.get("summary", {}).get("gpu_optional"))

        cpu_cores_needed = self._estimate_cpu_cores(python_deps, frameworks)
        python_version = self._detect_python_version()

        return {
            "ram": {
                "minimum_mb": int(runtime_ram * 0.7),
                "recommended_mb": int(runtime_ram * 1.2),
                "peak_mb": int(runtime_ram * 1.5),
                "minimum_gb": round(runtime_ram * 0.7 / 1024, 1),
                "recommended_gb": round(runtime_ram * 1.2 / 1024, 1),
            },
            "disk": {
                "install_mb": total_disk,
                "install_gb": round(total_disk / 1024, 1),
                "runtime_overhead_mb": 500,
            },
            "cpu": {
                "cores_minimum": cpu_cores_needed,
                "notes": self._cpu_notes(python_deps),
            },
            "gpu": {
                "required": gpu_required,
                "optional": gpu_optional,
                "required_packages": self.deps.get("summary", {}).get("gpu_required", []),
                "optional_packages": self.deps.get("summary", {}).get("gpu_optional", []),
            },
            "python_version": python_version,
            "network": self._check_network_deps(python_deps),
            "warnings": self._generate_warnings(runtime_ram, total_disk, gpu_required),
        }

    def _base_ram_estimate(self) -> int:
        project_type = self.structure.get("project_type", "")
        base_map = {
            "web-api-python": 150,
            "web-fullstack-python": 300,
            "data-app-streamlit": 400,
            "ml-demo-gradio": 500,
            "ml-training": 1000,
            "nlp-huggingface": 2000,
            "llm-application": 500,
            "python-script": 100,
            "node-app": 200,
        }
        return base_map.get(project_type, 200)

    def _estimate_cpu_cores(self, deps: List[Dict], frameworks: List[Dict]) -> int:
        fw_names = {f["name"] for f in frameworks}
        if any(fw in fw_names for fw in ("PyTorch", "TensorFlow", "HuggingFace")):
            return 4
        if "celery" in {d["name"] for d in deps}:
            return 2
        return 1

    def _cpu_notes(self, deps: List[Dict]) -> List[str]:
        notes = []
        dep_names = {d["name"] for d in deps}
        if "torch" in dep_names:
            notes.append("PyTorch will use all available CPU cores for inference")
        if "transformers" in dep_names:
            notes.append("HuggingFace inference is slow on CPU — expect 10-60s/query")
        if "numpy" in dep_names or "scipy" in dep_names:
            notes.append("NumPy/SciPy use optimized BLAS — benefits from multi-core")
        return notes

    def _detect_python_version(self) -> Dict[str, str]:
        """
        Report the project's declared Python requirement.

        The previous body looped over self.deps and did nothing (`pass`), always
        returning the same hardcoded answer. DependencyDetector now extracts the
        real declaration from .python-version / requires-python / python_requires,
        so read that and fall back to the generic advice only when absent.
        """
        declared = self.deps.get("python_requirement", {}) or {}
        minimum = declared.get("minimum", "")
        if minimum:
            return {
                "minimum": minimum,
                "recommended": f"{minimum}+",
                "declared": declared.get("declared", ""),
                "source": declared.get("source", ""),
            }
        return {"minimum": "3.8", "recommended": "3.10+", "declared": "", "source": "default"}

    def _check_network_deps(self, deps: List[Dict]) -> Dict[str, Any]:
        api_key_deps = [d["name"] for d in deps if d.get("requires_api_key")]
        external_services = []
        if api_key_deps:
            external_services.append("Paid API services (see api_key_required list)")
        return {
            "requires_internet": len(api_key_deps) > 0,
            "api_key_required": api_key_deps,
            "external_services": external_services,
        }

    def _generate_warnings(self, ram_mb: int, disk_mb: int, gpu_required: bool) -> List[Dict]:
        warnings = []
        if gpu_required:
            warnings.append({
                "level": "critical",
                "message": "This project has GPU-required dependencies. CPU-only mode requires modifications.",
            })
        if ram_mb > 7000:
            warnings.append({
                "level": "critical",
                "message": f"Estimated RAM usage ({ram_mb // 1024}GB) exceeds typical available RAM. System may swap.",
            })
        elif ram_mb > 4000:
            warnings.append({
                "level": "warning",
                "message": f"High RAM usage ({ram_mb // 1024}GB). Ensure no other heavy apps are running.",
            })
        if disk_mb > 20000:
            warnings.append({
                "level": "warning",
                "message": f"Large disk footprint ({disk_mb // 1024}GB). Ensure sufficient free space.",
            })
        return warnings


class ConstraintEngine:
    """
    Adapts a project to match user system constraints.
    Produces a list of required modifications and generates adapted configurations.
    """

    def __init__(
        self,
        dependency_analysis: Dict[str, Any],
        user_constraints: Dict[str, Any],
    ):
        self.deps = dependency_analysis
        self.constraints = user_constraints

    def adapt(self) -> Dict[str, Any]:
        """
        Returns adaptation plan with:
        - package_replacements
        - code_modifications
        - disabled_features
        - new_requirements_txt
        - environment_adaptations
        - compatibility_score (0-100)
        """
        python_deps = self.deps.get("python", {}).get("all", [])
        user_ram = self.constraints.get("ram_gb", 8)
        user_has_gpu = self.constraints.get("has_gpu", False)
        user_os = self.constraints.get("os", "linux")

        package_replacements = []
        code_modifications = []
        gpu_patches = []
        disabled_features = []
        removed_packages = []
        environment_changes = []

        # ── GPU → CPU adaptations ──────────────────────────────────────
        if not user_has_gpu:
            for dep in python_deps:
                name = dep["name"]
                alt_info = LIGHTWEIGHT_ALTERNATIVES.get(name, {})

                if dep.get("gpu_required"):
                    if alt_info.get("replacement"):
                        package_replacements.append({
                            "original": name,
                            "replacement": alt_info["replacement"],
                            "reason": "GPU required → CPU alternative",
                            "note": alt_info.get("note", ""),
                        })
                    else:
                        # Two different situations used to land here identically:
                        # a package we know has no CPU substitute, and one we
                        # simply have no entry for. Say which, so the user knows
                        # whether dropping it from requirements is safe.
                        known = name in LIGHTWEIGHT_ALTERNATIVES
                        profile_alts = [a for a in dep.get("alternatives", []) if a]
                        if known:
                            impact = alt_info.get("note") or "Feature will be disabled"
                        elif profile_alts:
                            impact = (
                                "Feature will be disabled. Candidates worth evaluating "
                                f"manually: {', '.join(profile_alts)}"
                            )
                        else:
                            impact = (
                                "Feature will be disabled. No CPU alternative is known to "
                                "Repo2Product — review this package before removing it."
                            )
                        removed_packages.append({
                            "package": name,
                            "reason": (
                                "GPU-only package — no CPU alternative" if known
                                else "GPU-only package — no CPU alternative on record"
                            ),
                            "impact": impact,
                            "confidence": "high" if known else "low",
                        })
                        disabled_features.append({
                            "feature": name,
                            "reason": "Requires GPU",
                            "workaround": alt_info.get("code_change", "Remove usage"),
                        })

                elif dep.get("gpu_optional") and name in LIGHTWEIGHT_ALTERNATIVES:
                    info = LIGHTWEIGHT_ALTERNATIVES[name]
                    if info.get("cpu_note"):
                        code_modifications.append({
                            "package": name,
                            "modification": info["cpu_note"],
                            "code_change": info.get("code_change", ""),
                        })
                    if info.get("cpu_install"):
                        package_replacements.append({
                            "original": name,
                            "replacement": f"{name} (CPU-only install)",
                            "install_cmd": info["cpu_install"],
                            "reason": "Install CPU-only variant",
                        })

            # GPU suppression patches only make sense when there is GPU-aware
            # code to suppress. They were previously emitted for every CPU-only
            # run, so a plain Flask app was told to patch eleven CUDA calls.
            gpu_aware_packages = {"torch", "tensorflow", "tensorflow-gpu", "jax", "cupy",
                                  "transformers", "diffusers", "paddlepaddle", "mxnet"}
            has_gpu_code = any(
                d.get("gpu_required") or d.get("gpu_optional") or d["name"] in gpu_aware_packages
                for d in python_deps
            )
            if has_gpu_code:
                for patch in GPU_CODE_PATTERNS:
                    gpu_patches.append({
                        "type": "regex_patch",
                        "pattern": patch["pattern"],
                        "replacement": patch["replacement"],
                        "description": patch["description"],
                    })

        # ── RAM adaptations ────────────────────────────────────────────
        resource_est = self.deps.get("summary", {}).get("resource_estimate", {})
        estimated_ram_gb = resource_est.get("estimated_ram_gb", 0)

        if estimated_ram_gb > user_ram * 0.8:
            environment_changes.append({
                "type": "memory_limit",
                "action": "Consider reducing batch sizes and model sizes",
                "suggestion": f"Available RAM: {user_ram}GB, Estimated need: {estimated_ram_gb}GB",
            })
            # Suggest streaming / chunking
            environment_changes.append({
                "type": "optimization",
                "action": "Enable model offloading if using HuggingFace",
                "code_change": "device_map={'': 'cpu'} and max_memory={'cpu': f'{int(user_ram*0.7)}GB'}",
            })

        # ── OS-specific adaptations ────────────────────────────────────
        if user_os == "windows":
            environment_changes.append({
                "type": "os_compat",
                "action": "Use setup.bat for Windows environment setup",
                "note": "Some Unix-specific paths may need adjustment",
            })

        # ── API key adaptations ────────────────────────────────────────
        api_key_deps = self.deps.get("summary", {}).get("api_key_required", [])
        for dep in api_key_deps:
            alt = LIGHTWEIGHT_ALTERNATIVES.get(dep, {})
            if alt.get("replacement") == "ollama":
                package_replacements.append({
                    "original": dep,
                    "replacement": "ollama (local)",
                    "reason": "Zero-cost local LLM alternative",
                    "note": alt.get("note", ""),
                    "code_change": alt.get("code_change", ""),
                })

        # ── Build adapted requirements.txt ─────────────────────────────
        new_reqs = self._build_adapted_requirements(
            python_deps, package_replacements, removed_packages
        )

        # ── Compatibility score ────────────────────────────────────────
        score = self._calculate_compatibility_score(
            python_deps, package_replacements, removed_packages, disabled_features
        )

        return {
            "compatibility_score": score,
            "compatibility_label": self._score_label(score),
            "package_replacements": package_replacements,
            "removed_packages": removed_packages,
            # code_modifications = per-package guidance; gpu_patches = regex
            # patches. These used to be the same list filtered two ways, so the
            # UI showed every patch twice.
            "code_modifications": code_modifications,
            "gpu_patches": gpu_patches,
            "disabled_features": disabled_features,
            "environment_changes": environment_changes,
            "adapted_requirements": new_reqs,
            "summary": {
                "packages_replaced": len(package_replacements),
                "packages_removed": len(removed_packages),
                "features_disabled": len(disabled_features),
                "code_patches_needed": len(gpu_patches),
            },
        }

    # Recognised PEP 440 comparison operators, longest first so "==" is not
    # matched as "=" and ">=" is not matched as ">".
    _VERSION_OPERATORS = ("===", "==", "!=", "<=", ">=", "~=", "<", ">")

    @classmethod
    def _normalize_version_spec(cls, version: str) -> str:
        """
        Keep the author's version constraint intact.

        The previous implementation rewrote every specifier as `>=`, which
        silently unpinned `==1.2.3`, widened `~=1.4` and inverted `!=2.0`.
        """
        if not version:
            return ""
        spec = version.strip()
        if not spec or spec.lower() == "any":
            return ""
        # Already a valid specifier (possibly a comma-separated set) — pass through.
        if spec.startswith(cls._VERSION_OPERATORS):
            return spec
        # A bare version such as "1.2.3" (Pipfile/pyproject style) becomes a
        # minimum bound, which is the closest faithful reading.
        if spec[0].isdigit():
            return f">={spec}"
        return ""

    def _build_adapted_requirements(
        self,
        original: List[Dict],
        replacements: List[Dict],
        removed: List[Dict],
    ) -> str:
        """Build the adapted requirements.txt content."""
        replacement_map = {r["original"]: r for r in replacements}
        removed_set = {r["package"] for r in removed}

        lines = [
            "# Adapted requirements.txt — generated by Repo2Product AI",
            "# Adapted for: CPU-only, no GPU, local execution",
            "",
        ]

        for dep in original:
            name = dep["name"]
            version_str = self._normalize_version_spec(dep.get("version", ""))

            if name in removed_set:
                lines.append(f"# REMOVED: {name}{version_str}  # GPU-only, not compatible with CPU")
                continue

            if name in replacement_map:
                rep = replacement_map[name]
                rep_name = rep.get("replacement", name)
                install_cmd = rep.get("install_cmd", "")
                if install_cmd:
                    lines.append(f"# Install separately: pip install {install_cmd}")
                    lines.append(f"# REPLACED: {name}{version_str}")
                    continue
                else:
                    lines.append(f"# Replaced: {name} → {rep_name}")
                    # A replacement package does not share the original's
                    # version history, so the original pin must not be carried over.
                    lines.append(f"{rep_name}")
                    continue

            lines.append(f"{name}{version_str}")

        return "\n".join(lines)

    def _calculate_compatibility_score(
        self,
        deps: List[Dict],
        replacements: List[Dict],
        removed: List[Dict],
        disabled: List[Dict],
    ) -> int:
        if not deps:
            return 90

        base = 100
        removed_set = {r["package"] for r in removed}
        replaced_set = {r["original"] for r in replacements}

        # A GPU package that we removed was already charged as a removal, and one
        # we replaced is largely handled — charging all three used to double- and
        # triple-penalise the same package.
        unresolved_gpu = [
            d for d in deps
            if d.get("gpu_required") and d["name"] not in removed_set and d["name"] not in replaced_set
        ]
        base -= len(unresolved_gpu) * 15
        base -= len(removed) * 10
        base -= len([r for r in replacements if r.get("reason", "").startswith("GPU required")]) * 5
        # Disabled features that aren't just the removal restated.
        extra_disabled = [d for d in disabled if d.get("feature") not in removed_set]
        base -= len(extra_disabled) * 5
        return max(0, min(100, base))

    def _score_label(self, score: int) -> str:
        if score >= 90:
            return "Excellent — runs natively"
        elif score >= 70:
            return "Good — minor modifications needed"
        elif score >= 50:
            return "Fair — significant modifications required"
        elif score >= 30:
            return "Poor — major features disabled"
        else:
            return "Critical — project needs substantial rework"
