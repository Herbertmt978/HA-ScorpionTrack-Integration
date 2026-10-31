"""Test ScorpionTrack Portal entities through Home Assistant's public surfaces."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pyscorpiontrack import (
    ScorpionTrackConnectionError,
    ScorpionTrackInvalidTokenError,
    ScorpionTrackShare,
    ScorpionTrackShareUnavailableError,
)
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.scorpiontrack_portal.account_api import (
    ScorpionTrackAccountData,
    ScorpionTrackAlertSummary,
)
from custom_components.scorpiontrack_portal.binary_sensor import (
    ACCOUNT_BINARY_SENSORS,
    SHARE_BINARY_SENSORS,
)
from custom_components.scorpiontrack_portal.const import (
    ACCOUNT_SCAN_INTERVAL,
    DOMAIN,
    SHARE_SCAN_INTERVAL,
)
from custom_components.scorpiontrack_portal.sensor import (
    ACCOUNT_SENSORS,
    ACCOUNT_VEHICLE_SENSORS,
    SHARE_SENSORS,
    SHARE_VEHICLE_SENSORS,
    SHARE_VEHICLE_SHARE_SENSORS,
)
from custom_components.scorpiontrack_portal.switch import SWITCHES

from . import setup_integration

FIXED_NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
HYBRID_ISSUE_ID = "hybrid_share_unavailable_01SCORPIONTRACK_HYBRID_TEST"


def _entity_id(
    entity_registry: er.EntityRegistry,
    domain: str,
    unique_id: str,
) -> str:
    """Return an entity ID for a known ScorpionTrack unique ID."""
    entity_id = entity_registry.async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id is not None
    return entity_id


def _state(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    domain: str,
    unique_id: str,
) -> Any:
    """Return the current state for a known ScorpionTrack unique ID."""
    state = hass.states.get(_entity_id(entity_registry, domain, unique_id))
    assert state is not None
    return state


async def _async_advance_poll(
    hass: HomeAssistant,
    freezer: Any,
    interval: timedelta,
) -> None:
    """Advance time and allow a natural coordinator refresh."""
    freezer.tick(interval + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _with_share_position(
    share: ScorpionTrackShare, **changes: Any
) -> ScorpionTrackShare:
    """Return the share with its first vehicle's position changed."""
    vehicle = share.vehicles[0]
    return replace(
        share,
        vehicles=(replace(vehicle, position=replace(vehicle.position, **changes)),),
    )


async def test_share_unique_ids_and_tracker_state(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    share_config_entry: MockConfigEntry,
) -> None:
    """Share mode keeps its unique IDs and publishes one plain GPS tracker."""
    await setup_integration(hass, share_config_entry)

    expected_unique_ids = {
        "101_2001_tracker",
        *(f"101_2001_{description.key}" for description in SHARE_VEHICLE_SENSORS),
        *(f"101_2001_{description.key}" for description in SHARE_VEHICLE_SHARE_SENSORS),
        *(f"101_2001_{description.key}" for description in SHARE_BINARY_SENSORS),
        *(f"101_share_{description.key}" for description in SHARE_SENSORS),
    }
    assert {
        entry.unique_id
        for entry in er.async_entries_for_config_entry(
            entity_registry, share_config_entry.entry_id
        )
    } == expected_unique_ids

    tracker = _state(hass, entity_registry, "device_tracker", "101_2001_tracker")
    assert tracker.attributes["latitude"] == 51.5074
    assert tracker.attributes["longitude"] == -0.1278
    assert "registration" not in tracker.attributes
    assert "speed" not in tracker.attributes


async def test_account_unique_ids_and_tracker_state(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
) -> None:
    """Account mode keeps its unique IDs and publishes one plain GPS tracker."""
    await setup_integration(hass, account_config_entry)

    expected_unique_ids = {
        "42_2001_tracker",
        "42_mark_alerts_read",
        *(f"42_{description.key}" for description in ACCOUNT_SENSORS),
        *(f"42_2001_{description.key}" for description in ACCOUNT_VEHICLE_SENSORS),
        *(f"42_2001_{description.key}" for description in ACCOUNT_BINARY_SENSORS),
        *(f"42_2001_{description.key}" for description in SWITCHES),
    }
    assert {
        entry.unique_id
        for entry in er.async_entries_for_config_entry(
            entity_registry, account_config_entry.entry_id
        )
    } == expected_unique_ids

    tracker = _state(hass, entity_registry, "device_tracker", "42_2001_tracker")
    assert tracker.attributes["latitude"] == 51.5074
    assert tracker.attributes["longitude"] == -0.1278
    assert tracker.attributes["gps_accuracy"] == 5
    assert "privacy_mode_enabled" not in tracker.attributes


@pytest.mark.parametrize(
    ("distance_units", "speed", "speed_unit", "odometer", "odometer_unit"),
    [
        ("miles", 30.012, "mph", 1000.0, "mi"),
        ("kilometres", 48.3, "km/h", 1609.344, "km"),
    ],
)
async def test_account_units_follow_distance_preference(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_account: ScorpionTrackAccountData,
    distance_units: str,
    speed: float,
    speed_unit: str,
    odometer: float,
    odometer_unit: str,
) -> None:
    """Native metric values are displayed in the account's preferred units."""
    vehicle = replace(mock_account.vehicles[0], odometer=1609.344)
    client_mocks.account.async_refresh_account.return_value = replace(
        mock_account, distance_units=distance_units, vehicles=(vehicle,)
    )
    await setup_integration(hass, account_config_entry)

    speed_state = _state(hass, entity_registry, "sensor", "42_2001_speed")
    assert float(speed_state.state) == pytest.approx(speed, abs=0.001)
    assert speed_state.attributes["unit_of_measurement"] == speed_unit
    odometer_state = _state(hass, entity_registry, "sensor", "42_2001_odometer")
    assert float(odometer_state.state) == pytest.approx(odometer)
    assert odometer_state.attributes["unit_of_measurement"] == odometer_unit


@pytest.mark.parametrize(
    ("distance_units", "speed", "speed_unit"),
    [("miles", 30.012, "mph"), ("kilometres", 48.3, "km/h")],
)
async def test_share_speed_follows_distance_preference(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    share_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
    distance_units: str,
    speed: float,
    speed_unit: str,
) -> None:
    """Share speeds are displayed in the share owner's preferred unit."""
    client_mocks.share.async_get_share.return_value = replace(
        mock_share, distance_units=distance_units
    )
    await setup_integration(hass, share_config_entry)

    state = _state(hass, entity_registry, "sensor", "101_2001_speed")
    assert float(state.state) == pytest.approx(speed, abs=0.001)
    assert state.attributes["unit_of_measurement"] == speed_unit


@pytest.mark.parametrize(
    ("status", "expected"),
    [("moving", "moving"), ("Parked", "parked"), ("teleporting", STATE_UNKNOWN)],
)
async def test_account_status_is_a_known_enum_value(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_account: ScorpionTrackAccountData,
    status: str,
    expected: str,
) -> None:
    """Portal statuses map to translated enum states, never free text."""
    client_mocks.account.async_refresh_account.return_value = replace(
        mock_account, vehicles=(replace(mock_account.vehicles[0], status=status),)
    )
    await setup_integration(hass, account_config_entry)

    state = _state(hass, entity_registry, "sensor", "42_2001_status")
    assert state.state == expected


@pytest.mark.parametrize(
    ("status", "expected"), [("idle", "idle"), ("unknown", STATE_UNKNOWN)]
)
async def test_share_status_is_a_known_enum_value(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    share_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
    status: str,
    expected: str,
) -> None:
    """Share statuses map to translated enum states."""
    client_mocks.share.async_get_share.return_value = replace(
        mock_share, vehicles=(replace(mock_share.vehicles[0], status=status),)
    )
    await setup_integration(hass, share_config_entry)

    state = _state(hass, entity_registry, "sensor", "101_2001_status")
    assert state.state == expected


@pytest.mark.parametrize(
    ("begin_field", "end_field", "unique_id"),
    [
        ("garage_mode_begin", "garage_mode_end", "42_2001_garage_mode_active"),
        ("transport_mode_begin", "transport_mode_end", "42_2001_transport_mode_active"),
        ("no_alert_start", "no_alert_end", "42_2001_no_alert_mode_active"),
    ],
)
async def test_account_mode_windows_follow_the_clock_with_unchanged_payload(
    hass: HomeAssistant,
    freezer: Any,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_account: ScorpionTrackAccountData,
    begin_field: str,
    end_field: str,
    unique_id: str,
) -> None:
    """Scheduled portal modes switch at their boundaries without new data."""
    now = dt_util.utcnow()
    vehicle = replace(
        mock_account.vehicles[0],
        **{begin_field: now + timedelta(hours=1), end_field: now + timedelta(hours=3)},
    )
    client_mocks.account.async_refresh_account.return_value = replace(
        mock_account, vehicles=(vehicle,)
    )
    await setup_integration(hass, account_config_entry)
    assert _state(hass, entity_registry, "binary_sensor", unique_id).state == "off"

    await _async_advance_poll(hass, freezer, timedelta(hours=2))
    assert _state(hass, entity_registry, "binary_sensor", unique_id).state == "on"

    await _async_advance_poll(hass, freezer, timedelta(hours=2))
    assert _state(hass, entity_registry, "binary_sensor", unique_id).state == "off"


@pytest.mark.parametrize(
    ("speed_kmh", "ignition", "expected"),
    [
        (1.0, False, "parked"),
        (2.9, None, "parked"),
        (1.0, True, "idle"),
        (3.0, False, "moving"),
    ],
)
async def test_hybrid_status_ignores_gps_drift(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    hybrid_account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
    speed_kmh: float,
    ignition: bool | None,
    expected: str,
) -> None:
    """A share speed below the portal's 3 km/h threshold is not movement."""
    share = _with_share_position(
        mock_share,
        timestamp=datetime.now(UTC),
        speed_kmh=speed_kmh,
        ignition=ignition,
    )
    client_mocks.share.async_get_share.return_value = replace(
        share, vehicles=(replace(share.vehicles[0], status="moving"),)
    )
    await setup_integration(hass, hybrid_account_config_entry)

    assert _state(hass, entity_registry, "sensor", "42_2001_status").state == expected


@pytest.mark.parametrize(
    ("speed_kmh", "ignition", "expected"),
    [(1.0, False, "parked"), (1.0, True, "idle"), (3.0, False, "moving")],
)
async def test_share_status_ignores_gps_drift(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    share_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
    speed_kmh: float,
    ignition: bool | None,
    expected: str,
) -> None:
    """Shared-link status applies the same 3 km/h moving threshold."""
    share = _with_share_position(mock_share, speed_kmh=speed_kmh, ignition=ignition)
    client_mocks.share.async_get_share.return_value = replace(
        share, vehicles=(replace(share.vehicles[0], status="moving"),)
    )
    await setup_integration(hass, share_config_entry)

    assert _state(hass, entity_registry, "sensor", "101_2001_status").state == expected


async def test_hybrid_account_uses_newer_share_position(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    hybrid_account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
) -> None:
    """Hybrid account entities use the fresher shared position and status."""
    client_mocks.share.async_get_share.return_value = _with_share_position(
        mock_share,
        latitude=52.1234,
        longitude=-1.2345,
        timestamp=datetime.now(UTC),
        speed_kmh=80.0,
    )
    await setup_integration(hass, hybrid_account_config_entry)

    tracker = _state(hass, entity_registry, "device_tracker", "42_2001_tracker")
    assert tracker.attributes["latitude"] == 52.1234
    assert tracker.attributes["longitude"] == -1.2345
    speed = _state(hass, entity_registry, "sensor", "42_2001_speed")
    assert float(speed.state) == pytest.approx(49.710, abs=0.001)
    assert _state(hass, entity_registry, "sensor", "42_2001_status").state == "moving"


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(None, None), (None, -1.2345), (52.1234, None)],
)
async def test_hybrid_share_with_incomplete_coordinates_preserves_account_location(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    hybrid_account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
    latitude: float | None,
    longitude: float | None,
) -> None:
    """An incomplete shared coordinate pair must not replace portal location."""
    client_mocks.share.async_get_share.return_value = _with_share_position(
        mock_share,
        latitude=latitude,
        longitude=longitude,
        timestamp=datetime.now(UTC),
        speed_kmh=80.0,
    )
    await setup_integration(hass, hybrid_account_config_entry)

    tracker = _state(hass, entity_registry, "device_tracker", "42_2001_tracker")
    assert tracker.attributes["latitude"] == 51.5074
    assert tracker.attributes["longitude"] == -0.1278
    speed = _state(hass, entity_registry, "sensor", "42_2001_speed")
    assert float(speed.state) == pytest.approx(49.710, abs=0.001)


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


async def test_hybrid_share_connection_failure_keeps_newer_position(
    hass: HomeAssistant,
    freezer: Any,
    entity_registry: er.EntityRegistry,
    issue_registry: ir.IssueRegistry,
    hybrid_account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
) -> None:
    """A transient share failure keeps the last newer position without a repair."""
    client_mocks.share.async_get_share.return_value = _with_share_position(
        mock_share, latitude=53.0, timestamp=datetime.now(UTC)
    )
    await setup_integration(hass, hybrid_account_config_entry)
    client_mocks.share.async_get_share.side_effect = ScorpionTrackConnectionError(
        "connection failed"
    )

    await _async_advance_poll(hass, freezer, SHARE_SCAN_INTERVAL)

    tracker = _state(hass, entity_registry, "device_tracker", "42_2001_tracker")
    assert tracker.state != STATE_UNAVAILABLE
    assert tracker.attributes["latitude"] == 53.0
    assert issue_registry.async_get_issue(DOMAIN, HYBRID_ISSUE_ID) is None


@pytest.mark.parametrize(
    "error",
    [
        ScorpionTrackInvalidTokenError("invalid token"),
        ScorpionTrackShareUnavailableError("expired"),
    ],
)
async def test_hybrid_share_unusable_link_raises_and_clears_repair(
    hass: HomeAssistant,
    freezer: Any,
    entity_registry: er.EntityRegistry,
    issue_registry: ir.IssueRegistry,
    hybrid_account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    error: Exception,
) -> None:
    """An expired or revoked hybrid link asks the user to reconfigure it."""
    client_mocks.share.async_get_share.side_effect = error
    await setup_integration(hass, hybrid_account_config_entry)

    issue = issue_registry.async_get_issue(DOMAIN, HYBRID_ISSUE_ID)
    assert issue is not None
    assert issue.translation_key == "hybrid_share_unavailable"
    assert issue.translation_placeholders == {"title": "ScorpionTrack (Owner)"}
    tracker = _state(hass, entity_registry, "device_tracker", "42_2001_tracker")
    assert tracker.state != STATE_UNAVAILABLE

    client_mocks.share.async_get_share.side_effect = None
    await _async_advance_poll(hass, freezer, SHARE_SCAN_INTERVAL)

    assert issue_registry.async_get_issue(DOMAIN, HYBRID_ISSUE_ID) is None


async def test_hybrid_share_repair_is_cleared_on_unload(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
    hybrid_account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
) -> None:
    """Unloading, for example to reconfigure the link, clears the repair."""
    client_mocks.share.async_get_share.side_effect = ScorpionTrackInvalidTokenError(
        "invalid token"
    )
    await setup_integration(hass, hybrid_account_config_entry)
    assert issue_registry.async_get_issue(DOMAIN, HYBRID_ISSUE_ID) is not None

    assert await hass.config_entries.async_unload(hybrid_account_config_entry.entry_id)

    assert issue_registry.async_get_issue(DOMAIN, HYBRID_ISSUE_ID) is None


async def test_hybrid_matches_vehicle_by_normalized_registration(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    hybrid_account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
) -> None:
    """A changed cross-source ID should fall back to a unique registration."""
    share = _with_share_position(mock_share, latitude=53.0, timestamp=datetime.now(UTC))
    client_mocks.share.async_get_share.return_value = replace(
        share,
        vehicles=(replace(share.vehicles[0], id=9999, registration="ab12cde"),),
    )
    await setup_integration(hass, hybrid_account_config_entry)

    tracker = _state(hass, entity_registry, "device_tracker", "42_2001_tracker")
    assert tracker.attributes["latitude"] == 53.0


async def test_hybrid_does_not_replace_newer_account_position(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    hybrid_account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
) -> None:
    """A stale share payload should never move an account tracker backwards."""
    client_mocks.share.async_get_share.return_value = _with_share_position(
        mock_share, latitude=53.0, timestamp=datetime.now(UTC) - timedelta(days=1)
    )
    await setup_integration(hass, hybrid_account_config_entry)

    tracker = _state(hass, entity_registry, "device_tracker", "42_2001_tracker")
    assert tracker.attributes["latitude"] == 51.5074


async def test_share_removed_vehicle_device_is_removed_and_recreated(
    hass: HomeAssistant,
    freezer: Any,
    caplog: pytest.LogCaptureFixture,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    share_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
) -> None:
    """A vehicle removed from the share loses its device until it returns."""
    await setup_integration(hass, share_config_entry)
    assert device_registry.async_get_device(identifiers={(DOMAIN, "101_2001")})

    client_mocks.share.async_get_share.return_value = replace(mock_share, vehicles=())
    await _async_advance_poll(hass, freezer, SHARE_SCAN_INTERVAL)

    assert device_registry.async_get_device(identifiers={(DOMAIN, "101_2001")}) is None
    assert device_registry.async_get_device(identifiers={(DOMAIN, "share_101")})
    assert not [
        entry
        for entry in er.async_entries_for_config_entry(
            entity_registry, share_config_entry.entry_id
        )
        if entry.unique_id.startswith("101_2001_")
    ]
    assert "Unexpected error updating listener" not in caplog.text

    client_mocks.share.async_get_share.return_value = mock_share
    await _async_advance_poll(hass, freezer, SHARE_SCAN_INTERVAL)

    tracker = _state(hass, entity_registry, "device_tracker", "101_2001_tracker")
    assert tracker.attributes["latitude"] == 51.5074


async def test_account_removed_vehicle_device_is_removed_and_recreated(
    hass: HomeAssistant,
    freezer: Any,
    caplog: pytest.LogCaptureFixture,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_account: ScorpionTrackAccountData,
) -> None:
    """A vehicle removed from the account loses its device until it returns."""
    await setup_integration(hass, account_config_entry)
    assert device_registry.async_get_device(identifiers={(DOMAIN, "42_vehicle_2001")})

    client_mocks.account.async_refresh_account.return_value = replace(
        mock_account, vehicles=()
    )
    await _async_advance_poll(hass, freezer, ACCOUNT_SCAN_INTERVAL)

    assert (
        device_registry.async_get_device(identifiers={(DOMAIN, "42_vehicle_2001")})
        is None
    )
    assert device_registry.async_get_device(identifiers={(DOMAIN, "account_42")})
    assert (
        entity_registry.async_get_entity_id("device_tracker", DOMAIN, "42_2001_tracker")
        is None
    )
    assert "Unexpected error updating listener" not in caplog.text

    client_mocks.account.async_refresh_account.return_value = mock_account
    await _async_advance_poll(hass, freezer, ACCOUNT_SCAN_INTERVAL)

    tracker = _state(hass, entity_registry, "device_tracker", "42_2001_tracker")
    assert tracker.state != STATE_UNAVAILABLE


async def test_share_adds_new_vehicle_dynamically(
    hass: HomeAssistant,
    freezer: Any,
    entity_registry: er.EntityRegistry,
    share_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
) -> None:
    """New share vehicles are added without reloading the entry."""
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

    assert _state(hass, entity_registry, "device_tracker", "101_2002_tracker")
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
    """New account vehicles are added without reloading the entry."""
    await setup_integration(hass, account_config_entry)
    new_vehicle = replace(
        mock_account.vehicles[0],
        id=2002,
        registration="EF34 ABC",
        alias="Tiguan",
        model="Tiguan",
    )
    client_mocks.account.async_refresh_account.return_value = replace(
        mock_account, vehicles=(*mock_account.vehicles, new_vehicle)
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
    client_mocks.share.async_get_share.side_effect = ScorpionTrackConnectionError(
        "connection failed"
    )

    await _async_advance_poll(hass, freezer, SHARE_SCAN_INTERVAL)

    tracker = _state(hass, entity_registry, "device_tracker", "101_2001_tracker")
    assert tracker.state == STATE_UNAVAILABLE


def _deterministic_share(share: ScorpionTrackShare) -> ScorpionTrackShare:
    """Return the fixture share with fixed timestamps."""
    share = _with_share_position(share, timestamp=FIXED_NOW - timedelta(minutes=5))
    return replace(
        share,
        created_at=FIXED_NOW - timedelta(days=3),
        expires_at=FIXED_NOW + timedelta(days=28),
    )


def _deterministic_account(
    account: ScorpionTrackAccountData,
) -> ScorpionTrackAccountData:
    """Return the fixture account with fixed timestamps and full readings."""
    vehicle = account.vehicles[0]
    assert vehicle.position is not None
    position = replace(
        vehicle.position,
        timestamp=FIXED_NOW - timedelta(minutes=5),
        gps_satellites=9,
        hdop=0.8,
    )
    vehicle = replace(
        vehicle,
        position=position,
        odometer=12345.6,
        vehicle_voltage=12.64,
        backup_battery_voltage=4.1,
        gps_antenna_voltage=3.3,
        gps_antenna_current=12.0,
        mot_due=date(2027, 3, 14),
        tax_due=date(2027, 1, 1),
        last_service_date=date(2026, 9, 1),
        unit_last_checked_in=FIXED_NOW - timedelta(minutes=10),
        ewm_enabled=True,
        armed_mode_enabled=False,
        g_sense_enabled=True,
        pending_commands_count=1,
        description="Weekend car",
        colour="Lapiz Blue",
        fuel_type="Petrol",
        battery_type="12V lead-acid",
        unit_make="ScorpionTrack",
        unit_model="S5",
        installed_at=datetime(2024, 5, 20, 9, 30, tzinfo=UTC),
        install_complete=True,
        immobiliser_fitted=False,
        driver_module=True,
    )
    alert = ScorpionTrackAlertSummary(
        id=1,
        source="vehicle",
        type="Speeding",
        severity="medium",
        timestamp=FIXED_NOW - timedelta(hours=1),
        read_status=False,
        vehicle_id=2001,
        vehicle_registration="AB12 CDE",
        vehicle_alias="Golf R",
        vehicle_name=None,
        alert_name=None,
        speed_recorded=None,
        road_speed=None,
        idle=None,
        engine_hours=None,
        latitude=None,
        longitude=None,
    )
    return replace(
        account,
        vehicles=(vehicle,),
        alerts=(alert,),
        fetched_at=FIXED_NOW,
    )


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize(
    ("entry_fixture", "platform"),
    [
        ("share_config_entry", Platform.BINARY_SENSOR),
        ("share_config_entry", Platform.DEVICE_TRACKER),
        ("share_config_entry", Platform.SENSOR),
        ("account_config_entry", Platform.BINARY_SENSOR),
        ("account_config_entry", Platform.BUTTON),
        ("account_config_entry", Platform.DEVICE_TRACKER),
        ("account_config_entry", Platform.SENSOR),
        ("account_config_entry", Platform.SWITCH),
    ],
)
async def test_entity_snapshots(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    request: pytest.FixtureRequest,
    client_mocks: SimpleNamespace,
    freezer: Any,
    mock_share: ScorpionTrackShare,
    mock_account: ScorpionTrackAccountData,
    entry_fixture: str,
    platform: Platform,
) -> None:
    """Every entity's registry entry and state match the reviewed snapshot."""
    # Location stale depends on the clock.
    freezer.move_to(FIXED_NOW)
    client_mocks.share.async_get_share.return_value = _deterministic_share(mock_share)
    client_mocks.account.async_refresh_account.return_value = _deterministic_account(
        mock_account
    )
    entry: MockConfigEntry = request.getfixturevalue(entry_fixture)
    with patch("custom_components.scorpiontrack_portal.PLATFORMS", [platform]):
        await setup_integration(hass, entry)

    await snapshot_platform(hass, entity_registry, snapshot, entry.entry_id)


@pytest.mark.parametrize(
    ("entry_fixture", "expected"),
    [
        (
            "account_config_entry",
            {
                "sensor.scorpiontrack_owner_vehicle_count",
                "sensor.scorpiontrack_owner_last_refreshed",
                "sensor.scorpiontrack_owner_user_id",
                "sensor.golf_r_location",
                "sensor.golf_r_portal_state",
                "sensor.golf_r_installed",
                "sensor.golf_r_registration",
                "sensor.golf_r_description",
                "sensor.golf_r_alias",
                "sensor.golf_r_colour",
                "sensor.golf_r_fuel_type",
                "sensor.golf_r_battery_type",
                "sensor.golf_r_make",
                "sensor.golf_r_model",
                "sensor.golf_r_vehicle_type",
                "sensor.golf_r_unit_model",
                "sensor.golf_r_unit_make",
                "sensor.golf_r_pending_command_count",
                "binary_sensor.golf_r_location_stale",
                "binary_sensor.golf_r_driver_module_fitted",
                "binary_sensor.golf_r_installation_complete",
                "binary_sensor.golf_r_immobiliser_fitted",
            },
        ),
        (
            "share_config_entry",
            {
                "sensor.family_cars_share_title",
                "sensor.family_cars_shared_by",
                "sensor.family_cars_share_created",
                "sensor.ab12_cde_location",
                "sensor.ab12_cde_share_expires",
                "binary_sensor.ab12_cde_location_stale",
            },
        ),
    ],
)
async def test_restored_entities_are_disabled_by_default(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    request: pytest.FixtureRequest,
    entry_fixture: str,
    expected: set[str],
) -> None:
    """Entities removed in 0.5.0 return disabled, with their 0.4.0 entity IDs."""
    entry: MockConfigEntry = request.getfixturevalue(entry_fixture)
    await setup_integration(hass, entry)

    restored = [
        registry_entry
        for registry_entry in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        )
        if registry_entry.unique_id.endswith("_v2")
    ]
    assert {registry_entry.entity_id for registry_entry in restored} == expected
    for registry_entry in restored:
        assert registry_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(registry_entry.entity_id) is None


async def test_restored_entities_stay_disabled_after_0_5_removed_them(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
) -> None:
    """Registry entries deleted by 0.5.0 do not bring their entities back enabled."""
    account_config_entry.add_to_hass(hass)
    removed = {
        ("sensor", "42_vehicle_count"): "scorpiontrack_owner_vehicle_count",
        ("sensor", "42_2001_registration"): "golf_r_registration",
        ("binary_sensor", "42_2001_location_stale"): "golf_r_location_stale",
    }
    for (domain, unique_id), object_id in removed.items():
        registry_entry = entity_registry.async_get_or_create(
            domain,
            DOMAIN,
            unique_id,
            config_entry=account_config_entry,
            suggested_object_id=object_id,
        )
        entity_registry.async_remove(registry_entry.entity_id)

    await setup_integration(hass, account_config_entry)

    for (domain, unique_id), object_id in removed.items():
        assert entity_registry.async_get_entity_id(domain, DOMAIN, unique_id) is None
        registry_entry = entity_registry.async_get(f"{domain}.{object_id}")
        assert registry_entry is not None
        assert registry_entry.unique_id == f"{unique_id}_v2"
        assert registry_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_share_location_stale_follows_the_clock(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    freezer: Any,
    share_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
) -> None:
    """Location stale turns on as the position ages, without new share data."""
    freezer.move_to(FIXED_NOW)
    client_mocks.share.async_get_share.return_value = _with_share_position(
        mock_share, timestamp=FIXED_NOW - timedelta(hours=24) + timedelta(minutes=1)
    )
    await setup_integration(hass, share_config_entry)
    unique_id = "101_2001_location_stale_v2"
    assert _state(hass, entity_registry, "binary_sensor", unique_id).state == "off"

    await _async_advance_poll(hass, freezer, SHARE_SCAN_INTERVAL)

    assert _state(hass, entity_registry, "binary_sensor", unique_id).state == "on"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_account_location_stale_follows_the_clock(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    freezer: Any,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_account: ScorpionTrackAccountData,
) -> None:
    """Portal-account Location stale also turns on as the position ages."""
    freezer.move_to(FIXED_NOW)
    vehicle = mock_account.vehicles[0]
    assert vehicle.position is not None
    position = replace(
        vehicle.position,
        timestamp=FIXED_NOW - timedelta(hours=24) + timedelta(minutes=1),
    )
    client_mocks.account.async_refresh_account.return_value = replace(
        mock_account, vehicles=(replace(vehicle, position=position),)
    )
    await setup_integration(hass, account_config_entry)
    unique_id = "42_2001_location_stale_v2"
    assert _state(hass, entity_registry, "binary_sensor", unique_id).state == "off"

    await _async_advance_poll(hass, freezer, ACCOUNT_SCAN_INTERVAL)

    assert _state(hass, entity_registry, "binary_sensor", unique_id).state == "on"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_account_location_falls_back_to_coordinates(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_account: ScorpionTrackAccountData,
) -> None:
    """Location shows coordinates without an address; no position is stale."""
    vehicle = mock_account.vehicles[0]
    assert vehicle.position is not None
    client_mocks.account.async_refresh_account.return_value = replace(
        mock_account,
        vehicles=(
            replace(vehicle, position=replace(vehicle.position, address=None)),
            replace(
                vehicle, id=2002, alias="Van", registration="CD34 EFG", position=None
            ),
        ),
    )
    await setup_integration(hass, account_config_entry)

    location = _state(hass, entity_registry, "sensor", "42_2001_location_v2")
    assert location.state == "51.507400, -0.127800"
    no_position = _state(hass, entity_registry, "sensor", "42_2002_location_v2")
    assert no_position.state == STATE_UNKNOWN
    stale = _state(hass, entity_registry, "binary_sensor", "42_2002_location_stale_v2")
    assert stale.state == "on"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_share_text_is_cut_to_the_state_limit(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    share_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
) -> None:
    """Long portal text is cut to 255 characters, and empty text is unknown."""
    share = _with_share_position(mock_share, address="A" * 300)
    client_mocks.share.async_get_share.return_value = replace(
        share, title="", owner_name="B" * 300
    )
    await setup_integration(hass, share_config_entry)

    location = _state(hass, entity_registry, "sensor", "101_2001_location_v2")
    assert location.state == "A" * 255
    shared_by = _state(hass, entity_registry, "sensor", "101_share_shared_by_v2")
    assert shared_by.state == "B" * 255
    title = _state(hass, entity_registry, "sensor", "101_share_share_title_v2")
    assert title.state == STATE_UNKNOWN


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_share_created_without_time_zone_is_utc(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    share_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
) -> None:
    """A share creation time sent without a time zone is read as UTC."""
    client_mocks.share.async_get_share.return_value = replace(
        mock_share, created_at=datetime(2026, 10, 28, 12, 0)
    )
    await setup_integration(hass, share_config_entry)

    created = _state(hass, entity_registry, "sensor", "101_share_share_created_v2")
    assert created.state == "2026-10-28T12:00:00+00:00"
