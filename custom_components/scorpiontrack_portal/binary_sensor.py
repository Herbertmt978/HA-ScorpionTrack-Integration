"""Binary sensor platform for ScorpionTrack Portal."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pyscorpiontrack import ScorpionTrackVehicle

from .account_api import ScorpionTrackVehicleSummary
from .coordinator import (
    ScorpionTrackAccountCoordinator,
    ScorpionTrackConfigEntry,
    ScorpionTrackShareCoordinator,
)
from .entity import (
    ScorpionTrackAccountVehicleEntity,
    ScorpionTrackShareVehicleEntity,
    async_add_vehicle_entities,
    position_is_stale,
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


ACCOUNT_BINARY_SENSORS: tuple[ScorpionTrackAccountBinarySensorDescription, ...] = (
    ScorpionTrackAccountBinarySensorDescription(
        key="ignition",
        name="Ignition",
        icon="mdi:key-variant",
        value_fn=lambda vehicle: (
            vehicle.position.ignition if vehicle.position is not None else None
        ),
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="engine",
        name="Engine",
        icon="mdi:engine",
        value_fn=lambda vehicle: (
            vehicle.position.engine if vehicle.position is not None else None
        ),
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="transport_mode_active",
        name="Transport Mode Active",
        icon="mdi:truck-fast",
        value_fn=lambda vehicle: vehicle.transport_mode_active,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="garage_mode_active",
        name="Garage Mode Active",
        icon="mdi:garage-variant",
        value_fn=lambda vehicle: vehicle.garage_mode_active,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="no_alert_mode_active",
        name="No-Alert Mode Active",
        icon="mdi:bell-off",
        value_fn=lambda vehicle: vehicle.no_alert_mode_active,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="ewm_enabled",
        name="EWM Enabled",
        icon="mdi:motion-sensor",
        value_fn=lambda vehicle: vehicle.ewm_enabled,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="armed_mode_enabled",
        name="Armed Mode Enabled",
        icon="mdi:shield-car",
        value_fn=lambda vehicle: vehicle.armed_mode_enabled,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="driver_module",
        name="Driver Module Fitted",
        icon="mdi:key-chain-variant",
        value_fn=lambda vehicle: vehicle.driver_module,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="g_sense_enabled",
        name="G-Sense Enabled",
        icon="mdi:car-emergency",
        value_fn=lambda vehicle: vehicle.g_sense_enabled,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="install_complete",
        name="Installation Complete",
        icon="mdi:check-decagram",
        value_fn=lambda vehicle: vehicle.install_complete,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="immobiliser_fitted",
        name="Immobiliser Fitted",
        icon="mdi:shield-car",
        value_fn=lambda vehicle: vehicle.immobiliser_fitted,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="pending_commands",
        name="Pending Commands",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:progress-clock",
        value_fn=lambda vehicle: vehicle.pending_commands_count > 0,
    ),
    ScorpionTrackAccountBinarySensorDescription(
        key="location_stale",
        name="Location Stale",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:map-marker-alert",
        value_fn=lambda vehicle: position_is_stale(
            vehicle.position.timestamp if vehicle.position is not None else None
        ),
    ),
)

SHARE_BINARY_SENSORS: tuple[ScorpionTrackShareBinarySensorDescription, ...] = (
    ScorpionTrackShareBinarySensorDescription(
        key="ignition",
        name="Ignition",
        icon="mdi:engine",
        value_fn=lambda vehicle: vehicle.position.ignition,
    ),
    ScorpionTrackShareBinarySensorDescription(
        key="location_stale",
        name="Location Stale",
        icon="mdi:clock-alert-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda vehicle: position_is_stale(vehicle.position.timestamp),
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
        super().__init__(coordinator, vehicle_id)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.account_identifier}_{vehicle_id}_{description.key}"
        )

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the sensor state."""
        return self.entity_description.value_fn(self.vehicle)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return self.common_vehicle_attributes()


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
        super().__init__(coordinator, vehicle_id)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.data.id}_{vehicle_id}_{description.key}"

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the sensor state."""
        return self.entity_description.value_fn(self.vehicle)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return self.common_location_attributes()
