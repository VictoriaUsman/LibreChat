"""
Typed, safe errors for the CXone transport/authentication client.

Every error here carries only scalar, non-secret fields (stage, reason
code, status code, attempt count, credential class). None of them ever
carry a raw exception message, response body, header value, or credential —
that discipline is what safe_logging.py's tests actually verify, but it
starts here: there is nowhere in this module a secret CAN leak from, by
construction.
"""

from __future__ import annotations

from enum import Enum


class AuthStage(str, Enum):
    SECRET_RETRIEVAL = "secret_retrieval"
    TOKEN_REQUEST = "token_request"
    TENANT_DISCOVERY = "tenant_discovery"
    API_REQUEST = "api_request"


class CredentialClass(str, Enum):
    """Which of the two credential PAIRS a rejection implicates — never
    finer-grained than that, since CXone's token endpoint authenticates the
    application (client_id/client_secret) and the API user (access key
    id/secret) together in one call; a rejection can't distinguish which
    half of a pair was wrong, only which pair."""

    APPLICATION = "application"  # CXone client_id / client_secret
    API_USER = "api_user"  # access_key_id / access_key_secret
    UNKNOWN = "unknown"  # CXone's response didn't identify which — report that honestly


class CXoneError(Exception):
    """Base class. __str__ is deliberately built only from the safe fields
    below — never from an underlying exception's message or a response
    body, so raising or logging one of these can never leak a secret."""

    def __init__(
        self,
        *,
        stage: AuthStage,
        reason_code: str,
        status_code: int | None = None,
        attempt_count: int = 1,
        credential_class: CredentialClass = CredentialClass.UNKNOWN,
    ) -> None:
        self.stage = stage
        self.reason_code = reason_code
        self.status_code = status_code
        self.attempt_count = attempt_count
        self.credential_class = credential_class
        super().__init__(self._safe_message())

    def _safe_message(self) -> str:
        return (
            f"{type(self).__name__}(stage={self.stage.value}, reason={self.reason_code}, "
            f"status={self.status_code}, credential_class={self.credential_class.value}, "
            f"attempts={self.attempt_count})"
        )

    def __repr__(self) -> str:  # match __str__ — no default Exception repr with raw args
        return self._safe_message()


class CredentialLoadError(CXoneError):
    """Key Vault / managed-identity access or secret retrieval failure.
    Carries which of the four LOGICAL credentials failed (client_id,
    client_secret, access_key_id, access_key_secret) and the non-secret
    Key Vault secret NAME involved (a config name, not a value — safe to
    log) — never the secret's value, never the SDK exception's text."""

    def __init__(self, *, logical_name: str, secret_name: str, reason_code: str, attempt_count: int = 1) -> None:
        self.logical_name = logical_name
        self.secret_name = secret_name
        super().__init__(
            stage=AuthStage.SECRET_RETRIEVAL,
            reason_code=reason_code,
            attempt_count=attempt_count,
        )

    def _safe_message(self) -> str:
        return (
            f"CredentialLoadError(logical_name={self.logical_name}, secret_name={self.secret_name}, "
            f"reason={self.reason_code}, attempts={self.attempt_count})"
        )


class ApplicationCredentialRejectedError(CXoneError):
    """The token endpoint rejected the application client_id/client_secret
    pair specifically (verified OAuth error code, see client.py's
    allowlist — never inferred from a bare 400/401)."""

    def __init__(self, *, reason_code: str, status_code: int, attempt_count: int = 1) -> None:
        super().__init__(
            stage=AuthStage.TOKEN_REQUEST,
            reason_code=reason_code,
            status_code=status_code,
            attempt_count=attempt_count,
            credential_class=CredentialClass.APPLICATION,
        )


class ApiUserCredentialRejectedError(CXoneError):
    """The token endpoint rejected the access_key_id/access_key_secret pair
    specifically (verified OAuth error code — see client.py's allowlist)."""

    def __init__(self, *, reason_code: str, status_code: int, attempt_count: int = 1) -> None:
        super().__init__(
            stage=AuthStage.TOKEN_REQUEST,
            reason_code=reason_code,
            status_code=status_code,
            attempt_count=attempt_count,
            credential_class=CredentialClass.API_USER,
        )


class AmbiguousCredentialRejectedError(CXoneError):
    """The token endpoint rejected the request, but its error code (if any)
    isn't in the verified allowlist — reported honestly as unknown rather
    than guessed. See client.py's _classify_auth_rejection."""

    def __init__(self, *, reason_code: str, status_code: int, attempt_count: int = 1) -> None:
        super().__init__(
            stage=AuthStage.TOKEN_REQUEST,
            reason_code=reason_code,
            status_code=status_code,
            attempt_count=attempt_count,
            credential_class=CredentialClass.UNKNOWN,
        )


class TenantDiscoveryError(CXoneError):
    """The tenant-configuration discovery call (GET .../cxone-configuration)
    failed or was rejected."""

    def __init__(self, *, reason_code: str, status_code: int | None = None, attempt_count: int = 1) -> None:
        super().__init__(
            stage=AuthStage.TENANT_DISCOVERY,
            reason_code=reason_code,
            status_code=status_code,
            attempt_count=attempt_count,
        )


class MalformedProtocolResponseError(CXoneError):
    """A response that should have been well-formed per the confirmed
    protocol (missing a required field, wrong type, invalid JSON, an
    invalid/insecure discovered host) wasn't. Never includes the actual
    malformed body."""

    def __init__(self, *, stage: AuthStage, reason_code: str, attempt_count: int = 1) -> None:
        super().__init__(stage=stage, reason_code=reason_code, attempt_count=attempt_count)


class ThrottlingExhaustedError(CXoneError):
    """429 retries exhausted, or a Retry-After wait would have exceeded the
    remaining deadline."""

    def __init__(self, *, stage: AuthStage, reason_code: str, status_code: int = 429, attempt_count: int = 1) -> None:
        super().__init__(stage=stage, reason_code=reason_code, status_code=status_code, attempt_count=attempt_count)


class TransientServerExhaustedError(CXoneError):
    """5xx/network-error retries exhausted."""

    def __init__(
        self, *, stage: AuthStage, reason_code: str, status_code: int | None = None, attempt_count: int = 1
    ) -> None:
        super().__init__(stage=stage, reason_code=reason_code, status_code=status_code, attempt_count=attempt_count)


class AuthorizationError(CXoneError):
    """403 from the API — never treated as token expiry, never retried."""

    def __init__(self, *, attempt_count: int = 1) -> None:
        super().__init__(
            stage=AuthStage.API_REQUEST, reason_code="forbidden", status_code=403, attempt_count=attempt_count
        )


class TerminalAuthenticationError(CXoneError):
    """A second 401 after exactly one recovery replay. Terminal — the
    caller's request fails; there is no further automatic recovery."""

    def __init__(self, *, attempt_count: int = 2) -> None:
        super().__init__(
            stage=AuthStage.API_REQUEST,
            reason_code="second_401_after_replay",
            status_code=401,
            attempt_count=attempt_count,
        )


class DeadlineExceededError(CXoneError):
    """A retry/backoff wait (including an honored Retry-After) would have
    exceeded the remaining total deadline — failed fast instead of
    sleeping past it and failing anyway."""

    def __init__(self, *, stage: AuthStage, attempt_count: int = 1) -> None:
        super().__init__(stage=stage, reason_code="deadline_exceeded", attempt_count=attempt_count)
