"""Shared entity helpers for ScorpionTrack Share."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, override

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from pyscorpiontrack import ScorpionTrackShare, ScorpionTrackVehicle

from .const import DOMAIN, MANUFACTURER, SHARE_DEFAULT_NAME, STALE_POSITION_THRESHOLD
from .share_coordinator import ScorpionTrackShareCoordinator


class ScorpionTrackEntity(CoordinatorEntity[ScorpionTrackShareCoordinator]):
    """Base class for ScorpionTrack entities."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: ScorpionTrackShareCoordinator, vehicle_id: int
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._vehicle_id = vehicle_id
        self._last_vehicle = coordinator.vehicles_by_id[vehicle_id]
        vehicle = self._last_vehicle
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self.share.id}_{vehicle.id}")},
            manufacturer=vehicle.make or MANUFACTURER,
            model=vehicle.model,
            name=vehicle.display_name,
        )

    @property
    def share(self) -> ScorpionTrackShare:
        """Return the active share data."""
        return self.coordinator.data

    def get_vehicle(self) -> ScorpionTrackVehicle:
        """Return the current vehicle, or its last snapshot while unavailable."""
        if vehicle := self.coordinator.vehicles_by_id.get(self._vehicle_id):
            self._last_vehicle = vehicle
        return self._last_vehicle

    @property
    def vehicle(self) -> ScorpionTrackVehicle:
        """Return the matching vehicle."""
        return self.get_vehicle()

    @property
    @override
    def available(self) -> bool:
        """Return if the entity is available."""
        return super().available and self._vehicle_id in self.coordinator.vehicles_by_id

    def position_age(
        self, vehicle: ScorpionTrackVehicle | None = None
    ) -> timedelta | None:
        """Return the age of the latest reported position."""
        selected_vehicle = vehicle or self.vehicle
        timestamp = selected_vehicle.position.timestamp
        if timestamp is None:
            return None

        age = dt_util.utcnow() - timestamp
        if age.total_seconds() < 0:
            return timedelta(seconds=0)
        return age

    def position_is_stale(self, vehicle: ScorpionTrackVehicle | None = None) -> bool:
        """Return True if the latest reported position is stale."""
        age = self.position_age(vehicle)
        return age is None or age >= STALE_POSITION_THRESHOLD

    def common_location_attributes(
        self, vehicle: ScorpionTrackVehicle | None = None
    ) -> dict[str, Any]:
        """Return shared location-related attributes."""
        selected_vehicle = vehicle or self.vehicle
        position = selected_vehicle.position
        age = self.position_age(selected_vehicle)
        age_seconds = max(0, int(age.total_seconds())) if age is not None else None

        return {
            "registration": selected_vehicle.registration,
            "make": selected_vehicle.make,
            "model": selected_vehicle.model,
            "status": selected_vehicle.status,
            "bearing": position.bearing,
            "heading_cardinal": _bearing_to_cardinal(position.bearing),
            "address": position.address,
            "ignition": position.ignition,
            "last_reported": (
                position.timestamp.isoformat() if position.timestamp else None
            ),
            "last_reported_age_seconds": age_seconds,
            "stale": age is None or age >= STALE_POSITION_THRESHOLD,
            "stale_after_hours": int(STALE_POSITION_THRESHOLD.total_seconds() // 3600),
            "share_title": self.share.title,
            "shared_by": self.share.owner_name,
            "share_expires": (
                self.share.expires_at.isoformat() if self.share.expires_at else None
            ),
        }


class ScorpionTrackShareEntity(CoordinatorEntity[ScorpionTrackShareCoordinator]):
    """Base class for share-level entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ScorpionTrackShareCoordinator) -> None:
        """Initialize a share-level entity."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"share_{self.share.id}")},
            manufacturer=MANUFACTURER,
            model="Location Share",
            name=self.share.title or SHARE_DEFAULT_NAME,
        )

    @property
    def share(self) -> ScorpionTrackShare:
        """Return the active share data."""
        return self.coordinator.data

    def share_common_attributes(self) -> dict[str, Any]:
        """Return shared share-level attributes."""
        return {
            "share_id": self.share.id,
            "share_title": self.share.title,
            "shared_by": self.share.owner_name,
            "distance_units": self.share.distance_units,
            "vehicle_count": len(self.share.vehicles),
            "created_at": (
                self.share.created_at.isoformat() if self.share.created_at else None
            ),
            "share_expires": (
                self.share.expires_at.isoformat() if self.share.expires_at else None
            ),
        }


def _bearing_to_cardinal(bearing: float | None) -> str | None:
    """Convert a numeric bearing into a cardinal heading."""
    if bearing is None:
        return None

    directions = (
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    )
    index = int((bearing % 360) / 22.5 + 0.5) % len(directions)
    return directions[index]
