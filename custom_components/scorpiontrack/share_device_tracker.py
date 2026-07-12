"""Device tracker platform for ScorpionTrack Share."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyscorpiontrack import ScorpionTrackVehicle

from .const import convert_speed
from .share_coordinator import (
    ScorpionTrackShareConfigEntry,
    ScorpionTrackShareCoordinator,
)
from .share_entity import ScorpionTrackEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScorpionTrackShareConfigEntry,
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


class ScorpionTrackTrackerEntity(ScorpionTrackEntity, TrackerEntity):
    """Represent the latest shared GPS location for a vehicle."""

    _attr_name = None
    _attr_translation_key = "vehicle_location"

    def __init__(
        self, coordinator: ScorpionTrackShareCoordinator, vehicle_id: int
    ) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator, vehicle_id)
        self._attr_unique_id = f"{coordinator.data.id}_{vehicle_id}_tracker"

    def _available_vehicle(self) -> ScorpionTrackVehicle | None:
        """Return the vehicle if the tracker is available."""
        if not super().available:
            return None
        return self.get_vehicle()

    @property
    @override
    def available(self) -> bool:
        """Return if the tracker is available."""
        vehicle = self._available_vehicle()
        return (
            vehicle is not None
            and vehicle.position.latitude is not None
            and vehicle.position.longitude is not None
        )

    @property
    @override
    def latitude(self) -> float | None:
        """Return the latitude."""
        vehicle = self._available_vehicle()
        return vehicle.position.latitude if vehicle is not None else None

    @property
    @override
    def longitude(self) -> float | None:
        """Return the longitude."""
        vehicle = self._available_vehicle()
        return vehicle.position.longitude if vehicle is not None else None

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        vehicle = self._available_vehicle()
        if vehicle is None:
            return {}

        position = vehicle.position
        speed_unit = self.coordinator.speed_unit
        converted_speed = convert_speed(position.speed_kmh, speed_unit)
        attributes = self.common_location_attributes(vehicle)
        attributes.update(
            {
                "speed": converted_speed,
                "speed_unit": speed_unit,
                "speed_kmh": position.speed_kmh,
                "distance_units": self.share.distance_units,
            }
        )
        return attributes
