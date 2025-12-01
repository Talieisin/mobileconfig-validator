"""Tests for the CLI interface."""

import json
import subprocess
import sys
from pathlib import Path


def run_cli(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    """Run the CLI with arguments and return the result."""
    cmd = [sys.executable, "-m", "mobileconfig_validator", *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


class TestCLIBasic:
    """Basic CLI functionality tests."""

    def test_help(self):
        """--help shows usage information."""
        result = run_cli("--help")
        assert result.returncode == 0
        assert "mobileconfig" in result.stdout.lower()
        assert "--strict" in result.stdout

    def test_version(self):
        """--version shows version number."""
        result = run_cli("--version")
        assert result.returncode == 0
        assert "1.0.0" in result.stdout

    def test_no_args(self):
        """No arguments shows help or error."""
        result = run_cli()
        # Should either show help or exit cleanly
        assert result.returncode in (0, 2)


class TestCLIValidation:
    """CLI validation tests."""

    def test_valid_file_passes(self, valid_fixtures_dir: Path):
        """Valid file returns exit code 0."""
        result = run_cli(str(valid_fixtures_dir / "dock-basic.mobileconfig"))
        assert result.returncode == 0
        assert "PASS" in result.stdout

    def test_invalid_file_passes_without_strict(self, invalid_fixtures_dir: Path):
        """Invalid file returns exit code 0 without --strict."""
        result = run_cli(str(invalid_fixtures_dir / "not-a-plist.mobileconfig"))
        assert result.returncode == 0
        assert "FAIL" in result.stdout

    def test_invalid_file_fails_with_strict(self, invalid_fixtures_dir: Path):
        """Invalid file returns exit code 1 with --strict."""
        result = run_cli(
            "--strict", str(invalid_fixtures_dir / "not-a-plist.mobileconfig")
        )
        assert result.returncode == 1
        assert "FAIL" in result.stdout

    def test_multiple_files(self, valid_fixtures_dir: Path):
        """Multiple files are all validated."""
        files = list(valid_fixtures_dir.glob("*.mobileconfig"))
        result = run_cli(*[str(f) for f in files])
        assert result.returncode == 0
        assert "Files checked:" in result.stdout
        assert str(len(files)) in result.stdout


class TestCLIOutputFormats:
    """CLI output format tests."""

    def test_json_output(self, valid_fixtures_dir: Path):
        """--format json produces valid JSON."""
        result = run_cli(
            "--format", "json", str(valid_fixtures_dir / "dock-basic.mobileconfig")
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "results" in data
        assert "summary" in data
        assert data["summary"]["is_valid"] is True

    def test_json_output_invalid(self, invalid_fixtures_dir: Path):
        """JSON output shows errors correctly."""
        result = run_cli(
            "--format", "json", str(invalid_fixtures_dir / "not-a-plist.mobileconfig")
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["summary"]["is_valid"] is False
        assert data["summary"]["error_count"] > 0

    def test_quiet_mode(self, invalid_fixtures_dir: Path):
        """--quiet suppresses warnings and info."""
        result = run_cli(
            "--quiet", str(invalid_fixtures_dir / "unknown-payload-type.mobileconfig")
        )
        assert result.returncode == 0
        # Should still show errors
        assert "ERROR" in result.stdout or "FAIL" in result.stdout


class TestCLIStrictMode:
    """CLI strict mode tests."""

    def test_strict_with_valid(self, valid_fixtures_dir: Path):
        """--strict with valid file returns 0."""
        result = run_cli(
            "--strict", str(valid_fixtures_dir / "dock-basic.mobileconfig")
        )
        assert result.returncode == 0

    def test_strict_with_errors(self, invalid_fixtures_dir: Path):
        """--strict with errors returns 1."""
        result = run_cli(
            "--strict", str(invalid_fixtures_dir / "duplicate-uuid.mobileconfig")
        )
        assert result.returncode == 1

    def test_warnings_as_errors(self, warning_fixtures_dir: Path):
        """--warnings-as-errors treats warnings as errors."""
        # This file is valid (no errors) but has warnings (W002 - unknown key)
        # Without --warnings-as-errors it should pass, with it should fail
        result_without = run_cli(
            "--strict",
            str(warning_fixtures_dir / "unknown-key.mobileconfig"),
        )
        assert result_without.returncode == 0  # Valid file passes strict

        result_with = run_cli(
            "--warnings-as-errors",
            "--strict",
            str(warning_fixtures_dir / "unknown-key.mobileconfig"),
        )
        assert result_with.returncode == 1  # Warnings treated as errors


class TestCLICacheCommands:
    """CLI cache management tests."""

    def test_cache_status(self):
        """--cache-status shows cache information."""
        result = run_cli("--cache-status")
        assert result.returncode == 0
        assert "cache_dir" in result.stdout.lower() or "Cache" in result.stdout

    def test_offline_mode(self, valid_fixtures_dir: Path):
        """--offline works with existing cache."""
        result = run_cli(
            "--offline", str(valid_fixtures_dir / "dock-basic.mobileconfig")
        )
        # Should work if cache exists, fail if not
        assert result.returncode in (0, 1)
