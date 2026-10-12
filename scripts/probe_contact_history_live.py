"""Read-only, exploratory report/API check using the established discovery setup.

Never writes credentials, raw contact records, agent names or phone numbers.
Marker normalization is a diagnostic hypothesis, not an accepted business rule.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--discovery-dir', type=Path, required=True)
    p.add_argument('--env-file', type=Path, required=True)
    p.add_argument('--report', type=Path, action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source-timezone', default='UTC')
    p.add_argument('--window-start', default='2026-10-01T00:00:00Z')
    p.add_argument('--window-end', default='2026-10-02T00:00:00Z')
    args = p.parse_args()
    sys.path.insert(0, str(args.discovery_dir))
    from cxone_client import CXoneSession, load_config

    env = {}
    for line in args.env_file.read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            env[key.strip()] = value.strip().strip('\"\'')
    cfg = load_config(env)
    session = CXoneSession(cfg)
    auth = session.authenticate()
    start, end = args.window_start, args.window_end
    report_zone = ZoneInfo(args.source_timezone)
    url = f'{auth.resource_server_base_uri}/incontactapi/services/{cfg.api_version}/contacts'
    fields = 'contactId,masterContactId,contactStartDate,skillId,skillName,mediaTypeName,teamId,teamName,totalDurationSeconds,transferIndicatorId,transferIndicatorName'
    records, pages = [], []
    expected_total = None
    with requests.Session() as http:
        for page in range(20):
            r = http.get(url, params={'startDate': start, 'endDate': end,
                'top': 1000, 'skip': page * 1000, 'fields': fields},
                headers={'Authorization': 'Bearer ' + auth.access_token}, timeout=60,
                allow_redirects=False)
            if r.status_code != 200:
                raise RuntimeError(f'contact_fetch_http_{r.status_code}')
            body = r.json()
            rows, total = body.get('contacts'), body.get('totalRecords')
            if not isinstance(rows, list) or not isinstance(total, int):
                raise RuntimeError('unexpected_page_schema')
            if expected_total is not None and total != expected_total:
                raise RuntimeError('total_changed_during_pagination')
            expected_total = total
            pages.append({'skip':page*1000, 'rows':len(rows), 'reported_total':total})
            records.extend(rows)
            if len(rows) < 1000:
                break
        else:
            raise RuntimeError('page_limit_exceeded')
    if len(records) != expected_total:
        raise RuntimeError('fetched_count_disagrees_with_total')
    by_id = {}
    for row in records:
        key = str(row['contactId'])
        if key in by_id:
            raise RuntimeError('duplicate_API_identity_across_pages')
        by_id[key] = row

    exported, inputs = [], []
    for path in args.report:
        with path.open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        exported.extend(rows)
        inputs.append({'basename':path.name, 'sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'rows':len(rows)})
    raw_ids = {row['Contact ID'] for row in exported}
    grouped = defaultdict(list)
    for row in exported:
        grouped[row['Contact ID'].rstrip('*')].append(row)
    matched = set(grouped) & set(by_id)
    skill_bad, time_bad, team_bad = 0, 0, 0
    deltas = Counter()
    marker_transfer = Counter()
    for cid in matched:
        a = by_id[cid]
        report_rows = grouped[cid]
        if any(row['Skill'] != a['skillName'] for row in report_rows): skill_bad += 1
        api_time = datetime.fromisoformat(a['contactStartDate'].replace('Z','+00:00'))
        if api_time.tzinfo is None:
            raise RuntimeError('naive_API_timestamp')
        for row in report_rows:
            report_time = datetime.strptime(row['Start Time:'], '%m/%d/%Y %I:%M:%S %p').replace(tzinfo=report_zone)
            deltas[round((api_time-report_time).total_seconds(), 3)] += 1
        if any(abs((api_time-datetime.strptime(row['Start Time:'], '%m/%d/%Y %I:%M:%S %p').replace(tzinfo=report_zone)).total_seconds()) >= 1 for row in report_rows): time_bad += 1
        if any((row['Team'] or '') != (a.get('teamName') or '') for row in report_rows): team_bad += 1
        if any(row['Contact ID'].endswith('*') for row in report_rows):
            marker_transfer[str(a.get('transferIndicatorName'))] += 1
    skill_pairs = defaultdict(set)
    for row in records:
        skill_pairs[row['skillName']].add(str(row['skillId']))
    export_counts = Counter(next(iter(rows))['Skill'] for rows in grouped.values())
    api_counts = Counter(row['skillName'] for row in records)
    result = {
        'captured_at_utc':datetime.now(timezone.utc).isoformat(),
        'mode':'real_read_only_discovery', 'acceptance_grade':False,
        'endpoint':'/contacts', 'api_version':cfg.api_version,
        'documentation':'https://developer.niceincontact.com/api/reportingapi',
        'window_start':start,'window_end':end,'pages':pages,'inputs':inputs,
        'api_rows':len(records),'api_unique_contact_ids':len(by_id),
        'export_rows':len(exported),'export_unique_literal_ids':len(raw_ids),
        'literal_id_matches':len(raw_ids & set(by_id)),
        'diagnostic_rules':['report timestamps interpreted as ' + args.source_timezone,'trailing * removed for diagnostic comparison only','repeated export contact IDs grouped; all skill/time variants checked','timestamp differences below one second reported as precision differences, not pre-approved tolerance'],
        'normalized_export_unique_ids':len(grouped),'normalized_matches':len(matched),
        'export_only':len(set(grouped)-set(by_id)),'api_only':len(set(by_id)-set(grouped)),
        'matched_skill_name_mismatches':skill_bad,'matched_start_differences_at_least_one_second':time_bad,
        'matched_team_name_mismatches':team_bad,
        'timestamp_delta_seconds_counts':dict(deltas),
        'marked_contact_transfer_labels':dict(marker_transfer),
        'per_skill':[{'name':name,'api_skill_ids':sorted(skill_pairs[name]),'export_distinct_contacts':export_counts[name],'api_contacts':api_counts[name]} for name in sorted(set(export_counts)|set(api_counts))],
        'limitations':['No SLA/AHT/ASA/abandonment reconciliation','No production CS scope confirmation','Marker meaning, duplicate policy, timezone/window and timestamp tolerance not independently accepted','No PBI-owner scope-change approval'],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('api_rows','export_rows','normalized_export_unique_ids','normalized_matches','export_only','api_only','matched_skill_name_mismatches','matched_start_differences_at_least_one_second','matched_team_name_mismatches','marked_contact_transfer_labels')}))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('Read-only check failed: ' + type(exc).__name__,file=sys.stderr)
        raise SystemExit(2)
