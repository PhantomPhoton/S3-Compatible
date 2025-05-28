"""Constants for the S3 Compatible integration."""

from collections.abc import Callable
from typing import Final
from botocore.config import Config

from homeassistant.util.hass_dict import HassKey

DOMAIN: Final = "s3_compatible"

CONF_ACCESS_KEY_ID = "access_key_id"
CONF_SECRET_ACCESS_KEY = "secret_access_key"
CONF_ENDPOINT_URL = "endpoint_url"
CONF_BUCKET = "bucket"
CONF_PREFIX = "prefix"

AWS_DOMAIN = "amazonaws.com"
DEFAULT_ENDPOINT_URL = f"https://s3.eu-central-1.{AWS_DOMAIN}/"

DATA_BACKUP_AGENT_LISTENERS: HassKey[list[Callable[[], None]]] = HassKey(
    f"{DOMAIN}.backup_agent_listeners"
)

DESCRIPTION_AWS_S3_DOCS_URL = "https://docs.aws.amazon.com/general/latest/gr/s3.html"
DESCRIPTION_BOTO3_DOCS_URL = "https://boto3.amazonaws.com/v1/documentation/api/latest/reference/core/session.html"

BOTO_CONFIG = Config(
    request_checksum_calculation="when_required",
    response_checksum_validation="when_required",
)
