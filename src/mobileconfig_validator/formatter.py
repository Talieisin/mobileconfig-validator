"""
Output formatters for validation results.

Supports text (with ANSI colors) and JSON output formats.
"""

import json
import sys
from typing import List

from .types import BatchResult, Severity, ValidationIssue, ValidationResult


class BaseFormatter:
    """Base class for output formatters."""

    def format_result(self, result: ValidationResult) -> str:
        """Format a single validation result."""
        raise NotImplementedError

    def format_summary(self, batch: BatchResult) -> str:
        """Format batch validation summary."""
        raise NotImplementedError

    def format_batch(self, batch: BatchResult) -> str:
        """Format complete batch output."""
        parts = []
        for result in batch.results:
            parts.append(self.format_result(result))
        parts.append(self.format_summary(batch))
        return "\n".join(parts)


class PlainTextFormatter(BaseFormatter):
    """
    Formats validation results for terminal output.
    Uses ANSI colors when stdout is a TTY.
    """

    # ANSI colour codes
    COLORS = {
        Severity.ERROR: "\033[91m",    # Red
        Severity.WARNING: "\033[93m",  # Yellow
        Severity.INFO: "\033[94m",     # Blue
        "RESET": "\033[0m",
        "BOLD": "\033[1m",
        "DIM": "\033[2m",
        "GREEN": "\033[92m",
    }

    def __init__(self, color: bool = True, colour: bool = None, quiet: bool = False):
        """
        Initialise formatter.

        Args:
            color: Enable ANSI colours. Auto-detected if stdout is TTY.
            colour: Alias for color (British spelling).
            quiet: Only show errors, suppress warnings and info.
        """
        # Accept both spellings
        if colour is not None:
            color = colour
        self.color = color and sys.stdout.isatty()
        self.quiet = quiet

    def _c(self, code: str) -> str:
        """Get colour code if colours enabled."""
        if not self.color:
            return ""
        if isinstance(code, Severity):
            return self.COLORS.get(code, "")
        return self.COLORS.get(code, "")

    def format_result(self, result: ValidationResult) -> str:
        """Format a single file's validation result."""
        lines = []

        # Header with PASS/FAIL status
        if result.is_valid:
            status = f"{self._c('GREEN')}PASS{self._c('RESET')}"
        else:
            status = f"{self._c(Severity.ERROR)}FAIL{self._c('RESET')}"

        lines.append(f"{status} {result.file_path}")

        # Show payload types and manifest versions
        if result.payload_types:
            for payload_type in result.payload_types:
                version = result.manifest_versions.get(payload_type)
                if version:
                    lines.append(f"  Manifest: {payload_type} (v{version})")
                else:
                    lines.append(f"  Manifest: {payload_type}")

        # Group issues by severity
        for severity in [Severity.ERROR, Severity.WARNING, Severity.INFO]:
            if self.quiet and severity != Severity.ERROR:
                continue

            severity_issues = [i for i in result.issues if i.severity == severity]
            if not severity_issues:
                continue

            lines.append("")
            color = self._c(severity)
            lines.append(f"  {color}{severity.value.upper()}S ({len(severity_issues)}):{self._c('RESET')}")

            for issue in severity_issues:
                lines.append(self._format_issue(issue))

        lines.append("")  # Blank line between files
        return "\n".join(lines)

    def _format_issue(self, issue: ValidationIssue) -> str:
        """Format a single issue."""
        color = self._c(issue.severity)
        parts = [f"    {color}[{issue.code}]{self._c('RESET')} {issue.key_path}: {issue.message}"]

        if issue.expected is not None:
            expected_str = self._format_value(issue.expected)
            parts.append(f"           Expected: {expected_str}")

        if issue.actual is not None:
            actual_str = self._format_value(issue.actual)
            parts.append(f"           Got: {actual_str}")

        return "\n".join(parts)

    def _format_value(self, value) -> str:
        """Format a value for display, truncating if too long."""
        if isinstance(value, list) and len(value) > 5:
            return f"[{', '.join(repr(v) for v in value[:5])}, ...] ({len(value)} items)"
        return repr(value)

    def format_summary(self, batch: BatchResult) -> str:
        """Format batch validation summary."""
        lines = [
            "=" * 60,
            "VALIDATION SUMMARY",
            "=" * 60,
            f"Files checked:    {batch.total_files}",
            f"Valid:            {self._c('GREEN')}{batch.valid_files}{self._c('RESET')}",
        ]

        if batch.invalid_files > 0:
            lines.append(
                f"Invalid:          {self._c(Severity.ERROR)}{batch.invalid_files}{self._c('RESET')}"
            )

        lines.extend([
            "",
            "Issues found:",
            f"  Errors:         {self._c(Severity.ERROR)}{batch.error_count}{self._c('RESET')}",
        ])

        if not self.quiet:
            lines.extend([
                f"  Warnings:       {self._c(Severity.WARNING)}{batch.warning_count}{self._c('RESET')}",
                f"  Info:           {self._c(Severity.INFO)}{batch.info_count}{self._c('RESET')}",
            ])

        return "\n".join(lines)


class JSONFormatter(BaseFormatter):
    """Formats validation results as JSON for CI/CD integration."""

    def __init__(self, pretty: bool = True):
        """
        Initialize formatter.

        Args:
            pretty: Pretty-print JSON with indentation.
        """
        self.pretty = pretty

    def format_result(self, result: ValidationResult) -> str:
        """Format a single result as JSON."""
        return json.dumps(self._result_to_dict(result), indent=2 if self.pretty else None)

    def format_summary(self, batch: BatchResult) -> str:
        """Format summary as JSON."""
        return json.dumps(
            {
                "total_files": batch.total_files,
                "valid_files": batch.valid_files,
                "invalid_files": batch.invalid_files,
                "error_count": batch.error_count,
                "warning_count": batch.warning_count,
                "info_count": batch.info_count,
                "is_valid": batch.is_valid,
            },
            indent=2 if self.pretty else None,
        )

    def format_batch(self, batch: BatchResult) -> str:
        """Format complete batch as single JSON object."""
        return json.dumps(
            {
                "results": [self._result_to_dict(r) for r in batch.results],
                "summary": {
                    "total_files": batch.total_files,
                    "valid_files": batch.valid_files,
                    "invalid_files": batch.invalid_files,
                    "error_count": batch.error_count,
                    "warning_count": batch.warning_count,
                    "info_count": batch.info_count,
                    "is_valid": batch.is_valid,
                },
            },
            indent=2 if self.pretty else None,
        )

    def _result_to_dict(self, result: ValidationResult) -> dict:
        """Convert ValidationResult to dict for JSON serialisation."""
        return {
            "file_path": str(result.file_path),
            "is_valid": result.is_valid,
            "payload_types": result.payload_types,
            "manifest_versions": result.manifest_versions,
            "error_count": result.error_count,
            "warning_count": result.warning_count,
            "info_count": result.info_count,
            "issues": [self._issue_to_dict(i) for i in result.issues],
        }

    def _issue_to_dict(self, issue: ValidationIssue) -> dict:
        """Convert ValidationIssue to dict for JSON serialisation."""
        result = {
            "severity": issue.severity.value,
            "code": issue.code,
            "message": issue.message,
            "key_path": issue.key_path,
        }
        if issue.expected is not None:
            result["expected"] = self._serialize_value(issue.expected)
        if issue.actual is not None:
            result["actual"] = self._serialize_value(issue.actual)
        return result

    def _serialize_value(self, value) -> any:
        """Serialise value for JSON, handling non-JSON types."""
        if isinstance(value, bytes):
            return f"<{len(value)} bytes>"
        if isinstance(value, (list, tuple)):
            return [self._serialize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        return value


def get_formatter(format_name: str, **kwargs) -> BaseFormatter:
    """
    Get formatter by name.

    Args:
        format_name: "text" or "json"
        **kwargs: Additional arguments passed to formatter.

    Returns:
        Formatter instance.
    """
    formatters = {
        "text": PlainTextFormatter,
        "json": JSONFormatter,
    }

    formatter_class = formatters.get(format_name.lower())
    if not formatter_class:
        raise ValueError(f"Unknown format: {format_name}. Use 'text' or 'json'.")

    return formatter_class(**kwargs)
