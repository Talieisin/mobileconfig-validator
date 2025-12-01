"""Pytest fixtures for mobileconfig-validator tests."""

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def valid_fixtures_dir(fixtures_dir: Path) -> Path:
    """Return the path to the valid fixtures directory."""
    return fixtures_dir / "valid"


@pytest.fixture
def invalid_fixtures_dir(fixtures_dir: Path) -> Path:
    """Return the path to the invalid fixtures directory."""
    return fixtures_dir / "invalid"


@pytest.fixture
def valid_fixture_files(valid_fixtures_dir: Path) -> list[Path]:
    """Return all valid fixture files."""
    return sorted(valid_fixtures_dir.glob("*.mobileconfig"))


@pytest.fixture
def invalid_fixture_files(invalid_fixtures_dir: Path) -> list[Path]:
    """Return all invalid fixture files."""
    return sorted(invalid_fixtures_dir.glob("*.mobileconfig"))


@pytest.fixture
def warning_fixtures_dir(fixtures_dir: Path) -> Path:
    """Return the path to the warning fixtures directory."""
    return fixtures_dir / "warning"
