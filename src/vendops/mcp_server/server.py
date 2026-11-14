"""VendOps ERP MCP Server implementation using official Python MCP SDK v2.x."""

import argparse
import asyncio
from typing import Any

from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette

from vendops.erp.seed import seed_database
from vendops.mcp_server.tools_read import (
    get_grn,
    get_invoice,
    get_payment_status,
    get_purchase_order,
    get_vendor,
)
from vendops.mcp_server.tools_write import execute_resolution


def create_mcp_server(name: str = "vendops-erp") -> MCPServer:
    """Create and configure the VendOps ERP MCPServer instance."""
    mcp_server = MCPServer(name)

    # Register all read tools
    mcp_server.add_tool(
        get_invoice,
        name="get_invoice",
        description="Fetch invoice details and line items by canonical Invoice ID (INV-XXXXXXXX).",
    )
    mcp_server.add_tool(
        get_purchase_order,
        name="get_purchase_order",
        description="Fetch purchase order details and line items by canonical PO ID (PO-XXXXXXXX).",
    )
    mcp_server.add_tool(
        get_grn,
        name="get_grn",
        description="Fetch goods receipt note and line items by canonical GRN ID (GRN-XXXXXXXX).",
    )
    mcp_server.add_tool(
        get_vendor,
        name="get_vendor",
        description="Fetch vendor master profile by canonical Vendor ID (VND-XXXXXX).",
    )
    mcp_server.add_tool(
        get_payment_status,
        name="get_payment_status",
        description="Fetch payment status and reference for an invoice ID (INV-XXXXXXXX).",
    )

    # Register write tool
    mcp_server.add_tool(
        execute_resolution,
        name="execute_resolution",
        description=(
            "Execute an automated dispute resolution action in the ERP. "
            "Action must strictly be one of: CREDIT_NOTE, REPLACEMENT, "
            "PARTIAL_PAYMENT, RELEASE_PAYMENT, REJECT, ESCALATE. "
            "Requires unique client-provided idempotency_key."
        ),
    )

    return mcp_server


# Default server instance
server: MCPServer = create_mcp_server("vendops-erp")


async def run_stdio_async() -> None:
    """Run the MCP server over stdio transport."""
    await server.run_stdio_async()


def streamable_http_app(*args: Any, **kwargs: Any) -> Starlette:
    """Return the Starlette ASGI app for HTTP streamable transport."""
    return server.streamable_http_app(*args, **kwargs)


def main() -> None:
    """CLI entrypoint for running the VendOps ERP MCP server."""
    parser = argparse.ArgumentParser(description="VendOps ERP MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport protocol (stdio or http)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="HTTP port (default: 8000)",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Seed the database before starting",
    )
    args = parser.parse_args()

    if args.seed:
        seed_database()

    if args.transport == "stdio":
        asyncio.run(run_stdio_async())
    elif args.transport == "http":
        import uvicorn

        app = streamable_http_app(host=args.host)
        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
