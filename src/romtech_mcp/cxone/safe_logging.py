"""
Safe, allowlisted logging for the CXone client.

The rule this module exists to enforce: nothing that isn't on
_ALLOWED_FIELDS can be logged from this package, full stop. That is a much
stronger guarantee than "remember not to log secrets" — a caller (including
future code in this package) literally cannot pass an arbitrary field
through `log_event`; only the ~10 known-safe scalar fields below are
accepted, and a wrong key raises immediately rather than silently logging
whatever was passed.

No credentials, tokens, Authorization headers, request/response bodies,
arbitrary response headers, or raw exception text ever flow through here.
"""

from __future__ import annotations

import logging
from typing import Final

_ALLOWED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "stage",
        "reason_code",
        "status_code",
        "attempt_count",
        "credential_class",
        "logical_name",
        "secret_name",
        "method",
        "path",
        "event",
        "generation",
    }
)

# Belt-and-suspenders: only these scalar types are ever accepted as values,
# so even an allowlisted field can't smuggle a large/opaque object (like an
# httpx.Response or an SDK exception) through as its "value".
_ALLOWED_VALUE_TYPES: Final[tuple[type, ...]] = (str, int, float, bool, type(None))


def log_event(logger: logging.Logger, level: int, event: str, **fields: object) -> None:
    """Logs `event` at `level` with only allowlisted, scalar fields.

    Raises ValueError immediately (not a logging-time failure swallowed by
    the logging module) if a caller passes a field name or value type that
    isn't allowlisted — this is meant to fail loudly in tests and in
    development, not to quietly drop the unexpected field in production.
    """
    unknown = set(fields) - _ALLOWED_FIELDS
    if unknown:
        raise ValueError(f"log_event received non-allowlisted field(s): {sorted(unknown)}")
    for key, value in fields.items():
        if not isinstance(value, _ALLOWED_VALUE_TYPES):
            raise ValueError(f"log_event field {key!r} has a non-scalar value of type {type(value).__name__}")

    parts = [f"event={event}"]
    for key in sorted(fields):
        parts.append(f"{key}={fields[key]}")
    logger.log(level, " ".join(parts))
