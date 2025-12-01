"""
Mobileconfig Validator

Validates Apple Configuration Profiles (.mobileconfig) against ProfileManifests schemas.

Usage:
    mobileconfig-validator profile.mobileconfig
    mobileconfig-validator --strict apps/**/*.mobileconfig
"""

from .api import validate_file, validate_files
from .types import Severity, ValidationIssue, ValidationResult

__version__ = "1.0.0"
__all__ = [
    "validate_file",
    "validate_files",
    "ValidationResult",
    "ValidationIssue",
    "Severity",
]
