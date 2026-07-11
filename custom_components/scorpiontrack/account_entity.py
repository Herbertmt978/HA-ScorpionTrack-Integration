"""Shared entity helpers for ScorpionTrack Account."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, override

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .account_api import (
    ScorpionTrackAccountData,
    ScorpionTrackVehiclePosition,
    ScorpionTrackVehicleSummary,
)
from .account_coordinator import ScorpionTrackAccountCoordinator
from .const import DOMAIN, MANUFACTURER

_STALE_AFTER = timedelta(hours=24)


class ScorpionTrackCoordinatorEntity(
    CoordinatorEntity[ScorpionTrackAccountCoordinator]
):
    """Base class for entities backed by the account coordinator."""

    _attr_has_entity_name = True

    @property
    def account(self) -> ScorpionTrackAccountData:
        """Return the latest account snapshot."""
        return self.coordinator.data

    @property
    def account_identifier(self) -> str:
        """Return a stable account identifier for device registry use."""
        return self.coordinator.account_identifier


class ScorpionTrackAccountEntity(ScorpionTrackCoordinatorEntity):
    """Base class for account-level entities."""

    def __init__(self, coordinator: ScorpionTrackAccountCoordinator) -> None:
        """Initialize an account-level entity."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"account_{self.account_identifier}")},
            manufacturer=MANUFACTURER,
            model="Portal Account",
            name=self.account.title,
        )

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


class ScorpionTrackVehicleEntity(ScorpionTrackCoordinatorEntity):
    """Base class for vehicle-level entities."""

    def __init__(
        self, coordinator: ScorpionTrackAccountCoordinator, vehicle_id: int
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._vehicle_id = vehicle_id
        self._last_vehicle = coordinator.vehicles_by_id[vehicle_id]
        vehicle = self._last_vehicle
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self.account_identifier}_vehicle_{vehicle.id}")},
            via_device=(DOMAIN, f"account_{self.account_identifier}"),
            manufacturer=vehicle.make or MANUFACTURER,
            model=vehicle.model
            or vehicle.unit_model
            or vehicle.vehicle_type
            or "Vehicle",
            name=vehicle.display_name,
        )

    def get_vehicle(self) -> ScorpionTrackVehicleSummary:
        """Return the current vehicle, or its last snapshot while unavailable."""
        if vehicle := self.coordinator.vehicles_by_id.get(self._vehicle_id):
            self._last_vehicle = vehicle
        return self._last_vehicle

    @property
    def vehicle(self) -> ScorpionTrackVehicleSummary:
        """Return the matching vehicle."""
        return self.get_vehicle()

    @property
    def position(self) -> ScorpionTrackVehiclePosition | None:
        """Return the best-known vehicle position."""
        return self.vehicle.position

    @property
    @override
    def available(self) -> bool:
        """Return if the entity is available."""
        return super().available and self._vehicle_id in self.coordinator.vehicles_by_id

    def location_is_stale(
        self, vehicle: ScorpionTrackVehicleSummary | None = None
    ) -> bool:
        """Return True when the current location is stale."""
        selected_vehicle = vehicle or self.vehicle
        position = selected_vehicle.position
        if position is None or position.timestamp is None:
            return True
        return datetime.now(UTC) - position.timestamp > _STALE_AFTER

    @staticmethod
    def format_location(position: ScorpionTrackVehiclePosition | None) -> str | None:
        """Return a human-friendly location string."""
        if position is None:
            return None
        if position.address:
            return position.address
        if position.latitude is None or position.longitude is None:
            return None
        return f"{position.latitude:.6f}, {position.longitude:.6f}"

    @staticmethod
    def common_position_attributes(
        position: ScorpionTrackVehiclePosition | None,
    ) -> dict[str, Any]:
        """Return shared position attributes."""
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
            "position_state": position.raw_state,
        }

    def common_vehicle_attributes(
        self, vehicle: ScorpionTrackVehicleSummary | None = None
    ) -> dict[str, Any]:
        """Return shared vehicle attributes."""
        selected_vehicle = vehicle or self.vehicle
        attributes = {
            "portal_vehicle_id": selected_vehicle.id,
            "registration": selected_vehicle.registration,
            "alias": selected_vehicle.alias,
            "description": selected_vehicle.description,
            "make": selected_vehicle.make,
            "model": selected_vehicle.model,
            "vehicle_type": selected_vehicle.vehicle_type,
            "colour": selected_vehicle.colour,
            "fuel_type": selected_vehicle.fuel_type,
            "status": selected_vehicle.status,
            "portal_state": selected_vehicle.raw_state,
            "odometer": selected_vehicle.odometer,
            "groups": list(selected_vehicle.group_names),
            "last_service_date": selected_vehicle.last_service_date,
            "battery_type": selected_vehicle.battery_type,
            "vehicle_voltage": selected_vehicle.vehicle_voltage,
            "backup_battery_voltage": selected_vehicle.backup_battery_voltage,
            "gps_antenna_voltage": selected_vehicle.gps_antenna_voltage,
            "gps_antenna_current": selected_vehicle.gps_antenna_current,
            "privacy_mode_enabled": selected_vehicle.privacy_mode_enabled,
            "zero_speed_mode_enabled": selected_vehicle.zero_speed_mode_enabled,
            "armed_mode_enabled": selected_vehicle.armed_mode_enabled,
            "transport_mode_active": selected_vehicle.transport_mode_active,
            "garage_mode_active": selected_vehicle.garage_mode_active,
            "no_alert_mode_active": selected_vehicle.no_alert_mode_active,
            "ewm_enabled": selected_vehicle.ewm_enabled,
            "driver_module": selected_vehicle.driver_module,
            "g_sense_enabled": selected_vehicle.g_sense_enabled,
            "immobiliser_fitted": selected_vehicle.immobiliser_fitted,
            "install_complete": selected_vehicle.install_complete,
            "pending_commands_count": selected_vehicle.pending_commands_count,
            "unit_type": selected_vehicle.unit_type,
            "unit_model": selected_vehicle.unit_model,
            "unit_make": selected_vehicle.unit_make,
            "installed_at": selected_vehicle.installed_at,
            "updated_at": selected_vehicle.updated_at,
            "distance_units": self.account.distance_units,
        }
        attributes.update(self.common_position_attributes(selected_vehicle.position))
        return attributes
