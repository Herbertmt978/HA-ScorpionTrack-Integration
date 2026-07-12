"""Switch platform for ScorpionTrack Account."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .account_api import (
    ScorpionTrackAuthError,
    ScorpionTrackConnectionError,
    ScorpionTrackPortalError,
)
from .account_coordinator import (
    ScorpionTrackAccountConfigEntry,
    ScorpionTrackAccountCoordinator,
)
from .account_entity import ScorpionTrackVehicleEntity
from .const import DOMAIN

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackVehicleSwitchDescription(SwitchEntityDescription):
    """Describe a vehicle-level switch."""

    mode_key: str
    value_fn: Callable[[object], bool | None]


VEHICLE_SWITCH_DESCRIPTIONS: tuple[ScorpionTrackVehicleSwitchDescription, ...] = (
    ScorpionTrackVehicleSwitchDescription(
        key="privacy_mode",
        name="Privacy Mode",
        icon="mdi:incognito",
        mode_key="privacy_mode_enabled",
        value_fn=lambda vehicle: vehicle.privacy_mode_enabled,
    ),
    ScorpionTrackVehicleSwitchDescription(
        key="zero_speed_mode",
        name="Zero-Speed Mode",
        icon="mdi:speedometer-slow",
        mode_key="zero_speed_mode_enabled",
        value_fn=lambda vehicle: vehicle.zero_speed_mode_enabled,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScorpionTrackAccountConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ScorpionTrack vehicle switches."""
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
            ScorpionTrackVehicleSwitchEntity(coordinator, vehicle_id, description)
            for vehicle_id in new_vehicle_ids
            for description in VEHICLE_SWITCH_DESCRIPTIONS
        )

    _async_add_missing_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_missing_entities))


class ScorpionTrackVehicleSwitchEntity(ScorpionTrackVehicleEntity, SwitchEntity):
    """Represent a vehicle-level ScorpionTrack switch."""

    _attr_has_entity_name = True

    entity_description: ScorpionTrackVehicleSwitchDescription

    def __init__(
        self,
        coordinator: ScorpionTrackAccountCoordinator,
        vehicle_id: int,
        description: ScorpionTrackVehicleSwitchDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, vehicle_id)
        self.entity_description = description
        self._attr_unique_id = (
            f"{self.account_identifier}_{vehicle_id}_{description.key}"
        )
        self._attr_name = description.name

    @property
    @override
    def available(self) -> bool:
        """Return if the switch is available."""
        return (
            super().available
            and self.entity_description.value_fn(self.vehicle) is not None
        )

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the switch state."""
        return self.entity_description.value_fn(self.vehicle)

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_set_enabled(True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_set_enabled(False)

    async def _async_set_enabled(self, enabled: bool) -> None:
        """Update the backing portal mode and refresh coordinator data."""
        try:
            await self.coordinator.client.async_set_vehicle_mode(
                self.vehicle.id,
                self.entity_description.mode_key,
                enabled,
            )
        except (
            ScorpionTrackAuthError,
            ScorpionTrackConnectionError,
            ScorpionTrackPortalError,
        ) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="vehicle_mode_update_failed",
                translation_placeholders={
                    "mode": self.entity_description.name or self.entity_description.key
                },
            ) from err

        await self.coordinator.async_request_account_refresh()

    @property
    @override
    def extra_state_attributes(self) -> dict[str, object]:
        """Return extra state attributes."""
        return self.common_vehicle_attributes()
