"""Data update coordinators for ScorpionTrack Portal."""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from datetime import datetime
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
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
    MANUFACTURER,
    MOVING_SPEED_THRESHOLD_KMH,
    SHARE_SCAN_INTERVAL,
)
from .utils import stable_hash

_LOGGER = logging.getLogger(__name__)
_NON_ALPHANUMERIC = re.compile(r"[^A-Z0-9]")

type ScorpionTrackConfigEntry = ConfigEntry[
    ScorpionTrackAccountCoordinator | ScorpionTrackShareCoordinator
]


class ScorpionTrackAccountCoordinator(DataUpdateCoordinator[ScorpionTrackAccountData]):
    """Coordinate authenticated ScorpionTrack account updates."""

    config_entry: ScorpionTrackConfigEntry
    account_device_id: str

    def __init__(
        self,
        hass: HomeAssistant,
        client: ScorpionTrackAccountClient,
        entry: ScorpionTrackConfigEntry,
        *,
        share_client: ScorpionTrackShareClient | None = None,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
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
        # Listeners must run on every refresh: scheduled transport, garage and
        # no-alert modes are evaluated against the clock, so their state can
        # change while the portal payload stays the same.
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
    def account_device_info(self) -> DeviceInfo:
        """Return the device that represents the portal account."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"account_{self.account_identifier}")},
            entry_type=DeviceEntryType.SERVICE,
            manufacturer=MANUFACTURER,
            model="Portal Account",
            name=self.data.title,
        )

    @callback
    def async_register_account_device(self) -> None:
        """Create the account device so vehicle devices can link to it."""
        self.account_device_id = (
            dr.async_get(self.hass)
            .async_get_or_create(
                config_entry_id=self.config_entry.entry_id, **self.account_device_info
            )
            .id
        )

    async def async_request_account_refresh(self) -> None:
        """Force the next composite refresh to include portal-account data."""
        self._force_account_refresh = True
        await self.async_request_refresh()

    @override
    async def _async_update_data(self) -> ScorpionTrackAccountData:
        """Fetch updated account data."""
        now = dt_util.utcnow()
        account = self._account_data
        if (
            account is None
            or self._last_account_refresh is None
            or self._force_account_refresh
            or now - self._last_account_refresh >= ACCOUNT_SCAN_INTERVAL
        ):
            account = await self._async_refresh_account()
            self._account_data = account
            self._last_account_refresh = now
            self._force_account_refresh = False

        if self.share_client is not None:
            account = await self._async_merge_share(self.share_client, account)

        self.vehicles_by_id = {vehicle.id: vehicle for vehicle in account.vehicles}
        _async_remove_stale_devices(
            self.hass,
            self.config_entry,
            {
                (DOMAIN, f"account_{self.account_identifier}"),
                *(
                    (DOMAIN, f"{self.account_identifier}_vehicle_{vehicle_id}")
                    for vehicle_id in self.vehicles_by_id
                ),
            },
        )
        return account

    async def _async_refresh_account(self) -> ScorpionTrackAccountData:
        """Fetch portal data and translate client failures."""
        try:
            return await self.client.async_refresh_account()
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

    async def _async_merge_share(
        self,
        share_client: ScorpionTrackShareClient,
        account: ScorpionTrackAccountData,
    ) -> ScorpionTrackAccountData:
        """Overlay fresher shared positions without making the share mandatory."""
        try:
            share = await share_client.async_get_share()
        except (
            ScorpionTrackShareConnectionError,
            ScorpionTrackInvalidTokenError,
            ScorpionTrackShareUnavailableError,
        ) as err:
            if self.share_last_update_success is not False:
                _LOGGER.info(
                    "Optional ScorpionTrack share is unavailable (%s); using "
                    "portal positions until it recovers",
                    type(err).__name__,
                )
            if not isinstance(err, ScorpionTrackShareConnectionError):
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    hybrid_share_issue_id(self.config_entry),
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="hybrid_share_unavailable",
                    translation_placeholders={"title": self.config_entry.title},
                )
            self.share_last_update_success = False
            self.share_last_exception_type = type(err).__name__
            self.matched_share_vehicle_count = 0
            return _preserve_newer_live_positions(account, self.data)

        if self.share_last_update_success is False:
            _LOGGER.info("Optional ScorpionTrack share is available again")
        ir.async_delete_issue(
            self.hass, DOMAIN, hybrid_share_issue_id(self.config_entry)
        )
        self.share = share
        self.share_last_update_success = True
        self.share_last_exception_type = None
        merged_vehicles, match_count = _merge_share_vehicles(
            account.vehicles,
            share.vehicles,
        )
        self.matched_share_vehicle_count = match_count
        return replace(account, vehicles=merged_vehicles)


class ScorpionTrackShareCoordinator(DataUpdateCoordinator[ScorpionTrackShare]):
    """Coordinate shared-location updates."""

    config_entry: ScorpionTrackConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: ScorpionTrackShareClient,
        entry: ScorpionTrackConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.vehicles_by_id: dict[int, ScorpionTrackVehicle] = {}
        # Listeners must run on every refresh: Location stale is evaluated
        # against the clock, so it can change while the share payload stays
        # the same.
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=SHARE_SCAN_INTERVAL,
        )

    @override
    async def _async_update_data(self) -> ScorpionTrackShare:
        """Fetch updated share data."""
        try:
            share = await self.client.async_get_share()
        except ScorpionTrackShareConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
            ) from err
        except ScorpionTrackInvalidTokenError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="invalid_token",
            ) from err
        except ScorpionTrackShareUnavailableError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="share_unavailable",
            ) from err

        self.vehicles_by_id = {vehicle.id: vehicle for vehicle in share.vehicles}
        _async_remove_stale_devices(
            self.hass,
            self.config_entry,
            {
                (DOMAIN, f"share_{share.id}"),
                *(
                    (DOMAIN, f"{share.id}_{vehicle_id}")
                    for vehicle_id in self.vehicles_by_id
                ),
            },
        )
        return share


def hybrid_share_issue_id(entry: ScorpionTrackConfigEntry) -> str:
    """Return the repair issue ID for an entry's unusable hybrid share."""
    return f"hybrid_share_unavailable_{entry.entry_id}"


def share_vehicle_status(vehicle: ScorpionTrackVehicle) -> str:
    """Return a shared vehicle's status using the portal's moving threshold.

    pyscorpiontrack reports any speed above zero as moving, so GPS drift on a
    parked vehicle would otherwise read as movement.
    """
    position = vehicle.position
    if (
        vehicle.status == "moving"
        and position.speed_kmh is not None
        and position.speed_kmh < MOVING_SPEED_THRESHOLD_KMH
    ):
        return "idle" if position.ignition else "parked"
    return vehicle.status


def _async_remove_stale_devices(
    hass: HomeAssistant,
    entry: ScorpionTrackConfigEntry,
    current_identifiers: set[tuple[str, str]],
) -> None:
    """Detach devices for vehicles no longer returned by ScorpionTrack."""
    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        if device.identifiers.isdisjoint(current_identifiers):
            device_registry.async_update_device(
                device.id, remove_config_entry_id=entry.entry_id
            )


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
            previous_vehicle is not None
            and previous_position is not None
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
        matched_vehicle = share_by_id.get(account_vehicle.id)
        if matched_vehicle is None:
            registration = _normalize_registration(account_vehicle.registration)
            if registration is not None:
                matched_vehicle = share_by_registration.get(registration)
        if matched_vehicle is None:
            merged.append(account_vehicle)
            continue

        match_count += 1
        merged.append(_merge_share_position(account_vehicle, matched_vehicle))

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
    status = share_vehicle_status(share_vehicle)
    if share_position.latitude is None or share_position.longitude is None:
        latitude, longitude = base.latitude, base.longitude
        address = base.address
    else:
        latitude, longitude = share_position.latitude, share_position.longitude
        address = share_position.address
    position = replace(
        base,
        latitude=latitude,
        longitude=longitude,
        timestamp=share_position.timestamp,
        speed=share_position.speed_kmh,
        speed_kmh=share_position.speed_kmh,
        bearing=share_position.bearing,
        address=address,
        ignition=share_position.ignition,
        raw_state=share_vehicle.status,
        friendly_state=status,
    )
    return replace(
        account_vehicle,
        position=position,
        raw_state=share_vehicle.status,
        status=status,
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
