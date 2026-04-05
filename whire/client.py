import asyncio
import logging
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from email.utils import parsedate_to_datetime
from enum import Enum
from urllib.parse import urlencode

import httpx
from pydantic import ValidationError as PydanticValidationError

logger = logging.getLogger("whire")

from whire.exceptions import (
    AuthenticationError,
    PaymentError,
    ValidationError,
    WhireError,
)
from whire.models import (
    BalanceResult,
    ConsentInfo,
    DebitResult,
    MandateResult,
    PaymentResult,
    PaymentStatusResult,
    RecipientListResult,
    RecipientResult,
    TransactionListResult,
    TransactionResult,
)

_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_BASE_DELAY = 0.5
_MAX_RETRY_DELAY = 60.0
_MAX_RETRIES_LIMIT = 10
_MAX_STRING_LENGTH = 256
_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _validate_amount(value: Decimal | float | str) -> Decimal:
    """Validate and convert amount to Decimal."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as e:
        raise ValidationError(f"Invalid amount: {value}") from e
    if amount <= 0:
        raise ValidationError(f"Amount must be positive, got {amount}")
    if amount.as_tuple().exponent is not None and amount.as_tuple().exponent < -2:
        raise ValidationError(f"Amount must have at most 2 decimal places, got {amount}")
    return amount


def _validate_string(value: str, field_name: str) -> str:
    """Validate a required string field is non-empty and within length limits."""
    if not value or not value.strip():
        raise ValidationError(f"{field_name} must not be empty")
    if len(value) > _MAX_STRING_LENGTH:
        raise ValidationError(f"{field_name} must be at most {_MAX_STRING_LENGTH} characters")
    return value


def _validate_id(value: str, field_name: str) -> str:
    """Validate an ID field contains only safe characters."""
    _validate_string(value, field_name)
    if not _SAFE_ID_RE.match(value):
        raise ValidationError(f"{field_name} contains invalid characters")
    return value


def _parse_retry_after(value: str | None, fallback_delay: float) -> float:
    """Parse Retry-After header values in seconds or HTTP-date format."""
    if not value:
        return fallback_delay

    try:
        delay = float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return fallback_delay
        delay = (retry_at - datetime.now(retry_at.tzinfo)).total_seconds()

    return max(delay, 0.0)


class Environment(Enum):
    """Whire API environments."""

    PRODUCTION = "https://api.whire.ai"
    SANDBOX = "https://sandbox.whire.ai"


class WhireClient:
    """Async client for the Whire Payments API.

    Use as an async context manager for proper resource cleanup:

        async with WhireClient(api_key="...") as client:
            result = await client.pay(...)

    For local testing:

        async with WhireClient(api_key="...", custom_base_url="http://localhost:8000") as client:
            ...
    """

    def __init__(
        self,
        api_key: str,
        environment: Environment = Environment.PRODUCTION,
        timeout: float = 30.0,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_base_delay: float = _DEFAULT_RETRY_BASE_DELAY,
        custom_base_url: str | None = None,
    ):
        if not api_key:
            raise ValueError("api_key is required")
        if max_retries < 0 or max_retries > _MAX_RETRIES_LIMIT:
            raise ValueError(f"max_retries must be between 0 and {_MAX_RETRIES_LIMIT}")

        if custom_base_url:
            if not custom_base_url.startswith(("http://localhost", "http://127.0.0.1")):
                raise ValueError(
                    "custom_base_url is only permitted for local testing "
                    "(must start with http://localhost or http://127.0.0.1). "
                    "For production or sandbox, use the environment parameter."
                )
            self._base_url = custom_base_url.rstrip("/")
        else:
            self._base_url = environment.value

        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._http: httpx.AsyncClient | None = None

    def __repr__(self) -> str:
        masked = self._api_key[:8] + "..." if len(self._api_key) > 8 else "***"
        return f"WhireClient(base_url={self._base_url!r}, api_key={masked!r})"

    async def _get_http(self) -> httpx.AsyncClient:
        """Get or create the persistent HTTP client."""
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=self._timeout, verify=True)
        return self._http

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    async def __aenter__(self) -> "WhireClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    def _headers(self) -> dict:
        return {
            "X-API-Key": self._api_key,
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        """Execute an HTTP request with exponential backoff retry."""
        last_error: Exception | None = None
        http = await self._get_http()

        for attempt in range(self._max_retries + 1):
            try:
                logger.debug("Request %s %s (attempt %d/%d)", method, path, attempt + 1, self._max_retries + 1)
                response = await http.request(
                    method,
                    f"{self._base_url}{path}",
                    json=json,
                    headers=self._headers(),
                )

                if response.status_code == 401:
                    logger.warning("Authentication failed for %s %s", method, path)
                    raise AuthenticationError()

                # 204 No Content (e.g. DELETE)
                if response.status_code == 204:
                    return {}

                try:
                    data = response.json()
                except ValueError as e:
                    logger.error("Non-JSON response (HTTP %d) for %s %s", response.status_code, method, path)
                    raise WhireError(
                        f"Invalid response from server (HTTP {response.status_code})",
                        status_code=response.status_code,
                        error_code="invalid_response",
                    ) from e

                if response.status_code == 422:
                    detail = data.get("detail", "Validation error")
                    raise ValidationError(str(detail))

                # Retry on 429 rate limit
                if response.status_code == 429:
                    retry_after = _parse_retry_after(
                        response.headers.get("Retry-After"),
                        self._retry_base_delay * (2 ** attempt),
                    )
                    logger.info("Rate limited on %s %s, retrying after %.1fs", method, path, retry_after)
                    if attempt < self._max_retries:
                        last_error = WhireError("Rate limited", status_code=429, error_code="rate_limited")
                        await asyncio.sleep(min(retry_after, _MAX_RETRY_DELAY))
                        continue
                    raise WhireError("Rate limited — retries exhausted", status_code=429, error_code="rate_limited")

                # Retry on 5xx
                if response.status_code >= 500:
                    error = WhireError(
                        data.get("detail", "Server error"),
                        status_code=response.status_code,
                        error_code="server_error",
                    )
                    if attempt < self._max_retries:
                        last_error = error
                        logger.info("Server error %d on %s %s, retrying", response.status_code, method, path)
                        await asyncio.sleep(min(self._retry_base_delay * (2 ** attempt), _MAX_RETRY_DELAY))
                        continue
                    raise error

                if response.status_code >= 400:
                    detail = data.get("detail", "Request failed")
                    error_code = data.get("error_code")
                    raise WhireError(str(detail), status_code=response.status_code, error_code=error_code)

                return data

            except httpx.TransportError as e:
                last_error = WhireError(str(e), error_code="network_error")
                if attempt < self._max_retries:
                    logger.info("Network error on %s %s: %s, retrying", method, path, e)
                    await asyncio.sleep(min(self._retry_base_delay * (2 ** attempt), _MAX_RETRY_DELAY))
                    continue
                raise last_error from e

        raise last_error or WhireError("Max retries exceeded", error_code="max_retries")

    # ── Recipients ──

    @staticmethod
    def _parse_recipient(data: dict) -> RecipientResult:
        return RecipientResult(
            recipient_id=data["id"],
            name=data["name"],
            account_number=data["iban"],
            country=data.get("country"),
            label=data.get("label"),
            created_at=data["created_at"],
        )

    async def create_recipient(
        self,
        name: str,
        account_number: str,
        country: str | None = None,
        label: str | None = None,
    ) -> RecipientResult:
        """Create a payment recipient.

        Args:
            name: Recipient's full legal name.
            account_number: Recipient's bank account number.
            country: Optional 3-letter country code (e.g. FRA, DEU).
            label: Optional label for your reference (e.g. 'Landlord').
        """
        _validate_string(name, "name")
        _validate_string(account_number, "account_number")

        if country is not None:
            if len(country) != 3 or not country.isalpha():
                raise ValidationError("country must be a 3-letter country code (e.g. FRA, DEU)")

        payload: dict = {
            "name": name,
            "iban": account_number,
        }
        if country:
            payload["country"] = country
        if label:
            payload["label"] = label

        data = await self._request("POST", "/recipients", json=payload)
        try:
            return self._parse_recipient(data)
        except KeyError as e:
            raise WhireError("Unexpected response format from recipient endpoint", error_code="invalid_response") from e

    async def list_recipients(
        self,
        search: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> RecipientListResult:
        """List recipients with optional search.

        Args:
            search: Optional search query to filter by name.
            offset: Pagination offset (default 0).
            limit: Number of results to return (default 20, max 100).
        """
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 100:
            raise ValidationError("limit must be an integer between 1 and 100")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValidationError("offset must be a non-negative integer")

        query: dict = {"offset": offset, "limit": limit}
        if search:
            query["search"] = search

        data = await self._request("GET", f"/recipients?{urlencode(query)}")
        try:
            return RecipientListResult(
                items=[self._parse_recipient(r) for r in data["items"]],
                total=data["total"],
                offset=data["offset"],
                limit=data["limit"],
            )
        except KeyError as e:
            raise WhireError("Unexpected response format from recipients endpoint", error_code="invalid_response") from e

    async def get_recipient(self, recipient_id: str) -> RecipientResult:
        """Get a single recipient by ID.

        Args:
            recipient_id: The recipient's ID.
        """
        _validate_id(recipient_id, "recipient_id")

        data = await self._request("GET", f"/recipients/{recipient_id}")
        try:
            return self._parse_recipient(data)
        except KeyError as e:
            raise WhireError("Unexpected response format from recipient endpoint", error_code="invalid_response") from e

    # ── Payments ──

    async def pay(
        self,
        recipient_id: str,
        amount: Decimal | float | str,
        label: str,
        idempotency_key: str | None = None,
    ) -> PaymentResult:
        """Send an instant payment to a recipient.

        Args:
            recipient_id: ID of a previously created recipient.
            amount: Amount to send (must be positive, max 2 decimal places).
            label: Description on bank statements.
            idempotency_key: Unique key to prevent duplicate payments.
        """
        validated_amount = _validate_amount(amount)
        _validate_id(recipient_id, "recipient_id")
        _validate_string(label, "label")

        payload: dict = {
            "recipient_id": recipient_id,
            "amount": str(validated_amount),
            "label": label,
        }
        if idempotency_key:
            payload["idempotency_key"] = idempotency_key

        data = await self._request("POST", "/payments/send", json=payload)
        return self._parse_payment_result(data)

    async def get_payment_status(self, payment_id: str) -> PaymentStatusResult:
        """Check the current status of a payment."""
        _validate_id(payment_id, "payment_id")
        data = await self._request("GET", f"/payments/status/{payment_id}")
        try:
            return PaymentStatusResult(**data)
        except PydanticValidationError as e:
            raise WhireError("Unexpected response format from payment status endpoint", error_code="invalid_response") from e

    async def get_balance(self) -> BalanceResult:
        """Get the available and booked balance."""
        data = await self._request("GET", "/payments/balance")
        try:
            return BalanceResult(
                available=Decimal(data["available"]["value"]),
                available_currency=data["available"]["currency"],
                booked=Decimal(data["booked"]["value"]),
                booked_currency=data["booked"]["currency"],
            )
        except (KeyError, TypeError) as e:
            raise WhireError("Unexpected response format from balance endpoint", error_code="invalid_response") from e

    async def get_transactions(self, limit: int = 20) -> TransactionListResult:
        """Get recent transactions.

        Args:
            limit: Number of transactions to return (default 20, max 100).
        """
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 100:
            raise ValidationError("limit must be an integer between 1 and 100")

        data = await self._request("GET", f"/payments/transactions?limit={limit}")
        try:
            return TransactionListResult(
                transactions=[
                    TransactionResult(
                        id=t["id"],
                        type=t["type"],
                        side=t["side"],
                        amount=Decimal(t["amount"]),
                        currency=t["currency"],
                        label=t.get("label"),
                        status=t["status"],
                        created_at=t["created_at"],
                    )
                    for t in data["transactions"]
                ]
            )
        except (KeyError, TypeError) as e:
            raise WhireError("Unexpected response format from transactions endpoint", error_code="invalid_response") from e

    # ── Direct Debit ──

    async def create_mandate(
        self,
        recipient_id: str,
        sequence: str = "Recurrent",
    ) -> MandateResult:
        """Create a direct debit mandate for recurring collections.

        Args:
            recipient_id: ID of a previously created recipient.
            sequence: 'Recurrent' for recurring debits or 'OneOff' for a single debit.
        """
        _validate_id(recipient_id, "recipient_id")

        data = await self._request("POST", "/payments/mandates", json={
            "recipient_id": recipient_id,
            "sequence": sequence,
        })

        try:
            return MandateResult(
                mandate_id=data["mandate_id"],
                status=data["status"],
                recipient_name=data["recipient_name"],
                recipient_account=data["recipient_iban"],
                sequence=data["sequence"],
            )
        except KeyError as e:
            raise WhireError("Unexpected response format from mandate endpoint", error_code="invalid_response") from e

    async def debit(
        self,
        mandate_id: str,
        amount: Decimal | float | str,
        label: str,
        reference: str | None = None,
    ) -> DebitResult:
        """Collect a payment using an existing mandate."""
        _validate_id(mandate_id, "mandate_id")
        _validate_string(label, "label")
        validated_amount = _validate_amount(amount)

        payload: dict = {
            "mandate_id": mandate_id,
            "amount": str(validated_amount),
            "label": label,
        }
        if reference:
            payload["reference"] = reference

        data = await self._request("POST", "/payments/debit", json=payload)

        try:
            return DebitResult(
                payment_id=data.get("payment_id"),
                status=data["status"],
                amount=Decimal(data["amount"]) if data.get("amount") else None,
                currency=data.get("currency", "EUR"),
                label=data["label"],
                message=data["message"],
                created_at=data["created_at"],
            )
        except KeyError as e:
            raise WhireError("Unexpected response format from debit endpoint", error_code="invalid_response") from e

    # ── Helpers ──

    @staticmethod
    def _parse_payment_result(data: dict) -> PaymentResult:
        try:
            return PaymentResult(
                receipt_id=data["receipt_id"],
                status=data["status"],
                transaction_id=data.get("transaction_id"),
                amount_charged=Decimal(data["amount_charged"]) if data.get("amount_charged") else None,
                currency=data.get("currency", "EUR"),
                message=data["processor_message"],
                error_code=data.get("error_code"),
                consent=ConsentInfo(consent_url=data.get("consent_url")),
                processed_at=data["processed_at"],
            )
        except KeyError as e:
            raise WhireError("Unexpected response format from payment endpoint", error_code="invalid_response") from e
