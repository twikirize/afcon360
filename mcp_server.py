import os
from mcp.server.fastmcp import FastMCP
from flask import Flask
from app import create_app

# Create an MCP server
mcp = FastMCP("Afcon360")

# Lazy load flask app
_flask_app = None

def get_flask_app():
    global _flask_app
    if _flask_app is None:
        _flask_app = create_app()
    return _flask_app

@mcp.tool()
async def get_system_status() -> str:
    """Returns the status of the Afcon360 system."""
    return "Afcon360 MCP Server is running and connected to the project."

@mcp.tool()
async def list_users(limit: int = 10) -> str:
    """Lists the first few users in the system (placeholder for actual DB query)."""
    # This is where we would use the flask app's context to query the database
    # For now, returning a message
    return f"Would list up to {limit} users if DB connection was initialized."

if __name__ == "__main__":
    mcp.run(transport="stdio")
import os
from mcp.server.fastmcp import FastMCP
from flask import Flask
from app import create_app

# Create an MCP server
mcp = FastMCP("Afcon360")

# Lazy load flask app
_flask_app = None

def get_flask_app():
    global _flask_app
    if _flask_app is None:
        _flask_app = create_app()
    return _flask_app

@mcp.tool()
async def get_system_status() -> str:
    """Returns the status of the Afcon360 system."""
    return "Afcon360 MCP Server is running and connected to the project."

@mcp.tool()
async def list_users(limit: int = 10) -> str:
    """Lists the first few users in the system (placeholder for actual DB query)."""
    # This is where we would use the flask app's context to query the database
    # For now, returning a message
    return f"Would list up to {limit} users if DB connection was initialized."

if __name__ == "__main__":
    mcp.run(transport="stdio")
