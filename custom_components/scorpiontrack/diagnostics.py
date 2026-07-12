"""Privacy-safe diagnostics for the ScorpionTrack integration."""

from __future__ import annotations

from collections import Counter
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import ScorpionTrackConfigEntry
from .account_api import ScorpionTrackAccountData
from .account_coordinator import ScorpionTrackAccountCoordinator
from .const import get_setup_type


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ScorpionTrackConfigEntry,
) -> dict[str, Any]:
    """Return an allowlisted diagnostics payload for a config entry."""
    coordinator = entry.runtime_data
    registry_entries = er.async_entries_for_config_entry(
        er.async_get(hass), entry.entry_id
    )
    entities_by_platform = Counter(
        registry_entry.domain for registry_entry in registry_entries
    )
    update_interval = coordinator.update_interval

    diagnostics: dict[str, Any] = {
        "config_entry": {
            "setup_type": get_setup_type(entry.data),
            "state": entry.state.value,
            "version": entry.version,
            "minor_version": entry.minor_version,
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception_type": (
                type(coordinator.last_exception).__name__
                if coordinator.last_exception is not None
                else None
            ),
            "update_interval_seconds": (
                update_interval.total_seconds() if update_interval is not None else None
            ),
            "vehicle_count": len(coordinator.vehicles_by_id),
        },
        "entities": {
            "total": len(registry_entries),
            "disabled": sum(
                registry_entry.disabled_by is not None
                for registry_entry in registry_entries
            ),
            "by_platform": dict(sorted(entities_by_platform.items())),
        },
    }

    if isinstance(coordinator, ScorpionTrackAccountCoordinator) and isinstance(
        coordinator.data, ScorpionTrackAccountData
    ):
        diagnostics["account"] = {
            "app_api_key_available": coordinator.data.app_api_key_available,
            "fms_api_available": coordinator.data.fms_api_available,
            "total_alerts": coordinator.data.total_alerts,
            "unread_alerts": coordinator.data.unread_alerts,
        }
        if coordinator.share_client is not None:
            diagnostics["hybrid_share"] = {
                "last_update_success": coordinator.share_last_update_success,
                "last_exception_type": coordinator.share_last_exception_type,
                "matched_vehicle_count": coordinator.matched_share_vehicle_count,
            }

    return diagnostics
