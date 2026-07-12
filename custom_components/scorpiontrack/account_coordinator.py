"""Coordinator for ScorpionTrack Account."""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from datetime import datetime
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from pyscorpiontrack import (
    ScorpionTrackClient as ScorpionTrackShareClient,
)
from pyscorpiontrack import (
    ScorpionTrackConnectionError as ScorpionTrackShareConnectionError,
)
from pyscorpiontrack import (
    ScorpionTrackInvalidTokenError,
    ScorpionTrackShare,
    ScorpionTrackShareUnavailableError,
    ScorpionTrackVehicle,
)

from .account_api import (
    ScorpionTrackAccountClient,
    ScorpionTrackAccountData,
    ScorpionTrackAuthError,
    ScorpionTrackConnectionError,
    ScorpionTrackPortalError,
    ScorpionTrackVehiclePosition,
    ScorpionTrackVehicleSummary,
)
from .const import (
    ACCOUNT_SCAN_INTERVAL,
    DOMAIN,
    SHARE_SCAN_INTERVAL,
    get_speed_unit,
)
from .utils import stable_hash

_LOGGER = logging.getLogger(__name__)
_NON_ALPHANUMERIC = re.compile(r"[^A-Z0-9]")


type ScorpionTrackAccountConfigEntry = ConfigEntry[ScorpionTrackAccountCoordinator]


class ScorpionTrackAccountCoordinator(DataUpdateCoordinator[ScorpionTrackAccountData]):
    """Coordinate authenticated ScorpionTrack account updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ScorpionTrackAccountClient,
        entry: ScorpionTrackAccountConfigEntry,
        *,
        share_client: ScorpionTrackShareClient | None = None,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.entry = entry
        self.share_client = share_client
        self.share: ScorpionTrackShare | None = None
        self.share_last_update_success: bool | None = None
        self.share_last_exception_type: str | None = None
        self.matched_share_vehicle_count = 0
        self._account_data: ScorpionTrackAccountData | None = None
        self._last_account_refresh: datetime | None = None
        self._force_account_refresh = False
        email_hash = stable_hash(entry.data[CONF_EMAIL])
        unique_id_suffix = (entry.unique_id or "").removeprefix("account_")
        self.account_identifier = (
            f"acct_{email_hash}"
            if unique_id_suffix in ("", email_hash)
            else unique_id_suffix
        )
        self.vehicles_by_id: dict[int, ScorpionTrackVehicleSummary] = {}
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=(
                SHARE_SCAN_INTERVAL
                if share_client is not None
                else ACCOUNT_SCAN_INTERVAL
            ),
        )

    @property
    def speed_unit(self) -> str:
        """Return the configured unit for speed entities."""
        account = self.data or self._account_data
        return get_speed_unit(
            self.entry.data,
            self.entry.options,
            uses_miles=account.uses_miles if account is not None else False,
        )

    async def async_request_account_refresh(self) -> None:
        """Force the next composite refresh to include portal-account data."""
        self._force_account_refresh = True
        await self.async_request_refresh()

    @override
    async def _async_update_data(self) -> ScorpionTrackAccountData:
        """Fetch updated account data."""
        now = dt_util.utcnow()
        account_refresh_due = (
            self._account_data is None
            or self._last_account_refresh is None
            or self._force_account_refresh
            or now - self._last_account_refresh >= ACCOUNT_SCAN_INTERVAL
        )

        if account_refresh_due:
            account = await self._async_refresh_account()
            self._account_data = account
            self._last_account_refresh = now
            self._force_account_refresh = False
        else:
            account = self._account_data
            assert account is not None

        if self.share_client is not None:
            account = await self._async_merge_share(account)

        self.vehicles_by_id = {vehicle.id: vehicle for vehicle in account.vehicles}
        return account

    async def _async_refresh_account(self) -> ScorpionTrackAccountData:
        """Fetch portal data while preserving existing error semantics."""
        try:
            account = await self.client.async_refresh_account()
        except ScorpionTrackConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
            ) from err
        except ScorpionTrackAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="invalid_auth",
            ) from err
        except ScorpionTrackPortalError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="unexpected_response",
            ) from err
        return account

    async def _async_merge_share(
        self, account: ScorpionTrackAccountData
    ) -> ScorpionTrackAccountData:
        """Overlay fresher shared positions without making the share mandatory."""
        assert self.share_client is not None
        try:
            share = await self.share_client.async_get_share()
        except (
            ScorpionTrackShareConnectionError,
            ScorpionTrackInvalidTokenError,
            ScorpionTrackShareUnavailableError,
        ) as err:
            if self.share_last_update_success is not False:
                _LOGGER.warning(
                    "Optional ScorpionTrack share refresh failed (%s); using "
                    "the latest available positions",
                    type(err).__name__,
                )
            self.share_last_update_success = False
            self.share_last_exception_type = type(err).__name__
            self.matched_share_vehicle_count = 0
            return _preserve_newer_live_positions(account, self.data)

        self.share = share
        self.share_last_update_success = True
        self.share_last_exception_type = None
        merged_vehicles, match_count = _merge_share_vehicles(
            account.vehicles,
            share.vehicles,
        )
        self.matched_share_vehicle_count = match_count
        return replace(account, vehicles=merged_vehicles)


def _preserve_newer_live_positions(
    account: ScorpionTrackAccountData,
    previous: ScorpionTrackAccountData | None,
) -> ScorpionTrackAccountData:
    """Keep newer live positions when the optional share is unavailable."""
    if previous is None:
        return account

    previous_by_id = {vehicle.id: vehicle for vehicle in previous.vehicles}
    vehicles: list[ScorpionTrackVehicleSummary] = []
    for vehicle in account.vehicles:
        previous_vehicle = previous_by_id.get(vehicle.id)
        previous_position = (
            previous_vehicle.position if previous_vehicle is not None else None
        )
        current_position = vehicle.position
        if (
            previous_position is not None
            and previous_position.timestamp is not None
            and (
                current_position is None
                or current_position.timestamp is None
                or previous_position.timestamp > current_position.timestamp
            )
        ):
            vehicle = replace(
                vehicle,
                position=previous_position,
                raw_state=previous_vehicle.raw_state,
                status=previous_vehicle.status,
            )
        vehicles.append(vehicle)

    return replace(account, vehicles=tuple(vehicles))


def _merge_share_vehicles(
    account_vehicles: tuple[ScorpionTrackVehicleSummary, ...],
    share_vehicles: tuple[ScorpionTrackVehicle, ...],
) -> tuple[tuple[ScorpionTrackVehicleSummary, ...], int]:
    """Return account vehicles with fresher share positions overlaid."""
    share_by_id = {vehicle.id: vehicle for vehicle in share_vehicles}
    share_by_registration: dict[str, ScorpionTrackVehicle] = {}
    duplicate_registrations: set[str] = set()
    for share_vehicle in share_vehicles:
        registration = _normalize_registration(share_vehicle.registration)
        if registration is None:
            continue
        if registration in share_by_registration:
            duplicate_registrations.add(registration)
        else:
            share_by_registration[registration] = share_vehicle
    for registration in duplicate_registrations:
        share_by_registration.pop(registration, None)

    merged: list[ScorpionTrackVehicleSummary] = []
    match_count = 0
    for account_vehicle in account_vehicles:
        share_vehicle = share_by_id.get(account_vehicle.id)
        if share_vehicle is None:
            registration = _normalize_registration(account_vehicle.registration)
            if registration is not None:
                share_vehicle = share_by_registration.get(registration)
        if share_vehicle is None:
            merged.append(account_vehicle)
            continue

        match_count += 1
        merged.append(_merge_share_position(account_vehicle, share_vehicle))

    return tuple(merged), match_count


def _normalize_registration(value: str | None) -> str | None:
    """Normalize a registration for safe cross-source matching."""
    if value is None:
        return None
    normalized = _NON_ALPHANUMERIC.sub("", value.upper())
    return normalized or None


def _merge_share_position(
    account_vehicle: ScorpionTrackVehicleSummary,
    share_vehicle: ScorpionTrackVehicle,
) -> ScorpionTrackVehicleSummary:
    """Overlay a share position only when it is at least as recent."""
    share_position = share_vehicle.position
    account_position = account_vehicle.position
    if share_position.timestamp is None:
        return account_vehicle
    if (
        account_position is not None
        and account_position.timestamp is not None
        and share_position.timestamp < account_position.timestamp
    ):
        return account_vehicle

    base = account_position or _empty_account_position()
    friendly_state = share_vehicle.status.replace("_", " ").title()
    if share_position.latitude is None or share_position.longitude is None:
        latitude, longitude = base.latitude, base.longitude
    else:
        latitude, longitude = share_position.latitude, share_position.longitude
    position = replace(
        base,
        latitude=latitude,
        longitude=longitude,
        timestamp=share_position.timestamp,
        speed=share_position.speed_kmh,
        speed_kmh=share_position.speed_kmh,
        bearing=share_position.bearing,
        address=share_position.address,
        ignition=share_position.ignition,
        raw_state=share_vehicle.status,
        friendly_state=friendly_state,
    )
    return replace(
        account_vehicle,
        position=position,
        raw_state=share_vehicle.status,
        status=friendly_state,
    )


def _empty_account_position() -> ScorpionTrackVehiclePosition:
    """Return an empty account position ready for a share overlay."""
    return ScorpionTrackVehiclePosition(
        latitude=None,
        longitude=None,
        timestamp=None,
        speed=None,
        speed_kmh=None,
        bearing=None,
        accuracy=None,
        address=None,
        ignition=None,
        engine=None,
        gps_satellites=None,
        hdop=None,
        raw_state=None,
        friendly_state=None,
        vehicle_voltage=None,
        odometer=None,
        unit_type=None,
        unit_id=None,
        distance_units=None,
        units_speed=None,
    )
