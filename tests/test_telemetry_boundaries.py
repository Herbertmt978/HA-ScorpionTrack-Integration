"""Exercise telemetry boundaries through HTTP parsing and Home Assistant states."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyscorpiontrack import ScorpionTrackShare
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scorpiontrack_portal.const import DOMAIN

from . import setup_integration
from .test_account_api_parsing import (
    _client,
    _login_responses,
    _ResponseSpec,
    _ScriptedSession,
)


@pytest.mark.parametrize(
    ("map_data", "latest_data", "vehicle_data", "domain", "key", "expected"),
    [
        (
            {"odometer": 0, "state": "OFF"},
            {},
            {"odometer": 100},
            "sensor",
            "odometer",
            "0.0",
        ),
        (
            {"gps": 0, "state": "OFF"},
            {"gps_satellites": 9},
            {},
            "sensor",
            "gps_satellites",
            "0",
        ),
        (
            {"gps": "bad", "gps_satellites": 8, "state": "OFF"},
            {},
            {},
            "sensor",
            "gps_satellites",
            "8",
        ),
        ({"vehicleVoltage": "12.50V"}, {}, {}, "sensor", "battery_voltage", "12.5"),
        ({"ignition": False}, {}, {}, "binary_sensor", "ignition", "off"),
        ({"state": "OFF"}, {}, {}, "binary_sensor", "engine", "unknown"),
        ({"engine": False}, {}, {}, "binary_sensor", "engine", "off"),
        (
            {"lat": 51.5, "state": "OFF"},
            {"speed": 50, "ignition": True},
            {},
            "sensor",
            "status",
            "moving",
        ),
        ({"lat": 51.5}, {}, {"state": "ALM"}, "sensor", "status", "alarm"),
        ({"speed": 10, "unitsSpeed": "mph"}, {}, {}, "sensor", "speed", "16.09344"),
        (
            {"speedkm": 0, "speed": 10, "unitsSpeed": "mph"},
            {},
            {},
            "sensor",
            "speed",
            "0.0",
        ),
        (
            {"speedkm": "bad", "speed": 10, "unitsSpeed": "mph"},
            {},
            {},
            "sensor",
            "speed",
            "16.09344",
        ),
        (
            {"speedkm": "NaN", "state": "OFF"},
            {"speed": 0},
            {},
            "sensor",
            "speed",
            "0.0",
        ),
        (
            {"bearing": "Infinity", "state": "OFF"},
            {"bearing": 90},
            {},
            "sensor",
            "heading",
            "90.0",
        ),
        (
            {"timestamp": 10**30, "state": "OFF"},
            {"timestamp": "2026-10-12T12:00:00Z"},
            {},
            "sensor",
            "last_reported",
            "2026-10-12T12:00:00+00:00",
        ),
        (
            {"timestamp": "9" * 100, "state": "OFF"},
            {"timestamp": "2026-10-12T12:00:00Z"},
            {},
            "sensor",
            "last_reported",
            "2026-10-12T12:00:00+00:00",
        ),
        (
            {"vehicleVoltage": "NaNV", "state": "OFF"},
            {"vehicleVoltage": 12.4},
            {},
            "sensor",
            "battery_voltage",
            "12.4",
        ),
        (
            {"state": "OFF"},
            {"odometer": 0},
            {"odometer": 100},
            "sensor",
            "odometer",
            "0.0",
        ),
        (
            {"gps": float("inf"), "state": "OFF"},
            {"gps_satellites": 9},
            {},
            "sensor",
            "gps_satellites",
            "9",
        ),
        (
            {"engine": float("nan"), "state": "OFF"},
            {},
            {},
            "binary_sensor",
            "engine",
            "unknown",
        ),
        (
            {"vehicleVoltage": 10**1000, "state": "OFF"},
            {"vehicleVoltage": 12.4},
            {},
            "sensor",
            "battery_voltage",
            "12.4",
        ),
        (
            {"unitId": 123, "distanceUnits": "Mi"},
            {},
            {"timestamp": "2026-10-12T12:00:00Z"},
            "sensor",
            "last_reported",
            "2026-10-12T12:00:00+00:00",
        ),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_account_telemetry_boundaries(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    map_data: dict[str, object],
    latest_data: dict[str, object],
    vehicle_data: dict[str, object],
    domain: str,
    key: str,
    expected: str,
) -> None:
    """Keep zero and unknown readings, merge before deriving, reject bad numbers."""
    # Speed rows assert parsed km/h, so use an account that displays km/h.
    login = (
        _login_responses(distance_units="kilometres")
        if key == "speed"
        else _login_responses()
    )
    session = _ScriptedSession(
        [
            *login,
            _ResponseSpec(
                json.dumps(
                    {
                        "vehicles": {
                            "data": [
                                {
                                    "id": 2001,
                                    "registration": "AB12 CDE",
                                    **vehicle_data,
                                    "latest_position": {"data": latest_data},
                                }
                            ]
                        }
                    }
                )
            ),
            _ResponseSpec(json.dumps({"Positions": [{"vehicleId": 2001, **map_data}]})),
            _ResponseSpec(json.dumps({"data": [], "meta": {"total": 0}})),
            _ResponseSpec(json.dumps({"data": []})),
        ]
    )
    account = await _client(session).async_refresh_account()
    assert session.remaining == 0
    client_mocks.account.async_refresh_account.return_value = account
    await setup_integration(hass, account_config_entry)
    entity_id = entity_registry.async_get_entity_id(domain, DOMAIN, f"42_2001_{key}")
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    if key == "speed":
        assert float(state.state) == pytest.approx(float(expected), rel=0.001)
        assert state.attributes["unit_of_measurement"] == "km/h"
    else:
        assert state.state == expected
    if key == "status" and map_data.get("state"):
        assert account.vehicles[0].position.friendly_state == expected


@pytest.mark.parametrize(
    ("installed", "expected"),
    [("bad", "2026-10-12T12:00:00+00:00"), (0, "1970-01-01T00:00:00+00:00")],
)
async def test_installed_date_boundaries(installed: object, expected: str) -> None:
    """An invalid install date falls back to the unit's fitted date; zero is kept."""
    session = _ScriptedSession(
        [
            *_login_responses(),
            _ResponseSpec(
                json.dumps(
                    {
                        "vehicles": {
                            "data": [
                                {
                                    "id": 2001,
                                    "installed": installed,
                                    "unit": {
                                        "data": {"fitted": "2026-10-12T12:00:00Z"}
                                    },
                                }
                            ]
                        }
                    }
                )
            ),
            _ResponseSpec(json.dumps({"Positions": [{"vehicleId": 2001}]})),
            _ResponseSpec(json.dumps({"data": [], "meta": {"total": 0}})),
            _ResponseSpec(json.dumps({"data": []})),
        ]
    )
    account = await _client(session).async_refresh_account()

    installed_at = account.vehicles[0].installed_at
    assert installed_at is not None
    assert installed_at.isoformat() == expected


@pytest.mark.parametrize("alert_data", [None, 123, {"unexpected": "object"}])
async def test_malformed_optional_alert_data_keeps_vehicle_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    alert_data: object,
) -> None:
    """Malformed optional alerts cannot prevent valid tracking from refreshing."""
    session = _ScriptedSession(
        [
            *_login_responses(),
            _ResponseSpec(json.dumps({"vehicles": {"data": [{"id": 2001}]}})),
            _ResponseSpec(
                json.dumps({"Positions": [{"vehicleId": 2001, "speedkm": 0}]})
            ),
            _ResponseSpec(json.dumps({"data": alert_data, "meta": {"total": 0}})),
            _ResponseSpec(json.dumps({"data": []})),
        ]
    )
    account = await _client(session).async_refresh_account()
    client_mocks.account.async_refresh_account.return_value = account
    await setup_integration(hass, account_config_entry)
    entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, "42_2001_speed")
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert float(state.state) == 0
    assert account.alerts == ()


@pytest.mark.parametrize("distance_units", ["miles", "km"])
@pytest.mark.parametrize("map_present", [True, False])
async def test_odometer_has_consistent_units_across_sources(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    account_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    distance_units: str,
    map_present: bool,
) -> None:
    """A mile map reading and kilometre fleet fallback describe the same distance."""
    session = _ScriptedSession(
        [
            *_login_responses(distance_units=distance_units),
            _ResponseSpec(
                json.dumps({"vehicles": {"data": [{"id": 2001, "odometer": 160.9344}]}})
            ),
            _ResponseSpec(
                json.dumps(
                    {
                        "Positions": [
                            {
                                "vehicleId": 2001,
                                "odometer": 100,
                                "distanceUnits": "Mi",
                                "state": "OFF",
                            }
                        ]
                        if map_present
                        else []
                    }
                )
            ),
            _ResponseSpec(json.dumps({"data": [], "meta": {"total": 0}})),
            _ResponseSpec(json.dumps({"data": []})),
        ]
    )
    account = await _client(session).async_refresh_account()
    client_mocks.account.async_refresh_account.return_value = account
    await setup_integration(hass, account_config_entry)
    entity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, "42_2001_odometer"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert float(state.state) == pytest.approx(
        100 if distance_units == "miles" else 160.9344
    )
    assert state.attributes["unit_of_measurement"] == (
        "mi" if distance_units == "miles" else "km"
    )


@pytest.mark.parametrize(
    ("ignition", "expected"), [(None, "unknown"), (False, "off"), (True, "on")]
)
async def test_share_ignition_preserves_unknown(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    share_config_entry: MockConfigEntry,
    client_mocks: SimpleNamespace,
    mock_share: ScorpionTrackShare,
    ignition: bool | None,
    expected: str,
) -> None:
    """Unknown ignition is distinguishable from an explicit off reading."""
    vehicle = mock_share.vehicles[0]
    client_mocks.share.async_get_share.return_value = replace(
        mock_share,
        vehicles=(
            replace(vehicle, position=replace(vehicle.position, ignition=ignition)),
        ),
    )
    await setup_integration(hass, share_config_entry)
    entity_id = entity_registry.async_get_entity_id(
        "binary_sensor", DOMAIN, "101_2001_ignition"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == expected
