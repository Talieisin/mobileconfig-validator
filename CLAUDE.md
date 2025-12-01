# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

```bash
# Set up venv and install dependencies (uses uv)
uv sync --all-extras

# Run linter
uv run ruff check src tests

# Run type checker (has known issues, CI allows failure)
uv run mypy src

# Run all tests with coverage
uv run pytest --cov=mobileconfig_validator --cov-report=xml

# Run a single test file
uv run pytest tests/test_something.py

# Run a specific test
uv run pytest tests/test_something.py::test_function_name -v

# Test CLI works
uv run mobileconfig-validator --help
```

## Architecture Overview

This is a pure Python validator for Apple Configuration Profiles (.mobileconfig) that validates against ProfileManifests schemas.

### Module Structure

- **`types.py`** - Core data types: `Severity` enum (ERROR/WARNING/INFO), `ValidationIssue`, `ValidationResult`, `BatchResult`
- **`validator.py`** - `SchemaValidator` class with all validation logic; checks payloads against pfm_* schema attributes
- **`loader.py`** - `ManifestLoader` class that loads ProfileManifests plists on-demand from the index
- **`cache.py`** - `ManifestCache` class managing sparse git clone of ProfileManifests repo
- **`api.py`** - Public API: `validate_file()`, `validate_files()`, `update_cache()`, `get_cache_status()`
- **`cli.py`** - CLI entry point with argument parsing
- **`formatter.py`** - Output formatting (text/JSON)

### Validation Flow

1. CLI/API receives file path(s)
2. `ManifestCache.ensure_cache()` ensures ProfileManifests repo is cloned (sparse, ~5MB)
3. `ManifestLoader.load_index()` parses the binary plist index file
4. For each payload in the mobileconfig:
   - `ManifestLoader.get_manifest()` looks up schema by PayloadType
   - `SchemaValidator._validate_payload_against_manifest()` validates against pfm_* attributes
5. Issues are collected with severity codes (E000-E009, W001-W003, I002-I003)

### Key Design Decisions

- **Pure stdlib**: No runtime dependencies - uses only Python standard library (plistlib, subprocess, etc.)
- **Sparse git clone**: Downloads only Manifests directory to minimise disc usage (requires `git` in PATH)
- **Lazy loading**: Manifests are loaded on-demand and cached in memory
- **ProfileManifests schema format**: Uses pfm_* attributes (pfm_type, pfm_require, pfm_range_list, pfm_subkeys, etc.)

## Cache Management

```bash
# Check cache status
uv run mobileconfig-validator --cache-status

# Force update from ProfileManifests repo
uv run mobileconfig-validator --update-cache

# Clear cache completely
uv run mobileconfig-validator --clear-cache
```

## Test Structure

Test fixtures in `tests/fixtures/`:
- `valid/` - profiles that should pass validation
- `invalid/` - profiles with specific errors (E000-E009)
- `warning/` - profiles that pass but have warnings (W001-W003)
