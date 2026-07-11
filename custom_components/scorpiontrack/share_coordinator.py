"""Coordinator for ScorpionTrack Share."""

from __future__ import annotations

import logging
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pyscorpiontrack import (
    ScorpionTrackClient,
    ScorpionTrackConnectionError,
    ScorpionTrackInvalidTokenError,
    ScorpionTrackShare,
    ScorpionTrackShareUnavailableError,
    ScorpionTrackVehicle,
)

from .const import DOMAIN, SHARE_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


type ScorpionTrackShareConfigEntry = ConfigEntry[ScorpionTrackShareCoordinator]


class ScorpionTrackShareCoordinator(DataUpdateCoordinator[ScorpionTrackShare]):
    """Coordinate shared-location updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ScorpionTrackClient,
        entry: ScorpionTrackShareConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.vehicles_by_id: dict[int, ScorpionTrackVehicle] = {}
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=SHARE_SCAN_INTERVAL,
        )

    @override
    async def _async_update_data(self) -> ScorpionTrackShare:
        """Fetch updated share data."""
        try:
            share = await self.client.async_get_share()
        except ScorpionTrackConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
            ) from err
        except ScorpionTrackInvalidTokenError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="invalid_token",
            ) from err
        except ScorpionTrackShareUnavailableError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="share_unavailable",
            ) from err
        else:
            self.vehicles_by_id = {vehicle.id: vehicle for vehicle in share.vehicles}
            return share
