#!/usr/bin/env python3
"""
Launches the LiteLLM proxy via Python directly, bypassing the litellm.exe
wrapper which may be blocked by AppLocker on managed Windows machines.

Usage (from project root):
  python scripts/start_litellm.py
"""
import sys
import os

# Add project root to sys.path so 'callbacks' package is importable by LiteLLM.
# When running scripts/start_litellm.py, Python adds scripts/ to sys.path but
# not the project root, so callbacks.litellm_usage_callback can't be found.
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load scripts/.env before litellm imports so DATABASE_URL and other
# vars are in the environment when Prisma and LiteLLM read them.
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
try:
    from dotenv import load_dotenv
    load_dotenv(env_path, override=True)
except ImportError:
    pass

config_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "litellm_routing_config.yaml",
)

sys.argv = ["litellm", "--config", config_path, "--port", "4000"]

from litellm.proxy.proxy_cli import run_server
run_server()
