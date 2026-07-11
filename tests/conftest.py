"""Fixtures for ScorpionTrack tests."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from pyscorpiontrack import (
    ScorpionTrackClient,
    ScorpionTrackPosition,
    ScorpionTrackShare,
    ScorpionTrackVehicle,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import (
    HomeAssistantSnapshotExtension,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.scorpiontrack.account_api import (
    ScorpionTrackAccountData,
    ScorpionTrackVehiclePosition,
    ScorpionTrackVehicleSummary,
)
from custom_components.scorpiontrack.const import (
    CONF_SETUP_TYPE,
    CONF_SHARE_TOKEN,
    DOMAIN,
    SETUP_TYPE_ACCOUNT,
    SETUP_TYPE_SHARE,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations for every test."""


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Use Home Assistant's snapshot serializer."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture
def mock_share() -> ScorpionTrackShare:
    """Return a representative shared-location response."""
    now = datetime.now(UTC)
    return ScorpionTrackShare(
        id=101,
        token="canonical-token",
        title="Family Cars",
        owner_name="ScorpionTrack User",
        distance_units="miles",
        created_at=now - timedelta(days=3),
        expires_at=now + timedelta(days=28),
        vehicles=(
            ScorpionTrackVehicle(
                id=2001,
                name="Golf R",
                registration="AB12 CDE",
                make="Volkswagen",
                model="Golf R",
                position=ScorpionTrackPosition(
                    latitude=51.5074,
                    longitude=-0.1278,
                    timestamp=now - timedelta(minutes=5),
                    speed_kmh=48.3,
                    ignition=True,
                    bearing=182.0,
                    address="Westminster, London",
                ),
                status="moving",
            ),
        ),
    )


@pytest.fixture
def mock_account() -> ScorpionTrackAccountData:
    """Return a representative portal-account response."""
    now = datetime.now(UTC)
    position_values: dict[str, Any] = {
        field.name: None for field in fields(ScorpionTrackVehiclePosition)
    }
    position_values.update(
        latitude=51.5074,
        longitude=-0.1278,
        timestamp=now - timedelta(minutes=5),
        speed=30.0,
        speed_kmh=48.3,
        bearing=182.0,
        accuracy=5.0,
        address="Westminster, London",
        ignition=True,
        engine=True,
        raw_state="moving",
        friendly_state="Moving",
        distance_units="miles",
        units_speed="mph",
    )
    position = ScorpionTrackVehiclePosition(**position_values)

    vehicle_values: dict[str, Any] = {
        field.name: None for field in fields(ScorpionTrackVehicleSummary)
    }
    vehicle_values.update(
        id=2001,
        registration="AB12 CDE",
        alias="Golf R",
        make="Volkswagen",
        model="Golf R",
        vehicle_type="Car",
        raw_state="moving",
        status="Moving",
        pending_commands_count=0,
        group_names=("Family",),
        privacy_mode_enabled=False,
        zero_speed_mode_enabled=True,
        position=position,
    )
    vehicle = ScorpionTrackVehicleSummary(**vehicle_values)

    return ScorpionTrackAccountData(
        email="owner@example.com",
        title="ScorpionTrack (Owner)",
        user_id=42,
        distance_units="miles",
        app_api_key_available=True,
        fms_api_available=True,
        vehicles=(vehicle,),
        total_alerts=2,
        unread_alerts=1,
        alerts=(),
        fetched_at=now,
    )


@pytest.fixture(autouse=True)
def mock_clients(
    mock_share: ScorpionTrackShare,
    mock_account: ScorpionTrackAccountData,
) -> Iterator[SimpleNamespace]:
    """Mock both ScorpionTrack clients at their integration boundaries."""
    with (
        patch(
            "custom_components.scorpiontrack.ScorpionTrackShareClient",
            autospec=True,
        ) as share_client_class,
        patch(
            "custom_components.scorpiontrack.config_flow.ScorpionTrackShareClient",
            new=share_client_class,
        ),
        patch(
            "custom_components.scorpiontrack.ScorpionTrackAccountClient",
            autospec=True,
        ) as account_client_class,
        patch(
            "custom_components.scorpiontrack.config_flow.ScorpionTrackAccountClient",
            new=account_client_class,
        ),
    ):
        share_client_class.extract_token.side_effect = ScorpionTrackClient.extract_token
        share_client = share_client_class.return_value
        share_client.token = "canonical-token"
        share_client.async_get_share = AsyncMock(return_value=mock_share)

        account_client = account_client_class.return_value
        account_client.email = "owner@example.com"
        account_client.async_refresh_account = AsyncMock(return_value=mock_account)
        account_client.async_mark_all_alerts_read = AsyncMock(return_value=1)
        account_client.async_set_vehicle_mode = AsyncMock(return_value=None)

        yield SimpleNamespace(
            share=share_client,
            share_class=share_client_class,
            account=account_client,
            account_class=account_client_class,
        )


@pytest.fixture
def share_config_entry() -> MockConfigEntry:
    """Return a shared-location config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Family Cars",
        data={
            CONF_SETUP_TYPE: SETUP_TYPE_SHARE,
            CONF_SHARE_TOKEN: "canonical-token",
        },
        unique_id="share_101",
        entry_id="01SCORPIONTRACK_SHARE_TEST",
    )


@pytest.fixture
def account_config_entry() -> MockConfigEntry:
    """Return a portal-account config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="ScorpionTrack (Owner)",
        data={
            CONF_SETUP_TYPE: SETUP_TYPE_ACCOUNT,
            CONF_EMAIL: "owner@example.com",
            CONF_PASSWORD: "correct-password",
        },
        unique_id="account_42",
        entry_id="01SCORPIONTRACK_ACCOUNT_TEST",
    )


@pytest.fixture
def client_mocks(mock_clients: SimpleNamespace) -> SimpleNamespace:
    """Expose the mocked clients to tests."""
    return mock_clients
