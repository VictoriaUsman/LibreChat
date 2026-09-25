"""
Small reporting adapter around PBI-02's CXoneClient.

Owns exactly two things: making the HTTP call (via the client — which
already owns bounded retry, 429/5xx backoff, Retry-After honoring, and a
shared deadline; this module does not reimplement any of that) and
validating + normalizing whatever comes back into models.py's typed rows.
Business semantics (scope filtering, formulas, comparisons) live in
scope.py/reconcile.py, not here.

Endpoint access and a 200 response are NOT evidence that a dashboard metric
means the same thing as an API field — this module only proves the
response's own shape is what SourceEndpointConfig claims it is.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from romtech_mcp.cxone.client import CXoneClient
from romtech_mcp.cxone.errors import CXoneError

from .models import CoverageState, NormalizedRow, ReportingWindow, SourceEndpointConfig, SourceObservation, ValidationIssue

# Field names that, if present and truthy in a response body, indicate the
# response is paginated. This endpoint's shape has NOT been confirmed to
# ever include one of these — they exist so an actual (even if unexpected)
# continuation marker is reported as unverified/incomplete coverage rather
# than silently ignored and treated as a complete fetch.
_UNVERIFIED_PAGINATION_MARKERS = ("nextLink", "continuationToken", "nextPageToken", "@odata.nextLink")


class SourceFetchError(RuntimeError):
    """Sanitized wrapper around a CXoneError raised while fetching mapping
    data. Carries only the underlying error's already-safe fields (via its
    repr — CXoneError's __repr__ is built exclusively from typed, non-secret
    fields) — never a raw response body, header, or credential."""

    def __init__(self, *, endpoint_path: str, window_label: str, cause: CXoneError) -> None:
        self.endpoint_path = endpoint_path
        self.window_label = window_label
        self.cause_repr = repr(cause)
        super().__init__(f"Fetch failed for {endpoint_path} window={window_label}: {self.cause_repr}")


def normalize_response_body(
    response_body: Any, endpoint: SourceEndpointConfig
) -> tuple[list[NormalizedRow], CoverageState, list[ValidationIssue]]:
    """The validation/normalization core, independent of how the response
    body was obtained — used by ReportingSource.fetch_window for a live
    call, and directly by offline fixture-comparison tooling (e.g.
    scripts/reconcile_dashboard.py in fixture mode) so both paths validate
    identically rather than fixture mode trusting its input blindly."""
    issues: list[ValidationIssue] = []

    if response_body is _INVALID_JSON:
        issues.append(ValidationIssue(metric_key="<source>", field="response_body", message="response body was not valid JSON"))
        return [], CoverageState.UNKNOWN, issues

    coverage = CoverageState.COMPLETE
    if isinstance(response_body, dict):
        for marker in _UNVERIFIED_PAGINATION_MARKERS:
            if response_body.get(marker):
                issues.append(
                    ValidationIssue(
                        metric_key="<source>", field=marker,
                        message=f"response contains {marker!r} — pagination is not verified/implemented for this "
                                "endpoint; coverage cannot be considered complete",
                    )
                )
                coverage = CoverageState.UNKNOWN

    if endpoint.response_array_key:
        if not isinstance(response_body, dict):
            issues.append(ValidationIssue(metric_key="<source>", field="response_body",
                                           message="expected a JSON object containing the response array key"))
            return [], CoverageState.UNKNOWN, issues
        rows_raw = response_body.get(endpoint.response_array_key)
    else:
        rows_raw = response_body

    if not isinstance(rows_raw, list):
        issues.append(
            ValidationIssue(metric_key="<source>", field=endpoint.response_array_key or "<root>",
                             message=f"expected an array, got {type(rows_raw).__name__}")
        )
        return [], CoverageState.UNKNOWN, issues

    rows: list[NormalizedRow] = []
    for i, raw_row in enumerate(rows_raw):
        if not isinstance(raw_row, dict):
            issues.append(ValidationIssue(metric_key="<source>", field=f"[{i}]",
                                           message=f"row {i} is not an object, got {type(raw_row).__name__}"))
            continue
        skill_id_raw = raw_row.get(endpoint.skill_id_field)
        skill_id = None if skill_id_raw is None else str(skill_id_raw)
        if skill_id is None:
            issues.append(
                ValidationIssue(metric_key="<source>", field=endpoint.skill_id_field,
                                 message=f"row {i} has no {endpoint.skill_id_field!r} — cannot attribute to a skill",
                                 severity="warning")
            )
        rows.append(NormalizedRow(skill_id=skill_id, raw=raw_row))

    return rows, coverage, issues


class ReportingSource:
    """Fetches and normalizes one endpoint's data for one window at a time.
    A caller wanting several windows calls fetch_window per window — this
    class does not batch or parallelize; that's a concern for whatever
    orchestrates reconciliation, not the adapter itself."""

    def __init__(
        self, client: CXoneClient, endpoint: SourceEndpointConfig, *, now_utc: Callable[[], datetime] | None = None
    ) -> None:
        self._client = client
        self._endpoint = endpoint
        self._now_utc = now_utc or (lambda: datetime.now(timezone.utc))

    async def fetch_window(self, window: ReportingWindow) -> SourceObservation:
        params = {
            self._endpoint.param_start: window.utc_start.isoformat(),
            self._endpoint.param_end: window.utc_end.isoformat(),
        }
        requested_at_utc = self._now_utc()

        try:
            # The client's own bounded retry/backoff/deadline policy governs
            # this call end to end — see CXoneClient._send_with_retry. This
            # adapter makes exactly one logical request per window; it never
            # adds a second, competing retry loop on top.
            response = await self._client.get(self._endpoint.endpoint_path, params=params)
        except CXoneError as exc:
            raise SourceFetchError(
                endpoint_path=self._endpoint.endpoint_path, window_label=window.label, cause=exc
            ) from exc

        return self._normalize(response_body=self._safe_json(response), window=window, params=params,
                                 requested_at_utc=requested_at_utc)

    @staticmethod
    def _safe_json(response: Any) -> Any:
        try:
            return response.json()
        except ValueError:
            return _INVALID_JSON

    def _normalize(
        self, *, response_body: Any, window: ReportingWindow, params: dict[str, str], requested_at_utc: datetime
    ) -> SourceObservation:
        rows, coverage, issues = normalize_response_body(response_body, self._endpoint)
        return self._observation(window, params, requested_at_utc, rows=rows, coverage=coverage, issues=issues)

    def _observation(
        self, window: ReportingWindow, params: dict[str, str], requested_at_utc: datetime, *,
        rows: list[NormalizedRow], coverage: CoverageState, issues: list[ValidationIssue],
    ) -> SourceObservation:
        return SourceObservation(
            window=window,
            endpoint_path=self._endpoint.endpoint_path,
            api_version=self._endpoint.api_version,
            request_params=params,
            requested_at_utc=requested_at_utc,
            rows=rows,
            coverage=coverage,
            issues=issues,
        )


class _InvalidJsonSentinel:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return "<invalid JSON>"


_INVALID_JSON = _InvalidJsonSentinel()
