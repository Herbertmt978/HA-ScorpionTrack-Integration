"""Switch platform for ScorpionTrack Portal."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .account_api import (
    ScorpionTrackAuthError,
    ScorpionTrackConnectionError,
    ScorpionTrackPortalError,
    ScorpionTrackVehicleSummary,
)
from .const import DOMAIN
from .coordinator import ScorpionTrackAccountCoordinator, ScorpionTrackConfigEntry
from .entity import ScorpionTrackAccountVehicleEntity, async_add_vehicle_entities

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackSwitchDescription(SwitchEntityDescription):
    """Describe a portal-account vehicle switch."""

    mode_key: str
    error_translation_key: str
    value_fn: Callable[[ScorpionTrackVehicleSummary], bool | None]


SWITCHES: tuple[ScorpionTrackSwitchDescription, ...] = (
    ScorpionTrackSwitchDescription(
        key="privacy_mode",
        translation_key="privacy_mode",
        mode_key="privacy_mode_enabled",
        error_translation_key="privacy_mode_update_failed",
        value_fn=lambda vehicle: vehicle.privacy_mode_enabled,
    ),
    ScorpionTrackSwitchDescription(
        key="zero_speed_mode",
        translation_key="zero_speed_mode",
        mode_key="zero_speed_mode_enabled",
        error_translation_key="zero_speed_mode_update_failed",
        value_fn=lambda vehicle: vehicle.zero_speed_mode_enabled,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScorpionTrackConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up ScorpionTrack portal-account switches."""
    coordinator = entry.runtime_data
    if not isinstance(coordinator, ScorpionTrackAccountCoordinator):
        return

    async_add_vehicle_entities(
        entry,
        coordinator,
        async_add_entities,
        lambda vehicle_id: (
            ScorpionTrackSwitch(coordinator, vehicle_id, description)
            for description in SWITCHES
        ),
    )


class ScorpionTrackSwitch(ScorpionTrackAccountVehicleEntity, SwitchEntity):
    """Represent a verified portal vehicle mode."""

    entity_description: ScorpionTrackSwitchDescription

    def __init__(
        self,
        coordinator: ScorpionTrackAccountCoordinator,
        vehicle_id: int,
        description: ScorpionTrackSwitchDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, vehicle_id, description.key)
        self.entity_description = description

    @property
    @override
    def available(self) -> bool:
        """Return if the portal reports the mode."""
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
        """Update the portal mode and refresh account data."""
        try:
            await self.coordinator.client.async_set_vehicle_mode(
                self._vehicle_id,
                self.entity_description.mode_key,
                enabled,
            )
        except ScorpionTrackAuthError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_auth",
            ) from err
        except (ScorpionTrackConnectionError, ScorpionTrackPortalError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=self.entity_description.error_translation_key,
            ) from err

        await self.coordinator.async_request_account_refresh()
