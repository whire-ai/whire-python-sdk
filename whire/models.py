from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ConsentInfo(BaseModel):
    """Consent URL returned when a payment requires user approval."""

    consent_url: str | None = None

    @property
    def requires_consent(self) -> bool:
        return self.consent_url is not None


class PaymentResult(BaseModel):
    """Result of an instant payment."""

    receipt_id: str
    status: str
    transaction_id: str | None = None
    amount_charged: Decimal | None = None
    currency: str = "EUR"
    message: str
    error_code: str | None = None
    consent: ConsentInfo
    processed_at: datetime


class PaymentStatusResult(BaseModel):
    """Result of checking a payment's status."""

    payment_id: str
    status: str
    created_at: str | None = None


class BalanceResult(BaseModel):
    """Account balance information."""

    available: Decimal
    available_currency: str
    booked: Decimal
    booked_currency: str


class TransactionResult(BaseModel):
    """A single transaction."""

    id: str
    type: str
    side: str
    amount: Decimal
    currency: str
    label: str | None = None
    status: str
    created_at: str


class TransactionListResult(BaseModel):
    """List of recent transactions."""

    transactions: list[TransactionResult]


class RecipientResult(BaseModel):
    """A payment recipient."""

    recipient_id: str
    name: str
    account_number: str
    country: str | None = None
    label: str | None = None
    created_at: str


class RecipientListResult(BaseModel):
    """Paginated list of recipients."""

    items: list[RecipientResult]
    total: int
    offset: int
    limit: int


class MandateResult(BaseModel):
    """Result of creating a direct debit mandate."""

    mandate_id: str
    status: str
    recipient_name: str
    recipient_account: str
    sequence: str


class DebitResult(BaseModel):
    """Result of initiating a debit collection."""

    payment_id: str | None = None
    status: str
    amount: Decimal | None = None
    currency: str = "EUR"
    label: str
    message: str
    created_at: datetime
