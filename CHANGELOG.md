# Changelog

All notable changes to this project are documented here.

## Unreleased

No changes yet.

## 0.3.0 - 2026-07-12

### Added

- Selectable `mph` or `km/h` speed units for portal-account and shared-link entries.
- Optional hybrid authentication that combines a portal account with a validated shared-location link in one config entry.
- Privacy-safe hybrid diagnostics for share health and matched-vehicle counts.

### Changed

- Hybrid entries now refresh live share positions every 2 minutes while retaining the 5-minute portal-account cadence for alerts, metadata, and controls.
- Newer share positions update the existing account tracker and live sensors without changing deployed entity IDs; temporary share failures retain the last newer live position while portal metadata and controls continue.

## 0.2.1 - 2026-07-11

### Added

- Privacy-safe Home Assistant diagnostics with explicit redaction regression tests.
- One-click HACS installation and built-in-versus-HACS guidance.
- Update, verification, rollback, switching, and removal instructions.
- Structured issue forms, a pull-request template, contributing guidance, and a manual release checklist.
- Automated release-version consistency validation.

### Changed

- Clarified the integration's logging, data-storage, network, telemetry, and support boundaries.
- Removed internal portal user IDs from logs and redacted numeric endpoint identifiers.
- Made workflow check names stable and added timeouts and scheduled compatibility testing.
- Prepared the repository for protected, human-reviewed changes and immutable future releases.

## 0.2.0 - 2026-07-11

### Added

- Complete portal-account and shared-location functionality in a single custom integration.
- Dynamic vehicle discovery, account alerts, verified portal actions, synchronized translations, icons, and locked dependencies.
- Compatibility testing for Home Assistant 2025.1.0 on Python 3.12 and Home Assistant 2026.7.2 on Python 3.14.

### Changed

- Improved config-entry lifecycle handling, reauthentication, coordinator failures, and removed-vehicle recovery.
- Adopted `pyscorpiontrack==0.1.1` for shared-location links.
- Hardened portal requests, redirect handling, origin validation, sensitive errors, optional records, and transient HTTP failures.

### Validation

- 123 tests passed on each compatibility lane.
- Config-flow coverage reached 100%; overall integration coverage reached 95.72%.
- Ruff, Hassfest, and HACS validation passed.

For older releases, see the [GitHub release history](https://github.com/Herbertmt978/HA-ScorpionTrack-Integration/releases).
