# Mobileconfig Validator

Validate Apple Configuration Profiles (.mobileconfig) against ProfileManifests schemas.

## Features

- Schema-based validation against [ProfileManifests](https://github.com/ProfileManifests/ProfileManifests)
- Automatic manifest cache management (sparse git clone)
- Multiple severity levels: errors, warnings, info
- CI-friendly with configurable exit codes
- JSON output format for tooling integration
- Pure Python (standard library only)

## Installation

### From PyPI

```bash
pip install mobileconfig-validator
```

### From Source

```bash
git clone https://github.com/Talieisin/mobileconfig-validator.git
cd mobileconfig-validator
pip install -e .
```

### Using pipx (Isolated)

```bash
pipx install mobileconfig-validator
```

## Quick Start

```bash
# Validate a single file
mobileconfig-validator profile.mobileconfig

# Or use the short alias
mcv profile.mobileconfig

# Validate multiple files
mobileconfig-validator *.mobileconfig

# Strict mode for CI (exits 1 on errors)
mobileconfig-validator --strict profile.mobileconfig

# JSON output for tooling
mobileconfig-validator --format json profile.mobileconfig
```

## Programmatic API

```python
from mobileconfig_validator import validate_file, validate_files, Severity

# Single file
result = validate_file("profile.mobileconfig")
print(f"Valid: {result.is_valid}")
for issue in result.issues:
    print(f"[{issue.severity.name}] {issue.code}: {issue.message}")

# Multiple files
batch = validate_files(["a.mobileconfig", "b.mobileconfig"])
print(f"Valid: {batch.valid_files}/{batch.total_files}")
```

## Validation Checks

### Errors (block deployment)

| Code | Description |
|------|-------------|
| E001 | Unknown PayloadType (no manifest found) |
| E002 | Missing required key (pfm_require="always") |
| E003 | Type mismatch (expected vs actual) |
| E004 | Value not in allowed list (pfm_range_list) |
| E005 | Value outside numeric range (pfm_range_min/max) |
| E006 | Format violation (regex pattern mismatch) |
| E007 | Invalid/missing PayloadUUID format |
| E008 | PayloadVersion not 1 |
| E009 | Duplicate PayloadUUID |

### Warnings (valid but suboptimal)

| Code | Description |
|------|-------------|
| W001 | Deprecated key |
| W002 | Unknown key not in schema |
| W003 | Platform mismatch (not macOS) |
| W004 | macOS version requirement noted |

### Info (suggestions)

| Code | Description |
|------|-------------|
| I001 | Missing optional recommended key |
| I002 | Missing PayloadOrganization |
| I003 | Non-unique PayloadIdentifier |

## CLI Options

```
usage: mobileconfig-validator [-h] [--strict] [--warnings-as-errors]
                              [--format {text,json}] [--quiet] [--no-colour]
                              [--update-cache] [--cache-status]
                              [--cache-dir PATH] [--offline] [--verbose]
                              [--version]
                              [files ...]

Options:
  --strict, -s          Exit with code 1 if any errors found (for CI)
  --warnings-as-errors  Treat warnings as errors
  --format {text,json}  Output format (default: text)
  --quiet, -q           Only show errors, suppress warnings and info
  --no-colour           Disable ANSI colour output
  --update-cache, -u    Force update ProfileManifests cache
  --cache-status        Show cache status and exit
  --cache-dir PATH      Custom cache directory
  --offline             Don't attempt network operations
  --verbose, -v         Enable verbose logging
  --version             Show version and exit
```

## Cache Management

The validator downloads ProfileManifests schemas on first run and caches them locally:

- **Default location**: `~/.cache/mobileconfig-validator/`
- **Environment variable**: `VALIDATOR_CACHE_DIR`
- **Staleness threshold**: 7 days (configurable via `VALIDATOR_CACHE_MAX_AGE`)

```bash
# Check cache status
mobileconfig-validator --cache-status

# Force update
mobileconfig-validator --update-cache

# Work offline (use existing cache)
mobileconfig-validator --offline profile.mobileconfig
```

## Pre-commit Integration

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: validate-mobileconfigs
        name: Validate mobileconfigs
        entry: mobileconfig-validator --strict
        language: python
        types: [file]
        files: \.mobileconfig$
```

## Contributing

This repository provides the standalone mobileconfig validation tool. For issues and contributions, please use the GitHub issue tracker.

## Licence

MIT

---

**Maintained By**: Talieisin IT Team
