"""Binary sensor platform for ScorpionTrack Share."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .share_coordinator import (
    ScorpionTrackShareConfigEntry,
    ScorpionTrackShareCoordinator,
)
from .share_entity import ScorpionTrackEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a ScorpionTrack binary sensor."""

    value_fn: Callable[[ScorpionTrackBinarySensorEntity], bool]


BINARY_SENSOR_DESCRIPTIONS: tuple[ScorpionTrackBinarySensorDescription, ...] = (
    ScorpionTrackBinarySensorDescription(
        key="ignition",
        name="Ignition",
        icon="mdi:engine",
        value_fn=lambda entity: entity.vehicle.position.ignition is True,
    ),
    ScorpionTrackBinarySensorDescription(
        key="location_stale",
        name="Location Stale",
        icon="mdi:clock-alert-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda entity: entity.position_is_stale(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScorpionTrackShareConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ScorpionTrack binary sensor entities."""
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
            ScorpionTrackBinarySensorEntity(coordinator, vehicle_id, description)
            for vehicle_id in new_vehicle_ids
            for description in BINARY_SENSOR_DESCRIPTIONS
        )

    _async_add_missing_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_missing_entities))


class ScorpionTrackBinarySensorEntity(ScorpionTrackEntity, BinarySensorEntity):
    """Represent a ScorpionTrack binary sensor."""

    _attr_has_entity_name = True

    entity_description: ScorpionTrackBinarySensorDescription

    def __init__(
        self,
        coordinator: ScorpionTrackShareCoordinator,
        vehicle_id: int,
        description: ScorpionTrackBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, vehicle_id)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.data.id}_{vehicle_id}_{description.key}"
        self._attr_name = description.name

    @property
    @override
    def is_on(self) -> bool:
        """Return the binary sensor state."""
        return self.entity_description.value_fn(self)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, object]:
        """Return extra state attributes."""
        return self.common_location_attributes()
