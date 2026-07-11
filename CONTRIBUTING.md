# Contributing

Contributions to the HACS custom integration are welcome. The built-in Home Assistant implementation is maintained separately in [Herbertmt978/ScorpionTrack-Integration](https://github.com/Herbertmt978/ScorpionTrack-Integration); do not mix Core changes into a pull request for this repository.

## Before starting

- Search existing issues and pull requests.
- Use the bug or feature issue form for changes that need discussion.
- Never publish live credentials, share tokens, registrations, identifiers, alert contents, alert screenshots, or location data.
- Keep compatibility with existing config entries, entity unique IDs, and device identifiers.
- Treat portal behaviour as private and unstable. Do not expose a writable control until its endpoint behaviour has been verified in both directions.

## Development environment

Install [uv](https://docs.astral.sh/uv/) and create a locked environment:

```bash
uv sync --locked --all-groups --python 3.12
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

CI repeats the suite on the minimum and current pinned Home Assistant compatibility lanes.

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
- Do not automate merging or publishing. The maintainer reviews and completes those actions manually.

All contributed code is provided under the repository's [MIT Licence](LICENSE).
