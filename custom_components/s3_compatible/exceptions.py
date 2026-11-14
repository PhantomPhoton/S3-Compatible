"""Local exception types used by the integration (replacement for botocore.exceptions).

These are minimal classes to mirror the shape of the exceptions the code
previously expected. They are intentionally simple and only used for
exception handling control flow.
"""

class BotoCoreError(Exception):
    pass


class ClientError(BotoCoreError):
    def __init__(self, error_response=None, operation_name=None):
        super().__init__(error_response, operation_name)
        self.response = error_response or {}
        self.operation_name = operation_name

    @property
    def status_code(self) -> int | None:
        return self.response.get("ResponseMetadata", {}).get("HTTPStatusCode")

    @property
    def headers(self) -> dict[str, str]:
        return self.response.get("ResponseMetadata", {}).get("HTTPHeaders", {})


class ConnectionError(BotoCoreError):
    pass


class ParamValidationError(BotoCoreError):
    def __init__(self, message: str = "") -> None:
        self.error_message = message
        super().__init__(message)
