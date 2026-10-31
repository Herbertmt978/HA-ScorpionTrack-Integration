"""Config flow for ScorpionTrack."""

from __future__ import annotations

import logging
from typing import Any, override

import voluptuous as vol
from aiohttp import CookieJar
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
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
    get_setup_type,
    get_share_token,
)
from .utils import stable_hash

_LOGGER = logging.getLogger(__name__)


def _speed_unit_selector() -> SelectSelector:
    """Return the shared speed-unit selector."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[str(unit) for unit in SPEED_UNITS],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _default_speed_unit(hass: HomeAssistant) -> str:
    """Return a sensible initial speed unit from Home Assistant's unit system."""
    return (
        UnitOfSpeed.KILOMETERS_PER_HOUR
        if hass.config.units.wind_speed_unit != UnitOfSpeed.MILES_PER_HOUR
        else UnitOfSpeed.MILES_PER_HOUR
    )


async def _async_validate_account_input(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> dict[str, str]:
    """Validate the provided account credentials."""
    session = async_create_clientsession(
        hass,
        cookie_jar=CookieJar(quote_cookie=False),
    )
    client = ScorpionTrackAccountClient(
        session=session,
        email=user_input[CONF_EMAIL],
        password=user_input[CONF_PASSWORD],
    )
    account = await client.async_refresh_account()

    unique_id = (
        str(account.user_id)
        if account.user_id is not None
        else stable_hash(account.email)
    )
    return {
        "email": account.email,
        "title": account.title,
        "unique_id": f"{SETUP_TYPE_ACCOUNT}_{unique_id}",
    }


async def _async_validate_share_input(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> ScorpionTrackShare:
    """Validate the provided share token or URL."""
    try:
        normalized_token = ScorpionTrackShareClient.extract_token(
            user_input[CONF_SHARE_TOKEN]
        )
    except (ScorpionTrackInvalidTokenError, ValueError) as err:
        raise ScorpionTrackInvalidTokenError(
            "Invalid ScorpionTrack share token"
        ) from err

    client = ScorpionTrackShareClient(
        session=async_get_clientsession(hass),
        token=normalized_token,
    )
    return await client.async_get_share()


def _share_title(share: ScorpionTrackShare) -> str:
    """Return the best config entry title for a share."""
    if share.title:
        return share.title
    if share.vehicles:
        return share.vehicles[0].display_name
    return SHARE_DEFAULT_NAME


class ScorpionTrackConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ScorpionTrack."""

    VERSION = 1

    @staticmethod
    @callback
    @override
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> ScorpionTrackOptionsFlow:
        """Return the ScorpionTrack options flow."""
        return ScorpionTrackOptionsFlow(config_entry)

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user choose how to connect."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["account", "share"],
        )

    @override
    async def async_step_account(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the portal account flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _async_validate_account_input(self.hass, user_input)
            except ScorpionTrackAccountConnectionError:
                errors["base"] = "cannot_connect"
            except ScorpionTrackAuthError:
                errors["base"] = "invalid_auth"
            except ScorpionTrackPortalError:
                errors["base"] = "unexpected_response"
            except Exception:
                _LOGGER.exception(
                    "Unexpected exception while validating ScorpionTrack account"
                )
                errors["base"] = "unknown"
            else:
                share_token = user_input.get(CONF_SHARE_TOKEN, "").strip()
                if share_token:
                    try:
                        share = await _async_validate_share_input(self.hass, user_input)
                    except ScorpionTrackShareConnectionError:
                        errors["base"] = "cannot_connect"
                    except ScorpionTrackInvalidTokenError:
                        errors["base"] = "invalid_token"
                    except ScorpionTrackShareUnavailableError:
                        errors["base"] = "share_unavailable"
                    except Exception:
                        _LOGGER.exception(
                            "Unexpected exception while validating optional "
                            "ScorpionTrack share"
                        )
                        errors["base"] = "unknown"
                    else:
                        share_token = share.token

            if user_input is not None and not errors:
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_configured()
                options = {CONF_SPEED_UNIT: user_input[CONF_SPEED_UNIT]}
                if share_token:
                    options[CONF_SHARE_TOKEN] = share_token
                return self.async_create_entry(
                    title=info["title"],
                    data={
                        CONF_SETUP_TYPE: SETUP_TYPE_ACCOUNT,
                        CONF_EMAIL: info["email"],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                    options=options,
                )

        return self.async_show_form(
            step_id="account",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_SHARE_TOKEN, default=""): str,
                    vol.Required(
                        CONF_SPEED_UNIT,
                        default=_default_speed_unit(self.hass),
                    ): _speed_unit_selector(),
                }
            ),
            errors=errors,
        )

    @override
    async def async_step_share(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the shared-location flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                share = await _async_validate_share_input(self.hass, user_input)
            except ScorpionTrackShareConnectionError:
                errors["base"] = "cannot_connect"
            except ScorpionTrackInvalidTokenError:
                errors["base"] = "invalid_token"
            except ScorpionTrackShareUnavailableError:
                errors["base"] = "share_unavailable"
            except Exception:
                _LOGGER.exception(
                    "Unexpected exception while validating ScorpionTrack share"
                )
                errors["base"] = "unknown"
            else:
                unique_id = f"{SETUP_TYPE_SHARE}_{share.id}"
                core_unique_id = str(share.id)
                if any(
                    entry.unique_id in (unique_id, core_unique_id)
                    for entry in self._async_current_entries()
                ):
                    return self.async_abort(reason="already_configured")

                await self.async_set_unique_id(unique_id)
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
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SHARE_TOKEN): str,
                    vol.Required(
                        CONF_SPEED_UNIT,
                        default=_default_speed_unit(self.hass),
                    ): _speed_unit_selector(),
                }
            ),
            errors=errors,
        )

    @override
    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start account credential reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate and store replacement account credentials."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            credentials = {
                CONF_EMAIL: entry.data[CONF_EMAIL],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            try:
                info = await _async_validate_account_input(self.hass, credentials)
            except ScorpionTrackAccountConnectionError:
                errors["base"] = "cannot_connect"
            except ScorpionTrackAuthError:
                errors["base"] = "invalid_auth"
            except ScorpionTrackPortalError:
                errors["base"] = "unexpected_response"
            except Exception:
                _LOGGER.exception(
                    "Unexpected exception while reauthenticating ScorpionTrack account"
                )
                errors["base"] = "unknown"
            else:
                fallback_unique_id = (
                    f"{SETUP_TYPE_ACCOUNT}_{stable_hash(info['email'])}"
                )
                if entry.unique_id not in (
                    None,
                    info["unique_id"],
                    fallback_unique_id,
                ):
                    errors["base"] = "reauth_account_mismatch"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        unique_id=entry.unique_id or info["unique_id"],
                        title=info["title"],
                        data_updates={
                            CONF_SETUP_TYPE: SETUP_TYPE_ACCOUNT,
                            CONF_EMAIL: info["email"],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                        },
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )


class ScorpionTrackOptionsFlow(OptionsFlow):
    """Manage speed units and the optional account share feed."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry

    @override
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and validate ScorpionTrack options."""
        errors: dict[str, str] = {}
        entry_type = get_setup_type(self._config_entry.data)

        if user_input is not None:
            options = {CONF_SPEED_UNIT: user_input[CONF_SPEED_UNIT]}
            if entry_type == SETUP_TYPE_ACCOUNT:
                share_token = user_input.get(CONF_SHARE_TOKEN, "").strip()
                if share_token:
                    try:
                        share = await _async_validate_share_input(self.hass, user_input)
                    except ScorpionTrackShareConnectionError:
                        errors["base"] = "cannot_connect"
                    except ScorpionTrackInvalidTokenError:
                        errors["base"] = "invalid_token"
                    except ScorpionTrackShareUnavailableError:
                        errors["base"] = "share_unavailable"
                    except Exception:
                        _LOGGER.exception(
                            "Unexpected exception while validating optional "
                            "ScorpionTrack share"
                        )
                        errors["base"] = "unknown"
                    else:
                        options[CONF_SHARE_TOKEN] = share.token
                else:
                    options[CONF_SHARE_TOKEN] = ""

            if not errors:
                return self.async_create_entry(title="", data=options)

        current_speed_unit = self._config_entry.options.get(
            CONF_SPEED_UNIT, _default_speed_unit(self.hass)
        )
        schema: dict[vol.Marker, object] = {
            vol.Required(
                CONF_SPEED_UNIT,
                default=current_speed_unit,
            ): _speed_unit_selector()
        }
        if entry_type == SETUP_TYPE_ACCOUNT:
            schema[
                vol.Optional(
                    CONF_SHARE_TOKEN,
                    default=get_share_token(
                        self._config_entry.data,
                        self._config_entry.options,
                    )
                    or "",
                )
            ] = str

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            errors=errors,
        )
