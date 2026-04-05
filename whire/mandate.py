import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal


def build_payment_mandate(
    mandate_id: str,
    payment_details_id: str,
    amount: Decimal,
    label: str,
    account_id: str,
    recipient_id: str,
    merchant_agent: str,
    method_name: str = "credit_transfer",
    currency: str = "EUR",
) -> dict:
    """Build a payment mandate dict with auto-generated authorization hash."""
    contents = {
        "payment_mandate_id": mandate_id,
        "payment_details_id": payment_details_id,
        "payment_details_total": {
            "label": label,
            "amount": str(amount),
            "currency": currency,
        },
        "payment_response": {
            "request_id": payment_details_id,
            "method_name": method_name,
            "details": {
                "account_id": account_id,
                "recipient_id": recipient_id,
            },
        },
        "merchant_agent": merchant_agent,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    payload = json.dumps(contents, separators=(",", ":"), sort_keys=False)
    authorization = hashlib.sha256(payload.encode()).hexdigest()

    return {
        "payment_mandate_contents": contents,
        "user_authorization": authorization,
    }
