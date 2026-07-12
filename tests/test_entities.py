"""Test ScorpionTrack entities through Home Assistant's public surfaces."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyscorpiontrack import ScorpionTrackConnectionError, ScorpionTrackShare
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.scorpiontrack.account_api import ScorpionTrackAccountData
from custom_components.scorpiontrack.account_binary_sensor import (
    VEHICLE_BINARY_SENSOR_DESCRIPTIONS as ACCOUNT_BINARY_SENSORS,
)
from custom_components.scorpiontrack.account_sensor import (
    ACCOUNT_SENSOR_DESCRIPTIONS,
)
from custom_components.scorpiontrack.account_sensor import (
    VEHICLE_SENSOR_DESCRIPTIONS as ACCOUNT_VEHICLE_SENSORS,
)
from custom_components.scorpiontrack.account_switch import (
    VEHICLE_SWITCH_DESCRIPTIONS,
)
from custom_components.scorpiontrack.const import (
    ACCOUNT_SCAN_INTERVAL,
    DOMAIN,
    SHARE_SCAN_INTERVAL,
)
from custom_components.scorpiontrack.share_binary_sensor import (
    BINARY_SENSOR_DESCRIPTIONS as SHARE_BINARY_SENSORS,
)
from custom_components.scorpiontrack.share_sensor import (
    SENSOR_DESCRIPTIONS as SHARE_VEHICLE_SENSORS,
)
from custom_components.scorpiontrack.share_sensor import (
    SHARE_SENSOR_DESCRIPTIONS,
)

from . import setup_integration


def _entity_id(
    entity_registry: er.EntityRegistry,
    domain: str,
    unique_id: str,
) -> str:
    """Return an entity ID for a known ScorpionTrack unique ID."""
    entity_id = entity_registry.async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id is not None
    return entity_id


async def _async_advance_poll(
    hass: HomeAssistant,
    freezer: Any,
    interval: timedelta,
) -> None:
    """Advance time and allow a natural coordinator refresh."""
    freezer.tick(interval + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_share_unique_ids_and_tracker_state(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    share_config_entry: MockConfigEntry,
) -> None:
    """Share mode should retain IDs, rich state, and one GPS marker."""
    await setup_integration(hass, share_config_entry)

    expected_unique_ids = {
        "101_2001_tracker",
        *(f"101_2001_{description.key}" for description in SHARE_VEHICLE_SENSORS),
        *(f"101_2001_{description.key}" for description in SHARE_BINARY_SENSORS),
        *(f"101_share_{description.key}" for description in SHARE_SENSOR_DESCRIPTIONS),
    }
    actual_unique_ids = {
        entry.unique_id
        for entry in er.async_entries_for_config_entry(
            entity_registry, share_config_entry.entry_id
        )
    }
    assert actual_unique_ids == expected_unique_ids

    tracker_id = _entity_id(entity_registry, "device_tracker", "101_2001_tracker")
    tracker = hass.states.get(tracker_id)
    assert tracker is not None
    assert tracker.attributes["latitude"] == 51.5074
    assert tracker.attributes["longitude"] == -0.1278
    assert tracker.attributes["speed"] == 30.0
    assert tracker.attributes["speed_unit"] == "mph"
    assert tracker.attributes["registration"] == "AB12 CDE"

    location_id = _entity_id(entity_registry, "sensor", "101_2001_location")
    location = hass.states.get(location_id)
    assert location is not None
    assert location.state == "Westminster, London"
    assert "latitude" not in location.attributes
    assert "longitude" not in location.attributes
    assert location.attributes["coordinates"] == "51.507400, -0.127800"


async def test_account_unique_ids_and_tracker_state(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
) -> None:
    """Account mode should retain every deployed unique ID and rich state."""
    await setup_integration(hass, account_config_entry)

    expected_unique_ids = {
        "42_2001_tracker",
        "42_mark_alerts_read",
        *(f"42_{description.key}" for description in ACCOUNT_SENSOR_DESCRIPTIONS),
        *(f"42_2001_{description.key}" for description in ACCOUNT_VEHICLE_SENSORS),
        *(f"42_2001_{description.key}" for description in ACCOUNT_BINARY_SENSORS),
        *(f"42_2001_{description.key}" for description in VEHICLE_SWITCH_DESCRIPTIONS),
    }
    actual_unique_ids = {
        entry.unique_id
        for entry in er.async_entries_for_config_entry(
            entity_registry, account_config_entry.entry_id
        )
    }
    assert actual_unique_ids == expected_unique_ids

    tracker_id = _entity_id(entity_registry, "device_tracker", "42_2001_tracker")
    tracker = hass.states.get(tracker_id)
    assert tracker is not None
    assert tracker.attributes["latitude"] == 51.5074
    assert tracker.attributes["longitude"] == -0.1278
    assert tracker.attributes["formatted_location"] == "Westminster, London"
    assert tracker.attributes["privacy_mode_enabled"] is False
    assert tracker.attributes["zero_speed_mode_enabled"] is True


@pytest.mark.parametrize(
    ("entry_fixture", "speed_unique_id"),
    [
        ("share_config_entry", "101_2001_speed"),
        ("account_config_entry", "42_2001_speed"),
    ],
)
async def test_speed_unit_option_overrides_service_preference(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    request: pytest.FixtureRequest,
    entry_fixture: str,
    speed_unique_id: str,
) -> None:
    """The selected speed unit should override account/share preferences."""
    entry: MockConfigEntry = request.getfixturevalue(entry_fixture)
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry,
        options={"speed_unit": "km/h"},
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    speed_id = _entity_id(entity_registry, "sensor", speed_unique_id)
    speed = hass.states.get(speed_id)
    assert speed is not None
    assert speed.state == "48.3"
    assert speed.attributes["unit_of_measurement"] == "km/h"


async def test_hybrid_account_uses_newer_share_position(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    hybrid_account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
) -> None:
    """Hybrid account entities should use the fresher shared position."""
    share_position = replace(
        mock_share.vehicles[0].position,
        latitude=52.1234,
        longitude=-1.2345,
        timestamp=datetime.now(UTC),
        speed_kmh=80.0,
        address="Fresh share position",
    )
    client_mocks.share.async_get_share.return_value = replace(
        mock_share,
        vehicles=(replace(mock_share.vehicles[0], position=share_position),),
    )

    await setup_integration(hass, hybrid_account_config_entry)

    tracker_id = _entity_id(entity_registry, "device_tracker", "42_2001_tracker")
    tracker = hass.states.get(tracker_id)
    assert tracker is not None
    assert tracker.attributes["latitude"] == 52.1234
    assert tracker.attributes["longitude"] == -1.2345
    assert tracker.attributes["formatted_location"] == "Fresh share position"

    speed_id = _entity_id(entity_registry, "sensor", "42_2001_speed")
    speed = hass.states.get(speed_id)
    assert speed is not None
    assert speed.state == "80.0"
    assert speed.attributes["unit_of_measurement"] == "km/h"


async def test_hybrid_account_polls_share_faster_than_account(
    hass: HomeAssistant,
    freezer: Any,
    hybrid_account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
) -> None:
    """Hybrid refreshes should not increase portal-account request frequency."""
    await setup_integration(hass, hybrid_account_config_entry)

    await _async_advance_poll(hass, freezer, SHARE_SCAN_INTERVAL)

    assert client_mocks.share.async_get_share.await_count == 2
    assert client_mocks.account.async_refresh_account.await_count == 1

    await _async_advance_poll(hass, freezer, SHARE_SCAN_INTERVAL)
    await _async_advance_poll(hass, freezer, SHARE_SCAN_INTERVAL)

    assert client_mocks.share.async_get_share.await_count == 4
    assert client_mocks.account.async_refresh_account.await_count == 2


async def test_hybrid_share_failure_retains_newer_live_position(
    hass: HomeAssistant,
    freezer: Any,
    entity_registry: er.EntityRegistry,
    hybrid_account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
) -> None:
    """A failed optional share must retain the last newer live position."""
    share_vehicle = replace(
        mock_share.vehicles[0],
        position=replace(
            mock_share.vehicles[0].position,
            latitude=53.0,
            timestamp=datetime.now(UTC),
        ),
    )
    client_mocks.share.async_get_share.return_value = replace(
        mock_share, vehicles=(share_vehicle,)
    )
    await setup_integration(hass, hybrid_account_config_entry)
    tracker_id = _entity_id(entity_registry, "device_tracker", "42_2001_tracker")
    tracker = hass.states.get(tracker_id)
    assert tracker is not None
    assert tracker.attributes["latitude"] == 53.0
    client_mocks.share.async_get_share.side_effect = ScorpionTrackConnectionError(
        "connection failed"
    )

    await _async_advance_poll(hass, freezer, SHARE_SCAN_INTERVAL)

    tracker = hass.states.get(tracker_id)
    assert tracker is not None
    assert tracker.state != STATE_UNAVAILABLE
    assert tracker.attributes["latitude"] == 53.0
    assert hybrid_account_config_entry.runtime_data.share_last_update_success is False
    assert (
        hybrid_account_config_entry.runtime_data.share_last_exception_type
        == "ScorpionTrackConnectionError"
    )


async def test_hybrid_matches_vehicle_by_normalized_registration(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    hybrid_account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
) -> None:
    """A changed cross-source ID should fall back to a unique registration."""
    share_vehicle = replace(
        mock_share.vehicles[0],
        id=9999,
        registration="ab12cde",
        position=replace(
            mock_share.vehicles[0].position,
            latitude=53.0,
            timestamp=datetime.now(UTC),
        ),
    )
    client_mocks.share.async_get_share.return_value = replace(
        mock_share, vehicles=(share_vehicle,)
    )

    await setup_integration(hass, hybrid_account_config_entry)

    tracker_id = _entity_id(entity_registry, "device_tracker", "42_2001_tracker")
    tracker = hass.states.get(tracker_id)
    assert tracker is not None
    assert tracker.attributes["latitude"] == 53.0
    assert hybrid_account_config_entry.runtime_data.matched_share_vehicle_count == 1


async def test_hybrid_does_not_replace_newer_account_position(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    hybrid_account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
) -> None:
    """A stale share payload should never move an account tracker backwards."""
    share_vehicle = replace(
        mock_share.vehicles[0],
        position=replace(
            mock_share.vehicles[0].position,
            latitude=53.0,
            timestamp=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    client_mocks.share.async_get_share.return_value = replace(
        mock_share, vehicles=(share_vehicle,)
    )

    await setup_integration(hass, hybrid_account_config_entry)

    tracker_id = _entity_id(entity_registry, "device_tracker", "42_2001_tracker")
    tracker = hass.states.get(tracker_id)
    assert tracker is not None
    assert tracker.attributes["latitude"] == 51.5074


async def test_share_removed_vehicle_becomes_unavailable_and_recovers(
    hass: HomeAssistant,
    freezer: Any,
    caplog: pytest.LogCaptureFixture,
    entity_registry: er.EntityRegistry,
    share_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
) -> None:
    """Removed vehicles should be safe, unavailable, and recover by ID."""
    await setup_integration(hass, share_config_entry)
    tracker_id = _entity_id(entity_registry, "device_tracker", "101_2001_tracker")

    client_mocks.share.async_get_share.return_value = replace(mock_share, vehicles=())
    await _async_advance_poll(hass, freezer, SHARE_SCAN_INTERVAL)
    state = hass.states.get(tracker_id)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE
    vehicle_entries = [
        entry
        for entry in er.async_entries_for_config_entry(
            entity_registry, share_config_entry.entry_id
        )
        if entry.unique_id.startswith("101_2001_")
    ]
    assert vehicle_entries
    assert all(
        (state := hass.states.get(entry.entity_id)) is not None
        and state.state == STATE_UNAVAILABLE
        for entry in vehicle_entries
    )
    assert "Unexpected error updating listener" not in caplog.text

    client_mocks.share.async_get_share.return_value = mock_share
    await _async_advance_poll(hass, freezer, SHARE_SCAN_INTERVAL)
    state = hass.states.get(tracker_id)
    assert state is not None
    assert state.state != STATE_UNAVAILABLE
    assert state.attributes["latitude"] == 51.5074


async def test_account_removed_vehicle_becomes_unavailable_and_recovers(
    hass: HomeAssistant,
    freezer: Any,
    caplog: pytest.LogCaptureFixture,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_account: ScorpionTrackAccountData,
) -> None:
    """Account entities should tolerate a temporarily absent vehicle."""
    await setup_integration(hass, account_config_entry)
    tracker_id = _entity_id(entity_registry, "device_tracker", "42_2001_tracker")

    client_mocks.account.async_refresh_account.return_value = replace(
        mock_account,
        vehicles=(),
        fetched_at=datetime.now(UTC),
    )
    await _async_advance_poll(hass, freezer, ACCOUNT_SCAN_INTERVAL)
    state = hass.states.get(tracker_id)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE
    vehicle_entries = [
        entry
        for entry in er.async_entries_for_config_entry(
            entity_registry, account_config_entry.entry_id
        )
        if entry.unique_id.startswith("42_2001_")
    ]
    assert vehicle_entries
    assert all(
        (state := hass.states.get(entry.entity_id)) is not None
        and state.state == STATE_UNAVAILABLE
        for entry in vehicle_entries
    )
    assert "Unexpected error updating listener" not in caplog.text

    client_mocks.account.async_refresh_account.return_value = replace(
        mock_account, fetched_at=datetime.now(UTC)
    )
    await _async_advance_poll(hass, freezer, ACCOUNT_SCAN_INTERVAL)
    state = hass.states.get(tracker_id)
    assert state is not None
    assert state.state != STATE_UNAVAILABLE


async def test_share_adds_new_vehicle_dynamically(
    hass: HomeAssistant,
    freezer: Any,
    entity_registry: er.EntityRegistry,
    share_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
) -> None:
    """HACS should retain dynamic share-vehicle discovery."""
    await setup_integration(hass, share_config_entry)
    new_vehicle = replace(
        mock_share.vehicles[0],
        id=2002,
        name="Tiguan",
        registration="EF34 ABC",
        model="Tiguan",
    )
    client_mocks.share.async_get_share.return_value = replace(
        mock_share, vehicles=(*mock_share.vehicles, new_vehicle)
    )

    await _async_advance_poll(hass, freezer, SHARE_SCAN_INTERVAL)

    tracker_id = _entity_id(entity_registry, "device_tracker", "101_2002_tracker")
    assert hass.states.get(tracker_id) is not None
    assert _entity_id(entity_registry, "sensor", "101_2002_status")
    assert _entity_id(entity_registry, "binary_sensor", "101_2002_ignition")


async def test_account_adds_new_vehicle_dynamically(
    hass: HomeAssistant,
    freezer: Any,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_account: ScorpionTrackAccountData,
) -> None:
    """HACS should retain dynamic account-vehicle discovery."""
    await setup_integration(hass, account_config_entry)
    new_vehicle = replace(
        mock_account.vehicles[0],
        id=2002,
        registration="EF34 ABC",
        alias="Tiguan",
        model="Tiguan",
    )
    client_mocks.account.async_refresh_account.return_value = replace(
        mock_account,
        vehicles=(*mock_account.vehicles, new_vehicle),
        fetched_at=datetime.now(UTC),
    )

    await _async_advance_poll(hass, freezer, ACCOUNT_SCAN_INTERVAL)

    assert _entity_id(entity_registry, "device_tracker", "42_2002_tracker")
    assert _entity_id(entity_registry, "sensor", "42_2002_status")
    assert _entity_id(entity_registry, "switch", "42_2002_privacy_mode")


async def test_share_connection_error_makes_entities_unavailable(
    hass: HomeAssistant,
    freezer: Any,
    entity_registry: er.EntityRegistry,
    share_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
) -> None:
    """A transient refresh failure should mark existing entities unavailable."""
    await setup_integration(hass, share_config_entry)
    tracker_id = _entity_id(entity_registry, "device_tracker", "101_2001_tracker")
    client_mocks.share.async_get_share.side_effect = ScorpionTrackConnectionError(
        "connection failed"
    )

    await _async_advance_poll(hass, freezer, SHARE_SCAN_INTERVAL)
    state = hass.states.get(tracker_id)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE
