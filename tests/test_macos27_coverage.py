"""macOS profile changes from Apple's pinned Release-v27.0 CHANGES.md."""

import pytest

from mobileconfig_validator import api, validate_file, validate_files
from mobileconfig_validator.validator import SchemaValidator

from .test_validator import CompatibilityLoader, write_profile


@pytest.mark.parametrize("payload_type", [
    "com.apple.AssetCache.managed", "com.apple.applicationaccess.new",
    "com.apple.dnsProxy.managed", "com.apple.dnsSettings.managed",
    "com.apple.mobiledevice.passwordpolicy", "com.apple.relay.managed",
])
def test_deprecated_payload_boundaries(tmp_path, payload_type):
    path = write_profile(tmp_path, {"PayloadType": payload_type})
    for version in (None, "26.6", "27", "27.1"):
        issues = SchemaValidator(
            loader=CompatibilityLoader(), target_macos=version
        ).validate(path).issues
        assert any(i.code == "W004" for i in issues) == (version in ("27", "27.1"))
        assert not any(i.code == "E010" for i in issues)


@pytest.mark.parametrize("payload_type,key", [
    ("com.apple.applicationaccess", key) for key in (
        "allowRapidSecurityResponseInstallation", "allowRapidSecurityResponseRemoval",
        "enforcedSoftwareUpdateDelay", "enforcedSoftwareUpdateMajorOSDeferredInstallDelay",
        "enforcedSoftwareUpdateMinorOSDeferredInstallDelay",
        "enforcedSoftwareUpdateNonOSDeferredInstallDelay", "forceDelayedAppSoftwareUpdates",
        "forceDelayedMajorSoftwareUpdates", "forceDelayedSoftwareUpdates",
    )
] + [("com.apple.system.logging", "Processes")])
def test_removed_key_boundaries_and_paths(tmp_path, payload_type, key):
    value = {"example": {"arbitrary": True}} if key == "Processes" else (
        30 if key.startswith("enforced") else False
    )
    path = write_profile(tmp_path, {"PayloadType": payload_type, key: value})
    for version in (None, "26.6", "27", "27.1"):
        issues = SchemaValidator(
            loader=CompatibilityLoader(), target_macos=version
        ).validate(path).issues
        assert any(i.code == "W002" for i in issues) == (version is None)
        assert not any(i.code == "E003" for i in issues)
        removed = [i for i in issues if i.code == "E010"]
        assert bool(removed) == (version in ("27", "27.1"))
        if removed:
            assert removed[0].key_path == f"PayloadContent[0].{key}"
            assert removed[0].expected == "macOS earlier than 27.0"
    absent = write_profile(tmp_path, {"PayloadType": payload_type})
    assert not any(i.code == "E010" for i in SchemaValidator(
        loader=CompatibilityLoader(), target_macos="27"
    ).validate(absent).issues)


@pytest.mark.parametrize("key,value", [
    ("AllowWebLoginPasswordSync", False), ("WebLoginURLAllowList", []),
])
def test_new_platform_sso_keys(tmp_path, key, value):
    path = write_profile(tmp_path, {
        "PayloadType": "com.apple.extensiblesso", "PlatformSSO": {key: value},
    })
    for version in (None, "26.6", "27"):
        issues = SchemaValidator(
            loader=CompatibilityLoader(), target_macos=version
        ).validate(path).issues
        introduced = [i for i in issues if i.code == "W005"]
        assert bool(introduced) == (version == "26.6")
        if introduced:
            assert introduced[0].key_path == f"PayloadContent[0].PlatformSSO.{key}"
        if version is not None:
            assert not any(i.code == "W002" for i in issues)


@pytest.mark.parametrize("old_parent", [False, True])
def test_nested_overlay_retains_unknown_sibling_checks(tmp_path, old_parent):
    class Loader(CompatibilityLoader):
        def get_manifest(self, payload_type):
            return {"pfm_subkeys": [{
                "pfm_name": "PlatformSSO", "pfm_type": "dictionary",
                "pfm_subkeys": [{"pfm_name": "OldKey", "pfm_type": "boolean"}],
            }] if old_parent else []}

    path = write_profile(tmp_path, {
        "PayloadType": "com.apple.extensiblesso",
        "PlatformSSO": {"AllowWebLoginPasswordSync": True, "Unexpected": True},
        "Unrelated": True,
    })
    for version in (None, "26.6.1", "27"):
        issues = SchemaValidator(loader=Loader(), target_macos=version).validate(path).issues
        unknown = {i.key_path for i in issues if i.code == "W002"}
        assert "PayloadContent[0].Unrelated" in unknown
        if version is None:
            assert ("PayloadContent[0].PlatformSSO.AllowWebLoginPasswordSync" if old_parent
                    else "PayloadContent[0].PlatformSSO") in unknown
        else:
            assert unknown == {"PayloadContent[0].Unrelated",
                               "PayloadContent[0].PlatformSSO.Unexpected"}
        if version == "26.6.1":
            assert next(i.actual for i in issues if i.code == "W005") == "macOS 26.6.1"


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("version,removed", [(None, False), ("26.6", False), ("27", True)])
def test_public_api_forwards_target(tmp_path, monkeypatch, batch, version, removed):
    # Stub only the external manifest source; exercise the real public API and validator.
    monkeypatch.setattr(api, "ManifestLoader", lambda **kwargs: CompatibilityLoader())
    path = write_profile(tmp_path, {"PayloadType": "com.apple.SoftwareUpdate"})
    options = {"offline": True, "cache_dir": tmp_path / "cache", "target_macos": version}
    result = (validate_files([path], **options).results[0] if batch
              else validate_file(path, **options))
    assert any(i.code == "E010" for i in result.issues) == removed


@pytest.mark.parametrize("target", ["", "27-beta", "27.0.0.1"])
@pytest.mark.parametrize("batch", [False, True])
def test_public_api_rejects_invalid_target(tmp_path, batch, target):
    path = tmp_path / "unused.mobileconfig"
    with pytest.raises(ValueError, match="Invalid macOS version"):
        if batch:
            validate_files([path], offline=True, cache_dir=tmp_path, target_macos=target)
        else:
            validate_file(path, offline=True, cache_dir=tmp_path, target_macos=target)


@pytest.mark.parametrize("payload_type,key", [
    ("com.apple.loginwindow", "ForceWifiConfigurationOnLockScreen"),
    ("com.apple.loginwindow", "ForceCaptivePortalConnectionFromLockScreen"),
    ("com.apple.extensiblesso", "PlatformSSO.AllowWebLoginPasswordSync"),
])
@pytest.mark.parametrize("value", ["true", [], 42])
def test_introduced_booleans_reject_wrong_types(tmp_path, payload_type, key, value):
    payload = {"PayloadType": payload_type}
    if "." in key:
        parent, child = key.split(".")
        payload[parent] = {child: value}
    else:
        payload[key] = value
    path = write_profile(tmp_path, payload)
    result = SchemaValidator(loader=CompatibilityLoader(), target_macos="27").validate(path)
    assert any(i.code == "E003" and i.key_path.endswith(key) for i in result.issues)


@pytest.mark.parametrize("value,error_path", [
    ("example.com", "PlatformSSO.WebLoginURLAllowList"),
    ([1], "PlatformSSO.WebLoginURLAllowList[0]"),
    ([{}], "PlatformSSO.WebLoginURLAllowList[0]"),
    ([False], "PlatformSSO.WebLoginURLAllowList[0]"),
    (["example.com"], None),
    ([], None),
])
def test_introduced_sso_array_and_item_types(tmp_path, value, error_path):
    path = write_profile(tmp_path, {
        "PayloadType": "com.apple.extensiblesso", "PlatformSSO": {"WebLoginURLAllowList": value},
    })
    result = SchemaValidator(loader=CompatibilityLoader(), target_macos="27").validate(path)
    errors = [i for i in result.issues if i.code == "E003"]
    assert bool(errors) == (error_path is not None)
    if error_path:
        assert errors[0].key_path.endswith(error_path)


@pytest.mark.parametrize("payload_type,key", [
    ("com.apple.applicationaccess", "allowRapidSecurityResponseInstallation"),
    ("com.apple.applicationaccess", "enforcedSoftwareUpdateDelay"),
    ("com.apple.system.logging", "Processes"),
])
@pytest.mark.parametrize("version", ["26.6", "27"])
def test_historical_keys_retain_type_and_unknown_sibling_checks(
    tmp_path, payload_type, key, version,
):
    path = write_profile(tmp_path, {
        "PayloadType": payload_type, key: "invalid", "Unrelated": True,
    })
    issues = SchemaValidator(
        loader=CompatibilityLoader(), target_macos=version
    ).validate(path).issues
    assert {i.key_path for i in issues if i.code == "W002"} == {"PayloadContent[0].Unrelated"}
    assert {i.key_path for i in issues if i.code == "E003"} == {f"PayloadContent[0].{key}"}
    assert any(i.code == "E010" for i in issues) == (version == "27")
