"""Behavior tests for authenticated account parsing and workflows."""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from custom_components.scorpiontrack.account_api import (
    ScorpionTrackAccountClient,
    ScorpionTrackAccountData,
    ScorpionTrackAlertSummary,
    ScorpionTrackAuthError,
    ScorpionTrackConnectionError,
    ScorpionTrackPortalError,
    ScorpionTrackVehicleSummary,
)


@dataclass(slots=True)
class _ResponseSpec:
    """One response returned by the scripted HTTP session."""

    body: str = ""
    status: int = 200
    final_url: str | None = None


class _FakeResponse:
    """Minimal asynchronous aiohttp response context manager."""

    def __init__(self, spec: _ResponseSpec, request_url: str) -> None:
        self.status = spec.status
        self.url = spec.final_url or request_url
        self._body = spec.body

    async def text(self) -> str:
        """Return the scripted response body."""
        return self._body

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class _ScriptedSession:
    """Return HTTP responses in order while recording every request."""

    def __init__(
        self,
        responses: Iterable[_ResponseSpec | BaseException],
    ) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        """Record a request and return the next scripted result."""
        if not self._responses:
            raise AssertionError(f"Unexpected request: {method} {url}")

        self.calls.append({"method": method, "url": url, "kwargs": kwargs})
        result = self._responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return _FakeResponse(result, url)

    @property
    def remaining(self) -> int:
        """Return the number of unused scripted responses."""
        return len(self._responses)


def _portal_page(
    *,
    user_id: object = 42,
    name: object = " Fleet Owner ",
    distance_units: object = "miles",
    api_key: object = "private-fms-key",
    fms_url: str = "https://fleet.scorpiontrack.com/v1/",
) -> str:
    """Build an authenticated portal bootstrap page."""
    user = json.dumps(
        {
            "userId": user_id,
            "name": name,
            "distanceUnits": distance_units,
            "appApiKey": api_key,
        }
    )
    return (
        f"<script>window.ScorpionData.user = {user};\n"
        f'window.ScorpionData.fmsApiUrl = "{fms_url}";</script>'
    )


def _login_responses(**portal_page_overrides: object) -> list[_ResponseSpec]:
    """Return the three responses used by a successful portal login."""
    return [
        _ResponseSpec(
            '<form id="login_form"><input name="ci_csrf_token" '
            'value="csrf-private"><input name="pass"></form>'
        ),
        _ResponseSpec("<html>Account selected</html>"),
        _ResponseSpec(_portal_page(**portal_page_overrides)),
    ]


def _client(
    session: _ScriptedSession,
    *,
    email: str = " Owner@Example.COM ",
    password: str = "private-password",
) -> ScorpionTrackAccountClient:
    """Create the real client against a scripted session."""
    return ScorpionTrackAccountClient(
        session,  # type: ignore[arg-type]
        email,
        password,
        timeout_seconds=1,
    )


def _vehicle_payloads() -> tuple[dict[str, object], dict[str, object]]:
    """Return two representative, deliberately differently shaped vehicles."""
    rich_vehicle: dict[str, object] = {
        "id": "101",
        "registration": " AB12 CDE ",
        "alias": " Roadster ",
        "make": "Example",
        "model": "GT",
        "type": "Car",
        "description": " Primary vehicle ",
        "colour": "Blue",
        "fuel_type": "Petrol",
        "state": "OFF",
        "odometer": "9876.5",
        "installed": "2026-01-02T03:04:05Z",
        "timestamp": "2026-02-03 04:05:06",
        "lastService": "2026-01-01",
        "mot_due": "2026-10-10T12:00:00+01:00",
        "tax_due": "not-a-date",
        "battery_type": "AGM",
        "install_complete": "yes",
        "immobiliser": 1,
        "driver_module": 0,
        "ewm_enabled": True,
        "g_sense": "false",
        "privacy_mode_enabled": "on",
        "zero_speed_mode_enabled": "off",
        "monitored_mode_enabled": 1,
        "transport_mode_begin": "2026-01-01T00:00:00Z",
        "transport_mode_end": "2026-01-02T00:00:00Z",
        "garage_mode_begin": None,
        "garage_mode_end": None,
        "no_alert_start": "invalid",
        "no_alert_end": "invalid",
        "unit": {
            "data": {
                "type": "S5",
                "model": "Track Pro",
                "make": "Scorpion",
                "fitted": "2025-12-01T10:30:00Z",
                "last_checked_in": 1_767_225_600,
            }
        },
        "groups": {
            "data": [
                {"group_name": " Family "},
                {"name": "Work"},
                "ignored",
            ]
        },
        "pending_commands": {"data": [{"id": 1}, {"id": 2}, "ignored"]},
        "healthcheck": {
            "data": {
                "vehicle_system_voltage": "12.4",
                "backup_battery_voltage": "3.7",
                "gps_antenna_voltage": 5,
                "gps_antenna_current": "0.2",
            }
        },
        "latest_position": {
            "data": {
                "lat": "51.5",
                "lng": "-0.13",
                "timestamp": "2026-02-03T04:00:00Z",
                "speed": "2.5",
                "bearing": "90",
                "accuracy": "4.5",
                "address": "Fallback address",
                "ignition": "false",
                "engine": "0",
                "gps_satellites": "9",
                "hdop": "0.8",
                "state": "OFF",
                "vehicleVoltage": "12.3",
                "odometer": "9875",
                "unitType": "S5",
                "unitId": "501",
                "distanceUnits": "miles",
                "unitsSpeed": "mph",
            }
        },
    }
    alarm_vehicle: dict[str, object] = {
        "id": 202,
        "registration": "ZX98 YWV",
        "alias": "",
        "state": "ALM",
        "groups": [{"name": "Solo"}],
        "latest_position": {},
    }
    return rich_vehicle, alarm_vehicle


def _alert_payload(*, alert_id: object = "77") -> dict[str, object]:
    """Return a representative alert record."""
    return {
        "id": alert_id,
        "source": "device",
        "type": "Speed",
        "severity": "high",
        "timestamp": "2026-02-03T05:06:07Z",
        "read_status": "0",
        "vehicle": {
            "data": {
                "id": "101",
                "registration": "AB12 CDE",
                "alias": "Roadster",
                "vehicle_name": "Example GT",
            }
        },
        "details": {
            "data": {
                "alert_name": "Overspeed",
                "speed_recorded": "72.5",
                "road_speed": 60,
                "idle": "1.5",
                "engine_hours": "800.25",
            }
        },
        "location": {"data": {"latitude": "51.5074", "longitude": "-0.1278"}},
    }


@pytest.mark.asyncio
async def test_login_submits_normalized_credentials_then_reuses_session() -> None:
    """A successful login sends the CSRF form once and caches the session."""
    session = _ScriptedSession(_login_responses())
    client = _client(session)

    await client.async_login()
    await client.async_login()

    assert client.email == "owner@example.com"
    assert session.remaining == 0
    assert [call["method"] for call in session.calls] == ["GET", "POST", "GET"]
    login_form = session.calls[1]["kwargs"]["data"]
    assert login_form == {
        "ci_csrf_token": "csrf-private",
        "register": "false",
        "email": "owner@example.com",
        "pass": "private-password",
    }
    assert session.calls[0]["kwargs"]["allow_redirects"] is True
    assert session.calls[1]["kwargs"]["allow_redirects"] is False
    assert session.calls[2]["url"].endswith("/customer/vehicle/vehiclelist")


@pytest.mark.asyncio
async def test_login_debug_log_does_not_expose_portal_user_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A successful login log should not expose the internal portal user ID."""
    internal_user_id = 987654321
    session = _ScriptedSession(_login_responses(user_id=internal_user_id))
    client = _client(session)
    caplog.set_level(
        logging.DEBUG, logger="custom_components.scorpiontrack.account_api"
    )

    await client.async_login()

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "Authenticated ScorpionTrack portal session" in logged
    assert str(internal_user_id) not in logged
    assert "user_id" not in logged


@pytest.mark.asyncio
async def test_login_failure_log_does_not_expose_portal_user_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A malformed portal bootstrap log should not expose its internal user ID."""
    internal_user_id = 987654321
    session = _ScriptedSession(_login_responses(user_id=internal_user_id, api_key=""))
    client = _client(session)
    caplog.set_level(
        logging.WARNING, logger="custom_components.scorpiontrack.account_api"
    )

    with pytest.raises(ScorpionTrackPortalError, match="fleet API details"):
        await client.async_login()

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "missing expected API details" in logged
    assert str(internal_user_id) not in logged
    assert "user_id" not in logged


@pytest.mark.asyncio
async def test_login_refuses_a_cross_origin_credential_preserving_redirect() -> None:
    """A 307 response cannot replay portal credentials to another origin."""
    target = "https://attacker.example/collect"
    session = _ScriptedSession(
        [
            _ResponseSpec(
                '<input name="ci_csrf_token" value="csrf-private"><input name="pass">'
            ),
            _ResponseSpec("redirect", status=307, final_url=target),
        ]
    )
    client = _client(session)

    with pytest.raises(ScorpionTrackPortalError, match="HTTP 307"):
        await client.async_login()

    assert session.remaining == 0
    assert [call["method"] for call in session.calls] == ["GET", "POST"]
    assert session.calls[1]["kwargs"]["allow_redirects"] is False
    assert session.calls[1]["url"] == (
        "https://app.scorpiontrack.com/login/check_for_multiple_accounts"
    )
    assert all(call["url"] != target for call in session.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("responses", "error_type", "message"),
    [
        (
            [_ResponseSpec('<form id="login_form"><input name="pass"></form>')],
            ScorpionTrackPortalError,
            "CSRF token",
        ),
        (
            [
                _ResponseSpec(
                    '<input name="ci_csrf_token" value="csrf"><input name="pass">'
                ),
                _ResponseSpec('<h1 class="u-heading--dark">Error</h1> user_model.php'),
            ],
            ScorpionTrackAuthError,
            "rejected",
        ),
        (
            [
                *_login_responses()[:-1],
                _ResponseSpec(
                    '<form id="login_form"><input name="ci_csrf_token" '
                    'value="new"><input name="pass"></form>',
                    final_url="https://app.scorpiontrack.com/home/login",
                ),
            ],
            ScorpionTrackAuthError,
            "redirected back to login",
        ),
        (
            _login_responses(api_key=""),
            ScorpionTrackPortalError,
            "fleet API details",
        ),
    ],
)
async def test_login_classifies_portal_failures(
    responses: list[_ResponseSpec],
    error_type: type[Exception],
    message: str,
) -> None:
    """Credential failures and malformed bootstrap pages remain distinguishable."""
    session = _ScriptedSession(responses)
    client = _client(session)

    with pytest.raises(error_type, match=message):
        await client.async_login()

    assert session.remaining == 0


@pytest.mark.asyncio
async def test_login_timeout_is_a_retryable_connection_error() -> None:
    """A portal timeout is classified as a connection failure, not bad credentials."""
    session = _ScriptedSession([TimeoutError("must not be copied")])
    client = _client(session)

    with pytest.raises(
        ScorpionTrackConnectionError,
        match="Timed out contacting the ScorpionTrack portal",
    ) as raised:
        await client.async_login()

    assert "must not be copied" not in str(raised.value)
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_refresh_parses_paginated_account_snapshot_and_public_models() -> None:
    """A full refresh parses vehicles, merged positions, alerts, and account metadata."""
    rich_vehicle, alarm_vehicle = _vehicle_payloads()
    page_one = {
        "vehicles": {
            "data": [rich_vehicle],
            "meta": {"total_pages": "2"},
        }
    }
    page_two = {
        "vehicles": {
            "data": [alarm_vehicle, {"id": "not-an-id"}, "ignored"],
            "meta": {"total_pages": 2},
        }
    }
    map_positions = {
        "Positions": [
            {
                "vehicleId": "101",
                "lat": "52.0",
                "timestamp": "2026-02-03T04:05:00Z",
                "speedkm": "5.0",
                "bearing": "180",
                "ignition": 1,
                "engine": True,
                "gps": "10",
                "state": "MOV",
                "vehicleVoltage": "12.8",
                "odometer": "9999.5",
            },
            {"vehicleId": 202, "state": "ALM"},
            {"vehicleId": "invalid", "lat": 1},
            "ignored",
        ]
    }
    session = _ScriptedSession(
        [
            *_login_responses(),
            _ResponseSpec(json.dumps(page_one)),
            _ResponseSpec(json.dumps(page_two)),
            _ResponseSpec(json.dumps(map_positions)),
            _ResponseSpec(
                json.dumps({"data": [_alert_payload()], "meta": {"total": "7"}})
            ),
            _ResponseSpec(json.dumps({"meta": {"total": "3"}})),
        ]
    )
    client = _client(session)

    account = await client.async_refresh_account()

    assert session.remaining == 0
    assert account.email == "owner@example.com"
    assert account.title == "ScorpionTrack (Fleet Owner)"
    assert account.user_id == 42
    assert account.distance_units == "miles"
    assert account.uses_miles is True
    assert account.app_api_key_available is True
    assert account.fms_api_available is True
    assert account.total_alerts == 7
    assert account.unread_alerts == 3
    assert account.fetched_at.tzinfo is UTC

    assert len(account.vehicles) == 2
    roadster, alarm = account.vehicles
    assert roadster.id == 101
    assert roadster.display_name == "Roadster"
    assert roadster.registration == "AB12 CDE"
    assert roadster.group_names == ("Family", "Work")
    assert roadster.pending_commands_count == 2
    assert roadster.install_complete is True
    assert roadster.immobiliser_fitted is True
    assert roadster.driver_module is False
    assert roadster.privacy_mode_enabled is True
    assert roadster.zero_speed_mode_enabled is False
    assert roadster.armed_mode_enabled is True
    assert roadster.last_service_date == date(2026, 1, 1)
    assert roadster.tax_due is None
    assert roadster.unit_type == "S5"
    assert roadster.unit_model == "Track Pro"
    assert roadster.vehicle_voltage == 12.8
    assert roadster.backup_battery_voltage == 3.7
    assert roadster.position is not None
    assert roadster.position.latitude == 52.0
    assert roadster.position.longitude == -0.13
    assert roadster.position.address == "Fallback address"
    assert roadster.position.speed_kmh == 5.0
    assert roadster.position.gps_satellites == 10
    assert roadster.position.distance_units == "miles"
    assert roadster.raw_state == "MOV"
    assert roadster.status == "moving"
    assert roadster.transport_mode_active is False
    assert roadster.garage_mode_active is False
    assert roadster.no_alert_mode_active is False

    assert alarm.display_name == "ZX98 YWV"
    assert alarm.status == "alarm"
    assert alarm.group_names == ("Solo",)
    assert alarm.position is not None
    assert alarm.position.friendly_state == "alarm"

    assert len(account.alerts) == 1
    alert = account.alerts[0]
    assert account.latest_alert is alert
    assert alert.display_vehicle == "Roadster"
    assert alert.location == "51.507400, -0.127800"
    assert alert.summary == "Speed (Overspeed) - Roadster"
    assert alert.timestamp == datetime(2026, 2, 3, 5, 6, 7, tzinfo=UTC)
    assert alert.read_status is False
    assert alert.as_attribute_dict() == {
        "alert_id": 77,
        "source": "device",
        "type": "Speed",
        "severity": "high",
        "timestamp": "2026-02-03T05:06:07+00:00",
        "read": False,
        "vehicle_id": 101,
        "vehicle": "Roadster",
        "vehicle_registration": "AB12 CDE",
        "alert_name": "Overspeed",
        "speed_recorded": 72.5,
        "road_speed": 60.0,
        "idle": 1.5,
        "engine_hours": 800.25,
        "alert_location": "51.507400, -0.127800",
        "alert_latitude": 51.5074,
        "alert_longitude": -0.1278,
    }

    vehicle_calls = [
        call for call in session.calls if call["url"].endswith("/v1/vehicles")
    ]
    assert [call["kwargs"]["params"]["page"] for call in vehicle_calls] == [1, 2]
    fms_headers = vehicle_calls[0]["kwargs"]["headers"]
    assert (
        fms_headers["Authorization"]
        == "Basic " + base64.b64encode(b"private-fms-key").decode()
    )
    assert vehicle_calls[0]["kwargs"]["allow_redirects"] is False


@pytest.mark.asyncio
async def test_refresh_keeps_vehicles_when_optional_endpoints_are_malformed() -> None:
    """Map and alert endpoint failures do not discard otherwise valid vehicles."""
    session = _ScriptedSession(
        [
            *_login_responses(name=""),
            _ResponseSpec(
                json.dumps(
                    {
                        "vehicles": {
                            "data": [{"id": 1, "registration": "SAFE 1"}],
                            "meta": {"total_pages": 1},
                        }
                    }
                )
            ),
            _ResponseSpec("[]"),
            _ResponseSpec("[]"),
            _ResponseSpec("not-json"),
        ]
    )
    client = _client(session)

    account = await client.async_refresh_account()

    assert session.remaining == 0
    assert account.title == "ScorpionTrack Account"
    assert [vehicle.display_name for vehicle in account.vehicles] == ["SAFE 1"]
    assert account.alerts == ()
    assert account.total_alerts is None
    assert account.unread_alerts is None
    assert account.latest_alert is None


@pytest.mark.asyncio
async def test_refresh_ignores_a_malformed_optional_alert_record() -> None:
    """One malformed alert payload cannot take down vehicle tracking."""
    session = _ScriptedSession(
        [
            *_login_responses(),
            _ResponseSpec(
                json.dumps(
                    {
                        "vehicles": {
                            "data": [],
                            "meta": {"total_pages": 1},
                        }
                    }
                )
            ),
            _ResponseSpec(
                json.dumps(
                    {"data": [_alert_payload(alert_id="invalid")], "meta": {"total": 1}}
                )
            ),
            _ResponseSpec(json.dumps({"data": []})),
        ]
    )
    client = _client(session)

    account = await client.async_refresh_account()

    assert session.remaining == 0
    assert account.vehicles == ()
    assert account.alerts == ()
    assert account.total_alerts == 1
    assert account.unread_alerts == 0


@pytest.mark.asyncio
async def test_refresh_reauthenticates_once_after_fleet_session_expiry() -> None:
    """A rejected fleet key triggers one forced login and a complete retry."""
    empty_vehicles = {"vehicles": {"data": [], "meta": {"total_pages": 1}}}
    session = _ScriptedSession(
        [
            *_login_responses(),
            _ResponseSpec("denied", status=401),
            *_login_responses(),
            _ResponseSpec(json.dumps(empty_vehicles)),
            _ResponseSpec(json.dumps({"data": [], "meta": {"total": 0}})),
            _ResponseSpec(json.dumps({"data": []})),
        ]
    )
    client = _client(session)

    account = await client.async_refresh_account()

    assert session.remaining == 0
    assert account.vehicles == ()
    assert account.total_alerts == 0
    assert account.unread_alerts == 0
    assert [call["method"] for call in session.calls].count("POST") == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vehicle_response", "message"),
    [
        (_ResponseSpec("not-json"), "non-JSON content"),
        (_ResponseSpec("[]"), "non-object payload"),
    ],
)
async def test_get_vehicles_rejects_malformed_fleet_payloads(
    vehicle_response: _ResponseSpec,
    message: str,
) -> None:
    """Malformed mandatory vehicle responses become stable portal errors."""
    session = _ScriptedSession([*_login_responses(), vehicle_response])
    client = _client(session)

    with pytest.raises(ScorpionTrackPortalError, match=message):
        await client.async_get_vehicles()

    assert session.remaining == 0


@pytest.mark.asyncio
async def test_get_vehicles_rejects_a_malformed_map_payload() -> None:
    """The standalone vehicle API reports a malformed mandatory map response."""
    session = _ScriptedSession(
        [
            *_login_responses(),
            _ResponseSpec(
                json.dumps(
                    {
                        "vehicles": {
                            "data": [{"id": 9}],
                            "meta": {"total_pages": 1},
                        }
                    }
                )
            ),
            _ResponseSpec("[]"),
        ]
    )
    client = _client(session)

    with pytest.raises(ScorpionTrackPortalError, match="map endpoint"):
        await client.async_get_vehicles(limit=1)

    assert session.remaining == 0
    assert session.calls[3]["kwargs"]["params"] == {"page": 1, "limit": 1}


@pytest.mark.asyncio
async def test_get_vehicles_returns_an_empty_tuple_without_a_map_request() -> None:
    """An account with no vehicles completes without a pointless map call."""
    session = _ScriptedSession(
        [
            *_login_responses(),
            _ResponseSpec(
                json.dumps(
                    {
                        "vehicles": {
                            "data": [],
                            "meta": {"total_pages": 1},
                        }
                    }
                )
            ),
        ]
    )
    client = _client(session)

    vehicles = await client.async_get_vehicles(limit=50)

    assert vehicles == ()
    assert session.remaining == 0
    assert len(session.calls) == 4
    assert session.calls[-1]["kwargs"]["params"] == {"page": 1, "limit": 50}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("map_response", "error_type", "message"),
    [
        (
            _ResponseSpec(
                '<form id="login_form"><input name="ci_csrf_token" '
                'value="new"><input name="pass"></form>',
                final_url="https://app.scorpiontrack.com/home/login",
            ),
            ScorpionTrackAuthError,
            "redirected to login",
        ),
        (_ResponseSpec("not-json"), ScorpionTrackPortalError, "non-JSON content"),
    ],
)
async def test_get_vehicles_classifies_portal_map_failures(
    map_response: _ResponseSpec,
    error_type: type[Exception],
    message: str,
) -> None:
    """Login HTML and corrupt JSON from the map endpoint remain distinguishable."""
    session = _ScriptedSession(
        [
            *_login_responses(),
            _ResponseSpec(
                json.dumps(
                    {
                        "vehicles": {
                            "data": [{"id": 9}],
                            "meta": {"total_pages": 1},
                        }
                    }
                )
            ),
            map_response,
        ]
    )
    client = _client(session)

    with pytest.raises(error_type, match=message):
        await client.async_get_vehicles()

    assert session.remaining == 0


@pytest.mark.asyncio
async def test_get_vehicles_classifies_a_fleet_timeout_as_retryable() -> None:
    """A fleet timeout is surfaced as a retryable connection failure."""
    session = _ScriptedSession([*_login_responses(), TimeoutError("upstream secret")])
    client = _client(session)

    with pytest.raises(
        ScorpionTrackConnectionError,
        match="Timed out contacting the ScorpionTrack fleet API",
    ) as raised:
        await client.async_get_vehicles()

    assert "upstream secret" not in str(raised.value)
    assert session.remaining == 0


@pytest.mark.asyncio
async def test_set_vehicle_mode_reauthenticates_and_retries_exact_payload() -> None:
    """A mode update retries after auth expiry without changing the command."""
    session = _ScriptedSession(
        [
            *_login_responses(),
            _ResponseSpec("denied", status=403),
            *_login_responses(),
            _ResponseSpec("", status=204),
        ]
    )
    client = _client(session)

    await client.async_set_vehicle_mode(101, "privacy_mode_enabled", enabled=1)

    assert session.remaining == 0
    put_calls = [call for call in session.calls if call["method"] == "PUT"]
    assert len(put_calls) == 2
    assert {call["url"] for call in put_calls} == {
        "https://fleet.scorpiontrack.com/v1/vehicles/101"
    }
    assert [call["kwargs"]["json"] for call in put_calls] == [
        {"privacy_mode_enabled": True},
        {"privacy_mode_enabled": True},
    ]


@pytest.mark.asyncio
async def test_mark_all_alerts_read_paginates_and_uses_server_count() -> None:
    """The read action gathers every page and returns the server's update count."""
    first_alert = _alert_payload(alert_id=1)
    second_alert = _alert_payload(alert_id="2")
    session = _ScriptedSession(
        [
            *_login_responses(),
            _ResponseSpec(
                json.dumps(
                    {
                        "data": [first_alert, {"id": "invalid"}, "ignored"],
                        "meta": {"total_pages": 2},
                    }
                )
            ),
            _ResponseSpec(
                json.dumps(
                    {
                        "data": [second_alert],
                        "meta": {"total_pages": "2"},
                    }
                )
            ),
            _ResponseSpec(json.dumps({"data": {"updated": "2"}})),
        ]
    )
    client = _client(session)

    updated = await client.async_mark_all_alerts_read()

    assert updated == 2
    assert session.remaining == 0
    alert_gets = [
        call
        for call in session.calls
        if call["method"] == "GET" and call["url"].endswith("/alerts-dashboard/alerts")
    ]
    assert [call["kwargs"]["params"]["page"] for call in alert_gets] == [1, 2]
    bulk_call = session.calls[-1]
    assert bulk_call["url"].endswith("/alerts-dashboard/bulk-read")
    assert bulk_call["kwargs"]["json"] == {"alerts": [first_alert, second_alert]}


@pytest.mark.asyncio
async def test_mark_all_alerts_read_reauthenticates_before_bulk_update() -> None:
    """The alert action repeats discovery after auth expiry before mutating state."""
    unread_alert = _alert_payload(alert_id=1)
    session = _ScriptedSession(
        [
            *_login_responses(),
            _ResponseSpec("denied", status=401),
            *_login_responses(),
            _ResponseSpec(json.dumps({"data": [unread_alert]})),
            _ResponseSpec(json.dumps({})),
        ]
    )
    client = _client(session)

    updated = await client.async_mark_all_alerts_read()

    assert updated == 1
    assert session.remaining == 0
    fms_gets = [
        call
        for call in session.calls
        if call["method"] == "GET" and call["url"].endswith("/alerts-dashboard/alerts")
    ]
    assert len(fms_gets) == 2
    assert session.calls[-1]["kwargs"]["json"] == {"alerts": [unread_alert]}


@pytest.mark.asyncio
async def test_mark_all_alerts_read_rejects_a_non_object_page() -> None:
    """The mutating alert action stops before POST on a malformed discovery page."""
    session = _ScriptedSession([*_login_responses(), _ResponseSpec("[]")])
    client = _client(session)

    with pytest.raises(ScorpionTrackPortalError, match="non-object payload"):
        await client.async_mark_all_alerts_read()

    assert session.remaining == 0
    assert len([call for call in session.calls if call["method"] == "POST"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("unread_payload", "bulk_payload", "expected", "expected_posts"),
    [
        ({"data": [], "meta": {"total_pages": 1}}, None, 0, 1),
        ({"data": [{"id": 1}]}, {}, 1, 2),
        ({"data": [{"id": 1}]}, {"data": {"updated": "bad"}}, 1, 2),
    ],
)
async def test_mark_all_alerts_read_handles_empty_and_unreported_updates(
    unread_payload: dict[str, object],
    bulk_payload: dict[str, object] | None,
    expected: int,
    expected_posts: int,
) -> None:
    """The read action is a no-op when empty and otherwise has a safe count fallback."""
    responses = [*_login_responses(), _ResponseSpec(json.dumps(unread_payload))]
    if bulk_payload is not None:
        responses.append(_ResponseSpec(json.dumps(bulk_payload)))
    session = _ScriptedSession(responses)
    client = _client(session)

    updated = await client.async_mark_all_alerts_read()

    assert updated == expected
    assert session.remaining == 0
    assert len([call for call in session.calls if call["method"] == "POST"]) == (
        expected_posts
    )


def _alert(**overrides: object) -> ScorpionTrackAlertSummary:
    """Build a public alert model with explicit defaults."""
    values: dict[str, object] = {
        field.name: None for field in fields(ScorpionTrackAlertSummary)
    }
    values.update(id=9, **overrides)
    return ScorpionTrackAlertSummary(**values)  # type: ignore[arg-type]


def test_alert_and_account_properties_have_stable_empty_fallbacks() -> None:
    """Public display helpers remain useful for sparse portal records."""
    alert = _alert(vehicle_id=55, type="Alert", alert_name="alert")
    generic_alert = _alert()
    no_alerts = ScorpionTrackAccountData(
        email="secret@example.com",
        title="ScorpionTrack Account",
        user_id=None,
        distance_units=" kilometres ",
        app_api_key_available=False,
        fms_api_available=False,
        vehicles=(),
        total_alerts=None,
        unread_alerts=None,
        alerts=(),
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert alert.display_vehicle == "Vehicle 55"
    assert alert.location is None
    assert alert.summary == "Alert - Vehicle 55"
    assert generic_alert.display_vehicle is None
    assert generic_alert.summary == "Alert"
    assert no_alerts.uses_miles is False
    assert no_alerts.latest_alert is None
    assert "secret@example.com" not in repr(no_alerts)


def test_vehicle_mode_properties_cover_inside_and_incomplete_windows() -> None:
    """Public mode flags require a complete window containing the current time."""
    now = datetime.now(UTC)
    values: dict[str, object] = {
        field.name: None for field in fields(ScorpionTrackVehicleSummary)
    }
    values.update(
        id=8,
        pending_commands_count=0,
        group_names=(),
        transport_mode_begin=now - timedelta(hours=1),
        transport_mode_end=now + timedelta(hours=1),
        garage_mode_begin=now - timedelta(hours=1),
        garage_mode_end=None,
    )
    vehicle = ScorpionTrackVehicleSummary(**values)  # type: ignore[arg-type]

    assert vehicle.display_name == "Vehicle 8"
    assert vehicle.transport_mode_active is True
    assert vehicle.garage_mode_active is False
    assert vehicle.no_alert_mode_active is False
