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


class ConnectionError(BotoCoreError):
    pass


class ParamValidationError(BotoCoreError):
    def __init__(self, message: str = "") -> None:
        self.error_message = message
        super().__init__(message)
