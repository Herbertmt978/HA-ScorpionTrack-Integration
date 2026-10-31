"""The ScorpionTrack Portal integration."""

from __future__ import annotations

import logging
import re

from aiohttp import CookieJar
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import (
    async_create_clientsession,
    async_get_clientsession,
)
from pyscorpiontrack import ScorpionTrackClient as ScorpionTrackShareClient

from .account_api import ScorpionTrackAccountClient
from .const import (
    CONF_SETUP_TYPE,
    CONF_SHARE_TOKEN,
    CONF_SPEED_UNIT,
    DOMAIN,
    PLATFORMS,
    SETUP_TYPE_ACCOUNT,
)
from .coordinator import (
    ScorpionTrackAccountCoordinator,
    ScorpionTrackConfigEntry,
    ScorpionTrackShareCoordinator,
    hybrid_share_issue_id,
)

_LOGGER = logging.getLogger(__name__)

# Unique ID patterns for entities removed in config entry version 1.3.
_REMOVED_ENTITY_PATTERNS: dict[str, re.Pattern[str]] = {
    Platform.SENSOR: re.compile(
        r"_(?:vehicle_count|last_refreshed|user_id|portal_state|location|installed"
        r"|registration|description|alias|colour|fuel_type|battery_type|make|model"
        r"|vehicle_type|unit_model|unit_make|pending_command_count|share_title"
        r"|shared_by|share_created)$"
        # A share vehicle's copy of the expiry; the share device keeps its own.
        r"|^\d+_\d+_share_expires$"
    ),
    Platform.BINARY_SENSOR: re.compile(
        r"_(?:location_stale|driver_module|install_complete|immobiliser_fitted)$"
    ),
}


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
    ir.async_delete_issue(hass, DOMAIN, hybrid_share_issue_id(entry))
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

    if entry.version == 1 and entry.minor_version < 3:
        # 1.3 replaces the speed-unit option with Home Assistant's unit settings
        # and removes entities that are no longer provided.
        entity_registry = er.async_get(hass)
        for registry_entry in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        ):
            pattern = _REMOVED_ENTITY_PATTERNS.get(registry_entry.domain)
            if pattern is not None and pattern.search(registry_entry.unique_id):
                entity_registry.async_remove(registry_entry.entity_id)
        options = {
            key: value for key, value in entry.options.items() if key != CONF_SPEED_UNIT
        }
        hass.config_entries.async_update_entry(entry, options=options, minor_version=3)

    _LOGGER.debug(
        "Migrated ScorpionTrack Portal entry to version %s.%s",
        entry.version,
        entry.minor_version,
    )
    return True
