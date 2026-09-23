"""Pinned Apple compatibility corrections not yet reliable in ProfileManifests."""

from typing import Any

# https://github.com/apple/device-management/commit/09f249a06e7e3289930bf6d05f38fb562f748ebf
APPLE_SCHEMA_RELEASE = "apple/device-management 09f249a06e7e3289930bf6d05f38fb562f748ebf"

# macOS profile changes in Release-v27.0, including keys retained in the
# YAML with removed metadata and Processes, deleted and recorded in CHANGES.md.
SOFTWARE_UPDATE_RESTRICTION_KEYS = (
    "allowRapidSecurityResponseInstallation",
    "allowRapidSecurityResponseRemoval",
    "enforcedSoftwareUpdateDelay",
    "enforcedSoftwareUpdateMajorOSDeferredInstallDelay",
    "enforcedSoftwareUpdateMinorOSDeferredInstallDelay",
    "enforcedSoftwareUpdateNonOSDeferredInstallDelay",
    "forceDelayedAppSoftwareUpdates",
    "forceDelayedMajorSoftwareUpdates",
    "forceDelayedSoftwareUpdates",
)

MACOS_COMPATIBILITY: dict[str, dict[str, Any]] = {
    "com.apple.AssetCache.managed": {
        "deprecated_in": "27.0",
        "replacement": "com.apple.configuration.content-cache.settings",
    },
    "com.apple.applicationaccess.new": {"deprecated_in": "27.0"},
    "com.apple.dnsProxy.managed": {
        "deprecated_in": "27.0",
        "replacement": "com.apple.configuration.network.dns-proxy",
    },
    "com.apple.dnsSettings.managed": {
        "deprecated_in": "27.0",
        "replacement": "com.apple.configuration.network.dns-settings",
    },
    "com.apple.relay.managed": {
        "deprecated_in": "27.0",
        "replacement": "com.apple.configuration.network.relay",
    },
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
        "introduced_key_schema": {
            "ForceWifiConfigurationOnLockScreen": {"pfm_type": "boolean"},
            "ForceCaptivePortalConnectionFromLockScreen": {"pfm_type": "boolean"},
        },
    },
    "com.apple.applicationaccess": {
        "deprecated_keys": dict.fromkeys(SOFTWARE_UPDATE_RESTRICTION_KEYS, "26.0"),
        "removed_keys": dict.fromkeys(SOFTWARE_UPDATE_RESTRICTION_KEYS, "27.0"),
        "replacement": "com.apple.configuration.softwareupdate.settings",
    },
    "com.apple.system.logging": {"removed_keys": {"Processes": "27.0"}},
    "com.apple.extensiblesso": {
        "introduced_keys": {
            "PlatformSSO.AllowWebLoginPasswordSync": "27.0",
            "PlatformSSO.WebLoginURLAllowList": "27.0",
        },
        "introduced_key_schema": {
            "PlatformSSO.AllowWebLoginPasswordSync": {"pfm_type": "boolean"},
            "PlatformSSO.WebLoginURLAllowList": {
                "pfm_type": "array",
                "pfm_subkeys": [{"pfm_name": "Hosts", "pfm_type": "string"}],
            },
        },
    },
}
