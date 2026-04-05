"""Agent tool definitions for the Whire Payments SDK."""

TOOL_CREATE_RECIPIENT = {
    "name": "create_recipient",
    "description": (
        "Create a payment recipient to store their bank details securely. "
        "You must create a recipient before sending them a payment or "
        "setting up a direct debit mandate. Returns a recipient_id to use "
        "in subsequent operations."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Recipient's full legal name.",
            },
            "account_number": {
                "type": "string",
                "description": "Recipient's bank account number.",
            },
            "country": {
                "type": "string",
                "description": "Optional 3-letter country code (e.g. 'FRA', 'DEU', 'ESP').",
            },
            "label": {
                "type": "string",
                "description": "Optional label for your reference (e.g. 'Landlord', 'Supplier').",
            },
        },
        "required": ["name", "account_number"],
    },
}

TOOL_LIST_RECIPIENTS = {
    "name": "list_recipients",
    "description": (
        "List or search saved recipients. "
        "Use this to find an existing recipient before sending a payment "
        "or creating a mandate."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "search": {
                "type": "string",
                "description": "Optional search query to filter recipients by name.",
            },
            "offset": {
                "type": "integer",
                "description": "Pagination offset (default 0).",
            },
            "limit": {
                "type": "integer",
                "description": "Number of results to return (default 20, max 100).",
            },
        },
        "required": [],
    },
}

TOOL_GET_RECIPIENT = {
    "name": "get_recipient",
    "description": (
        "Get details for a single recipient by ID."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "recipient_id": {
                "type": "string",
                "description": "The recipient's ID.",
            },
        },
        "required": ["recipient_id"],
    },
}

TOOL_SEND_PAYMENT = {
    "name": "send_payment",
    "description": (
        "Send an instant payment to a recipient. "
        "Requires a recipient_id from create_recipient. "
        "Returns a payment result with a consent_url that MUST be presented "
        "to the user for approval before the transfer is finalized. "
        "The user must open the consent_url and approve the payment."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "recipient_id": {
                "type": "string",
                "description": "ID of the recipient (from create_recipient).",
            },
            "amount": {
                "type": "string",
                "description": "Amount to send (e.g. '50.00'). Must be a positive decimal.",
            },
            "label": {
                "type": "string",
                "description": "Description shown on both sender's and recipient's bank statement.",
            },
            "idempotency_key": {
                "type": "string",
                "description": "Optional unique key to prevent duplicate payments on retry.",
            },
        },
        "required": ["recipient_id", "amount", "label"],
    },
}

TOOL_GET_PAYMENT_STATUS = {
    "name": "get_payment_status",
    "description": (
        "Check the current status of a previously initiated payment. "
        "Use this after sending a payment to verify if the user has completed "
        "consent and whether the payment has settled. "
        "Common statuses: ConsentPending (waiting for user approval), "
        "Initiated (processing), Booked (settled), Rejected."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "payment_id": {
                "type": "string",
                "description": "The transaction_id returned from send_payment.",
            },
        },
        "required": ["payment_id"],
    },
}

TOOL_GET_BALANCE = {
    "name": "get_balance",
    "description": (
        "Check the available and booked balance of the account. "
        "Use this before initiating a payment to verify sufficient funds. "
        "'available' is what can be spent now. "
        "'booked' includes pending transactions."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

TOOL_GET_TRANSACTIONS = {
    "name": "get_transactions",
    "description": (
        "Get recent transactions for the account. "
        "Returns a list of transactions with type, amount, status, and timestamp. "
        "Use this to show payment history or verify a specific transaction."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Number of transactions to return (default 20, max 100).",
            },
        },
        "required": [],
    },
}

TOOL_CREATE_MANDATE = {
    "name": "create_mandate",
    "description": (
        "Create a direct debit mandate to allow recurring debits from a customer. "
        "Requires a recipient_id from create_recipient. "
        "Once created, you can pull payments without requiring user approval each time. "
        "The mandate goes live immediately (status: Enabled). "
        "Use this for subscriptions or recurring billing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "recipient_id": {
                "type": "string",
                "description": "ID of the recipient to debit from (from create_recipient).",
            },
            "sequence": {
                "type": "string",
                "enum": ["Recurrent", "OneOff"],
                "description": "Whether this mandate is for recurring debits or a single one-time debit. Default: 'Recurrent'.",
            },
        },
        "required": ["recipient_id"],
    },
}

TOOL_DEBIT_PAYMENT = {
    "name": "debit_payment",
    "description": (
        "Pull money from a customer's account using an existing mandate. "
        "No additional authorization is required — the mandate already authorizes the debit. "
        "Settlement takes 1-2 business days (not instant). "
        "You must have a valid mandate_id from create_mandate."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mandate_id": {
                "type": "string",
                "description": "The mandate ID returned from create_mandate.",
            },
            "amount": {
                "type": "string",
                "description": "Amount to debit (e.g. '25.00').",
            },
            "label": {
                "type": "string",
                "description": "Description shown on the customer's bank statement.",
            },
            "reference": {
                "type": "string",
                "description": "Optional internal reference (e.g. invoice ID).",
            },
        },
        "required": ["mandate_id", "amount", "label"],
    },
}

ALL_TOOLS = [
    TOOL_CREATE_RECIPIENT,
    TOOL_LIST_RECIPIENTS,
    TOOL_GET_RECIPIENT,
    TOOL_SEND_PAYMENT,
    TOOL_GET_PAYMENT_STATUS,
    TOOL_GET_BALANCE,
    TOOL_GET_TRANSACTIONS,
    TOOL_CREATE_MANDATE,
    TOOL_DEBIT_PAYMENT,
]
