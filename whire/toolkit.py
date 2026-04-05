"""Agent toolkit that wraps WhireClient into a tool-calling interface.

Usage with any LLM agent framework:

    toolkit = WhireToolkit(api_key="...", environment=Environment.PRODUCTION)

    # Get system prompt for the agent
    system_prompt = toolkit.system_prompt

    # Get tool definitions (OpenAI/Anthropic function calling format)
    tools = toolkit.get_tools()

    # Execute a tool call from the agent
    result = await toolkit.execute("send_payment", {
        "recipient_id": "rcp-123",
        "amount": "50.00",
        "label": "Invoice 42",
    })
"""

from decimal import Decimal, InvalidOperation

from whire.client import Environment, WhireClient
from whire.exceptions import WhireError
from whire.prompts import SYSTEM_PROMPT
from whire.tools import ALL_TOOLS


def _safe_decimal(value: str, field: str) -> Decimal:
    """Convert string to Decimal with a clear error message."""
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        raise WhireError(f"Invalid {field}: '{value}' is not a valid number", error_code="invalid_input")


def _require(args: dict, *keys: str) -> None:
    """Validate that required keys are present and non-empty in args."""
    for key in keys:
        if key not in args or not args[key]:
            raise WhireError(f"Missing required parameter: {key}", error_code="missing_fields")


class WhireToolkit:
    """Agent-friendly toolkit for Whire payment operations."""

    def __init__(
        self,
        api_key: str,
        environment: Environment = Environment.PRODUCTION,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_base_delay: float = 0.5,
        custom_base_url: str | None = None,
    ):
        self._client = WhireClient(
            api_key=api_key,
            environment=environment,
            timeout=timeout,
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
            custom_base_url=custom_base_url,
        )

    @property
    def system_prompt(self) -> str:
        """Return the system prompt to inject into the agent's context."""
        return SYSTEM_PROMPT

    @staticmethod
    def get_tools() -> list[dict]:
        """Return tool definitions in function calling format."""
        return [{"type": "function", "function": tool} for tool in ALL_TOOLS]

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.close()

    async def __aenter__(self) -> "WhireToolkit":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def execute(self, tool_name: str, arguments: dict) -> dict:
        """Execute a tool by name with the given arguments.

        Returns a dict the agent can reason about. On success, returns the
        result data. On failure, returns structured error info with
        error_code, retryable flag, and a suggestion for the agent.
        """
        try:
            handler = self._handlers.get(tool_name)
            if not handler:
                available = ", ".join(self._handlers.keys())
                return {
                    "error": f"Unknown tool: {tool_name}",
                    "error_code": "unknown_tool",
                    "retryable": False,
                    "suggestion": f"Available tools: {available}",
                }
            return await handler(self, arguments)
        except WhireError as e:
            return e.to_agent_dict()

    @staticmethod
    def _recipient_to_dict(r) -> dict:
        d: dict = {
            "recipient_id": r.recipient_id,
            "name": r.name,
        }
        if r.label:
            d["label"] = r.label
        if r.country:
            d["country"] = r.country
        return d

    async def _handle_create_recipient(self, args: dict) -> dict:
        _require(args, "name", "account_number")

        result = await self._client.create_recipient(
            name=args["name"],
            account_number=args["account_number"],
            country=args.get("country"),
            label=args.get("label"),
        )
        response = self._recipient_to_dict(result)
        response["message"] = (
            "Recipient created. "
            "Use this recipient_id with send_payment or create_mandate."
        )
        return response

    async def _handle_list_recipients(self, args: dict) -> dict:
        result = await self._client.list_recipients(
            search=args.get("search"),
            offset=args.get("offset", 0),
            limit=min(args.get("limit", 20), 100),
        )
        return {
            "recipients": [self._recipient_to_dict(r) for r in result.items],
            "total": result.total,
        }

    async def _handle_get_recipient(self, args: dict) -> dict:
        _require(args, "recipient_id")

        result = await self._client.get_recipient(args["recipient_id"])
        return self._recipient_to_dict(result)

    async def _handle_send_payment(self, args: dict) -> dict:
        _require(args, "recipient_id", "amount", "label")

        result = await self._client.pay(
            recipient_id=args["recipient_id"],
            amount=_safe_decimal(args["amount"], "amount"),
            label=args["label"],
            idempotency_key=args.get("idempotency_key"),
        )

        response: dict = {
            "receipt_id": result.receipt_id,
            "status": result.status,
            "transaction_id": result.transaction_id,
            "amount_charged": str(result.amount_charged) if result.amount_charged else None,
            "currency": result.currency,
            "message": result.message,
        }

        if result.error_code:
            response["error_code"] = result.error_code

        if result.consent.requires_consent:
            response["consent_url"] = result.consent.consent_url
            response["action_required"] = (
                "The user must open the consent_url to approve this payment. "
                "Present this URL to the user now. Use get_payment_status "
                "with the transaction_id to check if they have approved."
            )

        return response

    async def _handle_get_payment_status(self, args: dict) -> dict:
        _require(args, "payment_id")

        result = await self._client.get_payment_status(args["payment_id"])
        response: dict = {
            "payment_id": result.payment_id,
            "status": result.status,
        }
        if result.created_at:
            response["created_at"] = result.created_at

        status_hints = {
            "ConsentPending": "The user has not yet approved the payment. Remind them to open the consent URL.",
            "Initiated": "The payment has been approved and is being processed.",
            "Booked": "The payment has been settled successfully.",
            "Rejected": "The payment was rejected. Check the error details.",
        }
        hint = status_hints.get(result.status)
        if hint:
            response["hint"] = hint

        return response

    async def _handle_get_balance(self, args: dict) -> dict:
        result = await self._client.get_balance()
        return {
            "available": str(result.available),
            "booked": str(result.booked),
            "currency": result.available_currency,
        }

    async def _handle_get_transactions(self, args: dict) -> dict:
        limit = args.get("limit", 20)
        result = await self._client.get_transactions(limit=min(limit, 100))
        return {
            "transactions": [
                {
                    "id": t.id,
                    "type": t.type,
                    "side": t.side,
                    "amount": str(t.amount),
                    "currency": t.currency,
                    "label": t.label,
                    "status": t.status,
                    "created_at": t.created_at,
                }
                for t in result.transactions
            ],
            "count": len(result.transactions),
        }

    async def _handle_create_mandate(self, args: dict) -> dict:
        _require(args, "recipient_id")

        result = await self._client.create_mandate(
            recipient_id=args["recipient_id"],
            sequence=args.get("sequence", "Recurrent"),
        )
        return {
            "mandate_id": result.mandate_id,
            "status": result.status,
            "recipient_name": result.recipient_name,
            "sequence": result.sequence,
            "message": (
                f"Mandate created and {result.status.lower()}. "
                "You can now use debit_payment with this mandate_id."
            ),
        }

    async def _handle_debit_payment(self, args: dict) -> dict:
        _require(args, "mandate_id", "amount", "label")

        result = await self._client.debit(
            mandate_id=args["mandate_id"],
            amount=_safe_decimal(args["amount"], "amount"),
            label=args["label"],
            reference=args.get("reference"),
        )
        return {
            "payment_id": result.payment_id,
            "status": result.status,
            "amount": str(result.amount) if result.amount else None,
            "currency": result.currency,
            "label": result.label,
            "message": result.message,
        }

    _handlers = {
        "create_recipient": _handle_create_recipient,
        "list_recipients": _handle_list_recipients,
        "get_recipient": _handle_get_recipient,
        "send_payment": _handle_send_payment,
        "get_payment_status": _handle_get_payment_status,
        "get_balance": _handle_get_balance,
        "get_transactions": _handle_get_transactions,
        "create_mandate": _handle_create_mandate,
        "debit_payment": _handle_debit_payment,
    }
