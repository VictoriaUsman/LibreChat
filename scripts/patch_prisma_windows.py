"""
Applies a Windows-specific fix to Prisma's query engine subprocess spawning.

Run this once after initial setup, and again after any:
  pip install --upgrade litellm

Root cause
----------
Prisma's Rust query engine binary triggers a CTRL_C_EVENT when it starts on
Windows. Because Python spawns it without console group isolation, the event
propagates to the parent process. Uvicorn captures it as SIGINT and replays it
on shutdown — crashing LiteLLM immediately after "Uvicorn running on :4000".

Fix
---
Spawn the Prisma engine with CREATE_NEW_PROCESS_GROUP so it is isolated from
the parent's Windows console group. The CTRL_C_EVENT no longer reaches Python.

This is a targeted, idempotent patch — safe to run multiple times.
"""
import sys
import importlib.util

if sys.platform != 'win32':
    print("Not Windows — no patch needed.")
    sys.exit(0)

spec = importlib.util.find_spec('prisma.engine._query')
if spec is None:
    print("ERROR: prisma package not found. Install litellm[proxy] first.")
    sys.exit(1)

path = spec.origin
print(f"Target: {path}")

with open(path, encoding='utf-8') as f:
    content = f.read()

PATCHED_MARKER = 'CREATE_NEW_PROCESS_GROUP'
if PATCHED_MARKER in content:
    print("Patch already applied — nothing to do.")
    sys.exit(0)

OLD = (
    "        if platform.name() != 'windows':\n"
    "            # ensure SIGINT is unblocked before forking the query engine\n"
    "            # https://github.com/RobertCraigie/prisma-client-py/pull/678\n"
    "            popen_kwargs['preexec_fn'] = lambda: signal.pthread_sigmask(\n"
    "                signal.SIG_UNBLOCK, [signal.SIGINT, signal.SIGTERM]\n"
    "            )"
)

NEW = (
    "        if platform.name() != 'windows':\n"
    "            # ensure SIGINT is unblocked before forking the query engine\n"
    "            # https://github.com/RobertCraigie/prisma-client-py/pull/678\n"
    "            popen_kwargs['preexec_fn'] = lambda: signal.pthread_sigmask(\n"
    "                signal.SIG_UNBLOCK, [signal.SIGINT, signal.SIGTERM]\n"
    "            )\n"
    "        else:\n"
    "            # Isolate the query engine from the parent's Windows console group.\n"
    "            # Without this the Rust binary triggers a CTRL_C_EVENT on startup\n"
    "            # that propagates to the parent Python process, causing uvicorn to\n"
    "            # capture and replay it as SIGINT — crashing the server immediately.\n"
    "            popen_kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP"
)

if OLD not in content:
    print("ERROR: Expected code block not found — Prisma version may have changed.")
    print("Inspect the file manually and update OLD in this script to match.")
    sys.exit(1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content.replace(OLD, NEW))

print("Patch applied successfully.")
