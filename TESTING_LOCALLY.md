# Local Testing Reference

This document describes the REST endpoints and JSON shapes your local mock server needs to implement when using the `custom_base_url` parameter.

```python
import asyncio
from whire import WhireClient

async def main():
    async with WhireClient(
        api_key="whire_test_key",
        custom_base_url="http://localhost:8000",
    ) as client:
        ...

asyncio.run(main())
```

Auth: all requests include an `X-API-Key` header.

---

## Recipients

### POST /recipients — Create a recipient

**Request:**
```json
{
  "name": "John Doe",
  "iban": "FR7630006000011234567890189",
  "country": "FRA",
  "label": "Landlord"
}
```

**Response (201):**
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

### GET /recipients?search=...&offset=0&limit=20 — List recipients

**Response (200):**
```json
{
  "items": [
    { "id": "rcpt-001", "name": "John Doe", "iban": "FR7630006000011234567890189", "country": "FRA", "label": "Landlord", "created_at": "2025-01-15T10:30:00Z" }
  ],
  "total": 1,
  "offset": 0,
  "limit": 20
}
```

### GET /recipients/{recipient_id} — Get a single recipient

Same response shape as create.

---

## Payments

### POST /payments/send — Send a payment

**Request:**
```json
{
  "recipient_id": "rcpt-001",
  "amount": "50.00",
  "label": "Invoice #42",
  "idempotency_key": "optional-unique-key"
}
```

**Response (201):**
```json
{
  "receipt_id": "pay-001",
  "status": "approved",
  "transaction_id": "txn-001",
  "amount_charged": "50.00",
  "currency": "EUR",
  "processor_message": "Payment processed",
  "error_code": null,
  "consent_url": null,
  "processed_at": "2025-01-15T10:30:00Z"
}
```

### GET /payments/status/{payment_id} — Payment status

**Response (200):**
```json
{
  "payment_id": "pay-001",
  "status": "approved",
  "created_at": "2025-01-15T10:30:00Z"
}
```

### GET /payments/balance — Account balance

**Response (200):**
```json
{
  "available": { "value": "1000.00", "currency": "EUR" },
  "booked": { "value": "950.00", "currency": "EUR" }
}
```

### GET /payments/transactions?limit=20 — Transaction history

**Response (200):**
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
      "status": "approved",
      "created_at": "2025-01-15T10:30:00Z"
    }
  ]
}
```

### POST /payments/mandates — Create a mandate

**Request:**
```json
{
  "recipient_id": "rcpt-001",
  "sequence": "Recurrent"
}
```

**Response (201):**
```json
{
  "mandate_id": "mdt-001",
  "status": "active",
  "recipient_name": "Jane Doe",
  "recipient_iban": "DE89370400440532013000",
  "sequence": "Recurrent"
}
```

### POST /payments/debit — Collect via mandate

**Request:**
```json
{
  "mandate_id": "mdt-001",
  "amount": "25.00",
  "label": "Monthly subscription",
  "reference": "optional-reference"
}
```

**Response (201):**
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

---

## Transfers

### POST /transfers/ — Initiate a credit transfer

> **Note:** This endpoint is not yet wrapped by the SDK client. Use it directly if building a custom integration.

**Request:**
```json
{
  "account_id": "acc-001",
  "target_iban": "FR7630006000011234567890189",
  "target_name": "John Doe",
  "amount": "10.00",
  "label": "Test transfer"
}
```

**Response (201):**
```json
{
  "payment_id": "pay-002",
  "status": "approved",
  "message": "Transfer initiated"
}
```

---

## SDD (Direct Debit — low-level)

> **Note:** These low-level endpoints are not wrapped by the SDK. The SDK uses the higher-level `/payments/mandates` and `/payments/debit` endpoints instead.

### POST /sdd/mandates — Create a mandate

**Request:**
```json
{
  "debtor_name": "Jane Doe",
  "debtor_iban": "DE89370400440532013000",
  "debtor_country": "FRA",
  "sequence": "Recurrent"
}
```

**Response (201):**
```json
{
  "mandate_id": "mdt-002",
  "status": "active",
  "debtor_name": "Jane Doe",
  "debtor_iban": "DE89370400440532013000",
  "sequence": "Recurrent"
}
```

### POST /sdd/payments — Initiate a direct debit payment

**Request:**
```json
{
  "mandate_id": "mdt-002",
  "amount": "25.00",
  "label": "Monthly subscription",
  "reference": "optional-reference"
}
```

**Response (201):**
```json
{
  "payment_id": "dbt-002",
  "status": "pending",
  "amount": "25.00",
  "currency": "EUR",
  "label": "Monthly subscription",
  "message": "Debit initiated",
  "created_at": "2025-01-15T10:30:00Z"
}
```
