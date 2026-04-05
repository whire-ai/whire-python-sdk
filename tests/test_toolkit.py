"""Tests for WhireToolkit agent interface."""

from unittest.mock import AsyncMock, patch

import pytest

from whire.toolkit import WhireToolkit


@pytest.fixture
def toolkit():
    return WhireToolkit(
        api_key="test-key",
        custom_base_url="http://localhost:8000",
    )


def test_get_tools_format(toolkit):
    """Tools are in function calling format."""
    tools = toolkit.get_tools()
    assert len(tools) == 9

    for tool in tools:
        assert tool["type"] == "function"
        assert "name" in tool["function"]
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]


def test_system_prompt_not_empty(toolkit):
    assert len(toolkit.system_prompt) > 100
    assert "send_payment" in toolkit.system_prompt
    assert "get_balance" in toolkit.system_prompt
    assert "create_recipient" in toolkit.system_prompt


def test_system_prompt_has_no_service_references(toolkit):
    """System prompt should not mention specific banking services."""
    prompt = toolkit.system_prompt.lower()
    assert "sepa" not in prompt
    assert "swan" not in prompt
    assert "sca" not in prompt
    assert "sdd" not in prompt
    assert "psd2" not in prompt


def test_tool_names(toolkit):
    tools = toolkit.get_tools()
    names = {t["function"]["name"] for t in tools}
    assert names == {
        "send_payment",
        "get_payment_status",
        "get_balance",
        "get_transactions",
        "create_mandate",
        "debit_payment",
        "create_recipient",
        "list_recipients",
        "get_recipient",

    }


def test_tool_descriptions_have_no_service_references(toolkit):
    """Tool descriptions should not mention specific banking services."""
    for tool in toolkit.get_tools():
        desc = tool["function"]["description"].lower()
        assert "sepa" not in desc, f"Tool {tool['function']['name']} mentions SEPA"
        assert "swan" not in desc, f"Tool {tool['function']['name']} mentions Swan"
        assert "sca" not in desc, f"Tool {tool['function']['name']} mentions SCA"
        assert "sdd" not in desc, f"Tool {tool['function']['name']} mentions SDD"
        assert "iban" not in desc, f"Tool {tool['function']['name']} mentions IBAN"


@pytest.mark.asyncio
async def test_execute_unknown_tool(toolkit):
    result = await toolkit.execute("nonexistent_tool", {})
    assert "error" in result
    assert result["error_code"] == "unknown_tool"
    assert result["retryable"] is False


@pytest.mark.asyncio
async def test_execute_send_payment_with_consent(toolkit):
    mock_result = AsyncMock()
    mock_result.receipt_id = "rcpt-1"
    mock_result.status = "approved"
    mock_result.transaction_id = "txn-1"
    mock_result.amount_charged = "50.00"
    mock_result.currency = "EUR"
    mock_result.message = "Transfer initiated"
    mock_result.error_code = None
    mock_result.consent.requires_consent = True
    mock_result.consent.consent_url = "https://consent.example.com"

    with patch.object(toolkit._client, "pay", new_callable=AsyncMock, return_value=mock_result):
        result = await toolkit.execute("send_payment", {
            "recipient_id": "rcp-123",
            "amount": "50.00",
            "label": "Test",
        })

    assert result["status"] == "approved"
    assert "consent_url" in result
    assert "action_required" in result


@pytest.mark.asyncio
async def test_execute_get_balance(toolkit):
    mock_result = AsyncMock()
    mock_result.available = "1000.00"
    mock_result.booked = "950.00"
    mock_result.available_currency = "EUR"

    with patch.object(toolkit._client, "get_balance", new_callable=AsyncMock, return_value=mock_result):
        result = await toolkit.execute("get_balance", {})

    assert "available" in result
    assert "booked" in result
    assert "currency" in result


@pytest.mark.asyncio
async def test_execute_handles_whire_error(toolkit):
    from whire.exceptions import WhireError

    with patch.object(
        toolkit._client, "pay",
        new_callable=AsyncMock,
        side_effect=WhireError("Bad account", status_code=422, error_code="invalid_account_number"),
    ):
        result = await toolkit.execute("send_payment", {
            "recipient_id": "rcp-123",
            "amount": "10.00",
            "label": "Test",
        })

    assert "error" in result
    assert result["error_code"] == "invalid_account_number"
    assert result["is_input_error"] is True
    assert "suggestion" in result


@pytest.mark.asyncio
async def test_execute_missing_required_param(toolkit):
    """Toolkit returns structured error when agent omits required params."""
    result = await toolkit.execute("send_payment", {"amount": "10.00"})
    assert "error" in result
    assert result["error_code"] == "missing_fields"
    assert result["retryable"] is False


@pytest.mark.asyncio
async def test_execute_invalid_amount(toolkit):
    """Toolkit returns structured error for bad amount."""
    result = await toolkit.execute("send_payment", {
        "recipient_id": "rcp-123",
        "amount": "not-a-number",
        "label": "Test",
    })
    assert "error" in result
    assert result["error_code"] == "invalid_input"


@pytest.mark.asyncio
async def test_execute_debit_missing_mandate_id(toolkit):
    result = await toolkit.execute("debit_payment", {"amount": "10.00", "label": "Test"})
    assert "error" in result
    assert result["error_code"] == "missing_fields"


@pytest.mark.asyncio
async def test_execute_create_mandate_missing_fields(toolkit):
    result = await toolkit.execute("create_mandate", {"sequence": "Recurrent"})
    assert "error" in result
    assert result["error_code"] == "missing_fields"


# ── Remaining handler tests ──


@pytest.mark.asyncio
async def test_execute_get_payment_status(toolkit):
    mock_result = AsyncMock()
    mock_result.payment_id = "txn-1"
    mock_result.status = "ConsentPending"
    mock_result.created_at = "2026-04-01T10:00:00Z"

    with patch.object(toolkit._client, "get_payment_status", new_callable=AsyncMock, return_value=mock_result):
        result = await toolkit.execute("get_payment_status", {"payment_id": "txn-1"})

    assert result["payment_id"] == "txn-1"
    assert result["status"] == "ConsentPending"
    assert result["hint"] == "The user has not yet approved the payment. Remind them to open the consent URL."


@pytest.mark.asyncio
async def test_execute_get_payment_status_booked(toolkit):
    mock_result = AsyncMock()
    mock_result.payment_id = "txn-2"
    mock_result.status = "Booked"
    mock_result.created_at = None

    with patch.object(toolkit._client, "get_payment_status", new_callable=AsyncMock, return_value=mock_result):
        result = await toolkit.execute("get_payment_status", {"payment_id": "txn-2"})

    assert result["status"] == "Booked"
    assert result["hint"] == "The payment has been settled successfully."
    assert "created_at" not in result


@pytest.mark.asyncio
async def test_execute_get_payment_status_unknown_status(toolkit):
    """Unknown status returns no hint."""
    mock_result = AsyncMock()
    mock_result.payment_id = "txn-3"
    mock_result.status = "SomeNewStatus"
    mock_result.created_at = None

    with patch.object(toolkit._client, "get_payment_status", new_callable=AsyncMock, return_value=mock_result):
        result = await toolkit.execute("get_payment_status", {"payment_id": "txn-3"})

    assert result["status"] == "SomeNewStatus"
    assert "hint" not in result


@pytest.mark.asyncio
async def test_execute_get_transactions(toolkit):
    mock_txn = AsyncMock()
    mock_txn.id = "txn-1"
    mock_txn.type = "CreditTransferOut"
    mock_txn.side = "Debit"
    mock_txn.amount = "50.00"
    mock_txn.currency = "EUR"
    mock_txn.label = "Payment"
    mock_txn.status = "Booked"
    mock_txn.created_at = "2026-04-01T10:00:00Z"

    mock_result = AsyncMock()
    mock_result.transactions = [mock_txn]

    with patch.object(toolkit._client, "get_transactions", new_callable=AsyncMock, return_value=mock_result):
        result = await toolkit.execute("get_transactions", {"limit": 5})

    assert result["count"] == 1
    assert result["transactions"][0]["id"] == "txn-1"
    assert result["transactions"][0]["amount"] == "50.00"


@pytest.mark.asyncio
async def test_execute_get_transactions_default_limit(toolkit):
    """get_transactions uses default limit when not specified."""
    mock_result = AsyncMock()
    mock_result.transactions = []

    with patch.object(toolkit._client, "get_transactions", new_callable=AsyncMock, return_value=mock_result) as mock_fn:
        result = await toolkit.execute("get_transactions", {})

    mock_fn.assert_called_once_with(limit=20)
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_execute_get_transactions_caps_at_100(toolkit):
    """get_transactions caps limit at 100."""
    mock_result = AsyncMock()
    mock_result.transactions = []

    with patch.object(toolkit._client, "get_transactions", new_callable=AsyncMock, return_value=mock_result) as mock_fn:
        await toolkit.execute("get_transactions", {"limit": 500})

    mock_fn.assert_called_once_with(limit=100)


@pytest.mark.asyncio
async def test_execute_create_mandate(toolkit):
    mock_result = AsyncMock()
    mock_result.mandate_id = "mand-1"
    mock_result.status = "Enabled"
    mock_result.recipient_name = "John Doe"
    mock_result.recipient_account = "FR76X"
    mock_result.sequence = "Recurrent"

    with patch.object(toolkit._client, "create_mandate", new_callable=AsyncMock, return_value=mock_result):
        result = await toolkit.execute("create_mandate", {
            "recipient_id": "rcp-123",
        })

    assert result["mandate_id"] == "mand-1"
    assert result["status"] == "Enabled"
    assert result["recipient_name"] == "John Doe"
    assert "debit_payment" in result["message"]


@pytest.mark.asyncio
async def test_execute_debit_payment(toolkit):
    mock_result = AsyncMock()
    mock_result.payment_id = "spi-1"
    mock_result.status = "Initiated"
    mock_result.amount = "25.00"
    mock_result.currency = "EUR"
    mock_result.label = "Sub"
    mock_result.message = "Payment initiated"

    with patch.object(toolkit._client, "debit", new_callable=AsyncMock, return_value=mock_result):
        result = await toolkit.execute("debit_payment", {
            "mandate_id": "mand-1",
            "amount": "25.00",
            "label": "Sub",
        })

    assert result["payment_id"] == "spi-1"
    assert result["amount"] == "25.00"


@pytest.mark.asyncio
async def test_execute_debit_with_reference(toolkit):
    mock_result = AsyncMock()
    mock_result.payment_id = "spi-2"
    mock_result.status = "Initiated"
    mock_result.amount = "10.00"
    mock_result.currency = "EUR"
    mock_result.label = "Sub"
    mock_result.message = "OK"

    with patch.object(toolkit._client, "debit", new_callable=AsyncMock, return_value=mock_result) as mock_fn:
        await toolkit.execute("debit_payment", {
            "mandate_id": "mand-1",
            "amount": "10.00",
            "label": "Sub",
            "reference": "inv-42",
        })

    mock_fn.assert_called_once()
    assert mock_fn.call_args[1]["reference"] == "inv-42"


@pytest.mark.asyncio
async def test_execute_send_payment_without_consent(toolkit):
    """Payment that doesn't need consent has no action_required."""
    mock_result = AsyncMock()
    mock_result.receipt_id = "rcpt-1"
    mock_result.status = "approved"
    mock_result.transaction_id = "txn-1"
    mock_result.amount_charged = "50.00"
    mock_result.currency = "EUR"
    mock_result.message = "OK"
    mock_result.error_code = None
    mock_result.consent.requires_consent = False

    with patch.object(toolkit._client, "pay", new_callable=AsyncMock, return_value=mock_result):
        result = await toolkit.execute("send_payment", {
            "recipient_id": "rcp-123",
            "amount": "50.00",
            "label": "Test",
        })

    assert result["status"] == "approved"
    assert "consent_url" not in result
    assert "action_required" not in result


@pytest.mark.asyncio
async def test_execute_create_recipient(toolkit):
    mock_result = AsyncMock()
    mock_result.recipient_id = "rcp-1"
    mock_result.name = "John Doe"
    mock_result.account_number = "FR7630006000011234567890189"
    mock_result.country = "FRA"
    mock_result.label = None
    mock_result.created_at = "2026-04-01T10:00:00Z"

    with patch.object(toolkit._client, "create_recipient", new_callable=AsyncMock, return_value=mock_result):
        result = await toolkit.execute("create_recipient", {
            "name": "John Doe",
            "account_number": "FR7630006000011234567890189",
        })

    assert result["recipient_id"] == "rcp-1"
    assert "message" in result
    assert "status" not in result


@pytest.mark.asyncio
async def test_execute_list_recipients(toolkit):
    mock_rcp = AsyncMock()
    mock_rcp.recipient_id = "rcp-1"
    mock_rcp.name = "John Doe"
    mock_rcp.label = None
    mock_rcp.country = None

    mock_result = AsyncMock()
    mock_result.items = [mock_rcp]
    mock_result.total = 1

    with patch.object(toolkit._client, "list_recipients", new_callable=AsyncMock, return_value=mock_result):
        result = await toolkit.execute("list_recipients", {"search": "John"})

    assert result["total"] == 1
    assert len(result["recipients"]) == 1
    assert result["recipients"][0]["recipient_id"] == "rcp-1"


@pytest.mark.asyncio
async def test_execute_get_recipient(toolkit):
    mock_result = AsyncMock()
    mock_result.recipient_id = "rcp-1"
    mock_result.name = "John Doe"
    mock_result.label = "Landlord"
    mock_result.country = "FRA"

    with patch.object(toolkit._client, "get_recipient", new_callable=AsyncMock, return_value=mock_result):
        result = await toolkit.execute("get_recipient", {"recipient_id": "rcp-1"})

    assert result["recipient_id"] == "rcp-1"
    assert result["label"] == "Landlord"


@pytest.mark.asyncio
async def test_execute_get_recipient_missing_id(toolkit):
    result = await toolkit.execute("get_recipient", {})
    assert "error" in result
    assert result["error_code"] == "missing_fields"


