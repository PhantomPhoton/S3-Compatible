"""Minimal S3 REST client with SigV4 signing.

This client implements the subset of S3 operations used by the
integration: `head_bucket`, `get_object`, `put_object`, `list_objects_v2`,
`create_multipart_upload`, `upload_part`, `complete_multipart_upload`,
`abort_multipart_upload`, and `delete_object`.
"""
from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET

from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests
from requests.exceptions import ConnectionError as RequestsConnectionError

from .exceptions import ClientError, ConnectionError, ParamValidationError
from .sigv4 import sign_request

_LOGGER = logging.getLogger(__name__)


class S3RestClient:
    """Synchronous S3 client using SigV4 signing."""

    def __init__(
        self,
        service_name: str = "s3",
        endpoint_url: Optional[str] = None,
        region_name: str = "us-east-1",
        verify: Optional[bool] = True,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
    ) -> None:
        self.service_name = service_name
        self.endpoint_url = (endpoint_url or "").rstrip("/")
        self.region = region_name or "us-east-1"
        self.verify = verify
        self.access_key = aws_access_key_id
        self.secret_key = aws_secret_access_key

        _LOGGER.info(
            "Initialized S3RestClient endpoint=%s region=%s verify=%s access_key=%s secret_key=%s",
            self.endpoint_url,
            self.region,
            self.verify,
            self.access_key,
            "********" if len(self.secret_key) > 0 else "(none)",
        )

    def _request(
        self,
        method: str,
        bucket: str = "",
        key: str = "",
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        payload: Optional[bytes] = None,
        operation: str = "",
    ) -> requests.Response:
        _LOGGER.info(
            "_request called method=%s bucket=%s key=%s operation=%s",
            method,
            bucket,
            key,
            operation,
        )

        if not self.endpoint_url:
            raise ConnectionError("No endpoint configured")

        if not self.access_key or not self.secret_key:
            raise ConnectionError("No AWS credentials provided")

        url = self._build_path(bucket, key)
        payload_bytes = payload or b""

        signed_headers, request_url = sign_request(
            method=method,
            url=url,
            access_key=self.access_key,
            secret_key=self.secret_key,
            region=self.region,
            service=self.service_name,
            params=params,
            headers=headers,
            payload=payload_bytes,
        )

        try:
            response = requests.request(
                method,
                request_url,
                headers=signed_headers,
                data=payload_bytes if payload_bytes else None,
                verify=self.verify,
                allow_redirects=False,
            )
        except RequestsConnectionError as err:
            raise ConnectionError(str(err)) from err

        _LOGGER.info("_request response status_code=%d", response.status_code)

        # Handle wrong region: if the server says a different region is expected,
        # raise an informative exception rather than silently failing.
        if response.status_code == 400:
            correct_region = response.headers.get("x-amz-bucket-region")
            if correct_region:
                raise ParamValidationError(
                    f"The bucket is in region '{correct_region}', "
                    f"but the configured region is '{self.region}'. "
                    f"Update your configuration to use region '{correct_region}'."
                )

        if response.status_code >= 400:
            raise ClientError(
                {
                    "Error": {
                        "Code": str(response.status_code),
                        "Message": response.reason or "",
                    },
                    "ResponseMetadata": {"HTTPStatusCode": response.status_code},
                },
                operation or method,
            )

        return response

    def _build_path(self, bucket: str = "", key: str = "") -> str:
        """Build the request path for the S3 endpoint."""
        url = self.endpoint_url
        parsed = urlparse(url)
        host = parsed.netloc

        path = "/"
        if bucket:
             # For virtual-hosted-style endpoints (standard S3), the bucket is
             # a subdomain of the host, so the path should only include the key.
             # For path-style endpoints (e.g. MinIO, self-hosted), include
             # the bucket in the path.
            if host.startswith(f"{bucket}."):
                _LOGGER.info(
                    "_build_path virtual-hosted: endpoint=%s host=%s bucket=%s => path=/%s",
                    url, host, bucket, key or '',
                )
                pass    # virtual-hosted style: skip bucket from path
            else:
                _LOGGER.info(
                    "_build_path path-style: endpoint=%s host=%s bucket=%s key=%s => %s%s",
                    url, host, bucket, key, path, f'{bucket}/{key}' if key else bucket,
                )
                path += f"{bucket}"
                if key:
                    path += f"/{key}"
        elif key:
            path += key

        full_url = url + path
        _LOGGER.info("_build_path full URL=%s", full_url)
        return full_url

    def head_bucket(self, Bucket: str) -> Dict[str, Any]:
        _LOGGER.info("head_bucket called Bucket=%s", Bucket)
        resp = self._request("HEAD", bucket=Bucket, operation="HeadBucket")
        return {"ResponseMetadata": {"HTTPStatusCode": resp.status_code}}

    def get_object(self, Bucket: str, Key: str) -> Dict[str, Any]:
        _LOGGER.info("get_object called Bucket=%s Key=%s", Bucket, Key)
        resp = self._request("GET", bucket=Bucket, key=Key, operation="GetObject")
        content = resp.content
        return {"Body": _Body(content), "ResponseMetadata": {"HTTPStatusCode": resp.status_code}}

    def put_object(self, Bucket: str, Key: str, Body: bytes) -> Dict[str, Any]:
        data = Body if isinstance(Body, (bytes, bytearray)) else Body.encode("utf-8")
        _LOGGER.info(
            "put_object called Bucket=%s Key=%s Body_bytes=%d",
            Bucket,
            Key,
            len(data),
        )
        resp = self._request("PUT", bucket=Bucket, key=Key, payload=data, operation="PutObject")
        return {"ResponseMetadata": {"HTTPStatusCode": resp.status_code}}

    def list_objects_v2(
        self,
        Bucket: str,
        Prefix: str = "",
    ) -> Dict[str, Any]:
        _LOGGER.info("list_objects_v2 called Bucket=%s Prefix=%s", Bucket, Prefix)
        params: Dict[str, str] = {"list-type": "2"}
        if Prefix:
            params["prefix"] = Prefix
        resp = self._request("GET", bucket=Bucket, params=params, operation="ListObjectsV2")
        
        root = ET.fromstring(resp.content)
        contents = []
        # Search for Contents elements regardless of namespace
        for c in root.iter():
            if c.tag == "Contents" or (isinstance(c.tag, str) and c.tag.endswith("}Contents")):
                # Find Key and Size within the Contents element
                key = None
                size = 0
                for child in c.iter():
                    if child.tag == "Key" or (isinstance(child.tag, str) and child.tag.endswith("}Key")):
                        key = child.text
                    elif child.tag == "Size" or (isinstance(child.tag, str) and child.tag.endswith("}Size")):
                        size = int(child.text or 0)

                if key:
                    contents.append({"Key": key, "Size": size})
        _LOGGER.info("Parsed %d objects from list_objects_v2", len(contents))
        return {"Contents": contents}

    def create_multipart_upload(self, Bucket: str, Key: str) -> Dict[str, Any]:
        _LOGGER.info("create_multipart_upload called Bucket=%s Key=%s", Bucket, Key)
        params = {"uploads": ""}
        resp = self._request(
            "POST",
            bucket=Bucket,
            key=Key,
            params=params,
            operation="CreateMultipartUpload",
        )
        root = ET.fromstring(resp.content)
        upload_id = None
        for el in root.iter():
            if el.tag == "UploadId" or (isinstance(el.tag, str) and el.tag.endswith("}UploadId")):
                upload_id = el.text
                break

        if upload_id is None:
            _LOGGER.info("create_multipart_upload failed to find UploadId in response:\n%s", resp.text)
        return {"UploadId": upload_id}

    def upload_part(
        self,
        Bucket: str,
        Key: str,
        PartNumber: int,
        UploadId: str,
        Body: bytes,
    ) -> Dict[str, Any]:
        _LOGGER.info(
            "upload_part called Bucket=%s Key=%s PartNumber=%d UploadId=%s Body_bytes=%d",
            Bucket,
            Key,
            PartNumber,
            UploadId,
            len(Body),
        )
        params = {"partNumber": str(PartNumber), "uploadId": UploadId}
        resp = self._request(
            "PUT",
            bucket=Bucket,
            key=Key,
            params=params,
            payload=Body,
            operation="UploadPart",
        )
        etag = resp.headers.get("ETag", "")
        return {"ETag": etag}

    def complete_multipart_upload(
        self,
        Bucket: str,
        Key: str,
        UploadId: str,
        MultipartUpload: Dict[str, Any],
    ) -> Dict[str, Any]:
        _LOGGER.info(
            "complete_multipart_upload called Bucket=%s Key=%s UploadId=%s",
            Bucket,
            Key,
            UploadId,
        )
        parts = MultipartUpload.get("Parts", [])
        root = ET.Element("CompleteMultipartUpload")
        for part in parts:
            p = ET.SubElement(root, "Part")
            ET.SubElement(p, "PartNumber").text = str(part["PartNumber"])
            ET.SubElement(p, "ETag").text = part["ETag"]
        body = ET.tostring(root, encoding="utf-8")
        params = {"uploadId": UploadId}
        resp = self._request(
            "POST",
            bucket=Bucket,
            key=Key,
            params=params,
            payload=body,
            operation="CompleteMultipartUpload",
        )
        return {"ResponseMetadata": {"HTTPStatusCode": resp.status_code}}

    def abort_multipart_upload(self, Bucket: str, Key: str, UploadId: str) -> None:
        _LOGGER.info(
            "abort_multipart_upload called Bucket=%s Key=%s UploadId=%s",
            Bucket,
            Key,
            UploadId,
        )
        params = {"uploadId": UploadId}
        self._request(
            "DELETE",
            bucket=Bucket,
            key=Key,
            params=params,
            operation="AbortMultipartUpload",
        )

    def delete_object(self, Bucket: str, Key: str) -> Dict[str, Any]:
        _LOGGER.info("delete_object called Bucket=%s Key=%s", Bucket, Key)
        resp = self._request("DELETE", bucket=Bucket, key=Key, operation="DeleteObject")
        return {"ResponseMetadata": {"HTTPStatusCode": resp.status_code}}


class _Body:
    """Async-iterable body wrapper backed by in-memory bytes."""

    def __init__(self, content: bytes, chunk_size: int = 65536) -> None:
        self._content = content
        self._pos = 0
        self._chunk_size = chunk_size

    def __aiter__(self) -> "_Body":
        return self

    async def __anext__(self) -> bytes:
        if self._pos >= len(self._content):
            raise StopAsyncIteration
        chunk = self._content[self._pos : self._pos + self._chunk_size]
        self._pos += len(chunk)
        return chunk

    async def read(self) -> bytes:
        """Read the entire body as bytes."""
        return self._content


@asynccontextmanager
async def create_client(service_name: str = "s3", **kwargs: Any) -> Any:
    _LOGGER.info("create_client called service_name=%s", service_name)
    client = S3RestClient(
        service_name=service_name,
        endpoint_url=kwargs.pop("endpoint_url", None),
        region_name=kwargs.pop("region_name", None) or kwargs.pop("region", None),
        verify=kwargs.pop("verify", True),
        aws_access_key_id=kwargs.pop("aws_access_key_id", None)
        or kwargs.pop("access_key", None),
        aws_secret_access_key=kwargs.pop("aws_secret_access_key", None)
        or kwargs.pop("secret_key", None),
    )

    class _Proxy:
        def __init__(self, client: S3RestClient) -> None:
            self._client = client

        async def __aenter__(self) -> "_Proxy":
            return self

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

        def __getattr__(self, name: str) -> Any:
            attr = getattr(self._client, name)

            if not callable(attr):
                return attr

            async def _method(*m_args: Any, **m_kwargs: Any) -> Any:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None, lambda a=attr, args=m_args, kwargs=m_kwargs: a(*args, **kwargs)
                )

            return _method

    try:
        yield _Proxy(client)
    finally:
        pass
