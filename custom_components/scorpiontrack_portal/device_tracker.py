"""Device tracker platform for ScorpionTrack Portal."""

from __future__ import annotations

from typing import override

from homeassistant.components.device_tracker.entity import TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .account_api import ScorpionTrackVehiclePosition
from .coordinator import (
    ScorpionTrackAccountCoordinator,
    ScorpionTrackConfigEntry,
    ScorpionTrackShareCoordinator,
)
from .entity import (
    ScorpionTrackAccountVehicleEntity,
    ScorpionTrackShareVehicleEntity,
    async_add_vehicle_entities,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScorpionTrackConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up ScorpionTrack tracker entities."""
    coordinator = entry.runtime_data
    if isinstance(coordinator, ScorpionTrackAccountCoordinator):
        account_coordinator = coordinator
        async_add_vehicle_entities(
            entry,
            account_coordinator,
            async_add_entities,
            lambda vehicle_id: (
                ScorpionTrackAccountTracker(account_coordinator, vehicle_id),
            ),
        )
        return

    share_coordinator = coordinator
    async_add_vehicle_entities(
        entry,
        share_coordinator,
        async_add_entities,
        lambda vehicle_id: (ScorpionTrackShareTracker(share_coordinator, vehicle_id),),
    )


class ScorpionTrackAccountTracker(ScorpionTrackAccountVehicleEntity, TrackerEntity):
    """Represent the latest portal-account GPS location for a vehicle."""

    _attr_name = None
    _attr_translation_key = "vehicle_location"

    def __init__(
        self, coordinator: ScorpionTrackAccountCoordinator, vehicle_id: int
    ) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator, vehicle_id, "tracker")

    @property
    def _position(self) -> ScorpionTrackVehiclePosition | None:
        """Return the vehicle position while the vehicle is available."""
        if not super().available:
            return None
        return self.vehicle.position

    @property
    @override
    def available(self) -> bool:
        """Return if the tracker has a complete position."""
        position = self._position
        return (
            position is not None
            and position.latitude is not None
            and position.longitude is not None
        )

    @property
    @override
    def latitude(self) -> float | None:
        """Return the latitude."""
        position = self._position
        return position.latitude if position is not None else None

    @property
    @override
    def longitude(self) -> float | None:
        """Return the longitude."""
        position = self._position
        return position.longitude if position is not None else None

    @property
    @override
    def location_accuracy(self) -> float:
        """Return the location accuracy in metres."""
        position = self._position
        if position is None or position.accuracy is None:
            return 0.0
        return float(position.accuracy)


class ScorpionTrackShareTracker(ScorpionTrackShareVehicleEntity, TrackerEntity):
    """Represent the latest shared GPS location for a vehicle."""

    _attr_name = None
    _attr_translation_key = "vehicle_location"

    def __init__(
        self, coordinator: ScorpionTrackShareCoordinator, vehicle_id: int
    ) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator, vehicle_id, "tracker")

    @property
    @override
    def available(self) -> bool:
        """Return if the tracker has a complete position."""
        if not super().available:
            return False
        position = self.vehicle.position
        return position.latitude is not None and position.longitude is not None

    @property
    @override
    def latitude(self) -> float | None:
        """Return the latitude."""
        return self.vehicle.position.latitude if super().available else None

    @property
    @override
    def longitude(self) -> float | None:
        """Return the longitude."""
        return self.vehicle.position.longitude if super().available else None
