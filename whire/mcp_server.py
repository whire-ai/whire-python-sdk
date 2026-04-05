"""MCP (Model Context Protocol) server for Whire Payments SDK.

Run standalone:
    python -m whire.mcp_server

Or configure in Claude Desktop:
    {
        "mcpServers": {
            "whire": {
                "command": "python",
                "args": ["-m", "whire.mcp_server"],
                "env": {
                    "WHIRE_API_KEY": "your-api-key",
                    "WHIRE_ACCOUNT_ID": "your-account-id"
                }
            }
        }
    }
"""

import asyncio
import json
import os

from whire import __version__
from whire.toolkit import WhireToolkit


async def handle_request(toolkit: WhireToolkit, request: dict) -> dict:
    """Handle a single MCP JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "whire-payments",
                    "version": __version__,
                },
            },
        }

    if method == "notifications/initialized":
        return None  # type: ignore[return-value]

    if method == "tools/list":
        tools = []
        for tool_def in toolkit.get_tools():
            func = tool_def["function"]
            tools.append({
                "name": func["name"],
                "description": func["description"],
                "inputSchema": func["parameters"],
            })
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": tools},
        }

    if method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        result = await toolkit.execute(tool_name, arguments)

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2, default=str),
                    }
                ],
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


async def main() -> None:
    """Run the MCP server over stdio."""
    api_key = os.environ.get("WHIRE_API_KEY", "")

    if not api_key:
        raise ValueError("WHIRE_API_KEY environment variable is required")

    toolkit = WhireToolkit(api_key=api_key)

    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, os.fdopen(0, "rb"))

    writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
        asyncio.streams.FlowControlMixin, os.fdopen(1, "wb")
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, None, asyncio.get_event_loop())

    while True:
        try:
            header = await reader.readline()
            if not header:
                break

            header_str = header.decode().strip()
            if header_str.startswith("Content-Length:"):
                content_length = int(header_str.split(":")[1].strip())
                await reader.readline()  # empty line
                body = await reader.readexactly(content_length)
                request = json.loads(body.decode())

                response = await handle_request(toolkit, request)

                if response is not None:
                    response_body = json.dumps(response).encode()
                    response_header = f"Content-Length: {len(response_body)}\r\n\r\n"
                    writer.write(response_header.encode() + response_body)
                    await writer.drain()

        except (asyncio.IncompleteReadError, ConnectionError):
            break


if __name__ == "__main__":
    asyncio.run(main())
