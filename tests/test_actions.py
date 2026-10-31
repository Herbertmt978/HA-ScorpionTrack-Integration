"""Test ScorpionTrack account controls."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scorpiontrack_portal.account_api import (
    ScorpionTrackAuthError,
    ScorpionTrackConnectionError,
    ScorpionTrackPortalError,
)
from custom_components.scorpiontrack_portal.const import DOMAIN

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


@pytest.mark.parametrize(
    ("unique_id", "translation_key"),
    [
        ("42_2001_privacy_mode", "privacy_mode_update_failed"),
        ("42_2001_zero_speed_mode", "zero_speed_mode_update_failed"),
    ],
)
async def test_switch_error_is_translated_without_upstream_text(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    unique_id: str,
    translation_key: str,
) -> None:
    """Portal failures surface as a translated error for the failing control."""
    await setup_integration(hass, account_config_entry)
    client_mocks.account.async_set_vehicle_mode.side_effect = ScorpionTrackPortalError(
        "upstream-secret-marker"
    )

    with pytest.raises(HomeAssistantError) as raised:
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": _entity_id(entity_registry, "switch", unique_id)},
            blocking=True,
        )

    assert raised.value.translation_key == translation_key
    assert "upstream-secret-marker" not in str(raised.value)


async def test_mark_alerts_read_error_is_translated(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
) -> None:
    """A failed bulk-read surfaces as a translated error."""
    await setup_integration(hass, account_config_entry)
    client_mocks.account.async_mark_all_alerts_read.side_effect = (
        ScorpionTrackConnectionError("upstream-secret-marker")
    )

    with pytest.raises(HomeAssistantError) as raised:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": _entity_id(entity_registry, "button", "42_mark_alerts_read")},
            blocking=True,
        )

    assert raised.value.translation_key == "mark_alerts_read_failed"
    assert "upstream-secret-marker" not in str(raised.value)


@pytest.mark.parametrize(
    ("domain", "service", "unique_id", "client_method"),
    [
        ("switch", "turn_on", "42_2001_privacy_mode", "async_set_vehicle_mode"),
        ("button", "press", "42_mark_alerts_read", "async_mark_all_alerts_read"),
    ],
)
async def test_action_auth_error_starts_reauthentication(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    domain: str,
    service: str,
    unique_id: str,
    client_method: str,
) -> None:
    """Rejected credentials during an action prompt the user to sign in again."""
    await setup_integration(hass, account_config_entry)
    getattr(client_mocks.account, client_method).side_effect = ScorpionTrackAuthError(
        "rejected"
    )

    with pytest.raises(HomeAssistantError) as raised:
        await hass.services.async_call(
            domain,
            service,
            {"entity_id": _entity_id(entity_registry, domain, unique_id)},
            blocking=True,
        )
    await hass.async_block_till_done()

    assert raised.value.translation_key == "invalid_auth"
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]
