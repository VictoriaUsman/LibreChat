"""
Live Contact History source for the PBI-04 reconciliation (read-only `GET /contacts`).

Reuses PBI-02's `CXoneClient` for authentication, bounded retry/backoff, the shared deadline and the
host-pinning/redirect rules; there is no second retry loop here. This module owns only:

  - the verified request/response contract (observed live 2026-10-06, see the constant below);
  - paging with validation (stable total, row count equals total, bounded pages, no repeated IDs);
  - turning a page set into an `ApiContactFetch` whose COMPLETE coverage is DERIVED from what the fetch
    actually did, never from a caller-supplied label.

Any failure (outage, deadline, auth, malformed page, unstable total, count mismatch, repeated ID, page limit)
yields coverage UNKNOWN with the reasons in `provenance.issues`; the comparison then reports UNRESOLVED. A subset
is never presented as complete, and zero returned rows are not proof that the day had no contacts.

Not established by this module (recorded in the provenance, not assumed): whether `startDate`/`endDate` select
contacts by start time or by completion time. The comparison treats the fetched set as "contacts the API
returned for this window", which equals "contacts that started in the window" only if that is confirmed.

Nothing here logs or stores a credential, header, raw response body or customer field; only counts, bounds and
the three fields the comparison needs (contact ID, skill ID, start time) are read from each row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from romtech_mcp.cxone.errors import CXoneError

from .contact_history_reconcile import ApiContact, ApiContactFetch, FetchProvenance
from .models import CoverageState

CONTRACT_VERSION = "contacts-v27.0-observed-2026-10-06"


@dataclass(frozen=True)
class ContactEndpointContract:
    """The request/response shape observed live against the ROMTECH tenant (docs/evidence/pbi-04/
    live-comparison-2026-10-06.md). Changing any value means the contract must be re-verified."""

    api_version: str = "v27.0"
    path: str = "/contacts"
    array_key: str = "contacts"
    total_key: str = "totalRecords"
    id_field: str = "contactId"
    skill_id_field: str = "skillId"
    start_field: str = "contactStartDate"
    param_start: str = "startDate"
    param_end: str = "endDate"
    param_top: str = "top"
    param_skip: str = "skip"
    fields: str = "contactId,skillId,contactStartDate"  # only what the comparison needs
    page_size: int = 1000
    max_pages: int = 20
    version: str = CONTRACT_VERSION
    date_filter_semantics: str = "unverified: start time vs completion time not established"

    def __post_init__(self) -> None:
        if not 1 <= self.page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")
        if self.max_pages < 1:
            raise ValueError("max_pages must be >= 1")

    @property
    def request_path(self) -> str:
        return f"/incontactapi/services/{self.api_version}{self.path}"


DEFAULT_CONTRACT = ContactEndpointContract()


def _utc_param(dt: datetime) -> str:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("window bounds must be timezone-aware")
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_start(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        return None  # a naive API timestamp is never read in a guessed zone
    return dt.astimezone(timezone.utc)


def _identifier(raw: object) -> str | None:
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, (int, str)):
        text = str(raw).strip()
        return text if text and text.isdigit() else None
    return None


async def fetch_contacts(
    client,
    window_start_utc: datetime,
    window_end_utc: datetime,
    *,
    contract: ContactEndpointContract = DEFAULT_CONTRACT,
    now_utc: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> ApiContactFetch:
    """Pages `GET /contacts` for `[window_start_utc, window_end_utc)` and returns the records with derived
    coverage and provenance. `client` is a `CXoneClient` (anything with an async `get(path, params=...)`)."""
    start_param, end_param = _utc_param(window_start_utc), _utc_param(window_end_utc)  # rejects naive bounds first
    if window_end_utc <= window_start_utc:
        raise ValueError("window end must be after window start")
    captured_at = now_utc()
    issues: list[str] = []
    pages: list[dict[str, int]] = []
    records: list[ApiContact] = []
    seen_ids: set[str] = set()
    repeated = 0
    reported_total: int | None = None
    finished = False

    for page_index in range(contract.max_pages):
        skip = page_index * contract.page_size
        params = {
            contract.param_start: start_param, contract.param_end: end_param,
            contract.param_top: str(contract.page_size), contract.param_skip: str(skip), "fields": contract.fields,
        }
        try:
            response = await client.get(contract.request_path, params=params)
        except CXoneError as exc:
            issues.append(f"fetch_failed_on_page_{page_index + 1}: {exc!r}")  # CXoneError repr is non-secret by design
            break
        except ValueError:
            issues.append("request_rejected_locally")
            break
        if response.status_code != 200:
            issues.append(f"http_status_{response.status_code}_on_page_{page_index + 1}")
            break
        try:
            body = response.json()
        except ValueError:
            issues.append(f"page_{page_index + 1}_not_json")
            break
        rows = body.get(contract.array_key) if isinstance(body, dict) else None
        total = body.get(contract.total_key) if isinstance(body, dict) else None
        if not isinstance(rows, list):
            issues.append(f"page_{page_index + 1}_missing_{contract.array_key}_array")
            break
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            issues.append(f"page_{page_index + 1}_missing_or_invalid_{contract.total_key}")
            break
        if reported_total is not None and total != reported_total:
            issues.append(f"total_changed_during_pagination ({reported_total} -> {total})")
            break
        reported_total = total
        if len(rows) > contract.page_size:
            issues.append(f"page_{page_index + 1}_larger_than_requested_page_size")
            break
        bad_rows = 0
        for row in rows:
            cid = _identifier(row.get(contract.id_field)) if isinstance(row, dict) else None
            sid = _identifier(row.get(contract.skill_id_field)) if isinstance(row, dict) else None
            start = _parse_start(row.get(contract.start_field)) if isinstance(row, dict) else None
            if cid is None or sid is None or start is None:
                bad_rows += 1  # never dropped quietly: the page set is then not complete
                continue
            if cid in seen_ids:
                repeated += 1
            seen_ids.add(cid)
            records.append(ApiContact(cid, sid, start))
        if bad_rows:
            issues.append(f"page_{page_index + 1}_has_{bad_rows}_row(s)_with_missing_or_invalid_id_skill_or_start")
        pages.append({"skip": skip, "rows": len(rows), "reported_total": total})
        if bad_rows:
            break
        collected = sum(p["rows"] for p in pages)
        if collected >= total or len(rows) < contract.page_size:
            finished = True
            break
        if not rows:
            issues.append(f"page_{page_index + 1}_empty_before_total_reached")
            break
    else:
        issues.append("page_limit_exceeded")

    collected = sum(p["rows"] for p in pages)
    if finished and reported_total is not None and collected != reported_total:
        issues.append(f"fetched_rows ({collected}) disagree with reported total ({reported_total})")
    if repeated:
        issues.append(f"{repeated} contact ID(s) returned more than once; pagination stability is not established")
    complete = finished and not issues and reported_total is not None
    return ApiContactFetch(
        records=tuple(records),
        coverage=CoverageState.COMPLETE if complete else CoverageState.UNKNOWN,
        endpoint_path=contract.request_path,
        api_version=contract.api_version,
        captured=True,
        provenance=FetchProvenance(
            contract_version=contract.version, requested_start_utc=start_param, requested_end_utc=end_param,
            captured_at_utc=_utc_param(captured_at), pages=tuple(pages),
            reported_total=reported_total, rows_fetched=collected, issues=tuple(issues),
            filter_scope="none: all contacts in the window; skill scope is applied client-side",
            date_filter_semantics=contract.date_filter_semantics,
        ),
    )
