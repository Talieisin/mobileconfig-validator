"""
Lightweight API for programmatic validation.

This module provides simple functions for validating mobileconfig files
without the overhead of CLI argument parsing.
"""

from pathlib import Path
from typing import Optional, Union

from .cache import ManifestCache
from .loader import ManifestLoader
from .types import BatchResult, ValidationResult
from .validator import SchemaValidator


def validate_file(
    path: Union[str, Path],
    offline: bool = False,
    cache_dir: Optional[Path] = None,
) -> ValidationResult:
    """
    Validate a single mobileconfig file.

    This is the recommended entry point for programmatic use.

    Args:
        path: Path to the mobileconfig file.
        offline: If True, don't attempt to update the manifest cache.
        cache_dir: Optional custom cache directory.

    Returns:
        ValidationResult with any issues found.

    Example:
        from mobileconfig_validator import validate_file

        result = validate_file("profile.mobileconfig")
        if not result.is_valid:
            for issue in result.issues:
                print(f"[{issue.code}] {issue.message}")
    """
    path = Path(path)
    cache = ManifestCache(cache_dir=cache_dir, offline=offline)
    loader = ManifestLoader(cache=cache, offline=offline)
    validator = SchemaValidator(loader=loader, offline=offline)
    return validator.validate(path)


def validate_files(
    paths: list[Union[str, Path]],
    offline: bool = False,
    cache_dir: Optional[Path] = None,
) -> BatchResult:
    """
    Validate multiple mobileconfig files.

    Shares the manifest cache across all validations for efficiency.

    Args:
        paths: List of paths to mobileconfig files.
        offline: If True, don't attempt to update the manifest cache.
        cache_dir: Optional custom cache directory.

    Returns:
        BatchResult containing all validation results.

    Example:
        from mobileconfig_validator import validate_files

        result = validate_files(["a.mobileconfig", "b.mobileconfig"])
        print(f"Valid: {result.valid_files}/{result.total_files}")
    """
    cache = ManifestCache(cache_dir=cache_dir, offline=offline)
    loader = ManifestLoader(cache=cache, offline=offline)
    validator = SchemaValidator(loader=loader, offline=offline)

    batch = BatchResult()
    for path in paths:
        batch.results.append(validator.validate(Path(path)))

    return batch


def update_cache(
    cache_dir: Optional[Path] = None,
    force: bool = False,
) -> bool:
    """
    Update the ProfileManifests cache.

    Args:
        cache_dir: Optional custom cache directory.
        force: If True, update even if cache is fresh.

    Returns:
        True if cache was updated, False if already up to date.
    """
    cache = ManifestCache(cache_dir=cache_dir)
    return cache.update(force=force)


def get_cache_status(cache_dir: Optional[Path] = None) -> dict:
    """
    Get information about the manifest cache.

    Args:
        cache_dir: Optional custom cache directory.

    Returns:
        Dict with cache status information.
    """
    cache = ManifestCache(cache_dir=cache_dir)
    return cache.get_status()
