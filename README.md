# Whire Python SDK

[![PyPI version](https://img.shields.io/pypi/v/whire.svg)](https://pypi.org/project/whire/)
[![Python Versions](https://img.shields.io/pypi/pyversions/whire.svg)](https://pypi.org/project/whire/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

The Whire Python SDK provides convenient access to the [Whire Payments API](https://docs.whire.ai) from Python applications. It includes support for instant payments, direct debit mandates, and a built-in agent toolkit for LLMs.

> **Note:** This SDK is currently in sandbox mode. All data and transactions are simulated — no real money is moved. 
> To get sandbox API keys, email [support@whire.ai](mailto:support@whire.ai).

## Requirements

- Python 3.11+

## Installation

```bash
pip install whire
```

## Environments

The SDK supports three modes of operation:

| Mode | Base URL | Use case |
|---|---|---|
| **Production** | `https://api.whire.ai` | Live payments with real money |
| **Sandbox** | `https://sandbox.whire.ai` | Testing with Whire's hosted sandbox (simulated transactions) |
| **Local** | `http://localhost:*` | Your own backend returning mock data |

### Sandbox (recommended for getting started)

Connect to Whire's hosted sandbox. Transactions are simulated — no real money moves.

```python
from whire import WhireClient, Environment

async with WhireClient(api_key="whire_sk_...", environment=Environment.SANDBOX) as client:
    result = await client.pay(...)
```

### Production

Switch to production when you're ready to move real money.

```python
async with WhireClient(api_key="whire_sk_...", environment=Environment.PRODUCTION) as client:
    result = await client.pay(...)
```

### Local development (custom backend)

Point the SDK at your own backend to test with mock data you control. The `custom_base_url` parameter accepts `localhost` and `127.0.0.1` addresses only.

```python
async with WhireClient(
    api_key="whire_sk_test",  # any valid-looking key — your backend decides auth
    custom_base_url="http://localhost:8000",
) as client:
    result = await client.pay(
        recipient_id="rcpt-mock-001",
        amount="50.00",
        label="Test payment",
    )
```

Your backend needs to implement the same REST endpoints and return the same JSON shapes. Here are the endpoints and their expected response formats:

<details>
<summary>Endpoint reference for local mock servers</summary>

**POST /recipients** — create a recipient
```json
{
  "id": "rcpt-001",
  "name": "John Doe",
  "iban": "FR7630006000011234567890189",
  "country": "FRA",
  "label": "Landlord",
  "created_at": "2025-01-15T10:30:00Z"
}
```

**GET /recipients?search=...&offset=0&limit=20** — list recipients
```json
{
  "items": [{ "id": "rcpt-001", "name": "John Doe", "iban": "FR76...", "created_at": "..." }],
  "total": 1,
  "offset": 0,
  "limit": 20
}
```

**GET /recipients/{id}** — get a single recipient (same shape as create)

**POST /payments/send** — send a payment
```json
{
  "receipt_id": "pay-001",
  "status": "completed",
  "transaction_id": "txn-001",
  "amount_charged": "50.00",
  "currency": "EUR",
  "processor_message": "Payment processed",
  "error_code": null,
  "consent_url": null,
  "processed_at": "2025-01-15T10:30:00Z"
}
```

**GET /payments/status/{id}** — payment status
```json
{
  "payment_id": "pay-001",
  "status": "completed",
  "created_at": "2025-01-15T10:30:00Z"
}
```

**GET /payments/balance** — account balance
```json
{
  "available": { "value": "1000.00", "currency": "EUR" },
  "booked": { "value": "950.00", "currency": "EUR" }
}
```

**GET /payments/transactions?limit=20** — transaction history
```json
{
  "transactions": [
    {
      "id": "txn-001",
      "type": "payment",
      "side": "debit",
      "amount": "50.00",
      "currency": "EUR",
      "label": "Invoice #42",
      "status": "completed",
      "created_at": "2025-01-15T10:30:00Z"
    }
  ]
}
```

**POST /payments/mandates** — create a mandate
```json
{
  "mandate_id": "mdt-001",
  "status": "active",
  "recipient_name": "Jane Doe",
  "recipient_iban": "DE89370400440532013000",
  "sequence": "Recurrent"
}
```

**POST /payments/debit** — collect via mandate
```json
{
  "payment_id": "dbt-001",
  "status": "pending",
  "amount": "25.00",
  "currency": "EUR",
  "label": "Monthly subscription",
  "message": "Debit initiated",
  "created_at": "2025-01-15T10:30:00Z"
}
```

</details>

## Usage

### Instant payments

```python
from whire import WhireClient, Environment

async with WhireClient(api_key="whire_sk_...", environment=Environment.SANDBOX) as client:
    # Create a recipient (stores their bank details securely)
    recipient = await client.create_recipient(
        name="John Doe",
        account_number="FR7630006000011234567890189",
    )

    # Send a payment
    result = await client.pay(
        recipient_id=recipient.recipient_id,
        amount="50.00",
        label="Invoice #42",
    )

    # The user must approve the payment by visiting the consent URL.
    if result.consent.requires_consent:
        print(f"Approve payment: {result.consent.consent_url}")

    # Poll until the payment settles.
    status = await client.get_payment_status(result.transaction_id)
```

### Balance and transaction history

```python
balance = await client.get_balance()
print(f"Available: {balance.available} {balance.available_currency}")

transactions = await client.get_transactions(limit=10)
for t in transactions.transactions:
    print(f"{t.created_at}  {t.side:>5}  {t.amount} {t.currency}  {t.label}")
```

### Recipients

```python
# Search for existing recipients
results = await client.list_recipients(search="John")
for r in results.items:
    print(f"{r.recipient_id}  {r.name}  {r.label}")

# Get a specific recipient
recipient = await client.get_recipient("a1b2c3d4-...")
```

### Direct debit

Create a recipient and mandate once, then collect payments without per-transaction approval.

```python
recipient = await client.create_recipient(
    name="Jane Doe",
    account_number="DE89370400440532013000",
    country="DEU",
)

mandate = await client.create_mandate(recipient_id=recipient.recipient_id)

debit = await client.debit(
    mandate_id=mandate.mandate_id,
    amount="25.00",
    label="Monthly subscription",
)
# Settlement takes 1-2 business days.
```

### Configuration

| Parameter | Default | Description |
|---|---|---|
| `api_key` | *required* | Your Whire API key |
| `environment` | `Environment.PRODUCTION` | `PRODUCTION` or `SANDBOX` |
| `custom_base_url` | `None` | Override for local testing (`localhost` / `127.0.0.1` only) |
| `timeout` | `30.0` | HTTP timeout in seconds |
| `max_retries` | `3` | Max retry attempts on 429 / 5xx / network errors |
| `retry_base_delay` | `0.5` | Base delay (seconds) for exponential backoff |

## AI agent toolkit

`WhireToolkit` wraps the client into a tool-calling interface compatible with OpenAI, Anthropic, and other function-calling LLMs.

```python
from whire import WhireToolkit, Environment

async with WhireToolkit(api_key="whire_sk_...", environment=Environment.SANDBOX) as toolkit:
    # Inject into your agent
    system_prompt = toolkit.system_prompt
    tools = toolkit.get_tools()

    # Execute tool calls returned by the model
    recipient = await toolkit.execute("create_recipient", {
        "name": "John Doe",
        "account_number": "FR7630006000011234567890189",
    })

    result = await toolkit.execute("send_payment", {
        "recipient_id": recipient["recipient_id"],
        "amount": "50.00",
        "label": "Invoice #42",
    })
```

### Available tools

| Tool | Description | Requires user approval | Settlement |
|---|---|---|---|
| `create_recipient` | Store recipient bank details | No | — |
| `list_recipients` | List or search recipients | No | — |
| `get_recipient` | Get recipient details | No | — |
| `send_payment` | Send an instant payment | Yes (consent URL) | Seconds |
| `get_payment_status` | Check payment status | No | — |
| `get_balance` | Check account balance | No | — |
| `get_transactions` | View transaction history | No | — |
| `create_mandate` | Create a direct debit mandate | No | — |
| `debit_payment` | Collect via an existing mandate | No | 1-2 days |

## MCP server (Claude Desktop)

The SDK ships with a built-in [MCP](https://modelcontextprotocol.io) server for Claude Desktop and other MCP-compatible clients.

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "whire": {
      "command": "python",
      "args": ["-m", "whire.mcp_server"],
      "env": {
        "WHIRE_API_KEY": "whire_sk_..."
      }
    }
  }
}
```

## Error handling

All errors inherit from `WhireError` and include structured metadata that agents can use to decide what to do next.

```python
from whire import WhireError, AuthenticationError

try:
    result = await client.pay(...)
except AuthenticationError:
    # Invalid or expired API key (HTTP 401)
    ...
except WhireError as e:
    print(e.message)       # Human-readable message
    print(e.error_code)    # Machine-readable code
    print(e.status_code)   # HTTP status code (if applicable)
    print(e.is_retryable)  # Safe to retry?
    print(e.is_input_error)    # Bad parameters — fix and retry
    print(e.needs_user_action) # User must do something (e.g. add funds)
```

### Exception types

| Exception | When |
|---|---|
| `AuthenticationError` | Invalid API key |
| `PaymentError` | Payment request fails |
| `MandateError` | Mandate operation fails |
| `ValidationError` | Invalid parameters (HTTP 422) |
| `WhireError` | Everything else |

## License

MIT
