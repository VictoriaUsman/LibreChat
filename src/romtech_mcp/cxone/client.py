"""
CXone (NICE inContact) transport/authentication client.

This is a production library, not the discovery probe — discovery/
(repository root) exists to measure what CXone actually does and
deliberately never retries; this module encodes what discovery confirmed
(the two-call auth+discovery flow, the password-grant shape) behind a
client with the production concerns discovery explicitly left out: Key
Vault-backed credentials, transparent token renewal, bounded retries,
one-shot 401 recovery, typed errors, and safe logging.

Clock, sleep, jitter, HTTP transport, and the credential provider are all
injected so tests are deterministic and never sleep or touch a network.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Awaitable, Callable, Protocol
from urllib.parse import urlsplit

import httpx

from .config import CXoneConfig
from .credentials import CredentialProvider
from .errors import (
    AmbiguousCredentialRejectedError,
    ApiUserCredentialRejectedError,
    ApplicationCredentialRejectedError,
    AuthorizationError,
    AuthStage,
    CredentialClass,
    CXoneError,
    DeadlineExceededError,
    MalformedProtocolResponseError,
    TenantDiscoveryError,
    TerminalAuthenticationError,
    ThrottlingExhaustedError,
    TransientServerExhaustedError,
)
from .safe_logging import log_event

logger = logging.getLogger(__name__)

# Verified only against RFC 6749 §5.2's standard OAuth2 error-code
# semantics (invalid_client = client authentication, i.e. the Basic-auth
# client_id/client_secret, failed; invalid_grant = the supplied grant —
# here, the access_key_id/access_key_secret used as the password-grant
# username/password — is invalid). NOT empirically confirmed against a real
# rejection from this tenant: discovery never intentionally submitted bad
# credentials (spec explicitly says not to rotate/invalidate production
# credentials just to test negative paths). Treat as provisional until
# confirmed with a real invalid-credential test in a non-prod context.
# Anything not in this map is reported as ambiguous/unknown, never guessed.
_OAUTH_ERROR_TO_CREDENTIAL_CLASS: dict[str, CredentialClass] = {
    "invalid_client": CredentialClass.APPLICATION,
    "invalid_grant": CredentialClass.API_USER,
}

_TRANSIENT_TRANSPORT_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
)


# --------------------------------------------------------------------------
# Injected clock / sleeper / jitter
# --------------------------------------------------------------------------


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def now_utc(self) -> datetime: ...


class RealClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)


class Sleeper(Protocol):
    async def sleep(self, seconds: float) -> None: ...


class RealSleeper:
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


# A jitter function: takes no args, returns seconds to add to a backoff delay.
Jitter = Callable[[], float]


def default_jitter() -> float:
    return random.uniform(0, 1)


@dataclass
class Deadline:
    """One shared budget across an entire logical client call — vault
    access, auth, discovery, the data call, retries, and one 401-recovery
    replay all draw down the SAME deadline, not one each."""

    clock: Clock
    total_seconds: float
    _start: float = field(init=False)

    def __post_init__(self) -> None:
        self._start = self.clock.monotonic()

    def remaining(self) -> float:
        return max(self.total_seconds - (self.clock.monotonic() - self._start), 0.0)

    @property
    def expired(self) -> bool:
        return self.remaining() <= 0


# --------------------------------------------------------------------------
# Small pure helpers
# --------------------------------------------------------------------------


def _decode_jwt_payload_unverified(token: str) -> dict[str, Any]:
    """Decodes a JWT's payload without verifying its signature. Used ONLY to
    read the tenantId routing claim from a token this client itself just
    received directly from the configured, trusted token endpoint over
    TLS — never for an authorization decision, and never for a
    caller-supplied JWT. Never includes the token itself in an error."""
    parts = token.split(".")
    if len(parts) < 2:
        raise MalformedProtocolResponseError(stage=AuthStage.TOKEN_REQUEST, reason_code="id_token_not_a_jwt")
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        raise MalformedProtocolResponseError(
            stage=AuthStage.TOKEN_REQUEST, reason_code="id_token_payload_undecodable"
        ) from None


def _validate_discovered_host(url: str) -> str:
    """Confirms the discovered api_endpoint is a plain https origin — no
    embedded userinfo, query, or fragment, which could otherwise be used to
    smuggle a request somewhere the Bearer token shouldn't go. Returns the
    URL with any trailing slash stripped."""
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise MalformedProtocolResponseError(stage=AuthStage.TENANT_DISCOVERY, reason_code="non_https_api_endpoint")
    if not parsed.netloc or "@" in parsed.netloc:
        raise MalformedProtocolResponseError(stage=AuthStage.TENANT_DISCOVERY, reason_code="invalid_api_endpoint_host")
    if parsed.query or parsed.fragment:
        raise MalformedProtocolResponseError(
            stage=AuthStage.TENANT_DISCOVERY, reason_code="api_endpoint_has_query_or_fragment"
        )
    return url.rstrip("/")


def _validate_relative_path(path: str) -> None:
    """The discovered host is the only thing this client will ever send its
    Bearer token to. A caller-supplied absolute URL (or one with an
    embedded scheme/host) is refused outright rather than honored, which is
    also why redirects are disabled on the underlying HTTP client."""
    if not path.startswith("/"):
        raise ValueError("path must start with '/' — an API path, not a full URL")
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc:
        raise ValueError("path must not include a scheme or host — the API host is discovered, not caller-supplied")


def _parse_retry_after(value: str | None, *, now: datetime) -> float | None:
    """Returns seconds to wait, or None if absent/unparseable. Accepts
    either a delay-seconds integer or an HTTP-date, per RFC 9110 §10.2.3."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max((dt - now).total_seconds(), 0.0)


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------


class CXoneClient:
    def __init__(
        self,
        config: CXoneConfig,
        credential_provider: CredentialProvider,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Clock | None = None,
        sleeper: Sleeper | None = None,
        jitter: Jitter = default_jitter,
    ) -> None:
        self._config = config
        self._credentials = credential_provider
        self._clock = clock or RealClock()
        self._sleeper = sleeper or RealSleeper()
        self._jitter = jitter

        timeout = httpx.Timeout(
            connect=config.connect_timeout_seconds,
            read=config.read_timeout_seconds,
            write=config.read_timeout_seconds,
            pool=config.read_timeout_seconds,
        )
        # follow_redirects=False: a redirect to another host must never
        # carry this client's Authorization header along with it.
        self._http = httpx.AsyncClient(transport=transport, timeout=timeout, follow_redirects=False)

        self._auth_lock = asyncio.Lock()
        self._generation = 0
        self._token: str | None = None
        self._api_host: str | None = None
        self._expiry_monotonic: float | None = None

    async def __aenter__(self) -> "CXoneClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        await self._credentials.aclose()

    # -- public API ---------------------------------------------------------

    async def get(self, path: str, *, params: dict[str, str] | None = None) -> httpx.Response:
        """GETs a relative API path against the discovered CXone host,
        authenticating (or renewing) first if needed. On a 401, recovers
        exactly once per call: reuses a newer token if a concurrent caller
        already refreshed, otherwise re-authenticates and replays the
        original request once. A second 401 is terminal. 403 is never
        treated as expiry and never retried."""
        _validate_relative_path(path)
        deadline = Deadline(self._clock, self._config.total_deadline_seconds)

        token, api_host, generation = await self._ensure_auth(deadline)
        response = await self._send_authenticated(api_host, path, params, token, deadline)

        if response.status_code == 401:
            log_event(logger, logging.WARNING, "api_401_recovery_attempt", path=path, generation=generation)
            async with self._auth_lock:
                if self._generation > generation:
                    # Someone else already refreshed concurrently — reuse it,
                    # no new authentication cycle needed for this 401.
                    token, api_host = self._token, self._api_host
                else:
                    await self._authenticate(deadline)
                    token, api_host = self._token, self._api_host
            response = await self._send_authenticated(api_host, path, params, token, deadline)
            if response.status_code == 401:
                log_event(logger, logging.ERROR, "api_401_terminal", path=path)
                raise TerminalAuthenticationError()

        if response.status_code == 403:
            log_event(logger, logging.ERROR, "api_403", path=path)
            raise AuthorizationError()

        return response

    # -- authentication lifecycle --------------------------------------------

    async def _ensure_auth(self, deadline: Deadline) -> tuple[str, str, int]:
        if self._is_token_fresh():
            assert self._token is not None and self._api_host is not None
            return self._token, self._api_host, self._generation
        async with self._auth_lock:
            if self._is_token_fresh():  # recheck: another caller may have refreshed while we waited for the lock
                assert self._token is not None and self._api_host is not None
                return self._token, self._api_host, self._generation
            await self._authenticate(deadline)
            assert self._token is not None and self._api_host is not None
            return self._token, self._api_host, self._generation

    def _is_token_fresh(self) -> bool:
        if self._token is None or self._expiry_monotonic is None:
            return False
        margin = self._config.token_expiry_safety_margin_seconds
        return self._clock.monotonic() < (self._expiry_monotonic - margin)

    async def _authenticate(self, deadline: Deadline) -> None:
        """Runs the full credential->token->discovery pipeline and only
        publishes new state once ALL of it has succeeded — a partial
        failure never leaves the client with, say, a new token but the old
        (or no) api_host."""
        creds = await self._load_credentials(deadline)
        access_token, id_token, expires_in = await self._request_token(creds, deadline)
        claims = _decode_jwt_payload_unverified(id_token)
        tenant_id = claims.get("tenantId")
        if not tenant_id:
            raise MalformedProtocolResponseError(stage=AuthStage.TENANT_DISCOVERY, reason_code="missing_tenant_id")
        api_endpoint = await self._discover_api_host(tenant_id, deadline)
        api_host = _validate_discovered_host(api_endpoint)

        self._token = access_token
        self._api_host = api_host
        self._expiry_monotonic = self._clock.monotonic() + expires_in
        self._generation += 1
        log_event(logger, logging.INFO, "authenticated", generation=self._generation)

    async def _load_credentials(self, deadline: Deadline) -> dict[str, str]:
        """Key Vault access (via the injected CredentialProvider — the
        Azure SDK's own internal retries included) draws down the SAME
        overall deadline as everything else in _authenticate. The SDK
        manages its own request-level timeouts/retries internally; this
        wrapper only bounds how long this client will wait for the whole
        thing before giving up, consistent with the rest of the pipeline."""
        names = self._config.secret_names
        wanted = (
            ("client_id", names.client_id),
            ("client_secret", names.client_secret),
            ("access_key_id", names.access_key_id),
            ("access_key_secret", names.access_key_secret),
        )
        result: dict[str, str] = {}
        for logical_name, secret_name in wanted:
            remaining = deadline.remaining()
            if remaining <= 0:
                raise DeadlineExceededError(stage=AuthStage.SECRET_RETRIEVAL)
            try:
                # CredentialLoadError from the provider itself is expected
                # to propagate as-is — the provider is responsible for
                # raising it with safe fields only.
                value = await asyncio.wait_for(
                    self._credentials.get_secret(secret_name, logical_name=logical_name), timeout=remaining
                )
            except asyncio.TimeoutError:
                raise DeadlineExceededError(stage=AuthStage.SECRET_RETRIEVAL) from None
            result[logical_name] = value
        return result

    async def _request_token(self, creds: dict[str, str], deadline: Deadline) -> tuple[str, str, float]:
        async def do_request() -> httpx.Response:
            return await self._http.post(
                self._config.auth_url,
                auth=(creds["client_id"], creds["client_secret"]),
                data={
                    "grant_type": "password",
                    "username": creds["access_key_id"],
                    "password": creds["access_key_secret"],
                },
                headers={"Accept": "application/json"},
            )

        response = await self._send_with_retry(do_request, deadline=deadline, stage=AuthStage.TOKEN_REQUEST)

        if response.status_code >= 400:
            raise self._classify_auth_rejection(response)

        try:
            body = response.json()
        except ValueError:
            raise MalformedProtocolResponseError(
                stage=AuthStage.TOKEN_REQUEST, reason_code="invalid_json"
            ) from None
        if not isinstance(body, dict):
            raise MalformedProtocolResponseError(stage=AuthStage.TOKEN_REQUEST, reason_code="body_not_an_object")

        access_token = body.get("access_token")
        id_token = body.get("id_token")
        if not access_token or not isinstance(access_token, str):
            raise MalformedProtocolResponseError(stage=AuthStage.TOKEN_REQUEST, reason_code="missing_access_token")
        if not id_token or not isinstance(id_token, str):
            raise MalformedProtocolResponseError(stage=AuthStage.TOKEN_REQUEST, reason_code="missing_id_token")

        try:
            expires_in = float(body.get("expires_in"))
        except (TypeError, ValueError):
            raise MalformedProtocolResponseError(stage=AuthStage.TOKEN_REQUEST, reason_code="invalid_expires_in") from None
        if not expires_in > 0:
            raise MalformedProtocolResponseError(stage=AuthStage.TOKEN_REQUEST, reason_code="nonpositive_expires_in")

        return access_token, id_token, expires_in

    def _classify_auth_rejection(self, response: httpx.Response) -> CXoneError:
        error_code: str | None = None
        try:
            body = response.json()
            if isinstance(body, dict):
                raw = body.get("error")
                if isinstance(raw, str):
                    error_code = raw
        except ValueError:
            pass

        mapped_class = _OAUTH_ERROR_TO_CREDENTIAL_CLASS.get(error_code) if error_code else None
        if mapped_class is CredentialClass.APPLICATION:
            return ApplicationCredentialRejectedError(
                reason_code=error_code or "unknown", status_code=response.status_code
            )
        if mapped_class is CredentialClass.API_USER:
            return ApiUserCredentialRejectedError(
                reason_code=error_code or "unknown", status_code=response.status_code
            )
        # Deliberately does not guess: an error code outside the verified
        # allowlist (or no parseable code at all) is reported as ambiguous,
        # per the constraint that the client must report ambiguity rather
        # than invent a diagnosis.
        return AmbiguousCredentialRejectedError(
            reason_code=error_code or "no_error_code", status_code=response.status_code
        )

    async def _discover_api_host(self, tenant_id: str, deadline: Deadline) -> str:
        async def do_request() -> httpx.Response:
            return await self._http.get(self._config.discovery_url, params={"tenantId": tenant_id})

        response = await self._send_with_retry(do_request, deadline=deadline, stage=AuthStage.TENANT_DISCOVERY)

        if response.status_code >= 400:
            raise TenantDiscoveryError(reason_code="discovery_rejected", status_code=response.status_code)

        try:
            body = response.json()
        except ValueError:
            raise MalformedProtocolResponseError(
                stage=AuthStage.TENANT_DISCOVERY, reason_code="invalid_json"
            ) from None
        if not isinstance(body, dict):
            raise MalformedProtocolResponseError(stage=AuthStage.TENANT_DISCOVERY, reason_code="body_not_an_object")

        api_endpoint = body.get("api_endpoint")
        if not api_endpoint or not isinstance(api_endpoint, str):
            raise MalformedProtocolResponseError(stage=AuthStage.TENANT_DISCOVERY, reason_code="missing_api_endpoint")
        return api_endpoint

    async def _send_authenticated(
        self, api_host: str, path: str, params: dict[str, str] | None, token: str, deadline: Deadline
    ) -> httpx.Response:
        url = f"{api_host}{path}"

        async def do_request() -> httpx.Response:
            return await self._http.get(url, params=params, headers={"Authorization": f"Bearer {token}"})

        return await self._send_with_retry(do_request, deadline=deadline, stage=AuthStage.API_REQUEST)

    # -- bounded retry --------------------------------------------------------

    async def _send_with_retry(
        self,
        do_request: Callable[[], Awaitable[httpx.Response]],
        *,
        deadline: Deadline,
        stage: AuthStage,
    ) -> httpx.Response:
        """The one retry owner for every HTTP operation this client makes —
        token, discovery, and API calls alike. Retries 429/5xx/transient
        network errors up to retry.max_attempts (including the initial
        attempt); does not retry a permanent 4xx credential rejection
        (that's handled by the caller inspecting the returned response,
        e.g. _classify_auth_rejection), 401, or 403."""
        attempt = 0
        max_attempts = self._config.retry.max_attempts
        while True:
            attempt += 1
            if deadline.expired:
                raise DeadlineExceededError(stage=stage, attempt_count=attempt - 1)
            try:
                response = await do_request()
            except _TRANSIENT_TRANSPORT_EXCEPTIONS:
                if attempt >= max_attempts:
                    log_event(
                        logger, logging.ERROR, "network_error_exhausted", stage=stage.value, attempt_count=attempt
                    )
                    raise TransientServerExhaustedError(
                        stage=stage, reason_code="network_error", attempt_count=attempt
                    ) from None
                log_event(logger, logging.WARNING, "network_error_retrying", stage=stage.value, attempt_count=attempt)
                await self._backoff_sleep(attempt=attempt, deadline=deadline, retry_after=None, stage=stage)
                continue

            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= max_attempts:
                    log_event(
                        logger,
                        logging.ERROR,
                        "transient_status_exhausted",
                        stage=stage.value,
                        status_code=response.status_code,
                        attempt_count=attempt,
                    )
                    if response.status_code == 429:
                        raise ThrottlingExhaustedError(
                            stage=stage, reason_code="retries_exhausted", attempt_count=attempt
                        )
                    raise TransientServerExhaustedError(
                        stage=stage,
                        reason_code="retries_exhausted",
                        status_code=response.status_code,
                        attempt_count=attempt,
                    )
                log_event(
                    logger,
                    logging.WARNING,
                    "transient_status_retrying",
                    stage=stage.value,
                    status_code=response.status_code,
                    attempt_count=attempt,
                )
                retry_after = _parse_retry_after(response.headers.get("retry-after"), now=self._clock.now_utc())
                await self._backoff_sleep(attempt=attempt, deadline=deadline, retry_after=retry_after, stage=stage)
                continue

            return response

    async def _backoff_sleep(
        self, *, attempt: int, deadline: Deadline, retry_after: float | None, stage: AuthStage
    ) -> None:
        if retry_after is not None:
            delay = retry_after
        else:
            policy = self._config.retry
            delay = min(policy.base_delay_seconds * (2 ** (attempt - 1)), policy.max_delay_seconds)
            delay += self._jitter()

        remaining = deadline.remaining()
        if delay > remaining:
            # Honor Retry-After / backoff faithfully, or not at all — never
            # sleep a truncated amount and then still fail past deadline.
            raise DeadlineExceededError(stage=stage, attempt_count=attempt)
        await self._sleeper.sleep(delay)
