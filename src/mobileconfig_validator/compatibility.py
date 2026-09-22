"""Pinned Apple compatibility corrections not yet reliable in ProfileManifests."""

from typing import Any

# https://github.com/apple/device-management/commit/09f249a06e7e3289930bf6d05f38fb562f748ebf
APPLE_SCHEMA_RELEASE = "apple/device-management 09f249a06e7e3289930bf6d05f38fb562f748ebf"

MACOS_COMPATIBILITY: dict[str, dict[str, Any]] = {
    "com.apple.SoftwareUpdate": {
        "deprecated_in": "26.0",
        "removed_in": "27.0",
        "replacement": "com.apple.configuration.softwareupdate.settings",
    },
    "com.apple.mobiledevice.passwordpolicy": {
        "deprecated_in": "27.0",
        "replacement": "declarative passcode configuration",
    },
    "com.apple.TCC.configuration-profile-policy": {
        "deprecated_keys": {
            "Services.Accessibility": "27.0",
            "Services.BluetoothAlways": "27.0",
            "Services.Camera": "27.0",
            "Services.Microphone": "27.0",
            "Services.SpeechRecognition": "27.0",
        },
        "replacement": "com.apple.configuration.app.settings Privacy.PermissionDefaults",
    },
    "com.apple.loginwindow": {
        "introduced_keys": {
            "ForceWifiConfigurationOnLockScreen": "27.0",
            "ForceCaptivePortalConnectionFromLockScreen": "27.0",
        },
    },
}
