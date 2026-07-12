"""ScorpionTrack integration."""

from __future__ import annotations

from aiohttp import CookieJar
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import (
    async_create_clientsession,
    async_get_clientsession,
)
from pyscorpiontrack import ScorpionTrackClient as ScorpionTrackShareClient

from .account_api import ScorpionTrackAccountClient
from .account_coordinator import ScorpionTrackAccountCoordinator
from .const import (
    CONF_SHARE_TOKEN,
    DOMAIN,
    PLATFORMS,
    SETUP_TYPE_ACCOUNT,
    SETUP_TYPE_SHARE,
    get_setup_type,
    get_share_token,
)
from .share_coordinator import ScorpionTrackShareCoordinator

type ScorpionTrackConfigEntry = ConfigEntry[
    ScorpionTrackAccountCoordinator | ScorpionTrackShareCoordinator
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ScorpionTrackConfigEntry
) -> bool:
    """Set up ScorpionTrack from a config entry."""
    entry_type = get_setup_type(entry.data)

    if entry_type == SETUP_TYPE_ACCOUNT:
        session = async_create_clientsession(
            hass,
            cookie_jar=CookieJar(quote_cookie=False),
        )
        client = ScorpionTrackAccountClient(
            session=session,
            email=entry.data[CONF_EMAIL],
            password=entry.data[CONF_PASSWORD],
        )
        share_token = get_share_token(entry.data, entry.options)
        share_client = (
            ScorpionTrackShareClient(
                session=async_get_clientsession(hass),
                token=share_token,
            )
            if share_token is not None
            else None
        )
        coordinator = ScorpionTrackAccountCoordinator(
            hass,
            client,
            entry,
            share_client=share_client,
        )
    elif entry_type == SETUP_TYPE_SHARE:
        client = ScorpionTrackShareClient(
            session=async_get_clientsession(hass),
            token=entry.data[CONF_SHARE_TOKEN],
        )
        coordinator = ScorpionTrackShareCoordinator(hass, client, entry)
    else:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="unsupported_setup_type",
        )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ScorpionTrackConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(
    hass: HomeAssistant, entry: ScorpionTrackConfigEntry
) -> None:
    """Reload an entry after its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
