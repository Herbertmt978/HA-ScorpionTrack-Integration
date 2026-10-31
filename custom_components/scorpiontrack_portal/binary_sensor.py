"""Binary sensor platform for ScorpionTrack Portal."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from pyscorpiontrack import ScorpionTrackVehicle

from .account_api import ScorpionTrackVehicleSummary
from .const import STALE_POSITION_AFTER
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


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackAccountBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a portal-account vehicle binary sensor."""

    value_fn: Callable[[ScorpionTrackVehicleSummary], bool | None]


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackShareBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a shared-location vehicle binary sensor."""

    value_fn: Callable[[ScorpionTrackVehicle], bool | None]


def _position_is_stale(timestamp: datetime | None) -> bool:
    """Return True when there is no position time or it is at least 24 hours old."""
    return timestamp is None or dt_util.utcnow() - timestamp >= STALE_POSITION_AFTER


ACCOUNT_BINARY_SENSORS: tuple[ScorpionTrackAccountBinarySensorDescription, ...] = (
    ScorpionTrackAccountBinarySensorDescription(
        key="ignition",
        translation_key="ignition",
        value_fn=lambda vehicle: (
            vehicle.position.ignition if vehicle.position is not None else None
        ),
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="engine",
        translation_key="engine",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda vehicle: (
            vehicle.position.engine if vehicle.position is not None else None
        ),
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="transport_mode_active",
        translation_key="transport_mode",
        value_fn=lambda vehicle: vehicle.transport_mode_active,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="garage_mode_active",
        translation_key="garage_mode",
        value_fn=lambda vehicle: vehicle.garage_mode_active,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="no_alert_mode_active",
        translation_key="no_alert_mode",
        value_fn=lambda vehicle: vehicle.no_alert_mode_active,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="armed_mode_enabled",
        translation_key="armed_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda vehicle: vehicle.armed_mode_enabled,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="ewm_enabled",
        translation_key="ewm",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda vehicle: vehicle.ewm_enabled,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="g_sense_enabled",
        translation_key="g_sense",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda vehicle: vehicle.g_sense_enabled,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="pending_commands",
        translation_key="pending_commands",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda vehicle: vehicle.pending_commands_count > 0,
    ),
    # Entities removed in 0.5.0 are available again, disabled by default. Their
    # keys end in "_v2" so their unique IDs differ from 0.4.0: Home Assistant
    # would otherwise restore the registry entries 0.5.0 deleted, enabled.
    ScorpionTrackAccountBinarySensorDescription(
        key="location_stale_v2",
        translation_key="location_stale",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda vehicle: _position_is_stale(
            vehicle.position.timestamp if vehicle.position is not None else None
        ),
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="driver_module_v2",
        translation_key="driver_module",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda vehicle: vehicle.driver_module,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="install_complete_v2",
        translation_key="install_complete",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda vehicle: vehicle.install_complete,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="immobiliser_fitted_v2",
        translation_key="immobiliser_fitted",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda vehicle: vehicle.immobiliser_fitted,
    ),
)

SHARE_BINARY_SENSORS: tuple[ScorpionTrackShareBinarySensorDescription, ...] = (
    ScorpionTrackShareBinarySensorDescription(
        key="ignition",
        translation_key="ignition",
        value_fn=lambda vehicle: vehicle.position.ignition,
    ),
    # Removed in 0.5.0 and available again, disabled by default (see above).
    ScorpionTrackShareBinarySensorDescription(
        key="location_stale_v2",
        translation_key="location_stale",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda vehicle: _position_is_stale(vehicle.position.timestamp),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScorpionTrackConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up ScorpionTrack binary sensors."""
    coordinator = entry.runtime_data
    if isinstance(coordinator, ScorpionTrackAccountCoordinator):
        account_coordinator = coordinator
        async_add_vehicle_entities(
            entry,
            account_coordinator,
            async_add_entities,
            lambda vehicle_id: (
                ScorpionTrackAccountBinarySensor(
                    account_coordinator, vehicle_id, description
                )
                for description in ACCOUNT_BINARY_SENSORS
            ),
        )
        return

    share_coordinator = coordinator
    async_add_vehicle_entities(
        entry,
        share_coordinator,
        async_add_entities,
        lambda vehicle_id: (
            ScorpionTrackShareBinarySensor(share_coordinator, vehicle_id, description)
            for description in SHARE_BINARY_SENSORS
        ),
    )


class ScorpionTrackAccountBinarySensor(
    ScorpionTrackAccountVehicleEntity, BinarySensorEntity
):
    """Represent a portal-account vehicle binary sensor."""

    entity_description: ScorpionTrackAccountBinarySensorDescription

    def __init__(
        self,
        coordinator: ScorpionTrackAccountCoordinator,
        vehicle_id: int,
        description: ScorpionTrackAccountBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, vehicle_id, description.key)
        self.entity_description = description

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the sensor state."""
        return self.entity_description.value_fn(self.vehicle)


class ScorpionTrackShareBinarySensor(
    ScorpionTrackShareVehicleEntity, BinarySensorEntity
):
    """Represent a shared-location vehicle binary sensor."""

    entity_description: ScorpionTrackShareBinarySensorDescription

    def __init__(
        self,
        coordinator: ScorpionTrackShareCoordinator,
        vehicle_id: int,
        description: ScorpionTrackShareBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, vehicle_id, description.key)
        self.entity_description = description

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the sensor state."""
        return self.entity_description.value_fn(self.vehicle)
