"""Tests for release version consistency checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_release_version import ReleaseVersionError, validate_versions


def test_validate_versions_accepts_matching_release(tmp_path: Path) -> None:
    """Matching metadata and tag values should return the release version."""
    _write_release_files(tmp_path, "0.2.1", "0.2.1", "0.2.1")

    assert validate_versions(tmp_path, ref_type="tag", ref_name="v0.2.1") == "0.2.1"


@pytest.mark.parametrize(
    ("manifest_version", "project_version", "lock_version"),
    [
        ("0.2.0", "0.2.1", "0.2.1"),
        ("0.2.1", "0.2.0", "0.2.1"),
        ("0.2.1", "0.2.1", "0.2.0"),
    ],
)
def test_validate_versions_rejects_metadata_mismatch(
    tmp_path: Path,
    manifest_version: str,
    project_version: str,
    lock_version: str,
) -> None:
    """Every release metadata source must agree."""
    _write_release_files(
        tmp_path,
        manifest_version,
        project_version,
        lock_version,
    )

    with pytest.raises(ReleaseVersionError, match="Version mismatch"):
        validate_versions(tmp_path)


def test_validate_versions_rejects_wrong_tag(tmp_path: Path) -> None:
    """A release tag must exactly match the validated version."""
    _write_release_files(tmp_path, "0.2.1", "0.2.1", "0.2.1")

    with pytest.raises(ReleaseVersionError, match=r"Tag v0\.2\.2 does not match"):
        validate_versions(tmp_path, ref_type="tag", ref_name="v0.2.2")


def test_validate_versions_rejects_non_release_version(tmp_path: Path) -> None:
    """Release metadata must use the supported numeric SemVer form."""
    _write_release_files(tmp_path, "0.2", "0.2", "0.2")

    with pytest.raises(ReleaseVersionError, match="numeric semantic version"):
        validate_versions(tmp_path)


def test_validate_versions_requires_root_lock_record(tmp_path: Path) -> None:
    """The lockfile must contain the virtual root project record."""
    _write_release_files(tmp_path, "0.2.1", "0.2.1", None)

    with pytest.raises(ReleaseVersionError, match="root project record"):
        validate_versions(tmp_path)


def _write_release_files(
    root: Path,
    manifest_version: str,
    project_version: str,
    lock_version: str | None,
) -> None:
    """Write the minimal release metadata used by the validator."""
    component = root / "custom_components" / "scorpiontrack"
    component.mkdir(parents=True)
    (component / "manifest.json").write_text(
        f'{{"version": "{manifest_version}"}}', encoding="utf-8"
    )
    (root / "pyproject.toml").write_text(
        "\n".join(
            (
                "[project]",
                'name = "ha-scorpiontrack-integration"',
                f'version = "{project_version}"',
            )
        ),
        encoding="utf-8",
    )

    packages = ""
    if lock_version is not None:
        packages = "\n".join(
            (
                "[[package]]",
                'name = "ha-scorpiontrack-integration"',
                f'version = "{lock_version}"',
                'source = { virtual = "." }',
            )
        )
    (root / "uv.lock").write_text(packages, encoding="utf-8")
