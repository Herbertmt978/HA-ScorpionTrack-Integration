# Security Policy

## Supported versions

Security fixes are made for the latest published release. Upgrade to the latest release before reporting a problem that may already have been corrected.

| Version | Supported |
| --- | --- |
| Latest published release | Yes |
| Older releases | No |

## Report a vulnerability privately

Use GitHub's [private vulnerability reporting form](https://github.com/Herbertmt978/HA-ScorpionTrack-Integration/security/advisories/new). Do not open a public issue for a suspected vulnerability.

Include:

- the affected integration and Home Assistant versions
- portal-account or shared-link setup mode
- the impact and a safe reproduction procedure
- whether the issue is already being exploited or publicly discussed

Never include:

- portal email addresses or passwords
- API keys, cookies, or session data
- complete or partial share tokens
- vehicle registrations, aliases, or internal identifiers
- current or historical coordinates, street addresses, alert contents, or location screenshots
- an unredacted Home Assistant backup, log, or diagnostics file

The maintainer aims to acknowledge a private report within seven calendar days. Validation and remediation timing depend on severity and whether a safe fix requires upstream changes. Replies, release notes, and disclosure decisions are reviewed and written by the maintainer.

## Scope

The main security-sensitive areas are:

- storage and use of ScorpionTrack portal credentials
- storage and use of shared-location tokens
- authenticated portal sessions and private portal endpoints
- diagnostics, logs, and entity attributes that could reveal identity or location
- writable account actions and vehicle controls

Reports about Home Assistant Core, HACS, GitHub, or ScorpionTrack's own services should be sent to the relevant project or provider unless the vulnerability is caused by this custom integration.

## Disclosure

Please allow time for a fix to be developed, tested, and released before publishing details. When appropriate, the maintainer will coordinate a GitHub security advisory and credit the reporter unless anonymity is requested.
