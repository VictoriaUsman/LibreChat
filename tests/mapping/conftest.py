from __future__ import annotations

import pytest

from romtech_mcp.cxone.config import CXoneConfig, RetryPolicy, SecretNames


@pytest.fixture
def base_config() -> CXoneConfig:
    return CXoneConfig(
        vault_url="https://kv-romtech-test.vault.azure.net",
        secret_names=SecretNames(),
        total_deadline_seconds=60.0,
        token_expiry_safety_margin_seconds=30.0,
        retry=RetryPolicy(max_attempts=3, base_delay_seconds=1.0, max_delay_seconds=30.0),
    )
