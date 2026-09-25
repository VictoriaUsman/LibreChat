"""
Pure client-side skill scoping.

Discovery confirmed the reporting endpoint ignores skillId/skillIds/
skillNumber query parameters entirely — the server returns every skill's
row regardless of what's asked for. Client-side, post-fetch filtering by
confirmed ID is therefore the ONLY scoping mechanism; nothing here ever
sends those parameters expecting the server to filter.

Team-based scoping is a hard, explicit block, not a silent no-op: this
endpoint's rows carry no team attribution field at all, so select_scope
raises UnsupportedTeamScopeError rather than quietly applying only the
skill filter while a configured team filter goes unhonored.

No network calls, no clock, no I/O — select_scope is a pure function over
already-fetched rows so it's trivially testable and reusable for both live
and historical fetches.
"""

from __future__ import annotations

from .models import CoverageState, NormalizedRow, ScopeConfig, ScopedObservations


class UnsupportedTeamScopeError(RuntimeError):
    """Raised when ScopeConfig.team_ids is non-empty. This endpoint's rows
    carry no team attribution field at all (confirmed by discovery) — there
    is no way for select_scope to honor a team filter, correctly or
    approximately. Silently applying only the skill-ID filter and ignoring
    team_ids would make every metric derived from the result look like it
    respected the configured scope when it didn't; this blocks instead."""


def select_scope(
    rows: list[NormalizedRow], scope: ScopeConfig, *, source_coverage: CoverageState,
    source_endpoint_path: str, source_api_version: str,
) -> ScopedObservations:
    """Applies `scope`'s included/excluded skill IDs to already-fetched
    rows. An empty `included_skill_ids` means "no inclusion filter" (every
    non-excluded, attributable row is in scope) — whether that's actually
    an acceptable state for an acceptance-grade run is a separate decision
    enforced by MappingConfig.assert_ready_for_acceptance, not by this pure
    function, which must behave predictably regardless of confirmation
    status so it stays usable for exploratory work too.

    Raises UnsupportedTeamScopeError if `scope.team_ids` is set — see that
    class's docstring. Get team data from a verified alternative source, or
    mark the dependent metric(s) unsupported, before calling this with a
    team-scoped configuration.

    `source_endpoint_path`/`source_api_version` identify which endpoint the
    given `rows` actually came from — carried onto the result so
    derive_metric can refuse a formula component that names a different
    endpoint/version instead of silently reading it from the wrong source.
    """
    if scope.team_ids:
        raise UnsupportedTeamScopeError(
            f"ScopeConfig.team_ids={list(scope.team_ids)!r} is set, but this endpoint's rows carry no team "
            "attribution — team-based scoping is not supported by select_scope."
        )

    requested_ids = frozenset(scope.included_skill_ids)
    excluded_set = frozenset(scope.excluded_skill_ids)

    seen_counts: dict[str, int] = {}
    duplicate_ids: set[str] = set()
    returned_ids: set[str] = set()
    included_ids: set[str] = set()
    excluded_ids: set[str] = set()
    included_rows: list[NormalizedRow] = []

    for row in rows:
        if row.skill_id is None:
            # Unattributable row: never silently counted as in-scope, and
            # not counted toward returned_ids either — it proves nothing
            # about which requested skill IDs actually came back.
            continue
        returned_ids.add(row.skill_id)
        seen_counts[row.skill_id] = seen_counts.get(row.skill_id, 0) + 1
        is_duplicate = seen_counts[row.skill_id] > 1
        if is_duplicate:
            duplicate_ids.add(row.skill_id)

        if row.skill_id in excluded_set:
            excluded_ids.add(row.skill_id)
            continue
        if requested_ids and row.skill_id not in requested_ids:
            continue  # never requested at all — out of scope, not "excluded"
        included_ids.add(row.skill_id)
        if not is_duplicate:
            # Only the first occurrence is kept for calculation — a caller
            # summing `rows` never silently double-counts a join-expanded
            # or otherwise duplicated skill ID. `duplicate_ids` still
            # records that it happened so it isn't invisible either.
            included_rows.append(row)

    missing_ids = requested_ids - returned_ids if requested_ids else frozenset()

    coverage = source_coverage
    if coverage == CoverageState.COMPLETE and (missing_ids or duplicate_ids):
        # A duplicate skill ID is untrustworthy even if only one occurrence
        # is kept for calculation: two rows for "the same" skill (e.g. 10
        # vs. 999) mean the response itself is internally inconsistent —
        # arbitrarily picking the first value and reporting it as if scope
        # were clean would let a conflicting/duplicated response silently
        # produce a "valid" (and possibly coincidentally matching) result.
        coverage = CoverageState.PARTIAL

    return ScopedObservations(
        requested_ids=requested_ids,
        returned_ids=frozenset(returned_ids),
        included_ids=frozenset(included_ids),
        excluded_ids=frozenset(excluded_ids),
        missing_ids=frozenset(missing_ids),
        duplicate_ids=frozenset(duplicate_ids),
        rows=included_rows,
        coverage=coverage,
        source_endpoint_path=source_endpoint_path,
        source_api_version=source_api_version,
    )
