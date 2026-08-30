"""
utils/runtime.py — Repo2Product AI
Single definition of the runtime-mode flags the app branches on.

CLOUD_MODE was previously re-derived from the environment in four separate
modules, which made it possible for them to disagree after a refactor.
"""

import os

# True when running on Hugging Face Spaces (SPACE_ID) or any deployment that
# sets R2P_CLOUD (see the Dockerfile). In cloud mode the app avoids `git clone`
# and analyses repositories through the GitHub API instead.
CLOUD_MODE = bool(os.environ.get("SPACE_ID") or os.environ.get("R2P_CLOUD"))


def default_output_dir() -> str:
    """Writable location for generated artifacts, per runtime."""
    return "/tmp/repo2product_output" if CLOUD_MODE else "./output"
