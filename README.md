# ScorpionTrack Integration

Use ScorpionTrack portal accounts or shared-location links in Home Assistant from one custom integration.

[![HACS validation](https://github.com/Herbertmt978/HA-ScorpionTrack-Integration/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/Herbertmt978/HA-ScorpionTrack-Integration/actions/workflows/validate.yml)
[![Hassfest](https://github.com/Herbertmt978/HA-ScorpionTrack-Integration/actions/workflows/hassfest.yml/badge.svg?branch=main)](https://github.com/Herbertmt978/HA-ScorpionTrack-Integration/actions/workflows/hassfest.yml)
[![Python quality](https://github.com/Herbertmt978/HA-ScorpionTrack-Integration/actions/workflows/python-quality.yml/badge.svg?branch=main)](https://github.com/Herbertmt978/HA-ScorpionTrack-Integration/actions/workflows/python-quality.yml)
[![GitHub release](https://img.shields.io/github/v/release/Herbertmt978/HA-ScorpionTrack-Integration?display_name=tag&sort=semver)](https://github.com/Herbertmt978/HA-ScorpionTrack-Integration/releases)
[![Licence: MIT](https://img.shields.io/github/license/Herbertmt978/HA-ScorpionTrack-Integration)](LICENSE)

[![Open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Herbertmt978&repository=HA-ScorpionTrack-Integration&category=integration)

## Choose the right integration

Home Assistant includes a built-in ScorpionTrack integration that you install from `Settings > Devices & services > Add integration`. It is simpler and has less functionality: it supports shared-location links only.

This HACS integration supports both portal accounts and shared-location links, including account alerts and verified portal controls.

| Capability | Built-in Home Assistant integration | This HACS integration |
| --- | --- | --- |
| Installation | Home Assistant's integration screen | HACS custom repository or manual copy |
| Shared-location links | Yes | Yes |
| Portal account login | No | Yes |
| Account alerts and `Mark Alerts Read` | No | Yes |
| Verified portal controls | No | `Privacy Mode` and `Zero-Speed Mode` |

The source and review history for the built-in integration are available in [Herbertmt978/ScorpionTrack-Integration](https://github.com/Herbertmt978/ScorpionTrack-Integration). Install that version from Home Assistant's integration screen, not from its source repository.

> [!IMPORTANT]
> Both versions use the `scorpiontrack` integration domain and cannot run at the same time. Installing this custom integration makes it take precedence over the built-in version. Make a Home Assistant backup before installing, removing, or switching between them.

Because this repository overrides a built-in domain, HACS cannot list it in the default store. Add it as a custom repository instead.

## Before you install

| Concern | Behaviour |
| --- | --- |
| Minimum Home Assistant version | 2025.1.0 |
| Data stored by Home Assistant | Portal email and password, a shared-location token, or both for hybrid mode |
| Network access | ScorpionTrack cloud and portal endpoints |
| Polling | Shared links every 2 minutes; portal accounts every 5 minutes; hybrid account live data every 2 minutes |
| Telemetry | No separate analytics or telemetry |
| Writable actions | Mark alerts read, Privacy Mode, and Zero-Speed Mode only |
| Reversibility | Back up first and follow the rollback or removal steps below |

Portal-account mode uses private ScorpionTrack web behaviour rather than a documented public API. Portal changes can temporarily break account mode even when shared-link mode continues to work.

Treat Home Assistant backups as sensitive because they can contain integration configuration.

## Installation

### HACS custom repository

Use the **Open this repository in HACS** button above, or add it manually:

1. Open HACS in Home Assistant.
2. Select `Integrations`.
3. Open the three-dot menu and select `Custom repositories`.
4. Add `https://github.com/Herbertmt978/HA-ScorpionTrack-Integration`.
5. Select `Integration` as the category.
6. Download `ScorpionTrack Integration`.
7. Restart Home Assistant.

<details>
<summary><strong>Manual installation</strong></summary>

1. Download this repository's latest release.
2. Copy `custom_components/scorpiontrack` into Home Assistant's `custom_components` directory.
3. Restart Home Assistant.

Manual installations must be updated manually by replacing the same directory with files from a newer release.

</details>

## Verify the installation

After restarting Home Assistant:

1. Open `Settings > Devices & services`.
2. Select `Add integration` and search for `ScorpionTrack Integration`.
3. Complete one of the setup routes below.
4. Confirm the config entry shows as loaded.
5. Confirm each vehicle has a device and `device_tracker` entity.

Setup performs an initial refresh. Later refreshes run every 2 minutes for shared links and every 5 minutes for portal accounts.

Speed can be displayed as `mph` or `km/h`. Choose the unit during setup or change it later from the config entry's `Configure` options.

## Setup

### Portal account

Choose `Portal account` for the fuller authenticated integration. Enter the email address and password used for the ScorpionTrack portal. You may also paste a shared-location URL or token during setup to create one hybrid entry.

Portal-account mode provides:

- live vehicle trackers for maps, zones, and automations
- account sensors such as `Unread Alerts`, `Latest Alert`, `Latest Alert Time`, and `Vehicle Count`
- a `Mark Alerts Read` account button
- vehicle sensors including `Status`, `Location`, `Speed`, `Heading`, `Odometer`, `Battery Voltage`, `Fuel Type`, `Battery Type`, `Unit Make`, and `MOT Due`
- binary sensors including `Ignition`, `Engine`, `Armed Mode Enabled`, `EWM Enabled`, `Driver Module Fitted`, `G-Sense Enabled`, and `Location Stale`
- verified switches for `Privacy Mode` and `Zero-Speed Mode`

### Faster live data for portal accounts

The portal account feed can return location data less frequently than Home Assistant polls it. To retain account alerts and controls while receiving newer live vehicle data:

1. Create a ScorpionTrack location share containing the same vehicle or vehicles.
2. Open the ScorpionTrack config entry and select `Configure`.
3. Paste the share URL or token, choose `mph` or `km/h`, and save.

Hybrid mode continues to refresh authenticated account data every 5 minutes. It refreshes the optional share every 2 minutes and overlays only a position that is at least as recent as the account position. Vehicle IDs are matched first, with a unique normalized registration as a fallback. Location, speed, heading, ignition, and derived status can therefore update faster without duplicating account devices or entities.

If the optional share temporarily fails, the entry remains available, retains its last newer live position, and continues using portal data for account metadata and controls. Remove the share from `Configure` to return to account-only polling.

`Armed Mode` remains read-only because the current portal endpoint reports it but does not reliably accept a true toggle.

### Shared-location link

Choose `Shared location link` for read-only tracking without portal credentials.

1. Open [ScorpionTrack Location Share](https://app.scorpiontrack.com/customer/locationshare).
2. Create a share and add every vehicle you want to track.
3. Choose an expiry.
4. Paste the generated share URL or token into Home Assistant.

One share can contain multiple vehicles. Shared-link mode provides:

- a `device_tracker` for every shared vehicle
- sensors such as `Status`, `Location`, `Speed`, `Heading`, `Last Reported`, and `Share Expires`
- binary sensors such as `Ignition` and `Location Stale`
- share sensors such as `Share Title`, `Shared By`, `Share Created`, and `Share Expires`

Choose `mph` or `km/h` during setup, or change it later from the config entry's `Configure` options.

## Entity behaviour

Vehicle coordinates are published by the `device_tracker`. Related sensors use readable location text and non-map attributes, so each vehicle produces one map marker instead of several.

Changing the speed-unit option reloads the config entry and updates every speed sensor (and share-tracker speed attribute) without changing entity IDs.

Alert coordinates use alert-specific attribute names rather than generic `latitude` and `longitude` attributes. This prevents alert sensors from appearing as additional vehicle markers.

Only controls verified to behave as true on/off operations are writable.

## Update, roll back, or remove

### Update

1. Create a Home Assistant backup and read the [release notes](https://github.com/Herbertmt978/HA-ScorpionTrack-Integration/releases).
2. Open HACS and find `ScorpionTrack Integration`.
3. If a release is missing, use the HACS three-dot menu and select `Update information` to refresh repository metadata.
4. Select `Download` or `Redownload` to install the release.
5. Restart Home Assistant.
6. Confirm the expected version in HACS and verify each config entry and vehicle entity.

`Update information` refreshes HACS metadata; it does not download integration files.

### Roll back

1. Create a backup.
2. Open the repository's three-dot menu in HACS and select `Redownload`.
3. Under `Need a different version?`, select the previous release.
4. Download it, restart Home Assistant, and verify the config entries.
5. Restore the backup or return to the latest release if the older version cannot load the current entries.

### Switch to the built-in integration

1. Create a backup and make sure you can recreate a valid shared-location link.
2. Remove every ScorpionTrack config entry from `Settings > Devices & services`.
3. Remove this custom repository from HACS.
4. Restart Home Assistant.
5. Open `Settings > Devices & services > Add integration`, search for `ScorpionTrack`, and add the shared-location link again.

Portal-account entries cannot be moved to the built-in integration because it supports shared-location links only. Do not assume an entry will migrate automatically, and do not edit Home Assistant's `.storage` files manually.

### Remove completely

1. Create a backup.
2. Remove every ScorpionTrack config entry from `Settings > Devices & services`.
3. Remove this repository from HACS, or delete `custom_components/scorpiontrack` for a manual installation.
4. Restart Home Assistant.

Removing repository files from HACS does not remove related Home Assistant configuration, which is why the config entries must be removed first.

## Security and privacy

- No live credentials or share tokens are included in this repository.
- Account mode stores the portal email and password in the Home Assistant config entry so it can refresh automatically.
- Share mode stores the share token in the config entry.
- Fleet requests are restricted to HTTPS Scorpion/ScorpionTrack hosts, do not follow redirects, and reject absolute request paths.
- Diagnostics use an explicit allowlist of counts and capability flags. They exclude credentials, tokens, account and vehicle identifiers, registrations, alert contents, alert timestamps, addresses, and coordinates.
- Expected authentication and connection failures are converted into concise categories. Routine logs can include a masked email address, HTTP status, method, and sanitized endpoint path, but not passwords, API keys, full tokens, full email addresses, or numeric account and vehicle identifiers.
- Unexpected exceptions and dependency logs can still contain technical or identifying information. Review and redact every log or diagnostics file before sharing it.

Report security problems privately through the repository's [security advisory form](https://github.com/Herbertmt978/HA-ScorpionTrack-Integration/security/advisories/new). Do not include secrets or current locations in a public issue. See [SECURITY.md](SECURITY.md) for the supported-version policy.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Release is missing in HACS | Select `Update information`, then reopen the download dialog |
| Portal login is rejected | Confirm the credentials in the ScorpionTrack portal and complete any portal-side verification first |
| Share is unavailable | Confirm the link is still active, has not expired, and contains at least one vehicle |
| Entities stop updating | Check the config-entry status, Home Assistant logs, and ScorpionTrack service availability |
| Built-in integration appears instead | Confirm this repository is installed, then restart Home Assistant |

Download diagnostics from the ScorpionTrack config entry's menu under `Settings > Devices & services`. Diagnostics are designed for issue reports, but review the file before uploading it.

For deeper logs, add:

```yaml
logger:
  logs:
    custom_components.scorpiontrack: debug
```

Before opening a [bug report](https://github.com/Herbertmt978/HA-ScorpionTrack-Integration/issues/new/choose), include:

- Home Assistant, HACS, and integration versions
- portal-account or shared-link setup mode
- clear reproduction steps and expected behaviour
- sanitized diagnostics and the smallest relevant log extract

Never post portal credentials, API keys, cookies, session data, complete or partial share tokens, registrations, aliases, vehicle IDs, coordinates, street addresses, alert contents, or location screenshots.

Support for this custom integration belongs in this repository, not in the Home Assistant Core or HACS issue trackers.

## Development

The test suite covers the minimum compatibility lane, Home Assistant 2025.1.0 on Python 3.12, and the current pinned lane, Home Assistant 2026.7.4 on Python 3.14. CI requires 100% config-flow coverage and at least 95% overall integration coverage.

Authenticated portal behaviour is documented in [docs/portal-notes.md](docs/portal-notes.md). Development commands and privacy requirements are in [CONTRIBUTING.md](CONTRIBUTING.md), changes are recorded in [CHANGELOG.md](CHANGELOG.md), and the manual publishing process is in [RELEASING.md](RELEASING.md).

## Licence

This project is available under the [MIT Licence](LICENSE).
