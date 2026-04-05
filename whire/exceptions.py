class WhireError(Exception):
    """Base exception for Whire SDK."""

    def __init__(self, message: str, status_code: int | None = None, error_code: str | None = None):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)

    @property
    def is_retryable(self) -> bool:
        """Whether the agent should retry this request."""
        return self.error_code in ("token_expired", "provider_error", "rate_limited", "unknown_error", "network_error") or (
            self.status_code is not None and self.status_code >= 500
        )

    @property
    def needs_user_action(self) -> bool:
        """Whether this error requires the user to do something."""
        return self.error_code in ("insufficient_funds", "forbidden", "consent_expired")

    @property
    def is_input_error(self) -> bool:
        """Whether the agent provided bad input and should fix parameters."""
        return self.error_code in (
            "invalid_input", "invalid_account_number", "invalid_authorization",
            "missing_fields", "account_not_found",
        )

    def to_agent_dict(self) -> dict:
        """Return a dict the agent can reason about."""
        return {
            "error": self.message,
            "error_code": self.error_code,
            "retryable": self.is_retryable,
            "needs_user_action": self.needs_user_action,
            "is_input_error": self.is_input_error,
            "suggestion": self._suggest(),
        }

    def _suggest(self) -> str:
        suggestions = {
            "invalid_account_number": "Ask the user to verify the recipient's account number is correct.",
            "insufficient_funds": "Inform the user their account has insufficient funds.",
            "forbidden": "The user's account may not have permission for this operation.",
            "account_not_found": "The account_id is invalid. Verify it with the user.",
            "missing_fields": "Check that all required fields are provided.",
            "invalid_authorization": "The payment mandate has been tampered with. Rebuild it.",
            "token_expired": "The session has expired. Re-authenticate and retry.",
            "invalid_input": "Check the request parameters — something was rejected by the provider.",
            "network_error": "The network request failed. Retry after a short delay.",
        }
        return suggestions.get(self.error_code or "", "An unexpected error occurred. You may retry.")


class AuthenticationError(WhireError):
    """Raised when API key is invalid or missing."""

    def __init__(self, message: str = "Invalid API key"):
        super().__init__(message, status_code=401, error_code="auth_failed")


class PaymentError(WhireError):
    """Raised when a payment request fails."""


class MandateError(WhireError):
    """Raised when a mandate operation fails."""


class ValidationError(WhireError):
    """Raised when request validation fails."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message, status_code=status_code, error_code="validation_error")
