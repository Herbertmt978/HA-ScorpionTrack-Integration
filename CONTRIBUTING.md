# Contributing

Contributions to the HACS custom integration are welcome. The built-in Home Assistant implementation is maintained separately in [Herbertmt978/ScorpionTrack-Integration](https://github.com/Herbertmt978/ScorpionTrack-Integration); do not mix Core changes into a pull request for this repository.

## Before starting

- Search existing issues and pull requests.
- Use the bug or feature issue form for changes that need discussion.
- Never publish live credentials, share tokens, registrations, identifiers, alert contents, alert screenshots, or location data.
- Keep compatibility with existing config entries, entity unique IDs, and device identifiers.
- Treat portal behaviour as private and unstable. Do not expose a writable control until its endpoint behaviour has been verified in both directions.

## Development environment

The test environment overrides Home Assistant's cryptography and PyJWT pins
with 50.0.1 and 2.15.0 respectively to address their security advisories. Its
lockfile also uses patched urllib3 2.8.0. Tests retain the Home Assistant
2026.8.0 compatibility baseline but do not use its stock dependency set.
These changes apply to development and CI; HACS installs use the dependencies
provided by the user's Home Assistant installation.

Install [uv](https://docs.astral.sh/uv/) and Python 3.14.2 or later in the
Python 3.14 series, then create a locked environment:

```bash
uv sync --locked --all-groups --python 3.14
```

Run the same quality checks used by CI:

```bash
uv run --locked --all-groups ruff check .
uv run --locked --all-groups ruff format --check --diff .
uv run --locked --all-groups pytest tests/test_config_flow.py \
  --cov=custom_components.scorpiontrack.config_flow \
  --cov-report=term-missing \
  --cov-fail-under=100
uv run --locked --all-groups pytest tests \
  --cov=custom_components.scorpiontrack \
  --cov-report=term-missing
```

Home Assistant tests require Linux; Windows contributors should run them under
WSL. Native Windows can still create the environment and run Ruff. CI runs the
suite with Home Assistant 2026.8.0 from the lockfile on Python 3.14.

## Tests and fixtures

- Add regression tests for behaviour changes.
- Test successful, unavailable, and invalid-data paths where relevant.
- Use synthetic fixture data only.
- Diagnostics and logging changes require explicit tests proving that secrets, identity, and location data are absent.
- Do not weaken the 100% config-flow or 95% overall coverage gates.

## Pull requests

- Keep each pull request focused.
- Explain user-visible behaviour and compatibility implications.
- State whether portal-account mode, shared-link mode, or both were tested.
- Update the README and changelog when behaviour changes.
- Let every required check finish before merge.
- Dependabot may queue individual stable patch/minor updates to the allowlisted
  GitHub Actions or Ruff for auto-merge after every required check passes.
  The policy accepts only the expected dependency files, excludes groups and
  maintainer-edited PRs, and never approves reviews or bypasses protections.
- Home Assistant test-fixture changes, client/runtime pins, dependency overrides,
  major/prerelease upgrades and all other changes remain maintainer-reviewed.
  Publishing releases and updating live installations are separate manual steps.

All contributed code is provided under the repository's [MIT Licence](LICENSE).

The uv tooling range supports both the explicitly pinned CI version and the
0.12-series version used by Dependabot. Keep the lockfile compatible with both;
changing that tooling range or the CI pin remains a manually reviewed change.
