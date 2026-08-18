// Failure alerting for the scheduled ACA Jobs (WI 12341).
//
// Azure Monitor sends the alert email NATIVELY via an action group — no app
// SMTP and no Ops dependency. Point `alertEmailAddresses` at the inboxes/DLs we own.
//
// The alert is a Log Analytics scheduled query rule over the jobs' console logs.
// VALIDATED IN DEV 2026-07-22 against a real forced failure: table is
// ContainerAppConsoleLogs_CL and jobs are scoped by ContainerGroupName_s (jobs
// leave ContainerAppName_s empty). The rule evaluates hourly, so the email lands
// within ~1h of a failure (not instantly, unlike the action-group Test button).
//
// COVERAGE / KNOWN GAP: this query keys on the jobs' own stdout, so it catches
// every *handled* failure (both scripts log `[ERROR]` before a non-zero exit; the
// sync job also emits `SYNC_SUMMARY status=failed`) plus escaped exceptions
// (`Traceback`). It does NOT catch failures that produce no stdout — OOM kills,
// image-pull failures, or a replica killed at `replicaTimeout` before it logs.
// Closing that requires a control-plane signal. Build it during the dev
// validation above: inspect ContainerAppSystemLogs_CL during a forced infra
// failure, then `union` an execution-failure clause into `failureQuery`. Left out
// here deliberately rather than shipped as unverified KQL. (Tracked as a follow-up.)


// ── OTP VERIFICATION REQUIREMENT (ADO 11662) ─────────────────────────────────
// Since 17 Jul 2026 Azure Monitor requires a one-time passcode before a NEWLY
// added email address receives anything from an action group. A pipeline cannot
// receive or enter that passcode, so a deploy that introduces a new address
// SUCCEEDS while that recipient silently receives nothing. Azure still reports
// the action group as healthy. There is no error to catch.
//
// Rules for changing alertEmailAddresses:
//
//  1. APPEND ONLY — never insert. Receivers are named positionally
//     (jobalerts-${i}), so inserting an address anywhere but the end renames
//     every receiver after it. Azure then sees receivers changing identity
//     rather than one being added, which may re-challenge people who were
//     already verified. Add new addresses to the END of the array.
//
//  2. A brand-new address needs a human to complete the passcode within 30
//     MINUTES of the deploy. Schedule the deploy for when that person is at
//     their desk. If the code expires, use Resend on the action group blade —
//     do not redeploy to force a new code.
//
//  3. Verification persists per address per TENANT, across existing and future
//     action groups. An address already verified anywhere in ROMTech needs no
//     further action here.
//
//  4. Do NOT add a `status` property to emailReceivers. It is response-side;
//     writing 'Enabled' does not bypass verification.
//
//  5. AFTER any deploy that changes alertEmailAddresses, run the check:
//       ./scripts/04-verify-receivers.sh --verified ./state/verified-addresses.txt
//     exit 0 = clear · exit 3 = an unverified recipient · exit 2 = incomplete
//     coverage, which is NOT a pass.
//
// Runbook: <https://dev.azure.com/ROMTechInc/ROMTech%20Solutions/_wiki/wikis/ROMTech-Solutions.wiki/1059/Adding-an-email-recipient-to-an-Azure-Monitor-action-group-(OTP-verification)>      
// Work item: ADO 11662

param envName string = 'Dev'
param location string = 'eastus'
// Log Analytics workspace the ACA environment logs to (main.bicep: cdb-workspace-<env>).
param workspaceName string
// Recipients for the failure email (inboxes/DLs we own). Empty => caller should
// not deploy this module (main.bicep gates on non-empty).
param alertEmailAddresses array

resource workspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = {
  name: workspaceName
}

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-cgfe-jobs-${toLower(envName)}'
  location: 'global'
  properties: {
    groupShortName: 'cgfejobs'
    enabled: true
    emailReceivers: [for (email, i) in alertEmailAddresses: {
      name: 'jobalerts-${i}'
      emailAddress: email
      useCommonAlertSchema: true
    }]
  }
}

// Scope to our jobs by ContainerGroupName_s — the job EXECUTION name, e.g.
// 'job-cgfe-cleanup-dev-<exec>'. ⚠️ ACA JOBS leave ContainerAppName_s EMPTY (only
// apps populate it), so the job identity lives in ContainerGroupName_s — verified
// against a real dev failure 2026-07-22. `startswith 'job-cgfe-'` matches both
// jobs across the execution suffix and excludes the apps (containers
// litellm/librechat/ragapi), so app traffic can't trip it.
// FAILURE-ONLY markers: `[ERROR]` (both scripts log it only on real failures),
// the sync job's explicit `SYNC_SUMMARY status=failed`, and `Traceback` (an
// exception that escaped main()). Deliberately NOT bare 'canary' / 'circuit
// breaker' — those appear in HEALTHY logs and would false-alarm.
// NB: single-quoted (interpolated) string — Bicep triple-quote strings do NOT
// interpolate.
var failureQuery = 'ContainerAppConsoleLogs_CL\n| where ContainerGroupName_s startswith \'job-cgfe-\'\n| where Log_s contains \'[ERROR]\' or Log_s contains \'SYNC_SUMMARY status=failed\' or Log_s contains \'Traceback (most recent call last)\''

resource jobFailureAlert 'Microsoft.Insights/scheduledQueryRules@2022-06-15' = {
  name: 'alert-cgfe-job-failure-${toLower(envName)}'
  location: location
  properties: {
    displayName: 'CGFE scheduled job failure (${envName})'
    description: 'Fires when the Okta sync or nightly cleanup ACA job logs a failure.'
    severity: 2
    enabled: true
    // Hourly evaluation over a 2h window (overlapping) so a failure whose log is
    // ingested a few minutes late can't slip between a 1h window and the next
    // evaluation. autoMitigate + the once-nightly cadence prevent double-alerting.
    evaluationFrequency: 'PT1H'
    windowSize: 'PT2H'
    // The workspace-wide _CL table always pre-exists (the always-on apps log to it
    // continuously), but skip PUT-time query validation so a first-ever deploy into
    // a brand-new workspace can't fail on a not-yet-created table.
    skipQueryValidation: true
    scopes: [
      workspace.id
    ]
    criteria: {
      allOf: [
        {
          query: failureQuery
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    autoMitigate: true
    actions: {
      actionGroups: [
        actionGroup.id
      ]
    }
  }
}

output actionGroupId string = actionGroup.id
output alertRuleId string = jobFailureAlert.id
