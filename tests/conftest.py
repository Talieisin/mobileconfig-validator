"""
Pytest fixtures for mobileconfig-validator tests.
"""

import pytest
from pathlib import Path


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
