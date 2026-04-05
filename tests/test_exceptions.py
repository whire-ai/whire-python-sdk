"""Tests for structured error handling."""

from whire.exceptions import AuthenticationError, PaymentError, ValidationError, WhireError


def test_whire_error_retryable_on_server_error():
    err = WhireError("fail", status_code=500, error_code="server_error")
    assert err.is_retryable is True


def test_whire_error_retryable_on_provider_error():
    err = WhireError("fail", error_code="provider_error")
    assert err.is_retryable is True


def test_whire_error_retryable_on_network_error():
    err = WhireError("fail", error_code="network_error")
    assert err.is_retryable is True


def test_whire_error_not_retryable_on_input_error():
    err = WhireError("bad account", status_code=422, error_code="invalid_account_number")
    assert err.is_retryable is False


def test_whire_error_needs_user_action():
    err = WhireError("no funds", error_code="insufficient_funds")
    assert err.needs_user_action is True
    assert err.is_input_error is False


def test_whire_error_is_input_error():
    err = WhireError("bad input", error_code="invalid_input")
    assert err.is_input_error is True
    assert err.needs_user_action is False


def test_whire_error_to_agent_dict():
    err = WhireError("Invalid account", status_code=422, error_code="invalid_account_number")
    d = err.to_agent_dict()
    assert d["error"] == "Invalid account"
    assert d["error_code"] == "invalid_account_number"
    assert d["retryable"] is False
    assert d["is_input_error"] is True
    assert "suggestion" in d


def test_authentication_error_defaults():
    err = AuthenticationError()
    assert err.status_code == 401
    assert err.error_code == "auth_failed"
    assert err.is_retryable is False


def test_validation_error_defaults():
    err = ValidationError("bad field")
    assert err.status_code == 422
    assert err.error_code == "validation_error"


def test_payment_error():
    err = PaymentError("no account", error_code="account_not_found")
    assert err.is_input_error is True
    assert err.message == "no account"


def test_suggestion_for_known_codes():
    codes_with_suggestions = [
        "invalid_account_number",
        "insufficient_funds",
        "forbidden",
        "account_not_found",
        "missing_fields",
        "invalid_authorization",
        "token_expired",
        "invalid_input",
    ]
    for code in codes_with_suggestions:
        err = WhireError("test", error_code=code)
        assert len(err.to_agent_dict()["suggestion"]) > 10


def test_suggestion_for_unknown_code():
    err = WhireError("test", error_code="something_new")
    assert "unexpected" in err.to_agent_dict()["suggestion"].lower()
