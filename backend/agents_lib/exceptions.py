"""Custom exception classes for agents."""


class AgentError(Exception):
    """Base exception for agent errors."""
    pass


class SearchError(AgentError):
    """Error during search operations."""
    def __init__(self, message: str, query: str = None, retryable: bool = True):
        self.message = message
        self.query = query
        self.retryable = retryable
        super().__init__(message)


class NetworkError(AgentError):
    """Network-related errors (QUIC, timeout, connection)."""
    def __init__(self, message: str, original_error: Exception = None, retryable: bool = True):
        self.message = message
        self.original_error = original_error
        self.retryable = retryable
        super().__init__(message)


class URLValidationError(AgentError):
    """URL validation failed."""
    def __init__(self, url: str, status_code: int = None, reason: str = None):
        self.url = url
        self.status_code = status_code
        self.reason = reason
        super().__init__(f"URL validation failed: {url} - {reason}")


class GenerationError(AgentError):
    """Content generation failed."""
    pass
