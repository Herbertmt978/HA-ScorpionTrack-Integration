# Releasing

Releases are validated automatically and published manually. Do not configure
automatic tagging, release-note generation, or publishing. The only automatic
merge exception is the narrow Dependabot policy documented in CONTRIBUTING:
individual stable patch/minor updates to allowlisted GitHub Actions or Ruff,
with expected changed paths and every protected-branch check passing.

Other pull requests are merged by the maintainer, or by a coding agent such as
Claude Code when the maintainer asks it to, following
[Merge a pull request](#merge-a-pull-request).

## Merge a pull request

Before an agent merges a pull request on the maintainer's behalf, it must:

1. Confirm that every required check has passed on the pull request's current
   head commit.
2. Read every review, inline review comment and conversation comment, including
   automated reviews such as Codex.
3. Fix each actionable finding in a follow-up commit, rerun the affected local
   checks, and wait for the required checks to pass again.
4. Confirm that no review threads are unresolved, no changes are requested, and
   the pull request can merge without bypassing the `main` ruleset.
5. Squash-merge the pull request by number against the reviewed head commit,
   for example `gh pr merge <number> --squash --match-head-commit <sha>`, with a
   commit message that summarises the change and its verification. Without a
   number, `gh` merges the pull request for the currently checked-out branch.

If the agent cannot complete a step, or considers a finding incorrect or out of
scope, it leaves the pull request open and explains what is outstanding to the
maintainer. Agents never bypass branch rules or enable GitHub auto-merge. They
tag and publish only a release the maintainer has asked for, following
[Tag and publish](#tag-and-publish), and never update an installed Home
Assistant environment.

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
   - `custom_components/scorpiontrack_portal/manifest.json`
   - `pyproject.toml`
   - the root project record in `uv.lock`
3. Move the relevant entries from `Unreleased` to a dated changelog section.
4. Run the release guard:

   ```bash
   python scripts/check_release_version.py
   ```

5. Run Ruff, formatting, 100% config-flow coverage, and the complete test suite.
6. Open a normal pull request to `main` and wait for every required check.
7. Review the diff, test evidence, privacy impact, and release notes.
8. Squash-merge the pull request yourself, or ask an agent to merge it following
   [Merge a pull request](#merge-a-pull-request).

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
