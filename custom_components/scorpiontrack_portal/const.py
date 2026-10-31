"""Constants for the ScorpionTrack Portal integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "scorpiontrack_portal"
ACCOUNT_DEFAULT_NAME = "ScorpionTrack Account"
SHARE_DEFAULT_NAME = "ScorpionTrack Share"
MANUFACTURER = "ScorpionTrack"

CONF_SETUP_TYPE = "setup_type"
CONF_SHARE_TOKEN = "share_token"
# Removed in config entry version 1.3; kept so the migration can drop it.
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

# The portal reports a vehicle as moving only from this speed, which keeps GPS
# drift on a parked vehicle from reading as movement.
MOVING_SPEED_THRESHOLD_KMH = 3.0

PLATFORMS: tuple[Platform, ...] = (
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.SWITCH,
    Platform.BUTTON,
)
