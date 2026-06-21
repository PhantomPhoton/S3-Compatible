"""Config flow for the S3 Compatible integration."""

from __future__ import annotations

import re
from typing import Any

from .s3rest import create_client
from .exceptions import ClientError, ConnectionError, ParamValidationError
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_ACCESS_KEY_ID,
    CONF_BUCKET,
    CONF_ENDPOINT_URL,
    CONF_SECRET_ACCESS_KEY,
    CONF_PREFIX,
    CONF_REGION,
    CONF_VERIFY,
    DEFAULT_ENDPOINT_URL,
    DEFAULT_REGION,
    DOMAIN,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_KEY_ID): cv.string,
        vol.Required(CONF_SECRET_ACCESS_KEY): TextSelector(
            config=TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_BUCKET): cv.string,
        vol.Required(CONF_REGION, default=DEFAULT_REGION): cv.string,
        vol.Optional(CONF_PREFIX, default=""): cv.string,
        vol.Optional(CONF_VERIFY, default=""): cv.string,
        vol.Required(CONF_ENDPOINT_URL, default=DEFAULT_ENDPOINT_URL): TextSelector(
            config=TextSelectorConfig(type=TextSelectorType.URL)
        ),
    }
)


class S3ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        return await self._async_step_setup("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow reconfiguration of an existing config entry."""
        return await self._async_step_setup("reconfigure", user_input)

    async def _async_step_setup(
        self,
        step_id: str,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle user setup and reconfiguration."""
        reconfigure = step_id == "reconfigure"
        entry = self._get_reconfigure_entry() if reconfigure else None
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            if self._is_duplicate(
                user_input,
                exclude_entry_id=entry.entry_id if entry else None,
            ):
                return self.async_abort(reason="already_configured")

            errors, description_placeholders = await self._async_validate_connection(
                user_input
            )

            if not errors:
                if reconfigure:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates=user_input,
                        title=user_input[CONF_BUCKET],
                    )
                return self.async_create_entry(
                    title=user_input[CONF_BUCKET], data=user_input
                )

        defaults = dict(entry.data) if entry else user_input
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, defaults
            ),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    def _is_duplicate(
        self,
        user_input: dict[str, Any],
        *,
        exclude_entry_id: str | None = None,
    ) -> bool:
        """Return True if another entry uses the same bucket and endpoint."""
        for existing in self._async_current_entries(include_ignore=False):
            if exclude_entry_id and existing.entry_id == exclude_entry_id:
                continue
            if (
                existing.data.get(CONF_BUCKET) == user_input[CONF_BUCKET]
                and existing.data.get(CONF_ENDPOINT_URL)
                == user_input[CONF_ENDPOINT_URL]
            ):
                return True
        return False

    async def _async_validate_connection(
        self,
        user_input: dict[str, Any],
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Validate credentials and bucket access."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}
        try:
            async with create_client(
                "s3",
                endpoint_url=user_input.get(CONF_ENDPOINT_URL),
                region_name=user_input.get(CONF_REGION),
                aws_secret_access_key=user_input[CONF_SECRET_ACCESS_KEY],
                aws_access_key_id=user_input[CONF_ACCESS_KEY_ID],
                verify=user_input.get(CONF_VERIFY, None)
                if user_input.get(CONF_VERIFY, None) != ""
                else None,
            ) as client:
                await client.head_bucket(Bucket=user_input[CONF_BUCKET])
        except ClientError:
            errors["base"] = "invalid_credentials"
        except ParamValidationError as err:
            if "Invalid bucket name" in str(err):
                errors[CONF_BUCKET] = "invalid_bucket_name"
            elif "region" in str(err).lower():
                errors["base"] = "wrong_region"
                match = re.search(r"region '([^']+)'", str(err))
                if match:
                    description_placeholders["region"] = match.group(1)
        except ValueError:
            errors[CONF_ENDPOINT_URL] = "invalid_endpoint_url"
        except ConnectionError:
            errors[CONF_ENDPOINT_URL] = "cannot_connect"

        return errors, description_placeholders
