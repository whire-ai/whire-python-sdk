"""Tests for WhireClient with mocked HTTP responses."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from email.utils import format_datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from whire.client import WhireClient
from whire.exceptions import AuthenticationError, ValidationError, WhireError


@pytest.fixture
def client():
    return WhireClient(
        api_key="test-key",
        custom_base_url="http://localhost:8000",
    )


def _mock_response(status_code: int, data: dict | None = None) -> httpx.Response:
    if data is None:
        return httpx.Response(
            status_code=status_code,
            content=b"",
            request=httpx.Request("DELETE", "http://test"),
        )
    return httpx.Response(
        status_code=status_code,
        json=data,
        request=httpx.Request("POST", "http://test"),
    )


@pytest.mark.asyncio
async def test_pay_success(client):
    mock_data = {
        "receipt_id": "rcpt-123",
        "status": "approved",
        "transaction_id": "txn-456",
        "amount_charged": "50.00",
        "currency": "EUR",
        "processor_message": "Transfer initiated",
        "error_code": None,
        "consent_url": "https://consent.example.com",
        "processed_at": "2026-04-01T10:00:00Z",
    }

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(201, mock_data)

        result = await client.pay(
            recipient_id="rcp-123",
            amount="50.00",
            label="Test",
        )

    assert result.status == "approved"
    assert result.transaction_id == "txn-456"
    assert result.amount_charged == Decimal("50.00")
    assert result.consent.requires_consent is True
    assert result.consent.consent_url == "https://consent.example.com"


@pytest.mark.asyncio
async def test_pay_declined(client):
    mock_data = {
        "receipt_id": "rcpt-789",
        "status": "declined",
        "transaction_id": None,
        "amount_charged": None,
        "currency": "EUR",
        "processor_message": "Insufficient funds",
        "error_code": "insufficient_funds",
        "consent_url": None,
        "processed_at": "2026-04-01T10:00:00Z",
    }

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(201, mock_data)

        result = await client.pay(
            recipient_id="rcp-123",
            amount="50.00",
            label="Test",
        )

    assert result.status == "declined"
    assert result.error_code == "insufficient_funds"


@pytest.mark.asyncio
async def test_authentication_error(client):
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(401, {"detail": "Unauthorized"})

        with pytest.raises(AuthenticationError):
            await client.get_payment_status("txn-123")


@pytest.mark.asyncio
async def test_validation_error(client):
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(422, {"detail": "Invalid account number"})

        with pytest.raises(ValidationError):
            await client.pay(
                recipient_id="rcp-123",
                amount="10.00",
                label="Test",
            )


@pytest.mark.asyncio
async def test_retry_on_server_error(client):
    """Client retries on 5xx errors with backoff."""
    success_data = {"payment_id": "txn-123", "status": "Booked", "created_at": "2026-04-01"}

    call_count = 0

    async def mock_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return _mock_response(500, {"detail": "Internal error"})
        return _mock_response(200, success_data)

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, side_effect=mock_request):
        client._retry_base_delay = 0.01
        result = await client.get_payment_status("txn-123")

    assert result.status == "Booked"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_exhausted_raises(client):
    """Client raises after exhausting retries."""
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(500, {"detail": "Server down"})
        client._retry_base_delay = 0.01

        with pytest.raises(WhireError, match="Server down"):
            await client.get_payment_status("txn-123")


@pytest.mark.asyncio
async def test_get_balance(client):
    mock_data = {
        "available": {"value": "1000.00", "currency": "EUR"},
        "booked": {"value": "950.00", "currency": "EUR"},
    }

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(200, mock_data)
        result = await client.get_balance()

    assert result.available == Decimal("1000.00")
    assert result.booked == Decimal("950.00")


@pytest.mark.asyncio
async def test_get_transactions(client):
    mock_data = {
        "transactions": [
            {
                "id": "txn-1",
                "type": "CreditTransferOut",
                "side": "Debit",
                "amount": "50.00",
                "currency": "EUR",
                "label": "Payment",
                "status": "Booked",
                "created_at": "2026-04-01T10:00:00Z",
            }
        ]
    }

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(200, mock_data)
        result = await client.get_transactions(limit=5)

    assert len(result.transactions) == 1
    assert result.transactions[0].amount == Decimal("50.00")
    assert result.transactions[0].side == "Debit"


@pytest.mark.asyncio
async def test_create_mandate(client):
    mock_data = {
        "mandate_id": "mand-123",
        "status": "Enabled",
        "recipient_name": "John Doe",
        "recipient_iban": "FR7630006000011234567890189",
        "sequence": "Recurrent",
    }

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(201, mock_data)

        result = await client.create_mandate(
            recipient_id="rcp-123",
        )

    assert result.mandate_id == "mand-123"
    assert result.status == "Enabled"
    assert result.recipient_name == "John Doe"
    assert result.recipient_account == "FR7630006000011234567890189"


@pytest.mark.asyncio
async def test_create_recipient(client):
    mock_data = {
        "id": "rcp-123",
        "name": "John Doe",
        "iban": "FR7630006000011234567890189",
        "country": "FRA",
        "label": None,
        "created_at": "2026-04-03T10:00:00Z",
    }

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(201, mock_data)

        result = await client.create_recipient(
            name="John Doe",
            account_number="FR7630006000011234567890189",
            country="FRA",
            label="Landlord",
        )

    assert result.recipient_id == "rcp-123"
    assert result.name == "John Doe"
    assert result.account_number == "FR7630006000011234567890189"
    assert result.country == "FRA"
    assert result.created_at == "2026-04-03T10:00:00Z"


@pytest.mark.asyncio
async def test_list_recipients(client):
    mock_data = {
        "items": [
            {
                "id": "rcp-123",
                "name": "John Doe",
                "iban": "FR7630006000011234567890189",
                "country": "FRA",
                "label": "Landlord",
                "created_at": "2026-04-03T10:00:00Z",
            },
            {
                "id": "rcp-456",
                "name": "Jane Smith",
                "iban": "DE89370400440532013000",
                "country": "DEU",
                "label": None,
                "created_at": "2026-04-02T09:00:00Z",
            },
        ],
        "total": 2,
        "offset": 0,
        "limit": 20,
    }

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(200, mock_data)
        result = await client.list_recipients()

    assert result.total == 2
    assert result.offset == 0
    assert result.limit == 20
    assert len(result.items) == 2
    assert result.items[0].recipient_id == "rcp-123"
    assert result.items[0].name == "John Doe"
    assert result.items[0].account_number == "FR7630006000011234567890189"
    assert result.items[1].recipient_id == "rcp-456"
    assert result.items[1].name == "Jane Smith"


@pytest.mark.asyncio
async def test_list_recipients_with_search(client):
    mock_data = {
        "items": [
            {
                "id": "rcp-123",
                "name": "John Doe",
                "iban": "FR7630006000011234567890189",
                "country": "FRA",
                "label": None,
                "created_at": "2026-04-03T10:00:00Z",
            },
        ],
        "total": 1,
        "offset": 0,
        "limit": 20,
    }

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(200, mock_data)
        result = await client.list_recipients(search="John")

    assert result.total == 1
    assert result.items[0].name == "John Doe"

    # Verify search param was included in the request URL
    call_args = mock_req.call_args
    url = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("url", "")
    assert "search=John" in str(url)


@pytest.mark.asyncio
async def test_get_recipient(client):
    mock_data = {
        "id": "rcp-123",
        "name": "John Doe",
        "iban": "FR7630006000011234567890189",
        "country": "FRA",
        "label": "Landlord",
        "created_at": "2026-04-03T10:00:00Z",
    }

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(200, mock_data)
        result = await client.get_recipient("rcp-123")

    assert result.recipient_id == "rcp-123"
    assert result.name == "John Doe"
    assert result.account_number == "FR7630006000011234567890189"
    assert result.country == "FRA"
    assert result.label == "Landlord"
    assert result.created_at == "2026-04-03T10:00:00Z"


@pytest.mark.asyncio
async def test_list_recipients_limit_validation(client):
    """Client validates recipient list limits before making a request."""
    with pytest.raises(ValidationError, match="limit must be an integer between 1 and 100"):
        await client.list_recipients(limit=0)

    with pytest.raises(ValidationError, match="limit must be an integer between 1 and 100"):
        await client.list_recipients(limit=101)


@pytest.mark.asyncio
async def test_debit(client):
    mock_data = {
        "payment_id": "spi-456",
        "status": "Initiated",
        "amount": "25.00",
        "currency": "EUR",
        "label": "Subscription",
        "message": "Payment initiated",
        "created_at": "2026-04-01T10:00:00Z",
    }

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(201, mock_data)

        result = await client.debit(
            mandate_id="mand-123",
            amount="25.00",
            label="Subscription",
        )

    assert result.payment_id == "spi-456"
    assert result.amount == Decimal("25.00")


# -- Input validation tests --


@pytest.mark.asyncio
async def test_pay_rejects_negative_amount(client):
    with pytest.raises(ValidationError, match="positive"):
        await client.pay(recipient_id="rcp-123", amount="-10.00", label="Test")


@pytest.mark.asyncio
async def test_pay_rejects_zero_amount(client):
    with pytest.raises(ValidationError, match="positive"):
        await client.pay(recipient_id="rcp-123", amount="0", label="Test")


@pytest.mark.asyncio
async def test_pay_rejects_bad_decimal(client):
    with pytest.raises(ValidationError, match="Invalid amount"):
        await client.pay(recipient_id="rcp-123", amount="not-a-number", label="Test")


@pytest.mark.asyncio
async def test_pay_rejects_too_many_decimals(client):
    with pytest.raises(ValidationError, match="decimal places"):
        await client.pay(recipient_id="rcp-123", amount="10.123", label="Test")


@pytest.mark.asyncio
async def test_pay_rejects_empty_recipient_id(client):
    with pytest.raises(ValidationError, match="recipient_id"):
        await client.pay(recipient_id="", amount="10.00", label="Test")


@pytest.mark.asyncio
async def test_create_recipient_rejects_bad_country(client):
    with pytest.raises(ValidationError, match="3-letter"):
        await client.create_recipient(name="Test", account_number="FR76X", country="FR")


@pytest.mark.asyncio
async def test_debit_rejects_empty_mandate_id(client):
    with pytest.raises(ValidationError, match="mandate_id"):
        await client.debit(mandate_id="", amount="10.00", label="Test")


# -- Error handling tests --


@pytest.mark.asyncio
async def test_invalid_json_response(client):
    """Client handles non-JSON responses gracefully."""
    raw_response = httpx.Response(
        status_code=200,
        content=b"<html>Bad Gateway</html>",
        request=httpx.Request("GET", "http://test"),
    )

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = raw_response
        with pytest.raises(WhireError, match="Invalid response"):
            await client.get_payment_status("txn-123")


@pytest.mark.asyncio
async def test_missing_response_fields(client):
    """Client handles missing fields in API response."""
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(200, {"unexpected": "data"})
        with pytest.raises(WhireError, match="Unexpected response"):
            await client.get_balance()


@pytest.mark.asyncio
async def test_rate_limit_retry(client):
    """Client retries on 429 with Retry-After header."""
    success_data = {"payment_id": "txn-123", "status": "Booked", "created_at": "2026-04-01"}
    call_count = 0

    async def mock_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            resp = httpx.Response(
                status_code=429,
                json={"detail": "Rate limited"},
                headers={"Retry-After": "0.01"},
                request=httpx.Request("GET", "http://test"),
            )
            return resp
        return _mock_response(200, success_data)

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, side_effect=mock_request):
        client._retry_base_delay = 0.01
        result = await client.get_payment_status("txn-123")

    assert result.status == "Booked"
    assert call_count == 2


@pytest.mark.asyncio
async def test_rate_limit_retry_with_http_date_header(client):
    """Client supports HTTP-date Retry-After headers."""
    success_data = {"payment_id": "txn-123", "status": "Booked", "created_at": "2026-04-01"}
    retry_after = format_datetime(datetime.now(timezone.utc) - timedelta(seconds=1), usegmt=True)
    call_count = 0

    async def mock_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(
                status_code=429,
                json={"detail": "Rate limited"},
                headers={"Retry-After": retry_after},
                request=httpx.Request("GET", "http://test"),
            )
        return _mock_response(200, success_data)

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, side_effect=mock_request):
        result = await client.get_payment_status("txn-123")

    assert result.status == "Booked"
    assert call_count == 2


@pytest.mark.asyncio
async def test_payment_status_invalid_response_wrapped(client):
    """Malformed payment status responses raise WhireError, not raw validation errors."""
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(200, {"payment_id": "txn-123"})

        with pytest.raises(WhireError, match="Unexpected response format from payment status endpoint"):
            await client.get_payment_status("txn-123")


@pytest.mark.asyncio
async def test_transactions_limit_validation(client):
    """Client validates transaction limits before making a request."""
    with pytest.raises(ValidationError, match="limit must be an integer between 1 and 100"):
        await client.get_transactions(limit=0)


# -- Context manager tests --


@pytest.mark.asyncio
async def test_context_manager():
    async with WhireClient(api_key="test", custom_base_url="http://localhost:8000") as client:
        assert client is not None
    # After exit, client should be cleaned up


@pytest.mark.asyncio
async def test_version_accessible():
    import whire
    assert whire.__version__ == "0.1.0"
