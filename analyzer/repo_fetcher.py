"""
repo_fetcher.py — Repo2Product AI
Clones a GitHub repository locally and fetches metadata via GitHub API.
Handles both public and private repos (with token), with shallow clone
to minimize disk and time usage on constrained systems.
"""

import os
import re
import json
import shutil
import subprocess
import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class RepoFetchError(Exception):
    """Raised when repo fetching fails."""
    pass


class RepoFetcher:
    """
    Handles cloning and metadata fetching for GitHub repositories.
    Uses shallow clone (--depth=1) to minimize disk usage.
    Falls back to GitHub API tree listing if git is unavailable.
    """

    GITHUB_API_BASE = "https://api.github.com"
    RAW_BASE = "https://raw.githubusercontent.com"

    def __init__(self, output_dir: str = "./output", github_token: Optional[str] = None, api_only: bool = False):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN")
        self.api_only = api_only
        self._cloned_path: Optional[Path] = None
        # Set by fetch_user_repos when its result may be incomplete.
        self.last_repo_list_error: Optional[str] = None
        # Set by fetch() when the local file scan hit its cap.
        self.file_scan_truncated: bool = False
        # Set by _fetch_key_files when more key files existed than the cap allows.
        self.key_files_truncated: bool = False

    # ------------------------------------------------------------------ #
    #  URL parsing                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def parse_github_url(url: str) -> Tuple[str, str, Optional[str]]:
        """
        Parse a GitHub URL into (owner, repo, branch).
        Supports:
          https://github.com/owner/repo
          https://github.com/owner/repo/tree/branch
          github.com/owner/repo  (no scheme)
          owner/repo  (bare format)
          git@github.com:owner/repo.git
        Returns (owner, repo, branch_or_None).
        """
        url = url.strip().rstrip("/")

        # SSH format — the repo name may legitimately contain dots (e.g. docs.example.com),
        # so only an explicit trailing ".git" is stripped.
        ssh_match = re.match(r"git@github\.com:([^/]+)/(.+?)(?:\.git)?$", url)
        if ssh_match:
            return ssh_match.group(1), ssh_match.group(2), None

        # HTTPS format with optional /tree/branch
        https_match = re.match(
            r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/([^/]+))?(?:/.*)?$",
            url,
        )
        if https_match:
            return https_match.group(1), https_match.group(2), https_match.group(3)

        # No-scheme: github.com/owner/repo
        no_scheme_match = re.match(
            r"github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/([^/]+))?(?:/.*)?$",
            url,
        )
        if no_scheme_match:
            return no_scheme_match.group(1), no_scheme_match.group(2), no_scheme_match.group(3)

        # Bare format: owner/repo (exactly two segments, no dots in first)
        bare_match = re.match(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$", url)
        if bare_match:
            return bare_match.group(1), bare_match.group(2), None

        raise RepoFetchError(f"Cannot parse GitHub URL: {url}")

    # ------------------------------------------------------------------ #
    #  GitHub API helpers                                                  #
    # ------------------------------------------------------------------ #

    def _api_headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "Repo2Product-AI/1.0"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    def _api_get(self, endpoint: str) -> Any:
        url = f"{self.GITHUB_API_BASE}{endpoint}"
        req = urllib.request.Request(url, headers=self._api_headers())
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 429):
                raise RepoFetchError(self._describe_auth_error(e))
            elif e.code == 404:
                raise RepoFetchError(f"Repository not found: {endpoint}")
            raise RepoFetchError(f"GitHub API error {e.code}: {e.reason}")
        except (urllib.error.URLError, TimeoutError) as e:
            raise RepoFetchError(f"Network error: {e}")
        except Exception as e:
            raise RepoFetchError(f"Unexpected API error: {e}")

    def _describe_auth_error(self, err: "urllib.error.HTTPError") -> str:
        """
        GitHub returns 403 for both exhausted rate limits and rejected credentials.
        The x-ratelimit-remaining header tells them apart, so the message can be
        actionable instead of always blaming the rate limit.
        """
        headers = getattr(err, "headers", None)
        remaining = None
        if headers is not None:
            raw = headers.get("x-ratelimit-remaining")
            if raw is not None:
                try:
                    remaining = int(raw)
                except (TypeError, ValueError):
                    remaining = None

        if err.code == 401:
            return "GitHub rejected the token (401). Check that GITHUB_TOKEN is valid and not expired."

        if remaining == 0 or err.code == 429:
            scope = "authenticated" if self.github_token else "unauthenticated"
            hint = (
                "Wait for the limit to reset."
                if self.github_token
                else "Set GITHUB_TOKEN to raise the limit from 60 to 5000 requests/hour."
            )
            return f"GitHub API rate limit exceeded ({scope} request). {hint}"

        if self.github_token:
            return (
                f"GitHub denied the request ({err.code}). The token may lack the required scope, "
                "or the repository may be private to another account."
            )
        return (
            f"GitHub denied the request ({err.code}). This repository may be private — "
            "set GITHUB_TOKEN to access it."
        )

    def fetch_user_repos(self, username: str) -> list:
        """
        Fetch all public repositories for a GitHub username.
        Returns list of dicts with name, full_name, description, stars, language.

        On a mid-pagination failure the partial list is returned and
        `last_repo_list_error` is set, so callers can distinguish a short list
        from a complete one.
        """
        repos: list = []
        self.last_repo_list_error: Optional[str] = None
        page = 1
        while True:
            try:
                url = f"{self.GITHUB_API_BASE}/users/{username}/repos?per_page=100&page={page}&sort=updated"
                req = urllib.request.Request(url, headers=self._api_headers())
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode())
                    if not data:
                        break
                    for r in data:
                        repos.append({
                            "name": r.get("name", ""),
                            "full_name": r.get("full_name", ""),
                            "description": r.get("description", "") or "",
                            "stars": r.get("stargazers_count", 0),
                            "language": r.get("language", "") or "",
                        })
                    if len(data) < 100:
                        break
                    page += 1
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    self.last_repo_list_error = f"GitHub user '{username}' not found."
                elif e.code in (401, 403, 429):
                    self.last_repo_list_error = self._describe_auth_error(e)
                else:
                    self.last_repo_list_error = f"GitHub API error {e.code}: {e.reason}"
                logger.warning(f"Error fetching user repos (page {page}): {self.last_repo_list_error}")
                break
            except Exception as e:
                self.last_repo_list_error = (
                    f"Repository list is incomplete — failed while fetching page {page}: {e}"
                )
                logger.warning(self.last_repo_list_error)
                break
        return repos

    def fetch_repo_metadata(self, owner: str, repo: str) -> Dict[str, Any]:
        """Fetch repository metadata from GitHub API."""
        data = self._api_get(f"/repos/{owner}/{repo}")
        return {
            "full_name": data.get("full_name", f"{owner}/{repo}"),
            "description": data.get("description", "No description"),
            "language": data.get("language", "Unknown"),
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "open_issues": data.get("open_issues_count", 0),
            "default_branch": data.get("default_branch", "main"),
            "size_kb": data.get("size", 0),
            "license": (data.get("license") or {}).get("spdx_id", "Unknown"),
            "topics": data.get("topics", []),
            "homepage": data.get("homepage", ""),
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
            "clone_url": data.get("clone_url", f"https://github.com/{owner}/{repo}.git"),
        }

    def fetch_repo_tree(self, owner: str, repo: str, branch: str = "main") -> list:
        """Fetch file tree from GitHub API (avoids cloning for listing)."""
        try:
            data = self._api_get(f"/repos/{owner}/{repo}/git/trees/{branch}?recursive=1")
            return [item["path"] for item in data.get("tree", []) if item["type"] == "blob"]
        except RepoFetchError:
            return []

    def fetch_raw_file(self, owner: str, repo: str, branch: str, path: str) -> Optional[str]:
        """Fetch a single raw file from GitHub."""
        url = f"{self.RAW_BASE}/{owner}/{repo}/{branch}/{path}"
        req = urllib.request.Request(url, headers=self._api_headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    #  Git clone                                                           #
    # ------------------------------------------------------------------ #

    def _git_available(self) -> bool:
        try:
            result = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _clone_matches(self, clone_path: Path, owner: str, repo: str, branch: Optional[str]) -> bool:
        """
        Confirm an existing directory really is a clone of the repo (and branch) we
        were asked for. Without this, a leftover directory whose name happens to
        collide gets analysed as if it were the requested project.
        """
        if not (clone_path / ".git").exists():
            return False
        try:
            remote = subprocess.run(
                ["git", "-C", str(clone_path), "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=10,
            )
            if remote.returncode != 0:
                return False
            actual = remote.stdout.strip().lower().removesuffix(".git")
            expected = f"github.com/{owner}/{repo}".lower()
            if not actual.endswith(expected):
                logger.info(f"Existing clone at {clone_path} points at {actual}, not {expected}")
                return False

            if branch:
                head = subprocess.run(
                    ["git", "-C", str(clone_path), "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True, timeout=10,
                )
                if head.returncode == 0 and head.stdout.strip() not in (branch, "HEAD"):
                    logger.info(f"Existing clone is on '{head.stdout.strip()}', wanted '{branch}'")
                    return False
            return True
        except (OSError, subprocess.SubprocessError) as e:
            logger.debug(f"Could not verify existing clone: {e}")
            return False

    def clone_repo(
        self,
        owner: str,
        repo: str,
        branch: Optional[str] = None,
        force_reclone: bool = False,
    ) -> Path:
        """
        Shallow-clone a GitHub repo to output_dir/owner__repo.
        Returns path to the cloned directory.

        An existing directory is only reused when it is verifiably a clone of the
        same repo and branch; otherwise it is replaced.
        """
        safe_name = f"{owner}__{repo}"
        clone_path = self.output_dir / safe_name

        if clone_path.exists() and not force_reclone and self._clone_matches(clone_path, owner, repo, branch):
            logger.info(f"Repo already cloned at {clone_path}, reusing.")
            self._cloned_path = clone_path
            return clone_path

        if clone_path.exists():
            shutil.rmtree(clone_path, ignore_errors=True)
            if clone_path.exists():
                raise RepoFetchError(f"Could not clear stale clone directory: {clone_path}")

        if not self._git_available():
            raise RepoFetchError(
                "git is not installed or not in PATH. "
                "Install git or use the API-only analysis mode."
            )

        clone_url = f"https://github.com/{owner}/{repo}.git"
        cmd = ["git", "clone", "--depth=1", "--single-branch"]
        if branch:
            cmd += ["-b", branch]
        cmd += [clone_url, str(clone_path)]

        logger.info(f"Cloning {clone_url} -> {clone_path}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode != 0:
                raise RepoFetchError(
                    f"git clone failed:\n{result.stderr.strip()}"
                )
        except subprocess.TimeoutExpired:
            raise RepoFetchError("git clone timed out after 3 minutes.")

        self._cloned_path = clone_path
        logger.info(f"Successfully cloned to {clone_path}")
        return clone_path

    # ------------------------------------------------------------------ #
    #  High-level fetch entry point                                        #
    # ------------------------------------------------------------------ #

    def fetch(self, url: str, force_reclone: bool = False) -> Dict[str, Any]:
        """
        Main entry point. Returns a rich dict with:
          - metadata
          - local_path (if cloned)
          - file_list
          - key_files (content of important files)
        """
        owner, repo, branch = self.parse_github_url(url)
        logger.info(f"Fetching repo: {owner}/{repo} (branch={branch})")

        result: Dict[str, Any] = {
            "owner": owner,
            "repo": repo,
            "branch": branch,
            "url": url,
            "metadata": {},
            "local_path": None,
            "file_list": [],
            "key_files": {},
            "clone_success": False,
            "api_success": False,
        }

        # 1. Metadata from API
        try:
            meta = self.fetch_repo_metadata(owner, repo)
            result["metadata"] = meta
            result["api_success"] = True
            if not branch:
                branch = meta.get("default_branch", "main")
                result["branch"] = branch
        except RepoFetchError as e:
            logger.warning(f"API metadata fetch failed: {e}")
            branch = branch or "main"
            result["branch"] = branch

        # 2. Clone locally (skip in API-only / cloud mode)
        if not self.api_only:
            try:
                local_path = self.clone_repo(owner, repo, branch, force_reclone)
                result["local_path"] = str(local_path)
                result["clone_success"] = True
            except RepoFetchError as e:
                logger.warning(f"Clone failed: {e}. Falling back to API tree.")
                result["clone_error"] = str(e)
        else:
            logger.info("API-only mode — skipping git clone")

        # 3. File list (from disk or API)
        if result["clone_success"]:
            result["file_list"] = self._scan_local_files(Path(result["local_path"]))
        elif result["api_success"]:
            result["file_list"] = self.fetch_repo_tree(owner, repo, branch)

        # 4. Key file contents
        result["key_files"] = self._fetch_key_files(
            owner, repo, branch, result.get("local_path"), result["file_list"]
        )
        result["file_scan_truncated"] = self.file_scan_truncated
        result["key_files_truncated"] = getattr(self, "key_files_truncated", False)

        return result

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    # Files worth downloading in full. `direct_names` are matched on the exact
    # filename; the extra rules below cover the glob-ish cases. Both live here so
    # the list and the matcher can't drift apart.
    KEY_FILE_NAMES = {
        "requirements.txt", "package.json", "package-lock.json",
        "Pipfile", "Pipfile.lock", "pyproject.toml", "setup.py", "setup.cfg",
        "Dockerfile", "dockerfile", "docker-compose.yml", "docker-compose.yaml",
        ".env.example", ".env.sample", ".env.template",
        "README.md", "README.rst", "README.txt", "readme.md",
        "main.py", "app.py", "run.py", "server.py", "index.py", "cli.py",
        "manage.py",  # Django
        "Makefile", "makefile",
        "go.mod", "go.sum",
        "Cargo.toml",
        "pom.xml", "build.gradle",
        "config.py", "config.yaml", "config.yml", "config.json",
        "settings.py",
        "entrypoint.sh", "start.sh", "run.sh",
        "environment.yml", "environment.yaml",
        # Declared interpreter version — read by DependencyDetector.
        ".python-version", "runtime.txt", ".nvmrc", ".tool-versions",
    }

    def _is_key_file(self, rel_path: str) -> bool:
        fname = Path(rel_path).name
        if fname in self.KEY_FILE_NAMES:
            return True
        if fname.startswith("requirements") and fname.endswith(".txt"):
            return True
        if "docker-compose" in fname:
            return True
        if fname.endswith((".yml", ".yaml")) and ".github/workflows" in rel_path.replace("\\", "/"):
            return True
        return False

    def _scan_local_files(self, root: Path, max_files: int = 2000) -> list:
        """
        Walk local directory and return relative paths.

        Stops at `max_files`; sets `file_scan_truncated` so callers know the
        listing is a prefix of the repo rather than the whole thing.
        """
        files = []
        self.file_scan_truncated = False
        skip_dirs = {".git", "__pycache__", "node_modules", ".tox", "venv", ".venv", "dist", "build"}
        for p in root.rglob("*"):
            if p.is_file():
                parts = set(p.relative_to(root).parts)
                if parts & skip_dirs:
                    continue
                files.append(str(p.relative_to(root)))
                if len(files) >= max_files:
                    self.file_scan_truncated = True
                    logger.warning(f"File scan capped at {max_files} files; listing is incomplete.")
                    break
        return files

    # Downloaded key files are the only content available in API-only mode, so the
    # cap is a real analysis limit — order by usefulness before applying it.
    MAX_KEY_FILES = 50

    # Lower sorts first.
    _KEY_FILE_PRIORITY = (
        ({"requirements.txt", "pyproject.toml", "Pipfile", "setup.py", "package.json",
          "environment.yml", "environment.yaml"}, 0),
        ({"main.py", "app.py", "run.py", "server.py", "index.py", "manage.py", "cli.py",
          "settings.py", "config.py"}, 1),
        ({"Dockerfile", "dockerfile", "docker-compose.yml", "docker-compose.yaml"}, 2),
        ({".env.example", ".env.sample", ".env.template"}, 3),
    )

    def _key_file_rank(self, rel_path: str) -> tuple:
        fname = Path(rel_path).name
        rank = 5
        for names, value in self._KEY_FILE_PRIORITY:
            if fname in names:
                rank = value
                break
        else:
            if fname.startswith("requirements") and fname.endswith(".txt"):
                rank = 0
        # Shallower paths first within a rank — root manifests beat vendored ones.
        return (rank, len(Path(rel_path).parts), rel_path)

    def _fetch_key_files(
        self,
        owner: str,
        repo: str,
        branch: str,
        local_path: Optional[str],
        file_list: list,
    ) -> Dict[str, str]:
        """Read important files from disk or download from GitHub."""
        key_files: Dict[str, str] = {}
        important = sorted(self._identify_key_files(file_list), key=self._key_file_rank)
        self.key_files_truncated = len(important) > self.MAX_KEY_FILES

        for rel_path in important[:self.MAX_KEY_FILES]:
            content = None

            if local_path:
                full = Path(local_path) / rel_path
                if full.is_file():
                    try:
                        with open(full, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read(50_000)  # max 50 KB per file
                    except Exception:
                        pass

            if content is None:
                content = self.fetch_raw_file(owner, repo, branch, rel_path)

            if content is not None:
                key_files[rel_path] = content

        return key_files

    def _identify_key_files(self, file_list: list) -> list:
        """Return files from file_list that match the key-file rules."""
        important = [f for f in file_list if self._is_key_file(f)]

        # Deduplicate while preserving order
        seen = set()
        result = []
        for f in important:
            if f not in seen:
                seen.add(f)
                result.append(f)

        return result

    @property
    def cloned_path(self) -> Optional[Path]:
        return self._cloned_path
