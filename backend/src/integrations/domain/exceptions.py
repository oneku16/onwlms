"""Integration-owned failures raised before external evidence is trusted."""


class IntegrationError(Exception):
    """Base class for failures owned by the integration boundary."""


class GradeEventSignatureError(IntegrationError):
    """Raised when a grade event cannot be authenticated for one tenant."""


class GradeEventRejectedError(IntegrationError):
    """Raised when an authenticated grade event has an unusable payload."""


__all__ = [
    "GradeEventRejectedError",
    "GradeEventSignatureError",
    "IntegrationError",
]
