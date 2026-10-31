"""Base entities for ScorpionTrack Portal."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import override

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from pyscorpiontrack import ScorpionTrackShare, ScorpionTrackVehicle

from .account_api import ScorpionTrackAccountData, ScorpionTrackVehicleSummary
from .const import DOMAIN, MANUFACTURER, SHARE_DEFAULT_NAME
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


class ScorpionTrackAccountEntity(CoordinatorEntity[ScorpionTrackAccountCoordinator]):
    """Base class for portal-account entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ScorpionTrackAccountCoordinator, key: str) -> None:
        """Initialize an account-level entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.account_identifier}_{key}"
        self._attr_device_info = coordinator.account_device_info

    @property
    def account(self) -> ScorpionTrackAccountData:
        """Return the latest account snapshot."""
        return self.coordinator.data


class ScorpionTrackAccountVehicleEntity(
    CoordinatorEntity[ScorpionTrackAccountCoordinator]
):
    """Base class for portal-account vehicle entities."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: ScorpionTrackAccountCoordinator, vehicle_id: int, key: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._vehicle_id = vehicle_id
        self._last_vehicle = coordinator.vehicles_by_id[vehicle_id]
        vehicle = self._last_vehicle
        account_identifier = coordinator.account_identifier
        self._attr_unique_id = f"{account_identifier}_{vehicle_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{account_identifier}_vehicle_{vehicle_id}")},
            via_device_id=coordinator.account_device_id,
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


class ScorpionTrackShareEntity(CoordinatorEntity[ScorpionTrackShareCoordinator]):
    """Base class for shared-location entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ScorpionTrackShareCoordinator, key: str) -> None:
        """Initialize a share-level entity."""
        super().__init__(coordinator)
        share = coordinator.data
        self._attr_unique_id = f"{share.id}_share_{key}"
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


class ScorpionTrackShareVehicleEntity(CoordinatorEntity[ScorpionTrackShareCoordinator]):
    """Base class for shared-location vehicle entities."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: ScorpionTrackShareCoordinator, vehicle_id: int, key: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._vehicle_id = vehicle_id
        self._last_vehicle = coordinator.vehicles_by_id[vehicle_id]
        vehicle = self._last_vehicle
        share_id = coordinator.data.id
        self._attr_unique_id = f"{share_id}_{vehicle_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{share_id}_{vehicle_id}")},
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
