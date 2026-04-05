"""Tests for MCP server request handling."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from whire import __version__
from whire.mcp_server import handle_request
from whire.toolkit import WhireToolkit


@pytest.fixture
def toolkit():
    return WhireToolkit(
        api_key="test-key",
        custom_base_url="http://localhost:8000",
    )


@pytest.mark.asyncio
async def test_initialize(toolkit):
    response = await handle_request(toolkit, {"method": "initialize", "id": 1})
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    result = response["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "whire-payments"
    assert result["serverInfo"]["version"] == __version__
    assert "tools" in result["capabilities"]


@pytest.mark.asyncio
async def test_initialized_notification(toolkit):
    response = await handle_request(toolkit, {"method": "notifications/initialized", "id": None})
    assert response is None


@pytest.mark.asyncio
async def test_tools_list(toolkit):
    response = await handle_request(toolkit, {"method": "tools/list", "id": 2})
    assert response["id"] == 2
    tools = response["result"]["tools"]
    assert len(tools) == 9
    names = {t["name"] for t in tools}
    assert "send_payment" in names
    assert "get_balance" in names
    assert "create_mandate" in names
    assert "create_recipient" in names
    assert "list_recipients" in names
    assert "get_recipient" in names
    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool


@pytest.mark.asyncio
async def test_tools_call(toolkit):
    mock_result = {"status": "approved", "transaction_id": "txn-1"}
    with patch.object(toolkit, "execute", new_callable=AsyncMock, return_value=mock_result):
        response = await handle_request(toolkit, {
            "method": "tools/call",
            "id": 3,
            "params": {
                "name": "send_payment",
                "arguments": {"recipient_id": "rcp-123", "amount": "10", "label": "X"},
            },
        })

    assert response["id"] == 3
    content = response["result"]["content"]
    assert len(content) == 1
    assert content[0]["type"] == "text"
    parsed = json.loads(content[0]["text"])
    assert parsed["status"] == "approved"


@pytest.mark.asyncio
async def test_tools_call_empty_params(toolkit):
    mock_result = {"available": "100.00", "booked": "100.00", "currency": "EUR"}
    with patch.object(toolkit, "execute", new_callable=AsyncMock, return_value=mock_result):
        response = await handle_request(toolkit, {
            "method": "tools/call",
            "id": 4,
            "params": {"name": "get_balance", "arguments": {}},
        })

    content = response["result"]["content"]
    parsed = json.loads(content[0]["text"])
    assert parsed["available"] == "100.00"


@pytest.mark.asyncio
async def test_unknown_method(toolkit):
    response = await handle_request(toolkit, {"method": "unknown/method", "id": 5})
    assert response["id"] == 5
    assert "error" in response
    assert response["error"]["code"] == -32601
    assert "unknown/method" in response["error"]["message"]


@pytest.mark.asyncio
async def test_missing_method(toolkit):
    response = await handle_request(toolkit, {"id": 6})
    assert response["id"] == 6
    assert "error" in response


@pytest.mark.asyncio
async def test_tools_call_missing_params(toolkit):
    """tools/call with no params still works (empty arguments)."""
    mock_result = {"error": "Missing required parameter: payment_id", "error_code": "missing_fields"}
    with patch.object(toolkit, "execute", new_callable=AsyncMock, return_value=mock_result):
        response = await handle_request(toolkit, {
            "method": "tools/call",
            "id": 7,
            "params": {"name": "get_payment_status"},
        })

    content = response["result"]["content"]
    parsed = json.loads(content[0]["text"])
    assert "error" in parsed
