## ScorpionTrack Integration

ScorpionTrack Integration gives Home Assistant a single setup flow for two ScorpionTrack sources:

- `Portal account` for the richer authenticated integration
- `Shared location link` for lightweight read-only tracking

### What it adds

- live `device_tracker` entities for Home Assistant maps and zones
- tidy `Location` sensors that avoid creating duplicate map markers
- account-level alert sensors for unread count, latest alert, and recent alert details
- an account-level `Mark Alerts Read` button
- account-mode vehicle sensors, binary sensors, and verified switches
- share-mode support for multiple vehicles from a single share link

### Setup options

Choose `Portal account` if you want the fuller portal-backed experience, including verified controls such as `Privacy Mode` and `Zero-Speed Mode`.

Choose `Shared location link` if you only want tracking from a ScorpionTrack share. One share can include multiple vehicles.

### Important note

Home Assistant includes a built-in `scorpiontrack` integration for shared links. This custom integration uses the same domain to preserve portal-account support and established entity IDs, so installing it overrides the built-in integration. HACS duplicate-domain rules mean it must remain a manually added custom repository.

The authenticated portal mode relies on private web behaviour rather than a documented public API, so it should be treated more conservatively than the shared-link mode. Make a Home Assistant backup before installing or removing it; portal-account entries require this custom integration.

### Troubleshooting

The integration classifies bad credentials, invalid or expired share links, login redirects, and malformed portal responses without logging passwords, API keys, full share tokens, full email addresses, or raw upstream error text. The share client may include a short masked token prefix and suffix in diagnostic logs, so review logs before sharing them. Enable Home Assistant debug logging for `custom_components.scorpiontrack` when collecting issue reports.
