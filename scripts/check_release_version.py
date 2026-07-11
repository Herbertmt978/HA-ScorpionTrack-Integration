"""Validate release versions across repository metadata."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

PROJECT_NAME = "ha-scorpiontrack-integration"
SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


class ReleaseVersionError(ValueError):
    """Raised when release metadata is incomplete or inconsistent."""


def validate_versions(
    root: Path,
    *,
    ref_type: str | None = None,
    ref_name: str | None = None,
) -> str:
    """Validate metadata and return the common release version."""
    manifest = _load_json(root / "custom_components/scorpiontrack/manifest.json")
    project = _load_toml(root / "pyproject.toml")
    lock = _load_toml(root / "uv.lock")

    manifest_version = manifest.get("version")
    project_version = project.get("project", {}).get("version")
    lock_version = _root_lock_version(lock)
    versions = {
        "manifest.json": manifest_version,
        "pyproject.toml": project_version,
        "uv.lock": lock_version,
    }

    if len(set(versions.values())) != 1:
        details = ", ".join(f"{name}={value!r}" for name, value in versions.items())
        raise ReleaseVersionError(f"Version mismatch: {details}")

    version = manifest_version
    if not isinstance(version, str) or not SEMVER_PATTERN.fullmatch(version):
        raise ReleaseVersionError(
            f"Release version must be a numeric semantic version (X.Y.Z), got {version!r}"
        )

    if ref_type == "tag":
        expected_tag = f"v{version}"
        if ref_name != expected_tag:
            raise ReleaseVersionError(
                f"Tag {ref_name or '<missing>'} does not match {expected_tag}"
            )

    return version


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object or raise a release-specific error."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise ReleaseVersionError(f"Unable to read {path}: {err}") from err
    if not isinstance(value, dict):
        raise ReleaseVersionError(f"Expected a JSON object in {path}")
    return value


def _load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML document or raise a release-specific error."""
    try:
        with path.open("rb") as file_handle:
            return tomllib.load(file_handle)
    except (OSError, tomllib.TOMLDecodeError) as err:
        raise ReleaseVersionError(f"Unable to read {path}: {err}") from err


def _root_lock_version(lock: dict[str, Any]) -> str:
    """Return the version of the virtual root package in uv.lock."""
    for package in lock.get("package", []):
        source = package.get("source")
        if (
            package.get("name") == PROJECT_NAME
            and isinstance(source, dict)
            and source.get("virtual") == "."
        ):
            version = package.get("version")
            if isinstance(version, str):
                return version
    raise ReleaseVersionError(
        "uv.lock does not contain the virtual root project record"
    )


def main() -> int:
    """Run the repository release version check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (defaults to the script's parent repository)",
    )
    args = parser.parse_args()

    try:
        version = validate_versions(
            args.root,
            ref_type=os.environ.get("GITHUB_REF_TYPE"),
            ref_name=os.environ.get("GITHUB_REF_NAME"),
        )
    except ReleaseVersionError as err:
        print(f"Release version check failed: {err}", file=sys.stderr)
        return 1

    print(f"Release metadata verified for v{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
