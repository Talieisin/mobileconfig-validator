"""
ProfileManifests cache management using sparse git clone.

Handles fetching, updating, and managing the local cache of ProfileManifests
from https://github.com/ProfileManifests/ProfileManifests
"""

import json
import logging
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

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

# Cache staleness threshold (days)
DEFAULT_MAX_AGE_DAYS = 7


class ManifestCache:
    """
    Manages ProfileManifests repository cache using sparse git clone.

    Uses shallow sparse clone to download only the Manifests directory (~5MB).
    Change detection is handled by git fetch/pull.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        max_age_days: Optional[int] = None,
        offline: bool = False,
    ):
        """
        Initialize the manifest cache.

        Args:
            cache_dir: Directory to store the cache. Defaults to ~/.cache/mobileconfig-validator/
            max_age_days: Days before cache is considered stale. Defaults to 7.
                          Can be overridden with VALIDATOR_CACHE_MAX_AGE env var.
            offline: If True, never attempt network operations.
        """
        self.cache_dir = cache_dir or Path(
            os.environ.get("VALIDATOR_CACHE_DIR", str(DEFAULT_CACHE_DIR))
        )
        self.max_age_days = max_age_days or int(
            os.environ.get("VALIDATOR_CACHE_MAX_AGE", str(DEFAULT_MAX_AGE_DAYS))
        )
        self.offline = offline or os.environ.get("VALIDATOR_OFFLINE", "").lower() in (
            "1",
            "true",
            "yes",
        )

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
        if not self.repo_dir.exists():
            if self.offline:
                raise RuntimeError(
                    f"ProfileManifests cache not found at {self.repo_dir} "
                    "and offline mode is enabled. Run with --update-cache first."
                )
            self._clone_repo()
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

        if not self.repo_dir.exists():
            self._clone_repo()
            return True

        if force or self._is_stale():
            return self._update_repo()

        return False

    def clear(self) -> None:
        """Remove all cached data."""
        import shutil

        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            logger.info(f"Cleared cache at {self.cache_dir}")

    def get_status(self) -> dict:
        """Get cache status information."""
        status = {
            "cache_dir": str(self.cache_dir),
            "exists": self.repo_dir.exists(),
            "offline": self.offline,
            "max_age_days": self.max_age_days,
        }

        if self.repo_dir.exists():
            metadata = self._load_metadata()
            status["last_check"] = metadata.get("last_check")
            status["clone_created"] = metadata.get("clone_created")
            status["is_stale"] = self._is_stale()

            # Get commit info
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=self.repo_dir,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                status["commit"] = result.stdout.strip()
            except subprocess.CalledProcessError:
                status["commit"] = "unknown"

            # Count manifests
            if self.manifests_dir.exists():
                manifest_count = sum(
                    1 for f in self.manifests_dir.rglob("*.plist") if f.is_file()
                )
                status["manifest_count"] = manifest_count

        return status

    def _clone_repo(self) -> None:
        """Clone the ProfileManifests repository with sparse checkout."""
        logger.info(f"Cloning ProfileManifests to {self.repo_dir}...")

        # Create cache directory
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Shallow clone with blob filter (downloads tree but not blobs initially)
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--sparse",
                REPO_URL,
                str(self.repo_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        # Set up sparse checkout for Manifests directory only
        subprocess.run(
            ["git", "sparse-checkout", "set", "Manifests"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
            text=True,
        )

        # Save metadata
        self._save_metadata(
            {
                "cache_version": 1,
                "clone_created": datetime.utcnow().isoformat() + "Z",
                "last_check": datetime.utcnow().isoformat() + "Z",
            }
        )

        logger.info("ProfileManifests cache created successfully")

    def _update_repo(self) -> bool:
        """
        Update the repository if there are changes.

        Returns:
            True if updated, False if already up to date.
        """
        logger.info("Checking for ProfileManifests updates...")

        try:
            # Fetch latest (shallow)
            subprocess.run(
                ["git", "fetch", "--depth", "1"],
                cwd=self.repo_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            # Check if there are changes
            result = subprocess.run(
                ["git", "diff", "--quiet", "HEAD", "FETCH_HEAD"],
                cwd=self.repo_dir,
                capture_output=True,
            )

            if result.returncode != 0:
                # There are changes, pull them
                subprocess.run(
                    ["git", "pull", "--depth", "1"],
                    cwd=self.repo_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                logger.info("ProfileManifests cache updated")
                updated = True
            else:
                logger.info("ProfileManifests cache is up to date")
                updated = False

            # Update last check time
            metadata = self._load_metadata()
            metadata["last_check"] = datetime.utcnow().isoformat() + "Z"
            self._save_metadata(metadata)

            return updated

        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to update cache: {e}")
            # Update last check even on failure to avoid hammering
            metadata = self._load_metadata()
            metadata["last_check"] = datetime.utcnow().isoformat() + "Z"
            self._save_metadata(metadata)
            return False

    def _is_stale(self) -> bool:
        """Check if the cache is older than max_age_days."""
        metadata = self._load_metadata()
        last_check = metadata.get("last_check")

        if not last_check:
            return True

        try:
            # Parse ISO timestamp
            last_check_dt = datetime.fromisoformat(last_check.rstrip("Z"))
            age = datetime.utcnow() - last_check_dt
            return age > timedelta(days=self.max_age_days)
        except (ValueError, TypeError):
            return True

    def _load_metadata(self) -> dict:
        """Load cache metadata from JSON file."""
        if not self.metadata_path.exists():
            return {}

        try:
            with open(self.metadata_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_metadata(self, metadata: dict) -> None:
        """Save cache metadata to JSON file."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with open(self.metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
