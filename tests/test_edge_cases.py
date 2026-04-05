"""Edge case tests for the Whire SDK."""

import hashlib
import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from whire.client import WhireClient
from whire.exceptions import WhireError
from whire.mandate import build_payment_mandate


@pytest.fixture
def client():
    return WhireClient(
        api_key="test-key",
        custom_base_url="http://localhost:8000",
    )


def _mock_response(status_code: int, data: dict) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=data,
        request=httpx.Request("POST", "http://test"),
    )


# ── Mandate edge cases ──


def test_mandate_unicode_label():
    """Mandate handles unicode characters in labels."""
    mandate = build_payment_mandate(
        mandate_id="test-unicode",
        payment_details_id="pd-u",
        amount=Decimal("50.00"),
        label="Paiement Café",
        account_id="acc",
        recipient_id="rcp-001",
        merchant_agent="agent",
    )

    contents = mandate["payment_mandate_contents"]
    assert contents["payment_details_total"]["label"] == "Paiement Café"
    assert contents["payment_response"]["details"]["recipient_id"] == "rcp-001"

    # Hash should still be valid
    payload = json.dumps(contents, separators=(",", ":"), sort_keys=False)
    expected = hashlib.sha256(payload.encode()).hexdigest()
    assert mandate["user_authorization"] == expected


def test_mandate_large_amount():
    """Mandate handles large amounts correctly."""
    mandate = build_payment_mandate(
        mandate_id="test-large",
        payment_details_id="pd-l",
        amount=Decimal("999999.99"),
        label="Big Payment",
        account_id="acc",
        recipient_id="rcp-001",
        merchant_agent="agent",
    )

    assert mandate["payment_mandate_contents"]["payment_details_total"]["amount"] == "999999.99"


def test_mandate_small_amount():
    """Mandate handles small amounts correctly."""
    mandate = build_payment_mandate(
        mandate_id="test-small",
        payment_details_id="pd-s",
        amount=Decimal("0.01"),
        label="Tiny Payment",
        account_id="acc",
        recipient_id="rcp-001",
        merchant_agent="agent",
    )

    assert mandate["payment_mandate_contents"]["payment_details_total"]["amount"] == "0.01"


def test_mandate_timestamp_is_utc_iso():
    """Mandate timestamp is ISO 8601 with UTC timezone."""
    mandate = build_payment_mandate(
        mandate_id="test-ts",
        payment_details_id="pd-ts",
        amount=Decimal("10.00"),
        label="Test",
        account_id="acc",
        recipient_id="rcp-001",
        merchant_agent="agent",
    )

    ts = mandate["payment_mandate_contents"]["timestamp"]
    assert "T" in ts
    assert "+" in ts or "Z" in ts


def test_mandate_custom_currency():
    """Mandate can use non-EUR currency."""
    mandate = build_payment_mandate(
        mandate_id="test-usd",
        payment_details_id="pd-usd",
        amount=Decimal("100.00"),
        label="USD Payment",
        account_id="acc",
        recipient_id="rcp-001",
        merchant_agent="agent",
        currency="USD",
    )

    assert mandate["payment_mandate_contents"]["payment_details_total"]["currency"] == "USD"


# ── Client edge cases ──


@pytest.mark.asyncio
async def test_empty_transaction_list(client):
    """Client handles empty transaction list."""
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(200, {"transactions": []})
        result = await client.get_transactions(limit=5)

    assert result.transactions == []


@pytest.mark.asyncio
async def test_pay_with_idempotency_key(client):
    """Idempotency key is used as mandate_id."""
    mock_data = {
        "receipt_id": "rcpt-idem",
        "order_id": "my-key-123",
        "status": "approved",
        "transaction_id": "txn-idem",
        "amount_charged": "25.00",
        "currency": "EUR",
        "processor_message": "OK",
        "error_code": None,
        "consent_url": None,
        "processed_at": "2026-04-01T10:00:00Z",
    }

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(201, mock_data)

        result = await client.pay(
            recipient_id="rcp-123",
            amount="25.00",
            label="Test",
            idempotency_key="my-key-123",
        )

    # Verify the simple JSON body sent to API contains our key and recipient
    sent_body = mock_req.call_args[1]["json"]
    assert sent_body["idempotency_key"] == "my-key-123"
    assert sent_body["recipient_id"] == "rcp-123"


@pytest.mark.asyncio
async def test_debit_with_reference(client):
    """Debit includes optional reference field."""
    mock_data = {
        "payment_id": "spi-ref",
        "status": "Initiated",
        "amount": "10.00",
        "currency": "EUR",
        "label": "Sub",
        "message": "OK",
        "created_at": "2026-04-01T10:00:00Z",
    }

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(201, mock_data)

        await client.debit(
            mandate_id="mand-123",
            amount="10.00",
            label="Sub",
            reference="inv-999",
        )

    sent_body = mock_req.call_args[1]["json"]
    assert sent_body["reference"] == "inv-999"


@pytest.mark.asyncio
async def test_debit_without_reference(client):
    """Debit omits reference when not provided."""
    mock_data = {
        "payment_id": "spi-noref",
        "status": "Initiated",
        "amount": "10.00",
        "currency": "EUR",
        "label": "Sub",
        "message": "OK",
        "created_at": "2026-04-01T10:00:00Z",
    }

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_response(201, mock_data)

        await client.debit(mandate_id="mand-123", amount="10.00", label="Sub")

    sent_body = mock_req.call_args[1]["json"]
    assert "reference" not in sent_body


@pytest.mark.asyncio
async def test_network_error_retries(client):
    """Client retries on network transport errors."""
    call_count = 0

    async def mock_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.ConnectError("Connection refused")
        return _mock_response(200, {"payment_id": "txn-1", "status": "Booked", "created_at": "2026-04-01"})

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, side_effect=mock_request):
        client._retry_base_delay = 0.01
        result = await client.get_payment_status("txn-1")

    assert result.status == "Booked"
    assert call_count == 3


