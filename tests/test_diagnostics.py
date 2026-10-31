"""Tests for privacy-safe ScorpionTrack diagnostics."""

from __future__ import annotations

import json
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pyscorpiontrack import ScorpionTrackConnectionError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scorpiontrack_portal.diagnostics import (
    async_get_config_entry_diagnostics,
)

from . import setup_integration


@pytest.mark.parametrize(
    ("entry_fixture", "expected"),
    [
        (
            "account_config_entry",
            {
                "config_entry": {
                    "setup_type": "account",
                    "state": "loaded",
                    "version": 1,
                    "minor_version": 3,
                },
                "coordinator": {
                    "last_update_success": True,
                    "last_exception_type": None,
                    "update_interval_seconds": 300.0,
                    "vehicle_count": 1,
                },
                "entities": {
                    "total": 53,
                    "disabled": 30,
                    "by_platform": {
                        "binary_sensor": 13,
                        "button": 1,
                        "device_tracker": 1,
                        "sensor": 36,
                        "switch": 2,
                    },
                },
                "account": {
                    "app_api_key_available": True,
                    "fms_api_available": True,
                    "total_alerts": 2,
                    "unread_alerts": 1,
                },
            },
        ),
        (
            "share_config_entry",
            {
                "config_entry": {
                    "setup_type": "share",
                    "state": "loaded",
                    "version": 1,
                    "minor_version": 3,
                },
                "coordinator": {
                    "last_update_success": True,
                    "last_exception_type": None,
                    "update_interval_seconds": 120.0,
                    "vehicle_count": 1,
                },
                "entities": {
                    "total": 13,
                    "disabled": 7,
                    "by_platform": {
                        "binary_sensor": 2,
                        "device_tracker": 1,
                        "sensor": 10,
                    },
                },
            },
        ),
    ],
)
async def test_diagnostics_exact_output(
    hass: HomeAssistant,
    request: pytest.FixtureRequest,
    entry_fixture: str,
    expected: dict[str, Any],
) -> None:
    """Diagnostics should expose only the intended support metadata."""
    entry: MockConfigEntry = request.getfixturevalue(entry_fixture)
    await setup_integration(hass, entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics == expected
    json.dumps(diagnostics)


async def test_hybrid_diagnostics_report_share_health_without_token(
    hass: HomeAssistant,
    hybrid_account_config_entry: MockConfigEntry,
) -> None:
    """Hybrid diagnostics should expose feed health but no share identity."""
    await setup_integration(hass, hybrid_account_config_entry)

    diagnostics = await async_get_config_entry_diagnostics(
        hass, hybrid_account_config_entry
    )
    serialized = json.dumps(diagnostics)

    assert diagnostics["hybrid_share"] == {
        "last_update_success": True,
        "last_exception_type": None,
        "matched_vehicle_count": 1,
    }
    assert "canonical-token" not in serialized


async def test_diagnostics_expose_exception_type_without_message(
    hass: HomeAssistant,
    share_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
) -> None:
    """Coordinator failures should be useful without leaking exception details."""
    await setup_integration(hass, share_config_entry)
    client_mocks.share.async_get_share.side_effect = ScorpionTrackConnectionError(
        "https://example.invalid/location-shares/secret-share-token/view"
    )
    await share_config_entry.runtime_data.async_refresh()

    diagnostics = await async_get_config_entry_diagnostics(hass, share_config_entry)
    serialized = json.dumps(diagnostics)

    assert diagnostics["coordinator"]["last_update_success"] is False
    assert diagnostics["coordinator"]["last_exception_type"] == "UpdateFailed"
    assert "secret-share-token" not in serialized
    assert "example.invalid" not in serialized


@pytest.mark.parametrize(
    "entry_fixture", ["account_config_entry", "share_config_entry"]
)
async def test_diagnostics_never_include_private_fields_or_values(
    hass: HomeAssistant,
    request: pytest.FixtureRequest,
    entry_fixture: str,
) -> None:
    """Diagnostics must not expose credentials, identity, or location data."""
    entry: MockConfigEntry = request.getfixturevalue(entry_fixture)
    await setup_integration(hass, entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    serialized = json.dumps(diagnostics)

    forbidden_keys = {
        "address",
        "alias",
        "created_at",
        "description",
        "email",
        "entry_id",
        "expires_at",
        "fetched_at",
        "groups",
        "last_exception",
        "latitude",
        "longitude",
        "owner_name",
        "password",
        "registration",
        "share_token",
        "title",
        "token",
        "unique_id",
        "user_id",
        "vehicle_id",
    }
    assert forbidden_keys.isdisjoint(_all_keys(diagnostics))

    for private_value in (
        "owner@example.com",
        "correct-password",
        "canonical-token",
        "AB12 CDE",
        "Golf R",
        "Westminster, London",
        "51.5074",
        "-0.1278",
    ):
        assert private_value not in serialized


def _all_keys(value: Any) -> set[str]:
    """Return every mapping key in a nested diagnostics payload."""
    if isinstance(value, Mapping):
        keys = {str(key) for key in value}
        for nested_value in value.values():
            keys.update(_all_keys(nested_value))
        return keys
    if isinstance(value, list | tuple):
        keys: set[str] = set()
        for nested_value in value:
            keys.update(_all_keys(nested_value))
        return keys
    return set()
