"""
Command-line interface for mobileconfig validation.

Usage:
    mobileconfig-validator profile.mobileconfig
    mobileconfig-validator --strict apps/**/*.mobileconfig
"""

import argparse
import glob
import logging
import sys
from pathlib import Path

from .api import get_cache_status, update_cache, validate_files
from .formatter import get_formatter

# Set up logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def expand_paths(paths: list[str]) -> list[Path]:
    """Expand glob patterns and ~ to list of files."""
    files = []
    for pattern in paths:
        # Expand ~ to home directory
        expanded_pattern = Path(pattern).expanduser()
        pattern_str = str(expanded_pattern)

        # Expand glob patterns
        if "*" in pattern_str or "?" in pattern_str:
            expanded = glob.glob(pattern_str, recursive=True)
            files.extend(Path(f) for f in expanded)
        else:
            files.append(expanded_pattern)

    # Filter to existing files with .mobileconfig extension (case-insensitive)
    return [f for f in files if f.exists() and f.suffix.lower() == ".mobileconfig"]


def main(args: list[str] = None) -> int:
    """
    Main entry point for CLI.

    Args:
        args: Command-line arguments. Uses sys.argv if None.

    Returns:
        Exit code: 0 for success, 1 for validation errors, 2 for other errors.
    """
    parser = argparse.ArgumentParser(
        prog="mobileconfig-validator",
        description="Validate mobileconfig files against ProfileManifests schemas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s profile.mobileconfig              Validate single file
  %(prog)s apps/**/*.mobileconfig            Validate multiple files
  %(prog)s --strict apps/**/*.mobileconfig   Fail on errors (for CI)
  %(prog)s --update-cache                    Force cache update
  %(prog)s --cache-status                    Show cache info
        """,
    )

    parser.add_argument(
        "files",
        nargs="*",
        help="Mobileconfig files to validate (supports glob patterns)",
    )

    parser.add_argument(
        "--strict",
        "-s",
        action="store_true",
        help="Exit with code 1 if any errors found (for pre-commit/CI)",
    )

    parser.add_argument(
        "--warnings-as-errors",
        "-W",
        action="store_true",
        help="Treat warnings as errors",
    )

    parser.add_argument(
        "--format",
        "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only show errors, suppress warnings and info",
    )

    parser.add_argument(
        "--no-colour",
        action="store_true",
        help="Disable ANSI colour output",
    )

    parser.add_argument(
        "--update-cache",
        "-u",
        action="store_true",
        help="Force update ProfileManifests cache",
    )

    parser.add_argument(
        "--cache-status",
        action="store_true",
        help="Show cache status and exit",
    )

    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear ProfileManifests cache and exit",
    )

    parser.add_argument(
        "--cache-dir",
        type=Path,
        help="Custom cache directory",
    )

    parser.add_argument(
        "--offline",
        action="store_true",
        help="Don't attempt network operations",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )

    parsed = parser.parse_args(args)

    # Set log level
    if parsed.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Handle cache status
    if parsed.cache_status:
        status = get_cache_status(cache_dir=parsed.cache_dir)
        print("ProfileManifests Cache Status")
        print("=" * 40)
        for key, value in status.items():
            print(f"  {key}: {value}")
        return 0

    # Handle cache clear
    if parsed.clear_cache:
        from .cache import ManifestCache

        cache = ManifestCache(cache_dir=parsed.cache_dir)
        try:
            cache.clear()
            print("Cache cleared successfully")
        except ValueError as e:
            print(f"Error clearing cache: {e}", file=sys.stderr)
            return 2
        return 0

    # Handle cache update
    if parsed.update_cache:
        print("Updating ProfileManifests cache...")
        try:
            updated = update_cache(cache_dir=parsed.cache_dir, force=True)
            if updated:
                print("Cache updated successfully")
            else:
                print("Cache is already up to date")
        except Exception as e:
            print(f"Error updating cache: {e}", file=sys.stderr)
            return 2

        # If no files specified, just update cache and exit
        if not parsed.files:
            return 0

    # Expand file paths
    files = expand_paths(parsed.files)

    # Handle no files
    if not files:
        if parsed.files:
            # User specified paths but none resolved - this is an error
            print("No mobileconfig files found", file=sys.stderr)
            return 2
        # No files specified at all - show help or exit cleanly
        return 0

    # Validate files
    try:
        result = validate_files(
            files,
            offline=parsed.offline,
            cache_dir=parsed.cache_dir,
        )
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        logger.exception("Unexpected error during validation")
        print(f"Error: {e}", file=sys.stderr)
        return 2

    # Format output
    formatter_kwargs = {}
    if parsed.format == "text":
        formatter_kwargs["colour"] = not parsed.no_colour
        formatter_kwargs["quiet"] = parsed.quiet

    formatter = get_formatter(parsed.format, **formatter_kwargs)
    print(formatter.format_batch(result))

    # Determine exit code
    if parsed.strict:
        if result.error_count > 0:
            return 1
        if parsed.warnings_as_errors and result.warning_count > 0:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
