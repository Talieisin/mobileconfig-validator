"""
Manifest loader for ProfileManifests.

Loads and parses plist manifests, providing lookup by PayloadType.
"""

import logging
import plistlib
from pathlib import Path
from typing import Dict, List, Optional

from .cache import ManifestCache

logger = logging.getLogger(__name__)


class ManifestLoader:
    """
    Loads ProfileManifests schemas on-demand.

    Categories covered:
    - ManifestsApple: Apple configuration profile payloads (com.apple.vpn.managed, etc.)
    - ManagedPreferencesApple: Apple app preferences (com.apple.Safari, etc.)
    - ManagedPreferencesApplications: 3rd party apps (com.microsoft.wdav, etc.)
    - ManagedPreferencesDeveloper: Developer tools
    """

    # Mapping of manifest categories to directories
    CATEGORIES = [
        "ManifestsApple",
        "ManagedPreferencesApple",
        "ManagedPreferencesApplications",
        "ManagedPreferencesDeveloper",
    ]

    def __init__(
        self,
        cache: Optional[ManifestCache] = None,
        offline: bool = False,
    ):
        """
        Initialize the manifest loader.

        Args:
            cache: ManifestCache instance. Created automatically if not provided.
            offline: If True, don't attempt network operations.
        """
        self.cache = cache or ManifestCache(offline=offline)
        self._index: Dict[str, dict] = {}  # domain -> {path, category, version, modified}
        self._manifests: Dict[str, dict] = {}  # domain -> parsed manifest (lazy loaded)
        self._index_loaded = False

    def load_index(self) -> None:
        """
        Parse the index file and build domain lookup.

        The index is a binary plist at Manifests/index containing:
        {
            "ManifestsApple": {
                "com.apple.dock": {"path": "...", "version": 1, "modified": "..."},
                ...
            },
            ...
        }
        """
        if self._index_loaded:
            return

        manifests_dir = self.cache.ensure_cache()
        index_path = manifests_dir / "index"

        if not index_path.exists():
            logger.warning(f"Index file not found at {index_path}")
            self._index_loaded = True
            return

        try:
            with open(index_path, "rb") as f:
                index_data = plistlib.load(f)
        except plistlib.InvalidFileException as e:
            logger.error(f"Failed to parse index file: {e}")
            self._index_loaded = True
            return

        # Flatten nested structure into single domain -> info mapping
        for category, domains in index_data.items():
            if category in ("date",):  # Skip metadata keys
                continue
            if not isinstance(domains, dict):
                continue

            for domain, info in domains.items():
                if isinstance(info, dict):
                    self._index[domain] = {
                        "path": info.get("path", ""),
                        "version": info.get("version"),
                        "modified": info.get("modified"),
                        "category": category,
                    }

        self._index_loaded = True
        logger.debug(f"Loaded index with {len(self._index)} domains")

    def get_manifest(self, payload_type: str) -> Optional[dict]:
        """
        Get manifest for a PayloadType.

        Args:
            payload_type: The PayloadType to look up (e.g., "com.apple.dock")

        Returns:
            The manifest dict, or None if not found.
        """
        self.load_index()

        # Check cache first
        if payload_type in self._manifests:
            return self._manifests[payload_type]

        # Look up in index
        info = self._index.get(payload_type)
        if not info:
            # Try case-insensitive match
            for domain in self._index:
                if domain.lower() == payload_type.lower():
                    info = self._index[domain]
                    break

        if not info:
            # Try platform-specific suffix variants (e.g., com.apple.applicationaccess → com.apple.applicationaccess-macOS)
            for suffix in ["-macOS", "-iOS", "-tvOS", ".macOS", ".iOS", ".tvOS"]:
                variant = f"{payload_type}{suffix}"
                if variant in self._index:
                    info = self._index[variant]
                    break

        if not info:
            return None

        # Load manifest from file
        manifest_path = self.cache.repo_dir / info["path"]
        if not manifest_path.exists():
            logger.warning(f"Manifest file not found: {manifest_path}")
            return None

        try:
            with open(manifest_path, "rb") as f:
                manifest = plistlib.load(f)
            self._manifests[payload_type] = manifest
            return manifest
        except plistlib.InvalidFileException as e:
            logger.error(f"Failed to parse manifest {manifest_path}: {e}")
            return None

    def get_manifest_version(self, payload_type: str) -> Optional[int]:
        """Get the version number for a manifest."""
        self.load_index()
        info = self._index.get(payload_type)
        return info.get("version") if info else None

    def get_all_domains(self) -> List[str]:
        """Get list of all known domains."""
        self.load_index()
        return list(self._index.keys())

    def has_manifest(self, payload_type: str) -> bool:
        """Check if a manifest exists for the given PayloadType."""
        self.load_index()
        if payload_type in self._index:
            return True
        # Case-insensitive check
        return any(d.lower() == payload_type.lower() for d in self._index)

    def get_subkey_definitions(self, manifest: dict) -> Dict[str, dict]:
        """
        Build a flat map of key names to their definitions from pfm_subkeys.

        Args:
            manifest: The manifest dict containing pfm_subkeys.

        Returns:
            Dict mapping key names to their pfm definitions.
        """
        result = {}
        subkeys = manifest.get("pfm_subkeys", [])
        self._extract_subkeys(subkeys, result)
        return result

    def _extract_subkeys(
        self,
        subkeys: list,
        result: Dict[str, dict],
        prefix: str = "",
    ) -> None:
        """
        Recursively extract subkey definitions.

        Args:
            subkeys: List of pfm_subkeys dicts.
            result: Dict to populate with key -> definition mappings.
            prefix: Path prefix for nested keys.
        """
        for subkey in subkeys:
            if not isinstance(subkey, dict):
                continue

            name = subkey.get("pfm_name")
            if not name:
                continue

            key_path = f"{prefix}.{name}" if prefix else name
            result[name] = subkey

            # Handle nested subkeys
            nested = subkey.get("pfm_subkeys", [])
            if nested:
                self._extract_subkeys(nested, result, key_path)

            # Handle array item subkeys
            item_subkeys = subkey.get("pfm_item_subkeys", [])
            if item_subkeys:
                self._extract_subkeys(item_subkeys, result, f"{key_path}[]")
