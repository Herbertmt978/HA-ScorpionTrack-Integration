"""Exercise the pinned shared-location client through integration setup."""

from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from . import setup_integration

SHARE_URL = (
    "https://api2.fleet.scorpiontrack.com/v1/location-shares/canonical-token/view"
)


@pytest.fixture(autouse=True)
def mock_clients() -> None:
    """Use the actual library; only its HTTP boundary is mocked here."""


async def test_real_share_client_loads_vehicle(
    hass: HomeAssistant,
    share_config_entry: MockConfigEntry,
    aioclient_mock: Any,
) -> None:
    """The installed client should produce a usable tracker from a share."""
    aioclient_mock.get(
        SHARE_URL,
        json={
            "data": {
                "id": 101,
                "vehicles": [
                    {
                        "id": 2001,
                        "registration": "TEST CAR",
                        "latest_position": {"lat": 51.5, "lng": -0.1},
                    }
                ],
            }
        },
    )

    await setup_integration(hass, share_config_entry)

    assert share_config_entry.state is ConfigEntryState.LOADED
    trackers = hass.states.async_all("device_tracker")
    assert len(trackers) == 1
    assert trackers[0].attributes["latitude"] == 51.5
    assert trackers[0].attributes["longitude"] == -0.1
    assert aioclient_mock.call_count == 1


@pytest.mark.parametrize("payload", [{}, {"data": {"id": 101, "vehicles": {}}}])
async def test_real_share_client_retries_malformed_response(
    hass: HomeAssistant,
    share_config_entry: MockConfigEntry,
    aioclient_mock: Any,
    caplog: pytest.LogCaptureFixture,
    payload: dict[str, Any],
) -> None:
    """Malformed service data must remain retryable without logging the token."""
    aioclient_mock.get(SHARE_URL, json=payload)

    await setup_integration(hass, share_config_entry)

    assert share_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert not hass.states.async_all("device_tracker")
    assert "canonical-token" not in caplog.text
    assert aioclient_mock.call_count == 1
