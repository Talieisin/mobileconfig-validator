"""
Type definitions for mobileconfig validation.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional


class Severity(Enum):
    """Validation issue severity levels."""
    ERROR = "error"      # Invalid, blocks commit
    WARNING = "warning"  # Valid but suboptimal
    INFO = "info"        # Suggestions


@dataclass
class ValidationIssue:
    """A single validation issue found in a mobileconfig."""
    severity: Severity
    code: str           # e.g., "E001", "W001", "I001"
    message: str
    key_path: str       # e.g., "PayloadContent[0].antivirusEngine.enforcementLevel"
    expected: Optional[Any] = None
    actual: Optional[Any] = None

    def __str__(self) -> str:
        parts = [f"[{self.code}] {self.key_path}: {self.message}"]
        if self.expected is not None:
            parts.append(f"  Expected: {self.expected}")
        if self.actual is not None:
            parts.append(f"  Got: {self.actual}")
        return "\n".join(parts)


@dataclass
class ValidationResult:
    """Result of validating a single mobileconfig file."""
    file_path: Path
    payload_types: List[str] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)
    manifest_versions: dict = field(default_factory=dict)  # payload_type -> version

    @property
    def is_valid(self) -> bool:
        """True if no errors found (warnings/info don't count)."""
        return not any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.INFO)


@dataclass
class BatchResult:
    """Result of validating multiple mobileconfig files."""
    results: List[ValidationResult] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.results)

    @property
    def valid_files(self) -> int:
        return sum(1 for r in self.results if r.is_valid)

    @property
    def invalid_files(self) -> int:
        return self.total_files - self.valid_files

    @property
    def error_count(self) -> int:
        return sum(r.error_count for r in self.results)

    @property
    def warning_count(self) -> int:
        return sum(r.warning_count for r in self.results)

    @property
    def info_count(self) -> int:
        return sum(r.info_count for r in self.results)

    @property
    def is_valid(self) -> bool:
        """True if all files are valid (no errors)."""
        return all(r.is_valid for r in self.results)
