"""The ScorpionTrack Portal integration."""

from __future__ import annotations

import logging

from aiohttp import CookieJar
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import (
    async_create_clientsession,
    async_get_clientsession,
)
from pyscorpiontrack import ScorpionTrackClient as ScorpionTrackShareClient

from .account_api import ScorpionTrackAccountClient
from .const import CONF_SETUP_TYPE, CONF_SHARE_TOKEN, PLATFORMS, SETUP_TYPE_ACCOUNT
from .coordinator import (
    ScorpionTrackAccountCoordinator,
    ScorpionTrackConfigEntry,
    ScorpionTrackShareCoordinator,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ScorpionTrackConfigEntry
) -> bool:
    """Set up ScorpionTrack Portal from a config entry."""
    coordinator: ScorpionTrackAccountCoordinator | ScorpionTrackShareCoordinator
    if entry.data[CONF_SETUP_TYPE] == SETUP_TYPE_ACCOUNT:
        share_token: str | None = entry.data.get(CONF_SHARE_TOKEN)
        coordinator = ScorpionTrackAccountCoordinator(
            hass,
            ScorpionTrackAccountClient(
                session=async_create_clientsession(
                    hass, cookie_jar=CookieJar(quote_cookie=False)
                ),
                email=entry.data[CONF_EMAIL],
                password=entry.data[CONF_PASSWORD],
            ),
            entry,
            share_client=(
                ScorpionTrackShareClient(
                    session=async_get_clientsession(hass), token=share_token
                )
                if share_token
                else None
            ),
        )
    else:
        coordinator = ScorpionTrackShareCoordinator(
            hass,
            ScorpionTrackShareClient(
                session=async_get_clientsession(hass),
                token=entry.data[CONF_SHARE_TOKEN],
            ),
            entry,
        )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ScorpionTrackConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(
    hass: HomeAssistant, entry: ScorpionTrackConfigEntry
) -> bool:
    """Migrate an older config entry."""
    if entry.version == 1 and entry.minor_version < 2:
        # 1.2 keeps the optional hybrid share token with the connection data.
        options = dict(entry.options)
        data = dict(entry.data)
        if share_token := str(options.pop(CONF_SHARE_TOKEN, "") or "").strip():
            data[CONF_SHARE_TOKEN] = share_token
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, minor_version=2
        )

    _LOGGER.debug(
        "Migrated ScorpionTrack Portal entry to version %s.%s",
        entry.version,
        entry.minor_version,
    )
    return True
