"""
LiteLLM custom callback — usage telemetry for ROMTech Central DB (PBI-XX-BE).

Fires after every successful LiteLLM request and emits a usage payload containing:
  department, model, input_tokens, output_tokens, estimated_cost_usd, timestamp

DOES NOT capture message content — usage metadata only, per Phase 0 data
governance (Section 1.5 of Phase_0_Findings_v1_Recommendation.md).

Local mode (TELEMETRY_ENDPOINT_URL not set):
  Payload is logged to stdout. This is the Phase 0 / local validation behaviour.

Live mode (TELEMETRY_ENDPOINT_URL set):
  Payload is logged to stdout AND POSTed to the Azure Function URL.
  Switching from local to live requires only a config change (set the env var) --
  no code changes. The Azure Function and Central DB write are PBI-12-BE.

Registration:
  Start LiteLLM from the project root so this package is importable:
    litellm --config config/litellm_routing_config.yaml
  The module-level instance is registered in litellm_routing_config.yaml:
    litellm_settings:
      callbacks: ["callbacks.litellm_usage_callback.proxy_handler_instance"]

Department attribution:
  Derived from the virtual key's team_id tag (set when the key is created).
  Department-scoped keys (DEPT_*_KEY in scripts/.env) carry their team_id.
  Requests via the unscoped librechat-phase0 key report department as "unknown".
"""

import json
import logging
import os
from datetime import datetime, timezone

try:
    from litellm.integrations.custom_logger import CustomLogger
except ImportError:
    # Allow the module to be imported outside a LiteLLM environment
    # (e.g. in validate_telemetry_callback.py) without crashing.
    class CustomLogger:  # type: ignore[no-redef]
        pass

logger = logging.getLogger(__name__)

# Fields that must NEVER appear in the emitted payload.
_CONTENT_FIELDS = frozenset({"messages", "content", "prompt", "text", "response", "choices"})


class AIUsageCallback(CustomLogger):
    """
    Custom LiteLLM callback that captures per-request usage metadata.

    The payload schema is the contract for the AIUsageLog Central DB table.
    See config/ai_usage_log_schema.md for the full schema definition.
    """

    def __init__(self):
        self._endpoint = os.environ.get("TELEMETRY_ENDPOINT_URL", "").strip()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_payload(self, kwargs, response_obj, end_time):
        """
        Build the telemetry payload from LiteLLM callback arguments.

        Args:
            kwargs:       LiteLLM callback kwargs dict.
            response_obj: LiteLLM ModelResponse (or None on some error paths).
            end_time:     datetime marking request completion.

        Returns:
            dict with keys: department, model, input_tokens, output_tokens,
                            estimated_cost_usd, timestamp.
            No message content is included.
        """
        metadata = kwargs.get("metadata") or {}

        # --- Department ---
        # LiteLLM stores the virtual key's team_id under user_api_key_team_id
        # in the metadata dict injected by the proxy.
        department = (
            metadata.get("user_api_key_team_id")
            or metadata.get("team_id")
            or "unknown"
        )

        # --- Model ---
        # metadata["model_group"] is the user-facing alias (e.g. "ROMTech AI Standard").
        # kwargs["model"] may be the resolved Azure deployment name after routing;
        # prefer the alias so the payload matches what the caller requested.
        model = (
            metadata.get("model_group")
            or kwargs.get("model", "unknown")
        )

        # --- Token counts ---
        usage = getattr(response_obj, "usage", None)
        if usage is not None:
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        else:
            input_tokens = 0
            output_tokens = 0

        # --- Estimated cost ---
        # LiteLLM pre-calculates this using the input_cost_per_token /
        # output_cost_per_token values from litellm_routing_config.yaml.
        estimated_cost = float(kwargs.get("response_cost") or 0.0)

        # --- Timestamp ---
        if isinstance(end_time, datetime):
            ts = end_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        else:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        payload = {
            "department": department,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": round(estimated_cost, 8),
            "timestamp": ts,
        }

        # Safety assertion: no content fields should have leaked in.
        leaked = _CONTENT_FIELDS & set(payload.keys())
        if leaked:
            logger.error(
                "AIUsageCallback: content fields found in payload -- stripping: %s", leaked
            )
            for field in leaked:
                del payload[field]

        return payload

    def _emit(self, payload):
        """Log payload to stdout and optionally POST to the telemetry endpoint."""
        line = json.dumps(payload, separators=(",", ":"))
        print(f"[AIUsageCallback] {line}", flush=True)

        if not self._endpoint:
            return

        try:
            import requests as _requests
            r = _requests.post(
                self._endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            if r.status_code >= 400:
                logger.warning(
                    "Telemetry endpoint returned HTTP %s (non-fatal)", r.status_code
                )
        except Exception as exc:
            # Telemetry forwarding is best-effort. A failure here must never
            # interrupt the request flow.
            logger.warning("Telemetry forwarding failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # LiteLLM CustomLogger interface
    # ------------------------------------------------------------------

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        try:
            payload = self._build_payload(kwargs, response_obj, end_time)
            self._emit(payload)
        except Exception as exc:
            logger.error("AIUsageCallback.log_success_event error (non-fatal): %s", exc)

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        try:
            payload = self._build_payload(kwargs, response_obj, end_time)
            self._emit(payload)
        except Exception as exc:
            logger.error(
                "AIUsageCallback.async_log_success_event error (non-fatal): %s", exc
            )


# Module-level instance referenced in litellm_routing_config.yaml:
#   callbacks: ["callbacks.litellm_usage_callback.proxy_handler_instance"]
proxy_handler_instance = AIUsageCallback()
