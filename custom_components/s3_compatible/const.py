"""Constants for the S3 Compatible integration."""

from collections.abc import Callable
from typing import Final
from homeassistant.util.hass_dict import HassKey

DOMAIN: Final = "s3_compatible"

CONF_ACCESS_KEY_ID = "access_key_id"
CONF_SECRET_ACCESS_KEY = "secret_access_key"
CONF_ENDPOINT_URL = "endpoint_url"
CONF_BUCKET = "bucket"
CONF_PREFIX = "prefix"
CONF_REGION = "region"
CONF_VERIFY = "verify"

# Upload performance settings (stored in a nested "upload_performance" dict).
CONF_UPLOAD_PERFORMANCE = "upload_performance"
CONF_PART_SIZE_MIB = "part_size_mib"
CONF_MAX_CONCURRENCY = "max_concurrency"

# Defaults match the original behaviour: 20 MiB parts, one at a time.
# Peak memory during an upload is roughly (max_concurrency + 1) * part_size.
DEFAULT_PART_SIZE_MIB = 20
DEFAULT_MAX_CONCURRENCY = 1
MIN_PART_SIZE_MIB = 5  # S3 minimum part size
MAX_PART_SIZE_MIB = 256
MIN_CONCURRENCY = 1
MAX_CONCURRENCY = 8

AWS_DOMAIN = "amazonaws.com"
DEFAULT_REGION = "us-east-1"
DEFAULT_ENDPOINT_URL = f"https://s3.{DEFAULT_REGION}.{AWS_DOMAIN}/"

DATA_BACKUP_AGENT_LISTENERS: HassKey[list[Callable[[], None]]] = HassKey(
    f"{DOMAIN}.backup_agent_listeners"
)
