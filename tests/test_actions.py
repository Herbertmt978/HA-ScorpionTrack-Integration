"""Test ScorpionTrack account controls."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scorpiontrack.account_api import ScorpionTrackPortalError
from custom_components.scorpiontrack.const import DOMAIN

from . import setup_integration


def _entity_id(
    entity_registry: er.EntityRegistry,
    domain: str,
    unique_id: str,
) -> str:
    """Return a registered ScorpionTrack entity ID."""
    entity_id = entity_registry.async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id is not None
    return entity_id


async def test_vehicle_switches_call_verified_modes_and_refresh(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
) -> None:
    """Both verified switches should call the portal and request fresh state."""
    await setup_integration(hass, account_config_entry)
    privacy = _entity_id(entity_registry, "switch", "42_2001_privacy_mode")
    zero_speed = _entity_id(entity_registry, "switch", "42_2001_zero_speed_mode")

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": privacy},
        blocking=True,
    )
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": zero_speed},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert client_mocks.account.async_set_vehicle_mode.await_args_list == [
        ((2001, "privacy_mode_enabled", True),),
        ((2001, "zero_speed_mode_enabled", False),),
    ]
    assert client_mocks.account.async_refresh_account.await_count >= 2


async def test_mark_alerts_read_calls_portal_and_refreshes(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
) -> None:
    """The alert button should preserve the existing bulk-read action."""
    await setup_integration(hass, account_config_entry)
    button = _entity_id(entity_registry, "button", "42_mark_alerts_read")

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": button},
        blocking=True,
    )
    await hass.async_block_till_done()

    client_mocks.account.async_mark_all_alerts_read.assert_awaited_once_with()
    assert client_mocks.account.async_refresh_account.await_count >= 2


async def test_action_error_does_not_expose_upstream_text(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
) -> None:
    """Portal exception text must not be surfaced through service failures."""
    await setup_integration(hass, account_config_entry)
    privacy = _entity_id(entity_registry, "switch", "42_2001_privacy_mode")
    client_mocks.account.async_set_vehicle_mode.side_effect = ScorpionTrackPortalError(
        "upstream-secret-marker"
    )

    try:
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": privacy},
            blocking=True,
        )
    except HomeAssistantError as err:
        assert "upstream-secret-marker" not in str(err)
    else:
        raise AssertionError("Expected the failed portal write to reach the caller")
