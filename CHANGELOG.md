# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added

- Reconfigure: add, replace or remove a portal account's hybrid share link, or give a shared-location entry a new link for the same share.
- Authentication failures during a switch or button action now start reauthentication.

### Changed

- The hybrid share link moved from the entry options to its connection data (config entry version 1.2, migrated automatically). `Configure` now only sets the speed unit and reloads the entry itself.
- Reauthentication with credentials for a different account now aborts instead of showing an error.
- Devices for vehicles removed from an account or share are removed. Vehicles that return are recreated, which previously did not happen.
- Switch and button actions run one at a time per platform; the previous concurrency setting was ignored.
- Portal and fleet API failures are logged at debug level, and logs no longer include the account's email address. The optional hybrid share logs once when it fails and once when it recovers.
- Switch errors now name the failing control through a translation.

### Developer

- Restructure the integration into Home Assistant's standard `coordinator.py`, `entity.py` and single platform modules.
- Add strict mypy, using Home Assistant Core's settings, to the required test job.
- Remove compatibility code for Core-created entries, which cannot exist under the `scorpiontrack_portal` domain.

## 0.4.0 - 2026-10-31

### Changed

- **Breaking:** Rename the integration to ScorpionTrack Portal and move it to its own `scorpiontrack_portal` domain (`custom_components/scorpiontrack_portal`). It no longer replaces Home Assistant's built-in ScorpionTrack integration, and both can now be installed and configured at the same time.
- Entries, devices and entities created by 0.3.x and earlier stay under the built-in `scorpiontrack` domain and are not migrated. Delete them before updating, remove any leftover `custom_components/scorpiontrack` directory, and add each portal account or share again. The README describes the upgrade steps.
- Debug logging now uses the `custom_components.scorpiontrack_portal` logger.

## 0.3.4 - 2026-10-12

### Fixed

- Preserve zero odometer and GPS satellite readings instead of replacing them with fallback values.
- Normalise map odometers from miles to kilometres before merging with fleet data. Display the odometer in the account's preferred distance unit and label it explicitly, so a fallback cannot change its scale.
- Honour `mph` when the map supplies a display speed without `speedkm`.
- Keep partial telemetry, including voltage and ignition, even when location and timestamp fields are absent.
- Derive vehicle status after merging readings and honour the vehicle-level state when a position has no state.
- Preserve unknown account engine and shared-link ignition readings instead of reporting them as off.
- Treat non-finite numbers and out-of-range timestamps as missing, allowing valid fallback readings to be used.
- Use the unit's fitted date when the vehicle installation date is invalid, while retaining a valid zero timestamp.
- Keep vehicle updates working when optional alert data is null or malformed.

### Changed

- Odometer attributes now explicitly use kilometres (`odometer_unit` and `position_odometer_unit`); the odometer sensor follows the account's distance preference.
- Update the development lockfile to `multidict` 6.9.1, fixing its items-view reference leak; installed Home Assistant dependencies are unchanged.

## 0.3.3 - 2026-10-12

### Fixed

- Parse portal battery-voltage readings with a `V` suffix so decimal readings match the ScorpionTrack map instead of falling back to the health-check voltage.
- Preserve valid zero-volt readings when a health-check voltage is also available.
- Require at least `pyscorpiontrack` 0.1.2 for the shared-location client, restoring Hassfest compatibility and using safer error handling while allowing Home Assistant to update its shared dependency.

### Changed

- Update the pinned Hassfest action and Ruff development tool.
- Update the development test environment to patched PyJWT and urllib3 versions; installed Home Assistant dependencies are unchanged.

## 0.3.2 - 2026-08-07

### Changed

- Raise the minimum supported Home Assistant version to 2026.8.0 and the development and test baseline to Python 3.14.2.
- Refresh the locked Home Assistant test stack and retire the vulnerable Home Assistant 2025.1 compatibility graph.

## 0.3.1 - 2026-07-13

### Fixed

- Hybrid entries retain the portal address with the portal coordinates when a newer share update has an incomplete coordinate pair.

## 0.3.0 - 2026-07-12

### Added

- Selectable `mph` or `km/h` speed units for portal-account and shared-link entries.
- Optional hybrid authentication that combines a portal account with a validated shared-location link in one config entry.
- Privacy-safe hybrid diagnostics for share health and matched-vehicle counts.

### Changed

- Hybrid entries now refresh live share positions every 2 minutes while retaining the 5-minute portal-account cadence for alerts, metadata, and controls.
- Newer share positions update the existing account tracker and live sensors without changing deployed entity IDs; temporary share failures retain the last newer live position while portal metadata and controls continue.

### Fixed

- Hybrid entries retain the portal location when a newer share update omits part or all of its coordinate pair.

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
