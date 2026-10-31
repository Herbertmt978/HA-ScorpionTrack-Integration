"""Sensor platform for ScorpionTrack."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import account_sensor, share_sensor
from .const import SETUP_TYPE_ACCOUNT, get_setup_type


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ScorpionTrack sensors for the configured entry type."""
    if get_setup_type(entry.data) == SETUP_TYPE_ACCOUNT:
        await account_sensor.async_setup_entry(hass, entry, async_add_entities)
        return

    await share_sensor.async_setup_entry(hass, entry, async_add_entities)
