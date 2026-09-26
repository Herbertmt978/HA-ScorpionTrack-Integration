"""Exercise the trusted workflow policy without GitHub credentials or mutations."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load(
    (ROOT / ".github/workflows/dependabot-automerge.yml").read_text(encoding="utf-8")
)
POLICY = next(
    step["run"]
    for step in WORKFLOW["jobs"]["manage"]["steps"]
    if step.get("id") == "policy"
)


class AutoMergePolicyTest(unittest.TestCase):
    """Execute the actual Bash step with a harmless metadata boundary."""

    def eligible(self, **changes: str) -> bool:
        """Supply metadata and fake changed paths; never call the real gh CLI."""
        environment = {
            **os.environ,
            "DEPENDENCY_GROUP": "",
            "DEPENDENCY_NAMES": "ruff",
            "DIRECTORY": "/",
            "MAINTAINER_CHANGES": "false",
            "NEW_VERSION": "0.15.22",
            "PACKAGE_ECOSYSTEM": "uv",
            "PR_URL": "https://github.invalid/pull/1",
            "UPDATE_TYPE": "version-update:semver-patch",
            "CHANGED_FILES": "uv.lock\npyproject.toml",
            "REVIEWS": '{"reviewDecision":"","reviews":[]}',
            **changes,
        }
        bash = shutil.which("bash")
        if os.name == "nt":
            bash = r"C:\Program Files\Git\bin\bash.exe"
        if bash is None:
            self.fail("Bash is required to verify the auto-merge policy")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "github-output"
            environment["GITHUB_OUTPUT"] = output.as_posix()
            result = subprocess.run(
                [
                    bash,
                    "-c",
                    'gh() { if [[ "$2" == "diff" ]]; then '
                    'printf "%s\\n" "$CHANGED_FILES"; else '
                    'printf "%s" "$REVIEWS" | jq -r "$7"; fi; };\n' + POLICY,
                ],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return output.read_text(encoding="utf-8").strip() == "eligible=true"

    def test_routine_package_updates(self) -> None:
        """Only individual stable Ruff patch/minor changes are eligible."""
        self.assertTrue(self.eligible())
        self.assertTrue(self.eligible(UPDATE_TYPE="version-update:semver-minor"))

    def test_sensitive_packages_and_ecosystems(self) -> None:
        """Compatibility baseline, runtime pins and overrides stay manual."""
        for dependency in (
            "pytest-homeassistant-custom-component",
            "pyscorpiontrack",
            "cryptography",
            "ruff,cryptography",
            "",
        ):
            with self.subTest(dependency=dependency):
                self.assertFalse(self.eligible(DEPENDENCY_NAMES=dependency))
        self.assertFalse(self.eligible(PACKAGE_ECOSYSTEM="npm"))
        self.assertFalse(self.eligible(DIRECTORY="/other"))

    def test_nonroutine_metadata(self) -> None:
        """Groups, maintainer changes and major/prerelease upgrades stay manual."""
        for changes in (
            {"DEPENDENCY_GROUP": "weekly"},
            {"MAINTAINER_CHANGES": "true"},
            {"MAINTAINER_CHANGES": ""},
            {"MAINTAINER_CHANGES": "unknown"},
            {"UPDATE_TYPE": "version-update:semver-major"},
            {"UPDATE_TYPE": ""},
            {"NEW_VERSION": "0.16.0rc1"},
            {"NEW_VERSION": "0.16.0-beta.1"},
            {"NEW_VERSION": ""},
            {"NEW_VERSION": "unknown"},
        ):
            with self.subTest(changes=changes):
                self.assertFalse(self.eligible(**changes))

    def test_unexpected_paths(self) -> None:
        """Code, override-only and policy edits cannot join a package update."""
        for files in (
            "uv.lock",
            "pyproject.toml",
            "pyproject.toml\nuv.lock\ncustom_components/scorpiontrack/api.py",
            "pyproject.toml\nuv.lock\n.github/workflows/dependabot-automerge.yml",
        ):
            with self.subTest(files=files):
                self.assertFalse(self.eligible(CHANGED_FILES=files))

    def test_existing_action_updates(self) -> None:
        """Retain the existing allowlist and exact workflow path checks."""
        cases = {
            "actions/checkout": (
                ".github/workflows/hassfest.yml\n"
                ".github/workflows/python-quality.yml\n"
                ".github/workflows/validate.yml"
            ),
            "actions/setup-python": ".github/workflows/python-quality.yml",
            "astral-sh/setup-uv": ".github/workflows/python-quality.yml",
            "hacs/action": ".github/workflows/validate.yml",
            "home-assistant/actions/hassfest": ".github/workflows/hassfest.yml",
        }
        for dependency, paths in cases.items():
            with self.subTest(dependency=dependency):
                self.assertTrue(
                    self.eligible(
                        PACKAGE_ECOSYSTEM="github_actions",
                        DEPENDENCY_NAMES=dependency,
                        NEW_VERSION="v10.0.2",
                        CHANGED_FILES=paths,
                    )
                )

    def test_privileged_workflow_never_executes_pr_source(self) -> None:
        """Only trusted metadata can queue a merge governed by branch checks."""
        steps = WORKFLOW["jobs"]["manage"]["steps"]
        self.assertFalse(
            any("actions/checkout" in step.get("uses", "") for step in steps)
        )
        queue = steps[-1]
        self.assertIn("--auto --squash --match-head-commit", queue["run"])
        self.assertNotIn("--admin", queue["run"])
        gate = WORKFLOW["jobs"]["manage"]["if"]
        expected_gate = (
            "github.repository == 'Herbertmt978/HA-ScorpionTrack-Integration' && "
            "github.event.pull_request.user.login == 'dependabot[bot]' && "
            "github.event.pull_request.base.ref == github.event.repository.default_branch && "
            "github.event.pull_request.head.repo.full_name == github.repository && "
            "(startsWith(github.event.pull_request.head.ref, 'dependabot/github_actions/') || "
            "startsWith(github.event.pull_request.head.ref, 'dependabot/uv/'))"
        )
        self.assertEqual(" ".join(gate.split()), expected_gate)

    def test_outstanding_change_requests_stay_manual(self) -> None:
        """Do not rely on a zero-approval rule to block a human change request."""
        requested = {
            "author": {"login": "reviewer"},
            "state": "CHANGES_REQUESTED",
            "submittedAt": "2026-09-01T10:00:00Z",
        }
        approved = {
            "author": {"login": "reviewer"},
            "state": "APPROVED",
            "submittedAt": "2026-09-02T10:00:00Z",
        }
        self.assertFalse(self.eligible(REVIEWS="{}"))
        self.assertFalse(self.eligible(REVIEWS='{"reviews":[{}]}'))
        self.assertFalse(
            self.eligible(REVIEWS='{"reviewDecision":"CHANGES_REQUESTED","reviews":[]}')
        )
        self.assertFalse(self.eligible(REVIEWS=json.dumps({"reviews": [requested]})))
        commented = {**approved, "state": "COMMENTED"}
        self.assertFalse(
            self.eligible(REVIEWS=json.dumps({"reviews": [requested, commented]}))
        )
        self.assertTrue(
            self.eligible(REVIEWS=json.dumps({"reviews": [requested, approved]}))
        )
        for timestamp in ("", "unknown", "2026-99-01T10:00:00Z"):
            malformed = {**requested, "submittedAt": timestamp}
            with self.subTest(timestamp=timestamp):
                self.assertFalse(
                    self.eligible(
                        REVIEWS=json.dumps({"reviews": [malformed, approved]})
                    )
                )
        approved["author"] = {"login": "another-reviewer"}
        self.assertFalse(
            self.eligible(REVIEWS=json.dumps({"reviews": [requested, approved]}))
        )


if __name__ == "__main__":
    unittest.main()
