"""Switch platform for ScorpionTrack."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import account_switch
from .const import SETUP_TYPE_ACCOUNT, get_setup_type


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ScorpionTrack switches for the configured entry type."""
    if get_setup_type(entry.data) == SETUP_TYPE_ACCOUNT:
        await account_switch.async_setup_entry(hass, entry, async_add_entities)
