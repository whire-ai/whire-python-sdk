# Local Testing Reference

This document describes the REST endpoints and JSON response shapes your local mock server needs to implement when using the `custom_base_url` parameter.

```python
from whire import WhireClient

async with WhireClient(
    api_key="whire_sk_test",
    custom_base_url="http://localhost:8000",
) as client:
    ...
```

## Endpoints

### POST /recipients — Create a recipient

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

```json
{
  "items": [{ "id": "rcpt-001", "name": "John Doe", "iban": "FR76...", "created_at": "..." }],
  "total": 1,
  "offset": 0,
  "limit": 20
}
```

### GET /recipients/{id} — Get a single recipient

Same shape as create.

### POST /payments/send — Send a payment

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

### GET /payments/status/{id} — Payment status

```json
{
  "payment_id": "pay-001",
  "status": "completed",
  "created_at": "2025-01-15T10:30:00Z"
}
```

### GET /payments/balance — Account balance

```json
{
  "available": { "value": "1000.00", "currency": "EUR" },
  "booked": { "value": "950.00", "currency": "EUR" }
}
```

### GET /payments/transactions?limit=20 — Transaction history

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

### POST /payments/mandates — Create a mandate

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
