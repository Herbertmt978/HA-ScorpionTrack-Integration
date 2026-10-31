"""Config flow for ScorpionTrack Portal."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, override

import voluptuous as vol
from aiohttp import CookieJar
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, UnitOfSpeed
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import (
    async_create_clientsession,
    async_get_clientsession,
)
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
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
)

from .account_api import (
    ScorpionTrackAccountClient,
    ScorpionTrackAuthError,
    ScorpionTrackPortalError,
)
from .account_api import (
    ScorpionTrackConnectionError as ScorpionTrackAccountConnectionError,
)
from .const import (
    CONF_SETUP_TYPE,
    CONF_SHARE_TOKEN,
    CONF_SPEED_UNIT,
    DOMAIN,
    SETUP_TYPE_ACCOUNT,
    SETUP_TYPE_SHARE,
    SHARE_DEFAULT_NAME,
    SPEED_UNITS,
)
from .utils import stable_hash

_LOGGER = logging.getLogger(__name__)

_EMAIL_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
)
_PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)
_SPEED_UNIT_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[str(unit) for unit in SPEED_UNITS],
        mode=SelectSelectorMode.DROPDOWN,
    )
)


class _ValidationError(Exception):
    """Raised when user input cannot be validated."""

    def __init__(self, error: str) -> None:
        """Store the config flow error key."""
        super().__init__(error)
        self.error = error


@dataclass(frozen=True, slots=True)
class _AccountInfo:
    """Details of a validated portal account."""

    email: str
    title: str
    unique_id: str


def _account_fallback_unique_id(email: str) -> str:
    """Return the unique ID used when the portal does not report a user ID."""
    return f"{SETUP_TYPE_ACCOUNT}_{stable_hash(email)}"


def _default_speed_unit(hass: HomeAssistant) -> str:
    """Return an initial speed unit from Home Assistant's unit system."""
    if hass.config.units.wind_speed_unit == UnitOfSpeed.MILES_PER_HOUR:
        return UnitOfSpeed.MILES_PER_HOUR
    return UnitOfSpeed.KILOMETERS_PER_HOUR


async def _async_validate_account(
    hass: HomeAssistant, email: str, password: str
) -> _AccountInfo:
    """Log in to the portal and return the account details."""
    client = ScorpionTrackAccountClient(
        session=async_create_clientsession(
            hass, cookie_jar=CookieJar(quote_cookie=False)
        ),
        email=email,
        password=password,
    )
    try:
        account = await client.async_refresh_account()
    except ScorpionTrackAccountConnectionError as err:
        raise _ValidationError("cannot_connect") from err
    except ScorpionTrackAuthError as err:
        raise _ValidationError("invalid_auth") from err
    except ScorpionTrackPortalError as err:
        raise _ValidationError("unexpected_response") from err
    except Exception as err:
        _LOGGER.exception(
            "Unexpected exception while validating a ScorpionTrack account"
        )
        raise _ValidationError("unknown") from err

    return _AccountInfo(
        email=account.email,
        title=account.title,
        unique_id=(
            f"{SETUP_TYPE_ACCOUNT}_{account.user_id}"
            if account.user_id is not None
            else _account_fallback_unique_id(account.email)
        ),
    )


async def _async_validate_share(
    hass: HomeAssistant, share_input: str
) -> ScorpionTrackShare:
    """Validate a shared-location URL or token and return the share."""
    try:
        token = ScorpionTrackShareClient.extract_token(share_input)
    except (ScorpionTrackInvalidTokenError, ValueError) as err:
        raise _ValidationError("invalid_token") from err

    client = ScorpionTrackShareClient(
        session=async_get_clientsession(hass), token=token
    )
    try:
        return await client.async_get_share()
    except ScorpionTrackShareConnectionError as err:
        raise _ValidationError("cannot_connect") from err
    except ScorpionTrackInvalidTokenError as err:
        raise _ValidationError("invalid_token") from err
    except ScorpionTrackShareUnavailableError as err:
        raise _ValidationError("share_unavailable") from err
    except Exception as err:
        _LOGGER.exception("Unexpected exception while validating a ScorpionTrack share")
        raise _ValidationError("unknown") from err


def _share_title(share: ScorpionTrackShare) -> str:
    """Return the best config entry title for a share."""
    if share.title:
        return share.title
    if share.vehicles:
        return share.vehicles[0].display_name
    return SHARE_DEFAULT_NAME


class ScorpionTrackConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ScorpionTrack Portal."""

    VERSION = 1
    MINOR_VERSION = 2

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> ScorpionTrackOptionsFlow:
        """Return the options flow."""
        return ScorpionTrackOptionsFlow()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user choose how to connect."""
        return self.async_show_menu(step_id="user", menu_options=["account", "share"])

    async def async_step_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up a portal account, optionally with a hybrid share."""
        errors: dict[str, str] = {}
        if user_input is not None:
            share_input = user_input.get(CONF_SHARE_TOKEN, "").strip()
            try:
                account = await _async_validate_account(
                    self.hass, user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
                share = (
                    await _async_validate_share(self.hass, share_input)
                    if share_input
                    else None
                )
            except _ValidationError as err:
                errors["base"] = err.error
            else:
                await self.async_set_unique_id(account.unique_id)
                self._abort_if_unique_id_configured()
                data = {
                    CONF_SETUP_TYPE: SETUP_TYPE_ACCOUNT,
                    CONF_EMAIL: account.email,
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                }
                if share is not None:
                    data[CONF_SHARE_TOKEN] = share.token
                return self.async_create_entry(
                    title=account.title,
                    data=data,
                    options={CONF_SPEED_UNIT: user_input[CONF_SPEED_UNIT]},
                )

        return self.async_show_form(
            step_id="account",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_EMAIL): _EMAIL_SELECTOR,
                        vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
                        vol.Optional(CONF_SHARE_TOKEN): str,
                        vol.Required(
                            CONF_SPEED_UNIT, default=_default_speed_unit(self.hass)
                        ): _SPEED_UNIT_SELECTOR,
                    }
                ),
                user_input or {},
            ),
            errors=errors,
        )

    async def async_step_share(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up a shared-location link."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                share = await _async_validate_share(
                    self.hass, user_input[CONF_SHARE_TOKEN]
                )
            except _ValidationError as err:
                errors["base"] = err.error
            else:
                await self.async_set_unique_id(f"{SETUP_TYPE_SHARE}_{share.id}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_share_title(share),
                    data={
                        CONF_SETUP_TYPE: SETUP_TYPE_SHARE,
                        CONF_SHARE_TOKEN: share.token,
                    },
                    options={CONF_SPEED_UNIT: user_input[CONF_SPEED_UNIT]},
                )

        return self.async_show_form(
            step_id="share",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_SHARE_TOKEN): str,
                        vol.Required(
                            CONF_SPEED_UNIT, default=_default_speed_unit(self.hass)
                        ): _SPEED_UNIT_SELECTOR,
                    }
                ),
                user_input or {},
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start portal-account reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate and store a replacement portal password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                account = await _async_validate_account(
                    self.hass, entry.data[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
            except _ValidationError as err:
                errors["base"] = err.error
            else:
                if entry.unique_id not in (
                    account.unique_id,
                    _account_fallback_unique_id(account.email),
                ):
                    return self.async_abort(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR}),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update the share link used by an entry."""
        if self._get_reconfigure_entry().data[CONF_SETUP_TYPE] == SETUP_TYPE_ACCOUNT:
            return await self.async_step_reconfigure_account()
        return await self.async_step_reconfigure_share()

    async def async_step_reconfigure_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add, replace or remove a portal account's hybrid share."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            share_input = user_input.get(CONF_SHARE_TOKEN, "").strip()
            try:
                share = (
                    await _async_validate_share(self.hass, share_input)
                    if share_input
                    else None
                )
            except _ValidationError as err:
                errors["base"] = err.error
            else:
                data = {
                    key: value
                    for key, value in entry.data.items()
                    if key != CONF_SHARE_TOKEN
                }
                if share is not None:
                    data[CONF_SHARE_TOKEN] = share.token
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reconfigure_account",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Optional(CONF_SHARE_TOKEN): str}),
                user_input or {CONF_SHARE_TOKEN: entry.data.get(CONF_SHARE_TOKEN)},
            ),
            errors=errors,
        )

    async def async_step_reconfigure_share(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Replace the link for the same shared location."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                share = await _async_validate_share(
                    self.hass, user_input[CONF_SHARE_TOKEN]
                )
            except _ValidationError as err:
                errors["base"] = err.error
            else:
                await self.async_set_unique_id(f"{SETUP_TYPE_SHARE}_{share.id}")
                self._abort_if_unique_id_mismatch(reason="wrong_share")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_SHARE_TOKEN: share.token}
                )

        return self.async_show_form(
            step_id="reconfigure_share",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_SHARE_TOKEN): str}),
                user_input or {CONF_SHARE_TOKEN: entry.data[CONF_SHARE_TOKEN]},
            ),
            errors=errors,
        )


class ScorpionTrackOptionsFlow(OptionsFlowWithReload):
    """Choose how ScorpionTrack speeds are displayed."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the speed unit."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_SPEED_UNIT): _SPEED_UNIT_SELECTOR}),
                {
                    CONF_SPEED_UNIT: _default_speed_unit(self.hass),
                    **self.config_entry.options,
                },
            ),
        )
