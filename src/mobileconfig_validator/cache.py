"""
ProfileManifests cache management using sparse git clone.

Handles fetching, updating, and managing the local cache of ProfileManifests
from https://github.com/ProfileManifests/ProfileManifests
"""

import json
import logging
import os
import re
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # Windows: no locking; concurrent first runs may race
    fcntl = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _get_default_cache_dir() -> Path:
    """
    Determine the default cache directory using platform conventions.

    Order of precedence:
    1. VALIDATOR_CACHE_DIR environment variable
    2. XDG_CACHE_HOME/mobileconfig-validator (Linux/macOS)
    3. ~/.cache/mobileconfig-validator (fallback)
    """
    # Environment variable takes precedence
    env_cache = os.environ.get("VALIDATOR_CACHE_DIR")
    if env_cache:
        return Path(env_cache)

    # Use XDG_CACHE_HOME if set (Linux/macOS standard)
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache) / "mobileconfig-validator"

    # Default to ~/.cache/mobileconfig-validator
    return Path.home() / ".cache" / "mobileconfig-validator"


DEFAULT_CACHE_DIR = _get_default_cache_dir()
REPO_URL = "https://github.com/ProfileManifests/ProfileManifests.git"
REPO_DIR_NAME = "ProfileManifests"

# ProfileManifests commit the validator is tested against. Tracking upstream
# HEAD let an unrelated manifest change fail every consumer's CI with no code
# change (2026-09-17, com.apple.screensaver moduleName). Bump deliberately:
# see "Updating the ProfileManifests pin" in README.md.
# VALIDATOR_PROFILEMANIFESTS_REF overrides it with another commit or a branch.
PROFILEMANIFESTS_REF = "73fc518f485c2b29ec8184d26b068266e8f30deb"

# Cache staleness threshold (days)
DEFAULT_MAX_AGE_DAYS = 7


class ManifestCache:
    """
    Manages ProfileManifests repository cache using sparse git clone.

    Uses shallow sparse clone to download only the Manifests directory (~10MB).
    A commit ref (the default) is checked out exactly and never goes stale; a
    branch ref is re-fetched once the cache is older than max_age_days.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        max_age_days: int | None = None,
        offline: bool = False,
        ref: str | None = None,
        repo_url: str = REPO_URL,
    ):
        """
        Initialise the manifest cache.

        Args:
            cache_dir: Directory to store the cache. Defaults to ~/.cache/mobileconfig-validator/
            max_age_days: Days before cache is considered stale. Defaults to 7.
                          Can be overridden with VALIDATOR_CACHE_MAX_AGE env var.
            offline: If True, never attempt network operations.
            ref: ProfileManifests commit or branch. Defaults to
                 VALIDATOR_PROFILEMANIFESTS_REF, then PROFILEMANIFESTS_REF.
            repo_url: Repository to clone (overridable for tests).
        """
        self.cache_dir = cache_dir or Path(
            os.environ.get("VALIDATOR_CACHE_DIR", str(DEFAULT_CACHE_DIR))
        )
        if max_age_days is not None:
            self.max_age_days = max_age_days
        else:
            self.max_age_days = int(
                os.environ.get("VALIDATOR_CACHE_MAX_AGE", str(DEFAULT_MAX_AGE_DAYS))
            )
        self.offline = offline or os.environ.get("VALIDATOR_OFFLINE", "").lower() in (
            "1",
            "true",
            "yes",
        )

        self.ref = (
            ref
            or os.environ.get("VALIDATOR_PROFILEMANIFESTS_REF")
            or PROFILEMANIFESTS_REF
        )
        self.pinned = re.fullmatch(r"[0-9a-fA-F]{40}", self.ref) is not None
        if self.pinned:
            self.ref = self.ref.lower()  # git rev-parse output is lowercase
        self.repo_url = repo_url

        self.repo_dir = self.cache_dir / REPO_DIR_NAME
        self.manifests_dir = self.repo_dir / "Manifests"
        self.metadata_path = self.cache_dir / "cache.json"

    def ensure_cache(self) -> Path:
        """
        Ensure the cache exists and is up to date.

        Returns the path to the Manifests directory.

        Raises:
            RuntimeError: If cache doesn't exist and offline mode is enabled.
        """
        with self._lock():
            return self._ensure_cache()

    def _ensure_cache(self) -> Path:
        if not self.repo_dir.exists():
            if self.offline:
                raise RuntimeError(
                    f"ProfileManifests cache not found at {self.repo_dir} "
                    "and offline mode is enabled. Run with --update-cache first."
                )
            self._clone_repo()
        elif self.pinned:
            if self._head() != self.ref:
                if self.offline:
                    logger.warning(
                        f"ProfileManifests cache is at {self._head() or 'unknown'}, "
                        f"not the pinned {self.ref}; offline mode, using it anyway"
                    )
                else:
                    self._update_repo()
        elif self._is_stale() and not self.offline:
            self._update_repo()

        return self.manifests_dir

    def update(self, force: bool = False) -> bool:
        """
        Update the cache from remote.

        Args:
            force: If True, update even if cache is fresh.

        Returns:
            True if cache was updated, False if already up to date.
        """
        if self.offline:
            logger.warning("Offline mode enabled, skipping cache update")
            return False

        with self._lock():
            return self._update(force)

    def _update(self, force: bool) -> bool:
        if not self.repo_dir.exists():
            self._clone_repo()
            return True

        if self.pinned:
            return self._head() != self.ref and self._update_repo()

        if force or self._is_stale():
            return self._update_repo()

        return False

    def clear(self) -> None:
        """Remove all cached data."""
        import shutil

        if not self.cache_dir.exists():
            return

        # Safety check: only delete if path looks like our cache directory
        # Must be under user's home or contain 'mobileconfig-validator' in path
        resolved = self.cache_dir.resolve()
        home = Path.home().resolve()
        is_safe = (
            resolved.is_relative_to(home)
            and "mobileconfig-validator" in str(resolved)
        )

        if not is_safe:
            raise ValueError(
                f"Refusing to delete {resolved}: "
                "path must be under home directory and contain 'mobileconfig-validator'"
            )

        shutil.rmtree(self.cache_dir)
        logger.info(f"Cleared cache at {self.cache_dir}")

    def get_status(self) -> dict[str, Any]:
        """Get cache status information."""
        status: dict[str, Any] = {
            "cache_dir": str(self.cache_dir),
            "exists": self.repo_dir.exists(),
            "offline": self.offline,
            "max_age_days": self.max_age_days,
            "ref": self.ref,
            "pinned": self.pinned,
        }

        if self.repo_dir.exists():
            metadata = self._load_metadata()
            status["last_check"] = metadata.get("last_check")
            status["clone_created"] = metadata.get("clone_created")
            head = self._head()
            status["commit"] = head or "unknown"
            if self.pinned:
                status["at_ref"] = head == self.ref
            else:
                status["is_stale"] = self._is_stale()

            # Count manifests
            if self.manifests_dir.exists():
                manifest_count = sum(
                    1 for f in self.manifests_dir.rglob("*.plist") if f.is_file()
                )
                status["manifest_count"] = manifest_count

        return status

    @contextmanager
    def _lock(self) -> Iterator[None]:
        """
        Serialise cache creation and updates across processes.

        pre-commit runs a hook as parallel batches, so a cold cache is
        otherwise cloned by several processes into the same directory at once.
        """
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with open(self.cache_dir / ".lock", "w") as handle:
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_EX)
            yield

    def _git(self, *args: str) -> str:
        """Run a git command in the cached repository and return stdout."""
        result = subprocess.run(
            ["git", *args],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def _head(self) -> str | None:
        """Return the full commit checked out in the cache, if any."""
        try:
            return self._git("rev-parse", "--verify", "--quiet", "HEAD")
        except (subprocess.CalledProcessError, OSError):
            return None

    def _checkout_ref(self) -> bool:
        """
        Fetch self.ref (shallow, blobs on demand) and check it out detached.

        Returns:
            True if HEAD moved, False if it was already there.
        """
        self._git(
            "fetch", "--depth", "1", "--filter=blob:none", "origin", self.ref
        )
        target = self._git("rev-parse", "FETCH_HEAD")
        if target == self._head():
            return False
        self._git("checkout", "--quiet", "--detach", target)
        return True

    def _clone_repo(self) -> None:
        """Create a sparse clone of ProfileManifests at self.ref."""
        logger.info(f"Cloning ProfileManifests {self.ref} to {self.repo_dir}...")

        self.repo_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._git("init", "--quiet")
            self._git("remote", "add", "origin", self.repo_url)
            # Sparse checkout for the Manifests directory only
            self._git("sparse-checkout", "set", "Manifests")
            self._checkout_ref()
        except (subprocess.CalledProcessError, OSError):
            # Leave no half-built clone behind: ensure_cache treats an existing
            # repo_dir as a usable cache.
            import shutil

            shutil.rmtree(self.repo_dir, ignore_errors=True)
            raise

        now = datetime.now(UTC).isoformat() + "Z"
        self._save_metadata(
            {
                "cache_version": 2,
                "ref": self.ref,
                "clone_created": now,
                "last_check": now,
            }
        )

        logger.info("ProfileManifests cache created successfully")

    def _update_repo(self) -> bool:
        """
        Move the cache to self.ref, fetching it if necessary.

        Also migrates caches cloned by earlier versions, which tracked HEAD.

        Returns:
            True if updated, False if already up to date or the fetch failed.
        """
        logger.info(f"Checking ProfileManifests cache against {self.ref}...")

        try:
            updated = self._checkout_ref()
            logger.info(
                "ProfileManifests cache updated"
                if updated
                else "ProfileManifests cache is up to date"
            )
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to update cache: {e}")
            updated = False

        # Update last check time, even on failure to avoid hammering
        metadata = self._load_metadata()
        metadata["ref"] = self.ref
        metadata["last_check"] = datetime.now(UTC).isoformat() + "Z"
        self._save_metadata(metadata)

        return updated

    def _is_stale(self) -> bool:
        """Check if the cache is older than max_age_days."""
        metadata = self._load_metadata()
        last_check = metadata.get("last_check")

        if not last_check:
            return True

        try:
            # Parse ISO timestamp
            last_check_dt = datetime.fromisoformat(last_check.rstrip("Z"))
            age = datetime.now(UTC) - last_check_dt
            return age > timedelta(days=self.max_age_days)
        except (ValueError, TypeError):
            return True

    def _load_metadata(self) -> dict[str, Any]:
        """Load cache metadata from JSON file."""
        if not self.metadata_path.exists():
            return {}

        try:
            with open(self.metadata_path) as f:
                metadata: dict[str, Any] = json.load(f)
                return metadata
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_metadata(self, metadata: dict[str, Any]) -> None:
        """Save cache metadata to JSON file."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with open(self.metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
