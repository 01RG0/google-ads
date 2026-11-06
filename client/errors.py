class TransparencyError(Exception):
    """Base exception for client errors."""


class ResponseShapeError(TransparencyError):
    """The upstream returned a payload outside the captured contract."""


class UnsupportedFilterError(TransparencyError):
    """A filter was requested whose RPC encoding was not captured."""


class UpstreamHTTPError(TransparencyError):
    """The upstream returned a non-success response after retries."""
