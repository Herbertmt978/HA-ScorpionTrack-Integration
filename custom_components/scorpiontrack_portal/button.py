"""Button platform for ScorpionTrack Portal."""

from __future__ import annotations

from typing import override

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .account_api import (
    ScorpionTrackAuthError,
    ScorpionTrackConnectionError,
    ScorpionTrackPortalError,
)
from .const import DOMAIN
from .coordinator import ScorpionTrackAccountCoordinator, ScorpionTrackConfigEntry
from .entity import ScorpionTrackAccountEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScorpionTrackConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up ScorpionTrack portal-account buttons."""
    coordinator = entry.runtime_data
    if isinstance(coordinator, ScorpionTrackAccountCoordinator):
        async_add_entities([ScorpionTrackMarkAlertsReadButton(coordinator)])


class ScorpionTrackMarkAlertsReadButton(ScorpionTrackAccountEntity, ButtonEntity):
    """Mark every unread portal alert as read."""

    _attr_translation_key = "mark_alerts_read"

    def __init__(self, coordinator: ScorpionTrackAccountCoordinator) -> None:
        """Initialize the alert button."""
        super().__init__(coordinator, "mark_alerts_read")

    @override
    async def async_press(self) -> None:
        """Mark unread alerts as read and refresh account data."""
        try:
            await self.coordinator.client.async_mark_all_alerts_read()
        except ScorpionTrackAuthError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_auth",
            ) from err
        except (ScorpionTrackConnectionError, ScorpionTrackPortalError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="mark_alerts_read_failed",
            ) from err

        await self.coordinator.async_request_account_refresh()
