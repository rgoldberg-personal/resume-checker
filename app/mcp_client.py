"""MCP client session management for the Platy MCP server.

Design notes
------------
The MCP stdio transport uses context managers (async with) to keep the
subprocess and streams alive.  We cannot simply return the session from inside
those context managers — the process would be killed when the managers exit.

Instead we run a dedicated long-lived asyncio event loop in a background thread
(one per Celery worker process).  Tool calls are dispatched into that loop via
``asyncio.run_coroutine_threadsafe``.

On worker_init we:
1. Start the background thread + event loop.
2. Launch the platy_mcp subprocess inside it and keep it alive via a never-
   completing coroutine that holds the context managers open.
3. Store the session reference in module-level ``_mcp_session``.

If anything fails the session stays None and tasks fall back to static bands.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Module-level state — one per worker process
_mcp_session: Any | None = None
_mcp_loop: asyncio.AbstractEventLoop | None = None
_mcp_thread: threading.Thread | None = None

# Event set once the session is ready (or failed)
_mcp_ready_event = threading.Event()


# ---------------------------------------------------------------------------
# Background loop management
# ---------------------------------------------------------------------------

def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Thread target: run the event loop forever."""
    asyncio.set_event_loop(loop)
    loop.run_forever()


async def _keep_session_alive(server_script: str) -> None:
    """
    Launch the MCP subprocess and hold the session open indefinitely.

    This coroutine is scheduled inside the background loop and never returns
    (it waits on an asyncio.Event that is never set).
    """
    global _mcp_session

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    # Resolve absolute path to the server script
    project_root = Path(__file__).parent.parent
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(project_root / server_script)],
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _mcp_session = session
                logger.info("Platy MCP session initialised successfully")
                _mcp_ready_event.set()

                # Park here forever — returning would close the context managers
                await asyncio.Event().wait()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Platy MCP session failed to initialise: %s", exc)
        _mcp_ready_event.set()  # unblock init_mcp_client even on failure


def init_mcp_client() -> None:
    """
    Spawn the background event loop thread and start the MCP session.

    Called once per Celery worker process (from the worker_init signal).
    Blocks for up to 10 seconds waiting for the session to be ready.
    On any failure, _mcp_session remains None → tasks use fallback bands.
    """
    global _mcp_loop, _mcp_thread

    loop = asyncio.new_event_loop()
    _mcp_loop = loop

    thread = threading.Thread(target=_run_loop, args=(loop,), daemon=True, name="mcp-loop")
    thread.start()
    _mcp_thread = thread

    asyncio.run_coroutine_threadsafe(
        _keep_session_alive("platy_mcp/server.py"),
        loop,
    )

    # Wait up to 10 s for the session to be initialised or fail
    ready = _mcp_ready_event.wait(timeout=10)
    if not ready:
        logger.warning("Platy MCP session did not initialise within timeout — using fallback")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_mcp_session() -> Any | None:
    """Return the current MCP session (None if not initialised)."""
    return _mcp_session


def set_mcp_session(session: Any) -> None:
    """Directly override the session reference (used in tests)."""
    global _mcp_session
    _mcp_session = session


async def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """
    Call a tool on the Platy MCP server (must be called from the background loop).

    Raises RuntimeError if the session is not initialised.
    """
    session = get_mcp_session()
    if session is None:
        raise RuntimeError("MCP session is not initialised")
    result = await session.call_tool(tool_name, arguments=arguments)
    return result


def call_get_salary_range(role_category: str, seniority_tier: str) -> dict:
    """
    Call the get_salary_range MCP tool and return a plain dict.

    Returns keys: min_czk, max_czk, source, year, found.
    Raises RuntimeError if the session is unavailable.
    Raises ValueError if the tool returns an unexpected payload.
    """
    session = get_mcp_session()
    if session is None:
        raise RuntimeError("MCP session is not initialised — use fallback bands")

    if _mcp_loop is None:
        raise RuntimeError("MCP background loop is not running")

    # Dispatch the async call into the background loop from the Celery worker thread
    future = asyncio.run_coroutine_threadsafe(
        _call_get_salary_range_async(session, role_category, seniority_tier),
        _mcp_loop,
    )
    # Block the Celery worker thread for up to 10 s
    result = future.result(timeout=10)
    return result


async def _call_get_salary_range_async(
    session: Any,
    role_category: str,
    seniority_tier: str,
) -> dict:
    result = await session.call_tool(
        "get_salary_range",
        arguments={"role_category": role_category, "seniority_tier": seniority_tier},
    )
    # MCP returns a CallToolResult; extract the text content
    if hasattr(result, "content") and result.content:
        import json
        item = result.content[0]
        raw = item.text if hasattr(item, "text") else str(item)
        return json.loads(raw)
    raise ValueError(f"Unexpected MCP result: {result!r}")
