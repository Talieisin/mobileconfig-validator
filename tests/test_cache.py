"""ProfileManifests cache pinning, against a local upstream repository."""

import logging
import subprocess
from pathlib import Path

import pytest

from mobileconfig_validator.cache import PROFILEMANIFESTS_REF, ManifestCache


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def upstream(tmp_path: Path) -> tuple[str, list[str]]:
    """A repository with three commits; returns (file URL, [old, ..., tip])."""
    repo = tmp_path / "upstream"
    repo.mkdir()
    git(repo, "init", "--quiet", "--initial-branch=master")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    # Allow shallow, filtered fetches of arbitrary commits, as GitHub does
    git(repo, "config", "uploadpack.allowFilter", "true")
    git(repo, "config", "uploadpack.allowAnySHA1InWant", "true")
    commits = []
    for n in range(3):
        (repo / "Manifests").mkdir(exist_ok=True)
        (repo / "Manifests" / "index").write_text(f"version {n}\n")
        (repo / "Other").mkdir(exist_ok=True)
        (repo / "Other" / "file").write_text("outside the sparse checkout\n")
        git(repo, "add", ".")
        git(repo, "commit", "--quiet", "-m", f"commit {n}")
        commits.append(git(repo, "rev-parse", "HEAD"))
    return repo.as_uri(), commits


def make_cache(tmp_path: Path, url: str, ref: str, **kwargs) -> ManifestCache:
    return ManifestCache(
        cache_dir=tmp_path / "cache", ref=ref, repo_url=url, **kwargs
    )


def index_text(cache: ManifestCache) -> str:
    return (cache.manifests_dir / "index").read_text()


def test_default_ref_is_a_full_commit(monkeypatch):
    monkeypatch.delenv("VALIDATOR_PROFILEMANIFESTS_REF", raising=False)
    cache = ManifestCache(cache_dir=Path("/nonexistent"))
    assert cache.ref == PROFILEMANIFESTS_REF
    assert cache.pinned


def test_environment_overrides_default_ref(monkeypatch):
    monkeypatch.setenv("VALIDATOR_PROFILEMANIFESTS_REF", "master")
    cache = ManifestCache(cache_dir=Path("/nonexistent"))
    assert cache.ref == "master"
    assert not cache.pinned


def test_clone_checks_out_pinned_commit_not_tip(tmp_path, upstream):
    url, commits = upstream
    cache = make_cache(tmp_path, url, commits[0])
    cache.ensure_cache()
    assert cache._head() == commits[0]
    assert index_text(cache) == "version 0\n"
    assert not (cache.repo_dir / "Other").exists()  # sparse
    status = cache.get_status()
    assert status["at_ref"] is True
    assert "is_stale" not in status


def test_existing_cache_moves_to_new_pin(tmp_path, upstream):
    """Covers caches from earlier versions, which tracked upstream HEAD."""
    url, commits = upstream
    make_cache(tmp_path, url, "master").ensure_cache()
    cache = make_cache(tmp_path, url, commits[1])
    assert cache.get_status()["at_ref"] is False
    cache.ensure_cache()
    assert cache._head() == commits[1]
    assert index_text(cache) == "version 1\n"


def test_pinned_cache_is_never_stale(tmp_path, upstream, monkeypatch):
    url, commits = upstream
    cache = make_cache(tmp_path, url, commits[0], max_age_days=0)
    cache.ensure_cache()
    fetched = []
    monkeypatch.setattr(cache, "_checkout_ref", lambda: fetched.append(1) or True)
    cache.ensure_cache()
    assert cache.update(force=True) is False
    assert not fetched


def test_offline_mismatch_warns_and_uses_cache(tmp_path, upstream, caplog):
    url, commits = upstream
    make_cache(tmp_path, url, commits[2]).ensure_cache()
    cache = make_cache(tmp_path, url, commits[0], offline=True)
    with caplog.at_level(logging.WARNING):
        cache.ensure_cache()
    assert cache._head() == commits[2]
    assert "offline mode" in caplog.text


def test_branch_ref_follows_upstream_on_update(tmp_path, upstream):
    url, commits = upstream
    cache = make_cache(tmp_path, url, "master")
    cache.ensure_cache()
    assert cache._head() == commits[2]
    upstream_dir = Path(url.removeprefix("file://"))
    (upstream_dir / "Manifests" / "index").write_text("version 3\n")
    git(upstream_dir, "commit", "--quiet", "-am", "commit 3")
    assert cache.update(force=True) is True
    assert index_text(cache) == "version 3\n"


def test_failed_clone_leaves_no_cache(tmp_path, upstream):
    url, _ = upstream
    cache = make_cache(tmp_path, url, "0" * 40)
    with pytest.raises(subprocess.CalledProcessError):
        cache.ensure_cache()
    assert not cache.repo_dir.exists()
