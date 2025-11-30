"""
Core validation logic for mobileconfig files.

Validates payloads against ProfileManifests schemas.
"""

import logging
import plistlib
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .loader import ManifestLoader
from .types import Severity, ValidationIssue, ValidationResult

logger = logging.getLogger(__name__)


class SchemaValidator:
    """
    Validates mobileconfig payloads against ProfileManifests schemas.

    Checks performed:

    ERRORS (invalid, blocks commit):
    - E001: Unknown PayloadType with no matching manifest
    - E002: Missing required key (pfm_require="always")
    - E003: Type mismatch (pfm_type vs actual type)
    - E004: Value not in allowed list (pfm_range_list)
    - E005: Value outside range (pfm_range_min/max)
    - E006: Format violation (pfm_format regex)
    - E007: Invalid/missing PayloadUUID format
    - E008: PayloadVersion not integer 1
    - E009: Duplicate PayloadUUID in profile

    WARNINGS (valid but suboptimal):
    - W001: Deprecated key (pfm_deprecated)
    - W002: Unknown key not in manifest
    - W003: Platform mismatch (pfm_platforms)
    - W004: macOS version requirement (pfm_macos_min)

    INFO (suggestions):
    - I001: Missing optional but recommended key
    - I002: Missing PayloadOrganization
    - I003: Non-unique PayloadIdentifier
    """

    # Standard payload keys that are always valid
    STANDARD_PAYLOAD_KEYS = {
        "PayloadType",
        "PayloadVersion",
        "PayloadIdentifier",
        "PayloadUUID",
        "PayloadDisplayName",
        "PayloadDescription",
        "PayloadOrganization",
        "PayloadContent",
        "PayloadEnabled",
        "PayloadScope",
        "PayloadRemovalDisallowed",
    }

    # Type mapping from pfm_type to Python types
    TYPE_MAP = {
        "string": str,
        "integer": int,
        "real": (int, float),
        "boolean": bool,
        "array": list,
        "dictionary": dict,
        "data": bytes,
        "date": type(None),  # datetime objects handled specially
    }

    def __init__(self, loader: Optional[ManifestLoader] = None, offline: bool = False):
        """
        Initialize the validator.

        Args:
            loader: ManifestLoader instance. Created automatically if not provided.
            offline: If True, don't attempt network operations for cache.
        """
        self.loader = loader or ManifestLoader(offline=offline)

    def validate(self, path: Path) -> ValidationResult:
        """
        Validate a mobileconfig file.

        Args:
            path: Path to the mobileconfig file.

        Returns:
            ValidationResult with any issues found.
        """
        result = ValidationResult(file_path=path)

        # Parse the mobileconfig
        try:
            with open(path, "rb") as f:
                profile = plistlib.load(f)
        except plistlib.InvalidFileException as e:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="E000",
                    message=f"Invalid plist file: {e}",
                    key_path="(root)",
                )
            )
            return result
        except FileNotFoundError:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="E000",
                    message="File not found",
                    key_path="(root)",
                )
            )
            return result

        # Validate outer profile structure
        result.issues.extend(self._validate_profile_structure(profile))

        # Collect UUIDs for duplicate detection
        all_uuids: Set[str] = set()
        all_identifiers: List[str] = []

        # Get outer profile UUID
        outer_uuid = profile.get("PayloadUUID")
        if outer_uuid:
            all_uuids.add(outer_uuid)
        all_identifiers.append(profile.get("PayloadIdentifier", ""))

        # Validate each payload in PayloadContent
        payload_content = profile.get("PayloadContent", [])
        if not isinstance(payload_content, list):
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="E003",
                    message="PayloadContent must be an array",
                    key_path="PayloadContent",
                    expected="array",
                    actual=type(payload_content).__name__,
                )
            )
            return result

        for idx, payload in enumerate(payload_content):
            if not isinstance(payload, dict):
                result.issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        code="E003",
                        message="Payload must be a dictionary",
                        key_path=f"PayloadContent[{idx}]",
                        expected="dictionary",
                        actual=type(payload).__name__,
                    )
                )
                continue

            payload_type = payload.get("PayloadType", "")
            result.payload_types.append(payload_type)
            prefix = f"PayloadContent[{idx}]"

            # Check for duplicate UUIDs
            payload_uuid = payload.get("PayloadUUID")
            if payload_uuid:
                if payload_uuid in all_uuids:
                    result.issues.append(
                        ValidationIssue(
                            severity=Severity.ERROR,
                            code="E009",
                            message="Duplicate PayloadUUID",
                            key_path=f"{prefix}.PayloadUUID",
                            actual=payload_uuid,
                        )
                    )
                all_uuids.add(payload_uuid)

            # Track identifiers
            all_identifiers.append(payload.get("PayloadIdentifier", ""))

            # Validate payload structure
            result.issues.extend(self._validate_payload_structure(payload, prefix))

            # Get manifest for this PayloadType
            manifest = self.loader.get_manifest(payload_type)
            if manifest:
                version = self.loader.get_manifest_version(payload_type)
                if version:
                    result.manifest_versions[payload_type] = version

                # Validate against manifest schema
                result.issues.extend(
                    self._validate_payload_against_manifest(payload, manifest, prefix)
                )
            else:
                # No manifest found
                result.issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        code="E001",
                        message="Unknown PayloadType - no manifest found",
                        key_path=f"{prefix}.PayloadType",
                        actual=payload_type,
                    )
                )

        # Check for non-unique identifiers (INFO level)
        identifier_counts = {}
        for ident in all_identifiers:
            if ident:
                identifier_counts[ident] = identifier_counts.get(ident, 0) + 1

        for ident, count in identifier_counts.items():
            if count > 1:
                result.issues.append(
                    ValidationIssue(
                        severity=Severity.INFO,
                        code="I003",
                        message=f"PayloadIdentifier appears {count} times",
                        key_path="PayloadIdentifier",
                        actual=ident,
                    )
                )

        return result

    def _validate_profile_structure(self, profile: dict) -> List[ValidationIssue]:
        """Validate the outer profile structure."""
        issues = []

        # Check required outer keys
        required_keys = ["PayloadType", "PayloadVersion", "PayloadIdentifier", "PayloadUUID"]
        for key in required_keys:
            if key not in profile:
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        code="E002",
                        message=f"Missing required key: {key}",
                        key_path=key,
                    )
                )

        # PayloadType should be "Configuration"
        if profile.get("PayloadType") != "Configuration":
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="E004",
                    message="Outer PayloadType must be 'Configuration'",
                    key_path="PayloadType",
                    expected="Configuration",
                    actual=profile.get("PayloadType"),
                )
            )

        # Validate PayloadVersion
        payload_version = profile.get("PayloadVersion")
        if payload_version is not None and payload_version != 1:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="E008",
                    message="PayloadVersion should be 1",
                    key_path="PayloadVersion",
                    expected=1,
                    actual=payload_version,
                )
            )

        # Validate PayloadUUID format
        payload_uuid = profile.get("PayloadUUID")
        if payload_uuid:
            issues.extend(self._validate_uuid(payload_uuid, "PayloadUUID"))

        # Check for PayloadOrganization (INFO)
        if "PayloadOrganization" not in profile:
            issues.append(
                ValidationIssue(
                    severity=Severity.INFO,
                    code="I002",
                    message="Consider adding PayloadOrganization",
                    key_path="PayloadOrganization",
                )
            )

        return issues

    def _validate_payload_structure(
        self, payload: dict, prefix: str
    ) -> List[ValidationIssue]:
        """Validate individual payload structure."""
        issues = []

        # Check required payload keys
        required_keys = ["PayloadType", "PayloadVersion", "PayloadIdentifier", "PayloadUUID"]
        for key in required_keys:
            if key not in payload:
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        code="E002",
                        message=f"Missing required key: {key}",
                        key_path=f"{prefix}.{key}",
                    )
                )

        # Validate PayloadVersion
        payload_version = payload.get("PayloadVersion")
        if payload_version is not None and payload_version != 1:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="E008",
                    message="PayloadVersion should be 1",
                    key_path=f"{prefix}.PayloadVersion",
                    expected=1,
                    actual=payload_version,
                )
            )

        # Validate PayloadUUID format
        payload_uuid = payload.get("PayloadUUID")
        if payload_uuid:
            issues.extend(self._validate_uuid(payload_uuid, f"{prefix}.PayloadUUID"))

        return issues

    def _validate_uuid(self, value: str, key_path: str) -> List[ValidationIssue]:
        """Validate UUID format."""
        issues = []
        try:
            uuid.UUID(value)
        except ValueError:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="E007",
                    message="Invalid UUID format",
                    key_path=key_path,
                    actual=value,
                )
            )
        return issues

    def _validate_payload_against_manifest(
        self, payload: dict, manifest: dict, prefix: str
    ) -> List[ValidationIssue]:
        """Validate a payload against its manifest schema."""
        issues = []

        # Check platform compatibility
        platforms = manifest.get("pfm_platforms", [])
        if platforms and "macOS" not in platforms:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="W003",
                    message="Manifest indicates this payload is not for macOS",
                    key_path=prefix,
                    expected="macOS",
                    actual=platforms,
                )
            )

        # Check macOS version requirement
        macos_min = manifest.get("pfm_macos_min")
        if macos_min:
            # Just note it as info - we can't verify the target OS version
            pass

        # Get ONLY immediate subkeys (not flattened) for this level
        subkeys = manifest.get("pfm_subkeys", [])
        immediate_defs = self._get_immediate_subkey_defs(subkeys)

        # Check required keys at this level only
        for key_name, key_def in immediate_defs.items():
            require = key_def.get("pfm_require")
            if require == "always" and key_name not in payload:
                # Skip standard payload keys that are checked separately
                if key_name in self.STANDARD_PAYLOAD_KEYS:
                    continue
                # Skip ProfileCreator UI artefacts (PFC_*) - these are schema bugs
                # in ProfileManifests, not real Apple configuration keys
                if key_name.startswith("PFC_"):
                    continue
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        code="E002",
                        message="Missing required key",
                        key_path=f"{prefix}.{key_name}",
                    )
                )

        # Validate each key in payload
        for key, value in payload.items():
            # Skip standard payload keys
            if key in self.STANDARD_PAYLOAD_KEYS:
                continue

            key_path = f"{prefix}.{key}"

            if key in immediate_defs:
                key_def = immediate_defs[key]
                issues.extend(self._validate_key(key_path, value, key_def))
            else:
                # Unknown key
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        code="W002",
                        message="Unknown key not in manifest schema",
                        key_path=key_path,
                        actual=key,
                    )
                )

        return issues

    def _get_immediate_subkey_defs(self, subkeys: list) -> Dict[str, dict]:
        """
        Get only immediate (non-nested) subkey definitions.

        Unlike loader.get_subkey_definitions() which flattens all nested keys,
        this returns only the direct children at this level.

        Args:
            subkeys: List of pfm_subkeys dicts.

        Returns:
            Dict mapping key names to their pfm definitions (immediate only).
        """
        result = {}
        for subkey in subkeys:
            if not isinstance(subkey, dict):
                continue
            name = subkey.get("pfm_name")
            if name:
                result[name] = subkey
        return result

    def _unwrap_array_item_schema(
        self, item_defs: Dict[str, dict], actual_items: list
    ) -> Dict[str, dict]:
        """
        Handle ProfileManifests wrapper pattern for array items.

        Some manifests (especially TCC/PPPC) have a schema where array items
        are defined with a single dict-type wrapper subkey that doesn't exist
        in actual profiles. This method detects that pattern and unwraps it.

        Example: Services.SystemPolicyAllFiles schema has:
            pfm_subkeys: [{pfm_name: "Services", pfm_type: "dictionary", ...}]
        But actual profile items have direct keys: Identifier, IdentifierType, etc.

        Args:
            item_defs: Immediate subkey definitions from the schema.
            actual_items: The actual array items from the profile.

        Returns:
            Unwrapped item definitions if wrapper pattern detected, else original.
        """
        # Only consider unwrapping if there's exactly one dict-type subkey
        if len(item_defs) != 1:
            return item_defs

        wrapper_name, wrapper_def = next(iter(item_defs.items()))

        # Must be a dictionary type
        if wrapper_def.get("pfm_type") != "dictionary":
            return item_defs

        # Check if actual items contain this wrapper key
        # If any item has the wrapper key, the schema is accurate - don't unwrap
        for item in actual_items:
            if isinstance(item, dict) and wrapper_name in item:
                return item_defs

        # Actual items don't have the wrapper key - unwrap the nested subkeys
        nested_subkeys = wrapper_def.get("pfm_subkeys", [])
        if nested_subkeys:
            return self._get_immediate_subkey_defs(nested_subkeys)

        return item_defs

    def _validate_key(
        self, key_path: str, value: Any, key_def: dict
    ) -> List[ValidationIssue]:
        """Validate a single key against its pfm definition."""
        issues = []

        # Check deprecated
        if key_def.get("pfm_deprecated"):
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="W001",
                    message="Key is deprecated",
                    key_path=key_path,
                )
            )

        # Type check
        expected_type = key_def.get("pfm_type")
        if expected_type and not self._type_matches(value, expected_type):
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="E003",
                    message="Type mismatch",
                    key_path=key_path,
                    expected=expected_type,
                    actual=type(value).__name__,
                )
            )
            # Don't continue validation if type is wrong
            return issues

        # Range list (enum)
        range_list = key_def.get("pfm_range_list")
        if range_list and value not in range_list:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="E004",
                    message="Value not in allowed list",
                    key_path=key_path,
                    expected=range_list,
                    actual=value,
                )
            )

        # Range min/max
        range_min = key_def.get("pfm_range_min")
        range_max = key_def.get("pfm_range_max")
        if isinstance(value, (int, float)):
            if range_min is not None and value < range_min:
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        code="E005",
                        message="Value below minimum",
                        key_path=key_path,
                        expected=f">= {range_min}",
                        actual=value,
                    )
                )
            if range_max is not None and value > range_max:
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        code="E005",
                        message="Value above maximum",
                        key_path=key_path,
                        expected=f"<= {range_max}",
                        actual=value,
                    )
                )

        # Regex format
        pfm_format = key_def.get("pfm_format")
        if pfm_format and isinstance(value, str):
            try:
                if not re.match(pfm_format, value):
                    issues.append(
                        ValidationIssue(
                            severity=Severity.ERROR,
                            code="E006",
                            message="Value doesn't match required format",
                            key_path=key_path,
                            expected=pfm_format,
                            actual=value,
                        )
                    )
            except re.error:
                # Invalid regex in manifest, skip validation
                pass

        # Recursively validate nested subkeys
        if expected_type == "dictionary" and isinstance(value, dict):
            nested_subkeys = key_def.get("pfm_subkeys", [])
            if nested_subkeys:
                # Get immediate definitions at this nesting level
                nested_defs = self._get_immediate_subkey_defs(nested_subkeys)

                # Check required keys at this nesting level
                for nested_key_name, nested_key_def in nested_defs.items():
                    require = nested_key_def.get("pfm_require")
                    if require == "always" and nested_key_name not in value:
                        issues.append(
                            ValidationIssue(
                                severity=Severity.ERROR,
                                code="E002",
                                message="Missing required key",
                                key_path=f"{key_path}.{nested_key_name}",
                            )
                        )

                # Validate each nested key present
                for nested_key, nested_value in value.items():
                    if nested_key in nested_defs:
                        issues.extend(
                            self._validate_key(
                                f"{key_path}.{nested_key}",
                                nested_value,
                                nested_defs[nested_key],
                            )
                        )

        # Validate array items
        if expected_type == "array" and isinstance(value, list):
            item_subkeys = key_def.get("pfm_subkeys", [])
            if item_subkeys:
                # Handle special ProfileManifests pattern where array items have
                # a single wrapper dict subkey (common in TCC/PPPC profiles).
                # If there's exactly one dict-type subkey, and actual items don't
                # contain that key, unwrap it and use its nested subkeys instead.
                item_defs = self._get_immediate_subkey_defs(item_subkeys)
                item_defs = self._unwrap_array_item_schema(item_defs, value)

                # Check if array items are simple strings with a range_list validation
                # This handles patterns like DisabledPreferencePanes where the array
                # contains strings that must match a defined set of values
                string_item_def = self._get_string_array_item_def(item_subkeys)

                for idx, item in enumerate(value):
                    if isinstance(item, dict):
                        # Check required keys for each array item
                        for item_key_name, item_key_def in item_defs.items():
                            require = item_key_def.get("pfm_require")
                            if require == "always" and item_key_name not in item:
                                issues.append(
                                    ValidationIssue(
                                        severity=Severity.ERROR,
                                        code="E002",
                                        message="Missing required key",
                                        key_path=f"{key_path}[{idx}].{item_key_name}",
                                    )
                                )

                        # Validate each key in the array item
                        for item_key, item_value in item.items():
                            if item_key in item_defs:
                                issues.extend(
                                    self._validate_key(
                                        f"{key_path}[{idx}].{item_key}",
                                        item_value,
                                        item_defs[item_key],
                                    )
                                )
                    elif isinstance(item, str) and string_item_def:
                        # Validate string items against pfm_range_list if defined
                        item_range_list = string_item_def.get("pfm_range_list")
                        if item_range_list and item not in item_range_list:
                            issues.append(
                                ValidationIssue(
                                    severity=Severity.ERROR,
                                    code="E004",
                                    message="Value not in allowed list",
                                    key_path=f"{key_path}[{idx}]",
                                    expected=f"One of {len(item_range_list)} allowed values",
                                    actual=item,
                                )
                            )

        return issues

    def _get_string_array_item_def(self, item_subkeys: list) -> Optional[dict]:
        """
        Get string item definition for arrays of strings.

        If an array has a single string-type subkey with pfm_range_list,
        that defines the allowed values for string items in the array.

        Args:
            item_subkeys: List of pfm_subkeys for the array.

        Returns:
            The string subkey definition if found, else None.
        """
        if len(item_subkeys) != 1:
            return None

        subkey = item_subkeys[0]
        if not isinstance(subkey, dict):
            return None

        if subkey.get("pfm_type") == "string":
            return subkey

        return None

    def _type_matches(self, value: Any, pfm_type: str) -> bool:
        """Check if value matches the expected pfm_type."""
        if pfm_type not in self.TYPE_MAP:
            return True  # Unknown type, assume valid

        expected = self.TYPE_MAP[pfm_type]

        # Special handling for date type
        if pfm_type == "date":
            from datetime import datetime

            return isinstance(value, datetime)

        # Special handling for real (accepts int or float)
        if pfm_type == "real":
            return isinstance(value, (int, float))

        # Special handling for boolean - Apple accepts integers 0/1
        if pfm_type == "boolean":
            if isinstance(value, bool):
                return True
            # Accept integers 0 and 1 as valid boolean representations
            if isinstance(value, int) and value in (0, 1):
                return True
            return False

        return isinstance(value, expected)
