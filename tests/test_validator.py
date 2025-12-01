"""Tests for the mobileconfig validator."""

from pathlib import Path

from mobileconfig_validator import Severity, ValidationResult, validate_file, validate_files
from mobileconfig_validator.types import ValidationIssue


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_is_valid_with_no_issues(self):
        result = ValidationResult(file_path=Path("test.mobileconfig"))
        assert result.is_valid is True

    def test_is_valid_with_warning(self):
        result = ValidationResult(file_path=Path("test.mobileconfig"))
        result.issues.append(
            ValidationIssue(
                severity=Severity.WARNING,
                code="W001",
                message="Test warning",
                key_path="test",
            )
        )
        assert result.is_valid is True  # Warnings don't make it invalid

    def test_is_valid_with_error(self):
        result = ValidationResult(file_path=Path("test.mobileconfig"))
        result.issues.append(
            ValidationIssue(
                severity=Severity.ERROR,
                code="E001",
                message="Test error",
                key_path="test",
            )
        )
        assert result.is_valid is False

    def test_counts(self):
        result = ValidationResult(file_path=Path("test.mobileconfig"))
        result.issues = [
            ValidationIssue(Severity.ERROR, "E001", "err1", "path"),
            ValidationIssue(Severity.ERROR, "E002", "err2", "path"),
            ValidationIssue(Severity.WARNING, "W001", "warn1", "path"),
            ValidationIssue(Severity.INFO, "I001", "info1", "path"),
        ]
        assert result.error_count == 2
        assert result.warning_count == 1
        assert result.info_count == 1


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_values(self):
        assert Severity.ERROR.value == "error"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"


class TestValidFixtures:
    """Tests using valid fixture files."""

    def test_all_valid_fixtures_pass(self, valid_fixture_files: list[Path]):
        """All files in valid/ should pass validation."""
        assert len(valid_fixture_files) > 0, "No valid fixtures found"
        for path in valid_fixture_files:
            result = validate_file(path)
            assert result.is_valid, f"{path.name} should be valid but had errors: {result.issues}"
            assert result.error_count == 0

    def test_dock_basic(self, valid_fixtures_dir: Path):
        """Basic dock profile validates correctly."""
        result = validate_file(valid_fixtures_dir / "dock-basic.mobileconfig")
        assert result.is_valid
        assert "com.apple.dock" in result.payload_types

    def test_multiple_payloads(self, valid_fixtures_dir: Path):
        """Profile with multiple payloads validates correctly."""
        result = validate_file(valid_fixtures_dir / "multiple-payloads.mobileconfig")
        assert result.is_valid
        assert len(result.payload_types) == 2
        assert "com.apple.dock" in result.payload_types
        assert "com.apple.finder" in result.payload_types

    def test_screensaver(self, valid_fixtures_dir: Path):
        """Screensaver profile validates correctly."""
        result = validate_file(valid_fixtures_dir / "screensaver.mobileconfig")
        assert result.is_valid
        assert "com.apple.screensaver" in result.payload_types


class TestInvalidFixtures:
    """Tests using invalid fixture files."""

    def test_all_invalid_fixtures_fail(self, invalid_fixture_files: list[Path]):
        """All files in invalid/ should fail validation."""
        assert len(invalid_fixture_files) > 0, "No invalid fixtures found"
        for path in invalid_fixture_files:
            result = validate_file(path)
            assert not result.is_valid, f"{path.name} should be invalid but passed"
            assert result.error_count > 0

    def test_missing_payload_uuid(self, invalid_fixtures_dir: Path):
        """Missing PayloadUUID triggers E002."""
        result = validate_file(invalid_fixtures_dir / "missing-payload-uuid.mobileconfig")
        assert not result.is_valid
        error_codes = {i.code for i in result.issues if i.severity == Severity.ERROR}
        assert "E002" in error_codes

    def test_invalid_uuid_format(self, invalid_fixtures_dir: Path):
        """Invalid UUID format triggers E007."""
        result = validate_file(invalid_fixtures_dir / "invalid-uuid-format.mobileconfig")
        assert not result.is_valid
        error_codes = {i.code for i in result.issues if i.severity == Severity.ERROR}
        assert "E007" in error_codes

    def test_duplicate_uuid(self, invalid_fixtures_dir: Path):
        """Duplicate UUIDs trigger E009."""
        result = validate_file(invalid_fixtures_dir / "duplicate-uuid.mobileconfig")
        assert not result.is_valid
        error_codes = {i.code for i in result.issues if i.severity == Severity.ERROR}
        assert "E009" in error_codes

    def test_unknown_payload_type(self, invalid_fixtures_dir: Path):
        """Unknown PayloadType triggers E001."""
        result = validate_file(invalid_fixtures_dir / "unknown-payload-type.mobileconfig")
        assert not result.is_valid
        error_codes = {i.code for i in result.issues if i.severity == Severity.ERROR}
        assert "E001" in error_codes

    def test_wrong_outer_type(self, invalid_fixtures_dir: Path):
        """Wrong outer PayloadType triggers E004."""
        result = validate_file(invalid_fixtures_dir / "wrong-outer-type.mobileconfig")
        assert not result.is_valid
        error_codes = {i.code for i in result.issues if i.severity == Severity.ERROR}
        assert "E004" in error_codes

    def test_not_a_plist(self, invalid_fixtures_dir: Path):
        """Non-plist file triggers E000."""
        result = validate_file(invalid_fixtures_dir / "not-a-plist.mobileconfig")
        assert not result.is_valid
        error_codes = {i.code for i in result.issues if i.severity == Severity.ERROR}
        assert "E000" in error_codes

    def test_wrong_payload_version(self, invalid_fixtures_dir: Path):
        """PayloadVersion != 1 triggers E008."""
        result = validate_file(invalid_fixtures_dir / "wrong-payload-version.mobileconfig")
        assert not result.is_valid
        error_codes = {i.code for i in result.issues if i.severity == Severity.ERROR}
        assert "E008" in error_codes


class TestValidateFiles:
    """Tests for batch validation."""

    def test_validate_multiple_files(self, valid_fixture_files: list[Path]):
        """validate_files processes multiple files."""
        batch = validate_files(valid_fixture_files)
        assert batch.total_files == len(valid_fixture_files)
        assert batch.valid_files == len(valid_fixture_files)
        assert batch.invalid_files == 0
        assert batch.is_valid

    def test_batch_with_mixed_results(
        self, valid_fixtures_dir: Path, invalid_fixtures_dir: Path
    ):
        """Batch with valid and invalid files reports correctly."""
        files = [
            valid_fixtures_dir / "dock-basic.mobileconfig",
            invalid_fixtures_dir / "not-a-plist.mobileconfig",
        ]
        batch = validate_files(files)
        assert batch.total_files == 2
        assert batch.valid_files == 1
        assert batch.invalid_files == 1
        assert not batch.is_valid


class TestFileNotFound:
    """Tests for missing file handling."""

    def test_nonexistent_file(self, tmp_path: Path):
        """Nonexistent file returns E000 error."""
        result = validate_file(tmp_path / "does-not-exist.mobileconfig")
        assert not result.is_valid
        error_codes = {i.code for i in result.issues if i.severity == Severity.ERROR}
        assert "E000" in error_codes


class TestWarningFixtures:
    """Tests using warning fixture files."""

    def test_unknown_key_triggers_warning(self, warning_fixtures_dir: Path):
        """Unknown key in payload triggers W002 warning."""
        result = validate_file(warning_fixtures_dir / "unknown-key.mobileconfig")
        # File is still valid (no errors)
        assert result.is_valid
        # But should have a warning
        warning_codes = {i.code for i in result.issues if i.severity == Severity.WARNING}
        assert "W002" in warning_codes
