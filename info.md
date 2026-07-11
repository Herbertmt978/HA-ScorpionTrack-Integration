## ScorpionTrack Integration

This custom Home Assistant integration supports both ScorpionTrack portal accounts and shared-location links.

Portal-account mode adds account alerts, a `Mark Alerts Read` action, richer vehicle entities, and verified `Privacy Mode` and `Zero-Speed Mode` controls. Shared-link mode provides read-only tracking for every vehicle in a ScorpionTrack share.

Home Assistant also includes a built-in ScorpionTrack integration that is installed from `Settings > Devices & services > Add integration`. It is simpler and has less functionality because it supports shared-location links only. Its source and review history are available in [Herbertmt978/ScorpionTrack-Integration](https://github.com/Herbertmt978/ScorpionTrack-Integration).

> [!IMPORTANT]
> Both integrations use the same `scorpiontrack` domain and cannot run together. Installing this custom version makes it take precedence over the built-in version. Make a Home Assistant backup before installing, removing, or switching.

See the [full README](https://github.com/Herbertmt978/HA-ScorpionTrack-Integration#readme) for installation, setup, update, rollback, removal, troubleshooting, and privacy guidance.
