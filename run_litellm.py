"""
Windows-compatible launcher for LiteLLM proxy.

Root cause: On Windows, uvicorn defaults to ProactorEventLoop (IOCP-based). When the
Prisma query-engine subprocess writes to its pipe during startup, the IOCP completion
fires uvicorn's SIGINT handler. uvicorn then replays the signal via signal.raise_signal()
in capture_signals.__exit__, which cancels the asyncio main task while it is still
executing — causing the immediate-exit crash seen after "Uvicorn running on...".

Fix: force WindowsSelectorEventLoopPolicy BEFORE uvicorn calls asyncio.run(), so the
select()-based loop is used instead of the IOCP-based ProactorEventLoop.
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from litellm.proxy.proxy_cli import run_server

run_server()
