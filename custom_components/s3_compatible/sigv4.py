"""AWS Signature Version 4 signing for S3 REST requests."""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import datetime, timezone
from typing import Mapping
from urllib.parse import quote, urlsplit, urlunsplit


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(
    secret_key: str, date_stamp: str, region: str, service: str
) -> bytes:
    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


def _remove_dot_segments(path: str) -> str:
    if not path:
        return "/"
    segments = path.split("/")
    output: list[str] = []
    for segment in segments:
        if segment in ("", "."):
            continue
        if segment == "..":
            if output:
                output.pop()
            continue
        output.append(segment)
    return "/" + "/".join(output) if output else "/"


def _normalize_url_path(path: str) -> str:
    if not path:
        return "/"
    return _remove_dot_segments(path)


def _host_from_url(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if re.match(r"^[0-9a-fA-F:]+$", host) and ":" in host:
        host = f"[{host}]"
    default_ports = {"http": 80, "https": 443}
    if parts.port is not None and parts.port != default_ports.get(parts.scheme):
        host = f"{host}:{parts.port}"
    return host


def _canonical_query_string(params: Mapping[str, str] | None) -> str:
    if not params:
        return ""
    key_val_pairs = [
        (quote(key, safe="-_.~"), quote(str(value), safe="-_.~"))
        for key, value in params.items()
    ]
    return "&".join(f"{key}={value}" for key, value in sorted(key_val_pairs))


def _canonical_uri(path: str) -> str:
    return quote(_normalize_url_path(path), safe="/~")


def sign_request(
    *,
    method: str,
    url: str,
    access_key: str,
    secret_key: str,
    region: str,
    service: str = "s3",
    params: Mapping[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
    payload: bytes = b"",
    timestamp: datetime | None = None,
) -> tuple[dict[str, str], str]:
    """Return signed headers and the request URL including query string."""
    parsed = urlsplit(url)
    host = _host_from_url(url)
    canonical_uri = _canonical_uri(parsed.path or "/")
    canonical_querystring = _canonical_query_string(params)

    payload_hash = hashlib.sha256(payload).hexdigest()
    amz_date = (timestamp or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    date_stamp = amz_date[:8]

    canonical_headers_map: dict[str, str] = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if headers:
        for key, value in headers.items():
            canonical_headers_map[key.lower()] = " ".join(value.split())

    signed_header_names = sorted(canonical_headers_map)
    canonical_headers = "".join(
        f"{name}:{canonical_headers_map[name]}\n" for name in signed_header_names
    )
    signed_headers = ";".join(signed_header_names)

    canonical_request = "\n".join(
        [
            method.upper(),
            canonical_uri,
            canonical_querystring,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )

    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    signing_key = _get_signature_key(secret_key, date_stamp, region, service)
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    authorization = (
        "AWS4-HMAC-SHA256 "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    signed_headers_out = {
        "Host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
        "Authorization": authorization,
    }
    if headers:
        signed_headers_out.update(headers)

    request_url = urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, canonical_querystring, "")
    )
    return signed_headers_out, request_url
