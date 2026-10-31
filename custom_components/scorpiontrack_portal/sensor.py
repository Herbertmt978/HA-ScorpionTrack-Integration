"""Sensor platform for ScorpionTrack Portal."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfSpeed,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from pyscorpiontrack import ScorpionTrackShare, ScorpionTrackVehicle

from .account_api import ScorpionTrackAccountData, ScorpionTrackVehicleSummary
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
)

PARALLEL_UPDATES = 0

ACCOUNT_VEHICLE_STATUSES = ["alarm", "alert", "idle", "ignition", "moving", "parked"]
SHARE_VEHICLE_STATUSES = ["idle", "moving", "parked"]

type SensorValue = StateType | date | datetime


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackAccountSensorDescription(SensorEntityDescription):
    """Describe a portal-account sensor."""

    value_fn: Callable[[ScorpionTrackAccountData], SensorValue]


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackAccountVehicleSensorDescription(SensorEntityDescription):
    """Describe a portal-account vehicle sensor."""

    value_fn: Callable[[ScorpionTrackVehicleSummary], SensorValue]
    suggested_unit_fn: Callable[[ScorpionTrackAccountData], str] | None = None


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackShareSensorDescription(SensorEntityDescription):
    """Describe a shared-location sensor."""

    value_fn: Callable[[ScorpionTrackShare], SensorValue]


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackShareVehicleSensorDescription(SensorEntityDescription):
    """Describe a shared-location vehicle sensor."""

    value_fn: Callable[[ScorpionTrackVehicle], SensorValue]
    suggested_unit_fn: Callable[[ScorpionTrackShare], str] | None = None


def _speed_unit(uses_miles: bool) -> str:
    """Return the speed unit matching the ScorpionTrack distance preference."""
    return UnitOfSpeed.MILES_PER_HOUR if uses_miles else UnitOfSpeed.KILOMETERS_PER_HOUR


def _status(value: str | None, options: list[str]) -> str | None:
    """Return a known status key, or None when the status is not recognised."""
    if value is None:
        return None
    status = value.strip().lower()
    return status if status in options else None


def _as_date(value: date | datetime | None) -> date | None:
    """Return a date value for Home Assistant date sensors."""
    if isinstance(value, datetime):
        return value.date()
    return value


ACCOUNT_SENSORS: tuple[ScorpionTrackAccountSensorDescription, ...] = (
    ScorpionTrackAccountSensorDescription(
        key="unread_alerts",
        translation_key="unread_alerts",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda account: account.unread_alerts,
    ),
    ScorpionTrackAccountSensorDescription(
        key="latest_alert",
        translation_key="latest_alert",
        value_fn=lambda account: (
            account.latest_alert.summary if account.latest_alert is not None else None
        ),
    ),
    ScorpionTrackAccountSensorDescription(
        key="latest_alert_time",
        translation_key="latest_alert_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda account: (
            account.latest_alert.timestamp if account.latest_alert is not None else None
        ),
    ),
)

ACCOUNT_VEHICLE_SENSORS: tuple[ScorpionTrackAccountVehicleSensorDescription, ...] = (
    ScorpionTrackAccountVehicleSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=ACCOUNT_VEHICLE_STATUSES,
        value_fn=lambda vehicle: _status(vehicle.status, ACCOUNT_VEHICLE_STATUSES),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="speed",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda vehicle: (
            vehicle.position.speed_kmh if vehicle.position is not None else None
        ),
        suggested_unit_fn=lambda account: _speed_unit(account.uses_miles),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="heading",
        translation_key="heading",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT_ANGLE,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda vehicle: (
            vehicle.position.bearing if vehicle.position is not None else None
        ),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="odometer",
        translation_key="odometer",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        value_fn=lambda vehicle: vehicle.odometer,
        suggested_unit_fn=lambda account: (
            UnitOfLength.MILES if account.uses_miles else UnitOfLength.KILOMETERS
        ),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda vehicle: vehicle.vehicle_voltage,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="mot_due",
        translation_key="mot_due",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda vehicle: _as_date(vehicle.mot_due),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="tax_due",
        translation_key="tax_due",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda vehicle: _as_date(vehicle.tax_due),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="last_service_date",
        translation_key="last_service_date",
        device_class=SensorDeviceClass.DATE,
        entity_registry_enabled_default=False,
        value_fn=lambda vehicle: _as_date(vehicle.last_service_date),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="last_reported",
        translation_key="last_reported",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda vehicle: (
            vehicle.position.timestamp
            if vehicle.position is not None
            else vehicle.updated_at
        ),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="unit_last_checked_in",
        translation_key="unit_last_checked_in",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda vehicle: vehicle.unit_last_checked_in,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="backup_battery_voltage",
        translation_key="backup_battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda vehicle: vehicle.backup_battery_voltage,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="gps_antenna_voltage",
        translation_key="gps_antenna_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda vehicle: vehicle.gps_antenna_voltage,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="gps_antenna_current",
        translation_key="gps_antenna_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda vehicle: vehicle.gps_antenna_current,
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="gps_satellites",
        translation_key="gps_satellites",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda vehicle: (
            vehicle.position.gps_satellites if vehicle.position is not None else None
        ),
    ),
    ScorpionTrackAccountVehicleSensorDescription(
        key="gps_hdop",
        translation_key="gps_hdop",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda vehicle: (
            vehicle.position.hdop if vehicle.position is not None else None
        ),
    ),
)

SHARE_SENSORS: tuple[ScorpionTrackShareSensorDescription, ...] = (
    ScorpionTrackShareSensorDescription(
        key="share_expires",
        translation_key="share_expires",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda share: share.expires_at,
    ),
)

SHARE_VEHICLE_SENSORS: tuple[ScorpionTrackShareVehicleSensorDescription, ...] = (
    ScorpionTrackShareVehicleSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=SHARE_VEHICLE_STATUSES,
        value_fn=lambda vehicle: _status(vehicle.status, SHARE_VEHICLE_STATUSES),
    ),
    ScorpionTrackShareVehicleSensorDescription(
        key="speed",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda vehicle: vehicle.position.speed_kmh,
        suggested_unit_fn=lambda share: _speed_unit(share.uses_miles),
    ),
    ScorpionTrackShareVehicleSensorDescription(
        key="heading",
        translation_key="heading",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT_ANGLE,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda vehicle: vehicle.position.bearing,
    ),
    ScorpionTrackShareVehicleSensorDescription(
        key="last_reported",
        translation_key="last_reported",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda vehicle: vehicle.position.timestamp,
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
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    @override
    def native_value(self) -> SensorValue:
        """Return the native sensor value."""
        return self.entity_description.value_fn(self.account)


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
        super().__init__(coordinator, vehicle_id, description.key)
        self.entity_description = description
        if (suggested_unit_fn := description.suggested_unit_fn) is not None:
            self._attr_suggested_unit_of_measurement = suggested_unit_fn(
                coordinator.data
            )

    @property
    @override
    def native_value(self) -> SensorValue:
        """Return the native sensor value."""
        return self.entity_description.value_fn(self.vehicle)


class ScorpionTrackShareSensor(ScorpionTrackShareEntity, SensorEntity):
    """Represent a shared-location sensor."""

    entity_description: ScorpionTrackShareSensorDescription

    def __init__(
        self,
        coordinator: ScorpionTrackShareCoordinator,
        description: ScorpionTrackShareSensorDescription,
    ) -> None:
        """Initialize the share sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    @override
    def native_value(self) -> SensorValue:
        """Return the native sensor value."""
        return self.entity_description.value_fn(self.share)


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
        super().__init__(coordinator, vehicle_id, description.key)
        self.entity_description = description
        if (suggested_unit_fn := description.suggested_unit_fn) is not None:
            self._attr_suggested_unit_of_measurement = suggested_unit_fn(
                coordinator.data
            )

    @property
    @override
    def native_value(self) -> SensorValue:
        """Return the native sensor value."""
        return self.entity_description.value_fn(self.vehicle)
