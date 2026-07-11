"""Coordinator for ScorpionTrack Account."""

from __future__ import annotations

import logging
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .account_api import (
    ScorpionTrackAccountClient,
    ScorpionTrackAccountData,
    ScorpionTrackAuthError,
    ScorpionTrackConnectionError,
    ScorpionTrackPortalError,
    ScorpionTrackVehicleSummary,
)
from .const import ACCOUNT_SCAN_INTERVAL, DOMAIN
from .utils import stable_hash

_LOGGER = logging.getLogger(__name__)


type ScorpionTrackAccountConfigEntry = ConfigEntry[ScorpionTrackAccountCoordinator]


class ScorpionTrackAccountCoordinator(DataUpdateCoordinator[ScorpionTrackAccountData]):
    """Coordinate authenticated ScorpionTrack account updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ScorpionTrackAccountClient,
        entry: ScorpionTrackAccountConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        email_hash = stable_hash(entry.data[CONF_EMAIL])
        unique_id_suffix = (entry.unique_id or "").removeprefix("account_")
        self.account_identifier = (
            f"acct_{email_hash}"
            if unique_id_suffix in ("", email_hash)
            else unique_id_suffix
        )
        self.vehicles_by_id: dict[int, ScorpionTrackVehicleSummary] = {}
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=ACCOUNT_SCAN_INTERVAL,
        )

    @override
    async def _async_update_data(self) -> ScorpionTrackAccountData:
        """Fetch updated account data."""
        try:
            account = await self.client.async_refresh_account()
        except ScorpionTrackConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
            ) from err
        except ScorpionTrackAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="invalid_auth",
            ) from err
        except ScorpionTrackPortalError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="unexpected_response",
            ) from err
        else:
            self.vehicles_by_id = {vehicle.id: vehicle for vehicle in account.vehicles}
            return account
