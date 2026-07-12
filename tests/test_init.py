"""Test ScorpionTrack setup and unload behavior."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import loader
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pyscorpiontrack import (
    ScorpionTrackConnectionError as ScorpionTrackShareConnectionError,
)
from pyscorpiontrack import (
    ScorpionTrackInvalidTokenError,
    ScorpionTrackShareUnavailableError,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scorpiontrack.account_api import (
    ScorpionTrackAccountData,
    ScorpionTrackAuthError,
    ScorpionTrackPortalError,
)
from custom_components.scorpiontrack.account_api import (
    ScorpionTrackConnectionError as ScorpionTrackAccountConnectionError,
)
from custom_components.scorpiontrack.account_coordinator import (
    ScorpionTrackAccountCoordinator,
)
from custom_components.scorpiontrack.const import (
    CONF_SETUP_TYPE,
    CONF_SHARE_TOKEN,
    DOMAIN,
)
from custom_components.scorpiontrack.share_coordinator import (
    ScorpionTrackShareCoordinator,
)
from custom_components.scorpiontrack.utils import stable_hash

from . import setup_integration


async def test_custom_integration_is_loaded(hass: HomeAssistant) -> None:
    """The custom package must win over the same-domain Core integration."""
    integration = await loader.async_get_integration(hass, DOMAIN)
    assert integration.pkg_path == "custom_components.scorpiontrack"


@pytest.mark.parametrize(
    ("entry_fixture", "coordinator_type", "expected_entities"),
    [
        ("share_config_entry", ScorpionTrackShareCoordinator, 13),
        ("account_config_entry", ScorpionTrackAccountCoordinator, 53),
    ],
)
async def test_setup_runtime_data_entity_count_and_unload(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    request: pytest.FixtureRequest,
    entry_fixture: str,
    coordinator_type: type,
    expected_entities: int,
) -> None:
    """Both source types should use runtime data and retain every entity."""
    entry: MockConfigEntry = request.getfixturevalue(entry_fixture)
    await setup_integration(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, coordinator_type)
    assert len(er.async_entries_for_config_entry(entity_registry, entry.entry_id)) == (
        expected_entities
    )

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_core_share_entry_without_setup_type_is_compatible(
    hass: HomeAssistant,
) -> None:
    """A share entry created by Core should load under the richer override."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Family Cars",
        data={CONF_SHARE_TOKEN: "canonical-token"},
        unique_id="101",
    )
    await setup_integration(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, ScorpionTrackShareCoordinator)


async def test_hybrid_account_uses_fast_share_coordinator_interval(
    hass: HomeAssistant,
    hybrid_account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
) -> None:
    """A hybrid entry should initialize both sources on a two-minute cadence."""
    await setup_integration(hass, hybrid_account_config_entry)

    coordinator = hybrid_account_config_entry.runtime_data
    assert isinstance(coordinator, ScorpionTrackAccountCoordinator)
    assert coordinator.update_interval.total_seconds() == 120
    client_mocks.account.async_refresh_account.assert_awaited_once()
    client_mocks.share.async_get_share.assert_awaited_once()


async def test_options_update_reloads_entry(
    hass: HomeAssistant,
    account_config_entry: MockConfigEntry,
) -> None:
    """Changing speed/share options should reload the active entry."""
    with patch.object(
        hass.config_entries,
        "async_reload",
        AsyncMock(return_value=True),
    ) as reload_entry:
        from custom_components.scorpiontrack import _async_reload_entry

        await _async_reload_entry(hass, account_config_entry)

    reload_entry.assert_awaited_once_with(account_config_entry.entry_id)


async def test_unknown_entry_type_fails_cleanly(hass: HomeAssistant) -> None:
    """Malformed legacy entries should fail setup instead of raising ValueError."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_SETUP_TYPE: "unsupported"},
    )
    await setup_integration(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_ERROR


@pytest.mark.parametrize(
    ("exception", "expected_state"),
    [
        (
            ScorpionTrackShareConnectionError("connection failed"),
            ConfigEntryState.SETUP_RETRY,
        ),
        (
            ScorpionTrackInvalidTokenError("invalid token"),
            ConfigEntryState.SETUP_ERROR,
        ),
        (
            ScorpionTrackShareUnavailableError("share unavailable"),
            ConfigEntryState.SETUP_ERROR,
        ),
    ],
)
async def test_share_setup_error_semantics(
    hass: HomeAssistant,
    share_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    exception: Exception,
    expected_state: ConfigEntryState,
) -> None:
    """Share setup should distinguish transient and permanent failures."""
    client_mocks.share.async_get_share.side_effect = exception
    await setup_integration(hass, share_config_entry)
    assert share_config_entry.state is expected_state


@pytest.mark.parametrize(
    ("exception", "expected_state"),
    [
        (
            ScorpionTrackAccountConnectionError("connection failed"),
            ConfigEntryState.SETUP_RETRY,
        ),
        (ScorpionTrackAuthError("bad credentials"), ConfigEntryState.SETUP_ERROR),
        (
            ScorpionTrackPortalError("unexpected response"),
            ConfigEntryState.SETUP_RETRY,
        ),
    ],
)
async def test_account_setup_error_semantics(
    hass: HomeAssistant,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    exception: Exception,
    expected_state: ConfigEntryState,
) -> None:
    """Account setup should retry transport failures and reauth credentials."""
    client_mocks.account.async_refresh_account.side_effect = exception
    await setup_integration(hass, account_config_entry)
    assert account_config_entry.state is expected_state


@pytest.mark.parametrize(
    ("entry_fixture", "identifier", "name", "manufacturer", "model"),
    [
        (
            "share_config_entry",
            (DOMAIN, "101_2001"),
            "AB12 CDE",
            "Volkswagen",
            "Golf R",
        ),
        (
            "account_config_entry",
            (DOMAIN, "42_vehicle_2001"),
            "Golf R",
            "Volkswagen",
            "Golf R",
        ),
    ],
)
async def test_vehicle_device_identity_is_preserved(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    request: pytest.FixtureRequest,
    entry_fixture: str,
    identifier: tuple[str, str],
    name: str,
    manufacturer: str,
    model: str,
) -> None:
    """Refactoring must not change deployed vehicle registry identifiers."""
    entry: MockConfigEntry = request.getfixturevalue(entry_fixture)
    await setup_integration(hass, entry)

    device = device_registry.async_get_device(identifiers={identifier})
    assert device is not None
    assert device.name == name
    assert device.manufacturer == manufacturer
    assert device.model == model


async def test_fallback_account_identity_survives_later_user_id(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    client_mocks: SimpleNamespace,
    mock_account: ScorpionTrackAccountData,
) -> None:
    """A fallback entry must not duplicate entities if a user ID later appears."""
    email_hash = stable_hash("owner@example.com")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="ScorpionTrack (Owner)",
        data={
            CONF_SETUP_TYPE: "account",
            CONF_EMAIL: "owner@example.com",
            CONF_PASSWORD: "correct-password",
        },
        unique_id=f"account_{email_hash}",
    )
    client_mocks.account.async_refresh_account.return_value = replace(
        mock_account, user_id=None
    )
    await setup_integration(hass, entry)

    fallback_tracker_id = entity_registry.async_get_entity_id(
        "device_tracker", DOMAIN, f"acct_{email_hash}_2001_tracker"
    )
    assert fallback_tracker_id is not None
    assert await hass.config_entries.async_unload(entry.entry_id)

    client_mocks.account.async_refresh_account.return_value = mock_account
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert (
        entity_registry.async_get_entity_id(
            "device_tracker", DOMAIN, f"acct_{email_hash}_2001_tracker"
        )
        == fallback_tracker_id
    )
    assert (
        entity_registry.async_get_entity_id("device_tracker", DOMAIN, "42_2001_tracker")
        is None
    )
