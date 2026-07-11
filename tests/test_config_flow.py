"""Test the ScorpionTrack config flow."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult, FlowResultType
from pyscorpiontrack import (
    ScorpionTrackConnectionError as ScorpionTrackShareConnectionError,
)
from pyscorpiontrack import (
    ScorpionTrackInvalidTokenError,
    ScorpionTrackShare,
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
from custom_components.scorpiontrack.const import (
    CONF_SETUP_TYPE,
    CONF_SHARE_TOKEN,
    DOMAIN,
    SETUP_TYPE_ACCOUNT,
    SETUP_TYPE_SHARE,
    SHARE_DEFAULT_NAME,
)
from custom_components.scorpiontrack.utils import stable_hash


@pytest.fixture(autouse=True)
def prevent_entry_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep config-flow tests isolated from config-entry setup side effects."""
    monkeypatch.setattr(
        "custom_components.scorpiontrack.async_setup_entry",
        AsyncMock(return_value=True),
    )


async def _async_start_route(hass: HomeAssistant, route: str) -> FlowResult:
    """Start the user flow and select a setup route."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "user"
    assert result["menu_options"] == ["account", "share"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": route},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == route
    assert result["errors"] == {}
    return result


async def test_share_flow_creates_entry(
    hass: HomeAssistant,
    client_mocks: SimpleNamespace,
) -> None:
    """A full share URL should be normalized and create an entry."""
    result = await _async_start_route(hass, "share")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SHARE_TOKEN: (
                "  https://app.scorpiontrack.com/shared/location"
                "?token=canonical-token  "
            )
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Family Cars"
    assert result["data"] == {
        CONF_SETUP_TYPE: SETUP_TYPE_SHARE,
        CONF_SHARE_TOKEN: "canonical-token",
    }
    assert result["result"].unique_id == "share_101"
    client_mocks.share.async_get_share.assert_awaited_once()


@pytest.mark.parametrize("fallback", ["vehicle", "default"])
async def test_share_flow_title_fallbacks(
    hass: HomeAssistant,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
    fallback: str,
) -> None:
    """Share entry titles should use the vehicle and then the default name."""
    share = replace(mock_share, title="")
    expected_title = share.vehicles[0].display_name
    if fallback == "default":
        share = replace(share, vehicles=())
        expected_title = SHARE_DEFAULT_NAME
    client_mocks.share.async_get_share.return_value = share

    result = await _async_start_route(hass, "share")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SHARE_TOKEN: "canonical-token"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == expected_title


@pytest.mark.parametrize("unique_id", ["share_101", "101"])
async def test_share_flow_aborts_for_hacs_and_core_duplicates(
    hass: HomeAssistant,
    unique_id: str,
) -> None:
    """Both HACS and Core forms of the share ID should prevent duplicates."""
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_SHARE_TOKEN: "canonical-token"},
        unique_id=unique_id,
    ).add_to_hass(hass)

    result = await _async_start_route(hass, "share")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SHARE_TOKEN: "canonical-token"},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        (ScorpionTrackShareConnectionError("connection failed"), "cannot_connect"),
        (ScorpionTrackInvalidTokenError("invalid token"), "invalid_token"),
        (
            ScorpionTrackShareUnavailableError("share unavailable"),
            "share_unavailable",
        ),
        (Exception("unexpected"), "unknown"),
    ],
)
async def test_share_flow_maps_validation_errors(
    hass: HomeAssistant,
    client_mocks: SimpleNamespace,
    side_effect: Exception,
    expected_error: str,
) -> None:
    """Share validation errors should map to stable form errors."""
    client_mocks.share.async_get_share.side_effect = side_effect
    result = await _async_start_route(hass, "share")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SHARE_TOKEN: "canonical-token"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "share"
    assert result["errors"] == {"base": expected_error}


async def test_share_flow_recovers_after_malformed_input(
    hass: HomeAssistant,
    client_mocks: SimpleNamespace,
) -> None:
    """The same flow should recover after an invalid pasted value."""
    client_mocks.share_class.extract_token.side_effect = [
        ValueError("could not parse"),
        "canonical-token",
    ]
    result = await _async_start_route(hass, "share")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SHARE_TOKEN: "not a share"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_token"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SHARE_TOKEN: "canonical-token"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "share_101"


async def test_account_flow_creates_entry(
    hass: HomeAssistant,
    client_mocks: SimpleNamespace,
) -> None:
    """Valid portal credentials should create an account entry."""
    result = await _async_start_route(hass, "account")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: " OWNER@EXAMPLE.COM ",
            CONF_PASSWORD: "correct-password",
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "ScorpionTrack (Owner)"
    assert result["data"] == {
        CONF_SETUP_TYPE: SETUP_TYPE_ACCOUNT,
        CONF_EMAIL: "owner@example.com",
        CONF_PASSWORD: "correct-password",
    }
    assert result["result"].unique_id == "account_42"
    client_mocks.account.async_refresh_account.assert_awaited_once()


async def test_account_flow_uses_hashed_email_without_user_id(
    hass: HomeAssistant,
    client_mocks: SimpleNamespace,
    mock_account: ScorpionTrackAccountData,
) -> None:
    """Accounts without a portal user ID should retain a stable hashed ID."""
    client_mocks.account.async_refresh_account.return_value = replace(
        mock_account, user_id=None
    )
    result = await _async_start_route(hass, "account")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "owner@example.com",
            CONF_PASSWORD: "correct-password",
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id.startswith("account_")
    assert result["result"].unique_id != "account_42"


async def test_account_flow_aborts_for_duplicate(
    hass: HomeAssistant,
    account_config_entry: MockConfigEntry,
) -> None:
    """The same portal account should not be configured twice."""
    account_config_entry.add_to_hass(hass)
    result = await _async_start_route(hass, "account")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "owner@example.com",
            CONF_PASSWORD: "correct-password",
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        (ScorpionTrackAccountConnectionError("connection failed"), "cannot_connect"),
        (ScorpionTrackAuthError("bad credentials"), "invalid_auth"),
        (ScorpionTrackPortalError("unexpected response"), "unexpected_response"),
        (Exception("unexpected"), "unknown"),
    ],
)
async def test_account_flow_maps_validation_errors(
    hass: HomeAssistant,
    client_mocks: SimpleNamespace,
    side_effect: Exception,
    expected_error: str,
) -> None:
    """Account validation errors should map to stable form errors."""
    client_mocks.account.async_refresh_account.side_effect = side_effect
    result = await _async_start_route(hass, "account")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "owner@example.com",
            CONF_PASSWORD: "wrong-password",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "account"
    assert result["errors"] == {"base": expected_error}


async def _async_start_reauth(
    hass: HomeAssistant, entry: MockConfigEntry
) -> FlowResult:
    """Start an account reauthentication flow."""
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {}
    return result


async def test_reauth_updates_password(
    hass: HomeAssistant,
    account_config_entry: MockConfigEntry,
) -> None:
    """Successful reauthentication should update and keep the account identity."""
    result = await _async_start_reauth(hass, account_config_entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PASSWORD: "new-password"},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert account_config_entry.data[CONF_PASSWORD] == "new-password"
    assert account_config_entry.unique_id == "account_42"


async def test_reauth_rejects_different_account(
    hass: HomeAssistant,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_account: ScorpionTrackAccountData,
) -> None:
    """Reauthentication must not silently switch account identities."""
    client_mocks.account.async_refresh_account.return_value = replace(
        mock_account, user_id=99
    )
    result = await _async_start_reauth(hass, account_config_entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PASSWORD: "different-account-password"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "reauth_account_mismatch"}
    assert account_config_entry.data[CONF_PASSWORD] == "correct-password"


async def test_reauth_keeps_fallback_identity_when_user_id_appears(
    hass: HomeAssistant,
    client_mocks: SimpleNamespace,
) -> None:
    """A later portal user ID must not replace a deployed email-hash identity."""
    fallback_unique_id = f"account_{stable_hash('owner@example.com')}"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="ScorpionTrack (Owner)",
        data={
            CONF_SETUP_TYPE: SETUP_TYPE_ACCOUNT,
            CONF_EMAIL: "owner@example.com",
            CONF_PASSWORD: "old-password",
        },
        unique_id=fallback_unique_id,
    )
    result = await _async_start_reauth(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PASSWORD: "new-password"},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.unique_id == fallback_unique_id
    assert entry.data[CONF_PASSWORD] == "new-password"
    client_mocks.account.async_refresh_account.assert_awaited_once()


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        (ScorpionTrackAccountConnectionError("connection failed"), "cannot_connect"),
        (ScorpionTrackAuthError("bad credentials"), "invalid_auth"),
        (ScorpionTrackPortalError("unexpected response"), "unexpected_response"),
        (Exception("unexpected"), "unknown"),
    ],
)
async def test_reauth_maps_validation_errors(
    hass: HomeAssistant,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    side_effect: Exception,
    expected_error: str,
) -> None:
    """Reauthentication should retain its form for recoverable errors."""
    client_mocks.account.async_refresh_account.side_effect = side_effect
    result = await _async_start_reauth(hass, account_config_entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PASSWORD: "wrong-password"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": expected_error}
