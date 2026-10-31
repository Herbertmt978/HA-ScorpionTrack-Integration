"""Base entities for ScorpionTrack Portal."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from typing import Any, override

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from pyscorpiontrack import ScorpionTrackShare, ScorpionTrackVehicle

from .account_api import (
    ScorpionTrackAccountData,
    ScorpionTrackVehiclePosition,
    ScorpionTrackVehicleSummary,
)
from .const import DOMAIN, MANUFACTURER, SHARE_DEFAULT_NAME, STALE_POSITION_THRESHOLD
from .coordinator import (
    ScorpionTrackAccountCoordinator,
    ScorpionTrackConfigEntry,
    ScorpionTrackShareCoordinator,
)


@callback
def async_add_vehicle_entities(
    entry: ScorpionTrackConfigEntry,
    coordinator: ScorpionTrackAccountCoordinator | ScorpionTrackShareCoordinator,
    async_add_entities: AddConfigEntryEntitiesCallback,
    create_entities: Callable[[int], Iterable[Entity]],
) -> None:
    """Add entities for each vehicle when it first appears in coordinator data."""
    known_vehicle_ids: set[int] = set()

    @callback
    def _async_add_new_vehicles() -> None:
        known_vehicle_ids.intersection_update(coordinator.vehicles_by_id)
        new_vehicle_ids = coordinator.vehicles_by_id.keys() - known_vehicle_ids
        if not new_vehicle_ids:
            return
        known_vehicle_ids.update(new_vehicle_ids)
        async_add_entities(
            entity
            for vehicle_id in sorted(new_vehicle_ids)
            for entity in create_entities(vehicle_id)
        )

    _async_add_new_vehicles()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_vehicles))


def format_location(
    latitude: float | None, longitude: float | None, address: str | None
) -> str | None:
    """Return the address, or coordinates when no address is known."""
    if address:
        return address
    return format_coordinates(latitude, longitude)


def format_coordinates(latitude: float | None, longitude: float | None) -> str | None:
    """Return coordinates in a compact string form."""
    if latitude is None or longitude is None:
        return None
    return f"{latitude:.6f}, {longitude:.6f}"


def position_age(timestamp: datetime | None) -> timedelta | None:
    """Return the non-negative age of a reported position."""
    if timestamp is None:
        return None
    return max(dt_util.utcnow() - timestamp, timedelta(0))


def position_is_stale(timestamp: datetime | None) -> bool:
    """Return True when a position is missing or older than the threshold."""
    age = position_age(timestamp)
    return age is None or age >= STALE_POSITION_THRESHOLD


class ScorpionTrackAccountEntity(CoordinatorEntity[ScorpionTrackAccountCoordinator]):
    """Base class for portal-account entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ScorpionTrackAccountCoordinator) -> None:
        """Initialize an account-level entity."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"account_{coordinator.account_identifier}")},
            entry_type=DeviceEntryType.SERVICE,
            manufacturer=MANUFACTURER,
            model="Portal Account",
            name=coordinator.data.title,
        )

    @property
    def account(self) -> ScorpionTrackAccountData:
        """Return the latest account snapshot."""
        return self.coordinator.data

    @property
    def account_identifier(self) -> str:
        """Return the stable account identifier used in unique IDs."""
        return self.coordinator.account_identifier

    def common_account_attributes(self) -> dict[str, Any]:
        """Return shared account attributes."""
        return {
            "user_id": self.account.user_id,
            "distance_units": self.account.distance_units,
            "vehicle_ids": [vehicle.id for vehicle in self.account.vehicles],
            "total_alerts": self.account.total_alerts,
            "unread_alerts": self.account.unread_alerts,
            "latest_alert": (
                self.account.latest_alert.summary
                if self.account.latest_alert is not None
                else None
            ),
            "app_api_key_available": self.account.app_api_key_available,
            "fms_api_available": self.account.fms_api_available,
        }


class ScorpionTrackAccountVehicleEntity(
    CoordinatorEntity[ScorpionTrackAccountCoordinator]
):
    """Base class for portal-account vehicle entities."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: ScorpionTrackAccountCoordinator, vehicle_id: int
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._vehicle_id = vehicle_id
        self._last_vehicle = coordinator.vehicles_by_id[vehicle_id]
        vehicle = self._last_vehicle
        account_identifier = coordinator.account_identifier
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{account_identifier}_vehicle_{vehicle_id}")},
            via_device=(DOMAIN, f"account_{account_identifier}"),
            manufacturer=vehicle.make or MANUFACTURER,
            model=vehicle.model
            or vehicle.unit_model
            or vehicle.vehicle_type
            or "Vehicle",
            name=vehicle.display_name,
        )

    @property
    def account(self) -> ScorpionTrackAccountData:
        """Return the latest account snapshot."""
        return self.coordinator.data

    @property
    def account_identifier(self) -> str:
        """Return the stable account identifier used in unique IDs."""
        return self.coordinator.account_identifier

    @property
    def vehicle(self) -> ScorpionTrackVehicleSummary:
        """Return the current vehicle, or its last snapshot while it is absent."""
        if vehicle := self.coordinator.vehicles_by_id.get(self._vehicle_id):
            self._last_vehicle = vehicle
        return self._last_vehicle

    @property
    @override
    def available(self) -> bool:
        """Return if the entity is available."""
        return super().available and self._vehicle_id in self.coordinator.vehicles_by_id

    def common_vehicle_attributes(self) -> dict[str, Any]:
        """Return shared vehicle attributes."""
        vehicle = self.vehicle
        attributes: dict[str, Any] = {
            "portal_vehicle_id": vehicle.id,
            "registration": vehicle.registration,
            "alias": vehicle.alias,
            "description": vehicle.description,
            "make": vehicle.make,
            "model": vehicle.model,
            "vehicle_type": vehicle.vehicle_type,
            "colour": vehicle.colour,
            "fuel_type": vehicle.fuel_type,
            "status": vehicle.status,
            "portal_state": vehicle.raw_state,
            "odometer": vehicle.odometer,
            "odometer_unit": "km",
            "groups": list(vehicle.group_names),
            "last_service_date": vehicle.last_service_date,
            "battery_type": vehicle.battery_type,
            "vehicle_voltage": vehicle.vehicle_voltage,
            "backup_battery_voltage": vehicle.backup_battery_voltage,
            "gps_antenna_voltage": vehicle.gps_antenna_voltage,
            "gps_antenna_current": vehicle.gps_antenna_current,
            "privacy_mode_enabled": vehicle.privacy_mode_enabled,
            "zero_speed_mode_enabled": vehicle.zero_speed_mode_enabled,
            "armed_mode_enabled": vehicle.armed_mode_enabled,
            "transport_mode_active": vehicle.transport_mode_active,
            "garage_mode_active": vehicle.garage_mode_active,
            "no_alert_mode_active": vehicle.no_alert_mode_active,
            "ewm_enabled": vehicle.ewm_enabled,
            "driver_module": vehicle.driver_module,
            "g_sense_enabled": vehicle.g_sense_enabled,
            "immobiliser_fitted": vehicle.immobiliser_fitted,
            "install_complete": vehicle.install_complete,
            "pending_commands_count": vehicle.pending_commands_count,
            "unit_type": vehicle.unit_type,
            "unit_model": vehicle.unit_model,
            "unit_make": vehicle.unit_make,
            "installed_at": vehicle.installed_at,
            "updated_at": vehicle.updated_at,
            "distance_units": self.account.distance_units,
        }
        attributes.update(_position_attributes(vehicle.position))
        return attributes


class ScorpionTrackShareEntity(CoordinatorEntity[ScorpionTrackShareCoordinator]):
    """Base class for shared-location entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ScorpionTrackShareCoordinator) -> None:
        """Initialize a share-level entity."""
        super().__init__(coordinator)
        share = coordinator.data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"share_{share.id}")},
            entry_type=DeviceEntryType.SERVICE,
            manufacturer=MANUFACTURER,
            model="Location Share",
            name=share.title or SHARE_DEFAULT_NAME,
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


class ScorpionTrackShareVehicleEntity(CoordinatorEntity[ScorpionTrackShareCoordinator]):
    """Base class for shared-location vehicle entities."""

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
            identifiers={(DOMAIN, f"{coordinator.data.id}_{vehicle_id}")},
            manufacturer=vehicle.make or MANUFACTURER,
            model=vehicle.model,
            name=vehicle.display_name,
        )

    @property
    def share(self) -> ScorpionTrackShare:
        """Return the active share data."""
        return self.coordinator.data

    @property
    def vehicle(self) -> ScorpionTrackVehicle:
        """Return the current vehicle, or its last snapshot while it is absent."""
        if vehicle := self.coordinator.vehicles_by_id.get(self._vehicle_id):
            self._last_vehicle = vehicle
        return self._last_vehicle

    @property
    @override
    def available(self) -> bool:
        """Return if the entity is available."""
        return super().available and self._vehicle_id in self.coordinator.vehicles_by_id

    def common_location_attributes(self) -> dict[str, Any]:
        """Return shared location-related attributes."""
        vehicle = self.vehicle
        position = vehicle.position
        age = position_age(position.timestamp)
        return {
            "registration": vehicle.registration,
            "make": vehicle.make,
            "model": vehicle.model,
            "status": vehicle.status,
            "bearing": position.bearing,
            "heading_cardinal": _bearing_to_cardinal(position.bearing),
            "address": position.address,
            "ignition": position.ignition,
            "last_reported": (
                position.timestamp.isoformat() if position.timestamp else None
            ),
            "last_reported_age_seconds": (
                int(age.total_seconds()) if age is not None else None
            ),
            "stale": position_is_stale(position.timestamp),
            "stale_after_hours": int(STALE_POSITION_THRESHOLD.total_seconds() // 3600),
            "share_title": self.share.title,
            "shared_by": self.share.owner_name,
            "share_expires": (
                self.share.expires_at.isoformat() if self.share.expires_at else None
            ),
            "distance_units": self.share.distance_units,
        }


def _position_attributes(
    position: ScorpionTrackVehiclePosition | None,
) -> dict[str, Any]:
    """Return shared portal position attributes."""
    if position is None:
        return {}
    return {
        "position_timestamp": position.timestamp,
        "speed_kmh": position.speed_kmh,
        "heading": position.bearing,
        "accuracy": position.accuracy,
        "address": position.address,
        "ignition": position.ignition,
        "engine": position.engine,
        "gps_satellites": position.gps_satellites,
        "gps_hdop": position.hdop,
        "vehicle_voltage": position.vehicle_voltage,
        "position_odometer": position.odometer,
        "position_odometer_unit": "km",
        "position_state": position.raw_state,
    }


def _bearing_to_cardinal(bearing: float | None) -> str | None:
    """Convert a numeric bearing into a sixteen-point cardinal heading."""
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
    return directions[int((bearing % 360) / 22.5 + 0.5) % len(directions)]
