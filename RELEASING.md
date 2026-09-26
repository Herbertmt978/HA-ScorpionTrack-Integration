# Releasing

Releases are validated automatically and published manually. Do not configure
automatic tagging, release-note generation, or publishing. The only automatic
merge exception is the narrow Dependabot policy documented in CONTRIBUTING:
individual stable patch/minor updates to allowlisted GitHub Actions or Ruff,
with expected changed paths and every protected-branch check passing.

## Monthly dependency review

Review dependencies at least monthly and before a release:

```bash
uv lock --upgrade
git diff -- pyproject.toml uv.lock .github/workflows
```

Retain full commit-SHA action pins and the complete lint and test gates. Review
changes outside the Dependabot allowlist manually, including Home Assistant
fixtures, client/runtime pins, dependency overrides and major/prerelease updates.
Auto-merging a routine dependency update never publishes a release or updates
an installed Home Assistant environment.

## Prepare a release

1. Choose the next semantic version, for example `0.2.1`.
2. Update the version in:
   - `custom_components/scorpiontrack/manifest.json`
   - `pyproject.toml`
   - the root project record in `uv.lock`
3. Move the relevant entries from `Unreleased` to a dated changelog section.
4. Run the release guard:

   ```bash
   python scripts/check_release_version.py
   ```

5. Run Ruff, formatting, 100% config-flow coverage, and the complete test suite.
6. Open a normal pull request to `main` and wait for every required check.
7. Review the diff, test evidence, privacy impact, and release notes manually.
8. Squash-merge the pull request manually.

## Tag and publish

1. Confirm the exact `main` commit is green.
2. Create an annotated tag from that commit:

   ```bash
   git switch main
   git pull --ff-only
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin vX.Y.Z
   ```

3. Wait for every tag workflow, including `Release version guard`, to pass.
4. Create a draft GitHub release using the existing tag.
5. Write and review the title, notes, upgrade guidance, and compare link manually.
6. Confirm the draft targets the exact green commit.
7. Publish the release manually.
8. Confirm HACS displays the new version. If necessary, use HACS `Update information` to refresh repository metadata.

Future releases are immutable after publication. Draft first, attach anything required, and verify every detail before publishing. The existing v0.2.0 release predates this policy and remains unchanged.

## Recovery

If checks fail, fix the code through another pull request; do not move or force-push a published tag. If a released defect cannot be corrected in place, publish a new patch version and document the rollback path.
