## Summary

<!-- Explain the user-visible problem and the focused change. -->

## Scope

- [ ] This pull request changes only the HACS custom integration repository.
- [ ] It does not modify the approved Home Assistant Core submission.

## Compatibility

- [ ] Existing config entries, entity unique IDs, and device identifiers are preserved.
- [ ] Portal-account mode was considered or tested.
- [ ] Shared-location mode was considered or tested.
- [ ] Any writable control has verified on/off behaviour and safe failure handling.

## Privacy and security

- [ ] Tests and fixtures contain only synthetic data.
- [ ] Logs, errors, diagnostics, states, and attributes do not expose credentials, tokens, identity, or location data unnecessarily.
- [ ] Dependency and workflow changes retain locked versions and full action commit-SHA pins.

## Validation

<!-- List the exact commands and results. -->

- [ ] Ruff check
- [ ] Ruff format check
- [ ] Config-flow coverage gate
- [ ] Complete test suite
- [ ] Hassfest
- [ ] HACS validation
- [ ] Release version guard

## Documentation and release impact

- [ ] README or supporting documentation updated where needed.
- [ ] Changelog updated for user-visible changes.
- [ ] Version change is intentional and matches the manifest, project metadata, lockfile, and release tag.
