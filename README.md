# Whire Python SDK

[![PyPI version](https://img.shields.io/pypi/v/whire.svg)](https://pypi.org/project/whire/)
[![Python Versions](https://img.shields.io/pypi/pyversions/whire.svg)](https://pypi.org/project/whire/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

**Payment infrastructure built specifically for AI agents.**

It provides a native agent toolkit and MCP server, allowing your Agents to safely execute instant payments.

### See it in action:

![Image](https://github.com/user-attachments/assets/47c90560-783b-42ea-a645-131627e50bb6)

## Quickstart: The Magic (Sandbox Mode)

The SDK is currently in an open Sandbox. Transactions are fully mocked so you can test agentic workflows without moving real money.

> **Zero friction:** Use the public test key `whire_test_key` to try it locally right now.

### 1. Install

```bash
pip install whire
```

### 2. Run your first Agentic Payment

`WhireToolkit` wraps the client into a tool-calling interface compatible with OpenAI, Anthropic, and other function-calling LLMs.

```python
import asyncio
from whire import WhireToolkit, Environment

async def run_agent():
    # Example Prompt: "Claude, pay my €150 AWS hosting bill to Alice Martin."

    # Initialize the toolkit with our public sandbox key
    async with WhireToolkit(api_key="whire_test_key", environment=Environment.SANDBOX) as toolkit:

        # Step 1: Agent autonomously creates the recipient
        recipient = await toolkit.execute("create_recipient", {
            "name": "Alice Martin",
            "account_number": "FR7630006000011234567890189",
            "label": "AWS Supplier"
        })

        # Step 2: Agent initiates the transfer
        payment = await toolkit.execute("send_payment", {
            "recipient_id": recipient["recipient_id"],
            "amount": "150.00",
            "label": "AWS March Invoice"
        })

        # Step 3: Humans stay in the loop for security
        if payment.get("consent_url"):
            print(f"ACTION REQUIRED: Approve transfer here: {payment['consent_url']}")

if __name__ == "__main__":
    asyncio.run(run_agent())
```

## MCP Server (Claude Desktop)

Developers building on Claude Desktop can plug Whire in natively. The SDK ships with a built-in [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server.

Add this to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "whire": {
      "command": "python",
      "args": [
        "-m",
        "whire.mcp_server"
      ],
      "env": {
        "WHIRE_API_KEY": "whire_test_key"
      }
    }
  }
}
```

> **Note:** Swap the test key for your production key when moving to live environments.

## Why Whire?

If you try to let an LLM write its own REST API calls to a traditional payment gateway, it will fail. LLMs hallucinate JSON structures, fail at multi-step financial compliance, and struggle to manage API state.

Whire solves this by enforcing strict schemas, managing local state, and handling the orchestration natively. We also return structured error metadata (like `needs_user_action`) so the agent knows exactly how to recover if a payment fails.

## The Plumbing: Standard SDK Usage

For backend engineers who want to bypass the AI toolkit and use Whire as a traditional payment gateway, you can interface directly with the `WhireClient`.

### Instant Payments

```python
import asyncio
from whire import WhireClient, Environment

async def main():
    async with WhireClient(api_key="whire_test_key", environment=Environment.SANDBOX) as client:
        # 1. Create a recipient
        recipient = await client.create_recipient(
            name="John Doe",
            account_number="FR7630006000011234567890189"
        )

        # 2. Send a payment
        result = await client.pay(
            recipient_id=recipient.recipient_id,
            amount="50.00",
            label="Invoice #42"
        )

asyncio.run(main())
```

### Balances & Direct Debits

```python
# Inside an async context with an initialized client:

# Check Balance
balance = await client.get_balance()
print(f"Available: {balance.available} {balance.available_currency}")

# Create Direct Debit Mandate
mandate = await client.create_mandate(recipient_id=recipient.recipient_id)
debit = await client.debit(
    mandate_id=mandate.mandate_id,
    amount="25.00",
    label="Monthly subscription"
)
```

## Local Testing & Mock Data

If you want to point the SDK at your own local backend instead of our hosted Sandbox, you can use the `custom_base_url` parameter (restricted to `localhost` and `127.0.0.1`).

```python
async with WhireClient(api_key="whire_test_key", custom_base_url="http://localhost:8000") as client:
    pass  # Your backend handles the requests
```

For a complete reference of the required JSON shapes and REST endpoints your local server needs to mock, please read [TESTING_LOCALLY.md](TESTING_LOCALLY.md).

## License

MIT
