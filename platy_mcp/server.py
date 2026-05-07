"""Platy MCP Server entry point."""
from platy_mcp.tools import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
