"""Security and reliability tests for the authenticated account API client."""

from __future__ import annotations

import asyncio
import base64
import importlib
import json
import logging
import sys
from dataclasses import fields
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from aiohttp import ClientError

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COMPONENT_DIR = _REPO_ROOT / "custom_components" / "scorpiontrack"
_TEST_PACKAGE = "_scorpiontrack_under_test"


def _install_import_shims() -> None:
    """Load account_api without requiring a full Home Assistant test install."""
    if "homeassistant.const" not in sys.modules:
        try:
            importlib.import_module("homeassistant.const")
        except ModuleNotFoundError as err:
            if err.name not in {"homeassistant", "homeassistant.const"}:
                raise

            homeassistant = ModuleType("homeassistant")
            homeassistant.__path__ = []  # type: ignore[attr-defined]
            homeassistant_const = ModuleType("homeassistant.const")

            class Platform(StrEnum):
                """Minimal stand-in for the enum used by the component constants."""

                BINARY_SENSOR = "binary_sensor"
                BUTTON = "button"
                DEVICE_TRACKER = "device_tracker"
                SENSOR = "sensor"
                SWITCH = "switch"

            homeassistant_const.Platform = Platform
            homeassistant.const = homeassistant_const  # type: ignore[attr-defined]
            sys.modules["homeassistant"] = homeassistant
            sys.modules["homeassistant.const"] = homeassistant_const

    if _TEST_PACKAGE not in sys.modules:
        package = ModuleType(_TEST_PACKAGE)
        package.__path__ = [str(_COMPONENT_DIR)]  # type: ignore[attr-defined]
        sys.modules[_TEST_PACKAGE] = package


_install_import_shims()

account_api = importlib.import_module(f"{_TEST_PACKAGE}.account_api")
ScorpionTrackAccountClient = account_api.ScorpionTrackAccountClient
ScorpionTrackAccountData = account_api.ScorpionTrackAccountData
ScorpionTrackAuthError = account_api.ScorpionTrackAuthError
ScorpionTrackConnectionError = account_api.ScorpionTrackConnectionError
ScorpionTrackPortalContext = account_api.ScorpionTrackPortalContext
ScorpionTrackPortalError = account_api.ScorpionTrackPortalError


class FakeResponse:
    """Small aiohttp response context-manager fake."""

    def __init__(self, status: int, url: str, body: str) -> None:
        self.status = status
        self.url = url
        self._body = body

    async def text(self) -> str:
        """Return the configured response body."""
        return self._body

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeSession:
    """Capture aiohttp-style requests without using the network."""

    def __init__(
        self,
        *,
        status: int = 200,
        body: str = "{}",
        final_url: str | None = None,
        error: ClientError | None = None,
    ) -> None:
        self.status = status
        self.body = body
        self.final_url = final_url
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        """Record a request, then return or raise the configured result."""
        self.calls.append({"method": method, "url": url, "kwargs": kwargs})
        if self.error is not None:
            raise self.error
        return FakeResponse(self.status, self.final_url or url, self.body)


def _client(
    session: FakeSession,
    *,
    email: str = "person@example.test",
    password: str = "test-password",
) -> Any:
    return ScorpionTrackAccountClient(
        session=session,
        email=email,
        password=password,
    )


def _portal_context(
    *,
    api_key: str = "test-fms-api-key",
    fms_url: str = "https://fleet.scorpiontrack.com/v1",
) -> Any:
    return ScorpionTrackPortalContext(
        user_id=123,
        name="Test Account",
        distance_units="miles",
        app_api_key=api_key,
        fms_api_url=fms_url,
    )


def _portal_page(fms_url: str, *, api_key: str = "test-fms-api-key") -> str:
    user = json.dumps(
        {
            "userId": 123,
            "name": "Test Account",
            "distanceUnits": "miles",
            "appApiKey": api_key,
        }
    )
    return (
        f"<script>window.ScorpionData.user = {user};\n"
        f'window.ScorpionData.fmsApiUrl = "{fms_url}";</script>'
    )


def _perform_raw_request(client: Any, request_kind: str) -> Any:
    if request_kind == "portal":
        return asyncio.run(client._request_text("GET", "/test", ajax=True))
    return asyncio.run(client._request_fms_text(_portal_context(), "GET", "/vehicles"))


@pytest.mark.parametrize(
    ("fms_url", "expected_url"),
    [
        (
            "https://fleet.scorpiontrack.com/api/",
            "https://fleet.scorpiontrack.com/api",
        ),
        (
            "https://scorpiontrack.com:443/fms/",
            "https://scorpiontrack.com:443/fms",
        ),
    ],
)
def test_portal_context_accepts_only_trusted_fms_hosts(
    fms_url: str, expected_url: str
) -> None:
    session = FakeSession(body=_portal_page(fms_url))
    client = _client(session)

    context = asyncio.run(client.async_get_portal_context())

    assert context.fms_api_url == expected_url
    assert context.user_id == 123
    assert len(session.calls) == 1


@pytest.mark.parametrize(
    "fms_url",
    [
        "http://fleet.scorpiontrack.com/api",
        "https://attacker.example/api",
        "https://scorpiontrack.com.attacker.example/api",
        "https://api-key@fleet.scorpiontrack.com/api",
        "https://fleet.scorpiontrack.com:8443/api",
        "https://fleet.scorpiontrack.com/api?token=test",
        "https://fleet.scorpiontrack.com/api#fragment",
        "//fleet.scorpiontrack.com/api",
        "https://fleet.scorpiontrack.com:not-a-port/api",
    ],
)
def test_portal_context_rejects_untrusted_fms_urls(fms_url: str) -> None:
    session = FakeSession(body=_portal_page(fms_url))
    client = _client(session)

    with pytest.raises(ScorpionTrackPortalError, match="fleet API URL"):
        asyncio.run(client.async_get_portal_context())

    assert len(session.calls) == 1


@pytest.mark.parametrize(
    "absolute_path",
    [
        "https://attacker.example/collect",
        "//attacker.example/collect",
        "http:collect",
    ],
)
def test_fms_request_rejects_absolute_paths_before_sending_credentials(
    absolute_path: str,
) -> None:
    session = FakeSession()
    client = _client(session)

    with pytest.raises(
        ScorpionTrackPortalError, match="FMS request path must be relative"
    ):
        asyncio.run(
            client._request_fms_json(
                _portal_context(),
                "GET",
                absolute_path,
            )
        )

    assert session.calls == []


def test_secret_values_are_absent_from_context_repr_and_account_data() -> None:
    api_key = "repr-must-not-contain-this-api-key"
    fms_url = "https://fleet.scorpiontrack.com/private-path"
    context = _portal_context(api_key=api_key, fms_url=fms_url)

    context_repr = repr(context)
    assert api_key not in context_repr
    assert "app_api_key=" not in context_repr

    data = ScorpionTrackAccountData(
        email="person@example.test",
        title="ScorpionTrack (Test Account)",
        user_id=123,
        distance_units="miles",
        app_api_key_available=True,
        fms_api_available=True,
        vehicles=(),
        total_alerts=0,
        unread_alerts=0,
        alerts=(),
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    field_names = {field.name for field in fields(data)}

    assert field_names.isdisjoint(
        {"app_api_key", "fms_api_url", "password", "authorization"}
    )
    assert not hasattr(data, "app_api_key")
    assert not hasattr(data, "fms_api_url")
    assert api_key not in repr(data)
    assert fms_url not in repr(data)
    assert data.app_api_key_available is True
    assert data.fms_api_available is True


@pytest.mark.parametrize("request_kind", ["portal", "fms"])
@pytest.mark.parametrize("status", [401, 403])
def test_auth_http_statuses_raise_auth_error(request_kind: str, status: int) -> None:
    session = FakeSession(status=status)
    client = _client(session)

    with pytest.raises(ScorpionTrackAuthError):
        _perform_raw_request(client, request_kind)

    assert len(session.calls) == 1


@pytest.mark.parametrize("request_kind", ["portal", "fms"])
@pytest.mark.parametrize("status", [408, 425, 429, 500, 503, 599])
def test_transient_http_statuses_raise_connection_error(
    request_kind: str, status: int
) -> None:
    session = FakeSession(status=status)
    client = _client(session)

    with pytest.raises(ScorpionTrackConnectionError, match=rf"HTTP {status}"):
        _perform_raw_request(client, request_kind)

    assert len(session.calls) == 1


@pytest.mark.parametrize("request_kind", ["portal", "fms"])
@pytest.mark.parametrize("status", [300, 302, 400, 404, 418, 499])
def test_other_non_success_http_statuses_raise_permanent_portal_error(
    request_kind: str, status: int
) -> None:
    session = FakeSession(status=status)
    client = _client(session)

    with pytest.raises(ScorpionTrackPortalError, match=rf"HTTP {status}"):
        _perform_raw_request(client, request_kind)

    assert len(session.calls) == 1


def test_authenticated_fms_request_does_not_follow_redirects() -> None:
    session = FakeSession(
        status=302,
        final_url="https://attacker.example/collect",
        body="redirect",
    )
    client = _client(session)

    with pytest.raises(ScorpionTrackPortalError, match="HTTP 302"):
        asyncio.run(
            client._request_fms_text(
                _portal_context(),
                "GET",
                "/vehicles",
            )
        )

    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == "https://fleet.scorpiontrack.com/v1/vehicles"
    assert call["kwargs"]["allow_redirects"] is False


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, ""),
        (204, " \r\n\t"),
    ],
)
def test_empty_successful_fms_response_returns_none(status: int, body: str) -> None:
    session = FakeSession(status=status, body=body)
    client = _client(session)

    result = asyncio.run(
        client._request_fms_json(
            _portal_context(),
            "PUT",
            "/vehicles/123",
            json_data={"garage_mode": True},
        )
    )

    assert result is None
    assert len(session.calls) == 1
    assert session.calls[0]["method"] == "PUT"


@pytest.mark.parametrize("request_kind", ["portal", "fms"])
def test_transport_errors_do_not_log_credentials_or_authorization(
    request_kind: str, caplog: pytest.LogCaptureFixture
) -> None:
    email = "private.person@example.test"
    password = "password-must-not-be-logged"
    api_key = "api-key-must-not-be-logged"
    authorization = "Basic " + base64.b64encode(api_key.encode()).decode()
    leaked_error = ClientError(
        f"email={email} password={password} api_key={api_key} "
        f"Authorization={authorization}"
    )
    session = FakeSession(error=leaked_error)
    client = _client(session, email=email, password=password)
    caplog.set_level(logging.DEBUG, logger=account_api.__name__)

    with pytest.raises(ScorpionTrackConnectionError):
        if request_kind == "portal":
            asyncio.run(
                client._request_text(
                    "POST",
                    "/login",
                    data={"email": email, "pass": password},
                    ajax=False,
                )
            )
        else:
            asyncio.run(
                client._request_fms_text(
                    _portal_context(api_key=api_key),
                    "POST",
                    "/vehicles",
                    json_data={"value": "safe"},
                )
            )

    logged = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name == account_api.__name__
    )
    assert "p***@example.test" in logged
    assert email not in logged
    assert password not in logged
    assert api_key not in logged
    assert authorization not in logged
    assert "authorization" not in logged.lower()
