"""Tests for output formatters."""

import json
from pathlib import Path

from mobileconfig_validator import Severity, ValidationResult
from mobileconfig_validator.formatter import (
    JSONFormatter,
    PlainTextFormatter,
    get_formatter,
)
from mobileconfig_validator.types import BatchResult, ValidationIssue


def make_result(
    file_path: str = "test.mobileconfig",
    is_valid: bool = True,
    payload_types: list[str] | None = None,
    issues: list[ValidationIssue] | None = None,
) -> ValidationResult:
    """Create a ValidationResult for testing."""
    result = ValidationResult(file_path=Path(file_path))
    result.payload_types = payload_types or []
    result.issues = issues or []
    return result


class TestPlainTextFormatter:
    """Tests for PlainTextFormatter."""

    def test_pass_output(self):
        """Valid result shows PASS."""
        formatter = PlainTextFormatter(color=False)
        result = make_result()
        output = formatter.format_result(result)
        assert "PASS" in output

    def test_fail_output(self):
        """Invalid result shows FAIL."""
        formatter = PlainTextFormatter(color=False)
        result = make_result(
            issues=[ValidationIssue(Severity.ERROR, "E001", "error", "path")]
        )
        output = formatter.format_result(result)
        assert "FAIL" in output

    def test_shows_error_code(self):
        """Error code is displayed."""
        formatter = PlainTextFormatter(color=False)
        result = make_result(
            issues=[ValidationIssue(Severity.ERROR, "E007", "invalid uuid", "path")]
        )
        output = formatter.format_result(result)
        assert "E007" in output

    def test_shows_payload_types(self):
        """Payload types are listed."""
        formatter = PlainTextFormatter(color=False)
        result = make_result(payload_types=["com.apple.dock"])
        output = formatter.format_result(result)
        assert "com.apple.dock" in output

    def test_quiet_mode_hides_warnings(self):
        """Quiet mode suppresses warnings."""
        formatter = PlainTextFormatter(color=False, quiet=True)
        result = make_result(
            issues=[
                ValidationIssue(Severity.ERROR, "E001", "error", "path"),
                ValidationIssue(Severity.WARNING, "W001", "warning", "path"),
            ]
        )
        output = formatter.format_result(result)
        assert "E001" in output
        assert "W001" not in output

    def test_summary_shows_counts(self):
        """Summary includes file and issue counts."""
        formatter = PlainTextFormatter(color=False)
        batch = BatchResult()
        batch.results = [
            make_result(issues=[ValidationIssue(Severity.ERROR, "E001", "err", "path")]),
            make_result(),
        ]
        output = formatter.format_summary(batch)
        assert "Files checked:" in output
        assert "2" in output


class TestJSONFormatter:
    """Tests for JSONFormatter."""

    def test_valid_json_output(self):
        """Output is valid JSON."""
        formatter = JSONFormatter()
        result = make_result()
        output = formatter.format_result(result)
        data = json.loads(output)
        assert "file_path" in data
        assert "is_valid" in data

    def test_batch_output(self):
        """Batch output includes results and summary."""
        formatter = JSONFormatter()
        batch = BatchResult()
        batch.results = [make_result(), make_result()]
        output = formatter.format_batch(batch)
        data = json.loads(output)
        assert "results" in data
        assert "summary" in data
        assert len(data["results"]) == 2

    def test_issues_serialized(self):
        """Issues are properly serialised."""
        formatter = JSONFormatter()
        result = make_result(
            issues=[
                ValidationIssue(
                    Severity.ERROR,
                    "E001",
                    "test error",
                    "test.path",
                    expected="foo",
                    actual="bar",
                )
            ]
        )
        output = formatter.format_result(result)
        data = json.loads(output)
        issue = data["issues"][0]
        assert issue["severity"] == "error"
        assert issue["code"] == "E001"
        assert issue["expected"] == "foo"
        assert issue["actual"] == "bar"

    def test_summary_fields(self):
        """Summary has all expected fields."""
        formatter = JSONFormatter()
        batch = BatchResult()
        batch.results = [
            make_result(issues=[ValidationIssue(Severity.ERROR, "E001", "err", "path")]),
        ]
        output = formatter.format_summary(batch)
        data = json.loads(output)
        assert "total_files" in data
        assert "valid_files" in data
        assert "invalid_files" in data
        assert "error_count" in data
        assert "is_valid" in data


class TestGetFormatter:
    """Tests for get_formatter factory."""

    def test_get_text_formatter(self):
        """'text' returns PlainTextFormatter."""
        formatter = get_formatter("text")
        assert isinstance(formatter, PlainTextFormatter)

    def test_get_json_formatter(self):
        """'json' returns JSONFormatter."""
        formatter = get_formatter("json")
        assert isinstance(formatter, JSONFormatter)

    def test_case_insensitive(self):
        """Format name is case insensitive."""
        formatter = get_formatter("JSON")
        assert isinstance(formatter, JSONFormatter)

    def test_invalid_format_raises(self):
        """Invalid format name raises ValueError."""
        try:
            get_formatter("xml")
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "xml" in str(e).lower()
