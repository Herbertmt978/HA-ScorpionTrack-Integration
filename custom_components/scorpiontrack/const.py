"""Constants for the ScorpionTrack integration."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from homeassistant.const import Platform, UnitOfSpeed

DOMAIN = "scorpiontrack"
DEFAULT_NAME = "ScorpionTrack Integration"
ACCOUNT_DEFAULT_NAME = "ScorpionTrack Account"
SHARE_DEFAULT_NAME = "ScorpionTrack Share"
MANUFACTURER = "ScorpionTrack"

CONF_SETUP_TYPE = "setup_type"
CONF_SHARE_TOKEN = "share_token"
CONF_SPEED_UNIT = "speed_unit"

SETUP_TYPE_ACCOUNT = "account"
SETUP_TYPE_SHARE = "share"

PORTAL_BASE_URL = "https://app.scorpiontrack.com"
LOGIN_PATH = "/home/login"
LOGIN_POST_PATH = "/login/check_for_multiple_accounts"
VEHICLE_LIST_PAGE_PATH = "/customer/vehicle/vehiclelist"
CUSTOMER_MAP_POSITIONS_PATH = "/customer/map/getNewVehiclePositions"
FMS_VEHICLES_PATH = "/vehicles"
FMS_ALERTS_PATH = "/alerts-dashboard/alerts"
FMS_ALERTS_BULK_READ_PATH = "/alerts-dashboard/bulk-read"

ACCOUNT_SCAN_INTERVAL = timedelta(minutes=5)
SHARE_SCAN_INTERVAL = timedelta(minutes=2)
STALE_POSITION_THRESHOLD = timedelta(hours=24)

SPEED_UNITS: tuple[str, ...] = (
    UnitOfSpeed.MILES_PER_HOUR,
    UnitOfSpeed.KILOMETERS_PER_HOUR,
)

PLATFORMS: tuple[Platform, ...] = (
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.SWITCH,
    Platform.BUTTON,
)


def get_setup_type(data: Mapping[str, Any]) -> str | None:
    """Return the configured source type, including legacy/Core entries."""
    setup_type = data.get(CONF_SETUP_TYPE)
    if setup_type in (SETUP_TYPE_ACCOUNT, SETUP_TYPE_SHARE):
        return setup_type

    if CONF_SHARE_TOKEN in data:
        return SETUP_TYPE_SHARE

    return None


def get_share_token(data: Mapping[str, Any], options: Mapping[str, Any]) -> str | None:
    """Return an optional share token, allowing options to remove a prior value."""
    value = (
        options[CONF_SHARE_TOKEN]
        if CONF_SHARE_TOKEN in options
        else data.get(CONF_SHARE_TOKEN)
    )
    if not isinstance(value, str):
        return None
    return value.strip() or None


def get_speed_unit(
    data: Mapping[str, Any],
    options: Mapping[str, Any],
    *,
    uses_miles: bool,
) -> str:
    """Return the configured speed unit or the source's existing preference."""
    value = options.get(CONF_SPEED_UNIT, data.get(CONF_SPEED_UNIT))
    if value in SPEED_UNITS:
        return str(value)
    return UnitOfSpeed.MILES_PER_HOUR if uses_miles else UnitOfSpeed.KILOMETERS_PER_HOUR


def convert_speed(
    speed_kmh: float | None, unit: str, *, precision: int = 1
) -> float | None:
    """Convert a normalized km/h speed into the configured display unit."""
    if speed_kmh is None:
        return None
    if unit == UnitOfSpeed.MILES_PER_HOUR:
        return round(speed_kmh * 0.621371, precision)
    return round(speed_kmh, precision)
