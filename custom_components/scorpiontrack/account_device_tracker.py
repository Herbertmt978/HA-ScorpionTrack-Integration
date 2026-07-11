"""Device tracker platform for ScorpionTrack Account."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .account_api import ScorpionTrackVehicleSummary
from .account_coordinator import (
    ScorpionTrackAccountConfigEntry,
    ScorpionTrackAccountCoordinator,
)
from .account_entity import ScorpionTrackVehicleEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScorpionTrackAccountConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ScorpionTrack tracker entities."""
    coordinator = entry.runtime_data
    known_vehicle_ids: set[int] = set()

    @callback
    def _async_add_missing_entities() -> None:
        new_vehicle_ids = [
            vehicle.id
            for vehicle in coordinator.data.vehicles
            if vehicle.id not in known_vehicle_ids
        ]
        if not new_vehicle_ids:
            return

        known_vehicle_ids.update(new_vehicle_ids)
        async_add_entities(
            ScorpionTrackTrackerEntity(coordinator, vehicle_id)
            for vehicle_id in new_vehicle_ids
        )

    _async_add_missing_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_missing_entities))


class ScorpionTrackTrackerEntity(ScorpionTrackVehicleEntity, TrackerEntity):
    """Represent the latest authenticated GPS location for a vehicle."""

    _attr_name = None
    _attr_translation_key = "vehicle_location"

    def __init__(
        self, coordinator: ScorpionTrackAccountCoordinator, vehicle_id: int
    ) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator, vehicle_id)
        self._attr_unique_id = f"{self.account_identifier}_{vehicle_id}_tracker"

    def _available_vehicle(self) -> ScorpionTrackVehicleSummary | None:
        """Return the vehicle if the tracker is available."""
        if not super().available:
            return None
        return self.get_vehicle()

    @property
    @override
    def available(self) -> bool:
        """Return if the tracker is available."""
        vehicle = self._available_vehicle()
        position = vehicle.position if vehicle is not None else None
        return (
            position is not None
            and position.latitude is not None
            and position.longitude is not None
        )

    @property
    @override
    def latitude(self) -> float | None:
        """Return the latitude."""
        vehicle = self._available_vehicle()
        position = vehicle.position if vehicle is not None else None
        return position.latitude if position is not None else None

    @property
    @override
    def longitude(self) -> float | None:
        """Return the longitude."""
        vehicle = self._available_vehicle()
        position = vehicle.position if vehicle is not None else None
        return position.longitude if position is not None else None

    @property
    @override
    def location_accuracy(self) -> float:
        """Return the location accuracy in meters."""
        vehicle = self._available_vehicle()
        position = vehicle.position if vehicle is not None else None
        if position is None or position.accuracy is None:
            return 0.0
        return float(position.accuracy)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        vehicle = self._available_vehicle()
        if vehicle is None:
            return {}

        attributes = self.common_vehicle_attributes(vehicle)
        attributes["formatted_location"] = self.format_location(vehicle.position)
        return attributes
