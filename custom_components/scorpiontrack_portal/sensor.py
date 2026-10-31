"""Sensor platform for ScorpionTrack Portal."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfLength,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from pyscorpiontrack import ScorpionTrackShare, ScorpionTrackVehicle

from .account_api import ScorpionTrackAccountData, ScorpionTrackVehicleSummary
from .const import convert_speed
from .coordinator import (
    ScorpionTrackAccountCoordinator,
    ScorpionTrackConfigEntry,
    ScorpionTrackShareCoordinator,
)
from .entity import (
    ScorpionTrackAccountEntity,
    ScorpionTrackAccountVehicleEntity,
    ScorpionTrackShareEntity,
    ScorpionTrackShareVehicleEntity,
    async_add_vehicle_entities,
    format_coordinates,
    format_location,
)

PARALLEL_UPDATES = 0

type SensorValue = StateType | date | datetime


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackAccountSensorDescription(SensorEntityDescription):
    """Describe a portal-account sensor."""

    value_fn: Callable[[ScorpionTrackAccountData], SensorValue]


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackAccountVehicleSensorDescription(SensorEntityDescription):
    """Describe a portal-account vehicle sensor."""

    value_fn: Callable[
        [ScorpionTrackAccountData, ScorpionTrackVehicleSummary], SensorValue
    ]
    unit_fn: Callable[[ScorpionTrackAccountData], str | None] | None = None
    uses_speed_unit: bool = False


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackShareSensorDescription(SensorEntityDescription):
    """Describe a shared-location sensor."""

    value_fn: Callable[[ScorpionTrackShare], SensorValue]


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackShareVehicleSensorDescription(SensorEntityDescription):
    """Describe a shared-location vehicle sensor."""

    value_fn: Callable[[ScorpionTrackShare, ScorpionTrackVehicle], SensorValue]
    uses_speed_unit: bool = False


ACCOUNT_SENSORS: tuple[ScorpionTrackAccountSensorDescription, ...] = (
    ScorpionTrackAccountSensorDescription(
        key="vehicle_count",
        name="Vehicle Count",
        icon="mdi:car-multiple",
        value_fn=lambda account: len(account.vehicles),
    ),
    ScorpionTrackAccountSensorDescription(
        key="unread_alerts",
        name="Unread Alerts",
        icon="mdi:bell-badge",
        value_fn=lambda account: account.unread_alerts,
    ),
    ScorpionTrackAccountSensorDescription(
        key="latest_alert",
        name="Latest Alert",
        icon="mdi:alert-circle-outline",
        value_fn=lambda account: (
            account.latest_alert.summary if account.latest_alert is not None else None
        ),
    ),
    ScorpionTrackAccountSensorDescription(
        key="latest_alert_time",
        name="Latest Alert Time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-alert-outline",
        value_fn=lambda account: (
            account.latest_alert.timestamp if account.latest_alert is not None else None
        ),
    ),
    ScorpionTrackAccountSensorDescription(
        key="last_refreshed",
        name="Last Refreshed",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-outline",
        value_fn=lambda account: account.fetched_at,
    ),
    ScorpionTrackAccountSensorDescription(
        key="user_id",
        name="User ID",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:identifier",
        value_fn=lambda account: account.user_id,
    ),
)

ACCOUNT_VEHICLE_SENSORS: tuple[ScorpionTrackAccountVehicleSensorDescription, ...] = (
    ScorpionTrackAccountVehicleSensorDescription(
        key="status",
        name="Status",
        icon="mdi:car-info",
        value_fn=lambda account, vehicle: vehicle.status,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="portal_state",
        name="Portal State",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:code-braces",
        value_fn=lambda account, vehicle: vehicle.raw_state,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="location",
        name="Location",
        icon="mdi:map-marker",
        value_fn=lambda account, vehicle: (
            format_location(
                vehicle.position.latitude,
                vehicle.position.longitude,
                vehicle.position.address,
            )
            if vehicle.position is not None
            else None
        ),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="speed",
        name="Speed",
        device_class=SensorDeviceClass.SPEED,
        icon="mdi:speedometer",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        uses_speed_unit=True,
        value_fn=lambda account, vehicle: (
            vehicle.position.speed_kmh if vehicle.position is not None else None
        ),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="heading",
        name="Heading",
        icon="mdi:compass",
        suggested_display_precision=0,
        native_unit_of_measurement="deg",
        value_fn=lambda account, vehicle: (
            round(vehicle.position.bearing)
            if vehicle.position is not None and vehicle.position.bearing is not None
            else None
        ),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="odometer",
        name="Odometer",
        suggested_display_precision=1,
        icon="mdi:counter",
        value_fn=lambda account, vehicle: (
            vehicle.odometer / 1.609344
            if vehicle.odometer is not None and account.uses_miles
            else vehicle.odometer
        ),
        unit_fn=lambda account: (
            UnitOfLength.MILES if account.uses_miles else UnitOfLength.KILOMETERS
        ),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="battery_voltage",
        name="Battery Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:car-battery",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value_fn=lambda account, vehicle: vehicle.vehicle_voltage,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="backup_battery_voltage",
        name="Backup Battery Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:battery-medium",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value_fn=lambda account, vehicle: vehicle.backup_battery_voltage,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="gps_satellites",
        name="GPS Satellites",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:satellite-variant",
        value_fn=lambda account, vehicle: (
            vehicle.position.gps_satellites if vehicle.position is not None else None
        ),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="gps_hdop",
        name="GPS HDOP",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        icon="mdi:crosshairs-question",
        value_fn=lambda account, vehicle: (
            vehicle.position.hdop if vehicle.position is not None else None
        ),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="last_reported",
        name="Last Reported",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-outline",
        value_fn=lambda account, vehicle: (
            vehicle.position.timestamp
            if vehicle.position is not None
            else vehicle.updated_at
        ),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="installed",
        name="Installed",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar-check",
        value_fn=lambda account, vehicle: vehicle.installed_at,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="unit_last_checked_in",
        name="Unit Last Checked In",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:router-wireless",
        value_fn=lambda account, vehicle: vehicle.unit_last_checked_in,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="last_service_date",
        name="Last Service Date",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:wrench-clock",
        value_fn=lambda account, vehicle: _as_date(vehicle.last_service_date),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="registration",
        name="Registration",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:card-text-outline",
        value_fn=lambda account, vehicle: vehicle.registration,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="description",
        name="Description",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:text-box-outline",
        value_fn=lambda account, vehicle: vehicle.description,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="alias",
        name="Alias",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:badge-account-outline",
        value_fn=lambda account, vehicle: vehicle.alias,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="colour",
        name="Colour",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:palette-outline",
        value_fn=lambda account, vehicle: vehicle.colour,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="fuel_type",
        name="Fuel Type",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:gas-station-outline",
        value_fn=lambda account, vehicle: vehicle.fuel_type,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="battery_type",
        name="Battery Type",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:battery-outline",
        value_fn=lambda account, vehicle: vehicle.battery_type,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="make",
        name="Make",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:factory",
        value_fn=lambda account, vehicle: vehicle.make,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="model",
        name="Model",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:car-side",
        value_fn=lambda account, vehicle: vehicle.model,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="vehicle_type",
        name="Vehicle Type",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:car-multiple",
        value_fn=lambda account, vehicle: vehicle.vehicle_type,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="unit_model",
        name="Unit Model",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:chip",
        value_fn=lambda account, vehicle: vehicle.unit_model,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="unit_make",
        name="Unit Make",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:chip",
        value_fn=lambda account, vehicle: vehicle.unit_make,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="gps_antenna_voltage",
        name="GPS Antenna Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:antenna",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value_fn=lambda account, vehicle: vehicle.gps_antenna_voltage,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="gps_antenna_current",
        name="GPS Antenna Current",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        native_unit_of_measurement="mA",
        icon="mdi:current-ac",
        value_fn=lambda account, vehicle: vehicle.gps_antenna_current,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="pending_command_count",
        name="Pending Command Count",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:progress-clock",
        value_fn=lambda account, vehicle: vehicle.pending_commands_count,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="mot_due",
        name="MOT Due",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar",
        value_fn=lambda account, vehicle: _as_date(vehicle.mot_due),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="tax_due",
        name="Tax Due",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar",
        value_fn=lambda account, vehicle: _as_date(vehicle.tax_due),
    ),
)

SHARE_SENSORS: tuple[ScorpionTrackShareSensorDescription, ...] = (
    ScorpionTrackShareSensorDescription(
        key="share_title",
        name="Share Title",
        icon="mdi:share-variant",
        value_fn=lambda share: share.title,
    ),
    ScorpionTrackShareSensorDescription(
        key="shared_by",
        name="Shared By",
        icon="mdi:account",
        value_fn=lambda share: share.owner_name,
    ),
    ScorpionTrackShareSensorDescription(
        key="share_created",
        name="Share Created",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar-plus",
        value_fn=lambda share: share.created_at,
    ),
    ScorpionTrackShareSensorDescription(
        key="share_expires",
        name="Share Expires",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar-clock",
        value_fn=lambda share: share.expires_at,
    ),
)

SHARE_VEHICLE_SENSORS: tuple[ScorpionTrackShareVehicleSensorDescription, ...] = (
    ScorpionTrackShareVehicleSensorDescription(
        key="status",
        name="Status",
        icon="mdi:car-info",
        value_fn=lambda share, vehicle: vehicle.status,
    ),
    ScorpionTrackShareVehicleSensorDescription(
        key="location",
        name="Location",
        icon="mdi:map-marker",
        value_fn=lambda share, vehicle: format_location(
            vehicle.position.latitude,
            vehicle.position.longitude,
            vehicle.position.address,
        ),
    ),
    ScorpionTrackShareVehicleSensorDescription(
        key="speed",
        name="Speed",
        device_class=SensorDeviceClass.SPEED,
        icon="mdi:speedometer",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        uses_speed_unit=True,
        value_fn=lambda share, vehicle: vehicle.position.speed_kmh,
    ),
    ScorpionTrackShareVehicleSensorDescription(
        key="heading",
        name="Heading",
        icon="mdi:compass",
        suggested_display_precision=0,
        native_unit_of_measurement="deg",
        value_fn=lambda share, vehicle: (
            round(vehicle.position.bearing)
            if vehicle.position.bearing is not None
            else None
        ),
    ),
    ScorpionTrackShareVehicleSensorDescription(
        key="last_reported",
        name="Last Reported",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-outline",
        value_fn=lambda share, vehicle: vehicle.position.timestamp,
    ),
    ScorpionTrackShareVehicleSensorDescription(
        key="share_expires",
        name="Share Expires",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar-clock",
        value_fn=lambda share, vehicle: share.expires_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScorpionTrackConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up ScorpionTrack sensors."""
    coordinator = entry.runtime_data
    if isinstance(coordinator, ScorpionTrackAccountCoordinator):
        account_coordinator = coordinator
        async_add_entities(
            ScorpionTrackAccountSensor(account_coordinator, description)
            for description in ACCOUNT_SENSORS
        )
        async_add_vehicle_entities(
            entry,
            account_coordinator,
            async_add_entities,
            lambda vehicle_id: (
                ScorpionTrackAccountVehicleSensor(
                    account_coordinator, vehicle_id, description
                )
                for description in ACCOUNT_VEHICLE_SENSORS
            ),
        )
        return

    share_coordinator = coordinator
    async_add_entities(
        ScorpionTrackShareSensor(share_coordinator, description)
        for description in SHARE_SENSORS
    )
    async_add_vehicle_entities(
        entry,
        share_coordinator,
        async_add_entities,
        lambda vehicle_id: (
            ScorpionTrackShareVehicleSensor(share_coordinator, vehicle_id, description)
            for description in SHARE_VEHICLE_SENSORS
        ),
    )


class ScorpionTrackAccountSensor(ScorpionTrackAccountEntity, SensorEntity):
    """Represent a portal-account sensor."""

    entity_description: ScorpionTrackAccountSensorDescription

    def __init__(
        self,
        coordinator: ScorpionTrackAccountCoordinator,
        description: ScorpionTrackAccountSensorDescription,
    ) -> None:
        """Initialize the account sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.account_identifier}_{description.key}"

    @property
    @override
    def native_value(self) -> SensorValue:
        """Return the native sensor value."""
        return self.entity_description.value_fn(self.account)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attributes = self.common_account_attributes()
        if self.entity_description.key == "latest_alert":
            latest_alert = self.account.latest_alert
            if latest_alert is not None:
                attributes.update(latest_alert.as_attribute_dict())
            attributes["recent_alerts"] = _recent_alert_attributes(self.account)
        elif self.entity_description.key == "unread_alerts":
            attributes["recent_alerts"] = _recent_alert_attributes(self.account)
        return attributes


class ScorpionTrackAccountVehicleSensor(
    ScorpionTrackAccountVehicleEntity, SensorEntity
):
    """Represent a portal-account vehicle sensor."""

    entity_description: ScorpionTrackAccountVehicleSensorDescription

    def __init__(
        self,
        coordinator: ScorpionTrackAccountCoordinator,
        vehicle_id: int,
        description: ScorpionTrackAccountVehicleSensorDescription,
    ) -> None:
        """Initialize the vehicle sensor."""
        super().__init__(coordinator, vehicle_id)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.account_identifier}_{vehicle_id}_{description.key}"
        )

    @property
    @override
    def native_value(self) -> SensorValue:
        """Return the native sensor value."""
        value = self.entity_description.value_fn(self.account, self.vehicle)
        if self.entity_description.uses_speed_unit and isinstance(value, float):
            return convert_speed(value, self.coordinator.speed_unit, precision=2)
        return value

    @property
    @override
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit of measurement."""
        if self.entity_description.uses_speed_unit:
            return self.coordinator.speed_unit
        if self.entity_description.unit_fn is not None:
            return self.entity_description.unit_fn(self.account)
        return super().native_unit_of_measurement

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attributes = self.common_vehicle_attributes()
        if self.entity_description.key == "location":
            position = self.vehicle.position
            attributes["formatted_location"] = self.native_value
            attributes["coordinates"] = (
                format_coordinates(position.latitude, position.longitude)
                if position is not None
                else None
            )
        return attributes


class ScorpionTrackShareSensor(ScorpionTrackShareEntity, SensorEntity):
    """Represent a shared-location sensor."""

    entity_description: ScorpionTrackShareSensorDescription

    def __init__(
        self,
        coordinator: ScorpionTrackShareCoordinator,
        description: ScorpionTrackShareSensorDescription,
    ) -> None:
        """Initialize the share sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.data.id}_share_{description.key}"

    @property
    @override
    def native_value(self) -> SensorValue:
        """Return the native sensor value."""
        return self.entity_description.value_fn(self.share)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return self.share_common_attributes()


class ScorpionTrackShareVehicleSensor(ScorpionTrackShareVehicleEntity, SensorEntity):
    """Represent a shared-location vehicle sensor."""

    entity_description: ScorpionTrackShareVehicleSensorDescription

    def __init__(
        self,
        coordinator: ScorpionTrackShareCoordinator,
        vehicle_id: int,
        description: ScorpionTrackShareVehicleSensorDescription,
    ) -> None:
        """Initialize the vehicle sensor."""
        super().__init__(coordinator, vehicle_id)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.data.id}_{vehicle_id}_{description.key}"

    @property
    @override
    def native_value(self) -> SensorValue:
        """Return the native sensor value."""
        value = self.entity_description.value_fn(self.share, self.vehicle)
        if self.entity_description.uses_speed_unit and isinstance(value, float):
            return convert_speed(value, self.coordinator.speed_unit)
        return value

    @property
    @override
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit of measurement."""
        if self.entity_description.uses_speed_unit:
            return self.coordinator.speed_unit
        return super().native_unit_of_measurement

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attributes = self.common_location_attributes()
        if self.entity_description.key == "location":
            position = self.vehicle.position
            attributes["formatted_location"] = self.native_value
            attributes["coordinates"] = format_coordinates(
                position.latitude, position.longitude
            )
        return attributes


def _as_date(value: date | datetime | None) -> date | None:
    """Return a date value for Home Assistant date sensors."""
    if isinstance(value, datetime):
        return value.date()
    return value


def _recent_alert_attributes(
    account: ScorpionTrackAccountData,
) -> list[dict[str, object]]:
    """Return a compact recent-alert list for state attributes."""
    return [
        {**alert.as_attribute_dict(), "summary": alert.summary}
        for alert in account.alerts
    ]
