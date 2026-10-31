## ScorpionTrack Portal

This custom Home Assistant integration supports both ScorpionTrack portal accounts and shared-location links. It uses its own `scorpiontrack_portal` domain, so it runs alongside Home Assistant's built-in ScorpionTrack integration.

Portal-account mode adds account alerts, a `Mark alerts read` action, richer vehicle entities, and verified `Privacy mode` and `Zero-speed mode` controls. Shared-link mode provides read-only tracking for every vehicle in a ScorpionTrack share.

Portal accounts can optionally use a share link in the same config entry: authenticated account data remains on its five-minute cadence while live location, speed, heading, ignition, and status can update from the share every two minutes. Speed and odometer follow the account's distance preference and can be changed per entity.

Home Assistant's built-in ScorpionTrack integration, installed from **Settings → Devices & services → Add integration**, uses the shared-location API for read-only tracking. Portal-account mode stays in this custom integration because it relies on the ScorpionTrack web portal's login route, which is less stable than that API. Its source and review history are available in [Herbertmt978/ScorpionTrack-Integration](https://github.com/Herbertmt978/ScorpionTrack-Integration).

> [!IMPORTANT]
> Version 0.5.0 removes entity attributes and several entities, replaces the speed-unit option with Home Assistant's unit settings, and changes status values. Version 0.6.0 brings those entities back, disabled by default; attributes stay removed. Check the README's "Upgrade to 0.6.0" and "Upgrade to 0.5.0" sections before updating.
>
> Versions 0.3.x and earlier used the built-in `scorpiontrack` domain and replaced the built-in integration. Updating from them means deleting the old entries and adding them again under ScorpionTrack Portal. Make a Home Assistant backup first and follow the upgrade steps in the README.

See the [full README](https://github.com/Herbertmt978/HA-ScorpionTrack-Integration#readme) for installation, upgrade, setup, update, rollback, removal, troubleshooting, and privacy guidance.
